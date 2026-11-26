#!/usr/bin/env python3
"""Mesh two exposures' bone as MATERIALS, so the wall between them is one surface.

WHY NOT THE PREVIOUS ATTEMPT. export_joined_bone.py meshes the union once and
then RECOVERS the wall: classify triangles by exposure, dissolve misclassified
islands, walk the boundary into loops, triangulate each loop as a cap. Every
step of that works except the last -- three triangulations of the same loop left
only 72%, 59% and 60% of the cap inside the bone, because the mandible's main
loop follows bone around a corner of the field-of-view BOX and no single plane
spans it without chording through the jaw (CLAUDE.md 245).

The fix is to stop recovering the boundary and let the mesher emit it.

THE CONSTRUCTION, and it is three lines of arithmetic rather than an algorithm:

    fU = smoothed indicator of the UNION      (outer surface is fU = 0.5)
    gA = smoothed indicator of A's TERRITORY  (the wall is gA = 0.5)

    A' = marching cubes of min(fU,     gA) at 0.5
    B' = marching cubes of min(fU, 1 - gA) at 0.5

`min` is intersection. min(fU, gA) is "inside the union AND in A's territory",
so its 0.5 isosurface is A's outer surface where gA > 0.5, and the WALL where
fU > 0.5. The same for B with the territory inverted.

WHY THE WALL COMES OUT IDENTICAL IN BOTH. Along a wall edge the active field is
gA for A' and 1-gA for B', and gA crosses 0.5 exactly where 1-gA does -- the
same parameter along the same grid edge. So marching cubes places the same
vertex. The wall is not made to agree; it cannot disagree.

And because it is an isosurface of the voxel data rather than a triangulation
spanning a loop, it FOLLOWS THE BONE. That is the property every cap failed.

WHAT IS STILL OPEN: decimation. 3M triangles have to come down to ~44k, and
decimating A' and B' independently would pull their walls apart again. See the
`--full` flag and the notes at the bottom of the report.

Usage: export_material_bone.py <joined.npz> <centered.nrrd> <fma-A> <fma-B> <out-dir>
"""
import argparse
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vol import Volume
from segment_tooth import write_binary_stl
from export_teeth import decimate
from meshsmooth import taubin, mesh_volume
from export_joined_bone import cap_loop

SMOOTH = 1.0
ATTRIB_VOX = 3
WALL_MIN_FU = 0.62   # above this the triangle is buried, so it is wall not surface
WALL_G_LO, WALL_G_HI = 0.15, 0.85   # ...and the territory field must be in transition


def unpack(npz, key):
    n = int(np.prod(npz["shape"]))
    return np.unpackbits(npz[key])[:n].astype(bool).reshape(tuple(npz["shape"]))


def seal(verts, faces, tag):
    """Ear-clip any hole left by the split. There should be almost none.

    The topological split leaves the sheets with matching boundaries, but a
    handful of tiny sheets can still be classified onto the wrong side and open
    a small hole -- one, on the mandible. A hole is fatal for the DRR (it cannot
    integrate depth through a surface that does not close), and these are small
    enough that ear-clipping them is a repair rather than an invention. If this
    ever seals a LARGE loop, the split is wrong and the loop is the symptom;
    that is why the size is reported.
    """
    from collections import Counter, defaultdict
    c = Counter()
    for t in faces:
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            c[(min(a, b), max(a, b))] += 1
    open_edges = [e for e, n in c.items() if n == 1]
    if not open_edges:
        return faces
    adj = defaultdict(list)
    for a, b in open_edges:
        adj[a].append(b)
        adj[b].append(a)
    seen, patches = set(), []
    for start in list(adj):
        if start in seen:
            continue
        loop, cur, prev = [start], start, None
        seen.add(start)
        while True:
            nxt = [v for v in adj[cur] if v != prev and v not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        if len(loop) < 3:
            continue
        tri, flat, err = cap_loop(verts, loop)
        if err:
            print(f"  {tag}: hole of {len(loop)} verts NOT sealed ({err})")
            continue
        patches.append(tri)
        print(f"  {tag}: sealed a hole of {len(loop)} vertices "
              f"(planarity {flat:.3f})")
    return np.vstack([faces] + patches) if patches else faces


def edge_stats(verts, faces, tag):
    from collections import Counter
    c = Counter()
    for f in faces:
        for k in range(3):
            a, b = f[k], f[(k + 1) % 3]
            c[(min(a, b), max(a, b))] += 1
    holes = sum(1 for v in c.values() if v == 1)
    nm = sum(1 for v in c.values() if v > 2)
    print(f"  {tag:10s} {len(verts):8,} verts {len(faces):9,} tris  "
          f"{holes} holes  {nm} non-manifold")
    return holes


def main():
    ap = argparse.ArgumentParser()
    for n in ("npz", "fixed_nrrd", "fma_a", "fma_b", "outdir"):
        ap.add_argument(n)
    ap.add_argument("--attrib", type=int, default=ATTRIB_VOX)
    ap.add_argument("--target", type=int, default=44000)
    ap.add_argument("--band", type=float, default=20.0)
    ap.add_argument("--inset", type=float, default=16.0)
    o = ap.parse_args()
    os.makedirs(o.outdir, exist_ok=True)

    z = np.load(o.npz)
    A, B = unpack(z, "A"), unpack(z, "B")
    fov = unpack(z, "fov")
    o_inset = None
    g_lo, sp = z["g_lo"], z["spacing"]
    vf = Volume.load(o.fixed_nrrd)
    vox = float(np.prod(sp))
    # the mask the meshes should reproduce: the centred scan inside its own
    # field of view, the focused scan only beyond it
    # the centred scan supplies bone only where it is at full strength; the
    # focused scan supplies everything beyond that, INCLUDING the fade zone
    inset_ok = ndi.binary_erosion(fov, np.ones((3, 3, 3)), int(o.inset)) if o.inset else fov
    U = (A & inset_ok) | (B & ~inset_ok)
    # NO "never lose bone" GUARD HERE. Adding back `A & ~dilate(B)` reinstates
    # exactly the faded, patchy label in the last 1.6 mm that the inset exists
    # to discard -- the guard put the torn edge straight back and the cut edge
    # measured no flatter for it (sd 0.338 mm either way). Losing the fade is
    # the POINT: it is segmentation dropout, not anatomy, and the focused scan
    # measures that bone properly.
    print(f"target {U.sum() * vox:.0f} mm3 in {U.shape} "
          f"(centred {A.sum() * vox:.0f} + focused beyond the FOV "
          f"{(B & ~fov).sum() * vox:.0f})")

    # ---- BLEND AT THE FIELD-OF-VIEW WALL, do not union the two labels ----
    #
    # The first version meshed the plain union and it was WRONG, in a way the
    # operator saw before any measurement found it: he reported the mandible
    # offset from the maxilla. The two registered mandibles sit at Dice 0.684,
    # so inside the centred scan's own territory their union INFLATES the jaw by
    # 8.1% -- 1,753 mm3 of bone the centred scan says is not there -- and
    # asymmetrically, because the misregistration has a direction. Volume
    # conservation against the union mask certified that as correct, because the
    # union mask was the wrong reference: it is the OR of two misaligned
    # measurements, not the anatomy.
    #
    # The right split is the one the operator proposed: cut where the centred
    # scan STOPS HAVING INFORMATION -- its own field-of-view box -- not wherever
    # the two labels disagree. Inside the box the centred exposure is
    # authoritative; outside it only the focused one can speak.
    #
    # And rather than switching hard at the wall, the two indicators are BLENDED
    # across a band, so the surface flows from one exposure's to the other's
    # instead of stepping by the registration residual at the boundary. That was
    # the other half of what he was describing.
    fA = ndi.gaussian_filter(A.astype(np.float32), SMOOTH)
    fB = ndi.gaussian_filter(B.astype(np.float32), SMOOTH)
    # signed distance to the FOV box wall, positive inside -- analytic, it is a box
    zz, yy, xx = (np.arange(s, dtype=np.float32) for s in U.shape)
    lo = np.array([np.argmax(fov.any((1, 2))), np.argmax(fov.any((0, 2))),
                   np.argmax(fov.any((0, 1)))], float)
    hi = np.array([len(a) - 1 - np.argmax(fov.any(ax)[::-1]) for a, ax in
                   ((zz, (1, 2)), (yy, (0, 2)), (xx, (0, 1)))], float)
    dz = np.minimum(zz - lo[0], hi[0] - zz)[:, None, None]
    dy = np.minimum(yy - lo[1], hi[1] - yy)[None, :, None]
    dx = np.minimum(xx - lo[2], hi[2] - xx)[None, None, :]
    d = np.minimum(np.minimum(dz + 0 * dy, dx + 0 * dz), dy + 0 * dx).astype(np.float32)
    # THE BAND MUST SIT ENTIRELY INSIDE THE FOV, and the first version did not.
    # Centring it on the wall blends A with B on BOTH sides -- but outside the
    # wall A's indicator is 0 because it has NO DATA there, not because there is
    # no bone. Averaging "no data" as "no bone" halves the field just outside
    # the wall and erodes the jaw exactly where the focused scan is supposed to
    # take over.
    #
    # So the ramp runs from 1 at `band` voxels INSIDE the wall to 0 AT the wall,
    # and stays 0 beyond it. Both exposures have real data everywhere in that
    # range. The cost is that a thin shell just inside the wall is described by
    # the focused scan rather than the centred one; that shell is far from the
    # dentition and it is what buys a surface that flows instead of stepping.
    # INSET THE CUT INTO GOOD DATA. The centred label does not END at the FOV
    # floor, it FADES OUT over the last ~1.6 mm as the reconstruction degrades:
    # measured on the mandible, the cross-section runs 1.1, 13.9, 75.8, 169,
    # 243, 349, 406, 516, 586, 643 mm2 over ten slices before settling at ~660.
    # Meshing that fade produces the torn inferior border the operator sees, and
    # cutting AT the FOV boundary -- which every earlier attempt did -- keeps
    # every bit of it.
    #
    # So the handover happens `inset` voxels inside the boundary, where the
    # centred scan is still at full strength, and the focused scan supplies
    # everything below. That is what the operator meant by jumping from one to
    # the other "somewhere along the mandible" rather than at the edge.
    d = d - o.inset
    print(f"  cut inset          {o.inset} voxels ({o.inset * sp[0]:.2f} mm) inside "
          f"the FOV boundary, into full-strength data")
    w = np.clip(d / max(o.band, 1e-6), 0.0, 1.0)
    print(f"  blend band         {o.band} voxels ({o.band * sp[0]:.2f} mm) inside "
          f"the centred scan's FOV wall, ramping to it")
    fU = w * fA + (1.0 - w) * fB
    gA = ndi.gaussian_filter((d > 0).astype(np.float32), SMOOTH)
    del A, B, fA, fB, d

    out = {}
    for tag, fma, field in (("centred", o.fma_a, np.minimum(fU, gA)),
                            ("focused", o.fma_b, np.minimum(fU, 1.0 - gA))):
        v, f, _, _ = marching_cubes(field, level=0.5)
        edge_stats(v, f, tag)
        out[tag] = (v, f)
        del field

    # ---- the load-bearing check: is the wall the SAME surface in both? -----
    (va, fa), (vb, fb) = out["centred"], out["focused"]
    # wall vertices are the ones buried inside the union
    def wall_of(v):
        s = ndi.map_coordinates(fU, [v[:, 0], v[:, 1], v[:, 2]],
                                order=1, mode="constant", cval=0.0)
        return v[s > 0.5 + 1e-3]
    wa, wb = wall_of(va), wall_of(vb)
    print(f"\n  wall vertices      centred {len(wa):,}   focused {len(wb):,}")
    if len(wa) and len(wb):
        from scipy.spatial import cKDTree
        d = cKDTree(wa).query(wb, workers=-1)[0]
        print(f"  focused wall -> centred wall: max {d.max():.6f} mm, "
              f"median {np.median(d):.6f}, {100 * np.mean(d < 1e-6):.2f}% exact")
        print("  (exact coincidence is the whole point; anything else means the "
              "two fields did not cross at the same place)")

    # ---- decimate ONCE, as one object, so the wall cannot drift -----------
    #
    # Decimating A' and B' separately would pull their walls apart again, which
    # is the entire defect this construction exists to remove. So they are
    # welded into ONE mesh first -- the wall vertices are bit-identical, so an
    # exact weld merges them with no tolerance to choose -- the duplicate wall
    # faces are dropped so it is not decimated twice, and the split is done
    # AFTERWARDS by asking the voxel fields which side each surviving triangle
    # is on. Whatever the decimator does to the wall, it does once.
    if o.target:
        nv = len(va)
        verts = np.vstack([va, vb])
        faces = np.vstack([fa, fb + nv])
        key = np.round(verts, 5)
        _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        verts = verts[idx]
        faces = inv[faces]
        print(f"\n  welded             {nv + len(vb):,} -> {len(verts):,} verts "
              f"({100 * (1 - len(verts) / (nv + len(vb))):.1f}% shared)")
        good = ((faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2])
                & (faces[:, 0] != faces[:, 2]))
        faces = faces[good]
        # drop one copy of every face that now appears twice (the shared wall)
        sk = np.sort(faces, axis=1)
        _, first, counts = np.unique(sk, axis=0, return_index=True,
                                     return_counts=True)
        dup = int((counts > 1).sum())
        faces = faces[np.sort(first)]
        print(f"  wall de-duplicated {dup:,} faces appeared twice -> kept once")

        verts = taubin(verts, faces, 16)
        verts, faces = decimate(verts, faces, o.target)
        verts = taubin(verts, faces, 4)
        print(f"  decimated          {len(faces):,} triangles")

        # ---- recover the split TOPOLOGICALLY, not by threshold ----------
        #
        # Classifying every triangle independently by sampling the fields at its
        # centroid left 3,712 holes: a per-face threshold does not respect the
        # junction curve, so each sheet came out with a ragged edge. But the
        # structure is already IN the mesh -- three sheets (A's outer surface,
        # B's outer surface, and the wall) meet along one curve, and that curve
        # is exactly the set of edges with THREE incident faces. Cut there and
        # the sheets fall out as connected components with matching boundaries,
        # whatever the decimator did to them.
        from collections import defaultdict
        owner = defaultdict(list)
        for fi, t in enumerate(faces):
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                owner[(min(a, b), max(a, b))].append(fi)
        junction = {e for e, fl in owner.items() if len(fl) > 2}
        nbr = defaultdict(list)
        for e, fl in owner.items():
            if e in junction or len(fl) != 2:
                continue
            nbr[fl[0]].append(fl[1])
            nbr[fl[1]].append(fl[0])
        comp = -np.ones(len(faces), int)
        groups = []
        for start in range(len(faces)):
            if comp[start] >= 0:
                continue
            c = len(groups)
            stack, members = [start], []
            comp[start] = c
            while stack:
                fi = stack.pop()
                members.append(fi)
                for j in nbr.get(fi, ()):
                    if comp[j] < 0:
                        comp[j] = c
                        stack.append(j)
            groups.append(np.asarray(members))
        print(f"  junction           {len(junction)} edges with 3+ faces -> "
              f"{len(groups)} sheet(s): "
              f"{sorted((len(g) for g in groups), reverse=True)[:6]}")

        cent = verts[faces].mean(axis=1)
        fsv = ndi.map_coordinates(fU, [cent[:, 0], cent[:, 1], cent[:, 2]],
                                  order=1, mode="constant", cval=0.0)
        gsv = ndi.map_coordinates(gA, [cent[:, 0], cent[:, 1], cent[:, 2]],
                                  order=1, mode="constant", cval=0.0)
        wall = np.zeros(len(faces), bool)
        centred = np.zeros(len(faces), bool)
        for g in groups:
            # A SHEET IS WALL ONLY IF IT IS AT THE MATERIAL INTERFACE. Testing
            # "is it buried" alone (median fU high) is not enough: any small
            # sheet inside the bone -- an internal cavity, a stray fragment --
            # passes it, and wall sheets are copied into BOTH meshes, so a
            # fragment 34 mm above the centred scan's field of view ended up
            # duplicated in the maxilla and blew its bounding box from 37.4 mm
            # to 71.4 mm while leaving the VOLUME right, which is why the volume
            # check did not catch it. The wall is where the territory field is
            # in transition, so gA must be near 0.5 as well.
            gm = float(np.median(gsv[g]))
            if np.median(fsv[g]) > WALL_MIN_FU and WALL_G_LO < gm < WALL_G_HI:
                wall[g] = True
            else:
                centred[g] = gm > 0.5
        print(f"  wall               {int(wall.sum()):,} triangles;  outer "
              f"{int((~wall).sum()):,} ({int(centred.sum()):,} centred)")
        fa = np.vstack([faces[centred & ~wall], faces[wall]])
        fb = np.vstack([faces[~centred & ~wall], faces[wall][:, ::-1]])
        va = vb = verts
        # Sealing can leave a hole behind: the walk marks vertices globally, so
        # two loops sharing a vertex are not both found in one pass. Repeat
        # until it converges rather than assuming one pass is enough -- the
        # maxilla needed three.
        for _ in range(6):
            n0 = len(fa) + len(fb)
            fa = seal(verts, fa, "centred")
            fb = seal(verts, fb, "focused")
            if len(fa) + len(fb) == n0:
                break
        edge_stats(va, fa, "centred")
        edge_stats(vb, fb, "focused")
        out["centred"], out["focused"] = (va, fa), (vb, fb)

        # ---- the check that replaces seam_audit for this construction -----
        #
        # With an abutting join the question was "how far apart are the two
        # surfaces". With a SHARED wall that question is meaningless -- they are
        # the same surface -- and the thing to verify instead is the arithmetic
        # the DRR does: the two meshes' volumes must ADD UP to the union, with
        # nothing lost to a gap and nothing counted twice by an overlap.
        va_mm3 = mesh_volume(verts, fa) * vox
        vb_mm3 = mesh_volume(verts, fb) * vox
        tgt = float(U.sum()) * vox
        print(f"\n  volume check       centred {va_mm3:.0f} + focused "
              f"{vb_mm3:.0f} = {va_mm3 + vb_mm3:.0f} mm3 "
              f"against a union mask of {tgt:.0f} "
              f"({100 * (va_mm3 + vb_mm3 - tgt) / tgt:+.2f}%)")

    world_of = lambda v: np.stack([
        vf.origin[0] + (v[:, 2] + g_lo[2]) * sp[0],
        vf.origin[1] + (v[:, 1] + g_lo[1]) * sp[1],
        vf.origin[2] + (v[:, 0] + g_lo[0]) * sp[2]], axis=1)
    for tag, fma in (("centred", o.fma_a), ("focused", o.fma_b)):
        v, f = out[tag]
        path = os.path.join(o.outdir, f"{fma}.stl")
        write_binary_stl(path, world_of(v), f)
        print(f"-> {path}  {len(f):,} triangles")


if __name__ == "__main__":
    main()
