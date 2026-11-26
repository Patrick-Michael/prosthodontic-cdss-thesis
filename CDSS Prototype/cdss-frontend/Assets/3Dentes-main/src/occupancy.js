// A coarse solid map of the anatomy, so the sensor cannot pass through it.
//
// A real intraoral sensor is a rigid 7.5 mm slab that has to fit in a mouth,
// and most of the difficulty of periapical radiography is that it often barely
// does. A simulator that lets the film sit inside the palate teaches the
// technique with its hardest constraint removed — so the film is collision
// tested against the anatomy and refused where it does not fit.
//
// WHY A GRID AND NOT RAYCASTS. Testing a few hundred points per exposure
// against ~300k triangles is far too slow to run while a slider moves. The
// anatomy never changes, so it is voxelised ONCE at load and every later test
// is an array lookup.
//
// The map is deliberately coarse (1.5 mm). It decides whether a slab of plastic
// fits in a mouth, not where a margin lies, and at that job a voxel is smaller
// than the error in calling the gingiva "derived" in the first place.

import * as THREE from 'three';

// HARD stops the sensor dead. SOFT yields — mucosa compresses under a film,
// which is why a sensor can rest against the palate but not inside it. Treating
// the two alike made every placement in the mouth impossible, because a real
// sensor is ALWAYS touching soft tissue somewhere.
//
// `ramus` AND `midface` WERE MISSING UNTIL 2026-09-06, and the sensor passed
// straight through them. Those two layers arrived with the focused exposures
// (d9d003e) and this set was written afterwards, in 0.8.0, without them -- so
// every posterior placement was free to bury the housing in the ramus and poke
// it out through the inferior border, which is exactly what the operator saw in
// the 3D view. They are bone; they stop a sensor. Anything added to `LAYERS` in
// manifest.mjs that is hard tissue has to be added here too, and nothing
// enforces that but this comment.
export const HARD = new Set(['teeth', 'prosthetic', 'mandible', 'maxilla',
                             'ramus', 'midface']);
export const SOFT = new Set(['gingiva']);
export const OBSTRUCTING = new Set([...HARD, ...SOFT]);

/**
 * Which arch a structure belongs to, or null if it belongs to neither.
 *
 * Teeth carry `arch` directly. Bone and gingiva do not, and the per-tooth
 * derived structures (enamel, pulp, pdl, lamina, prosthetic) are named
 * `<parent>-<kind>`, so their arch is their parent's.
 */
export function archOf(fma, structures) {
  const s = structures[fma];
  if (!s) return null;
  if (s.layer === 'mandible' || s.layer === 'ramus') return 'mandibular';
  if (s.layer === 'maxilla' || s.layer === 'midface') return 'maxillary';
  if (s.layer === 'gingiva') {
    return /lower/i.test(s.name || '') ? 'mandibular' : 'maxillary';
  }
  if (s.arch) return s.arch;
  const parent = structures[fma.split('-')[0]];
  return parent?.arch ?? null;
}

/**
 * How far the arches are held apart while a periapical is taken.
 *
 * THE MODEL IS ONE FROZEN FRAME WITH THE TEETH TOGETHER, and a periapical is
 * not taken that way. Every hard mesh goes into this grid including the
 * OPPOSING arch, so collision has been answering "does this sensor fit with the
 * mouth closed" -- and it has been leaking into the design already:
 * drr-plan.md records that the default apical `vshift` exists partly because
 * centring "catches the opposing arch". A constant was absorbing a posture.
 *
 * IT IS A PURE TRANSLATION AND THAT IS NOT HOW A MANDIBLE OPENS. Real opening
 * is rotation in the lower joint compartment and then translation down the
 * articular eminence, so a rigid drop is wrong at the condyle and roughly right
 * at the teeth -- which is the only place this grid is consulted. It is a
 * stand-in of the same kind as `mucosaMm`, and it should be replaced rather
 * than tuned when the TMJ exposures land and there is a measured condylar path.
 * CHOSEN AT SATURATION, not from a clinical opening. Sweeping it through the
 * audit (drr.html?audit=1&open=<mm>), the total adjustment the placement search
 * needs falls 165 -> 108 -> 80.5 mm at 0, 5 and 10 mm, and 20 mm is IDENTICAL
 * to 10 -- past 10 the opposing arch is simply out of the way and nothing more
 * happens. A real periapical is taken with the mouth wider than this, but the
 * grid cannot tell, and a rigid translation is least wrong where it is
 * smallest. So: the saturation point plus a little margin.
 *
 * The clearest single symptom it removes: FIVE teeth were pinned at the 7 mm
 * limit of the slide search, which means those placements were not found, they
 * were given up on at the edge of the search. One is left at 12 mm.
 *
 * See "Open and close the mouth" in docs/wishlist.md.
 */
export const INTEROCCLUSAL_MM = 12.0;

/**
 * Soft tissue the atlas does not have, as a thickness.
 *
 * A sensor rests on mucosa over bone; without mucosa it has to float clear of
 * the bone entirely, and a rigid 43 mm slab in a curved arch mostly cannot.
 * Measured: with no allowance, 5 of 28 teeth place; at 2.5 mm, 26 of 28 place
 * at paralleling with none failing. The cliff between 2.0 and 2.5 mm is sharp,
 * which is roughly the compressible depth the housing needs to find.
 *
 * IT STANDS IN FOR ANATOMY, NOT FOR TOLERANCE. Delete it when the tissue is
 * modelled; do not tune it when a placement looks wrong.
 */
export const SOFT_TISSUE_STANDIN_MM = 2.5;

export function buildOccupancy(meshes, structures,
                               { voxel = 0.9, pad = 4, mucosaMm = null,
                                 onlyArch = null } = {}) {
  const box = new THREE.Box3();
  const used = [];
  for (const [fma, mesh] of meshes) {
    const layer = structures[fma]?.layer;
    if (!OBSTRUCTING.has(layer)) continue;
    // ONE GRID PER ARCH, holding only that arch's structures. Testing the
    // sensor against the other arch with the sample points SHIFTED is the same
    // thing as moving that arch, and it makes the interocclusal opening a free
    // parameter of the search rather than something baked into the voxels. The
    // opening has to be searched, because the right one is the smallest that
    // works for THIS tooth, not one constant for the mouth.
    if (onlyArch && archOf(fma, structures) !== onlyArch) continue;
    mesh.updateWorldMatrix(true, false);
    box.expandByObject(mesh);
    used.push({ mesh, hard: HARD.has(layer) });
  }
  if (!used.length) return null;
  box.expandByScalar(pad);

  const size = box.getSize(new THREE.Vector3());
  const nx = Math.ceil(size.x / voxel), ny = Math.ceil(size.y / voxel),
        nz = Math.ceil(size.z / voxel);
  // 1 = hard, 2 = soft. Hard wins where they overlap: the gingival collar sits
  // on bone, and bone is what actually stops the film.
  const grid = new Uint8Array(nx * ny * nz);
  const at = (i, j, k) => (k * ny + j) * nx + i;
  const min = box.min;

  const mark = (x, y, z, val) => {
    const i = Math.floor((x - min.x) / voxel);
    const j = Math.floor((y - min.y) / voxel);
    const k = Math.floor((z - min.z) / voxel);
    if (i < 0 || j < 0 || k < 0 || i >= nx || j >= ny || k >= nz) return;
    const p = at(i, j, k);
    if (val === 1 || grid[p] === 0) grid[p] = val;
  };

  // Surface shell. Triangles are marked at their vertices, edge midpoints and
  // centroid: the tooth meshes are far finer than a voxel, but the jaw meshes
  // are not, and vertices alone would leave gaps a sensor could slide through.
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (const { mesh, hard } of used) {
    const val = hard ? 1 : 2;
    const pos = mesh.geometry.getAttribute('position');
    const idx = mesh.geometry.getIndex();
    const n = idx ? idx.count : pos.count;
    for (let t = 0; t < n; t += 3) {
      const i0 = idx ? idx.getX(t) : t;
      const i1 = idx ? idx.getX(t + 1) : t + 1;
      const i2 = idx ? idx.getX(t + 2) : t + 2;
      a.fromBufferAttribute(pos, i0).applyMatrix4(mesh.matrixWorld);
      b.fromBufferAttribute(pos, i1).applyMatrix4(mesh.matrixWorld);
      c.fromBufferAttribute(pos, i2).applyMatrix4(mesh.matrixWorld);
      mark(a.x, a.y, a.z, val); mark(b.x, b.y, b.z, val); mark(c.x, c.y, c.z, val);
      mark((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2, val);
      mark((b.x + c.x) / 2, (b.y + c.y) / 2, (b.z + c.z) / 2, val);
      mark((c.x + a.x) / 2, (c.y + a.y) / 2, (c.z + a.z) / 2, val);
      mark((a.x + b.x + c.x) / 3, (a.y + b.y + c.y) / 3, (a.z + b.z + c.z) / 3, val);
    }
  }

  // Fill the interiors: flood the OUTSIDE from the padded boundary, and
  // whatever the flood never reaches is inside something. Without this a sensor
  // could sit happily in the middle of the mandible, touching no surface.
  const seen = new Uint8Array(grid.length);
  const stack = [];
  for (let k = 0; k < nz; k++) {
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        if (i && j && k && i < nx - 1 && j < ny - 1 && k < nz - 1) continue;
        const p = at(i, j, k);
        if (!grid[p] && !seen[p]) { seen[p] = 1; stack.push(i, j, k); }
      }
    }
  }
  while (stack.length) {
    const k = stack.pop(), j = stack.pop(), i = stack.pop();
    for (const [di, dj, dk] of [[1, 0, 0], [-1, 0, 0], [0, 1, 0],
                                [0, -1, 0], [0, 0, 1], [0, 0, -1]]) {
      const x = i + di, y = j + dj, z = k + dk;
      if (x < 0 || y < 0 || z < 0 || x >= nx || y >= ny || z >= nz) continue;
      const p = at(x, y, z);
      if (grid[p] || seen[p]) continue;
      seen[p] = 1;
      stack.push(x, y, z);
    }
  }
  // Anything the outside flood never reached is inside something. Filled as
  // HARD: the inside of a tooth or a jaw is not somewhere a sensor may go.
  let interior = 0;
  for (let p = 0; p < grid.length; p++) {
    if (!grid[p] && !seen[p]) { grid[p] = 1; interior++; }
  }

  // THE MUCOSA THIS MODEL DOES NOT HAVE.
  //
  // A sensor is never placed against bare bone. It rests on mucosa — palatal,
  // sublingual, alveolar — which is compressible and a couple of millimetres
  // thick. This atlas has no such tissue: gingiva is a thin collar around the
  // teeth and nothing lines the palate or the floor of the mouth, so every hard
  // surface here sits a few millimetres closer to the sensor than it does in a
  // patient. Tested literally, almost nothing could be placed anywhere, which
  // is a statement about the missing tissue and not about the technique.
  //
  // So the hard region is ERODED by that thickness before it is used for
  // collision. This is an explicit stand-in for a structure the model lacks,
  // not a fudge factor to make placements succeed: it should be deleted the day
  // the intraoral scan lands and real mucosa exists.
  // ONE VOXEL OF THIS IS A VOXELISATION CORRECTION; THE REST IS A STAND-IN.
  //
  // This erosion was called `mucosaMm` and documented as a stand-in for
  // compressible soft tissue the atlas does not have. It never was one:
  // `round(0.9 / 0.9)` is exactly ONE CELL, and the marking pass above dilates
  // the anatomy by up to one cell because it marks every voxel a triangle
  // touches. The erosion undoes the dilation. It is a voxelisation correction
  // and nothing else, which is why it is no longer named after tissue.
  //
  // WHY THERE IS MORE THAN ONE CELL, STATED PLAINLY. With bone absolute and no
  // allowance -- which is what the operator asked for, and is correct -- only
  // 5 of 28 teeth could be placed at all. These films are taken every day, so
  // what is missing is not tolerance but ANATOMY: the sublingual and palatal
  // soft tissue the sensor actually rests on. The atlas has none.
  //
  // So this is a stand-in for tissue that does not exist yet, and it is named
  // as one. It is not a clinical tolerance, it is not a fudge factor to tune
  // when a placement looks wrong, and it should be DELETED rather than adjusted
  // when the intraoral scan lands. See "Model the sublingual and palatal soft
  // tissue" in docs/wishlist.md -- that item exists because of this number.
  const erodeCells = mucosaMm == null
    ? Math.max(1, Math.round(SOFT_TISSUE_STANDIN_MM / voxel))
    : Math.max(0, Math.round(mucosaMm / voxel));
  const hardTest = new Uint8Array(grid.length);
  for (let p = 0; p < grid.length; p++) hardTest[p] = grid[p] === 1 ? 1 : 0;
  if (erodeCells > 0) {
    // Separable erosion, one axis at a time: a cell survives only if every cell
    // within the radius along that axis is hard.
    const tmp = new Uint8Array(grid.length);
    const passes = [
      (i, j, k, d) => at(i + d, j, k),
      (i, j, k, d) => at(i, j + d, k),
      (i, j, k, d) => at(i, j, k + d),
    ];
    const limits = [nx, ny, nz];
    for (let axis = 0; axis < 3; axis++) {
      tmp.set(hardTest);
      for (let k = 0; k < nz; k++) {
        for (let j = 0; j < ny; j++) {
          for (let i = 0; i < nx; i++) {
            const p = at(i, j, k);
            if (!tmp[p]) { hardTest[p] = 0; continue; }
            const coord = [i, j, k][axis];
            let keep = 1;
            for (let d = -erodeCells; d <= erodeCells && keep; d++) {
              const c = coord + d;
              if (c < 0 || c >= limits[axis]) { keep = 0; break; }
              if (!tmp[passes[axis](i, j, k, d)]) keep = 0;
            }
            hardTest[p] = keep;
          }
        }
      }
    }
  }

  return {
    grid, hardTest, erodeCells, nx, ny, nz, voxel, min: min.clone(),
    stats: { meshes: used.length, cells: grid.length, interiorFilled: interior,
             onlyArch },
    occupied(x, y, z) {
      const i = Math.floor((x - this.min.x) / this.voxel);
      const j = Math.floor((y - this.min.y) / this.voxel);
      const k = Math.floor((z - this.min.z) / this.voxel);
      if (i < 0 || j < 0 || k < 0 || i >= this.nx || j >= this.ny || k >= this.nz) {
        return false;                     // outside the head is free space
      }
      const p = (k * this.ny + j) * this.nx + i;
      // Hard is read from the ERODED map (the mucosa stand-in above); soft is
      // read as marked, because the gingiva that IS modelled is real.
      if (this.hardTest[p]) return 1;
      return this.grid[p] === 2 ? 2 : 0;
    },
  };
}

/**
 * Corner radius of the housing, in millimetres.
 *
 * DERIVED, not measured here: published size-2 sensors run about 3-4 mm at the
 * corner, and nothing in this project has measured the operator's own housing.
 * It is a shape parameter of a manufactured object rather than of the patient,
 * so it carries no anatomical provenance tier -- but it is not measured either,
 * and a note is cheaper than a wrong assumption later.
 */
export const CORNER_MM = 3.5;

/**
 * Does the sensor SOLID fit here? Tests the whole slab, not two faces.
 *
 * WHAT THIS REPLACED, AND WHY IT WAS WRONG. The first version sampled a 13 x 9
 * lattice over the housing's two flat faces -- 234 points, one every ~3.6 mm --
 * and allowed 2.5% of them to sit in bone. Three things followed, and the
 * operator saw all three before the numbers did:
 *
 *   * THE INTERIOR AND RIM WERE NEVER TESTED. A lingual cortical plate one or
 *     two millimetres thick passes clean through the middle of a 7.5 mm housing
 *     without touching either face. That is not a near miss; it is the sensor
 *     inside the mandible with a clean bill of health.
 *   * THE LATTICE WAS COARSER THAN THE ANATOMY. At 3.6 mm spacing an entire
 *     alveolar crest can sit between samples.
 *   * THE ALLOWANCE WAS AREA, NOT TOLERANCE. Five permitted samples stood for
 *     about 70 mm2 of housing face legitimately buried in bone.
 *
 * So it now samples the VOLUME at the grid's own resolution and permits no hard
 * contact at all. The rounded corners are honoured in-plane, because that part
 * was right.
 *
 * NO HARD ALLOWANCE. The old 2.5% existed because the grid marks every voxel a
 * triangle touches, dilating the anatomy by up to a voxel -- but `hardTest` is
 * already eroded by `mucosaMm` for exactly that reason, so the compensation was
 * being applied twice. Contact means contact.
 *
 * EARLY EXIT ON THE FIRST HARD SAMPLE, which is what makes a volume test
 * affordable: the placement search spends nearly all of its time on placements
 * that fail, and those now fail on their first buried sample rather than after
 * counting all of them.
 */
export function sensorFits(occ, { centre, horiz, vert, normal, bw, bh, thickness },
                           { softAllowance = 0.35, cornerMm = CORNER_MM,
                             stepMm = 0.8, offsetY = 0,
                             skipCoarse = false } = {}) {
  if (!occ) return { fits: true, hard: 0, soft: 0, of: 0 };
  // TWO PASSES, COARSE THEN FINE. A volume test is ~60x the work of the old
  // surface probe, and the placement search spends nearly all its time on
  // placements that fail -- so failing cheaply is what makes this affordable.
  // The coarse pass is the same lattice at 3x the spacing, about 1/27 the
  // samples; anything deeply buried dies there. Only a placement that survives
  // it pays for the fine pass, and only the fine pass can accept.
  if (!skipCoarse) {
    const c = sensorFits(occ, { centre, horiz, vert, normal, bw, bh, thickness },
      { softAllowance: 1.1, cornerMm, stepMm: stepMm * 3, offsetY,
        skipCoarse: true });
    if (!c.fits && c.hard) return c;
  }
  const nu = Math.max(2, Math.ceil(bw / stepMm) + 1);
  const nv = Math.max(2, Math.ceil(bh / stepMm) + 1);
  const nw = Math.max(2, Math.ceil(thickness / stepMm) + 1);
  const ru = Math.max(bw / 2 - cornerMm, 0), rv = Math.max(bh / 2 - cornerMm, 0);
  let hard = 0, soft = 0, total = 0;
  const p = new THREE.Vector3();
  for (let iu = 0; iu < nu; iu++) {
    const su = (iu / (nu - 1) - 0.5) * bw;
    for (let iv = 0; iv < nv; iv++) {
      const sv = (iv / (nv - 1) - 0.5) * bh;
      const du = Math.max(Math.abs(su) - ru, 0), dv = Math.max(Math.abs(sv) - rv, 0);
      if (du * du + dv * dv > cornerMm * cornerMm) continue;
      for (let iw = 0; iw < nw; iw++) {
        const sw = (iw / (nw - 1) - 0.5) * thickness;
        p.copy(centre)
          .addScaledVector(horiz, su)
          .addScaledVector(vert, sv)
          .addScaledVector(normal, sw);
        total++;
        // `offsetY` shifts the SAMPLES instead of the anatomy, which is how the
        // interocclusal opening is applied to the opposing arch's own grid.
        const v = occ.occupied(p.x, p.y + offsetY, p.z);
        if (v === 1) return { fits: false, hard: 1, soft, of: total };
        if (v === 2) soft++;
      }
    }
  }
  return { fits: soft <= softAllowance * total, hard: 0, soft, of: total };
}
