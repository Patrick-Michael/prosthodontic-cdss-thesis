#!/usr/bin/env python3
"""Isolate the medullary bone, so the trabecular pattern can be measured on it.

THE OPERATOR'S POINT, 2026-09-06, and it is the right one: do not measure a
trabecular pattern on the raw bone envelope. Every structure already extracted
from this volume is still sitting inside that envelope, and each one injects
signal that is not trabeculation.

The worst offender is not the teeth. It is the LAMINA DURA AND THE PDL. They are
a bright ring and a dark ring, concentric, around all 28 roots, and the pair is
about 0.3-0.5 mm wide -- which is inside the spatial-frequency band trabeculae
occupy. Measure a power spectrum over unmasked bone and the strongest thing in
it is socket wall. Ship that as "measured trabeculation" and the atlas would be
carrying 28 sockets' worth of periodic structure and calling it marrow.

WHAT IS REMOVED, and why each:

  teeth              they are not bone
  PDL + lamina dura  the contaminant above; covered by dilating the teeth,
                     since both are a thin concentric band on the root surface
  mandibular canal   a dark tube; its wall is cortical-like and its lumen is not
                     bone at all
  traced canals      incisive, mental and infraorbital, same reason
  pulp               inside the teeth already, so this is belt-and-braces
  restorations       the zirconia on 19 and 30 clips at the volume's 3072
                     ceiling and throws beam-hardening streaks and a bright
                     halo well beyond the crown. Streaks read as texture and are
                     pure artefact, so a generous radius goes.

WHAT IS THEN SEPARATED. What survives that is still not trabecular bone: it is
cortical plate + trabecular bone + marrow. Averaging a statistic over the lot
inflates it with cortex. Once the sockets and canals are holes, though, the
separation is one line: a distance transform on the residual measures depth from
the nearest non-bone voxel, and thresholding it strips the outer plates AND the
socket walls together, because both are surfaces of the residual. The cortex
keeps the bulk density it already has in tissues.mjs; only the interior is
textured.

WHAT THIS DOES NOT DO, and must not be read as doing:

  * It does not resolve individual trabeculae. They are 50-200 um thick at
    0.5-1.5 mm spacing; this volume is 0.16 mm with a worse effective
    resolution. What is measurable is the COARSE DENSITY TEXTURE, partial-volume
    averaged. pdl.py already documents the same limit for the ligament width.
  * It does not produce a density. nrrd/volumes.json says it in as many words:
    "int16, Hounsfield-like; NOT calibrated HU". So the PATTERN and its RELATIVE
    variation are measured; any mapping to g/cm3 is derived from literature and
    has to be labelled that way.

HOW FAR OUT the teeth have to be dilated -- MEASURED 2026-09-06, and it is three
times what the anatomy alone would suggest. Sampling bone in shells at
increasing distance outside the tooth surface gives:

    0-0.16 mm   976      1.0-1.25 mm  731
    0.16-0.32   865      1.25-1.5     721   <- baseline reached here
    0.32-0.48   805      1.5-2.0      748   <- rising again: real bone
    0.48-0.80   ~800     2.0-3.0      801

There is NO bright lamina-dura spike and NO dark PDL trough in that profile, and
the absence is the finding. At 0.16 mm with a worse effective resolution the two
rings are blurred into each other and swamped by the tooth's own point-spread
halo, which decays monotonically and does not reach baseline until about 1.25 mm.
pdl.py documents the same limit for the ligament width. So the naive radius from
anatomy -- 0.2 mm of ligament plus 0.32 mm of socket wall, call it 0.6 mm --
would leave 0.6-1.25 mm of tooth halo sitting in the sample, biased bright, in a
shell around every root. That is precisely the contamination this script exists
to remove, and it would have survived a defensible-looking parameter.

1.25 mm, which is where that profile reaches baseline. It was briefly 1.5, which
was padding rather than measurement, and the operator called it too wide on the
slicer. A sweep of the whole result confirms 1.5 is not special:

    tooth r   residual   medullary   cort mean   med mean   separation
      0.6 mm    48,138       3,028         843        639        +204
      1.0        44,788       2,768         850        635        +214
      1.25       42,776       2,645         855        632        +223
      1.5        41,031       2,545         858        629        +230
      2.0        38,066       2,394         862        623        +239

READ THAT CURVE CAREFULLY, because the obvious reading is wrong. Separation rises
monotonically and smoothly with radius, with no knee -- so it offers no optimum,
and "bigger is better" would cut until nothing was left. Worse, the rise is not
purely contamination being removed: dilating the teeth MOVES THE SURFACE the
depth split is measured from, so the medullary compartment is pushed into deeper
and genuinely darker bone as the radius grows. Part of that +204 -> +239 is
geometry, not purity, and this sweep cannot separate the two.

The halo profile can, and it is the measurement that decides this: contamination
is at baseline by 1.25 mm. Past that, more radius buys separation by moving the
goalposts and costs 1,745 mm3 of real bone per 0.25 mm.

HOW DEEP the cortex runs -- MEASURED 2026-09-06 the same way, sampling the
residual by depth below its own surface:

    0-0.3 mm    594   <- partial volume against air/soft tissue: DISCARDED
    0.3-0.6     810
    0.6-0.9     889   <- the cortical plate, peak density
    0.9-1.2     871
    1.2-1.6     816
    1.6-2.0     703   <- turned over, falling monotonically from here
    2.0-2.5     586
    2.5-3.0     467
    3.0-3.5     411
    3.5+        339

Two things follow. The 0-0.3 mm shell is a MIXTURE, not bone, and assigning it to
the cortex is what made cortical and medullary means indistinguishable on the
first run (766 vs 786) -- it drags the cortical mean down by about 200. And the
turnover is at 1.6 mm, not the 1.0 mm first guessed, which had put half the
cortical plate on the medullary side.

THE RESTORATION COLLAR -- MEASURED 2026-09-06 after the operator said on the
slicer that it looked too wide. He was right, and the reason is better than
"too wide". Profiling bone outward from the >=2800 seed, away from teeth:

    dist from metal   voxels    mean     sd   p95-p05
      2-4 mm           8,134     788    235       782
      4-6             57,276     792    221       771
      6-8             96,699     823    206       719
      8-12           404,364     848    244       845
     12-20         2,050,695     820    322      1042
     20+           7,432,398     757    318      1035

There is NO halo. The mean is flat near the metal and RISES with distance, which
is anatomy -- crestal bone by the crowns, basal bone further off -- not artefact.
And a streak is bright AND dark bands, so it shows up as DISPERSION rather than
as a shifted mean: dispersion near the metal (sd 206-235) is LOWER than far from
it (318-322). Neither statistic finds a streak to exclude.

What 5 mm cost, measured as bone the tooth dilation had not already removed:

    radius 2 mm    0.0 mm3        radius 4 mm    33.3 mm3
    radius 3 mm    2.6 mm3        radius 5 mm   125.1 mm3

So the exclusion is almost entirely REDUNDANT with the tooth dilation, and every
millimetre past 2 is pure loss. Set to 2.0. Be clear about the size of the win
though: 125 mm3 against a 40,906 mm3 residual is 0.3%, and it is crestal bone by
the crowns, so it does not touch the medullary shortage below.

CAUTION ON THAT NEGATIVE RESULT: bone within a few mm of these crowns is a
small and anatomically particular sample -- alveolar crest around 19 and 30 --
so "low dispersion" may be homogeneous crestal bone rather than proven absence
of artefact. What can be said is that there is no positive evidence of a streak
to justify a wide collar.

BE AWARE HOW LITTLE DEEP BONE THERE IS. Past 2.5 mm there are only ~100k voxels
of 10.9M. The alveolus is nearly all socket, and the mandibular canal is a
separate label and therefore a hole down the middle of the body. Any statistic
fitted to the deep tail is fitted to a small, spatially clustered sample, and
should say so.

Usage:
    trabecular_isolate.py <volume.nrrd> <pred.nii.gz> <split-dir|-> <out-dir>
        [--traced DIR[,DIR...]]   extra boolean .npy masks to exclude
        [--tooth-dilate-mm 1.25]  MEASURED, see "how far out" below
        [--canal-dilate-mm 0.5]   covers the canal wall
        [--metal-threshold 2800]  near the 3072 clipping ceiling
        [--metal-dilate-mm 2.0]   MEASURED, see "the restoration collar"
        [--shell-mm 0.32]         partial-volume surface, discarded entirely
        [--cortex-mm 1.6]         MEASURED, see "how deep" below
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vol import Volume
from read_nifti import read_nifti

# DentalSegmentator's classes. Mirrors LABELS in eval_dentalseg.py -- if that
# changes, this is wrong and the bone envelope silently becomes something else.
UPPER_SKULL, MANDIBLE, UPPER_TEETH, LOWER_TEETH, MAND_CANAL = 1, 2, 3, 4, 5


def grow(mask, radius_mm, spacing_mm):
    """Dilate by a true Euclidean radius in millimetres.

    NOT a structuring element. A 5 mm ball at 0.16 mm is 63 voxels across --
    250k elements -- and scipy's brute-force binary_dilation runs out of memory
    on it. The distance transform of the COMPLEMENT gives the same answer in one
    linear pass, and gives it exactly rather than on a discretised ball.
    """
    if radius_mm <= 0:
        return mask
    return ndi.distance_transform_edt(~mask, sampling=spacing_mm) <= radius_mm


def describe(name, mask, data, sp):
    """Voxel count, volume and the intensity distribution inside a mask."""
    n = int(mask.sum())
    out = dict(voxels=n, mm3=round(n * sp ** 3, 1))
    if n:
        vals = data[mask].astype(np.float32)
        out.update(mean=round(float(vals.mean()), 1),
                   sd=round(float(vals.std()), 1),
                   p05=round(float(np.percentile(vals, 5)), 1),
                   p50=round(float(np.percentile(vals, 50)), 1),
                   p95=round(float(np.percentile(vals, 95)), 1))
    print(f"  {name:22s} {n:>10,} vox  {out['mm3']:>12,.1f} mm3"
          + (f"   mean {out['mean']:>7.1f}  sd {out['sd']:>6.1f}"
             f"  p05/50/95 {out['p05']:.0f}/{out['p50']:.0f}/{out['p95']:.0f}"
             if n else ""))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("volume")
    ap.add_argument("pred")
    ap.add_argument("split_dir", nargs="?", default="-",
                    help="per-tooth labels, or '-' to use this "
                         "exposure's own DentalSegmentator classes")
    ap.add_argument("outdir")
    ap.add_argument("--traced", default="")
    ap.add_argument("--tooth-dilate-mm", type=float, default=1.25)
    ap.add_argument("--canal-dilate-mm", type=float, default=0.5)
    ap.add_argument("--metal-threshold", type=int, default=2800)
    ap.add_argument("--metal-dilate-mm", type=float, default=2.0)
    ap.add_argument("--shell-mm", type=float, default=0.32)
    ap.add_argument("--cortex-mm", type=float, default=1.6)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    v = Volume.load(a.volume)
    sp = float(v.spacing[0])
    lab, _, _ = read_nifti(a.pred)
    if lab.shape != v.data.shape:
        sys.exit(f"label shape {lab.shape} != volume {v.data.shape} -- "
                 "these are different exposures, and mixing them would put "
                 "one person's labels on another's grid")
    print(f"volume {v.data.shape} at {sp} mm, range "
          f"{int(v.data.min())}..{int(v.data.max())}")

    rep = {"volume": os.path.abspath(a.volume), "pred": os.path.abspath(a.pred),
           "spacing_mm": sp, "params": vars(a).copy()}

    # --- the envelope --------------------------------------------------------
    bone = (lab == UPPER_SKULL) | (lab == MANDIBLE)
    print("\nenvelope")
    rep["bone_envelope"] = describe("bone (both jaws)", bone, v.data, sp)

    # --- what comes out of it -----------------------------------------------
    print("\nexcluded")
    excl = np.zeros_like(bone)
    parts = {}

    # THIS EXPOSURE'S OWN tooth classes are the frame-safe baseline: they came
    # out of the prediction being read, so they cannot be misregistered against
    # it. The per-tooth hand split is finer and is added where it belongs.
    own = (lab == UPPER_TEETH) | (lab == LOWER_TEETH)
    teeth = own.copy()
    if a.split_dir != "-":
        hand = ((np.load(os.path.join(a.split_dir, "upper_labels.npy")) > 0)
                | (np.load(os.path.join(a.split_dir, "lower_labels.npy")) > 0))
        # THE FRAME CHECK THAT SHAPE CANNOT DO. All three exposures here are
        # 512^3 at 0.16 mm, so an array-shape assertion passes while the frames
        # differ -- and they differ by 35 mm in x between the centered exposure
        # and each focused one (transform-*-to-centered.json). Applying the
        # centered split to a focused volume silently excludes the wrong side of
        # the mouth, and the run still prints a full set of plausible numbers.
        # Overlap against this exposure's own teeth is what actually catches it.
        inter = float((hand & own).sum())
        d = 2.0 * inter / max(float(hand.sum() + own.sum()), 1.0)
        print(f"    frame check: hand split vs this exposure's teeth, Dice {d:.3f}")
        if d < 0.5:
            sys.exit(
                f"REFUSING: Dice {d:.3f} between {a.split_dir} and the tooth "
                f"classes of {a.pred}.\n"
                "Those are different frames. The per-tooth split is built in the "
                "centered exposure's grid; the focused mandibular and maxillary "
                "exposures sit about 35 mm away in x. Either register the split "
                "first, or pass '-' to use this exposure's own tooth classes.")
        teeth |= hand
    # THE DILATION IS THE POINT. Subtracting the exact tooth label leaves the
    # PDL and the lamina dura behind, and they are the contaminant this whole
    # script exists to remove. 1.0 mm covers a ~0.2 mm ligament, a ~0.32 mm
    # socket wall and the point spread that smears both.
    teeth_d = grow(teeth, a.tooth_dilate_mm, sp)
    parts["teeth_pdl_lamina"] = describe(
        f"teeth +{a.tooth_dilate_mm}mm", teeth_d & bone, v.data, sp)
    excl |= teeth_d

    canal = (lab == MAND_CANAL)
    traced_files = []
    for d in [s for s in a.traced.split(",") if s]:
        for f in sorted(glob.glob(os.path.join(d, "*.npy"))):
            m = np.load(f)
            if m.shape != bone.shape:
                print(f"    skip {f} -- shape {m.shape}")
                continue
            canal |= m.astype(bool)
            traced_files.append(os.path.basename(f))
    if traced_files:
        print(f"    traced: {', '.join(traced_files)}")
    canal_d = grow(canal, a.canal_dilate_mm, sp)
    parts["canals"] = describe(
        f"canals +{a.canal_dilate_mm}mm", canal_d & bone, v.data, sp)
    parts["canals"]["traced_files"] = traced_files
    excl |= canal_d

    # Restorations. Not segmented as such -- they are found by the ceiling they
    # clip against, which is exactly how they were identified everywhere else in
    # this project.
    #
    # THE RADIUS WAS 5 mm ON A GUESS AND THE GUESS WAS WRONG. See "the
    # restoration collar" in the header: there is no measurable streak in bone
    # around 19 and 30, and 5 mm was throwing away 125 mm3 of good bone to
    # protect against an artefact that is not there.
    metal = v.data >= a.metal_threshold
    metal_d = grow(metal, a.metal_dilate_mm, sp)
    parts["restoration_halo"] = describe(
        f">={a.metal_threshold} +{a.metal_dilate_mm}mm", metal_d & bone, v.data, sp)
    excl |= metal_d

    residual = bone & ~excl
    print("\nresidual")
    rep["excluded"] = parts
    rep["residual"] = describe("bone, isolated", residual, v.data, sp)

    # --- cortex versus medulla ----------------------------------------------
    #
    # Depth from the nearest non-residual voxel. Because the sockets and canals
    # are now holes, this measures depth from the outer plate AND from every
    # socket wall at once, which is what separates the two without a threshold
    # on intensity -- an intensity threshold here would be circular, since
    # intensity is the thing being measured.
    print("\ndepth")
    depth = ndi.distance_transform_edt(residual, sampling=sp)

    # The profile is emitted whether or not anyone looks at it, because it is
    # the evidence for the two thresholds below and they are otherwise just
    # numbers in a default.
    prof = []
    edges = [0, 0.3, 0.6, 0.9, 1.2, 1.6, 2.0, 2.5, 3.0, 3.5, 1e3]
    print(f"  {'depth mm':>12} {'voxels':>10} {'mean':>7} {'sd':>6}")
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = residual & (depth > lo) & (depth <= hi)
        n = int(m.sum())
        if n < 50:
            continue
        x = v.data[m].astype(np.float32)
        prof.append(dict(lo_mm=lo, hi_mm=None if hi > 100 else hi, voxels=n,
                         mean=round(float(x.mean()), 1),
                         sd=round(float(x.std()), 1)))
        print(f"  {lo:>5}-{hi if hi < 100 else 99:<6} {n:>10,} "
              f"{x.mean():>7.0f} {x.std():>6.0f}")
    rep["depth_profile"] = prof

    # THE SURFACE SHELL IS DISCARDED, not assigned. It is bone mixed with
    # whatever is outside it, and it belongs to neither compartment.
    shell = residual & (depth <= a.shell_mm)
    cortical = residual & (depth > a.shell_mm) & (depth <= a.cortex_mm)
    medullary = depth > a.cortex_mm
    rep["surface_shell"] = describe(f"shell (<={a.shell_mm}mm, DISCARDED)",
                                    shell, v.data, sp)
    rep["cortical"] = describe(f"cortical ({a.shell_mm}-{a.cortex_mm}mm)",
                               cortical, v.data, sp)
    rep["medullary"] = describe(f"medullary (>{a.cortex_mm}mm)",
                                medullary, v.data, sp)
    rep["max_depth_mm"] = round(float(depth.max()), 2)
    print(f"  deepest point {rep['max_depth_mm']} mm from any surface")

    # --- out -----------------------------------------------------------------
    np.save(os.path.join(a.outdir, "residual.npy"), residual)
    np.save(os.path.join(a.outdir, "medullary.npy"), medullary)
    np.save(os.path.join(a.outdir, "cortical.npy"), cortical)
    with open(os.path.join(a.outdir, "isolate.json"), "w") as f:
        json.dump(rep, f, indent=2)
    print(f"\nwrote residual/medullary/cortical .npy + isolate.json to {a.outdir}")
    print("LOOK AT IT BEFORE MEASURING ANYTHING:")
    print(f"  tools/cbct/slicer.py {a.volume} /tmp/tb-look \\\n"
          f"      --names scratch --mask {a.outdir}")


if __name__ == "__main__":
    main()
