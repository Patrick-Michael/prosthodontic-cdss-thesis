#!/usr/bin/env python3
"""Split the mandible between two exposures at ONE axial plane.

THE OPERATOR'S DESIGN, and it is simpler than everything that came before it:
pick an anatomical level where BOTH scans have full-strength data, cut both
labels at that one world plane before either is meshed, and let the centred
exposure supply everything above it and the focused one everything below.

WHY EVERY EARLIER ATTEMPT FAILED, in one sentence: they all cut at the FIELD OF
VIEW boundary, which is inside the centred scan's fade zone.

    the mandible label does not END at the FOV floor, it FADES OUT
      z = -43.72    1.1 mm2
      z = -43.40   75.8
      z = -42.92  348.6
      z = -42.12  657.2   <- full strength from here up

Meshing that fade is what produces the torn inferior border, and any handover
placed inside it inherits both the raggedness and the disagreement between two
scans that are each guessing at the edge of their data.

WHY ONE PLANE IS ENOUGH, measured rather than hoped: at any level in the usable
window the two exposures agree on the mandible's OUTER boundary to a median of
0.160 mm and a 90th percentile of 0.320 mm -- one voxel and two. (Whole-area
IoU is only ~0.78, but that is dominated by INTERIOR marrow spaces the two
segmentations divide differently, which no surface mesh ever sees. Scoring the
filled outline instead of the label is the difference between "these disagree by
29%" and "these agree to a voxel".)

THE WINDOW is narrow and both ends are anatomical:
    above  z = -42.12   the centred label reaches full strength
    below  z = -40.51   the deepest lower root apex (tooth 19)
so the cut goes in between, and -41.30 sits in the middle of it.

NOTE the mental foramen does NOT work as the landmark, though it was the first
suggestion: the canal descends to z = -45.88 on the right and -46.30 on the
left, BELOW the centred scan's floor at -44.52. It is only traceable at all
because it was hand-traced in the mandibular exposure.

HOW THE CAP IS MADE FLAT. Marching cubes on min(label, half-space) puts the cut
exactly on the plane: where the half-space is the smaller field it decides the
crossing, so the cap is planar by construction rather than triangulated after
the fact. Both meshes use the SAME world plane, so their caps are coplanar and
a ray leaves one where it enters the other.

Usage: split_at_plane.py <centred.nrrd> <centred-pred> <split-dir>
                         <moving.nrrd> <moving-pred> <transform.json>
                         <z-cut-mm> <out-dir> [--target N]
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vol import Volume
from read_nifti import read_nifti
from register import euler
from segment_tooth import write_binary_stl
from export_teeth import decimate
from meshsmooth import taubin

MANDIBLE_LABEL = 2
SMOOTH = 1.0
EDGE = 1.5          # voxels over which the half-space goes 1 -> 0


def half_space(shape, z_of_voxel, z_cut, above, edge=EDGE):
    """Smooth indicator of one side of a plane, as a field to intersect with."""
    d = (z_of_voxel - z_cut) if above else (z_cut - z_of_voxel)
    return np.clip(0.5 + d / edge, 0.0, 1.0).astype(np.float32)


def mesh_field(field, target):
    v, f, _, _ = marching_cubes(field, level=0.5)
    v = taubin(v, f, 16)
    v, f = decimate(v, f, target)
    return taubin(v, f, 4), f


def report(v, f, tag):
    from collections import Counter
    c = Counter()
    for t in f:
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            c[(min(a, b), max(a, b))] += 1
    print(f"  {tag:10s} {len(f):7,} tris  {sum(1 for n in c.values() if n==1)} holes  "
          f"{sum(1 for n in c.values() if n>2)} non-manifold")


def main():
    ap = argparse.ArgumentParser()
    for n in ("cnrrd", "cpred", "split_dir", "mnrrd", "mpred", "tform", "zcut", "outdir"):
        ap.add_argument(n)
    ap.add_argument("--target", type=int, default=24000)
    ap.add_argument("--fma", default="FMA52748")
    o = ap.parse_args()
    zcut = float(o.zcut)
    os.makedirs(o.outdir, exist_ok=True)

    vc = Volume.load(o.cnrrd)
    fl, _, pix = read_nifti(o.cpred)
    sp = float(pix[0])
    teeth = np.load(os.path.join(o.split_dir, "lower_labels.npy")) > 0

    # ---- ABOVE the plane: the centred exposure, in its own grid -----------
    mand = (fl == MANDIBLE_LABEL) & ~teeth
    mand = ndi.binary_closing(mand, np.ones((3, 3, 3)))
    kz = np.arange(mand.shape[0], dtype=np.float32)
    zc = vc.origin[2] + kz * sp                       # world z of each slice
    kcut = (zcut - vc.origin[2]) / sp
    up = half_space(mand.shape, kz, kcut, above=True)[:, None, None]
    f_up = np.minimum(ndi.gaussian_filter(mand.astype(np.float32), SMOOTH), up)
    print(f"cut plane z = {zcut:.2f} mm  (centred slice {kcut:.1f})")
    (vu, fu) = mesh_field(f_up, o.target)
    world = np.empty_like(vu)
    world[:, 0] = vc.origin[0] + vu[:, 2] * sp
    world[:, 1] = vc.origin[1] + vu[:, 1] * sp
    world[:, 2] = vc.origin[2] + vu[:, 0] * sp
    report(world, fu, "above")
    write_binary_stl(os.path.join(o.outdir, f"{o.fma}.stl"), world, fu)

    # ---- BELOW the plane: the focused exposure, meshed in ITS grid --------
    # The plane is horizontal in the ATLAS frame, so in the moving grid it is
    # tilted; it is evaluated per voxel through the transform rather than
    # assumed to be an axial slice there.
    ml, _, _ = read_nifti(o.mpred)
    vm = Volume.load(o.mnrrd)
    p = json.load(open(o.tform))
    R = euler(*np.radians(p["rotation_deg"]))
    t = np.asarray(p["translation_mm"]) / sp
    centre = np.array(ndi.center_of_mass(fl == p["label"]))
    low = ml == MANDIBLE_LABEL
    low = ndi.binary_closing(low, np.ones((3, 3, 3)))

    idx = np.stack(np.indices(low.shape, dtype=np.float32), -1).reshape(-1, 3)
    fixed = (idx - centre + t) @ R.T + centre           # moving index -> fixed index
    zf = (vc.origin[2] + fixed[:, 0] * sp).reshape(low.shape).astype(np.float32)
    del idx, fixed
    dn = np.clip(0.5 + (zcut - zf) / (EDGE * sp), 0.0, 1.0)
    del zf
    f_dn = np.minimum(ndi.gaussian_filter(low.astype(np.float32), SMOOTH), dn)
    (vd, fd) = mesh_field(f_dn, o.target)
    mi = np.empty_like(vd)
    mi[:, 0] = vd[:, 0]; mi[:, 1] = vd[:, 1]; mi[:, 2] = vd[:, 2]
    fixed_v = (mi - centre + t) @ R.T + centre
    outv = np.empty_like(vd)
    outv[:, 0] = vc.origin[0] + fixed_v[:, 2] * sp
    outv[:, 1] = vc.origin[1] + fixed_v[:, 1] * sp
    outv[:, 2] = vc.origin[2] + fixed_v[:, 0] * sp
    report(outv, fd, "below")
    write_binary_stl(os.path.join(o.outdir, f"{o.fma}M.stl"), outv, fd)

    print(f"\n  above: z {world[:,2].min():7.2f} .. {world[:,2].max():6.2f}")
    print(f"  below: z {outv[:,2].min():7.2f} .. {outv[:,2].max():6.2f}")
    print(f"  the two caps should both sit at z = {zcut:.2f}")


if __name__ == "__main__":
    main()
