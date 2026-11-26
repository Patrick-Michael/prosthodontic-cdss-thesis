#!/usr/bin/env python3
"""Compare the model against a real radiograph WITHOUT fitting a projection.

    ~/projects/3Dentes-cbct/nnunet-venv/bin/python tools/cbct/drr_validate.py \
        --pa <image.jpg>

Phase 5 of docs/drr-plan.md, after the registration in drr_fit.py failed.

WHY NOT REGISTRATION. Fitting the projection by maximising gradient correlation
did not converge: scores spanned 0.04-0.14 with no basin, the best parameters
were unstable across a coarse grid, and the fitted scale implied a 56 mm sensor
against a real size-2 sensor's 35-41 mm. Two reasons, both structural rather
than fixable by tuning. The real film is full of trabecular texture that our
homogeneous bone has nothing to match, and OUR film has strong edges the real
one does not -- the ligament and lamina dura are drawn at 0.32 mm against a true
~0.2 mm, so they dominate our gradient image. Correlating those two gradient
fields mostly measures their disagreement about texture.

SO ASK A QUESTION THAT NEEDS NO FIT. The zirconia crown is the one structure
both images segment trivially and unambiguously: it is far denser than any
tissue in either. Its SHAPE RATIOS -- aspect and fill -- are invariant to scale
and to where the film sat, so they can be compared directly. That is a narrow
claim, and it is a real one.
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drr_mesh as dm


def shape_of(mask, label):
    lab, n = ndi.label(mask)
    if n == 0:
        return None
    sizes = ndi.sum(mask, lab, range(1, n + 1))
    keep = lab == (int(np.argmax(sizes)) + 1)
    ys, xs = np.where(keep)
    w = xs.max() - xs.min() + 1
    h = ys.max() - ys.min() + 1
    return {"label": label, "w_px": int(w), "h_px": int(h),
            "aspect_w_over_h": round(float(w) / h, 3),
            "fill_of_bbox": round(float(keep.sum()) / (w * h), 3),
            "area_px": int(keep.sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pa", required=True)
    ap.add_argument("--kvp", type=float, default=70.0)
    ap.add_argument("--px", type=int, default=900)
    ap.add_argument("--tilt", type=float, default=0.0)
    ap.add_argument("--vert", type=float, default=0.0)
    ap.add_argument("--sweep", action="store_true",
                    help="search angulations for the one matching the real crown")
    args = ap.parse_args()

    from PIL import Image
    pa = np.asarray(Image.open(args.pa).convert("L")).astype(float)
    # The crown is unmistakable: it sits ~214 against at most ~145 for any
    # tissue. A cut midway between needs no tuning and no Otsu.
    pa_crown = pa >= 180
    real = shape_of(pa_crown, "real PA")

    mu, keV = dm.mu_at(args.kvp)
    scene = dm.build_scene([31, 30, 29], radius_mm=30)
    _, L = dm.render_tau(scene, mu, args.px, tilt=args.tilt, vert=args.vert)
    z = np.asarray(L["zirconia"])
    sim = shape_of(z > 0.5, "geometry DRR")

    print(f"{'':16s} {'w px':>6s} {'h px':>6s} {'aspect w/h':>11s} {'fill of bbox':>13s}")
    for r in (real, sim):
        print(f"{r['label']:16s} {r['w_px']:6d} {r['h_px']:6d} "
              f"{r['aspect_w_over_h']:11.3f} {r['fill_of_bbox']:13.3f}")

    if args.sweep:
        # A single arbitrary geometry proves nothing either way: aspect is
        # strongly angulation-dependent, so comparing at paralleling when the
        # real exposure was not taken at paralleling measures the angulation,
        # not the model. Search instead, and report how close the best
        # CLINICALLY ORDINARY geometry comes.
        print(f"\nsweeping angulations against the real crown "
              f"(aspect {real['aspect_w_over_h']}, fill {real['fill_of_bbox']})")
        print(f"{'tilt':>5s} {'tube':>5s} {'aspect':>8s} {'d aspect':>9s} "
              f"{'fill':>7s} {'d fill':>8s}")
        best = None
        for tilt in (0, 5, 8, 10, 12):
            for vert in (2, 3, 4, 5, 6):
                _, Ls = dm.render_tau(scene, mu, args.px, tilt=tilt, vert=vert)
                sh = shape_of(np.asarray(Ls["zirconia"]) > 0.5, "sim")
                da_ = 100 * (sh["aspect_w_over_h"] - real["aspect_w_over_h"]) / real["aspect_w_over_h"]
                df_ = 100 * (sh["fill_of_bbox"] - real["fill_of_bbox"]) / real["fill_of_bbox"]
                print(f"{tilt:5d} {vert:5d} {sh['aspect_w_over_h']:8.3f} {da_:+8.1f}% "
                      f"{sh['fill_of_bbox']:7.3f} {df_:+7.1f}%")
                if best is None or abs(da_) + abs(df_) < best[0]:
                    best = (abs(da_) + abs(df_), tilt, vert, da_, df_)
        print(f"\nBEST tilt {best[1]}deg tube {best[2]}deg -> "
              f"aspect {best[3]:+.1f}%, fill {best[4]:+.1f}%")

    da = abs(real["aspect_w_over_h"] - sim["aspect_w_over_h"])
    df = abs(real["fill_of_bbox"] - sim["fill_of_bbox"])
    rel = 100 * da / real["aspect_w_over_h"]
    print(f"\naspect differs by {da:.3f} ({rel:.1f}%), fill by {df:.3f}")
    print("Both are scale-invariant, so neither depends on sensor size, source "
          "distance or where the film sat.")
    json.dump({"real": real, "simulated": sim,
               "aspect_abs_diff": round(da, 4),
               "aspect_pct_diff": round(rel, 2),
               "fill_abs_diff": round(df, 4)},
              open("/tmp/drr-crown-compare.json", "w"), indent=2)


if __name__ == "__main__":
    main()
