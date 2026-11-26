#!/usr/bin/env python3
"""Offline DRR through the CBCT volume — the REFERENCE image for the DRR work.

    ~/projects/3Dentes-cbct/nnunet-venv/bin/python tools/cbct/drr_volume.py \
        --teeth 31 30 29 --out /tmp/drr.png

This is Phase 0 of docs/drr-plan.md and it is deliberately the one part of the
work that integrates the VOLUME rather than the shipped meshes. The volume is
not calibrated HU and saturates at 3072 (CLAUDE.md 126), so this image is a
reference to check geometry against — never a shipped claim about density.

Geometry is a real cone beam: a source point, a receptor rectangle, and rays
from the one to the other. Nothing here is a parallel projection, because
foreshortening is the thing the eventual simulator has to teach.

The receptor frame is derived from the anatomy rather than from world axes:
the horizontal runs along the arch through the named teeth, the vertical is the
target tooth's own long axis by PCA, and buccal is whichever way points away
from the arch centre. Assuming +z is "up the tooth" would be wrong for a
posterior tooth, which is tilted lingually.
"""
import argparse
import json
import os
import struct
import sys

import numpy as np
from scipy.ndimage import map_coordinates

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vol import Volume  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STL_DIR = os.path.join(ROOT, "assets", "cbct", "stl")
TEETH_JSON = os.path.join(ROOT, "public", "teeth.json")
VOLUME = os.path.expanduser("~/projects/3Dentes-cbct/nrrd/centered.nrrd")

# Source-to-receptor distance. A real periapical uses a 200 mm (8") or 400 mm
# (16") cone; 300 mm sits between them and is the usual paralleling setup.
SRD_MM = 300.0
# How far lingual to the target tooth the receptor sits. A paralleling holder
# keeps the film off the tooth, in the palate or the floor of the mouth.
RECEPTOR_OFFSET_MM = 9.0
# Size 2 sensor, landscape, as the operator's own PA is.
RECEPTOR_W_MM, RECEPTOR_H_MM = 40.0, 28.5


def load_stl(path):
    with open(path, "rb") as f:
        b = f.read()
    n = struct.unpack("<I", b[80:84])[0]
    a = np.frombuffer(b[84:84 + n * 50], dtype=np.uint8).reshape(n, 50)
    return a[:, 12:48].copy().view("<f4").reshape(-1, 3).astype(np.float64)


def tooth_index():
    """Universal number -> FMA id, read from the manifest's own output."""
    d = json.load(open(TEETH_JSON))
    out = {}
    for fma, v in d["structures"].items():
        if v.get("layer") == "teeth" and "-" not in fma and v.get("universal"):
            out[int(v["universal"])] = fma
    return out


def frame(target_v, arch_v, mesial_v, distal_v):
    """Receptor axes from anatomy. Returns (u, v, buccal), all unit vectors."""
    # Vertical: the target tooth's own long axis, by PCA of its vertices.
    c = target_v.mean(0)
    _, _, vt = np.linalg.svd(target_v - c, full_matrices=False)
    long_axis = vt[0] / np.linalg.norm(vt[0])
    # ANATOMICAL ORIENTATION: patient-superior is UP on the film, both arches.
    # That is the mounting convention -- a mandibular film shows crowns at the
    # top and a maxillary one shows them at the bottom, because that is where
    # those crowns actually are. NOT crown-ward: that prints upper films upside
    # down. (+z is superior in LPS.)
    if long_axis[2] < 0:
        long_axis = -long_axis
    # Horizontal: along the arch, from the distal neighbour to the mesial one.
    along = mesial_v.mean(0) - distal_v.mean(0)
    along -= long_axis * along.dot(long_axis)   # orthogonalise against the long axis
    u = along / np.linalg.norm(along)
    v = long_axis - u * long_axis.dot(u)
    v /= np.linalg.norm(v)
    # Buccal: perpendicular to both, signed to point AWAY from the arch centre.
    buccal = np.cross(u, v)
    buccal /= np.linalg.norm(buccal)
    if buccal.dot(c - arch_v.mean(0)) < 0:
        buccal = -buccal
    return u, v, buccal


def cast(volume, source, corner, du, dv, w_px, h_px, steps, air):
    """Cone-beam ray integral. Returns (h_px, w_px) of accumulated attenuation.

    Integration STOPS AT THE RECEPTOR. An intraoral sensor is an opaque plate in
    the mouth: it records what reaches it and nothing beyond contributes. March
    the full slab instead and every ray picks up the far side of the mandible on
    its way out, which washes the image out and is not what the receptor sees.
    """
    j, i = np.meshgrid(np.arange(w_px), np.arange(h_px))
    # Pixel centres on the receptor plane, in world millimetres.
    p = (corner[None, None, :]
         + du[None, None, :] * (j[..., None] + 0.5)
         + dv[None, None, :] * (i[..., None] + 0.5))
    d = p - source[None, None, :]
    dist = np.linalg.norm(d, axis=-1, keepdims=True)
    d /= dist
    dirs = d.reshape(-1, 3)
    limit = dist.reshape(-1)                       # per-ray distance to the sensor

    # March only the slab that can contain the volume, so the ~250 mm of air
    # between the source and the face costs nothing.
    lo = volume.origin
    hi = volume.origin + np.array(volume.data.shape[::-1]) * volume.spacing
    centre = (lo + hi) / 2.0
    half = float(np.linalg.norm(hi - lo) / 2.0)
    mean_dir = dirs.mean(0)
    mean_dir /= np.linalg.norm(mean_dir)
    t_mid = float((centre - source).dot(mean_dir))
    t0 = max(t_mid - half, 0.0)
    t1 = min(t_mid + half, float(limit.max()))
    t = np.linspace(t0, t1, steps)
    step_mm = float(t[1] - t[0])

    total = np.zeros(dirs.shape[0], dtype=np.float64)
    inv = 1.0 / volume.spacing
    for tv in t:
        s = source[None, :] + dirs * tv
        idx = (s - volume.origin[None, :]) * inv[None, :]      # -> (x, y, z) index
        coords = np.stack([idx[:, 2], idx[:, 1], idx[:, 0]])   # map wants (z, y, x)
        val = map_coordinates(volume.data, coords, order=1, mode="constant",
                              cval=air, output=np.float32)
        total += np.where(tv < limit, np.maximum(val - air, 0.0), 0.0)
    return (total * step_mm).reshape(h_px, w_px)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teeth", nargs=3, type=int, default=[31, 30, 29],
                    help="distal, target, mesial (Universal numbers)")
    ap.add_argument("--out", default="/tmp/drr.png")
    ap.add_argument("--px", type=int, default=900)
    ap.add_argument("--steps", type=int, default=700)
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--window", nargs=2, type=float, default=[2.0, 99.5],
                    help="display percentiles (low, high)")
    ap.add_argument("--flip", action="store_true", help="mirror horizontally")
    ap.add_argument("--vshift", type=float, default=-4.0,
                    help="mm to slide the receptor along the tooth axis; "
                         "negative is apical. A PA is framed with the crown at "
                         "the edge and 2-3 mm beyond the apex, not centred on "
                         "the tooth's centre of mass.")
    args = ap.parse_args()

    idx = tooth_index()
    distal_u, target_u, mesial_u = args.teeth
    for u in args.teeth:
        if u not in idx:
            sys.exit(f"tooth {u} not in the manifest")
    verts = {u: load_stl(os.path.join(STL_DIR, f"{idx[u]}.stl")) for u in args.teeth}
    arch = np.concatenate([load_stl(os.path.join(STL_DIR, f"{f}.stl"))
                           for f in idx.values()])

    v = Volume.load(VOLUME)
    # Air level: the mode of the low tail, not a nominal -1000. This volume is
    # not calibrated and its background does not sit where HU says it should.
    lo_vals = v.data[v.data < 0]
    hist, edges = np.histogram(lo_vals, bins=200)
    air = float((edges[hist.argmax()] + edges[hist.argmax() + 1]) / 2.0)

    u_ax, v_ax, buccal = frame(verts[target_u], arch, verts[mesial_u], verts[distal_u])
    target = verts[target_u].mean(0)
    # Apical framing, in whichever direction the apex actually lies: the
    # receptor's vertical points superior, which is apex-ward in the maxilla
    # and crown-ward in the mandible. Universal 1-16 is the upper arch.
    apical = -1.0 if target_u <= 16 else 1.0
    receptor_c = (target - buccal * RECEPTOR_OFFSET_MM
                  + v_ax * (args.vshift * apical))
    source = receptor_c + buccal * SRD_MM

    h_px = int(round(args.px * RECEPTOR_H_MM / RECEPTOR_W_MM))
    du = u_ax * (RECEPTOR_W_MM / args.px)
    dv = -v_ax * (RECEPTOR_H_MM / h_px)          # row 0 is the top = crown-ward
    corner = (receptor_c - u_ax * RECEPTOR_W_MM / 2.0 + v_ax * RECEPTOR_H_MM / 2.0)

    print(f"air level        {air:.0f}")
    print(f"target {target_u} centroid  {np.round(target, 2)}")
    print(f"receptor centre  {np.round(receptor_c, 2)}")
    print(f"source           {np.round(source, 2)}  (SRD {SRD_MM:.0f} mm)")
    print(f"receptor         {RECEPTOR_W_MM} x {RECEPTOR_H_MM} mm at {args.px}x{h_px} px")
    print(f"marching         {args.steps} steps")

    acc = cast(v, source, corner, du, dv, args.px, h_px, args.steps, air)

    # A sensor records transmitted intensity and its software takes the log,
    # which lands back on the path integral -- so windowing `acc` directly IS
    # the display model, and dense reads bright the way film does. The window is
    # a percentile stretch: the scale is arbitrary because the volume is not
    # calibrated, so this is a windowing CHOICE and not a measurement. Phase 3
    # replaces it with a response curve fitted to the operator's own PA.
    lo_p, hi_p = np.percentile(acc, [args.window[0], args.window[1]])
    img = np.clip((acc - lo_p) / max(hi_p - lo_p, 1e-9), 0.0, 1.0)
    img = np.power(img, args.gamma)
    if args.flip:
        img = img[:, ::-1]

    from PIL import Image
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(args.out)
    print(f"wrote            {args.out}")


if __name__ == "__main__":
    main()
