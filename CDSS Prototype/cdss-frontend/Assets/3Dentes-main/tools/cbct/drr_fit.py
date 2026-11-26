#!/usr/bin/env python3
"""Fit the exposure geometry to a REAL radiograph, then say what still differs.

    ~/projects/3Dentes-cbct/nnunet-venv/bin/python tools/cbct/drr_fit.py \
        --pa <image.jpg> --teeth 31 30 29 --out-dir /tmp/fit

Phase 5 of docs/drr-plan.md. Until the projection is fitted, every difference
between our radiograph and the operator's own is confounded with the fact that
we guessed his angulation, his source distance and his sensor size. Fitting
first is what turns "these look different" into a statement about the MODEL.

WHAT IS FITTED, and why it is only this. Two geometric parameters that need a
re-render -- tube vertical angulation and receptor tilt -- plus a 2D similarity
(shift, rotation, scale) that does not. The similarity absorbs sensor size and
source distance, which trade off against each other and cannot be separated
from a single projection; the fitted scale is REPORTED so it can be sanity
checked against a real size-2 sensor rather than hidden.

WHY GRADIENTS, NOT GREY LEVELS. Our bone is a homogeneous slab and his is full
of trabeculae, so matching intensities would score mostly that known absence and
would be driven by it. Gradient magnitude keys on the strong edges -- tooth
outlines, the crown, canal walls, the crestal bone -- which are the things this
model actually claims to get right. It is a deliberately narrower question, and
the honest one to ask.
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drr_mesh as dm


def grad(img):
    gx = ndi.sobel(img, axis=1, mode="nearest")
    gy = ndi.sobel(img, axis=0, mode="nearest")
    g = np.hypot(gx, gy)
    return g / (g.std() + 1e-9)


def window(tau, metal_free, lo=2.0, hi=99.5):
    ref = tau[metal_free] if metal_free.any() else tau
    a, b = np.percentile(ref, [lo, hi])
    return np.clip((tau - a) / max(b - a, 1e-9), 0, 1)


def ncc(a, b, mask):
    x, y = a[mask], b[mask]
    x = x - x.mean(); y = y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d > 0 else -1.0


def warp(src, shape, dx, dy, theta, scale):
    """Similarity map from the DRR grid onto the reference grid."""
    c = np.cos(np.radians(theta)) / scale
    s = np.sin(np.radians(theta)) / scale
    M = np.array([[c, -s], [s, c]])
    centre_out = np.array(shape) / 2.0
    centre_in = np.array(src.shape) / 2.0
    off = centre_in - M @ (centre_out + np.array([dy, dx]))
    return ndi.affine_transform(src, M, offset=off, output_shape=shape,
                                order=1, mode="constant", cval=0.0)


def fit_inplane(drr_g, pa_g, x0=(0, 0, 0, 1.0)):
    inner = np.zeros(pa_g.shape, bool)
    m = int(0.06 * min(pa_g.shape))
    inner[m:-m, m:-m] = True
    max_shift = 0.18 * min(pa_g.shape)

    def cost(p):
        dx, dy, th, sc = p
        # AN OBJECTIVE SCORED OVER THE OVERLAP REWARDS HAVING NO OVERLAP.
        #
        # The first version computed NCC over `w != 0`, so sliding the DRR off
        # the frame shrank the mask until a handful of pixels could correlate by
        # chance -- and it duly "found" shifts of 80 and 108 px with a better
        # score than any real alignment. The area has to be held roughly fixed
        # for the comparison to mean anything, so overlap is required rather
        # than allowed to be traded away.
        if not (0.55 < sc < 1.8) or abs(th) > 25:
            return 2.0
        if abs(dx) > max_shift or abs(dy) > max_shift:
            return 2.0
        w = warp(drr_g, pa_g.shape, dx, dy, th, sc)
        mask = inner & (w != 0)
        if mask.sum() < 0.55 * inner.sum():
            return 2.0
        return -ncc(w, pa_g, mask)

    best = None
    for s0 in (0.8, 1.0, 1.25):
        r = minimize(cost, [x0[0], x0[1], x0[2], s0], method="Powell",
                     options={"xtol": 0.4, "ftol": 1e-3, "maxiter": 2000})
        if best is None or r.fun < best.fun:
            best = r
    return best.x, -best.fun


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pa", required=True)
    ap.add_argument("--teeth", nargs=3, type=int, default=[31, 30, 29])
    ap.add_argument("--kvp", type=float, default=70.0)
    ap.add_argument("--px", type=int, default=310)
    ap.add_argument("--out-dir", default="/tmp/drr-fit")
    ap.add_argument("--verts", nargs="+", type=float, default=[-6, -1, 4, 9, 14])
    ap.add_argument("--tilts", nargs="+", type=float, default=[0, 5, 10, 15, 20])
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    from PIL import Image
    pa_full = Image.open(args.pa).convert("L")
    mu, keV = dm.mu_at(args.kvp)
    scene = dm.build_scene(args.teeth, radius_mm=30)
    print(f"{len(scene['tris'])} meshes  ·  {args.kvp:.0f} kVp -> {keV:.1f} keV")

    probe, _ = dm.render_tau(scene, mu, args.px)
    h_px = probe.shape[0]
    pa = np.asarray(pa_full.resize((args.px, h_px), Image.LANCZOS)).astype(float) / 255
    pa_g = grad(pa)

    rows = []
    for tilt in args.tilts:
        for vert in args.verts:
            tau, L = dm.render_tau(scene, mu, args.px, tilt=tilt, vert=vert)
            free = np.asarray(L["zirconia"]) <= 0
            img = window(tau, free)
            p, score = fit_inplane(grad(img), pa_g)
            rows.append((score, tilt, vert, p, img))
            print(f"  tilt {tilt:5.1f}  tube {vert:5.1f}   NCC {score:.4f}"
                  f"   (shift {p[0]:+.1f},{p[1]:+.1f} px  rot {p[2]:+.1f}deg"
                  f"  scale {p[3]:.3f})")

    rows.sort(key=lambda r: -r[0])
    score, tilt, vert, p, img = rows[0]
    print(f"\nBEST  tilt {tilt}deg  tube {vert}deg  NCC {score:.4f}"
          f"  scale {p[3]:.3f}  rot {p[2]:+.1f}deg")

    # The fitted scale implies a sensor width, which is a claim that can be
    # checked against the real thing rather than accepted because it fitted.
    from drr_volume import RECEPTOR_W_MM
    implied = RECEPTOR_W_MM / p[3]
    print(f"implied sensor width {implied:.1f} mm "
          f"(a size-2 intraoral sensor is about 35-41 mm wide)")

    warped = warp(img, pa_g.shape, *p)
    Image.fromarray((np.clip(warped, 0, 1) * 255).astype(np.uint8)).save(
        os.path.join(args.out_dir, "drr-fitted.png"))
    Image.fromarray((pa * 255).astype(np.uint8)).save(
        os.path.join(args.out_dir, "pa-resampled.png"))
    rgb = np.zeros(pa.shape + (3,), np.uint8)
    rgb[..., 0] = (np.clip(pa, 0, 1) * 255).astype(np.uint8)
    rgb[..., 1] = (np.clip(warped, 0, 1) * 255).astype(np.uint8)
    rgb[..., 2] = rgb[..., 1]
    Image.fromarray(rgb).save(os.path.join(args.out_dir, "overlay.png"))

    json.dump({
        "pa": os.path.abspath(args.pa), "teeth": args.teeth, "kvp": args.kvp,
        "best": {"receptor_tilt_deg": tilt, "tube_vertical_deg": vert,
                 "ncc_gradient": round(score, 4),
                 "shift_px": [round(p[0], 2), round(p[1], 2)],
                 "rotation_deg": round(p[2], 2), "scale": round(p[3], 4),
                 "implied_sensor_width_mm": round(implied, 1)},
        "grid": [{"tilt": t, "vert": v, "ncc": round(sc, 4)}
                 for sc, t, v, _, _ in rows],
        "caveat": "Gradient NCC, not intensity: our bone is homogeneous and the "
                  "real film is trabeculated, so an intensity match would score "
                  "mostly that known absence. This measures agreement of EDGES.",
    }, open(os.path.join(args.out_dir, "fit.json"), "w"), indent=2)
    print(f"-> {args.out_dir}")


if __name__ == "__main__":
    main()
