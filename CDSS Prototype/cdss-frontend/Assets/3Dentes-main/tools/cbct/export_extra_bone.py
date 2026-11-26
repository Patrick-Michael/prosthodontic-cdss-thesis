#!/usr/bin/env python3
"""Export the bone a FOCUSED exposure saw and the centred volume did not.

Three volumes were acquired, and for a long time only the centred one supplied
geometry. The other two see substantially more of the structure they are aimed
at:

    upper skull   centred 31.3 cm3   maxillary  54.0 cm3
    mandible      centred 21.6 cm3   mandibular 32.1 cm3

The centred volume's mandible is cut through both rami by its field of view
(tools/fov-audit.mjs: 172 mm2 and 191 mm2 of flat cap on the side walls), and
its upper skull simply stops. This tool recovers the difference, per exposure,
so each focused scan contributes exactly the bone it alone measured.

TWO THINGS DECIDE HOW THIS IS BUILT.

1. The transform is fitted on the UPPER SKULL, not the mandible. The mandible is
   not rigid with respect to the maxilla across separate exposures, which is
   exactly why register.py refuses one global transform for both jaws. Held out
   from that fit, the UPPER TEETH label lands at Dice 0.708 against a ceiling of
   0.728 -- 97% of what the partial overlap allows, from a structure the
   optimiser never saw.

2. MESH IN THE MOVING GRID, THEN TRANSFORM THE VERTICES. Resampling the
   maxillary label onto the centred grid would silently discard every voxel that
   lands outside it -- which is precisely the new anatomy, since the exposures
   are about 35 mm apart in x. So the centred volume's own bone is pulled INTO
   the maxillary grid to subtract, the remainder is meshed there, and only the
   finished vertices are mapped into the atlas frame. This is the plan's
   "register in voxel space, fuse in mesh space" for the same reason it gave.

Usage: export_extra_bone.py <transform.json> <fixed-pred.nii.gz>
                            <moving-pred.nii.gz> <moving.nrrd> <centered.nrrd>
                            <label> <out-fma> <out-dir>
"""
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vol import Volume
from read_nifti import read_nifti
from register import euler
from segment_tooth import write_binary_stl
from export_bone import mesh_mask, TARGET

# How much of the centred volume's own bone to treat as already-covered, in
# voxels of dilation before the subtraction.
#
# WAS 2, AND THAT WAS THE SEAM. The reasoning for a pad was sound -- the two
# exposures disagree by up to a voxel, and a raw subtraction leaves a shell of
# duplicate surface -- but the value was never fitted, and two voxels at 0.16 mm
# is 0.32 mm of measured bone deleted along the whole join BY CONSTRUCTION,
# before marching cubes puts each surface another half-voxel inside its own
# mask. The operator saw the result as a seam on the model and worse on the
# film, where it prints DARK because a ray crossing the join passes through less
# bone than the patient has.
#
# WHY ZERO IS THE RIGHT VALUE IN ISOLATION, AND WHY IT IS NOT SET (see below).
# Zero is not a tuned value, it is the absence of one. `moving & ~have` with no
# dilation is the exact partition of two measurements: the focused exposure
# contributes precisely the bone the centred one does not have. Fitting the pad
# to some other constant would have replaced an unmeasured number with a
# measured one; removing it deletes the number.
#
# MEASURED, by rebuilding at every pad from +2 to -3 and measuring the join
# surface-to-surface (`seam_sweep.py`, `seam_audit.py`):
#
#     pad   bone mm3   median gap   join in contact   overlapping   depth
#      +2     11974      0.765 mm         0.4%            0.00%     0.00 mm
#      +1     12207      0.549 mm        14.8%            0.29%     0.09 mm
#       0     13563      0.142 mm        62.6%           23.29%     0.50 mm
#      -1     17226      0.168 mm        60.1%           74.74%     1.45 mm
#      -2     21107      0.367 mm        35.1%           69.20%     1.63 mm
#
# (mandible; the maxilla runs the same shape.) Two things settle it. Going
# NEGATIVE -- letting the focused label reach back into the centred bone -- does
# not keep closing the gap: the median stops improving at pad 0 and gets worse
# again, while the overlap explodes. So the residual is NOT a uniform offset
# that a constant could dial out; it is spatial variation from a rigid
# registration fitted to Dice 0.708, and no single number can serve it. And the
# pad was discarding 1,589 mm3 of measured bone in the mandible and 1,554 mm3 in
# the maxilla -- the same class of loss as rule 115, bone thrown away at EXPORT.
#
# WHAT THIS DOES NOT FIX, and it must not be claimed as fixed: 23% of the join
# now interpenetrates by up to 0.5 mm, which on the DRR double-counts path
# length and prints bright. The error is smaller and no longer biased in one
# direction, which is better; it is not zero. The remaining spread needs the
# join to exist as ONE surface rather than two that abut -- see
# docs/wishlist.md.
# STILL 2, DELIBERATELY. Zero is the measured-correct value in isolation, but
# applying it alone is not an improvement: a later measurement showed that of
# the 13,651 mm3 this tool ships as "new anatomy" for the mandible, 2,182 mm3
# (16%) is not new anatomy at all -- it is the two exposures DISAGREEING inside
# the centred scan's own field of view, where the centred scan is authoritative.
# Dropping the pad to 0 admits MORE of that disagreement, not less. The pad and
# the disagreement have to be fixed together, as part of the seam rebuild in
# docs/wishlist.md, and until then changing this constant on its own would trade
# one measured error for another.
OVERLAP_PAD_VOX = 2
MIN_PIECE_MM3 = 40.0


def fixed_index_of(moving_idx, R, t_vox, centre):
    """(z, y, x) index in the FIXED grid for a point in the MOVING grid.

    Inverse of the sampling in validate_registration.apply_to, which maps a
    fixed index to where it came from in the moving grid as
        src = (idx_fixed - centre) @ R + centre - t
    so                                                                      ."""
    return (moving_idx - centre + t_vox) @ R.T + centre


def main():
    tp, fp, mp, moving_nrrd, fixed_nrrd, label, out_fma, outdir = sys.argv[1:9]
    label = int(label)
    os.makedirs(outdir, exist_ok=True)
    p = json.load(open(tp))
    fl, _, pix = read_nifti(fp)
    ml, _, _ = read_nifti(mp)
    vm = Volume.load(moving_nrrd)
    vf = Volume.load(fixed_nrrd)
    sp = np.array([float(x) for x in pix], float)
    vox = float(np.prod(sp))
    R = euler(*np.radians(p["rotation_deg"]))
    t_vox = np.asarray(p["translation_mm"]) / sp
    centre = np.array(ndi.center_of_mass(fl == p["label"]))

    if label != p["label"]:
        # Not fatal -- the mandibular canal rides with the mandible, so exporting
        # it under the mandible's transform is legitimate -- but say so, because
        # a label that is NOT rigid with the fitted one would be silently wrong.
        print(f"note: exporting label {label} under a transform fitted on "
              f"{p['label']}; only valid if the two are rigidly attached")
    moving = ml == label
    print(f"moving label {label}          {moving.sum() * vox:9.0f} mm3")

    # pull the centred volume's own bone into the moving grid, so the subtraction
    # happens where all the anatomy still exists
    idx = np.stack(np.indices(moving.shape, dtype=np.float32), axis=-1)
    src = fixed_index_of(idx.reshape(-1, 3), R, t_vox, centre).reshape(idx.shape)
    have = ndi.map_coordinates((fl == label).astype(np.float32),
                               [src[..., 0], src[..., 1], src[..., 2]],
                               order=1, mode="constant", cval=0.0) > 0.5
    if OVERLAP_PAD_VOX:
        have = ndi.binary_dilation(have, np.ones((3, 3, 3)), OVERLAP_PAD_VOX)
    print(f"  already in the atlas  {have.sum() * vox:9.0f} mm3 (as seen here)")

    new = moving & ~have
    new = ndi.binary_closing(new, np.ones((3, 3, 3)))
    lab, n = ndi.label(new, structure=np.ones((3, 3, 3)))
    if n:
        szs = ndi.sum(new, lab, range(1, n + 1)) * vox
        new = np.isin(lab, [i + 1 for i, z in enumerate(szs) if z >= MIN_PIECE_MM3])
        big = sorted((z for z in szs if z >= MIN_PIECE_MM3), reverse=True)
        print(f"  NEW bone              {new.sum() * vox:9.0f} mm3 in "
              f"{len(big)} pieces: {[round(z) for z in big[:6]]}")
    if new.sum() * vox < 50:
        print("nothing worth exporting")
        return

    got = mesh_mask(new, vm, TARGET["bone"])
    if not got:
        print("mesh failed")
        return
    verts_world, faces = got

    # mesh_mask returned MOVING world mm; go back to moving index, through the
    # transform, then out to FIXED world mm -- the atlas frame.
    mi = np.empty_like(verts_world)
    mi[:, 0] = (verts_world[:, 2] - vm.origin[2]) / sp[2]      # z
    mi[:, 1] = (verts_world[:, 1] - vm.origin[1]) / sp[1]      # y
    mi[:, 2] = (verts_world[:, 0] - vm.origin[0]) / sp[0]      # x
    fi = fixed_index_of(mi, R, t_vox, centre)
    out = np.empty_like(verts_world)
    out[:, 0] = vf.origin[0] + fi[:, 2] * sp[0]
    out[:, 1] = vf.origin[1] + fi[:, 1] * sp[1]
    out[:, 2] = vf.origin[2] + fi[:, 0] * sp[2]

    path = os.path.join(outdir, f"{out_fma}.stl")
    write_binary_stl(path, out, faces)
    lo, hi = out.min(0), out.max(0)
    print(f"\n{out_fma}  {len(faces):,} triangles -> {path}")
    print(f"  in the atlas frame: x {lo[0]:7.1f}..{hi[0]:6.1f}  "
          f"y {lo[1]:7.1f}..{hi[1]:6.1f}  z {lo[2]:7.1f}..{hi[2]:6.1f} mm")


if __name__ == "__main__":
    main()
