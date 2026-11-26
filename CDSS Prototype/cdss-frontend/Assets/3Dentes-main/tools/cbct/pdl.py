#!/usr/bin/env python3
"""Build the periodontal ligament space, bounded by two measured surfaces.

The ligament itself is 0.15-0.25 mm and cannot be resolved at 0.16 mm voxels with
a worse effective resolution. But the SPACE it occupies is bounded by two
surfaces that are both measurable -- the root surface and the lamina dura -- so
this is not an offset shell of guessed thickness. Both walls are found in the
data, per tooth, per aspect, per level.

That the PDL is visible at all is already established: the 691-1514 HU dark ring
around the roots is what made per-tooth isolation possible in the first place
(docs/cbct-whole-mouth.md). This measures the gap that ring occupies.

Honest limit on the WIDTH. Measuring a 0.2 mm gap through a point-spread function
several voxels wide inflates it: the apparent width is dominated by blur, not by
anatomy. So the width reported here is an upper bound and should not be read as a
PDL width, let alone compared against a threshold for widening. What is
trustworthy is the space's LOCATION and CONTINUITY -- where the ligament runs,
and whether bone is present along the root at all.

The apical extent is the tooth's apex; the coronal extent is the alveolar crest
measured by crest.py, because above the crest there is no PDL -- that is the
attached gingiva's territory, and the collar in gingiva.py already covers it.

Usage: python3 tools/cbct/pdl.py <volume.nrrd> <split-dir> <landmarks.json>
                                 <crest.json> <out-dir>
"""
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import marching_cubes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vol import Volume
from segment_tooth import write_binary_stl

BONE_HU = 600.0
MAX_GAP_MM = 2.0          # beyond this there is no lamina dura to bound against
N_ANGLES = 24
STEP_MM = 0.3
RENDER_THICKNESS_MM = 0.32   # EXAGGERATED so the shell is renderable at all
LAMINA_THICKNESS_MM = 0.32   # the socket wall drawn outside the ligament


def pdl_for_tooth(vol, tooth, others, frame, crest_by_angle, spacing):
    """Fill the space between the root surface and the lamina dura."""
    c = np.array(frame["centre_index"], float)
    ax = np.array(frame["axis"], float)
    e2 = np.array(frame["e2"], float)
    e3 = np.array(frame["e3"], float)
    pts = np.argwhere(tooth).astype(float) - c
    t_all = pts @ ax
    u, w = pts @ e2, pts @ e3
    r_all = np.hypot(u, w)
    ang_all = np.degrees(np.arctan2(w, u))
    t_apex = float(t_all.min())

    dense = (vol > BONE_HU) & ~others & ~tooth
    out = np.zeros(tooth.shape, bool)
    step = 360.0 / N_ANGLES
    widths = []
    for k in range(N_ANGLES):
        crest = crest_by_angle.get(k)
        if crest is None:
            continue
        top = crest / spacing
        a0 = -180 + k * step
        sel = (ang_all >= a0 - step) & (ang_all < a0 + 2 * step)
        if sel.sum() < 20:
            continue
        for t in np.arange(t_apex, top, STEP_MM / spacing):
            near = sel & (np.abs(t_all - t) < 2.0)
            if near.sum() < 8:
                continue
            r_surf = float(np.percentile(r_all[near], 92))
            # walk outward for the lamina dura
            hit = None
            for off in np.arange(0.0, MAX_GAP_MM / spacing, 0.5):
                found = False
                for da in (-step / 3, 0.0, step / 3):
                    a = np.radians(a0 + step / 2 + da)
                    d2 = np.cos(a) * e2 + np.sin(a) * e3
                    p = c + t * ax + (r_surf + off) * d2
                    iz, iy, ix = (int(round(p[0])), int(round(p[1])),
                                  int(round(p[2])))
                    if (0 <= iz < vol.shape[0] and 0 <= iy < vol.shape[1]
                            and 0 <= ix < vol.shape[2] and dense[iz, iy, ix]):
                        found = True
                        break
                if found:
                    hit = off
                    break
            if hit is None or hit < 0.5:
                continue
            widths.append(hit * spacing)
            for rr in np.arange(r_surf - 0.4, r_surf + hit, 0.5):
                for da in (-step / 3, 0.0, step / 3):
                    a = np.radians(a0 + step / 2 + da)
                    d2 = np.cos(a) * e2 + np.sin(a) * e3
                    p = c + t * ax + rr * d2
                    iz, iy, ix = (int(round(p[0])), int(round(p[1])),
                                  int(round(p[2])))
                    if (0 <= iz < vol.shape[0] and 0 <= iy < vol.shape[1]
                            and 0 <= ix < vol.shape[2]):
                        out[iz, iy, ix] = True
    return out, widths


def main():
    vol_path, split_dir, lm_path, crest_path, outdir = sys.argv[1:6]
    os.makedirs(outdir, exist_ok=True)
    v = Volume.load(vol_path)
    lm = json.load(open(lm_path))
    crest = json.load(open(crest_path))
    sp = float(v.spacing[0])
    upper = np.load(os.path.join(split_dir, "upper_labels.npy"))
    lower = np.load(os.path.join(split_dir, "lower_labels.npy"))
    all_teeth = (upper > 0) | (lower > 0)

    report = dict(
        provenance="WIDTH MEASURED between two walls found in the data (root "
                   "surface and lamina dura). GEOMETRY EXAGGERATED: the mesh is "
                   "a 0.32 mm shell on the measured root surface, because a "
                   "0.2 mm ligament is ~1.3 voxels and will not mesh.",
        render_thickness_mm=RENDER_THICKNESS_MM,
        width_caveat="Apparent width is inflated by the point-spread function "
                     "and is an UPPER BOUND. Do not read it as a PDL width or "
                     "compare it against a threshold for widening.",
        teeth={})
    print(f"{'Univ':>4s} {'mm3':>7s} {'apparent width mm':>18s}  {'aspects':>7s}")
    all_w = []
    for arch, arr in (("upper", upper), ("lower", lower)):
        ids = list(range(1, int(arr.max()) + 1))
        cents = ndi.center_of_mass(arr > 0, arr, ids)
        boxes = ndi.find_objects(arr)
        acc = np.zeros(arr.shape, bool)
        for key, m in lm.items():
            if m["arch"] != arch:
                continue
            c = np.array(m["centre_index"], float)
            best = min(ids, key=lambda s: np.linalg.norm(np.array(cents[s - 1]) - c))
            box = boxes[best - 1]
            pad = 30
            sl = tuple(slice(max(0, b.start - pad), min(n, b.stop + pad))
                       for b, n in zip(box, arr.shape))
            tsub = np.zeros(tuple(x.stop - x.start for x in sl), bool)
            tsub[tuple(slice(b.start - x.start, b.stop - x.start)
                       for b, x in zip(box, sl))] = arr[box] == best
            fr = dict(m)
            fr["centre_index"] = [c[i] - sl[i].start for i in range(3)]
            cr = {int(k2): val for k2, val
                  in crest.get(key, {}).get("crest_mm", {}).items()}
            if not cr:
                continue
            others = all_teeth[sl] & ~tsub
            got, widths = pdl_for_tooth(v.data[sl].astype(np.float32), tsub,
                                        others, fr, cr, sp)
            # The measurement above is the point; the mesh cannot be. A 0.2 mm
            # ligament is ~1.3 voxels, so painting between the two measured walls
            # leaves a shell so sparse it meshes to nothing (0.3-6 mm3 per tooth
            # against a real ~40). As with the pulp lining, the geometry is
            # therefore an EXAGGERATED shell on the measured root surface,
            # restricted to below the measured crest. The width that was measured
            # stays in the JSON; the mesh is explicitly not it.
            # SEAL THE TOOTH BEFORE EXCLUDING IT.
            #
            # The split labels do NOT include the pulp chamber: the molars are
            # hollow by 3.4 to 27.7 mm3 (tooth 18 the worst, then 31). `~tsub`
            # is therefore TRUE INSIDE THE CHAMBER, so dilating the root and
            # subtracting the label painted a ligament down the inside of the
            # canal. The operator saw it in the 3D view within minutes on
            # 2026-09-05; no volume, continuity or closedness check here would
            # ever have reported it, because the mesh was valid in every way
            # except being in the wrong place.
            #
            # Filling alone is not enough: a chamber that drains through the
            # apical foramen is not an enclosed cavity, so fill_holes leaves it
            # open. Closing first seals a foramen under about 0.6 mm. The union
            # with the original mask guarantees this can only ADD to the tooth
            # -- closing nibbles thin cusps, and losing tooth here would grow
            # the ligament instead of shrinking it.
            solid_all = (tsub | ndi.binary_fill_holes(tsub)
                         | ndi.binary_fill_holes(
                             ndi.binary_closing(tsub, np.ones((3, 3, 3)), 2)))
            got &= ~solid_all
            med_crest = float(np.median(list(cr.values()))) / sp
            c_local = np.array(fr["centre_index"], float)
            ax_l = np.array(fr["axis"], float)
            zz, yy, xx = np.indices(tsub.shape)
            tcoord = ((np.stack([zz, yy, xx], -1) - c_local) @ ax_l)
            root = solid_all & (tcoord < med_crest)
            k = max(1, int(round(RENDER_THICKNESS_MM / sp)))
            shell = ndi.binary_dilation(root, np.ones((3, 3, 3)), k) & ~solid_all
            shell &= ndi.binary_dilation(root, np.ones((3, 3, 3)), k + 1)
            acc[sl] |= (shell | got)

            # PER-TOOTH MESH, PADDED AND THEREFORE CLOSED.
            #
            # The per-tooth ligaments used to be cut out of the whole-arch mesh
            # by assigning each FACE to its nearest pulp centroid, which leaves
            # every piece open along every cut -- 27 of 28 shipped with 6 to 139
            # boundary edges. That is invisible in the 3D view and fatal to a
            # DRR, which integrates path length as back-face depth minus
            # front-face depth and needs every ray entering a solid to leave it.
            # The operator's own PA shows the PDL space is one of the most
            # diagnostic features on a periapical, so this is not a structure
            # the radiograph can simply omit.
            #
            # Meshing each tooth's OWN mask closes it by construction. The pad
            # is rule 203: marching_cubes cannot close a surface at the array
            # boundary, so the mask must not touch it.
            # THE LAMINA DURA: the socket's own cortical wall, immediately
            # outside the ligament. Its POSITION is measured -- it is only
            # drawn where the volume actually holds dense bone, which is the
            # same wall pdl.py already walks outward to find -- while its
            # thickness is a drawing choice, exactly like the ligament's.
            #
            # It earns its own structure because of the radiograph. On the
            # operator's own PA the bright line around each root and the dark
            # line inside it are among the most diagnostic features on the
            # film, and the atlas had neither: bone was one homogeneous solid,
            # so a root sat in it with no socket at all.
            #
            # It OVERLAPS the mandible and maxilla meshes by construction. That
            # is not double counting so long as the DRR subtracts, the way
            # dentin is tooth minus enamel minus pulp -- the bone mesh is the
            # bulk, and this is the cortical part of it.
            kl = max(1, int(round(LAMINA_THICKNESS_MM / sp)))
            outer = ndi.binary_dilation(root, np.ones((3, 3, 3)), k + kl) & ~solid_all
            lamina = outer & ~shell & ~all_teeth[sl]
            # CONTINUOUS, on the operator's call 2026-09-05.
            #
            # This was intersected with (volume > BONE_HU), which made the
            # position measured and the mesh "extremely patchy" -- his words --
            # and he asked for it continuous like the ligament. The wall is now
            # drawn all the way round the root whether or not the scan resolves
            # cortex there, exactly as the ligament's thickness is drawn rather
            # than measured.
            #
            # THE MEASUREMENT IS NOT DISCARDED, IT MOVES TO THE REPORT. What
            # fraction of each wall actually sits in bone above BONE_HU is
            # recorded per tooth as lamina_in_bone_frac. A low figure there is a
            # real finding about that socket -- a fenestration or a dehiscence
            # -- and as a NUMBER it can be read, compared and trusted, where the
            # same fact rendered as a hole in a mesh just looks like a bug.
            in_bone = float((lamina & (v.data[sl] > BONE_HU)).sum())
            lamina_frac = in_bone / max(float(lamina.sum()), 1.0)
            if lamina.sum() > 200:
                lab_l, n_l = ndi.label(lamina, structure=np.ones((3, 3, 3)))
                if n_l:
                    # Drop specks only. The shell is continuous by
                    # construction now, so this no longer has to pick ONE
                    # component and throw the rest of the socket away -- which
                    # is most of why the old version looked so ragged.
                    szs = ndi.sum(lamina, lab_l, range(1, n_l + 1)) * (sp ** 3)
                    lamina = np.isin(lab_l, [i + 1 for i, z in enumerate(szs)
                                             if z >= 1.0])
                f_l = ndi.gaussian_filter(np.pad(lamina, 2).astype(np.float32), 0.9)
                if 0 < f_l.max() and f_l.min() < 0.5 < f_l.max():
                    vl, fl, _, _ = marching_cubes(f_l, level=0.5)
                    wl = np.empty_like(vl)
                    for a_i, s_i in enumerate((2, 1, 0)):
                        wl[:, a_i] = (v.origin[a_i]
                                      + (sl[s_i].start - 2 + vl[:, s_i]) * sp)
                    write_binary_stl(
                        os.path.join(outdir, f"{m['fma']}-lamina.stl"), wl, fl)

            per = (shell | got) & ~all_teeth[sl] & ~solid_all
            if per.sum() > 200:
                pad = 2
                f_t = ndi.gaussian_filter(np.pad(per, pad).astype(np.float32), 0.9)
                vt, ft, _, _ = marching_cubes(f_t, level=0.5)
                w_t = np.empty_like(vt)
                for a_i, s_i in enumerate((2, 1, 0)):          # (z,y,x) -> (x,y,z)
                    w_t[:, a_i] = (v.origin[a_i]
                                   + (sl[s_i].start - pad + vt[:, s_i]) * sp)
                write_binary_stl(os.path.join(outdir, f"{m['fma']}-pdl.stl"),
                                 w_t, ft)

            mm3 = float(got.sum()) * sp ** 3
            wmed = float(np.median(widths)) if widths else float("nan")
            all_w += widths
            report["teeth"][key] = dict(
                universal=m["universal"], fma=m["fma"], arch=arch,
                volume_mm3=round(mm3, 1),
                lamina_in_bone_frac=round(lamina_frac, 3),
                apparent_width_median_mm=round(wmed, 2) if widths else None,
                aspects=len(widths))
            print(f"{m['universal']:4d} {mm3:7.1f} {wmed:18.2f}  {len(widths):7d}")
        acc &= ~all_teeth
        if acc.sum() > 500 and acc.any() and not acc.all():
            f = ndi.gaussian_filter(acc.astype(np.float32), 0.9)
            verts, faces, _, _ = marching_cubes(f, level=0.5)
            world = np.empty_like(verts)
            world[:, 0] = v.origin[0] + verts[:, 2] * sp
            world[:, 1] = v.origin[1] + verts[:, 1] * sp
            world[:, 2] = v.origin[2] + verts[:, 0] * sp
            write_binary_stl(os.path.join(outdir, f"pdl-{arch}.stl"), world, faces)
            print(f"  {arch}: {acc.sum()*sp**3:.1f} mm3, {len(faces)} tris")
    report["apparent_width_median_mm"] = round(float(np.median(all_w)), 2)
    with open(os.path.join(outdir, "pdl.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"\napparent PDL width, all aspects: median "
          f"{np.median(all_w):.2f} mm (upper bound; true is 0.15-0.25 mm)")
    print(f"-> {outdir}")


if __name__ == "__main__":
    main()
