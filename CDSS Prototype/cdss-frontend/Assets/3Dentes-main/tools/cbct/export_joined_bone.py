#!/usr/bin/env python3
"""Mesh the union of two exposures' bone ONCE, then split it along a SHARED wall.

THE PROBLEM THIS SOLVES. The centred exposure's bone and a focused exposure's
are currently meshed separately and left to abut. Three defects live at that
join and they are not the same defect (CLAUDE.md 242): a GAP, a LEDGE, and --
the one the eye actually sees -- a ~30 degree break in surface NORMALS, because
each mesh's outer surface rolls over into its own field-of-view wall. No amount
of post-hoc smoothing removes a corner that the build put there, so the build
has to stop putting it there.

THE CONSTRUCTION.

  1. Mesh the UNION once, in one grid holding both labels (join_grid.py). The
     outer surface is then a single marching-cubes surface with no corner and
     no seam anywhere on it -- that is what kills the crease.
  2. Classify each triangle by which exposure's bone its centroid sits in.
  3. The two classes meet along one or more closed loops. Triangulate the
     cross-section bounded by each loop ONCE, as a cap.
  4. Ship centred = its triangles + the cap, focused = its triangles + the SAME
     cap reversed.

So the wall is one surface used twice, with opposite winding. Both meshes stay
closed, which the DRR needs; a ray leaves one exactly where it enters the other,
so the path length adds up with no gap to print dark and no overlap to print
bright; and `mandible`/`ramus` and `maxilla`/`midface` stay separate layers, so
which exposure measured what is still in the model. That was the operator's
requirement and it is why this is built rather than simply shipping the union.

WHAT IT COSTS, and it must be said rather than buried: the focused label is
RESAMPLED into the joined grid, where before only its finished vertices were
transformed. Measured cost is 0.3% of the label, a sub-voxel shell lost to
thresholding an interpolated binary. Nothing is CLIPPED -- the joined grid is
sized to hold both labels and the centred label round-trips at 100.0%.

Usage: export_joined_bone.py <joined.npz> <centered.nrrd> <out-fma-A> <out-fma-B>
                             <out-dir> [--target N]
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
from meshsmooth import taubin

TARGET = 44000       # for the union; the split parts inherit their share
SMOOTH = 1.0
MIN_LOOP = 8         # loops shorter than this are decimation noise, not a wall
ATTRIB_VOX = 3       # a triangle this close to centred bone belongs to it
MAJORITY_ROUNDS = 3  # clean stray triangles so the wall is a curve, not speckle
MIN_ISLAND = 400     # a patch smaller than this is an artefact, not a FOV cut
MAX_PLANARITY = 0.08 # above this a flat cap chords through the jaw; fan instead


def majority(faces, side, rounds):
    """Smooth a per-face classification over face adjacency.

    A single misclassified triangle in the middle of a region punches a hole in
    the wall and turns one loop into three, so the boundary has to be cleaned
    before it is walked.
    """
    from collections import defaultdict
    owner = defaultdict(list)
    for fi, f in enumerate(faces):
        for k in range(3):
            a, b = f[k], f[(k + 1) % 3]
            owner[(min(a, b), max(a, b))].append(fi)
    nbr = defaultdict(list)
    for fs in owner.values():
        if len(fs) == 2:
            nbr[fs[0]].append(fs[1])
            nbr[fs[1]].append(fs[0])
    side = side.copy()
    for _ in range(rounds):
        nxt = side.copy()
        for fi in range(len(faces)):
            n = nbr.get(fi)
            if not n:
                continue
            agree = sum(1 for j in n if side[j] == side[fi])
            if agree * 2 < len(n):
                nxt[fi] = not side[fi]
        if (nxt == side).all():
            break
        side = nxt
    return side


def unpack(npz, key):
    n = int(np.prod(npz["shape"]))
    return np.unpackbits(npz[key])[:n].astype(bool).reshape(tuple(npz["shape"]))


def face_neighbours(faces):
    from collections import defaultdict
    owner = defaultdict(list)
    for fi, f in enumerate(faces):
        for k in range(3):
            a, b = f[k], f[(k + 1) % 3]
            owner[(min(a, b), max(a, b))].append(fi)
    nbr = defaultdict(list)
    for fs in owner.values():
        if len(fs) == 2:
            nbr[fs[0]].append(fs[1])
            nbr[fs[1]].append(fs[0])
    return owner, nbr


def dissolve_islands(faces, side, nbr, min_faces):
    """Flip small connected patches so the wall is a few loops, not dozens.

    A patch of a hundred triangles marooned inside the other exposure's
    territory is a classification artefact, not a field-of-view boundary, and
    every one of them adds a loop that has to be capped. Un-capped loops leave
    HOLES -- 473 open edges on the first attempt -- so they are removed at the
    source instead of being dropped later.
    """
    side = side.copy()
    n = len(faces)
    comp = -np.ones(n, int)
    sizes = []
    for start in range(n):
        if comp[start] >= 0:
            continue
        c = len(sizes)
        stack, members = [start], []
        comp[start] = c
        while stack:
            fi = stack.pop()
            members.append(fi)
            for j in nbr.get(fi, ()):
                if comp[j] < 0 and side[j] == side[fi]:
                    comp[j] = c
                    stack.append(j)
        sizes.append(members)
    flipped = 0
    for members in sizes:
        if len(members) < min_faces:
            for fi in members:
                side[fi] = not side[fi]
            flipped += len(members)
    print(f"  dissolved          {sum(1 for m in sizes if len(m) < min_faces)} "
          f"island(s), {flipped} triangles, of {len(sizes)} patches")
    return side


def boundary_loops(faces, side):
    """Closed loops of edges where an A-face meets a B-face.

    On a closed manifold every edge has exactly two faces. The wall is the set
    of edges whose two faces are classified differently.
    """
    from collections import defaultdict
    owner = defaultdict(list)
    for fi, f in enumerate(faces):
        for k in range(3):
            a, b = f[k], f[(k + 1) % 3]
            owner[(min(a, b), max(a, b))].append(fi)
    edges = [e for e, fs in owner.items() if len(fs) == 2 and side[fs[0]] != side[fs[1]]]
    adj = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    seen = set()
    loops = []
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
        # Only keep it if it actually closes -- an open chain is a junction or
        # a broken walk, and capping one would not seal anything.
        if len(loop) >= MIN_LOOP and loop[0] in adj[loop[-1]]:
            loops.append(loop)
        elif len(loop) >= MIN_LOOP:
            print(f"    chain of {len(loop)} verts does not close -- skipped")
    return loops, len(edges)


def inside_polygon(pts, poly):
    """Even-odd test, vectorised over pts, for one 2D polygon."""
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cond = ((y0 > y) != (y1 > y))
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = x0 + (y - y0) * (x1 - x0) / np.where(y1 - y0 != 0, y1 - y0, 1)
        inside ^= cond & (x < xint)
    return inside


def ear_clip(xy):
    """Triangulate a simple polygon by ear clipping. Returns index triples.

    NOT Delaunay. A Delaunay triangulation of the loop's points is not
    guaranteed to contain the loop's own EDGES -- that needs a constrained
    triangulation -- so the cap's boundary came out different from the loop it
    was supposed to close and left 127 open edges. Ear clipping consumes the
    polygon boundary by construction, so the cap's boundary IS the loop, which
    is the property that makes both meshes closed.
    """
    n = len(xy)
    if n < 3:
        return []
    # work counter-clockwise
    area2 = 0.0
    for i in range(n):
        x0, y0 = xy[i]
        x1, y1 = xy[(i + 1) % n]
        area2 += x0 * y1 - x1 * y0
    order = list(range(n)) if area2 > 0 else list(range(n))[::-1]

    def cross(o, a, b):
        return ((xy[a][0] - xy[o][0]) * (xy[b][1] - xy[o][1])
                - (xy[a][1] - xy[o][1]) * (xy[b][0] - xy[o][0]))

    def inside(p, a, b, c):
        d1 = cross(a, b, p)
        d2 = cross(b, c, p)
        d3 = cross(c, a, p)
        neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (neg and pos)

    tris = []
    idx = order[:]
    guard = 0
    while len(idx) > 3 and guard < 8 * n:
        guard += 1
        clipped = False
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cross(a, b, c) <= 0:
                continue                      # reflex, not an ear
            if any(inside(p, a, b, c) for p in idx if p not in (a, b, c)):
                continue                      # something is inside it
            tris.append((a, b, c))
            idx.pop(k)
            clipped = True
            break
        if not clipped:
            # FORCED EAR. A loop that follows bone across more than one
            # field-of-view box face is not planar, and its projection can be
            # non-simple -- the 368-vertex mandibular loop is exactly that, and
            # strict ear clipping stalls on it at 331 of 366 triangles, leaving
            # the cap short and both meshes open. Clipping the sharpest corner
            # anyway always terminates and always yields n-2 triangles whose
            # boundary is the polygon, which is the property that matters.
            #
            # The cap's SHAPE does not have to be good, and this is the point of
            # a shared wall: whatever it is, mesh A exits through it exactly
            # where mesh B enters, so it cancels in the path length. It only has
            # to be shared, to close both meshes, and to stay buried inside the
            # bone -- which is checked after the fact, not assumed.
            best, best_a = None, None
            for k in range(len(idx)):
                a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
                v1 = xy[a] - xy[b]
                v2 = xy[c] - xy[b]
                n1 = np.linalg.norm(v1) * np.linalg.norm(v2)
                ang = float(np.dot(v1, v2) / n1) if n1 > 0 else 1.0
                if best_a is None or ang > best_a:
                    best, best_a = k, ang
            a, b, c = idx[best - 1], idx[best], idx[(best + 1) % len(idx)]
            tris.append((a, b, c))
            idx.pop(best)
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def cap_loop(verts, loop):
    """Triangulate the cross-section a loop bounds, in its own best-fit plane.

    The field-of-view cut is a box face, so each loop is close to planar and a
    projection is safe; planarity is reported so a loop that is not gets caught
    rather than capped badly.
    """
    P = verts[loop]
    c = P.mean(0)
    _, sv, vt = np.linalg.svd(P - c, full_matrices=False)
    flat = float(sv[2] / max(sv[0], 1e-9))
    xy = np.stack([(P - c) @ vt[0], (P - c) @ vt[1]], axis=1)
    tris = ear_clip(xy)
    if len(tris) != len(loop) - 2:
        return None, flat, (f"produced {len(tris)} triangles, expected "
                            f"{len(loop) - 2}")
    return np.asarray(loop)[np.asarray(tris)], flat, None


def planar_arcs(verts, loop, tol):
    """Split a loop into contiguous arcs each of which is near-planar.

    A field-of-view cut is a BOX, and a loop that follows bone around a box
    CORNER is not planar as a whole even though each piece of it lies in a flat
    face. Capping the whole loop in one best-fit plane chords straight through
    the jaw -- measured, only 72% of that cap stayed inside the bone, and the
    part that did not rendered as a flat plate across the ramus. Fanning it to
    an interior apex was worse still, at 59%.

    Splitting into planar arcs and capping each one closed by a CHORD keeps
    every cap inside the volume. The chords cost nothing: each is shared by two
    adjacent sub-caps with opposite orientation, so they cancel and the cap's
    outer boundary is still exactly the original loop -- which is the property
    that keeps both meshes closed.
    """
    P = verts[loop]
    n = len(loop)
    arcs, start = [], 0
    while start < n:
        end = start + 3
        while end <= n:
            seg = P[start:end] if end <= n else np.vstack([P[start:], P[:end - n]])
            if len(seg) >= 3:
                _, sv, _ = np.linalg.svd(seg - seg.mean(0), full_matrices=False)
                if sv[2] / max(sv[0], 1e-9) > tol:
                    break
            end += 1
        arcs.append(list(range(start, min(end - 1, n))))
        start = max(end - 1, start + 1)
    # fold a runt tail into its predecessor
    if len(arcs) > 1 and len(arcs[-1]) < 3:
        arcs[-2] += arcs[-1]
        arcs.pop()
    return arcs


def fan_cap(verts, loop, field, apex):
    """Cap a loop by fanning it to one interior apex vertex.

    WHY NOT THE PLANAR TRIANGULATION. A loop that follows bone across more than
    one field-of-view box face is not planar -- the mandibular one has planarity
    0.274 -- and a flat triangulation of it cuts straight through the jaw and
    out the other side. Measured: only 72% of the cap stayed buried, and the
    28% that did not rendered as a large flat plate across the ramus, which is
    worse than the crease it was meant to fix.

    A fan to a point KNOWN to be inside the bone bends the cap into the volume
    instead of chording across it. The apex is the centroid of the wall's own
    voxels, snapped to solid if the centroid of a curved wall falls outside it.

    The cap's shape still does not have to be good -- it cancels between the two
    meshes -- so the only test that matters is whether it stays buried, and that
    is measured, not assumed.
    """
    return apex, [(int(loop[i]), int(loop[(i + 1) % len(loop)]), apex)
                  for i in range(len(loop))]


def closed(faces):
    """(holes, non-manifold) -- edges used ONCE, and edges used more than twice.

    These are different defects and only the first is fatal. An edge used once
    is a hole and the DRR cannot integrate the mesh honestly. An edge used four
    times is two surfaces meeting along it -- which is what a cap seam against
    an existing mesh edge produces, and what `boundaryEdges` in
    tools/build-assets.mjs deliberately ignores, since it counts only
    once-used edges. Reporting them as one number said "375 open edges" when
    every one of them was in fact non-manifold and none was a hole.
    """
    from collections import Counter
    c = Counter()
    for f in faces:
        for k in range(3):
            a, b = f[k], f[(k + 1) % 3]
            c[(min(a, b), max(a, b))] += 1
    return (sum(1 for v in c.values() if v == 1),
            sum(1 for v in c.values() if v > 2))


def main():
    ap = argparse.ArgumentParser()
    for n in ("npz", "fixed_nrrd", "fma_a", "fma_b", "outdir"):
        ap.add_argument(n)
    ap.add_argument("--target", type=int, default=TARGET)
    o = ap.parse_args()
    os.makedirs(o.outdir, exist_ok=True)

    z = np.load(o.npz)
    A, B = unpack(z, "A"), unpack(z, "B")
    g_lo, sp = z["g_lo"], z["spacing"]
    vf = Volume.load(o.fixed_nrrd)
    vox = float(np.prod(sp))
    U = A | B
    print(f"union {U.sum() * vox:.0f} mm3 in a {U.shape} grid")

    # ---- one surface for the whole union --------------------------------
    f = ndi.gaussian_filter(U.astype(np.float32), SMOOTH)
    verts, faces, _, _ = marching_cubes(f, level=0.5)
    print(f"  marching cubes     {len(faces):,} triangles")
    verts = taubin(verts, faces, 16)
    verts, faces = decimate(verts, faces, o.target)
    verts = taubin(verts, faces, 4)
    print(f"  smoothed/decimated {len(faces):,} triangles, "
          f"{closed(faces)[0]} holes, {closed(faces)[1]} non-manifold edges")

    # ---- which exposure does each triangle belong to? --------------------
    #
    # NOT "is the centroid inside A". That was the first attempt and it produced
    # 356 boundary loops instead of a handful, because over most of the jaw BOTH
    # exposures measured the same outer surface -- so the union surface sits
    # exactly on A's own boundary and an inside/outside test there is a coin
    # flip. The result was not a wall, it was speckle.
    #
    # The wall wanted is the FIELD-OF-VIEW cut: the curve where the centred
    # exposure STOPS. So a triangle belongs to the centred exposure if it lies
    # within a short distance of A's bone, and to the focused exposure only
    # where A has nothing at all. Coincident surfaces attribute to the centred
    # volume, which is right -- it is the primary acquisition and the one whose
    # frame the atlas is in.
    grown = ndi.binary_dilation(A, np.ones((3, 3, 3)), ATTRIB_VOX)
    ga = ndi.gaussian_filter(grown.astype(np.float32), SMOOTH)
    cent = verts[faces].mean(axis=1)
    side = ndi.map_coordinates(ga, [cent[:, 0], cent[:, 1], cent[:, 2]],
                               order=1, mode="constant", cval=0.0) > 0.5
    side = majority(faces, side, MAJORITY_ROUNDS)
    owner, nbr = face_neighbours(faces)
    # repeat: dissolving an island can expose another one behind it
    for _ in range(4):
        prev = side.copy()
        side = dissolve_islands(faces, side, nbr, MIN_ISLAND)
        if (side == prev).all():
            break
    print(f"  centred exposure   {int(side.sum()):,} triangles;  "
          f"focused {int((~side).sum()):,}")

    loops, n_edges = boundary_loops(faces, side)
    print(f"  wall               {n_edges} edges in {len(loops)} loop(s): "
          f"{sorted((len(l) for l in loops), reverse=True)[:6]}")

    caps = []
    extra = []                       # apex vertices the fans need
    for i, loop in enumerate(loops):
        tri, flat, err = cap_loop(verts, loop)
        if (err is not None or flat > MAX_PLANARITY):
            # try planar arcs before falling back to a fan
            arcs = planar_arcs(verts, loop, MAX_PLANARITY)
            pieces, ok = [], len(arcs) > 1
            for arc in arcs:
                sub = [loop[i] for i in arc]
                if len(sub) < 3:
                    continue
                t2, f2, e2 = cap_loop(verts, sub)
                if e2:
                    ok = False
                    break
                pieces.append(t2)
            if ok and pieces:
                tri = np.vstack(pieces)
                print(f"    loop {i}: {len(loop)} verts -> {len(arcs)} planar "
                      f"arcs -> {len(tri)} cap triangles "
                      f"(whole-loop planarity was {flat:.3f})")
                caps.append(tri)
                continue
        use_fan = err is not None or flat > MAX_PLANARITY
        if use_fan:
            # apex: centroid of the loop, pulled onto solid bone if it is not
            # already there, so the fan bends into the jaw rather than across it
            c = verts[loop].mean(0)
            ci = np.round(c).astype(int)
            if not (0 <= ci[0] < U.shape[0] and 0 <= ci[1] < U.shape[1]
                    and 0 <= ci[2] < U.shape[2] and U[tuple(ci)]):
                zz, yy, xx = np.where(U[::4, ::4, ::4])
                pts = np.stack([zz * 4, yy * 4, xx * 4], 1).astype(float)
                c = pts[np.argmin(((pts - c) ** 2).sum(1))]
            apex = len(verts) + len(extra)
            extra.append(c)
            _, tri = fan_cap(verts, loop, f, apex)
            tri = np.asarray(tri)
            why = "not planar" if err is None else err
            print(f"    loop {i}: {len(loop)} verts -> {len(tri)} FAN triangles "
                  f"(planarity {flat:.3f}, {why})")
        else:
            print(f"    loop {i}: {len(loop)} verts -> {len(tri)} cap triangles, "
                  f"planarity {flat:.3f} (0 = flat)")
        caps.append(tri)
    if extra:
        verts = np.vstack([verts, np.asarray(extra)])
    if not caps:
        print("NO CAP BUILT -- nothing to ship")
        return
    cap = np.vstack(caps)

    # THE CAP MUST BE BURIED. Its shape cancels between the two meshes, but a
    # cap that pokes out through the outer surface would be a visible flap and
    # would put bone where there is none. Checked against the union's own field.
    ccent = verts[cap].mean(axis=1)
    inside_frac = float(np.mean(ndi.map_coordinates(
        f, [ccent[:, 0], ccent[:, 1], ccent[:, 2]],
        order=1, mode="constant", cval=0.0) > 0.5))
    print(f"  cap                {len(cap):,} triangles, "
          f"{100 * inside_frac:.1f}% buried inside the union "
          f"(100% wanted; anything visible would be a flap)")

    fa = np.vstack([faces[side], cap])
    fb = np.vstack([faces[~side], cap[:, ::-1]])
    for tag, fc in (("centred", fa), ("focused", fb)):
        h, nm = closed(fc)
        print(f"  {tag} mesh       {len(fc):,} tris, {h} holes, "
              f"{nm} non-manifold edges" + ("  <- FATAL" if h else ""))

    # ---- joined-grid index -> atlas world mm -----------------------------
    world = np.empty_like(verts)
    world[:, 0] = vf.origin[0] + (verts[:, 2] + g_lo[2]) * sp[0]
    world[:, 1] = vf.origin[1] + (verts[:, 1] + g_lo[1]) * sp[1]
    world[:, 2] = vf.origin[2] + (verts[:, 0] + g_lo[0]) * sp[2]

    for fma, fc in ((o.fma_a, fa), (o.fma_b, fb)):
        path = os.path.join(o.outdir, f"{fma}.stl")
        write_binary_stl(path, world, fc)
        print(f"-> {path}  {len(fc):,} triangles")


if __name__ == "__main__":
    main()
