#!/usr/bin/env python3
"""Put the centred exposure's bone and a focused exposure's into ONE grid.

WHY THIS EXISTS. `export_extra_bone.py` deliberately meshes each exposure in its
own grid and transforms only the finished vertices, because resampling the
focused label onto the centred grid would silently discard the new anatomy --
the exposures sit ~35 mm apart in x, so the very bone that makes the focused
scan worth having falls outside the centred grid. That decision is right for
what it was solving and it is the reason the two surfaces never share a vertex,
which is the reason there is a visible crease at the join (CLAUDE.md 242-244).

A shared wall needs both labels in one grid. The way to have that WITHOUT
throwing anything away is a grid big enough for both: built in the centred
(atlas) frame, extended by however much the focused exposure sticks out.

MEASURED, mandible: 19,430 mm3 of the centred volume's own bone is visible from
inside the moving grid against 21,600 mm3 in the centred label -- so meshing the
union in the MOVING grid would clip 10% of the mandible. Padding is not
optional.

Nothing here meshes anything. It produces the union mask and the label of which
exposure each voxel came from, which is what the shared-wall build needs.

Usage: join_grid.py <transform.json> <fixed-pred> <moving-pred> <label> [--save DIR]
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from read_nifti import read_nifti
from register import euler

PAD_VOX = 4          # breathing room so nothing sits on a grid wall
CHUNK_Z = 48         # resample this many output slices at a time


def moving_index_of(fixed_idx, R, t_vox, centre):
    """(z, y, x) index in the MOVING grid for a point in the FIXED grid.

    The inverse of export_extra_bone.fixed_index_of, and the same relation
    validate_registration.apply_to samples with:
        src = (idx_fixed - centre) @ R + centre - t
    """
    return (fixed_idx - centre) @ R + centre - t_vox


def build(tp, fp, mp, label):
    p = json.load(open(tp))
    fl, _, pix = read_nifti(fp)
    ml, _, _ = read_nifti(mp)
    sp = np.array([float(x) for x in pix], float)
    vox = float(np.prod(sp))
    R = euler(*np.radians(p["rotation_deg"]))
    t_vox = np.asarray(p["translation_mm"]) / sp
    centre = np.array(ndi.center_of_mass(fl == p["label"]))

    fixed = fl == label
    moving = ml == label
    print(f"centred label {label}   {fixed.sum() * vox:9.0f} mm3")
    print(f"focused label {label}   {moving.sum() * vox:9.0f} mm3")

    # Where does the focused label land in the fixed frame? Corners of its
    # bounding box are enough -- the transform is rigid, so the extremes of the
    # box map to the extremes of the image of the box.
    mz, my, mx = np.where(moving)
    lo = np.array([mz.min(), my.min(), mx.min()], float)
    hi = np.array([mz.max(), my.max(), mx.max()], float)
    corners = np.array([[a, b, c] for a in (lo[0], hi[0])
                        for b in (lo[1], hi[1]) for c in (lo[2], hi[2])])
    # forward map: fixed = (moving - centre + t) @ R.T + centre
    fc = (corners - centre + t_vox) @ R.T + centre

    fz, fy, fx = np.where(fixed)
    flo = np.array([fz.min(), fy.min(), fx.min()], float)
    fhi = np.array([fz.max(), fy.max(), fx.max()], float)

    g_lo = np.floor(np.minimum(fc.min(0), flo)).astype(int) - PAD_VOX
    g_hi = np.ceil(np.maximum(fc.max(0), fhi)).astype(int) + PAD_VOX
    shape = tuple((g_hi - g_lo).astype(int) + 1)
    print(f"joined grid          {shape[0]}x{shape[1]}x{shape[2]} voxels at "
          f"{sp[0]:.2f} mm, origin offset {tuple(g_lo)} in fixed indices "
          f"({np.prod(shape) / 1e6:.0f} M voxels)")

    A = np.zeros(shape, bool)          # the centred exposure's bone
    B = np.zeros(shape, bool)          # the focused exposure's bone
    # The centred label drops straight in -- no resampling, no interpolation.
    # Only its BOUNDING BOX is copied: the grid is sized to the two labels, not
    # to the 512^3 volume, so g_lo can sit inside the fixed volume and copying
    # the whole array would not fit.
    flo_i = flo.astype(int)
    fhi_i = fhi.astype(int)
    src = tuple(slice(flo_i[i], fhi_i[i] + 1) for i in range(3))
    dst = tuple(slice(flo_i[i] - g_lo[i], fhi_i[i] + 1 - g_lo[i]) for i in range(3))
    A[dst] = fixed[src]

    # the focused label is resampled, in z-chunks so the coordinate arrays for a
    # grid this size do not have to exist all at once
    for z0 in range(0, shape[0], CHUNK_Z):
        z1 = min(z0 + CHUNK_Z, shape[0])
        idx = np.stack(np.meshgrid(np.arange(z0, z1, dtype=np.float32) + g_lo[0],
                                   np.arange(shape[1], dtype=np.float32) + g_lo[1],
                                   np.arange(shape[2], dtype=np.float32) + g_lo[2],
                                   indexing="ij"), axis=-1)
        src = moving_index_of(idx.reshape(-1, 3), R, t_vox, centre)
        del idx
        B[z0:z1] = (ndi.map_coordinates(moving.astype(np.float32),
                                        [src[:, 0], src[:, 1], src[:, 2]],
                                        order=1, mode="constant", cval=0.0)
                    > 0.5).reshape(z1 - z0, shape[1], shape[2])
        del src

    print(f"  centred, in grid   {A.sum() * vox:9.0f} mm3  "
          f"({100 * A.sum() * vox / (fixed.sum() * vox):.1f}% of the label — "
          f"must be 100.0)")
    print(f"  focused, in grid   {B.sum() * vox:9.0f} mm3  "
          f"({100 * B.sum() * vox / (moving.sum() * vox):.1f}% of the label)")
    # WHERE THE CENTRED SCAN HAS INFORMATION AT ALL -- its own 512^3 box,
    # mapped into the joined grid. This is the thing the split should key on.
    #
    # Inside it the centred exposure is AUTHORITATIVE: if it says a voxel is not
    # bone, it is not bone. Outside it the centred scan knows nothing and only
    # the focused one can speak. Keying the split on "wherever the two labels
    # differ" instead was wrong, and measurably so -- the two registered
    # mandibles sit at Dice 0.684, so their union INFLATES the jaw by 8.1%
    # inside the centred scan's own territory, adding 1,753 mm3 of bone the
    # centred scan says is not there. The operator saw that as the mandible
    # being offset from the maxilla before any measurement found it.
    fov = np.zeros(shape, bool)
    fsl = tuple(slice(max(0, -g_lo[i]),
                      min(shape[i], -g_lo[i] + fixed.shape[i])) for i in range(3))
    fov[fsl] = True
    U = A | B
    print(f"  union              {U.sum() * vox:9.0f} mm3")
    print(f"  centred FOV box    {fov.sum() * vox:9.0f} mm3 of grid")
    print(f"  focused bone OUTSIDE it {(B & ~fov).sum() * vox:6.0f} mm3  "
          f"<- the only bone it should contribute")
    print(f"  focused bone INSIDE it, that the centred scan calls air: "
          f"{(B & ~A & fov).sum() * vox:.0f} mm3  <- disagreement, NOT new anatomy")
    out_fov = fov
    print(f"  focused ONLY       {(B & ~A).sum() * vox:9.0f} mm3  "
          f"(what export_extra_bone ships)")
    return dict(A=A, B=B, fov=out_fov, g_lo=g_lo, spacing=sp, shape=shape)


def main():
    ap = argparse.ArgumentParser()
    for n in ("tp", "fp", "mp", "label"):
        ap.add_argument(n)
    ap.add_argument("--save")
    a = ap.parse_args()
    out = build(a.tp, a.fp, a.mp, int(a.label))
    if a.save:
        os.makedirs(a.save, exist_ok=True)
        np.savez_compressed(os.path.join(a.save, "joined.npz"),
                            A=np.packbits(out["A"]), B=np.packbits(out["B"]),
                            fov=np.packbits(out["fov"]),
                            shape=np.array(out["shape"]), g_lo=out["g_lo"],
                            spacing=out["spacing"])
        print(f"-> {a.save}/joined.npz")


if __name__ == "__main__":
    main()
