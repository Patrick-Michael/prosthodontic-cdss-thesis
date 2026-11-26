// Standalone harness for the DRR. The atlas hosts the same engine in radiograph
// mode; this page is where it is developed and checked against the CPU
// reference in tools/cbct/drr_mesh.py.
//
// It takes its geometry from exposure.js and its physics from drr.js, exactly
// as the atlas does. Neither owns a private copy: a simulator whose harness and
// whose shipped mode disagreed about where the film sits would be worse than
// having only one of them.

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createDRR, loadField, capabilities, setShoulderConstant } from './drr.js';
import { indexTeeth, frameFor, placeSensor, housingGeometry, SENSOR, idealFor, magnification, wholeToothOnFilm } from './exposure.js';
import { buildOccupancy, sensorFits } from './occupancy.js';

const BASE = import.meta.env.BASE_URL;
const $ = (s) => document.querySelector(s);

async function main() {
  const canvas = $('#film');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
  renderer.setPixelRatio(1);

  const caps = capabilities(renderer);
  $('#caps').innerHTML = [
    `WebGL2 <b>${caps.isWebGL2 ? 'yes' : 'NO'}</b>`,
    `float colour buffer <b>${caps.colorBufferFloat ? 'yes' : 'no'}</b>`,
    `half-float <b>${caps.colorBufferHalf ? 'yes' : 'no'}</b>`,
    `max texture <b>${caps.maxTextureSize}</b>`,
    `GPU <b>${caps.renderer}</b>`,
  ].join(' &middot; ');
  if (!caps.ok) {
    $('#status').textContent =
      'This device cannot render the radiograph: it needs WebGL2 with a float '
      + 'or half-float colour buffer. Everything else in the atlas still works.';
    $('#status').style.color = '#e8a0a0';
    return;
  }

  const [meta, att] = await Promise.all([
    fetch(`${BASE}teeth.json`).then((r) => r.json()),
    fetch(`${BASE}attenuation.json`).then((r) => r.json()),
  ]);
  const structures = meta.structures;

  $('#status').textContent = 'Loading anatomy…';
  const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(`${BASE}dentition.glb`);
  const meshes = new Map();
  gltf.scene.traverse((o) => { if (o.isMesh) meshes.set(o.name, o); });
  gltf.scene.updateMatrixWorld(true);

  const drr = createDRR(renderer, structures, att);
  const groups = drr.build(meshes);
  // EAGER here, unlike the atlas. On this page the film IS the page, so there
  // is no one to spare the 4 MB from.
  const tf = await loadField(BASE);
  if (tf) drr.setField(tf.data, tf.meta);
  const shParam = new URLSearchParams(location.search).get('shoulder');
  if (shParam !== null) setShoulderConstant(parseFloat(shParam));
  const index = indexTeeth(structures, meshes);
  // ?mucosa overrides the stand-in thickness for sweeps; the DEFAULT lives in
  // occupancy.js so the harness and the atlas cannot disagree about it.
  const mParam = new URLSearchParams(location.search).get('mucosa');
  const mucosaOpt = mParam == null ? {} : { mucosaMm: Number(mParam) };
  // ?corner=<mm> sweeps the housing's corner radius and ?open=<mm> the
  // interocclusal opening; both DEFAULTS live in occupancy.js so the harness
  // and the atlas cannot disagree about the sensor or the posture, the same
  // rule as ?mucosa.
  const q0 = new URLSearchParams(location.search);
  const cParam = q0.get('corner');
  const fitsOpts = cParam === null ? undefined : { cornerMm: parseFloat(cParam) };
  const oParam = q0.get('open');
  const openOpt = oParam === null ? {} : { openingMm: parseFloat(oParam) };
  const FITS_OPTS = fitsOpts;
  // Two grids, one per arch, and the opening applied by SHIFTING THE SAMPLES
  // against the opposing arch's grid rather than by moving any anatomy. That is
  // what lets each tooth be solved at its own opening: filming a lower tooth,
  // the maxilla is "raised" by querying its grid `open` millimetres lower.
  const gridFor = {
    maxillary: buildOccupancy(meshes, structures, { ...mucosaOpt, onlyArch: 'maxillary' }),
    mandibular: buildOccupancy(meshes, structures, { ...mucosaOpt, onlyArch: 'mandibular' }),
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
  const occByArch = gridFor;
  const eroded = gridFor.mandibular ? gridFor.mandibular.erodeCells : 0;
  $('#status').textContent = '';
  const occ = occByArch.mandibular;      // the stats line reports one of the two
  if (occ) {
    let filled = 0;
    for (let i = 0; i < occ.grid.length; i++) filled += occ.grid[i];
    $('#caps').innerHTML += ` &middot; occupancy <b>${occ.nx}\u00d7${occ.ny}\u00d7${occ.nz}</b>`
      + ` @${occ.voxel}mm, <b>${(100 * filled / occ.grid.length).toFixed(1)}%</b> solid`
      + ` (${occ.stats.interiorFilled} interior, ${occ.stats.meshes} meshes,`
      + ` ${occ.stats.onlyArch} only)`;
  }

  const sel = $('#tooth');
  for (const u of [...index.teeth.keys()].sort((a, b) => a - b)) {
    sel.add(new Option(`${u}`, `${u}`, false, u === 30));
  }

  // Applied AFTER the tooth list is built: setting a select's value to an option
  // that does not exist yet is silently ignored, and three "different" arch
  // checks once all rendered the same lower molars because of it.
  const params = new URLSearchParams(location.search);
  for (const [key, id] of [['tooth', '#tooth'], ['kvp', '#kvp'],
                           ['vshift', '#vshift'], ['gamma', '#gamma'],
                           ['tilt', '#tilt'], ['vert', '#vert'],
                           ['aim', '#aim'], ['field', '#field']]) {
    if (params.has(key)) $(id).value = params.get(key);
  }

  // Derived from the angles, never stored alongside them: a separate flag for
  // "which preset is lit" is a second source of truth that drifts the moment a
  // slider moves.
  const PRESETS = { '#preset-par': [0, 0], '#preset-bis': [20, 10],
                    '#preset-bad': [20, 0] };
  function syncPresets() {
    const t = Number($('#tilt').value), v = Number($('#vert').value);
    for (const [id, [pt, pv]] of Object.entries(PRESETS)) {
      $(id).setAttribute('aria-pressed', String(t === pt && v === pv));
    }
  }
  for (const [id, [t, v]] of Object.entries(PRESETS)) {
    $(id).addEventListener('click', () => {
      $('#tilt').value = t; $('#vert').value = v;
      render(); syncPresets();
    });
  }

  // --- the exposure, drawn in 3D beside its own result ----------------------
  const inset = (() => {
    const c = $('#geom');
    const r = new THREE.WebGLRenderer({ canvas: c, antialias: true, alpha: true });
    r.setPixelRatio(Math.min(devicePixelRatio, 2));
    const sc = new THREE.Scene();
    const cam = new THREE.PerspectiveCamera(38, 1.4, 1, 3000);
    const ctl = new OrbitControls(cam, c);
    ctl.enableDamping = true;
    sc.add(new THREE.AmbientLight(0xffffff, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(0.4, 0.9, 0.7);
    sc.add(key);

    const toothMat = new THREE.MeshStandardMaterial({
      color: 0xece7db, roughness: 0.45, transparent: true, opacity: 0.92 });
    const teethGroup = new THREE.Group();
    sc.add(teethGroup);

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
    sc.add(body);
    const active = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ color: 0xbfe8ff, transparent: true,
                                    opacity: 0.5, side: THREE.DoubleSide,
                                    depthWrite: false }));
    sc.add(active);
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 40, 1, true),
      new THREE.MeshBasicMaterial({ color: 0xf0c860, transparent: true,
                                    opacity: 0.10, side: THREE.DoubleSide,
                                    depthWrite: false }));
    sc.add(beam);
    const ray = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
      [new THREE.Vector3(), new THREE.Vector3()]),
      new THREE.LineBasicMaterial({ color: 0xf0c860 }));
    sc.add(ray);
    const axis = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
      [new THREE.Vector3(), new THREE.Vector3()]),
      new THREE.LineBasicMaterial({ color: 0x8de08d }));
    sc.add(axis);

    let framed = false;
    function update({ region, e, f, field, ok }) {
      teethGroup.clear();
      for (const m of region) {
        const o = new THREE.Mesh(m.geometry, toothMat);
        m.updateWorldMatrix(true, false);
        o.matrixAutoUpdate = false;
        o.matrix.copy(m.matrixWorld);
        teethGroup.add(o);
      }
      const S = e.sensor;
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
      body.material.color.setHex(ok ? 0x2f6f8f : 0xb4443c);
      active.position.copy(e.centreR).addScaledVector(normal, S.thickness / 2 + 0.05);
      active.scale.set(S.w, S.h, 1);
      active.quaternion.copy(q);

      // Only the approach is drawn: at 300 mm the full cone fills the frame and
      // hides the anatomy this view exists to explain.
      const DRAW = 42;
      const len = e.source.distanceTo(e.centreR);
      const rNear = (field / 2) * (len - DRAW) / len;
      beam.geometry.dispose();
      beam.geometry = new THREE.CylinderGeometry(rNear, field / 2, DRAW, 40, 1, true);
      beam.position.copy(e.centreR).addScaledVector(e.beamDir, -DRAW / 2);
      beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), e.beamDir);
      ray.geometry.setFromPoints([
        e.centreR.clone().addScaledVector(e.beamDir, -DRAW * 2.2),
        e.centreR.clone().addScaledVector(e.beamDir, 6)]);
      axis.geometry.setFromPoints([f.ext.apex, f.ext.tip]);

      // Viewed DOWN THE ARCH: receptor tilt, tube angulation and the tooth's
      // long axis all lie in the plane perpendicular to the mesiodistal axis,
      // so any other viewpoint foreshortens the very angles being taught.
      if (!framed) {
        cam.position.copy(f.centre)
          .addScaledVector(e.horiz, 118)
          .addScaledVector(e.beamDir, -34)
          .addScaledVector(e.vr, 12);
        cam.up.set(0, 1, 0);
        ctl.target.copy(f.centre);
        framed = true;
      }
      const w = c.clientWidth, h = Math.round(w * 0.62);
      r.setSize(w, h, false);
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
    }
    (function loop() { ctl.update(); r.render(sc, cam); requestAnimationFrame(loop); })();
    return { update };
  })();

  // ?quick=1 reports what SELECTING a tooth actually produces -- the same cheap
  // placement path the atlas uses on click, not the slow ideal. That is the
  // thing the user sees, so it is the thing to measure.
  if (new URLSearchParams(location.search).get('quick') === '1') {
    const out = [];
    let ok = 0, clip = 0, off = 0;
    for (const u of [...index.teeth.keys()].sort((a, b) => a - b)) {
      const f = frameFor(u, index);
      const fits = fitsWithFor(f.arch)(12);
      let got = null;
      for (const tilt of [0, 8, -8, 16, 24]) {
        const e = placeSensor(f, { tilt, vert: tilt / 2, vshift: -4 }, fits,
                              { rolls: [0, 10, -10], alongs: [0],
                                accept: (x) => wholeToothOnFilm(f, x),
                                centre: f.centre });
        const whole = e.fits && wholeToothOnFilm(f, e);
        if (!got || (e.fits && !got.fits)
            || (e.fits === got.fits && whole && !got.whole)) {
          got = { tilt, fits: e.fits, whole };
        }
        if (e.fits && whole) break;
      }
      if (got.fits && got.whole) { ok++; out.push(`${u}:ok@${got.tilt}`); }
      else if (!got.fits) { clip++; out.push(`${u}:CLIP`); }
      else { off++; out.push(`${u}:OFF`); }
    }
    $('#readout').textContent =
      `ok ${ok}/28, clipping ${clip}, tooth off film ${off} | ` + out.join(' ');
    return;
  }

  // ?ideal=1 reports, per tooth, what the old fixed default achieved against
  // what the solved ideal does. The claim being tested is that a per-tooth
  // ideal is worth having at all -- if the flat default were already within the
  // accuracy band everywhere, this would be machinery for nothing.
  if (new URLSearchParams(location.search).get('ideal') === '1') {
    const rows = [];
    let winD = 0, winI = 0, tilted = 0;
    for (const u of [...index.teeth.keys()].sort((a, b) => a - b)) {
      const f = frameFor(u, index);
      const fits = fitsWithFor(f.arch)(0);
      const dflt = placeSensor(f, { tilt: 0, vert: 0, vshift: -4 }, fits);
      const md = magnification(f, dflt);
      // ?tol=<x> overrides the early-exit threshold so the tilt sweep can be
      // FORCED to run. Without it the zero-tilt exit fires at every tooth and
      // the search below is never exercised at all -- which is a fine result
      // and a terrible reason to trust untested code.
      const tolP = new URLSearchParams(location.search).get('tol');
      const it = idealFor(f, fitsWithFor(f.arch));
      if (md != null && Math.abs(md - 1) < 0.06) winD++;
      if (it && it.score < 0.06) winI++;
      if (it && it.tilt !== 0) tilted++;
      rows.push(`${u}:${md == null ? 'NA' : md.toFixed(3)}`
        + `->${it ? it.magnification.toFixed(3) : 'NA'}`
        + `@${it ? it.tilt : '?'}\u00b0`
        + `${it && !it.fits ? '!CLIP' : ''}`
        + `${it && it.fits && !it.wholeTooth ? '!OFF' : ''}`
        + `${it && it.openingMm ? `o${it.openingMm}` : ''}`);
    }
    $('#readout').textContent =
      `within 6%: default ${winD}/28, ideal ${winI}/28 | needs tilt ${tilted} `
      + `| ` + rows.join(' ');
    return;
  }

  // ?window=1 reports the DISPLAY WINDOW chosen for every tooth.
  //
  // The window is a percentile stretch fitted per film, and the suspicion it
  // exists to test is that a low-contrast view -- thin anterior roots, nasal
  // air, and maxillary alveolar bone measured 42% less dense than mandibular --
  // gets a narrow window and therefore amplifies everything faint in it,
  // including the trabecular field. That is a claim about numbers, so measure
  // the numbers before changing how they are chosen.
  if (new URLSearchParams(location.search).get('window') === '1') {
    const out = [];
    for (const u of [...index.teeth.keys()].sort((a, b) => a - b)) {
      const f = frameFor(u, index);
      const e = placeSensor(f, { tilt: 0, vert: 0, vshift: -4 },
                            fitsWithFor(f.arch)(0));
      const S = e.sensor;
      const w = S.portrait ? 150 : 240, h = Math.round(w * S.h / S.w);
      drr.resize(w, h);
      drr.place({ source: e.source, pa: e.pa, pb: e.pb, pc: e.pc });
      drr.setEnergy(70);
      drr.setBeam({ axis: e.beamDir, fieldDiameterMm: 60,
                    distanceMm: e.source.distanceTo(e.centreR) });
      drr.accumulate();
      const win = drr.autoWindow();
      out.push(win ? `${u}:${win.lo.toFixed(2)}-${win.hi.toFixed(2)}`
                     + `(${(win.hi - win.lo).toFixed(2)})` : `${u}:FAILED`);
    }
    $('#readout').textContent = 'window lo-hi(width) per tooth | ' + out.join(' ');
    return;
  }

  // ?audit=1 places the sensor at every tooth in one load and reports the
  // distribution. Sweeping the mucosa stand-in one tooth at a time was going to
  // take an hour of page loads to answer a question worth one.
  if (new URLSearchParams(location.search).get('audit') === '1') {
    const rows = [];
    let fitN = 0, movedN = 0, failN = 0;
    for (const u of [...index.teeth.keys()].sort((a, b) => a - b)) {
      const f = frameFor(u, index);
      const aTilt = Number(new URLSearchParams(location.search).get('tilt') ?? 0);
      const e = placeSensor(f, { tilt: aTilt, vert: aTilt / 2, vshift: -4 },
                            fitsWithFor(f.arch)(Number(oParam ?? 0)));
      // Report the CONTACT at the chosen placement, not just the verdict: a
      // placement can pass the budget and still be visibly in bone if the
      // budget or the sampling is wrong, and "ok" hides that.
      const probe = sensorFits(occByArch[f.arch] ?? occByArch.mandibular, {
        centre: e.centreR, horiz: e.horiz, vert: e.vr,
        normal: new THREE.Vector3().crossVectors(e.horiz, e.vr).normalize(),
        bw: e.sensor.bw, bh: e.sensor.bh, thickness: e.sensor.thickness,
      }, fitsOpts);
      if (!e.fits) { failN++; rows.push(`${u}:FAIL(${e.hits})`); }
      else if (Math.abs(e.moved) > 0.01 || Math.abs(e.slid) > 0.01) {
        movedN++;
        rows.push(`${u}:mv${e.moved.toFixed(1)}/sl${e.slid.toFixed(1)}`);
      } else { fitN++; rows.push(`${u}:ok`); }
      rows[rows.length - 1] += `[h${probe.hard}/s${probe.soft}of${probe.of}]`;
    }
    $('#readout').textContent =
      `voxel-correction ${eroded} cell, opening ${Number(oParam ?? 0)} mm — `
      + `nominal ${fitN}, `
      + `moved ${movedN}, fail ${failN} `
      + `of ${rows.length} | ` + rows.join(' ');
    return;
  }

  function render() {
    const universal = Number(sel.value);
    const opts = {
      kvp: Number($('#kvp').value), vshift: Number($('#vshift').value),
      tilt: Number($('#tilt').value), vert: Number($('#vert').value),
    };
    const gamma = Number($('#gamma').value);
    const aim = Number($('#aim').value);
    const field = Number($('#field').value);
    $('#kvpv').textContent = `${opts.kvp} kVp`;
    $('#vshiftv').textContent = `${opts.vshift.toFixed(1)} mm`;
    $('#gammav').textContent = gamma.toFixed(2);
    $('#tiltv').textContent = `${opts.tilt}°`;
    $('#vertv').textContent = `${opts.vert}°`;
    $('#aimv').textContent = `${aim} mm`;
    $('#fieldv').textContent = `${field} mm`;

    const f = frameFor(universal, index);
    const e = placeSensor(f, opts, fitsWithFor(f.arch)(Number(oParam ?? 0)));
    const S = e.sensor;

    const wMax = Math.min(900, Math.floor(canvas.clientWidth));
    const w = S.portrait ? Math.round(wMax * 0.62) : wMax;
    const h = Math.round(w * S.h / S.w);
    renderer.setSize(w, h, false);
    drr.resize(w, h);

    drr.place({ source: e.source, pa: e.pa, pb: e.pb, pc: e.pc });
    const energy = drr.setEnergy(opts.kvp);
    drr.setGamma(gamma);
    const rot = (v, ax, deg) => v.clone().applyAxisAngle(ax, deg * Math.PI / 180);
    const beamAxis = aim
      ? rot(e.beamDir, f.u, Math.atan2(aim, e.source.distanceTo(e.centreR)) * 180 / Math.PI)
      : e.beamDir;
    drr.setBeam({ axis: beamAxis, fieldDiameterMm: field,
                  distanceMm: e.source.distanceTo(e.centreR) });
    drr.accumulate();
    // Fixed, not fitted -- the harness must show what the atlas shows.
    // ?window=1 above still calls autoWindow, which is what it exists to measure.
    const win = drr.setWindow();
    drr.draw(null);

    const order = [...index.teeth.keys()].sort((a, b) => a - b);
    const near = order.filter((u) => Math.abs(u - universal) <= 1
      && index.teeth.get(u).arch === f.arch);
    inset.update({ region: near.map((u) => index.teeth.get(u).mesh),
                   e, f, field, ok: e.fits });

    const toFilm = (p) => {
      const n = p.clone().project(drr.camera);
      return new THREE.Vector2((n.x * 0.5 + 0.5) * S.w, (n.y * 0.5 + 0.5) * S.h);
    };
    const filmLen = toFilm(f.ext.tip).distanceTo(toFilm(f.ext.apex));
    const ratio = filmLen / f.ext.length;
    // A correct film still magnifies: the tooth is held off the receptor and the
    // beam diverges, so flawless paralleling comes back 3-5% long. The band is
    // 6% for that reason, not zero.
    const verdict = Math.abs(ratio - 1) < 0.06
      ? `accurate (×${ratio.toFixed(2)} magnification)`
      : ratio > 1 ? `ELONGATED ${((ratio - 1) * 100).toFixed(0)}%`
                  : `FORESHORTENED ${((1 - ratio) * 100).toFixed(0)}%`;
    const placement = !e.fits
      ? `<b>WILL NOT FIT</b> — best overlap ${e.hits} of ${e.probe.of} samples in bone; tilt the sensor`
      : (Math.abs(e.moved) > 0.01 || Math.abs(e.slid) > 0.01)
        ? `moved ${e.moved.toFixed(1)} mm out, ${e.slid.toFixed(1)} mm along`
        : 'nominal placement';

    $('#readout').innerHTML =
      `tooth ${universal} (${f.type}, ${S.portrait ? 'portrait' : 'landscape'}) `
      + `&middot; ${energy.keV.toFixed(1)} keV eff &middot; tilt ${opts.tilt}°, `
      + `tube ${opts.vert}° (rule wants ${(opts.tilt / 2).toFixed(1)}°) `
      + `&middot; <b>${verdict}</b> &mdash; ${filmLen.toFixed(1)} mm on film vs `
      + `${f.ext.length.toFixed(1)} mm true &middot; ${placement} &middot; `
      + `window ${win ? `${win.lo.toFixed(2)}–${win.hi.toFixed(2)} τ` : 'default'}`;
  }

  for (const id of ['#tooth', '#kvp', '#vshift', '#gamma', '#tilt', '#vert',
                    '#aim', '#field']) {
    $(id).addEventListener('input', render);
  }
  window.addEventListener('resize', render);
  for (const id of ['#tilt', '#vert']) $(id).addEventListener('input', syncPresets);
  render();
  syncPresets();
}

main().catch((err) => {
  $('#status').textContent = `Failed: ${err.message}`;
  $('#status').style.color = '#e8a0a0';
  throw err;
});
