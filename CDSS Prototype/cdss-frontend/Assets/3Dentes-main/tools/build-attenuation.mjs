#!/usr/bin/env node
// Emit public/attenuation.json — mu(E) per tissue over the diagnostic range.
//
//   node tools/build-attenuation.mjs
//
// The app reads this instead of carrying NIST's tables or the mixture rule into
// the browser. It ships ENERGY-RESOLVED mu, not one baked coefficient, so kVp
// stays a control the user can turn -- which is the whole reason tissues.mjs
// stores composition and density rather than a single number.

import { writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildTable, effectiveKeV } from './attenuation.mjs';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const OUT = join(ROOT, 'public', 'attenuation.json');

const table = buildTable();
await writeFile(OUT, JSON.stringify(table));

const bytes = JSON.stringify(table).length;
console.log(`tissues         ${Object.keys(table.tissues).length}`);
console.log(`energies        ${table.energies_keV.length} `
          + `(${table.energies_keV[0]}-${table.energies_keV.at(-1)} keV)`);
console.log(`wrote           ${OUT}  (${(bytes / 1024).toFixed(1)} kB)`);

// A readable summary, because a JSON blob of coefficients is unreviewable and
// the ordering below is something a clinician can check at a glance.
const at = (kvp) => {
  const keV = effectiveKeV(kvp);
  const i = table.energies_keV.findIndex((e) => e >= keV);
  return { keV, i };
};
const cols = [60, 70, 85].map(at);
console.log(`\nmu (per mm) at the effective energy of each tube potential`);
console.log(`${''.padEnd(16)}${'rho'.padStart(7)}`
  + cols.map((c, j) => `${[60, 70, 85][j]} kVp`.padStart(11)).join(''));
console.log(`${''.padEnd(16)}${''.padStart(7)}`
  + cols.map((c) => `${c.keV.toFixed(0)} keV`.padStart(11)).join(''));
for (const [name, t] of Object.entries(table.tissues)) {
  console.log(name.padEnd(16) + t.density_g_cm3.toFixed(3).padStart(7)
    + cols.map((c) => t.mu_per_mm[c.i].toFixed(4).padStart(11)).join(''));
}
