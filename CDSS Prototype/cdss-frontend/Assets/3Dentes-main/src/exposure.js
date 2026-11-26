// Where the sensor and the tube go, given a tooth.
//
// Shared by the standalone harness (drr.html) and by the atlas's radiograph
// mode. It exists so those two cannot compute the exposure differently: a
// simulator whose side panel and whose 3D overlay disagree about where the film
// is would be worse than having neither.
//
// This mirrors frame() in tools/cbct/drr_volume.py, which is the reference the
// whole DRR is checked against.

import * as THREE from 'three';
import { CORNER_MM } from './occupancy.js';

/**
 * A real size-2 intraoral sensor, to the millimetre.
 *
 * ACTIVE 36 x 25.6 mm, HOUSING 43 x 31.2 x 7.5 mm. The active area is the
 * image; the housing is what has to fit in the mouth, and they are not the same
 * rectangle — there is 3.5 mm of dead plastic along each long edge and 2.8 mm
 * along each short one. Positioning is constrained by the housing while the
 * radiograph only ever shows the active area, which is a large part of why
 * placement is hard.
 *
 * Source: published physical and active dimensions for size-2 sensors, which
 * agree across manufacturers on 36 x 25.6 mm active. Independent check: that
 * aspect is 1.406, and the operator's own periapical is 2400 x 1708 px = 1.405.
 * The film we are validating against came off a sensor of exactly this shape.
 */
export const SENSOR = {
  active: { long: 36.0, short: 25.6 },
  body: { long: 43.0, short: 31.2, thickness: 7.5 },
};

/**
 * Anteriors are shot PORTRAIT, posteriors landscape.
 *
 * Not a preference: a canine or incisor is longer than the short side of the
 * sensor and would not fit crown-to-apex across it, and the anterior arch is
 * too tightly curved to take 43 mm of rigid housing sideways. Turning the
 * sensor is what makes the exposure possible at all.
 */
export function sensorFor(type) {
  // MATCHED AS A SUBSTRING, because the manifest's type is the full descriptor
  // -- "central incisor", "lateral incisor", "first premolar". An equality test
  // against 'incisor' matched nothing at all, so every incisor was being shot
  // landscape while the canines beside them turned correctly.
  const portrait = /incisor|canine/i.test(type || '');
  const a = SENSOR.active, b = SENSOR.body;
  return portrait
    ? { w: a.short, h: a.long, bw: b.short, bh: b.long,
        thickness: b.thickness, portrait: true }
    : { w: a.long, h: a.short, bw: b.long, bh: b.short,
        thickness: b.thickness, portrait: false };
}

/**
 * The housing as a rounded slab, at true millimetre size.
 *
 * SHARED for the same reason the exposure geometry is: the atlas and the
 * harness both draw this sensor, and a housing that is rounded in one and
 * square in the other would be two different objects wearing one name. The
 * collision test rounds the same corners in occupancy.js.
 *
 * Built at real size rather than as a unit cube scaled to fit, because a
 * corner radius does not survive non-uniform scaling -- scaling a unit box by
 * (43, 31.2, 7.5) would give three different radii on three axes.
 */
export function housingGeometry(bw, bh, thickness, r = CORNER_MM) {
  const rr = Math.min(r, bw / 2, bh / 2);
  const shape = new THREE.Shape();
  const x = bw / 2 - rr, y = bh / 2 - rr;
  shape.moveTo(-x - rr, -y);
  shape.lineTo(-x - rr, y);
  shape.quadraticCurveTo(-x - rr, y + rr, -x, y + rr);
  shape.lineTo(x, y + rr);
  shape.quadraticCurveTo(x + rr, y + rr, x + rr, y);
  shape.lineTo(x + rr, -y);
  shape.quadraticCurveTo(x + rr, -y - rr, x, -y - rr);
  shape.lineTo(-x, -y - rr);
  shape.quadraticCurveTo(-x - rr, -y - rr, -x - rr, -y);
  // A bevel breaks the edge in the thickness direction, which is the other half
  // of "rounded corners and edges" -- a real housing has no sharp rim either.
  const bevel = Math.min(0.6, thickness / 4);
  const g = new THREE.ExtrudeGeometry(shape, {
    depth: thickness - 2 * bevel, bevelEnabled: true, bevelThickness: bevel,
    bevelSize: bevel, bevelSegments: 2, curveSegments: 8,
  });
  g.translate(0, 0, -(thickness - 2 * bevel) / 2 - bevel);
  return g;
}

// Ordered by increasing deviation from square-and-centred, so the search
// returns the least-contorted placement that works rather than the first one
// it stumbles on.
export const ROLLS = [0, 5, -5, 10, -10, 15, -15, 20, -20];
export const ALONGS = [0, 2, -2, 4, -4, 6, -6, 9, -9];

export const OFFSET = 9.0;         // nominal lingual stand-off
export const SRD = 300.0;          // source to receptor

/**
 * The tube potential the ideal exposure uses.
 *
 * ONE NUMBER FOR THE WHOLE MOUTH, AND THAT IS KNOWN TO BE WRONG. The operator
 * sets exposure by region -- fewer impulses anteriorly, more posteriorly,
 * because there is more bone and tissue to get through at the back -- and this
 * constant cannot express that. It is here as a constant rather than inline so
 * that when per-region exposure is built (wishlist 2b) there is one place that
 * becomes a function of the tooth, and every caller already reads it from the
 * ideal rather than from its own default.
 *
 * What it IS good for today is making kVp reset with the tooth like every other
 * exposure parameter, which is the bug it was added to fix.
 */
export const IDEAL_KVP = 70;

/** Principal axis of a point cloud, by power iteration on its covariance. */
export function principalAxis(pts, centre) {
  const c = [0, 0, 0, 0, 0, 0];
  for (let i = 0; i < pts.length; i += 3) {
    const x = pts[i] - centre.x, y = pts[i + 1] - centre.y, z = pts[i + 2] - centre.z;
    c[0] += x * x; c[1] += x * y; c[2] += x * z;
    c[3] += y * y; c[4] += y * z; c[5] += z * z;
  }
  let v = new THREE.Vector3(0, 1, 0.001).normalize();
  for (let i = 0; i < 64; i++) {
    const n = new THREE.Vector3(
      c[0] * v.x + c[1] * v.y + c[2] * v.z,
      c[1] * v.x + c[3] * v.y + c[4] * v.z,
      c[2] * v.x + c[4] * v.y + c[5] * v.z);
    if (n.length() < 1e-12) break;
    v = n.normalize();
  }
  return v;
}

export function meshPoints(mesh) {
  mesh.updateWorldMatrix(true, false);
  const p = mesh.geometry.getAttribute('position');
  const out = new Float32Array(p.count * 3);
  const t = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    t.fromBufferAttribute(p, i).applyMatrix4(mesh.matrixWorld);
    out[i * 3] = t.x; out[i * 3 + 1] = t.y; out[i * 3 + 2] = t.z;
  }
  return out;
}

export function centroidOf(pts) {
  const c = new THREE.Vector3();
  for (let i = 0; i < pts.length; i += 3) c.add(new THREE.Vector3(pts[i], pts[i + 1], pts[i + 2]));
  return c.multiplyScalar(3 / pts.length);
}

/** Extent along an axis, and the two extremes — apex and crown tip. */
export function axialExtent(pts, centre, v) {
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < pts.length; i += 3) {
    const t = (pts[i] - centre.x) * v.x + (pts[i + 1] - centre.y) * v.y
            + (pts[i + 2] - centre.z) * v.z;
    if (t < lo) lo = t;
    if (t > hi) hi = t;
  }
  return {
    apex: centre.clone().addScaledVector(v, lo),
    tip: centre.clone().addScaledVector(v, hi),
    length: hi - lo,
  };
}

/** Index the teeth by Universal number, with their points cached. */
export function indexTeeth(structures, meshes) {
  const teeth = new Map();
  for (const [fma, s] of Object.entries(structures)) {
    if (s.layer !== 'teeth' || !s.universal) continue;
    const mesh = meshes.get(fma);
    if (!mesh) continue;
    const pts = meshPoints(mesh);
    teeth.set(Number(s.universal), {
      fma, arch: s.arch, type: s.type, mesh, pts, centre: centroidOf(pts),
    });
  }
  let archCentre = new THREE.Vector3();
  for (const t of teeth.values()) archCentre.add(t.centre);
  archCentre.multiplyScalar(1 / teeth.size);
  return { teeth, archCentre };
}

/**
 * The receptor frame for one tooth: along the arch, up the tooth, out the cheek.
 *
 * THE FILM IS ORIENTED ANATOMICALLY: patient-superior is UP, both arches. That
 * is the mounting convention, and it is one rule rather than two — a mandibular
 * film shows crowns at the top and a maxillary film shows them at the bottom
 * because that is where those crowns are. Orienting crown-ward instead gets the
 * lower arch right and prints every upper film upside down.
 */
export function frameFor(universal, { teeth, archCentre }) {
  const order = [...teeth.keys()].sort((a, b) => a - b);
  const i = order.indexOf(universal);
  const self = teeth.get(universal);
  const distal = teeth.get(order[Math.max(0, i - 1)]);
  const mesial = teeth.get(order[Math.min(order.length - 1, i + 1)]);

  const long = principalAxis(self.pts, self.centre);
  if (long.y < 0) long.negate();                 // +Y is superior in app space
  const along = mesial.centre.clone().sub(distal.centre);
  along.addScaledVector(long, -along.dot(long));
  const u = along.normalize();
  const v = long.clone().addScaledVector(u, -long.dot(u)).normalize();
  const buccal = new THREE.Vector3().crossVectors(u, v).normalize();
  if (buccal.dot(self.centre.clone().sub(archCentre)) < 0) buccal.negate();
  return { centre: self.centre, u, v, buccal, arch: self.arch, type: self.type,
           sensor: sensorFor(self.type),
           ext: axialExtent(self.pts, self.centre, v) };
}

/**
 * A complete exposure: where the film sits, where the tube is, where it points.
 *
 * The film's horizontal is derived so cross(pb-pa, pc-pa) points AT the source.
 * Taking the arch tangent directly would put the source behind the film on one
 * side of the mouth, and the DRR refuses that rather than mirroring the image —
 * see the note in drr.js on laterality.
 */
export function exposureFor(f, { tilt = 0, vert = 0, vshift = -4, srd = SRD,
                                 offset = OFFSET, roll = 0, along = 0,
                                 horizAngle = 0 } = {}) {
  const rot = (vec, axis, deg) => vec.clone().applyAxisAngle(axis, deg * Math.PI / 180);
  const S = f.sensor;
  // THE ARCH FLIPS EVERY VERTICAL SIGN, and the controls must mean one thing.
  //
  // The receptor's vertical points superior in both arches (the mounting
  // convention), which is APEX-ward in the maxilla and CROWN-ward in the
  // mandible. So a tilt or a tube angulation that opens the angle downward in
  // the lower arch closes it in the upper one. Applying the raw value to both
  // made maxillary bisecting rotate the film INTO the palate: the fit got worse
  // the more correctly the user tilted, which is the exact opposite of the
  // lesson.
  //
  // With the sign following the arch, "tilt" means the same thing everywhere:
  // the film diverging from the tooth's long axis, and the tube following it.
  const apical = f.arch === 'maxillary' ? -1 : 1;
  let vr = rot(f.v, f.u, tilt * apical);
  let horiz = new THREE.Vector3().crossVectors(vr, f.buccal).normalize();
  // ROLL: the film turned in its own plane. An operator does this constantly --
  // it is how a 43 mm housing is persuaded past a curved arch or a tight floor
  // of mouth -- and searching only stand-off and slide meant the simulator
  // could not do it at all. Applied before the centre is computed, so `vshift`
  // still means "along the film's own vertical" afterwards.
  if (roll) {
    const n = new THREE.Vector3().crossVectors(horiz, vr).normalize();
    vr = rot(vr, n, roll);
    horiz = rot(horiz, n, roll);
  }
  const centreR = f.centre.clone()
    .addScaledVector(f.buccal, -offset)
    .addScaledVector(vr, vshift * apical)
    // ALONG THE ARCH. The film does not have to be centred on the tooth; sliding
    // it mesially or distally is often what makes it fit at all.
    .addScaledVector(horiz, along);
  const pa = centreR.clone()
    .addScaledVector(horiz, -S.w / 2).addScaledVector(vr, -S.h / 2);
  const pb = pa.clone().addScaledVector(horiz, S.w);
  const pc = pa.clone().addScaledVector(vr, S.h);
  // Angling the tube MOVES THE SOURCE along an arc, which is what a tube head
  // does. Merely re-aiming a fixed beam would change no projection at all.
  // THE TUBE HAS TWO ANGULATIONS AND WE ONLY HAD ONE.
  //
  // Vertical angulation about the arch tangent is the bisecting rule and was
  // already here. HORIZONTAL angulation -- swinging the tube mesially or
  // distally about the tooth's long axis -- was missing entirely, and the
  // operator's point is that this is where the flexibility actually lives:
  // "the flexibility of dental xrays comes from the positioning of the tube
  // head less so the placement of the sensor", from an endodontic view.
  //
  // It is the freedom that separates superimposed roots and canals -- shifting
  // the tube and reading which structure moves with it (SLOB) is how a
  // mesiobuccal canal is told from a mesiolingual one. A simulator that cannot
  // swing the tube horizontally cannot show the one manoeuvre endodontics uses
  // most, and it also cannot produce horizontal overlap, which is the classic
  // bitewing error.
  let beamDir = rot(f.buccal.clone().negate(), f.u, vert * apical);
  if (horizAngle) beamDir = rot(beamDir, vr, horizAngle);
  const source = f.centre.clone().addScaledVector(beamDir, -srd);
  return { vr, horiz, centreR, pa, pb, pc, beamDir, source, sensor: S, offset };
}


/**
 * Where a world point lands on the receptor, in receptor millimetres.
 *
 * ANALYTIC, not a render. The DRR already reports magnification by projecting
 * through its camera and reading the film, but that costs an accumulate and a
 * readback -- far too much to have inside a search over placements. This is the
 * same projection done directly: intersect the line from the source through the
 * point with the receptor plane, then express it in the receptor's own basis.
 */
export function toReceptor(p, e) {
  const n = new THREE.Vector3().crossVectors(e.horiz, e.vr).normalize();
  const dir = p.clone().sub(e.source);
  const denom = n.dot(dir);
  if (Math.abs(denom) < 1e-9) return null;          // parallel to the receptor
  const t = n.dot(e.centreR.clone().sub(e.source)) / denom;
  const q = e.source.clone().addScaledVector(dir, t);
  const rel = q.sub(e.centreR);
  return new THREE.Vector2(rel.dot(e.horiz), rel.dot(e.vr));
}

/**
 * How long the tooth measures on the film against its true length.
 *
 * 1.0 would be exact and is not achievable: the tooth is held a few millimetres
 * off the receptor and the beam diverges, so a correct film still magnifies by
 * 3-5%. That floor is why the atlas's accuracy band is +/-6% and not zero, and
 * it is why the ideal below MINIMISES |ratio - 1| rather than seeking it.
 */
export function magnification(f, e) {
  const a = toReceptor(f.ext.tip, e), b = toReceptor(f.ext.apex, e);
  if (!a || !b) return null;
  return a.distanceTo(b) / f.ext.length;
}

/**
 * Is the whole tooth actually ON the film?
 *
 * Magnification says how long the tooth measures; it says nothing about whether
 * the apex made it onto the receptor at all. A placement can be beautifully
 * undistorted and still cut the apex off, which on a periapical is the one
 * failure that matters most -- the apex is usually why the film was taken.
 * Tested against the ACTIVE area, not the housing: the plastic is what has to
 * fit in the mouth, the active area is what records.
 */
export function wholeToothOnFilm(f, e, marginMm = 1.0) {
  const S = e.sensor;
  for (const pt of [f.ext.tip, f.ext.apex]) {
    const q = toReceptor(pt, e);
    if (!q) return false;
    if (Math.abs(q.x) > S.w / 2 - marginMm) return false;
    if (Math.abs(q.y) > S.h / 2 - marginMm) return false;
  }
  return true;
}

/**
 * The ideal exposure for one tooth, in the operator's own order of priority.
 *
 * HIS WORDS, 2026-09-06: "run the math FIRST making sure no clipping THEN make
 * sure the whole tooth is in view, angulation and tilt will suffer but that's
 * the reality". That is the technique, and it is not what this function did
 * before -- it treated fitting as one factor among several and optimised
 * angulation, which had it choosing pretty placements that put the housing
 * through the mandible.
 *
 * So the order is strict:
 *
 *   1. THE SENSOR MUST NOT INTERSECT BONE OR TOOTH. Not "mostly clear", not
 *      "within an allowance" -- a hard constraint, checked against the solid.
 *   2. THE WHOLE TOOTH MUST BE ON THE ACTIVE AREA, crown tip to apex.
 *   3. Only then: the smallest interocclusal opening that achieves it, and
 *      within that the smallest tilt.
 *
 * MAGNIFICATION IS NO LONGER AN OBJECTIVE AT ALL. It is reported, because the
 * film should say what it measures, but a placement is not chosen for it. The
 * previous version's whole premise -- minimise |magnification - 1| -- optimised
 * the one quantity the operator says gives way.
 *
 * THE OPENING IS SEARCHED FROM ZERO UPWARD because the mouth should open only
 * as far as this tooth needs. A fixed opening for the whole mouth was wrong in
 * both directions: too little for the anteriors, more than necessary for the
 * molars.
 */
export function idealFor(f, fitsWith, { maxTiltDeg = 22.5, tiltStepDeg = 7.5,
                                        minOpenMm = 12, maxOpenMm = 28,
                                        openStepMm = 4 } = {}) {
  const tilts = [0];
  for (let t = tiltStepDeg; t <= maxTiltDeg + 1e-9; t += tiltStepDeg) {
    tilts.push(t, -t);
  }
  let fallback = null;
  // THE SEARCH STARTS AT A REALISTIC OPENING, NOT AT ZERO. It used to start at
  // zero and return the first opening that worked -- so any tooth placeable
  // with the teeth together came back with `openingMm: 0` and the atlas shut
  // the mouth when the ideal was applied. A periapical is not taken with the
  // mouth closed: the patient has to open far enough to admit a 7.5 mm housing
  // and its holder before anything else is negotiable. "Only as wide as
  // necessary" is measured from there, not from zero.
  for (let open = minOpenMm; open <= maxOpenMm + 1e-9; open += openStepMm) {
    for (const tilt of tilts) {
      const opts = { tilt, vert: tilt / 2, vshift: -4 };
      // Coarser than the interactive search on purpose: this runs 100+ times
      // per tooth and half-millimetre precision in the stand-off is not what
      // decides whether an exposure is possible.
      // A COARSER SEARCH THAN THE INTERACTIVE ONE, on purpose. This runs
      // ~56 times per tooth and each call is itself a sweep; using the full
      // roll and arch-shift lists here would be 81 sub-sweeps per call and
      // seconds of stall on every tooth the user clicks. Three values of each
      // covers the manoeuvres that matter and the interactive path refines
      // from the result.
      const e = placeSensor(f, opts, fitsWith(open),
                            { step: 1.5, slideStep: 1.5,
                              rolls: [0, 10, -10], alongs: [0, 4, -4],
                              accept: (x) => wholeToothOnFilm(f, x),
                              centre: f.centre });
      const m = magnification(f, e);
      const whole = e.fits && wholeToothOnFilm(f, e);
      // CARRY THE WHOLE PLACEMENT, not just the angles. The search found this
      // exposure using a particular roll, arch shift and slide; storing only
      // the angles and re-searching afterwards lands somewhere that was never
      // the thing validated -- which is how teeth ended up half off the film
      // after the freedoms were added.
      const cand = { tilt, vert: tilt / 2, openingMm: open,
                     // EXPOSURE IS PART OF THE IDEAL, not a setting beside it.
                     // A dentist picks kVp for the region being filmed, so it
                     // belongs to the tooth the same way the angulation does
                     // and must reset with it. Constant for now; see
                     // IDEAL_KVP.
                     kvp: IDEAL_KVP,
                     // Zero: the ideal tube aims through the contacts. Swinging
                     // it mesially or distally is the SLOB manoeuvre, which is a
                     // deliberate DEPARTURE from the ideal, not part of it -- so
                     // it must reset with everything else when the tooth changes.
                     horizAngle: 0,
                     vshift: (opts.vshift ?? -4) + (e.slid ?? 0),
                     offset: e.offset, roll: e.rolled ?? 0, along: e.alongBy ?? 0,
                     magnification: m, fits: e.fits, wholeTooth: whole };
      if (e.fits && whole) return cand;
      // Rank the near misses so a tooth that cannot be done properly still
      // reports the best available rather than nothing: clearing bone first,
      // then getting the tooth on the film.
      const rank = (c) => (c.fits ? 2 : 0) + (c.wholeTooth ? 1 : 0);
      if (!fallback || rank(cand) > rank(fallback)) fallback = cand;
    }
  }
  return fallback;
}

/**
 * Find a stand-off at which the sensor actually FITS, or report that none does.
 *
 * Searched OUTWARD FROM THE NOMINAL IN BOTH DIRECTIONS, which matters: pushing
 * the film further lingual is not always the way out. In the maxilla the palate
 * vaults away from the teeth, so too far palatal is as obstructed as too close,
 * and the free space is a gap rather than a half-line.
 *
 * Where no stand-off fits, this says so instead of quietly choosing one. That
 * failure is the real lesson — it is why the bisecting technique exists, and a
 * simulator that always finds room has removed the difficulty it exists to
 * teach.
 */
export function placeSensor(f, opts, fits, { span = 12, step = 0.5,
                                            slide = 20, slideStep = 0.5,
                                            rolls = ROLLS, alongs = ALONGS,
                                            accept = null, centre = null } = {}) {
  const nominal = opts.offset ?? OFFSET;
  const baseShift = opts.vshift ?? -4;
  let roll = 0, along = 0;
  const test = (offset, vshift) => {
    const e = exposureFor(f, { ...opts, offset, vshift, roll, along });
    // `accept` lets the CALLER add a requirement the collision grid knows
    // nothing about -- in practice, that the tooth is still on the film. It has
    // to be inside the search rather than checked afterwards: sliding the
    // housing 20 mm to clear bone is a fine answer to "does it fit" and a
    // useless one to "can you see the tooth", and the search was only ever
    // asked the first question.
    const normal = new THREE.Vector3().crossVectors(e.horiz, e.vr).normalize();
    const ok = fits({
      centre: e.centreR, horiz: e.horiz, vert: e.vr, normal,
      bw: e.sensor.bw, bh: e.sensor.bh, thickness: e.sensor.thickness,
    });
    if (ok.fits && accept && !accept(e)) {
      return { e, ok: { ...ok, fits: false, rejectedBy: 'accept' } };
    }
    return { e, ok };
  };

  // TWO degrees of freedom, because one is not how a sensor is placed. An
  // operator both pushes the film away from the tooth AND slides it along its
  // own long axis; searching only the stand-off found nothing anywhere in the
  // mouth, which said more about the search than about the anatomy.
  //
  // THE SLIDE RANGE WAS 7 mm AND THE HOUSING IS 43 mm LONG. Once bone became an
  // absolute barrier, 21 of 28 teeth could not be placed at all -- and the
  // sample counts said why: they failed within the first two to fifteen samples
  // of 23,760, meaning one END of the housing was buried before the search
  // began. For an upper incisor the superior end sits 21 mm above the tooth
  // centre, inside the palate, and 7 mm of travel cannot bring it out. That was
  // a limit of the search, not of the mouth. Real operators slide the film much
  // further than that, which is most of what "placing" a film IS.
  //
  // TILT IS NOT SEARCHED, deliberately. Tilting the film is the bisecting
  // technique — the user's decision and the thing being taught — so finding it
  // automatically would answer the question the simulator is asking. Where
  // nothing fits, the honest response is to say so and let them tilt.
  const first = test(nominal, baseShift);
  if (first.ok.fits) {
    return { ...first.e, moved: 0, slid: 0, rolled: 0, alongBy: 0,
             fits: true, hits: 0, probe: first.ok };
  }

  // RANK THE FALLBACK PROPERLY, because `hard` no longer ranks anything: the
  // solid test early-exits on the first buried sample, so it returns 1 for
  // everything that clips and 0 for everything that does not. Ranking on that
  // let a placement which cleared bone but put the tooth off the receptor beat
  // a sensible one -- and since such placements can be far from the tooth, the
  // sensor ended up drawn nowhere near it.
  //
  // When nothing works, what the user should see is what an operator would have
  // TRIED: near the tooth, square, nominal -- with the readout saying it will
  // not fit. So the fallback prefers clearing bone, then the tooth being on the
  // film, then the LEAST DEVIATION from the nominal placement.
  const deviation = (mv, sl, rl, al) =>
    Math.abs(mv) + Math.abs(sl) + Math.abs(rl) * 0.3 + Math.abs(al);
  const rank = (ok, mv, sl, rl, al) =>
    (ok.hard === 0 ? 100 : 0)
    + (ok.rejectedBy === 'accept' ? 0 : 50)
    - deviation(mv, sl, rl, al);
  let best = { score: rank(first.ok, 0, 0, 0, 0), e: first.e, moved: 0, slid: 0,
               rolled: 0, alongBy: 0 };
  // SOLVE THE SLIDE, DO NOT SWEEP IT.
  //
  // The slide that puts the tooth in the middle of the film is not something to
  // go looking for: it is where the tooth currently projects, negated. Two
  // evaluations give the derivative -- the sign conventions differ between the
  // arches and are not worth reasoning about -- and one linear step lands on
  // it. Searching a small window around that instead of the full +/-20 mm turns
  // ~81 slide positions into ~9, and it is also what stops the search choosing
  // a placement that clears bone by sliding the tooth off the receptor.
  //
  // Without this the four freedoms multiply into a sweep that took minutes per
  // tooth and hung the tab.
  const solveSlide = () => {
    if (!centre) return null;
    const at = (vs) => {
      const e = exposureFor(f, { ...opts, offset: nominal, vshift: vs, roll, along });
      const q = toReceptor(centre, e);
      return q ? q.y : null;
    };
    const a = at(0), b = at(10);
    if (a == null || b == null) return null;
    const slope = (b - a) / 10;
    if (Math.abs(slope) < 1e-6) return null;
    return Math.max(-slide, Math.min(slide, -a / slope));
  };

  // HIERARCHICAL, so the ordinary case stays cheap and the least-contorted
  // placement wins. Roll and arch-shift are the freedoms an operator reaches
  // for when the simple ones run out, and they are searched in that order:
  // (0,0) first, then outward. Trying all four freedoms as one flat product
  // would be tens of thousands of placements per tooth and would also let a
  // heavily rolled film beat a straight one that fits just as well.
  for (const along_ of alongs) {
    for (const roll_ of rolls) {
      roll = roll_; along = along_;
      const centred = solveSlide();
      const slideFrom = centred == null ? baseShift : centred;
      const slideSpan = centred == null ? slide : 4;
      for (let d = 0; d <= span; d += step) {
        for (const sgn of d === 0 ? [1] : [1, -1]) {
          const offset = nominal + sgn * d;
          if (offset < 2.0) continue;             // never inside the tooth
          for (let sv = 0; sv <= slideSpan; sv += slideStep) {
            for (const ssgn of sv === 0 ? [1] : [1, -1]) {
              const vshift = slideFrom + ssgn * sv;
              const r = test(offset, vshift);
              if (r.ok.fits) {
                return { ...r.e, moved: sgn * d, slid: vshift - baseShift,
                         rolled: roll_, alongBy: along_, fits: true,
                         hits: 0, probe: r.ok };
              }
              const sc = rank(r.ok, sgn * d, vshift - baseShift, roll_, along_);
              if (sc > best.score) {
                best = { score: sc, e: r.e, moved: sgn * d,
                         slid: vshift - baseShift, rolled: roll_,
                         alongBy: along_ };
              }
            }
          }
        }
      }
    }
  }
  // Nothing fits. Return the LEAST bad placement, flagged, so the collision can
  // be seen rather than an image taken from an impossible position.
  return { ...best.e, moved: best.moved, slid: best.slid, rolled: best.rolled,
           alongBy: best.alongBy, fits: false, hits: 1,
           probe: first.ok };
}
