#!/usr/bin/env python3
"""Export the zirconia crowns on 19 and 30 as their own structures.

    python3 tools/cbct/export_prosthetic.py <volume.nrrd> <split-dir> \
        <landmarks.json> <out-dir>

Phase 2 of docs/drr-plan.md, and half of open question 6. Until now the
restorations were MEASURED (enamel.py's restorations(), 340 and 273 mm3) but
never meshed, so the atlas showed two crowned molars as though they were natural
teeth. On a radiograph that is not a small omission: zirconia is the most
attenuating thing in the mouth by a wide margin -- about 32x dentin at 65 kVp --
so a DRR of that region without it would be wrong in the most conspicuous
possible way.

WHAT THIS CAN AND CANNOT CLAIM. The threshold locates the restoration cleanly
and says NOTHING about how dense it is: the volume saturates at 3072 and 14-18%
of each crowned molar is pegged there (CLAUDE.md 126). Density therefore comes
from the literature, in tools/tissues.mjs, and the structure ships tiered
`schematic` for that reason while its GEOMETRY is measured. The threshold also
understates the crown near its margin, where the material thins below a voxel
and partial-volume averaging drags it under the cut -- so the margin is the
least trustworthy part of this mesh.

Label ids are matched BY CENTROID against landmarks, never by index into
split.json: the lower arch is walked from the patient's left, so label 1 is
tooth 31 and not 18 (CLAUDE.md 125). Indexing by id mirrors every figure onto
its contralateral pair, which is the same tooth TYPE and so survives a glance.
"""
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vol import Volume
from segment_tooth import write_binary_stl
from meshsmooth import taubin, weld
from export_teeth import decimate
from enamel import RESTORATION_HU, RESTORATION_MIN_MM3

TARGET_TRIS = 3000
PAD = 2                 # rule 203: a mask touching the array wall meshes open


def main():
    vol_path, split_dir, lm_path, outdir = sys.argv[1:5]
    os.makedirs(outdir, exist_ok=True)
    v = Volume.load(vol_path)
    lm = json.load(open(lm_path))
    sp = float(v.spacing[0])
    vox = sp ** 3

    found = []
    rejected = []
    for arch in ("upper", "lower"):
        arr = np.load(os.path.join(split_dir, f"{arch}_labels.npy"))
        ids = list(range(1, int(arr.max()) + 1))
        cents = ndi.center_of_mass(arr > 0, arr, ids)
        boxes = ndi.find_objects(arr)
        for key, m in lm.items():
            if m["arch"] != arch:
                continue
            c = np.array(m["centre_index"], float)
            best = min(ids, key=lambda s: np.linalg.norm(np.array(cents[s - 1]) - c))
            box = boxes[best - 1]
            sl = tuple(slice(max(0, b.start - 4), min(n, b.stop + 4))
                       for b, n in zip(box, arr.shape))
            solid = arr[sl] == best
            sub = v.data[sl]

            metal = solid & (sub >= RESTORATION_HU)
            if not metal.any():
                continue
            # A restoration is a SUBSTANTIAL CONNECTED BLOB, not every bright
            # voxel: enamel.py learned that treating specks as metal deleted up
            # to 22% of a lower incisor's crown. Keep only blobs over the same
            # threshold that module uses.
            lab, n = ndi.label(metal, structure=np.ones((3, 3, 3)))
            sizes = ndi.sum(metal, lab, range(1, n + 1)) * vox
            keep = [i + 1 for i, sz in enumerate(sizes) if sz >= RESTORATION_MIN_MM3]
            if not keep:
                # NEVER DROP THIS SILENTLY (CLAUDE.md 60). The difference
                # between "this tooth has no restoration" and "this tooth was
                # not examined" is exactly what a silent continue destroys.
                #
                # THESE ARE NOT ALL ONE THING, and two causes separate
                # cleanly. Settled 2026-09-05: the operator has NO restorations
                # anywhere but 19 and 30 -- no fillings, no endodontics -- so
                # none of what follows is dental work.
                #
                #   next to a crown (20 beside 19, 29 beside 30): BLOOM. Both
                #   SATURATE at 3072, because the halo around the zirconia is
                #   labelled as tooth.
                #
                #   anterior (22, 23, 24, 26, 27): EDGE OVERSHOOT. These top out
                #   at 2621-2871 and never saturate. Every one of them sits at
                #   88-99% of crown-root height and within 0.5 mm of the
                #   surface -- the incisal edges -- where a thin sharp
                #   high-contrast boundary drives reconstruction overshoot above
                #   the true value.
                #
                # A streak between the two crowns was the first hypothesis and
                # it is WRONG: the anterior teeth lie 23-28 mm off the 19-30
                # axis, because the mandible bows forward and that line passes
                # behind the incisors. Measured, not assumed.
                #
                # SO RESTORATION_MIN_MM3 IS LOAD-BEARING, not a rounding choice.
                # Tooth 23's largest blob is 1.64 mm3 against a 2.0 mm3 cut:
                # the threshold alone does NOT separate zirconia from incisal
                # enamel, and without the blob filter a lower lateral incisor
                # would be meshed a crown it does not have.
                rejected.append((m["universal"], float(metal.sum()) * vox,
                                 float(sizes.max()) if n else 0.0))
                continue
            big = np.isin(lab, keep)
            # MAKE IT CONTIGUOUS. Operator, 2026-09-05: the crowns rendered
            # patchy. A hard threshold on a saturating material is not a solid
            # -- the core is pegged at 3072 but occlusal grooves, the margin and
            # any porosity dip under 2600 and punch holes straight through the
            # mesh. Close across those gaps, then fill what is enclosed.
            #
            # This only ever ADDS, and only inside the tooth's own label, so it
            # cannot grow the crown outwards past where the scan puts it.
            # 3 iterations (0.48 mm), not 2. At 2 the crown on 19 came out
            # GENUS 1 -- a tunnel clean through the distolingual cusp, which the
            # operator spotted on screen on 2026-09-05. A tunnel is still a
            # CLOSED surface with zero boundary edges, so every closedness check
            # here passed it; "closed" and "no holes" are not the same claim.
            #
            # The bridging voxels sit at 2500-2599 HU, just under the cut: crown
            # material read low, not a void. Closing across them is therefore
            # restoring the crown rather than inventing it, and it is preferred
            # to simply lowering the threshold because 2500 would also promote
            # the incisal-edge overshoot on the anterior teeth (up to 2871) into
            # restorations that do not exist.
            big = ndi.binary_closing(big, np.ones((3, 3, 3)), 3) | big
            big = ndi.binary_fill_holes(big) & solid
            mm3 = float(big.sum()) * vox

            f = ndi.gaussian_filter(np.pad(big, PAD).astype(np.float32), 0.6)
            verts, faces, _, _ = marching_cubes(f, level=0.5)
            world = np.empty_like(verts)
            for a_i, s_i in enumerate((2, 1, 0)):        # (z,y,x) -> (x,y,z)
                world[:, a_i] = v.origin[a_i] + (sl[s_i].start - PAD
                                                 + verts[:, s_i]) * sp
            vt, ft = weld(world[faces].reshape(-1, 3))
            vt = taubin(vt, ft, 6)
            vt, ft = decimate(vt, ft, TARGET_TRIS)
            vt = taubin(vt, ft, 3)
            out = os.path.join(outdir, f"{m['fma']}-prosthetic.stl")
            write_binary_stl(out, vt, ft)
            found.append((m["universal"], m["fma"], mm3, len(ft)))
            print(f"  {m['universal']:>3}  {m['fma']:<10s} {mm3:7.1f} mm3  "
                  f"{len(ft):5d} tris  -> {os.path.basename(out)}")

    if rejected:
        print("\nsub-threshold metal-density voxels, NOT meshed "
              f"(no connected blob reaches {RESTORATION_MIN_MM3} mm3):")
        for u, total, biggest in sorted(rejected):
            print(f"  {u:>3}  {total:6.2f} mm3 of metal-density voxels, "
                  f"largest blob {biggest:.2f} mm3")

    if not found:
        sys.exit("no restorations found — check the threshold and the labels")
    print(f"\n{len(found)} prosthetic meshes, "
          f"{sum(f[2] for f in found):.1f} mm3 total")
    json.dump({
        "threshold_hu": RESTORATION_HU,
        "caveat": "Threshold LOCATES the restoration; it cannot measure its "
                  "density. The volume saturates at 3072 and both crowns are "
                  "partly pegged there, so density comes from the literature "
                  "(tools/tissues.mjs). The margin is understated where the "
                  "material thins below a voxel.",
        "teeth": [{"universal": u, "fma": f, "volume_mm3": round(v3, 1)}
                  for u, f, v3, _ in found],
        "rejected_subthreshold": [{"universal": u, "metal_mm3": round(t, 2),
                               "largest_blob_mm3": round(b, 2)}
                              for u, t, b in sorted(rejected)],
    }, open(os.path.join(outdir, "prosthetic.json"), "w"), indent=2)
    print(f"-> {outdir}")


if __name__ == "__main__":
    main()
