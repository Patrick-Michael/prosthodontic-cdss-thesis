import * as THREE from 'three';
import { createScene } from './scene.js';
import { createPicking } from './picking.js';
import { createOdontogram } from './odontogram.js';
import { createRadiograph } from './radiograph.js';
import { registerServiceWorker } from './sw-update.js';
import { createLayerPanel, createNotationPicker, createDetailPanel } from './ui.js';

const HOVER_TINT = 0x2f6f8f;
const SELECT_TINT = 0x3d9bd1;

const $ = (sel) => document.querySelector(sel);

// Collapse every panel behind one button. Default to collapsed on a narrow
// screen: the panels are useful, but on a phone they cover the anatomy, and an
// atlas that opens with its subject hidden has failed before it starts.
// matchMedia is read ONCE, so a rotation or resize never yanks the panels out
// from under someone who has deliberately opened them.
//
// Wired at module scope, BEFORE the model is fetched. Inside main() it sat
// behind an await on a 9.9 MB glb, so on a slow phone connection -- precisely
// when someone wants the anatomy unobscured -- the button would not respond.
// Stamped at build time from package.json, so the corner label and the
// changelog cannot drift apart -- both move in the same commit. Wired at module
// scope like initChrome, so it does not wait on the 9.9 MB glb.
function initVersion() {
  const el = document.querySelector('#version');
  if (!el) return;
  // Guarded because this runs at MODULE SCOPE: if the build-time define ever
  // fails to substitute, a bare __APP_VERSION__ is a ReferenceError that takes
  // the whole module down with it, and the atlas would fail to load over a
  // corner label. Never worth that.
  let v = 'dev';
  try { v = __APP_VERSION__; } catch { /* define not substituted */ }
  el.textContent = v;
}

initVersion();

// At module scope, like initVersion: registering the worker must not wait on
// the 15 MB glb, and an update check is the one thing that should happen even
// if the anatomy fails to load.
registerServiceWorker(import.meta.env.BASE_URL);

function initChrome() {
  const btn = document.querySelector('#chrome');
  if (!btn) return;
  const setChrome = (shown) => {
    document.body.classList.toggle('chrome-hidden', !shown);
    btn.setAttribute('aria-expanded', String(shown));
    btn.classList.toggle('is-active', !shown);
  };
  setChrome(!window.matchMedia('(max-width: 900px)').matches);
  btn.addEventListener('click', () => {
    setChrome(document.body.classList.contains('chrome-hidden'));
  });
}
initChrome();

async function main() {
  const canvas = $('#view');
  const status = $('#status');

  const meta = await fetch(`${import.meta.env.BASE_URL}teeth.json`).then((r) => r.json());
  const { layers, structures } = meta;

  const view = createScene(canvas);


  status.textContent = 'Loading anatomy…';
  const meshes = await view.load(`${import.meta.env.BASE_URL}dentition.glb`);

  // APPLY THE LAYER DEFAULTS BEFORE THE FIRST FRAME CAN DRAW THEM.
  //
  // The render loop is already running by the time load() resolves, and the
  // full layer state is not applied until the end of main() -- with the
  // radiograph's two occupancy grids built in between. So for as long as that
  // took, the atlas painted every layer visible: mid-face, ramus and the whole
  // nerve supply flashing up before snapping to the intended set.
  //
  // Setting visibility here closes the window entirely. applyAll() still runs
  // later and is still the single source of truth for opacity and isolation;
  // this only stops the frames before it from lying.
  for (const [fma, mesh] of meshes) {
    const layer = layers[structures[fma]?.layer];
    if (layer) mesh.visible = layer.visible;
  }
  status.remove();

  // --- radiograph mode ------------------------------------------------------
  //
  // Loaded alongside the anatomy but inert until switched on. The attenuation
  // table is small (~50 kB) next to the 15 MB of geometry, so fetching it up
  // front costs nothing measurable and avoids a stall the first time someone
  // asks for a radiograph.
  const att = await fetch(`${import.meta.env.BASE_URL}attenuation.json`)
    .then((r) => r.json()).catch(() => null);
  const radiograph = att && createRadiograph({
    renderer: view.renderer,
    scene: view.scene,
    structures,
    meshes,
    att,
    dom: {
      panel: $('#xray-panel'),
      canvas: $('#rg-film'),
      readout: $('#rg-readout'),
      toothLabel: $('#rg-tooth'),
    },
    // Selecting a tooth now moves the angles to that tooth's ideal, so the
    // sliders have to follow. WITHOUT re-entering radiograph.set(): these are
    // the values it just chose, and echoing them back would re-render for
    // nothing and risk a loop.
    onState: (next) => {
      for (const [id, key, fmt] of [
        ['#rg-tilt', 'tilt', (v) => `${v}\u00b0`],
        ['#rg-vert', 'vert', (v) => `${v}\u00b0`],
        ['#rg-horiz', 'horizAngle', (v) => `${v}\u00b0`],
        ['#rg-vshift', 'vshift', (v) => `${(+v).toFixed(1)} mm`],
        // kVp is part of the ideal exposure, so it comes back with the angles.
        ['#rg-kvp', 'kvp', (v) => `${v} kVp`],
      ]) {
        if (next[key] === undefined) continue;
        const el = document.querySelector(id);
        if (!el) continue;
        el.value = next[key];
        const label = document.querySelector(`${id}v`);
        if (label) label.textContent = fmt(next[key]);
      }
      document.querySelector('#rg-tilt')?.dispatchEvent(
        new Event('techniquesync'));
    },
  });

  // The tooth the current selection belongs to, whatever part of it was clicked.
  const selectedUniversal = () => {
    if (!selected) return null;
    const owner = structures[selected]?.tooth ?? selected;
    const u = Number(structures[owner]?.universal);
    return Number.isFinite(u) ? u : null;
  };

  function setXray(on) {
    if (!radiograph) return;
    $('#xray-panel').hidden = !on;
    $('#xray').classList.toggle('is-active', on);
    $('#xray').setAttribute('aria-pressed', String(on));
    document.body.classList.toggle('xray-on', on);
    if (on && selectedUniversal() != null) radiograph.setTooth(selectedUniversal());
    radiograph.toggle(on);
  }
  $('#xray').addEventListener('click', () => setXray(!radiograph?.isOn()));
  // Assigned inside the radiograph block below; a no-op when the device cannot
  // render a film at all, so callers outside that block need no guard.
  let syncTechniqueSafe = () => {};

  if (radiograph?.ok) {
    for (const [id, key, fmt] of [
      ['#rg-tilt', 'tilt', (v) => `${v}\u00b0`],
      ['#rg-vert', 'vert', (v) => `${v}\u00b0`],
      ['#rg-horiz', 'horizAngle', (v) => `${v}\u00b0`],
      ['#rg-vshift', 'vshift', (v) => `${(+v).toFixed(1)} mm`],
      ['#rg-kvp', 'kvp', (v) => `${v} kVp`],
      ['#rg-field', 'field', (v) => `${v} mm`],
    ]) {
      const label = $(`${id}v`);
      $(id).addEventListener('input', (ev) => {
        label.textContent = fmt(ev.target.value);
        radiograph.set(key, Number(ev.target.value));
      });
    }
    // The technique is DERIVED from the angles rather than stored beside them.
    // A separate "which button is lit" flag is a second source of truth for the
    // same fact, and it drifts the moment a slider moves. Reading it back means
    // the highlight is always what the geometry actually is — and because the
    // angles live in the radiograph's own state, it survives changing tooth for
    // free rather than needing to be restored.
    // THE TECHNIQUE IS WHICH ONE IT IS, not which preset was pressed.
    //
    // This used to light a button only on an EXACT match against (0,0) or
    // (20,10), so every placement the atlas chose for itself -- which is now
    // most of them, at whatever tilt the anatomy allows -- lit neither, and the
    // panel said nothing about what it was showing. Paralleling IS zero
    // receptor tilt; anything else is bisecting, by definition, and the reader
    // wants to know which they are looking at more than they want to know
    // whether a preset was clicked.
    function syncTechnique() {
      const tilt = Number($('#rg-tilt').value);
      const onIdeal = !!radiograph.isOnIdeal?.();
      for (const [id, on] of [
        ['#rg-ideal', onIdeal],
        ['#rg-par', tilt === 0],
        ['#rg-bis', tilt !== 0],
      ]) {
        const el = $(id);
        if (!el) continue;
        el.classList.toggle('is-active', on);
        el.setAttribute('aria-pressed', String(on));
      }
    }
    const preset = (tilt, vert) => () => {
      $('#rg-tilt').value = tilt; $('#rg-tiltv').textContent = `${tilt}\u00b0`;
      $('#rg-vert').value = vert; $('#rg-vertv').textContent = `${vert}\u00b0`;
      radiograph.set('tilt', tilt);
      radiograph.set('vert', vert);
      syncTechnique();
    };
    $('#rg-par').addEventListener('click', preset(0, 0));
    $('#rg-bis').addEventListener('click', preset(20, 10));
    // The ideal is per tooth and solved from the anatomy, so unlike the two
    // presets it has no fixed angles to write here -- it asks for them back.
    $('#rg-ideal').addEventListener('click', () => {
      radiograph.restoreIdeal();
      syncTechnique();
    });
    for (const id of ['#rg-tilt', '#rg-vert']) {
      $(id).addEventListener('input', syncTechnique);
    }
    $('#rg-tilt').addEventListener('techniquesync', syncTechnique);
    syncTechniqueSafe = syncTechnique;
    syncTechnique();
  }

  // --- layer state ---------------------------------------------------------
  const layerState = Object.fromEntries(
    Object.entries(layers).map(([k, l]) => [k, { visible: l.visible, opacity: l.defaultOpacity }]),
  );
  const meshesByLayer = new Map();
  for (const [fma, mesh] of meshes) {
    const layer = structures[fma]?.layer;
    if (!layer) continue;
    mesh.userData.layer = layer;
    if (!meshesByLayer.has(layer)) meshesByLayer.set(layer, []);
    meshesByLayer.get(layer).push(mesh);
  }

  let selected = null;
  let isolated = false;

  function applyLayer(key) {
    const { visible, opacity } = layerState[key];
    for (const mesh of meshesByLayer.get(key) ?? []) {
      const isFocus = isolated && selected === mesh.name;
      mesh.visible = isolated ? isFocus : visible;
      mesh.material.opacity = isFocus ? 1 : opacity;
      // A fully opaque material renders faster and avoids sort artefacts.
      mesh.material.transparent = mesh.material.opacity < 1;
      mesh.material.depthWrite = mesh.material.opacity > 0.95;
    }
  }
  const applyAll = () => Object.keys(layerState).forEach(applyLayer);

  // --- selection & highlight ----------------------------------------------
  const detail = createDetailPanel($('#detail'));
  let chart;

  function tint(fma, color) {
    const mesh = meshes.get(fma);
    if (!mesh) return;
    if (color === null) mesh.material.color.copy(mesh.userData.baseColor);
    else mesh.material.color.copy(mesh.userData.baseColor).lerp(new THREE.Color(color), 0.55);
  }

  /**
   * Where to view a structure from. Flying straight in along the current
   * direction leaves a molar hidden behind the premolars in front of it, since
   * the arch curves away from a frontal viewpoint. Approaching from outside the
   * arch — buccally — puts the camera where the tooth is actually exposed:
   * near-frontal for incisors, near-lateral for molars, and a natural
   * three-quarter view for everything between.
   */
  function approachFor(focus) {
    const outward = new THREE.Vector3(focus.x, 0, focus.z);
    if (outward.lengthSq() < 1e-6) outward.set(0, 0, 1); // dead centre: face it
    outward.normalize();
    return outward
      .add(new THREE.Vector3(0, 0, 0.32))  // bias forward, avoiding a flat profile
      .add(new THREE.Vector3(0, 0.22, 0))  // and slightly above the occlusal plane
      .normalize();
  }

  let hovered = null;
  function setHover(fma) {
    if (hovered && hovered !== selected) tint(hovered, null);
    hovered = fma;
    if (fma && fma !== selected) tint(fma, HOVER_TINT);
  }

  function select(fma, { fly = false } = {}) {
    if (selected) tint(selected, null);
    selected = fma && structures[fma] ? fma : null;

    if (selected) {
      tint(selected, SELECT_TINT);
      detail.show(structures[selected]);
      if (fly) {
        const mesh = meshes.get(selected);
        const box = new THREE.Box3().setFromObject(mesh);
        const size = box.getSize(new THREE.Vector3()).length();
        const focus = box.getCenter(new THREE.Vector3());
        view.flyTo(focus, Math.max(size * 4.2, 70), approachFor(focus));
      }
    } else {
      detail.clear();
      if (isolated) { isolated = false; $('#isolate').classList.remove('is-active'); }
    }

    // Selecting a tooth aims the tube at it, so the radiograph follows what the
    // user is already looking at rather than needing its own picker. Anything
    // that is not a tooth leaves the exposure alone -- re-aiming at the mandible
    // because someone clicked bone would be worse than doing nothing.
    if (selected) {
      // Resolve through the PARENT TOOTH. On a crowded arch the enamel cap is
      // often the only thing a pointer can reach -- it clads the crown, so it is
      // what is in front -- and clicking it must aim the tube at its tooth
      // rather than doing nothing. Same for pulp, ligament, lamina and crowns.
      const s = structures[selected];
      const owner = s?.tooth ?? selected;
      const u = Number(structures[owner]?.universal);
      if (Number.isFinite(u)) {
        radiograph?.setTooth(u);
        // Selecting a tooth puts the exposure on its ideal, so the button that
        // says so has to light with it.
        syncTechniqueSafe();
      }
    }
    chart?.setSelected(selected);
    $('#isolate').disabled = !selected;
    applyAll();
  }

  createPicking(canvas, view.camera, view.root, {
    onHover: setHover,
    onSelect: (fma) => select(fma),
  });

  // --- panels --------------------------------------------------------------
  createLayerPanel($('#layers'), layers, {
    onVisibility: (key, visible) => { layerState[key].visible = visible; applyLayer(key); },
    onOpacity: (key, opacity) => { layerState[key].opacity = opacity; applyLayer(key); },
  });

  chart = createOdontogram($('#chart'), structures, {
    onSelect: (fma) => select(fma, { fly: true }),
  });

  createNotationPicker($('#notation'), { onChange: (n) => chart.setNotation(n) });

  $('#isolate').addEventListener('click', () => {
    if (!selected) return;
    isolated = !isolated;
    $('#isolate').classList.toggle('is-active', isolated);
    applyAll();
  });

  $('#reset').addEventListener('click', () => {
    isolated = false;
    $('#isolate').classList.remove('is-active');
    select(null);
    view.resetView();
  });

  applyAll();

  // ?xray=1 opens straight into radiograph mode, so a specific exposure is
  // linkable. It runs HERE, at the end, and not beside the rest of the
  // radiograph wiring: setXray reads the current selection, and `selected` is
  // declared further down, so calling it early threw a temporal-dead-zone
  // ReferenceError that aborted the rest of main() -- the panel opened with its
  // static markup intact and looked merely wrong rather than broken.
  // ?select=<FMA> deep-links a structure, and pairs with ?xray=1 to link a
  // whole exposure. Applied BEFORE the mode opens so it arrives already aimed.
  const params = new URLSearchParams(location.search);
  const wanted = params.get('select');
  if (wanted && structures[wanted]) select(wanted, { fly: true });
  if (params.get('xray') === '1') setXray(true);

  // Dev-only handle so the scene can be inspected from the console or a
  // DevTools-Protocol driver. Stripped from production builds.
  if (import.meta.env.DEV) Object.assign(window, { __view: view, __meshes: meshes, __structures: structures,
                                          __select: select, __radiograph: radiograph });
}

main().catch((err) => {
  console.error(err);
  const status = document.querySelector('#status');
  if (status) status.textContent = `Failed to load: ${err.message}`;
});
