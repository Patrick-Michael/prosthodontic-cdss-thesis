const NOTATIONS = [
  ['universal', 'Universal'],
  ['fdi', 'FDI'],
  ['palmer', 'Palmer'],
];

const TITLE_CASE = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// Provenance text is authored prose, not markup, and it contains apostrophes and
// quotation marks. Escape it rather than trusting it into innerHTML.
const escapeHtml = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/**
 * How the layer list is grouped and ordered in the panel.
 *
 * PRESENTATION, so it lives here rather than in the manifest: the manifest says
 * what a layer IS, this says where a reader expects to find it. Grouped by what
 * the structure is made of, and ordered within each group from the outside in,
 * which is the order someone peels an atlas apart.
 *
 * ANY LAYER NOT LISTED STILL APPEARS, under "Other" at the end. A new layer
 * silently vanishing from the panel because someone forgot to add it here would
 * be far worse than an ugly heading, and the atlas has been bitten by exactly
 * that kind of quiet omission before -- `ramus` and `midface` sat outside the
 * collision set for three releases.
 */
const SECTIONS = [
  { title: 'Teeth', accent: '#e8d9a8',
    keys: ['teeth', 'enamel', 'prosthetic', 'pulp'] },
  { title: 'Attachment', accent: '#e0a8b4',
    keys: ['pdl', 'lamina', 'gingiva'] },
  { title: 'Bone', accent: '#bcd4e6',
    keys: ['mandible', 'maxilla', 'ramus', 'midface'] },
  { title: 'Neurovascular', accent: '#c9b8e8',
    keys: ['nerves', 'vessels'] },
];

/** Layer visibility + opacity controls. */
export function createLayerPanel(root, layers, { onVisibility, onOpacity }) {
  const listed = new Set(SECTIONS.flatMap((s) => s.keys));
  const leftover = Object.keys(layers).filter((k) => !listed.has(k));
  const sections = leftover.length
    ? [...SECTIONS, { title: 'Other', accent: '#9aa4ad', keys: leftover }]
    : SECTIONS;

  for (const section of sections) {
    const keys = section.keys.filter((k) => layers[k]);
    if (!keys.length) continue;
    const head = document.createElement('div');
    head.className = 'layer-section';
    head.textContent = section.title;
    head.style.setProperty('--section-accent', section.accent);
    root.appendChild(head);
    for (const key of keys) renderLayer(root, key, layers[key], onVisibility, onOpacity);
  }
}

function renderLayer(root, key, layer, onVisibility, onOpacity) {
  {
    const row = document.createElement('div');
    row.className = 'layer';

    const toggle = document.createElement('label');
    toggle.className = 'layer-toggle';
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = layer.visible;
    box.addEventListener('change', () => {
      onVisibility(key, box.checked);
      row.classList.toggle('is-off', !box.checked);
    });
    toggle.append(box, Object.assign(document.createElement('span'), { textContent: layer.label }));

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.className = 'layer-opacity';
    slider.min = '0.05';
    slider.max = '1';
    slider.step = '0.05';
    slider.value = String(layer.defaultOpacity);
    slider.title = `${layer.label} opacity`;
    slider.addEventListener('input', () => onOpacity(key, Number(slider.value)));

    row.append(toggle, slider);
    row.classList.toggle('is-off', !layer.visible);
    root.appendChild(row);
  }
}

/** Notation selector — which numbering system the chart and detail panel show. */
export function createNotationPicker(root, { onChange }) {
  for (const [value, label] of NOTATIONS) {
    const btn = document.createElement('button');
    btn.className = 'seg';
    btn.textContent = label;
    btn.classList.toggle('is-active', value === 'universal');
    btn.addEventListener('click', () => {
      for (const b of root.children) b.classList.remove('is-active');
      btn.classList.add('is-active');
      onChange(value);
    });
    root.appendChild(btn);
  }
}

/** Detail panel for the selected structure. */
export function createDetailPanel(root) {
  function empty() {
    root.innerHTML = '<p class="detail-empty">Select a structure in the 3D view or on the chart.</p>';
  }

  function field(label, value) {
    return `<div class="field"><dt>${label}</dt><dd>${value}</dd></div>`;
  }

  empty();

  // Provenance is the answer to "how do you know?", and it belongs on the thing
  // the user just clicked rather than only in a caveat about the build. The
  // whole atlas is one person's anatomy at three very different standings, and
  // measured bone and a textbook nerve course render alike.
  function provenanceBlock(p) {
    if (!p) return '';
    const sources = (p.sources ?? [])
      .map((src) => `<li>${escapeHtml(src)}</li>`)
      .join('');
    return `
      <section class="prov prov-${p.tier}">
        <div class="prov-head">
          <span class="prov-badge">${p.label}</span>
          <span class="prov-blurb">${p.blurb}</span>
        </div>
        <p class="prov-method">${escapeHtml(p.method)}</p>
        ${sources ? `<ul class="prov-sources">${sources}</ul>` : ''}
      </section>`;
  }

  return {
    clear: empty,
    show(s) {
      const rows = [];
      if (s.layer === 'teeth') {
        rows.push(
          field('Universal', s.universal),
          field('FDI', s.fdi),
          field('Palmer', s.palmer),
          field('Arch', TITLE_CASE(s.arch)),
          field('Quadrant', String(s.quadrant)),
        );
      }
      rows.push(field('Side', TITLE_CASE(s.side)));
      rows.push(field('FMA', s.fma.replace('FMA', '')));

      root.innerHTML = `
        <h2 class="detail-name">${s.name}</h2>
        <dl class="detail-fields">${rows.join('')}</dl>
        ${provenanceBlock(s.provenance)}
      `;
    },
  };
}
