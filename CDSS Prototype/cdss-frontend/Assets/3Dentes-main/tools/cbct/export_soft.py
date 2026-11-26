#!/usr/bin/env python3
"""Export pulp and PDL into the CBCT asset tree so the atlas can show them.

Both were modelled and neither was viewable: they existed as STLs in the working
directory and were never added to the manifest. This puts them in the build.

Per tooth, keyed as <FMA>-pulp and <FMA>-pdl so the FMA id stays the join key and
the app can associate each with its tooth. Provenance differs between them and
from the teeth, and the atlas must not present them alike:

  pulp   MEASURED lumen -- intensity-deficit integration
  pdl    MEASURED location, EXAGGERATED thickness -- a 0.2 mm ligament is
         ~1.3 voxels and will not mesh at its true size

Usage: python3 tools/cbct/export_soft.py <pulp-dir> <pdl-dir> <split-dir> <out-dir>
"""
import json
import os
import struct
import sys

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segment_tooth import write_binary_stl
from meshsmooth import taubin, weld
from export_teeth import decimate

TARGET_PULP = 2500
TARGET_PDL = 3000
TARGET_LAMINA = 3000


def load_stl(path):
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[80:84])[0]
    rec = np.frombuffer(b[84:84 + n * 50], dtype=np.uint8).reshape(n, 50)
    return rec[:, 12:48].copy().view("<f4").reshape(n * 3, 3).astype(np.float64)


def process(soup, target, smooth=8):
    verts, faces = weld(soup)
    if len(faces) < 8:
        return None
    verts = taubin(verts, faces, smooth)
    verts, faces = decimate(verts, faces, target)
    return taubin(verts, faces, 3), faces


def main():
    pulp_dir, pdl_dir, split_dir, outdir = sys.argv[1:5]
    os.makedirs(outdir, exist_ok=True)
    rep = json.load(open(os.path.join(split_dir, "split.json")))
    teeth = [(t["universal"], t["fma"], a)
             for a in ("upper", "lower") for t in rep[a]["teeth"]]
    made = {"pulp": 0, "pdl": 0}

    # Pulp is NOT exported here. pulp_solid.py owns <FMA>-pulp.stl, and this
    # module used to write the same filenames from the older tube model -- so
    # running it afterwards silently replaced solid pulp with thin filaments.
    # The pulp directory is still read below, for the centroids the PDL split
    # needs.

    # PDL, per tooth. pdl.py now meshes each tooth's OWN mask, padded, so every
    # ligament is closed by construction. Prefer those.
    #
    # The old path below cut the per-tooth pieces out of the whole-arch mesh by
    # assigning each FACE to its nearest pulp centroid, and a face subset of a
    # closed surface is open along every cut -- which is how 27 of 28 shipped
    # with holes. It is kept only as a fallback for a pdl directory built before
    # the change, and it prints when it is used, because a silently open mesh is
    # exactly the failure that survived four releases.
    per_tooth = 0
    for num, fma, arch in sorted(teeth):
        src = os.path.join(pdl_dir, f"{fma}-pdl.stl")
        if not os.path.exists(src):
            continue
        got = process(load_stl(src), TARGET_PDL, smooth=6)
        if got:
            write_binary_stl(os.path.join(outdir, f"{fma}-pdl.stl"), *got)
            made["pdl"] += 1
            per_tooth += 1
    if per_tooth:
        print(f"pdl: {per_tooth} per-tooth meshes (closed by construction)")

    # The lamina dura rides along with the PDL: same source module, same crop,
    # same per-tooth mask, so it is exported here rather than in a module of its
    # own that would need all the same inputs.
    lamina = 0
    for num, fma, arch in sorted(teeth):
        src = os.path.join(pdl_dir, f"{fma}-lamina.stl")
        if not os.path.exists(src):
            continue
        got = process(load_stl(src), TARGET_LAMINA, smooth=6)
        if got:
            write_binary_stl(os.path.join(outdir, f"{fma}-lamina.stl"), *got)
            lamina += 1
    if lamina:
        print(f"lamina dura: {lamina} per-tooth meshes")

    # Fallback: split the arch mesh. LEAVES EVERY PIECE OPEN -- see above.
    for arch in ("upper", "lower") if not per_tooth else ():
        src = os.path.join(pdl_dir, f"pdl-{arch}.stl")
        if not os.path.exists(src):
            continue
        print(f"  WARNING: splitting the {arch} arch mesh; the pieces will be "
              f"OPEN. Rebuild with a current pdl.py to get closed ligaments.")
        soup = load_stl(src)
        verts, faces = weld(soup)
        centres = []
        ids = []
        for num, fma, a in sorted(teeth):
            if a != arch:
                continue
            p = os.path.join(pulp_dir, f"{fma}-pulp.stl")
            if not os.path.exists(p):
                p = os.path.join(outdir, f"{fma}-pulp.stl")
            if not os.path.exists(p):
                continue
            v = load_stl(p)
            centres.append(v.mean(axis=0))
            ids.append(fma)
        if not centres:
            continue
        C = np.array(centres)
        fc = verts[faces].mean(axis=1)
        owner = np.argmin(((fc[:, None, :] - C[None, :, :]) ** 2).sum(-1), axis=1)
        for i, fma in enumerate(ids):
            sel = faces[owner == i]
            if len(sel) < 40:
                continue
            got = process(verts[sel].reshape(-1, 3), TARGET_PDL, smooth=6)
            if got:
                write_binary_stl(os.path.join(outdir, f"{fma}-pdl.stl"), *got)
                made["pdl"] += 1
    print(f"pulp meshes: {made['pulp']}   pdl meshes: {made['pdl']}")
    print(f"-> {outdir}")


if __name__ == "__main__":
    main()
