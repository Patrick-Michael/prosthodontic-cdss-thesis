// Radiograph mode for the atlas: a film on the right, the sensor in the mouth.
//
// The standalone harness at drr.html stays as the reference and the place to
// develop; this is the same engine wired into the atlas, so the two must not
// diverge — both take their geometry from exposure.js and their physics from
// drr.js, and neither owns a private copy of either.
//
// It SHARES THE ATLAS'S RENDERER. A second WebGL context would upload all 15 MB
// of geometry again; instead the film is rendered to an offscreen target and
// read back into a 2D canvas, which costs one readback per control change
// rather than a second copy of the mouth sitting in video memory.

import * as THREE from 'three';
import { createDRR, loadField } from './drr.js';
import { indexTeeth, frameFor, placeSensor, housingGeometry, SENSOR,
         idealFor, wholeToothOnFilm, IDEAL_KVP } from './exposure.js';
import { buildOccupancy, sensorFits, archOf, INTEROCCLUSAL_MM }
  from './occupancy.js';

export function createRadiograph({ renderer, scene, structures, meshes, att, dom,
                                  onState = () => {} }) {
  const drr = createDRR(renderer, structures, att);
  if (!drr.ok) {
    dom.panel.innerHTML =
      '<h2 class="panel-title">Radiograph</h2><p class="rg-note">This device '
      + 'cannot render the simulated radiograph: it needs WebGL2 with a float '
      + 'or half-float colour buffer. The rest of the atlas is unaffected.</p>';
    return { ok: false, setTooth() {}, toggle() {}, isOn: () => false };
  }
  drr.build(meshes);
  const index = indexTeeth(structures, meshes);
  // Voxelised once. Every later placement test is an array lookup, which is
  // what makes collision affordable while a slider is moving.
  // ONE GRID PER ARCH BEING FILMED. The opposing arch is held away by the
  // interocclusal opening, because a periapical is not taken with the mouth
  // shut; the arch being filmed stays where it is, since the sensor is placed
  // against it. Two grids at ~1.4M cells each is cheaper than the readback it
  // replaces, and they are built once.
  const FITS_OPTS = undefined;
  // Two grids, one per arch, and the opening applied by SHIFTING THE SAMPLES
  // against the opposing arch's grid rather than by moving any anatomy. That is
  // what lets each tooth be solved at its own opening: filming a lower tooth,
  // the maxilla is "raised" by querying its grid `open` millimetres lower.
  const gridFor = {
    maxillary: buildOccupancy(meshes, structures, { onlyArch: 'maxillary' }),
    mandibular: buildOccupancy(meshes, structures, { onlyArch: 'mandibular' }),
  };
  const fitsWithFor = (arch) => (open) => (spec) => {
    const self = sensorFits(gridFor[arch], spec, FITS_OPTS);
    if (!self.fits) return self;
    const opp = arch === 'mandibular' ? 'maxillary' : 'mandibular';
    const offsetY = arch === 'mandibular' ? -open : open;
    const other = sensorFits(gridFor[opp], spec, { ...FITS_OPTS, offsetY });
    return other.fits
      ? { fits: true, hard: 0, soft: self.soft + other.soft, of: self.of + other.of }
      : other;
  };



  // --- the sensor, drawn in the mouth --------------------------------------
  //
  // docs/wishlist.md asked for the receptor and beam visible in the 3D view
  // alongside the film. Seeing the tilt that foreshortened an image teaches
  // more than being told the image is foreshortened.
  const rig = new THREE.Group();
  rig.visible = false;
  scene.add(rig);

  // THE HOUSING, not the image. 43 x 31.2 x 7.5 mm of rigid plastic is what has
  // to fit in the mouth, and drawing only the active area would show the
  // sensor as thin and smaller than it is -- flattering exactly the constraint
  // this is meant to make visible.
  // The housing is built at TRUE SIZE and cached per orientation, because a
  // corner radius does not survive being scaled from a unit cube. Only two
  // shapes ever exist -- portrait and landscape -- so a two-entry cache is the
  // whole of it.
  const housings = new Map();
  const housingFor = (S) => {
    const key = `${S.bw}x${S.bh}x${S.thickness}`;
    if (!housings.has(key)) {
      housings.set(key, housingGeometry(S.bw, S.bh, S.thickness));
    }
    return housings.get(key);
  };

  const body = new THREE.Mesh(
    housingGeometry(SENSOR.body.long, SENSOR.body.short, SENSOR.body.thickness),
    new THREE.MeshStandardMaterial({ color: 0x2f6f8f, roughness: 0.55,
                                     transparent: true, opacity: 0.62 }));
  const bodyEdges = new THREE.LineSegments(
    new THREE.EdgesGeometry(body.geometry, 25),
    new THREE.LineBasicMaterial({ color: 0x9fdcff }));
  body.add(bodyEdges);
  rig.add(body);
  // The active area, on the face the beam meets.
  const film = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({ color: 0xbfe8ff, transparent: true,
                                  opacity: 0.5, side: THREE.DoubleSide,
                                  depthWrite: false }));
  rig.add(film);

  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(1, 1, 1, 40, 1, true),
    new THREE.MeshBasicMaterial({ color: 0xf0c860, transparent: true,
                                  // Very faint on purpose. The beam is context,
                                  // not subject: at any weight that reads as a
                                  // solid it becomes a tan slab lying across the
                                  // face and hides the anatomy the atlas exists
                                  // to show.
                                  opacity: 0.055, side: THREE.DoubleSide,
                                  depthWrite: false }));
  rig.add(beam);
  const ray = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
    new THREE.LineBasicMaterial({ color: 0xf0c860 }));
  rig.add(ray);

  // NO DEFAULT TOOTH. Opening on tooth 30 whatever the user had selected states
  // a subject they did not choose, and on a simulated radiograph that is worse
  // than showing nothing: it looks like an answer.
  const state = { tooth: null, kvp: IDEAL_KVP, tilt: 0, vert: 0, vshift: -4,
                  // Swinging the tube mesially or distally about the tooth's
                  // long axis. The operator's point is that this is where the
                  // flexibility of the technique actually lives, and it is the
                  // manoeuvre endodontics leans on hardest -- shift the tube,
                  // see which root moves, and you have told MB from ML.
                  horizAngle: 0,
                  // The rest of the placement the ideal actually found. Kept so
                  // update() reproduces THAT exposure instead of re-searching
                  // and finding a different one.
                  roll: 0, along: 0, offset: undefined,
                  // How far the mouth is held open for THIS exposure. Set from
                  // the tooth's ideal, because the right opening is the
                  // smallest one that tooth needs, not one figure for the mouth.
                  openingMm: 0,
                  gamma: 1, field: 60, on: false };
  const ctx = dom.canvas.getContext('2d');
  let fieldTried = false;

  // The ideal exposure per tooth, solved on first use and kept.
  //
  // LAZY because the solve places the sensor at up to 21 tilts and each of
  // those may run the stand-off and slide search; doing all 28 at load would
  // stall the atlas for a feature most visits never open. One tooth's solve is
  // imperceptible, and it is the tooth the user just asked for.
  // --- opening the mouth, in the scene as well as in the grid ---------------
  //
  // The collision grids hold the opposing arch INTEROCCLUSAL_MM away, because a
  // periapical is not taken with the mouth shut. Doing that to the grid alone
  // was a bug: placement was solved against an open mouth and the sensor was
  // then drawn in a closed one, so it clipped through the opposing arch at
  // every tooth. The view and the physics have to describe the same mouth.
  //
  // Applied to the meshes the atlas is already showing, so the user SEES the
  // mouth open when radiograph mode is on -- which is also the honest picture
  // of how the exposure is taken.
  const byArch = { maxillary: [], mandibular: [] };
  for (const [fma, mesh] of meshes) {
    const a = archOf(fma, structures);
    if (a) byArch[a].push({ mesh, y0: mesh.position.y });
  }
  let openedFor = null;
  function openMouthFor(arch, mm) {
    const key = `${arch}:${mm}`;
    if (openedFor === key) return;
    for (const k of ['maxillary', 'mandibular']) {
      const dy = arch == null ? 0
        : (k === arch ? 0 : (k === 'maxillary' ? mm : -mm));
      for (const { mesh, y0 } of byArch[k]) mesh.position.y = y0 + dy;
    }
    openedFor = key;
    // The DRR's accumulation meshes are frozen copies; without this the film
    // would still be integrating the closed mouth.
    drr.refreshTransforms();
  }

  const ideals = new Map();
  // Warm the rest in the background once the mode is open, so only the first
  // tooth ever pays. requestIdleCallback keeps it off the frames the user is
  // actually looking at; a tooth clicked before its turn is solved on demand
  // and the warmer skips it.
  function ideal(universal) {
    if (!ideals.has(universal)) {
      const f = frameFor(universal, index);
      ideals.set(universal, idealFor(f, fitsWithFor(f.arch)));
    }
    return ideals.get(universal);
  }

  /**
   * Put the controls back to this tooth's ideal.
   *
   * SELECTING A TOOTH DOES THIS, which is the point: the old behaviour carried
   * the outgoing tooth's angles to the incoming one, so a 20-degree tilt chosen
   * for a molar silently became the starting point for an incisor. The user's
   * adjustments are theirs to keep while they are on a tooth, and meaningless
   * once they leave it.
   */
  /**
   * A good placement for this tooth, cheaply.
   *
   * WHY THIS EXISTS SEPARATELY FROM THE IDEAL. Solving the ideal sweeps eight
   * openings by seven tilts by nine roll/arch-shift branches, each one a
   * stand-off sweep of SOLID collision tests -- tens of thousands of them per
   * tooth. That is fine for a deliberate "find me the ideal"; it is not
   * something to run when someone clicks a tooth, and running it there hung the
   * tab hard enough to take the page down.
   *
   * So selecting a tooth gets this: paralleling, a nominal opening, and the
   * slide SOLVED so the tooth lands on the film rather than swept for. One
   * placement search, no outer loops. The full ideal is a button.
   */
  // CACHED, because a tooth with NO valid placement is the expensive case: the
  // search cannot short-circuit, so it runs every tilt, roll, stand-off and
  // slide before giving up. That is exactly the six mandibular teeth, and
  // without a cache the cost was paid again on every click.
  const quicks = new Map();
  function quickPlacement(universal) {
    if (quicks.has(universal)) return quicks.get(universal);
    const got = solveQuick(universal);
    quicks.set(universal, got);
    return got;
  }

  function solveQuick(universal) {
    const f = frameFor(universal, index);
    const fits = fitsWithFor(f.arch)(INTEROCCLUSAL_MM);
    // IT HAS TO TRY TILTS. Paralleling cannot clear an anterior palate: a 43 mm
    // portrait housing sitting 9 mm palatal to an upper incisor runs 21 mm up
    // into the vault, and no amount of stand-off or slide gets it out --
    // TILTING it is the answer, which is the whole reason the bisecting
    // technique exists. Searching tilt 0 only meant every anterior fell through
    // to the least-bad placement and was drawn buried in the palate.
    //
    // Affordable now because the centring slide is solved rather than swept:
    // five tilts by three rolls is fifteen branches, not the eight-openings-by-
    // seven-tilts sweep the full ideal runs.
    let fallback = null;
    for (const tilt of [0, 8, -8, 16, 24]) {
      const opts = { tilt, vert: tilt / 2, vshift: -4 };
      // MILLIMETRE STEPS, not half-millimetre. This search runs on a click, and
      // for a tooth with no valid placement it cannot short-circuit -- it runs
      // every branch to the end. At the default 0.5 mm that is 25 stand-offs by
      // 17 slides per branch; at 1 mm it is 13 by 9, four times less, and half
      // a millimetre of stand-off does not decide whether an exposure is
      // possible. The Ideal button still searches finely.
      const e = placeSensor(f, opts, fits,
                            { step: 1.0, slideStep: 1.0,
                              rolls: [0, 10, -10], alongs: [0],
                              accept: (x) => wholeToothOnFilm(f, x),
                              centre: f.centre });
      const whole = e.fits && wholeToothOnFilm(f, e);
      const cand = { tilt, vert: tilt / 2, horizAngle: 0,
                     vshift: -4 + (e.slid ?? 0),
                     offset: e.offset, roll: e.rolled ?? 0,
                     along: e.alongBy ?? 0, openingMm: INTEROCCLUSAL_MM,
                     kvp: IDEAL_KVP,
                     fits: e.fits, wholeTooth: whole, quick: true };
      if (e.fits && whole) return cand;
      if (!fallback
          || (cand.fits && !fallback.fits)
          || (cand.fits === fallback.fits && cand.wholeTooth && !fallback.wholeTooth)) {
        fallback = cand;
      }
    }
    return fallback;
  }

  // Which tooth the current placement was solved for, so opening the panel
  // later solves the tooth that is already selected.
  let placedFor = null;
  function placeFor(universal) {
    if (placedFor === universal) return;
    applyIdeal(universal, ideals.get(universal) ?? quickPlacement(universal));
    placedFor = universal;
  }

  let lastQuick = null;
  function applyIdeal(universal, it) {
    it = it ?? ideal(universal);
    lastQuick = it;
    if (!it) return null;
    state.tilt = it.tilt;
    state.vert = it.vert;
    state.vshift = it.vshift;
    state.openingMm = it.openingMm ?? 0;
    state.horizAngle = it.horizAngle ?? 0;
    state.roll = it.roll ?? 0;
    state.along = it.along ?? 0;
    state.offset = it.offset;
    // KVP RESETS WITH THE TOOTH, for the same reason the angles do: it is a
    // property of the exposure being taken, not of the session. It was the one
    // exposure parameter left out when selecting a tooth started restoring the
    // ideal, so a tube potential dialled up for a molar silently became an
    // incisor's starting point -- exactly the bug horizAngle had, one control
    // over.
    //
    // NOT reset here, deliberately: `field` is the collimator, which is a
    // property of the MACHINE and does not change between exposures; and
    // `gamma` is a display control on the rendered film, not a property of the
    // exposure at all. Both are correct to persist.
    state.kvp = it.kvp ?? IDEAL_KVP;
    onState({ tilt: it.tilt, vert: it.vert, vshift: it.vshift,
              horizAngle: it.horizAngle ?? 0, kvp: state.kvp });
    return it;
  }

  function update() {
    if (!state.on) return;
    if (state.tooth == null || !index.teeth.has(state.tooth)) {
      const c = dom.canvas.getContext('2d');
      dom.canvas.width = dom.canvas.width;          // clear
      c.fillStyle = '#000';
      c.fillRect(0, 0, dom.canvas.width, dom.canvas.height);
      dom.readout.textContent =
        'Select a tooth — in the 3D view or on the chart — to expose it.';
      dom.toothLabel.textContent = '—';
      return;
    }
    const f = frameFor(state.tooth, index);
    openMouthFor(f.arch, state.openingMm);
    // Pinned to the placement the ideal validated: the roll and arch shift are
    // not re-searched, and the stand-off and slide start from what it found, so
    // the first test reproduces it exactly. That is also what makes selecting a
    // tooth fast -- the interactive path is one collision test, not a sweep.
    const e = placeSensor(f, state, fitsWithFor(f.arch)(state.openingMm),
                          { rolls: [state.roll], alongs: [state.along] });
    const S = e.sensor;

    // --- the film ---------------------------------------------------------
    // Portrait for anteriors, so the canvas follows the sensor rather than the
    // other way round.
    const wMax = Math.max(64, Math.min(520, dom.canvas.clientWidth || 240));
    const w = S.portrait ? Math.round(wMax * 0.62) : wMax;
    const h = Math.round(w * S.h / S.w);
    dom.canvas.width = w; dom.canvas.height = h;
    drr.resize(w, h);
    drr.place({ source: e.source, pa: e.pa, pb: e.pb, pc: e.pc });
    const energy = drr.setEnergy(state.kvp);
    drr.setGamma(state.gamma);
    drr.setBeam({ axis: e.beamDir, fieldDiameterMm: state.field,
                  distanceMm: e.source.distanceTo(e.centreR) });
    drr.accumulate();
    // Fixed, not fitted: see drr.js WINDOW_LO. Was a GPU readback per render.
    const win = drr.setWindow();
    drr.toCanvas(ctx, w, h);

    // --- the sensor in the mouth ------------------------------------------
    const normal = new THREE.Vector3().crossVectors(e.horiz, e.vr).normalize();
    const q = new THREE.Quaternion().setFromRotationMatrix(
      new THREE.Matrix4().makeBasis(e.horiz, e.vr, normal));
    body.position.copy(e.centreR);
    const g = housingFor(S);
    if (body.geometry !== g) {
      body.geometry = g;
      bodyEdges.geometry.dispose();
      bodyEdges.geometry = new THREE.EdgesGeometry(g, 25);
    }
    body.quaternion.copy(q);
    body.material.color.setHex(e.fits ? 0x2f6f8f : 0xb4443c);
    film.position.copy(e.centreR).addScaledVector(normal, S.thickness / 2 + 0.05);
    film.scale.set(S.w, S.h, 1);
    film.quaternion.copy(q);

    // Only the approach is drawn. At a 300 mm source distance the full cone
    // swallows the whole model and hides the anatomy it exists to explain.
    const DRAW = 30;
    const len = e.source.distanceTo(e.centreR);
    const rNear = (state.field / 2) * (len - DRAW) / len;
    beam.geometry.dispose();
    beam.geometry = new THREE.CylinderGeometry(rNear, state.field / 2, DRAW, 40, 1, true);
    beam.position.copy(e.centreR).addScaledVector(e.beamDir, -DRAW / 2);
    beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), e.beamDir);
    ray.geometry.setFromPoints([
      e.centreR.clone().addScaledVector(e.beamDir, -DRAW * 3.0),
      e.centreR.clone().addScaledVector(e.beamDir, 5)]);

    // --- what it actually measures ----------------------------------------
    const toFilm = (p) => {
      const n = p.clone().project(drr.camera);
      return new THREE.Vector2((n.x * 0.5 + 0.5) * S.w, (n.y * 0.5 + 0.5) * S.h);
    };
    const onFilm = toFilm(f.ext.tip).distanceTo(toFilm(f.ext.apex));
    const ratio = onFilm / f.ext.length;
    // A CORRECT FILM STILL MAGNIFIES. The tooth is held a few millimetres off
    // the receptor and the beam diverges, so even flawless paralleling comes
    // back 3-5% long -- which is why the tolerance sits at 6% and not at zero.
    // A ±3% band called teeth 18 and 31 "elongated" at paralleling, where
    // nothing was wrong but the physics.
    const verdict = Math.abs(ratio - 1) < 0.06
      ? `accurate — ×${ratio.toFixed(2)} magnification`
      : ratio > 1 ? `elongated ${((ratio - 1) * 100).toFixed(0)}%`
                  : `foreshortened ${((1 - ratio) * 100).toFixed(0)}%`;
    // Placement is reported as plainly as the distortion. A film that could not
    // be placed is not a rendering fault, it is the exposure being impossible,
    // and saying so is the whole point of testing collision at all.
    const adj = [];
    if (Math.abs(e.moved) > 0.01) {
      adj.push(`${Math.abs(e.moved).toFixed(1)} mm `
        + `${e.moved > 0 ? 'further from' : 'closer to'} the tooth`);
    }
    if (Math.abs(e.slid) > 0.01) {
      adj.push(`slid ${Math.abs(e.slid).toFixed(1)} mm `
        + `${e.slid > 0 ? 'coronally' : 'apically'}`);
    }
    const placement = !e.fits
      ? '<b class="rg-bad">will not fit</b> — the housing meets bone wherever it '
        + 'is put. Tilt the sensor: that is what the bisecting technique is for.'
      : adj.length ? `moved ${adj.join(', ')} to clear tissue`
                   : 'sits where it was placed';
    dom.readout.innerHTML =
      `<b>${verdict}</b> — ${onFilm.toFixed(1)} mm on film, `
      + `${f.ext.length.toFixed(1)} mm true<br>`
      + `${S.portrait ? 'portrait' : 'landscape'} · ${placement}<br>`
      + `${energy.keV.toFixed(0)} keV effective · bisecting rule wants `
      + `${(state.tilt / 2).toFixed(1)}°`
      + (() => {
        // WHY THE IDEAL IS NOT ALWAYS ZERO TILT. Where nothing fits flat, the
        // whole root can only be caught by tilting -- that IS the bisecting
        // technique doing its job, and presenting the compromise silently would
        // teach the opposite of what the simulator exists to teach.
        // NEVER SOLVE FROM THE READOUT. `ideal()` sweeps openings by tilts by
        // roll branches; calling it to write a status line ran that sweep on
        // every render and was the second half of what hung the tab. Describe
        // the placement in hand, and only mention the ideal if one has already
        // been solved.
        const it = ideals.get(state.tooth) ?? lastQuick;
        if (!it) return '';
        const onIdeal = Math.abs(state.tilt - it.tilt) < 0.01
          && Math.abs(state.vert - it.vert) < 0.01
          && Math.abs(state.vshift - it.vshift) < 0.01;
        if (onIdeal) {
          const op = `mouth open ${(it.openingMm ?? 0).toFixed(0)} mm`;
          if (!it.fits) return `<br><b class="rg-bad">no placement clears bone</b>`;
          if (!it.wholeTooth) {
            return `<br><b class="rg-bad">apex runs off the film</b> — `
              + `${op}, ${it.tilt.toFixed(0)}° tilt is the best available`;
          }
          if (it.quick) {
            return `<br>placed at paralleling, ${op} — press Ideal to search `
              + 'the tilts and openings for this tooth';
          }
          return it.tilt === 0
            ? `<br>ideal placement — parallels cleanly, ${op}`
            : `<br>ideal placement — ${it.tilt.toFixed(0)}° of tilt and ${op}; `
              + 'nothing flatter clears the tissue here';
        }
        return `<br>moved off the ideal (${it.tilt.toFixed(1)}° tilt, `
          + `${it.vshift.toFixed(1)} mm framing)`;
      })()
      + (win ? '' : '<br><b>uncalibrated:</b> auto-window failed');
    dom.toothLabel.textContent = `${state.tooth}`;
  }

  return {
    ok: true,
    isOn: () => state.on,
    /** Follow the atlas's own selection: picking a tooth aims the tube at it. */
    setTooth(universal) {
      if (universal == null || !index.teeth.has(universal)) return false;
      const changed = state.tooth !== universal;
      state.tooth = universal;
      // NOTHING IS SOLVED WHILE THE MODE IS CLOSED. `update()` already returns
      // early when the panel is shut, but the placement search sat OUTSIDE that
      // guard -- so every click in the plain 3D atlas paid for an exposure
      // nobody was looking at, and on the mandibular teeth (where the search
      // cannot short-circuit) that was the lag the operator felt with the
      // radiograph panel closed.
      if (changed) {
        placedFor = null;
        if (state.on) placeFor(universal);
      }
      rig.visible = state.on;
      update();
      return true;
    },
    /** Put this tooth back to its ideal after the user has moved things. */
    /** Solve and apply the full ideal. Slow on purpose; the caller says so. */
    restoreIdeal() {
      if (state.tooth == null) return false;
      const ok = !!applyIdeal(state.tooth, ideal(state.tooth));
      if (ok) update();
      return ok;
    },
    idealFor: (u) => ideal(u),
    /**
     * Is the current exposure the one that was chosen for this tooth?
     *
     * The UI lights its "Ideal" button from this rather than tracking a flag of
     * its own: a flag beside the state is a second source of truth for the same
     * fact and drifts the instant a slider moves. Same reasoning as the
     * technique highlight, which is read back from the angles.
     */
    isOnIdeal() {
      const it = ideals.get(state.tooth) ?? lastQuick;
      if (!it) return false;
      return Math.abs(state.tilt - it.tilt) < 0.01
        && Math.abs(state.vert - it.vert) < 0.01
        && Math.abs((state.horizAngle ?? 0) - (it.horizAngle ?? 0)) < 0.01
        && Math.abs(state.vshift - it.vshift) < 0.01
        && Math.abs((state.openingMm ?? 0) - (it.openingMm ?? 0)) < 0.01
        // Once exposure is part of the ideal, a film taken at a kVp the ideal
        // did not choose is not the ideal exposure, and the button that puts it
        // back has to light up to say so.
        && Math.abs((state.kvp ?? IDEAL_KVP) - (it.kvp ?? IDEAL_KVP)) < 0.01;
    },
    set(key, value) { state[key] = value; update(); },
    get: (key) => state[key],
    teeth: () => [...index.teeth.keys()].sort((a, b) => a - b),
    toggle(on) {
      state.on = on;
      rig.visible = on && state.tooth != null;
      if (!on) openMouthFor(null, 0);       // the atlas is a closed mouth again
      if (on) {
        // Opening the panel is when the selected tooth gets its placement.
        if (state.tooth != null) placeFor(state.tooth);
        update();
        // LAZY, and on purpose. The trabecular field is 4 MB and most visits
        // never open radiograph mode; loading it with the anatomy would charge
        // every user for a feature they did not ask for. The film renders
        // immediately without it and re-renders once it lands.
        if (!fieldTried) {
          fieldTried = true;
          loadField(import.meta.env.BASE_URL).then((f) => {
            if (!f) return;
            drr.setField(f.data, f.meta);
            if (state.on) update();
          }).catch(() => {});
        }
      }
    },
    refresh: update,
  };
}
