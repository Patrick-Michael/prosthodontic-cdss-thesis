#!/usr/bin/env python3
"""DRR by ray-integrating the SHIPPED MESHES, not the volume.

    ~/projects/3Dentes-cbct/nnunet-venv/bin/python tools/cbct/drr_mesh.py \
        --teeth 31 30 29 --kvp 70 --out /tmp/drr-mesh.png

Phase 3 of docs/drr-plan.md, on the CPU. The browser will do this on the GPU,
but the ALGORITHM is identical and this version can be checked against the
Phase 0 volume reference and against the operator's own periapical -- so when
the shader disagrees with this, the shader is what is wrong.

THE ALGORITHM. For a closed surface, the path length a ray spends inside it is

    sum(distance at back faces) - sum(distance at front faces)

because the ray alternates in and out and every entry has a matching exit. That
is exact, needs no sorting, and is why Phase 2 spent its effort making every
mesh closed and outward-wound: an inverted solid subtracts itself, and an open
one lets a ray in that never comes out.

It also means NO CSG IS NEEDED for tissues that nest. Dentin is not modelled;
it is the tooth less its enamel, pulp and crown, subtracted per pixel after the
fact. Trabecular bone is the bone mesh less the lamina dura that sits inside it.

Attenuation then follows Beer-Lambert with mu(E) from public/attenuation.json,
which carries composition and density per tissue rather than a baked
coefficient. Monoenergetic, by the operator's decision on 2026-09-05: the
crowns will read as flat white silhouettes and that is an ACCEPTED ARTEFACT,
not a bug to hunt.
"""
import argparse
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STL_DIR = os.path.join(ROOT, "assets", "cbct", "stl")

# Which tissue each layer's meshes are made of. Layers absent here contribute
# nothing: nerves and vessels are soft tissue inside bone and their own
# attenuation is far below the geometric error, so drawing them would add
# nothing a reader could see.
LAYER_TISSUE = {
    "teeth": "tooth", "enamel": "enamel", "pulp": "pulp", "pdl": "pdl",
    "lamina": "corticalBone", "prosthetic": "zirconia",
    "mandible": "bone", "maxilla": "bone", "midface": "bone", "ramus": "bone",
    "gingiva": "gingiva",
}


def load_stl(path):
    with open(path, "rb") as f:
        b = f.read()
    n = struct.unpack("<I", b[80:84])[0]
    a = np.frombuffer(b[84:84 + n * 50], dtype=np.uint8).reshape(n, 50)
    return a[:, 12:48].copy().view("<f4").reshape(n, 3, 3).astype(np.float64)


def accumulate(tris, source, corner, u_ax, v_ax, pw, ph, w_px, h_px, out):
    """Rasterise triangles, accumulating SIGNED distance-from-source per pixel.

    Back faces add and front faces subtract, so the total is the path length
    the ray spends inside the surface. Depth is computed analytically from the
    triangle's own plane rather than interpolated, so it is exact at every
    pixel and needs no perspective correction.
    """
    n_t = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n_t, axis=1)
    good = ln > 1e-12
    tris, n_t, ln = tris[good], n_t[good], ln[good]
    n_t /= ln[:, None]

    # Project every vertex onto the receptor plane through the source.
    plane_n = np.cross(u_ax, v_ax)
    plane_n /= np.linalg.norm(plane_n)
    d0 = np.dot(corner, plane_n)
    flat = tris.reshape(-1, 3)
    dirs = flat - source
    denom = dirs @ plane_n
    denom[np.abs(denom) < 1e-12] = 1e-12
    t = (d0 - source @ plane_n) / denom
    hit = source + dirs * t[:, None]
    rel = hit - corner
    px = (rel @ u_ax) / pw - 0.5
    py = -(rel @ v_ax) / ph - 0.5
    P = np.stack([px, py], 1).reshape(-1, 3, 2)
    behind = (t <= 0).reshape(-1, 3).any(1)

    for k in range(len(tris)):
        if behind[k]:
            continue
        a, b, c = P[k]
        x0 = int(np.floor(min(a[0], b[0], c[0]))); x1 = int(np.ceil(max(a[0], b[0], c[0])))
        y0 = int(np.floor(min(a[1], b[1], c[1]))); y1 = int(np.ceil(max(a[1], b[1], c[1])))
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, w_px - 1), min(y1, h_px - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1); ys = np.arange(y0, y1 + 1)
        gx, gy = np.meshgrid(xs, ys)
        d1 = b - a; d2 = c - a
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-12:
            continue
        wx = gx - a[0]; wy = gy - a[1]
        s = (wx * d2[1] - wy * d2[0]) / det
        r = (wy * d1[0] - wx * d1[1]) / det
        inside = (s >= 0) & (r >= 0) & (s + r <= 1)
        if not inside.any():
            continue
        # Exact ray/plane distance for the pixels this triangle covers.
        cen = (corner[None, :]
               + u_ax[None, :] * (pw * (gx[inside] + 0.5))[:, None]
               + v_ax[None, :] * (-ph * (gy[inside] + 0.5))[:, None])
        rd = cen - source
        rd /= np.linalg.norm(rd, axis=1)[:, None]
        R = np.linalg.norm(cen - source, axis=1)      # source -> this receptor pixel
        nd = rd @ n_t[k]
        nd[np.abs(nd) < 1e-9] = 1e-9
        dist = ((tris[k, 0] - source) @ n_t[k]) / nd
        # THE RECEPTOR IS OPAQUE, SO CLIP EVERY INTERSECTION TO IT.
        #
        # Without this the mesh DRR integrates the far side of the mandible on
        # the way out and the image doubles -- the same defect the volume DRR
        # had in Phase 0, arriving again in a different substrate.
        #
        # Clamping each distance to the receptor's own distance is exactly
        # right, not an approximation, because path length is a difference of
        # distances: a solid wholly behind the sensor contributes R - R = 0, one
        # wholly in front is untouched, and one straddling the plane contributes
        # R - d_front, which is precisely the part in front.
        dist = np.minimum(dist, R)
        sign = np.where(nd < 0, -1.0, 1.0)     # normal toward source = front face
        np.add.at(out, (gy[inside], gx[inside]), sign * dist)


def build_scene(teeth_universal, radius_mm=None):
    """Everything that does not change while fitting: meshes, frame, densities.

    `radius_mm` culls to structures near the target. A periapical sees maybe a
    third of the mouth, and the rasteriser costs per TRIANGLE, so dropping the
    far side is most of the speed when a fit has to render the same scene
    dozens of times. It changes nothing in the image: a mesh that projects
    outside the receptor contributes no pixels either way.
    """
    from drr_volume import frame, tooth_index
    idx = tooth_index()
    distal_u, target_u, mesial_u = teeth_universal
    verts = {u: load_stl(os.path.join(STL_DIR, f"{idx[u]}.stl")).reshape(-1, 3)
             for u in teeth_universal}
    arch = np.concatenate([load_stl(os.path.join(STL_DIR, f"{f}.stl")).reshape(-1, 3)
                           for f in idx.values()])
    u_ax, v_ax, buccal = frame(verts[target_u], arch, verts[mesial_u], verts[distal_u])
    meta = json.load(open(os.path.join(ROOT, "public", "teeth.json")))["structures"]
    tris = []
    for fma, st in meta.items():
        tissue = LAYER_TISSUE.get(st["layer"])
        if tissue is None:
            continue
        f = os.path.join(STL_DIR, f"{fma}.stl")
        if not os.path.exists(f):
            continue
        t = load_stl(f)
        if radius_mm is not None:
            c = t.reshape(-1, 3).mean(0)
            reach = np.linalg.norm(t.reshape(-1, 3) - c, axis=1).max()
            if np.linalg.norm(c - verts[target_u].mean(0)) - reach > radius_mm:
                continue
        tris.append((tissue, t))
    return {"u": u_ax, "v": v_ax, "buccal": buccal,
            "target": verts[target_u].mean(0), "tris": tris,
            "apical": -1.0 if target_u <= 16 else 1.0}


def render_tau(scene, mu, px, vshift=-4.0, tilt=0.0, vert=0.0,
               offset=None, srd=None, w_mm=None, h_mm=None):
    """Path integral image for one exposure geometry. Returns (tau, h_px)."""
    from drr_volume import (RECEPTOR_W_MM, RECEPTOR_H_MM, RECEPTOR_OFFSET_MM,
                            SRD_MM)
    W = RECEPTOR_W_MM if w_mm is None else w_mm
    H = RECEPTOR_H_MM if h_mm is None else h_mm
    OFF = RECEPTOR_OFFSET_MM if offset is None else offset
    SRD = SRD_MM if srd is None else srd
    u_ax, v_ax, buccal = scene["u"], scene["v"], scene["buccal"]

    def rot(vec, axis, deg):
        a = np.radians(deg)
        axis = axis / np.linalg.norm(axis)
        return (vec * np.cos(a) + np.cross(axis, vec) * np.sin(a)
                + axis * axis.dot(vec) * (1 - np.cos(a)))

    vr = rot(v_ax, u_ax, tilt)
    centre_r = (scene["target"] - buccal * OFF + vr * (vshift * scene["apical"]))
    beam = rot(-buccal, u_ax, vert)
    source = scene["target"] - beam * SRD
    horiz = np.cross(vr, buccal)
    horiz /= np.linalg.norm(horiz)

    h_px = int(round(px * H / W))
    pw, ph = W / px, H / h_px
    corner = centre_r - horiz * W / 2 + vr * H / 2

    paths = {}
    for tissue, tri in scene["tris"]:
        paths.setdefault(tissue, np.zeros((h_px, px)))
        accumulate(tri, source, corner, horiz, vr, pw, ph, px, h_px, paths[tissue])

    L = {
        "enamel": paths.get("enamel", 0.0),
        "pulp": paths.get("pulp", 0.0),
        "zirconia": paths.get("zirconia", 0.0),
        "corticalBone": paths.get("corticalBone", 0.0),
        "pdl": paths.get("pdl", 0.0),
        "gingiva": paths.get("gingiva", 0.0),
    }
    L["dentin"] = np.clip(paths.get("tooth", 0.0) - L["enamel"] - L["pulp"]
                          - L["zirconia"], 0, None)
    L["trabecularBone"] = np.clip(paths.get("bone", 0.0) - L["corticalBone"], 0, None)
    tau = np.zeros((h_px, px))
    for name, l in L.items():
        if not np.isscalar(l):
            tau += mu[name] * l
    return tau, L


def mu_at(kvp):
    att = json.load(open(os.path.join(ROOT, "public", "attenuation.json")))
    keV = kvp * att["effective_fraction"]
    ei = int(np.argmin(np.abs(np.array(att["energies_keV"], float) - keV)))
    return {k: v["mu_per_mm"][ei] for k, v in att["tissues"].items()}, keV


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teeth", nargs=3, type=int, default=[31, 30, 29])
    ap.add_argument("--kvp", type=float, default=70.0)
    ap.add_argument("--out", default="/tmp/drr-mesh.png")
    ap.add_argument("--px", type=int, default=900)
    ap.add_argument("--vshift", type=float, default=-4.0)
    ap.add_argument("--window", nargs=2, type=float, default=[2.0, 99.5])
    ap.add_argument("--gamma", type=float, default=1.0)
    args = ap.parse_args()

    from drr_volume import (RECEPTOR_W_MM, RECEPTOR_H_MM, RECEPTOR_OFFSET_MM,
                            SRD_MM, frame, tooth_index)

    att = json.load(open(os.path.join(ROOT, "public", "attenuation.json")))
    meta = json.load(open(os.path.join(ROOT, "public", "teeth.json")))["structures"]
    keV = args.kvp * att["effective_fraction"]
    ei = int(np.argmin(np.abs(np.array(att["energies_keV"], float) - keV)))
    mu = {k: v["mu_per_mm"][ei] for k, v in att["tissues"].items()}
    print(f"{args.kvp:.0f} kVp -> {keV:.1f} keV effective "
          f"(table row {att['energies_keV'][ei]} keV)")

    idx = tooth_index()
    distal_u, target_u, mesial_u = args.teeth
    verts = {u: load_stl(os.path.join(STL_DIR, f"{idx[u]}.stl")).reshape(-1, 3)
             for u in args.teeth}
    arch = np.concatenate([load_stl(os.path.join(STL_DIR, f"{f}.stl")).reshape(-1, 3)
                           for f in idx.values()])
    u_ax, v_ax, buccal = frame(verts[target_u], arch, verts[mesial_u], verts[distal_u])
    target = verts[target_u].mean(0)
    # Apical framing, in whichever direction the apex actually lies: the
    # receptor's vertical points superior, which is apex-ward in the maxilla
    # and crown-ward in the mandible. Universal 1-16 is the upper arch.
    apical = -1.0 if target_u <= 16 else 1.0
    receptor_c = (target - buccal * RECEPTOR_OFFSET_MM
                  + v_ax * (args.vshift * apical))
    source = receptor_c + buccal * SRD_MM

    h_px = int(round(args.px * RECEPTOR_H_MM / RECEPTOR_W_MM))
    pw, ph = RECEPTOR_W_MM / args.px, RECEPTOR_H_MM / h_px
    corner = receptor_c - u_ax * RECEPTOR_W_MM / 2 + v_ax * RECEPTOR_H_MM / 2

    paths = {}
    n_meshes = 0
    for fma, s in meta.items():
        tissue = LAYER_TISSUE.get(s["layer"])
        if tissue is None:
            continue
        p = os.path.join(STL_DIR, f"{fma}.stl")
        if not os.path.exists(p):
            continue
        paths.setdefault(tissue, np.zeros((h_px, args.px)))
        accumulate(load_stl(p), source, corner, u_ax, v_ax, pw, ph,
                   args.px, h_px, paths[tissue])
        n_meshes += 1
    print(f"integrated {n_meshes} meshes into {len(paths)} tissue channels")

    # NESTED TISSUES COME OUT BY SUBTRACTION, not by CSG. Clamped at zero: a
    # small negative is a mesh whose child pokes marginally outside its parent,
    # which is a geometry question and not something to smuggle in as negative
    # attenuation.
    L = {}
    L["enamel"] = paths.get("enamel", 0)
    L["pulp"] = paths.get("pulp", 0)
    L["zirconia"] = paths.get("zirconia", 0)
    L["dentin"] = np.clip(paths.get("tooth", 0) - L["enamel"] - L["pulp"]
                          - L["zirconia"], 0, None)
    L["corticalBone"] = paths.get("corticalBone", 0)
    L["trabecularBone"] = np.clip(paths.get("bone", 0) - L["corticalBone"], 0, None)
    L["pdl"] = paths.get("pdl", 0)
    L["gingiva"] = paths.get("gingiva", 0)

    acc = np.zeros((h_px, args.px))
    print(f"\n{'tissue':16s} {'mu/mm':>8s} {'max path mm':>12s} {'mean tau':>10s}")
    for name, l in L.items():
        if np.isscalar(l):
            continue
        acc += mu[name] * l
        print(f"{name:16s} {mu[name]:8.4f} {l.max():12.2f} {(mu[name]*l).mean():10.3f}")

    # WINDOW ON THE ANATOMY, AND LET THE METAL CLIP.
    #
    # The crown reaches an optical depth of ~127 while every dental tissue sits
    # between 1 and 5, so a percentile taken over the whole image is set by the
    # zirconia and crushes the anatomy into the bottom few grey levels -- which
    # is exactly what the first render did. A real sensor does not behave that
    # way either: its range is finite, the restoration saturates, and the tissue
    # around it still uses the full scale.
    #
    # So the window is taken over pixels the metal does not touch. This is the
    # same decision a clinician makes at the console, and it is the display
    # standing in for the polyenergetic beam we chose not to model.
    free = np.asarray(L["zirconia"]) <= 0 if not np.isscalar(L["zirconia"]) \
        else np.ones_like(acc, bool)
    ref = acc[free] if free.any() else acc
    lo, hi = np.percentile(ref, args.window)
    print(f"window {lo:.2f}-{hi:.2f} tau over {100*free.mean():.0f}% metal-free pixels; "
          f"peak tau {acc.max():.0f}")
    img = np.clip((acc - lo) / max(hi - lo, 1e-9), 0, 1) ** args.gamma
    from PIL import Image
    Image.fromarray((img * 255).astype(np.uint8)).save(args.out)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
