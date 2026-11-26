#!/usr/bin/env python3
"""Emit the measured trabecular modulation field the DRR samples.

WHAT THIS SHIPS. The fine-scale density variation of this patient's own bone,
measured from the CBCT and resampled onto an app-space grid. Not a procedural
texture, not a noise function fitted to look plausible -- the actual field,
downsampled.

WHY IT IS DEFENSIBLE, and where the line is. The PATTERN and its RELATIVE
variation are measured. The ABSOLUTE SCALE is not: nrrd/volumes.json records
these as "int16, Hounsfield-like; NOT calibrated HU", so turning a grey-value
residual into g/cm3 needs a coefficient that comes from literature, not from
here. Provenance is therefore **pattern measured, scale derived** -- stronger
than a synthesised texture, weaker than `measured`, and it must be labelled as
the former.

THE EVIDENCE THAT THERE IS A PATTERN AT ALL is in docs/wishlist.md under
"MEASURED 2026-09-06": bone shows sustained excess autocorrelation along z and
transverse anticorrelation at 0.8-2 mm, against soft-tissue and air controls put
through the identical filter. Critically, the controls' own anisotropy runs
y > z > x while bone's runs z > y = x, so the orientation is the patient's and
not the reconstruction's.

THE SAMPLING IS 0.48 mm AND THAT IS A BUDGET DECISION, made against measured
amplitude retention rather than by eye:

    sampling   amplitude kept   raw size
    0.16 mm         100%         111 MB      unshippable
    0.32 mm          83%          13.9 MB    +63% on a 16 MB build
    0.48 mm          70%           4.1 MB    +19%
    0.64 mm          58%           1.7 MB
    0.80 mm          49%           0.9 MB

0.48 mm keeps 70% of the SD 198.5 modulation for 4.1 MB. Note this survives
downsampling BETTER than textbook trabecular spacing (0.5-1.5 mm) would suggest,
because 0.16 mm CBCT with its blur only ever resolved the coarse end: the
measured transverse scale is 0.8-2 mm.

NOT MEASURED BY AUTOCORRELATION SURVIVAL. Block-averaging is a low-pass and
INFLATES autocorrelation between neighbouring samples, so a coarser field scores
higher on that test while carrying less. Amplitude is what degrades and what is
seen on a film.

KNOWN WASTE. Bone fills 9% of its own bounding box, so ~91% of this file is
empty space at 128. A sparse brick layout would carry the same fidelity in about
1.5 MB, and needs an indirection table in drr.js. Worth doing if the budget ever
tightens; not worth doing first.

Usage: trabecular_field.py <volume.nrrd> <residual.npy> <teeth.json> <out-dir>
                           [--sampling-mm 0.48] [--highpass-mm 2.0] [--clip-sd 4.0]
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vol import Volume


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("volume")
    ap.add_argument("residual")
    ap.add_argument("teeth_json")
    ap.add_argument("outdir")
    ap.add_argument("--sampling-mm", type=float, default=0.48)
    ap.add_argument("--highpass-mm", type=float, default=2.0)
    ap.add_argument("--clip-sd", type=float, default=4.0)
    ap.add_argument("--near-teeth-mm", type=float, default=25.0)
    ap.add_argument("--shell-mm", type=float, default=0.32)
    ap.add_argument("--split-dir", default=None)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    v = Volume.load(a.volume)
    sp = float(v.spacing[0])
    res = np.load(a.residual)
    if res.shape != v.data.shape:
        sys.exit(f"residual {res.shape} != volume {v.data.shape}")
    frame = json.load(open(a.teeth_json))["frame"]

    factor = int(round(a.sampling_mm / sp))
    if abs(factor * sp - a.sampling_mm) > 1e-9:
        sys.exit(f"--sampling-mm must be a multiple of {sp}; "
                 f"{a.sampling_mm} is not")
    print(f"volume {v.data.shape} at {sp} mm -> factor {factor} "
          f"({factor * sp} mm)")

    # --- what the field is actually ALLOWED to cover -------------------------
    #
    # TWO RESTRICTIONS, both added 2026-09-06 after the maxillary exposures came
    # out unreadable while the mandibular ones were fine.
    #
    # 1. NEAR THE TEETH ONLY. The bone envelope is DentalSegmentator's whole
    #    "Upper Skull" label, and export_bone.py deliberately keeps all of it --
    #    nasal conchae, sinus and orbital walls, zygoma. That is thin convoluted
    #    bone with air on BOTH sides, and its bone/air transitions are far
    #    stronger than any trabecular variation. An upper incisor ray crosses a
    #    great deal of it, so the same gain that is right in the mandible
    #    produced chaos in the maxilla. It is also outside the claim: the
    #    amplitude was fitted against a periapical of alveolar bone, and the
    #    midface was never part of what this measured.
    #
    # 2. NOT THE SURFACE SHELL. Voxels within `shell-mm` of a bone surface are
    #    bone averaged with whatever is beside them, not bone -- the same reason
    #    trabecular_isolate.py discards them before splitting cortex from
    #    medulla. They carry sd 205 against 167 in the interior, and every one
    #    of those excursions is an edge rather than a trabecula.
    keep = res.copy()
    if a.split_dir:
        teeth = ((np.load(os.path.join(a.split_dir, "upper_labels.npy")) > 0)
                 | (np.load(os.path.join(a.split_dir, "lower_labels.npy")) > 0))
        near = ndi.distance_transform_edt(~teeth, sampling=sp) <= a.near_teeth_mm
        print(f"  near teeth (<={a.near_teeth_mm} mm): keeps "
              f"{(keep & near).sum() / keep.sum():.1%} of the bone")
        keep &= near
    if a.shell_mm > 0:
        depth = ndi.distance_transform_edt(res, sampling=sp)
        print(f"  interior (>{a.shell_mm} mm deep): keeps "
              f"{(keep & (depth > a.shell_mm)).sum() / keep.sum():.1%} of that")
        keep &= depth > a.shell_mm
        del depth
    res = keep

    # --- crop to the bone ----------------------------------------------------
    idx = np.argwhere(res)
    lo, hi = idx.min(0), idx.max(0) + 1
    shape = np.array(res.shape)
    # The span must stay a whole number of blocks or the reshape below cannot
    # work. Round it UP, then slide the window back inside the volume; only if
    # the volume itself is smaller than the rounded span does the span shrink,
    # and it shrinks by whole blocks.
    span = np.ceil((hi - lo) / factor).astype(int) * factor
    lo = np.maximum(np.minimum(lo, shape - span), 0)
    span = np.minimum(span, ((shape - lo) // factor) * factor)
    hi = lo + span
    assert not (span % factor).any(), (span, factor)
    sl = tuple(slice(int(p), int(q)) for p, q in zip(lo, hi))
    data = v.data[sl].astype(np.float32)
    mask = res[sl]

    # --- the fine-scale residual --------------------------------------------
    #
    # Subtract a LOCAL mean, not a global or per-depth one. A per-depth-bin
    # global mean leaves every centimetre-scale variation in place, and the
    # first version of this analysis measured that instead of trabeculae. The
    # box is above trabecular spacing and below anatomical scale.
    W = int(round(a.highpass_mm / sp)) | 1
    m = mask.astype(np.float32)
    num = ndi.uniform_filter(data * m, W)
    den = ndi.uniform_filter(m, W)
    fine = (data - np.where(den > 1e-3, num / np.maximum(den, 1e-6), 0.0)) * m
    del num, den, m, data
    sd_native = float(fine[mask].std())

    # --- downsample ----------------------------------------------------------
    #
    # Block MEAN, weighted by the mask, so bone voxels are not diluted by the
    # empty space beside them. A plain mean over the block would pull every
    # sample near a bone surface toward zero and flatten exactly the margin the
    # radiograph reads.
    sh = fine.shape
    assert all(n % factor == 0 for n in sh), sh
    g = tuple(n // factor for n in sh)
    r = (g[0], factor, g[1], factor, g[2], factor)
    acc = fine.reshape(r).sum((1, 3, 5))
    cnt = mask.reshape(r).sum((1, 3, 5)).astype(np.float32)
    small = np.where(cnt > 0, acc / np.maximum(cnt, 1), 0.0).astype(np.float32)
    occ = cnt / (factor ** 3)
    del fine, acc, r
    sd_small = float(small[occ > 0.5].std())
    print(f"fine-scale sd  native {sd_native:.1f} -> {a.sampling_mm} mm "
          f"{sd_small:.1f}  ({sd_small / sd_native:.0%} kept)")

    # --- to app axes ---------------------------------------------------------
    #
    # app = rotate(LPS) - centre, and the rotation sends (x, y, z) to (x, z, -y).
    # That is a pure axis permutation with one sign flip, so it is a transpose
    # and a reverse -- NO INTERPOLATION, and therefore no second smoothing pass
    # on top of the downsample.
    #
    # Volume axes are (lps_z, lps_y, lps_x). The texture wants (app_z, app_y,
    # app_x) in C order, and app_z runs opposite to lps_y, hence the [::-1].
    out = np.ascontiguousarray(small.transpose(1, 0, 2)[::-1])
    occ_out = np.ascontiguousarray(occ.transpose(1, 0, 2)[::-1])

    # World origin of out[0, 0, 0], in app mm. lps_x/lps_z take their minimum
    # there and lps_y its maximum, which is why all three come out as the low
    # corner in app space.
    lps_min = v.origin + lo[::-1] * sp                     # (x, y, z) lps
    lps_max = v.origin + hi[::-1] * sp
    step = a.sampling_mm
    # Use the matrix the build recorded rather than re-deriving the rotation by
    # hand. out[0,0,0] sits at minimum lps_x and lps_z and MAXIMUM lps_y, since
    # app_z runs opposite to lps_y; that corner is the low corner in app space.
    M = np.array(frame["lps_to_app"], float).reshape(4, 4)
    corner = M @ np.array([lps_min[0], lps_max[1], lps_min[2], 1.0])
    # Half a voxel: a sample is the CENTRE of its block, not its corner.
    origin_app = [float(c) + step / 2 for c in corner[:3]]

    # --- quantise ------------------------------------------------------------
    scale = a.clip_sd * sd_small / 127.0
    q = np.clip(np.round(out / scale) + 128, 0, 255).astype(np.uint8)
    clipped = float((np.abs(out) > a.clip_sd * sd_small).mean())
    # Outside bone the field is zero, which is 128 -- no modulation. The DRR only
    # applies this inside a bone mesh anyway, so 128 is a safe fill rather than a
    # value anything depends on.
    q[occ_out <= 0.5] = 128

    path = os.path.join(a.outdir, "trabecular.bin")
    q.tofile(path)
    meta = {
        "note": "Measured fine-scale bone density variation, this patient's own "
                "CBCT. Pattern measured, absolute scale derived -- see the "
                "header of tools/cbct/trabecular_field.py.",
        "provenance": "pattern-measured-scale-derived",
        "file": "trabecular.bin",
        "dtype": "uint8", "layout": "z-major, C order, width = app x",
        "dims_zyx": [int(n) for n in q.shape],
        "spacing_mm": step,
        "origin_app_mm": origin_app,
        "zero_level": 128,
        "units_per_lsb": round(scale, 4),
        "units": "uncalibrated CBCT grey value (int16, Hounsfield-like)",
        "sd_native": round(sd_native, 1),
        "sd_at_sampling": round(sd_small, 1),
        "amplitude_kept": round(sd_small / sd_native, 3),
        "clipped_fraction": round(clipped, 6),
        "highpass_mm": a.highpass_mm,
        "bone_fill_fraction": round(float((occ_out > 0.5).mean()), 4),
        "bytes": int(q.nbytes),
    }
    with open(os.path.join(a.outdir, "trabecular.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  grid      {'x'.join(str(n) for n in q.shape)} (z, y, x)")
    print(f"  origin    {[round(c, 2) for c in origin_app]} app mm, "
          f"step {step} mm")
    print(f"  scale     {scale:.3f} grey units per LSB, "
          f"{clipped:.4%} clipped at +/-{a.clip_sd} sd")
    print(f"  bone fill {meta['bone_fill_fraction']:.1%}")
    print(f"  wrote     {path}  {q.nbytes / 1048576:.2f} MB")


if __name__ == "__main__":
    main()
