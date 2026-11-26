#!/usr/bin/env python3
"""Weld and smooth the band where two exposures' bone meshes meet.

STATUS 2026-09-07: **TRIED, MEASURED, AND NOT SHIPPED.** It is kept because it
is what diagnosed the crease -- see "what the crease actually is" below -- and
because the diagnosis rules out a whole family of fixes. Do not reach for it
again without reading that.

    metric                       pad 0 alone      pad 0 + this
    ------------------------------------------------------------
    median separation             0.142 mm         0.146 mm
    join within 0.2 mm            62.6%            63.0%
    ledge at the rim (median)    +0.187 mm        +0.051 mm   <- the one win
    NORMAL BREAK at the rim        31.5 deg         27.7 deg   <- barely moved
    join interpenetrating          23.3%            39.8%      <- WORSE
    overlap depth                 0.496 mm         0.799 mm    <- WORSE

It moves 10,793 vertices of measured mesh, does not change what the crease looks
like, and makes the DRR's double-count worse. That is a bad trade in every
direction, so it was reverted.

WHAT THE CREASE ACTUALLY IS, which none of the earlier notes had right. It is
not a gap: closing the gap from 0.77 mm to 0.14 mm changed under 1% of pixels.
It is not mainly a ledge either: this tool removes 73% of the ledge and the line
is still there. It is a **~30 degree discontinuity in surface NORMALS**, and the
reason is structural -- each mesh's outer surface ROLLS OVER INTO ITS OWN FOV
WALL at the rim, over the voxel or two that marching cubes needs to turn a
corner. Taubin smoothing cannot remove it because the rim vertices belong to the
wall as well as to the outer surface, so averaging pulls them back into the
corner they came from. The corner is the thing that has to go, and no amount of
band smoothing will take it.

That leaves only fixes that change how the join is BUILT rather than how it is
finished, and those have a provenance cost that is the operator's to weigh --
see docs/wishlist.md.

The original description follows; the mechanism is still accurate and the ledge
measurement is the useful part.

WHAT THIS FIXES, AND WHAT IT DOES NOT. Setting OVERLAP_PAD_VOX to 0 in
export_extra_bone.py closed most of the GAP between the centred volume's bone
and a focused exposure's -- median separation 0.77 mm -> 0.14 mm in the mandible
-- and that is what the X-ray beam sees, because a ray only cares how much bone
lies on it. It did almost nothing for what the EYE sees: with the camera held
fixed, under 1% of pixels changed in the 3D view and the crease down the ramus
was still plainly there.

A crease is not a hole. It is a discontinuity in surface NORMALS between two
independently marching-cubed, independently decimated surfaces meeting at an
angle, and two surfaces 0.14 mm apart crease exactly as visibly as two 0.77 mm
apart. Closing the last 0.14 mm would not help either. The only thing that
removes it is making the two surfaces continuous ACROSS the join, which needs
connectivity they do not have -- they share no vertices.

SO: build the connectivity temporarily, smooth through it, and write the two
meshes back out separately.

  1. Find the join: vertices of each mesh within `band` of the other's surface.
  2. Add CROSS EDGES between mutually-near vertex pairs. These enter the
     Laplacian adjacency and NOT the face list, so no triangle is created, no
     mesh changes topology, and both stay closed -- which the DRR requires,
     since it integrates each mesh separately as back-face depth less
     front-face depth.
  3. Taubin-smooth over the augmented adjacency, with per-vertex weight falling
     from 1 at the join to 0 at `band`, so nothing outside the seam moves.
  4. Split back and write.

THE HONEST BOUND, and it is the reason this is a rendering fix rather than
invented geometry. Every vertex is clamped to `max_move` total displacement,
defaulting to 0.4 mm. The two exposures already disagree about where this bone
is by more than that -- the registration is rigid and sits at Dice 0.708 against
a 0.728 ceiling -- so reconciling them inside a narrow band moves no surface
further than the measurement's own disagreement, and moves BOTH sides rather
than dragging one exposure's bone onto the other's. The wishlist's provenance
caution allows exactly this and forbids exactly that. The report prints the
displacement actually used; if it ever approaches the cap, say so rather than
raising the cap.

Usage: seam_stitch.py <A.stl> <B.stl> <outA.stl> <outB.stl>
                      [--band MM] [--weld MM] [--iters N] [--max-move MM]
"""
import argparse
import os
import sys

import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from seam_audit import read_stl, surface_distance
from segment_tooth import write_binary_stl

BAND_MM = 1.2       # how far from the join smoothing reaches at all
WELD_MM = 0.4       # within this, vertices are treated as the same place
ITERS = 12
MAX_MOVE_MM = 0.4
# Cross edges are kept only where the two surfaces face the SAME way.
#
# THIS IS THE WHOLE DIFFERENCE BETWEEN A STITCH AND A SMEAR. The focused
# exposure's bone wraps AROUND the centred volume's, so over a large area B's
# inner wall runs alongside A's outer surface a fraction of a millimetre away --
# with a 2 mm band and no normal test that caught 6,701 of A's 11,921 vertices
# and 8,151 of B's, and smoothing "the seam" moved 14,847 vertices. That is not
# a seam band, it is most of the mandible.
#
# Those broad near-contact regions are the two meshes' FACING WALLS, whose
# normals are OPPOSED -- and they must not be welded: they are supposed to stay
# as two coincident walls, because that is exactly what makes the DRR's path
# length add up (a ray leaves A where it enters B). What should be welded is the
# RIM, the curve where A's outer surface and B's outer surface meet, and there
# the normals AGREE. So the dot product of the two vertex normals is the
# discriminator, and it is a geometric fact rather than a tuned threshold.
NORMAL_MIN = 0.3


def falloff(d, weld, band):
    """1 at the join, 0 beyond the band, smooth in between (smoothstep)."""
    t = np.clip((d - weld) / max(band - weld, 1e-9), 0.0, 1.0)
    return 1.0 - (t * t * (3.0 - 2.0 * t))


def vertex_normals(verts, faces):
    """Area-weighted vertex normals, oriented OUTWARD."""
    t = verts[faces]
    fn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n = np.zeros_like(verts)
    for k in range(3):
        np.add.at(n, faces[:, k], fn)
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1.0
    n /= ln[:, None]
    # A closed surface wound inward has negative signed volume; flip so "same
    # direction" below means "both point out of the bone".
    vol = float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)
    return -n if vol < 0 else n


def adjacency(n, faces, cross):
    e = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    if len(cross):
        e = np.vstack([e, cross])
    e = np.vstack([e, e[:, ::-1]])
    A = sparse.coo_matrix((np.ones(len(e), np.float32), (e[:, 0], e[:, 1])),
                          shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(axis=1)).ravel()
    deg[deg == 0] = 1.0
    return A, deg


def main():
    ap = argparse.ArgumentParser()
    for n in ("a", "b", "out_a", "out_b"):
        ap.add_argument(n)
    ap.add_argument("--band", type=float, default=BAND_MM)
    ap.add_argument("--weld", type=float, default=WELD_MM)
    ap.add_argument("--iters", type=int, default=ITERS)
    ap.add_argument("--max-move", type=float, default=MAX_MOVE_MM)
    ap.add_argument("--lam", type=float, default=0.5)
    ap.add_argument("--mu", type=float, default=-0.53)
    ap.add_argument("--normal-min", type=float, default=NORMAL_MIN)
    o = ap.parse_args()

    av, af = read_stl(o.a)
    bv, bf = read_stl(o.b)
    na = len(av)
    print(f"A {os.path.basename(o.a):18s} {na:6d} verts  {len(af):6d} faces")
    print(f"B {os.path.basename(o.b):18s} {len(bv):6d} verts  {len(bf):6d} faces")

    da, _ = surface_distance(av, bv, bf)
    db, _ = surface_distance(bv, av, af)
    wa, wb = falloff(da, o.weld, o.band), falloff(db, o.weld, o.band)
    print(f"  join band: {int((wa > 0).sum())} of A and {int((wb > 0).sum())} of B "
          f"within {o.band} mm; {int((da <= o.weld).sum())} + "
          f"{int((db <= o.weld).sum())} within the weld distance")

    # CROSS EDGES, mutual-nearest only. A one-way k-nearest link would tie a
    # dense patch of one mesh to a single vertex of the other and drag it.
    an, bn = vertex_normals(av, af), vertex_normals(bv, bf)
    ta, tb = cKDTree(av), cKDTree(bv)
    pairs = set()
    idx_a = np.where(da <= o.band)[0]
    cand = tb.query_ball_point(av[idx_a], r=o.weld * 2.0)
    rejected = 0
    for ia, js in zip(idx_a, cand):
        near_a = set(ta.query(bv[js], k=6)[1].ravel().tolist()) if js else set()
        for jb in js:
            if ia not in near_a:
                continue          # not mutually nearest: would drag a patch
            if float(an[ia] @ bn[jb]) < o.normal_min:
                rejected += 1     # facing walls, not the rim -- leave them
                continue
            pairs.add((int(ia), int(jb) + na))
    cross = np.array(sorted(pairs), dtype=np.int64) if pairs else np.zeros((0, 2), np.int64)
    print(f"  cross edges: {len(cross)} kept, {rejected} rejected as facing walls")

    # Only vertices that actually took part in the rim may move. Without this
    # the falloff weight alone still lets the whole broad near-contact region
    # smooth, which is the smear the normal test exists to prevent.
    on_rim = np.zeros(len(av) + len(bv), bool)
    if len(cross):
        on_rim[cross[:, 0]] = True
        on_rim[cross[:, 1]] = True
        rim_pts = np.vstack([av, bv])[on_rim]
        tr = cKDTree(rim_pts)
        dr = tr.query(np.vstack([av, bv]), workers=-1)[0]
        rim_w = falloff(dr, 0.0, o.band)
    else:
        rim_w = np.zeros(len(av) + len(bv))
    if not len(cross):
        print("  NOTHING TO STITCH -- the two meshes never come within the weld "
              "distance. Check the pad before smoothing.")

    # ---- SPLIT THE DIFFERENCE, before any smoothing --------------------
    #
    # MEASURED: the focused exposure's surface sits PROUD of the centred one at
    # the rim 90% of the time, by a median +0.187 mm and +0.524 at p95, with a
    # median 31.5 degree break between the two surface normals. That is a LEDGE,
    # not a gap and not only a normals discontinuity -- which is why closing the
    # gap (pad 2 -> 0) left the crease exactly where it was, and why a Taubin
    # band alone does not shift it either: smoothing averages a step, it does
    # not remove one.
    #
    # So the step is removed explicitly, and SYMMETRICALLY: each side moves HALF
    # the locally measured offset toward the other. Neither exposure is treated
    # as the truth, and no surface moves further than half the disagreement the
    # two measurements already have between them -- which at a rigid
    # registration sitting at Dice 0.708 is well inside their own uncertainty.
    # Moving one mesh the whole way onto the other would be picking a winner
    # between two measurements, and that is the thing the wishlist's provenance
    # caution forbids.
    step = np.zeros((len(av) + len(bv), 3))
    if len(cross):
        ia = cross[:, 0]
        ib = cross[:, 1] - na
        # offset of B from A's surface, along A's own outward normal
        off = np.einsum("ij,ij->i", bv[ib] - av[ia], an[ia])
        corr = 0.5 * off[:, None] * an[ia]
        # several B vertices can share one A vertex, so accumulate and average
        cnt = np.zeros(len(av) + len(bv))
        np.add.at(step, ia, +corr)
        np.add.at(cnt, ia, 1.0)
        np.add.at(step, cross[:, 1], -corr)
        np.add.at(cnt, cross[:, 1], 1.0)
        cnt[cnt == 0] = 1.0
        step /= cnt[:, None]
        print(f"  ledge at the rim: median {np.median(off):+.3f} mm, "
              f"p95 {np.percentile(off, 95):+.3f}, proud {100 * (off > 0).mean():.0f}% "
              f"of the time -- each side moves half of it")

    verts = np.vstack([av, bv])
    faces = np.vstack([af, bf + na])
    w = (np.concatenate([wa, wb]) * rim_w)[:, None]
    A, deg = adjacency(len(verts), faces, cross)
    inv = sparse.diags(1.0 / deg)

    orig = verts.copy()
    # Feather the correction out over the band so it does not end in a new step
    # of its own one ring away from the rim.
    v = verts.astype(np.float64) + step * rim_w[:, None]
    for _ in range(o.iters):
        for step in (o.lam, o.mu):
            # weighted: a vertex outside the band has w = 0 and cannot move
            v += (step * w) * (inv @ (A @ v) - v)

    # Clamp total displacement. This is the provenance guard, not a safety net.
    d = v - orig
    mag = np.linalg.norm(d, axis=1)
    over = mag > o.max_move
    if over.any():
        d[over] *= (o.max_move / mag[over])[:, None]
    v = orig + d
    mag = np.linalg.norm(v - orig, axis=1)
    moved = mag > 1e-6
    print(f"  moved {int(moved.sum())} vertices  median {np.median(mag[moved]):.3f} mm  "
          f"p95 {np.percentile(mag[moved], 95):.3f}  max {mag.max():.3f}  "
          f"(cap {o.max_move}, {int(over.sum())} clamped)")

    write_binary_stl(o.out_a, v[:na], af)
    write_binary_stl(o.out_b, v[na:], bf)
    print(f"-> {o.out_a}\n-> {o.out_b}")


if __name__ == "__main__":
    main()
