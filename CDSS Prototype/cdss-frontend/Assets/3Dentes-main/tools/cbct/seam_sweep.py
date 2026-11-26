#!/usr/bin/env python3
"""Sweep the overlap pad in export_extra_bone.py and measure the seam it leaves.

THE PAD IS A GUESS AND HAS NEVER BEEN FITTED. `export_extra_bone.py` removes the
centred volume's own bone dilated by OVERLAP_PAD_VOX = 2 before meshing what is
left, so the focused exposure's surface starts two voxels (0.32 mm) outside the
centred one BY CONSTRUCTION, and marching cubes then puts each surface half a
voxel inside its own mask. Both effects open a gap, and a gap prints DARK.

This rebuilds the extra bone at several pad values -- including NEGATIVE ones,
which let the focused label reach back INTO the centred bone -- and measures
what each leaves at the join. The expensive part, resampling the centred label
through the transform into the moving grid, is done once and reused.

WHAT COUNTS AS BETTER IS NOT OBVIOUS, and that is the point of measuring:

  - For the 3D render, an overlap is invisible and a gap is a hole. Overlap wins.
  - For the DRR, an overlap DOUBLE-COUNTS path length and prints bright, which
    is the same size of error as the gap printing dark. Neither wins.

So the target is surfaces that MEET: the distance distribution pushed to zero
with as little depth of overlap as possible. If no constant does both, that is a
result -- it says the pad cannot be a constant, which is what the wishlist
suspected -- and it needs to be measured rather than assumed.

Usage: seam_sweep.py <transform.json> <fixed-pred> <moving-pred> <moving.nrrd>
                     <centered.nrrd> <label> <out-fma> <centred.stl> <out-dir>
                     [--pads 2,1,0,-1,-2]
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vol import Volume
from read_nifti import read_nifti
from register import euler
from segment_tooth import write_binary_stl
from export_bone import mesh_mask, TARGET
from export_extra_bone import fixed_index_of, MIN_PIECE_MM3


def build(new, vm, vf, R, t_vox, centre, sp, path):
    got = mesh_mask(new, vm, TARGET["bone"])
    if not got:
        return None
    verts_world, faces = got
    mi = np.empty_like(verts_world)
    mi[:, 0] = (verts_world[:, 2] - vm.origin[2]) / sp[2]
    mi[:, 1] = (verts_world[:, 1] - vm.origin[1]) / sp[1]
    mi[:, 2] = (verts_world[:, 0] - vm.origin[0]) / sp[0]
    fi = fixed_index_of(mi, R, t_vox, centre)
    out = np.empty_like(verts_world)
    out[:, 0] = vf.origin[0] + fi[:, 2] * sp[0]
    out[:, 1] = vf.origin[1] + fi[:, 1] * sp[1]
    out[:, 2] = vf.origin[2] + fi[:, 0] * sp[2]
    write_binary_stl(path, out, faces)
    return len(faces)


def main():
    ap = argparse.ArgumentParser()
    for n in ("tp", "fp", "mp", "moving_nrrd", "fixed_nrrd", "label",
              "out_fma", "centred_stl", "outdir"):
        ap.add_argument(n)
    ap.add_argument("--pads", default="2,1,0,-1,-2")
    a = ap.parse_args()
    label = int(a.label)
    os.makedirs(a.outdir, exist_ok=True)

    p = json.load(open(a.tp))
    fl, _, pix = read_nifti(a.fp)
    ml, _, _ = read_nifti(a.mp)
    vm = Volume.load(a.moving_nrrd)
    vf = Volume.load(a.fixed_nrrd)
    sp = np.array([float(x) for x in pix], float)
    vox = float(np.prod(sp))
    R = euler(*np.radians(p["rotation_deg"]))
    t_vox = np.asarray(p["translation_mm"]) / sp
    centre = np.array(ndi.center_of_mass(fl == p["label"]))

    moving = ml == label
    print(f"moving label {label}   {moving.sum() * vox:9.0f} mm3", flush=True)

    # ONCE: the centred volume's own bone, resampled into the moving grid.
    idx = np.stack(np.indices(moving.shape, dtype=np.float32), axis=-1)
    src = fixed_index_of(idx.reshape(-1, 3), R, t_vox, centre).reshape(idx.shape)
    have0 = ndi.map_coordinates((fl == label).astype(np.float32),
                                [src[..., 0], src[..., 1], src[..., 2]],
                                order=1, mode="constant", cval=0.0) > 0.5
    del idx, src
    print(f"  centred bone here   {have0.sum() * vox:9.0f} mm3", flush=True)

    rows = []
    for pad in [int(x) for x in a.pads.split(",")]:
        # pad > 0 pushes the focused label AWAY from the centred bone (today's
        # behaviour); pad < 0 lets it reach back INTO it.
        if pad > 0:
            have = ndi.binary_dilation(have0, np.ones((3, 3, 3)), pad)
        elif pad < 0:
            have = ndi.binary_erosion(have0, np.ones((3, 3, 3)), -pad)
        else:
            have = have0
        new = moving & ~have
        new = ndi.binary_closing(new, np.ones((3, 3, 3)))
        lab, n = ndi.label(new, structure=np.ones((3, 3, 3)))
        if n:
            szs = ndi.sum(new, lab, range(1, n + 1)) * vox
            new = np.isin(lab, [i + 1 for i, z in enumerate(szs)
                                if z >= MIN_PIECE_MM3])
        stl = os.path.join(a.outdir, f"{a.out_fma}-pad{pad}.stl")
        tris = build(new, vm, vf, R, t_vox, centre, sp, stl)
        rep = os.path.join(a.outdir, f"audit-pad{pad}.json")
        subprocess.run([sys.executable, os.path.join(HERE, "seam_audit.py"),
                        a.centred_stl, stl, "--json", rep,
                        "--label", f"{a.out_fma} pad={pad}"],
                       stdout=subprocess.DEVNULL, check=True)
        r = json.load(open(rep))
        rows.append(dict(pad=pad, mm3=round(new.sum() * vox), tris=tris,
                         **{k: r.get(k) for k in
                            ("near_vertices", "surface_mm", "within_0.1mm",
                             "within_0.2mm", "within_0.3mm",
                             "inside_centred_pct", "overlap_depth_mm")}))
        s = rows[-1]
        print(f"pad {pad:+d}  {s['mm3']:6d} mm3  "
              f"closest {s['surface_mm']['closest']:.3f}  "
              f"p5 {s['surface_mm']['p5']:.3f}  "
              f"median {s['surface_mm']['p50']:.3f}  "
              f"<=0.2mm {s['within_0.2mm']:5.1f}%  "
              f"inside {s['inside_centred_pct']:5.2f}%  "
              f"depth {s['overlap_depth_mm']:.2f}", flush=True)

    json.dump(rows, open(os.path.join(a.outdir, "sweep.json"), "w"), indent=2)
    print(f"-> {a.outdir}/sweep.json")


if __name__ == "__main__":
    main()
