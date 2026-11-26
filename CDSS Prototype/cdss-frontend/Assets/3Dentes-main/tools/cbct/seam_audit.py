#!/usr/bin/env python3
"""Measure the join between the centred volume's bone and a focused exposure's.

Three exposures were acquired. The centred one supplies `mandible` and
`maxilla`; the two focused ones supply the bone the centred field of view cut
off, and `export_extra_bone.py` builds those. The two surfaces are meshed in
different grids, so they do not share vertices along the join -- and the
operator sees a seam there, on the model and worse on the radiograph.

WHY POINT-TO-SURFACE AND NOT POINT-TO-VERTEX. The first measurement of this
seam used vertex-to-nearest-VERTEX, which cannot be smaller than the true
surface separation and on a ~1 mm triangulation is systematically larger: two
surfaces can touch exactly while their nearest vertices are half an edge apart.
That inflates a gap and, worse, would hide an OVERLAP entirely. This computes
exact point-to-triangle distance, and reports the vertex-to-vertex figure beside
it so the two are comparable.

SIGN MATTERS AND DISTANCE HAS NONE. A gap and an overlap are the same unsigned
number, and they are opposite defects -- a gap prints dark on the film, an
overlap prints bright. So this also reports, for each near-join vertex, whether
it lies INSIDE the other mesh, by even-odd ray crossing. "Inside" is overlap.

Usage: seam_audit.py <centred.stl> <extra.stl> [--near MM] [--json OUT]
"""
import argparse
import json
import struct
import sys

import numpy as np
from scipy.spatial import cKDTree

# The join is where the two surfaces come near each other at all. Everything
# further than this is the rest of the anatomy and says nothing about the seam.
NEAR_MM = 2.0


def read_stl(path):
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[80:84])[0]
    rec = np.frombuffer(b[84:84 + n * 50], dtype=np.uint8).reshape(n, 50)
    tri = rec[:, 12:48].copy().view("<f4").reshape(n * 3, 3).astype(np.float64)
    v, idx, inv = np.unique(np.round(tri, 6), axis=0,
                            return_index=True, return_inverse=True)
    verts = tri[idx]
    faces = inv.reshape(-1, 3)
    keep = ((faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2])
            & (faces[:, 0] != faces[:, 2]))
    return verts, faces[keep]


def point_triangle_dist(p, a, b, c):
    """Exact distance from points p to triangles (a,b,c), elementwise.

    The standard region-by-region closest-point solve (Ericson, Real-Time
    Collision Detection). Vectorised over one point per triangle.
    """
    ab, ac, ap = b - a, c - a, p - a
    d1 = np.einsum("ij,ij->i", ab, ap)
    d2 = np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3 = np.einsum("ij,ij->i", ab, bp)
    d4 = np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5 = np.einsum("ij,ij->i", ab, cp)
    d6 = np.einsum("ij,ij->i", ac, cp)

    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    denom = va + vb + vc
    with np.errstate(divide="ignore", invalid="ignore"):
        v_f = np.where(denom != 0, vb / np.where(denom != 0, denom, 1), 0.0)
        w_f = np.where(denom != 0, vc / np.where(denom != 0, denom, 1), 0.0)
        closest = a + ab * v_f[:, None] + ac * w_f[:, None]

        # vertex and edge regions override the face solution
        m = (d1 <= 0) & (d2 <= 0)
        closest[m] = a[m]
        m = (d3 >= 0) & (d4 <= d3)
        closest[m] = b[m]
        m = (d6 >= 0) & (d5 <= d6)
        closest[m] = c[m]
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
        t = np.where(d1 - d3 != 0, d1 / np.where(d1 - d3 != 0, d1 - d3, 1), 0.0)
        closest[m] = (a + ab * t[:, None])[m]
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
        t = np.where(d2 - d6 != 0, d2 / np.where(d2 - d6 != 0, d2 - d6, 1), 0.0)
        closest[m] = (a + ac * t[:, None])[m]
        m = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)
        dd = (d4 - d3) + (d5 - d6)
        t = np.where(dd != 0, (d4 - d3) / np.where(dd != 0, dd, 1), 0.0)
        closest[m] = (b + (c - b) * t[:, None])[m]
    return np.linalg.norm(p - closest, axis=1)


def surface_distance(pts, verts, faces, k=48):
    """Distance from each point to the nearest point ON the surface.

    KDTree over triangle CENTROIDS to shortlist, then exact point-triangle on
    the shortlist. k=48 centroids is generous for a ~1 mm triangulation; the
    check below reports whether the shortlist radius ever bound the answer,
    because a shortlist that is too small fails silently by returning a
    plausible larger number.
    """
    cen = verts[faces].mean(axis=1)
    tree = cKDTree(cen)
    d_cen, idx = tree.query(pts, k=min(k, len(cen)), workers=-1)
    best = np.full(len(pts), np.inf)
    tri = verts[faces]
    for j in range(idx.shape[1]):
        t = tri[idx[:, j]]
        d = point_triangle_dist(pts, t[:, 0], t[:, 1], t[:, 2])
        best = np.minimum(best, d)
    # If the true nearest surface point were outside the shortlist, it would
    # have to be nearer than the shortlist's own farthest centroid; flag it.
    bound_hit = int(np.sum(best > d_cen[:, -1]))
    return best, bound_hit


def inside_mesh(pts, verts, faces, cell=2.0):
    """Even-odd crossing count along +x. True = the point is inside.

    Triangles are bucketed by their (y, z) bounding box into a fixed grid so a
    point only tests the triangles whose projection could contain it. Without
    that this is points x triangles and takes minutes on a 24k-triangle mesh.
    """
    tri = verts[faces]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ymin = np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1])
    ymax = np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1])
    zmin = np.minimum(np.minimum(a[:, 2], b[:, 2]), c[:, 2])
    zmax = np.maximum(np.maximum(a[:, 2], b[:, 2]), c[:, 2])

    y0, z0 = ymin.min(), zmin.min()
    buckets = {}
    for t in range(len(faces)):
        for iy in range(int((ymin[t] - y0) // cell), int((ymax[t] - y0) // cell) + 1):
            for iz in range(int((zmin[t] - z0) // cell), int((zmax[t] - z0) // cell) + 1):
                buckets.setdefault((iy, iz), []).append(t)
    buckets = {k: np.asarray(v) for k, v in buckets.items()}

    out = np.zeros(len(pts), dtype=bool)
    for i, p in enumerate(pts):
        cand = buckets.get((int((p[1] - y0) // cell), int((p[2] - z0) // cell)))
        if cand is None:
            continue
        m = ((ymin[cand] <= p[1]) & (ymax[cand] >= p[1])
             & (zmin[cand] <= p[2]) & (zmax[cand] >= p[2]))
        if not m.any():
            continue
        sel = cand[m]
        A, B, C = a[sel], b[sel], c[sel]
        # barycentric in the (y, z) projection
        v0, v1 = C - A, B - A
        v2y, v2z = p[1] - A[:, 1], p[2] - A[:, 2]
        d00 = v0[:, 1] * v0[:, 1] + v0[:, 2] * v0[:, 2]
        d01 = v0[:, 1] * v1[:, 1] + v0[:, 2] * v1[:, 2]
        d11 = v1[:, 1] * v1[:, 1] + v1[:, 2] * v1[:, 2]
        d20 = v2y * v0[:, 1] + v2z * v0[:, 2]
        d21 = v2y * v1[:, 1] + v2z * v1[:, 2]
        den = d00 * d11 - d01 * d01
        ok = np.abs(den) > 1e-12
        u = np.zeros(len(A)); w = np.zeros(len(A))
        u[ok] = (d11[ok] * d20[ok] - d01[ok] * d21[ok]) / den[ok]
        w[ok] = (d00[ok] * d21[ok] - d01[ok] * d20[ok]) / den[ok]
        hit = ok & (u >= 0) & (w >= 0) & (u + w <= 1)
        if not hit.any():
            continue
        x = A[hit, 0] + u[hit] * v0[hit, 0] + w[hit] * v1[hit, 0]
        out[i] = (np.sum(x > p[0]) % 2) == 1
    return out


def pct(d, qs=(0, 1, 5, 10, 25, 50)):
    return {f"p{q}": round(float(np.percentile(d, q)), 3) for q in qs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("centred")
    ap.add_argument("extra")
    ap.add_argument("--near", type=float, default=NEAR_MM)
    ap.add_argument("--json")
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    cv, cf = read_stl(a.centred)
    ev, ef = read_stl(a.extra)

    d_surf, bound = surface_distance(ev, cv, cf)
    d_vert = cKDTree(cv).query(ev, workers=-1)[0]

    near = d_surf <= a.near
    n = int(near.sum())
    rep = {
        "label": a.label,
        "centred": {"verts": len(cv), "faces": len(cf)},
        "extra": {"verts": len(ev), "faces": len(ef)},
        "near_mm": a.near,
        "near_vertices": n,
        "near_fraction": round(n / len(ev), 4),
        "shortlist_bound_hits": bound,
    }
    if n:
        dn = d_surf[near]
        rep["surface_mm"] = {"closest": round(float(dn.min()), 3), **pct(dn)}
        rep["vertex_mm"] = {"closest": round(float(d_vert[near].min()), 3),
                            **pct(d_vert[near])}
        for t in (0.05, 0.1, 0.2, 0.3, 0.5, 1.0):
            rep[f"within_{t}mm"] = round(float(np.mean(dn <= t)) * 100, 2)
        ins = inside_mesh(ev[near], cv, cf)
        rep["inside_centred_pct"] = round(float(ins.mean()) * 100, 2)
        rep["overlap_depth_mm"] = (round(float(dn[ins].max()), 3)
                                   if ins.any() else 0.0)

    print(json.dumps(rep, indent=2))
    if a.json:
        json.dump(rep, open(a.json, "w"), indent=2)


if __name__ == "__main__":
    main()
