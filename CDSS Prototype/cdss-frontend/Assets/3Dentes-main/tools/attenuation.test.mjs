// Does the mixture rule reproduce NIST's own compound tables?
//
//   node tools/attenuation.test.mjs
//
// This is the check that stands between a plausible density model and a wrong
// one. Every tissue in tissues.mjs is built by summing elemental mu/rho over
// mass fractions; NIST separately publishes mu/rho for several of those exact
// materials as compounds. Building them from elements and comparing against
// NIST's own answer tests the rule, the interpolation, the edge handling and
// the composition parsing in one shot -- and none of it can be tuned to pass,
// because both sides came off the same website untouched.
//
// The repo has been bitten five times by metrics that could not see the defect
// they were measuring (CLAUDE.md 120). This one has an external answer key.

import assert from 'node:assert';
import { NIST, massAttenuation, interpolate, resolve, muPerMm, effectiveKeV }
  from './attenuation.mjs';
import { TISSUES, COMPONENTS, fromFormula } from './tissues.mjs';

let checks = 0;
const ok = (name) => { checks++; console.log(`  ok  ${name}`); };

// --- 1. the mixture rule against NIST's published compounds ------------------
//
// Two SEPARATE tolerances, because they test two different things and lumping
// them together would hide the one that matters.
//
// ON NIST'S OWN ENERGY GRID neither side interpolates: the elements and the
// compound are tabulated at the same energies, so agreement tests the mixture
// rule, the composition parsing and the arithmetic, and nothing else. That is
// held to 0.1%, and it lands at ~0.03%.
//
// BETWEEN grid points my side interpolates log-log over a coarse grid, and
// around 25 keV -- where mu/rho falls steeply -- the residual reaches ~0.7%.
// That is a property of the grid, NOT a modelling error, which the on-grid
// figure proves. It is bounded at 1% so a real regression still trips it.
//
// Neither number can be tuned to pass: both sides came off NIST untouched.
const TOL_ON_GRID = 0.001;
const TOL_INTERPOLATED = 0.01;
let worstOn = { rel: 0 }, worstOff = { rel: 0 };

for (const [name, m] of Object.entries(NIST.materials)) {
  if (!m.reference_mu_over_rho_cm2_g) continue;

  m.reference_energy_MeV.forEach((eMeV, i) => {
    const keV = eMeV * 1000;
    if (keV < 10 || keV > 120) return;
    const mine = massAttenuation(m.composition_by_weight, keV);
    const theirs = m.reference_mu_over_rho_cm2_g[i];
    const rel = Math.abs(mine - theirs) / theirs;
    if (rel > worstOn.rel) worstOn = { rel, name, keV };
    assert.ok(rel < TOL_ON_GRID,
      `${name} at ${keV.toFixed(1)} keV (on grid): mixture rule ${mine.toFixed(5)} `
      + `vs NIST ${theirs.toFixed(5)} (${(rel * 100).toFixed(3)}%)`);
  });

  for (let keV = 10; keV <= 120; keV += 1) {
    const mine = massAttenuation(m.composition_by_weight, keV);
    const theirs = interpolate(m.reference_energy_MeV,
                               m.reference_mu_over_rho_cm2_g, keV);
    const rel = Math.abs(mine - theirs) / theirs;
    if (rel > worstOff.rel) worstOff = { rel, name, keV };
    assert.ok(rel < TOL_INTERPOLATED,
      `${name} at ${keV} keV (interpolated): ${mine.toFixed(5)} vs `
      + `${theirs.toFixed(5)} (${(rel * 100).toFixed(2)}%)`);
  }
  ok(`${name} reproduced from elements, 10-120 keV`);
}
console.log(`      worst on-grid      ${(worstOn.rel * 100).toFixed(3)}% `
          + `(${worstOn.name} at ${worstOn.keV.toFixed(0)} keV)`);
console.log(`      worst interpolated ${(worstOff.rel * 100).toFixed(3)}% `
          + `(${worstOff.name} at ${worstOff.keV} keV)`);

// --- 2. stoichiometry --------------------------------------------------------
for (const [name, c] of Object.entries(COMPONENTS)) {
  const sum = Object.values(c.composition).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sum - 1) < 1e-9, `${name} mass fractions sum to ${sum}`);
}
// Hydroxyapatite is 39.89% calcium by weight. If this moves, the formula or an
// atomic weight was edited, and every mineralised tissue moved with it.
assert.ok(Math.abs(COMPONENTS.hydroxyapatite.composition[20] - 0.39894) < 1e-4,
  'hydroxyapatite calcium fraction');
ok('component stoichiometry sums to 1 and Ca fraction holds');

// --- 3. every tissue resolves, and to something physical --------------------
for (const name of Object.keys(TISSUES)) {
  const { composition, density_g_cm3 } = resolve(name);
  const sum = Object.values(composition).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sum - 1) < 5e-3, `${name} composition sums to ${sum}`);
  assert.ok(density_g_cm3 > 0, `${name} density`);
  assert.ok(muPerMm(name, 30) > 0, `${name} mu`);
}
ok(`all ${Object.keys(TISSUES).length} tissues resolve to a composition and a density`);

// --- 4. the ordering a radiograph actually shows -----------------------------
//
// Not a tautology: these come from independent compositions and densities, and
// getting one inverted would make an image that looks plausible until a
// clinician reads it. The operator's own PA shows exactly this ordering.
const E = effectiveKeV(65);
const mu = Object.fromEntries(Object.keys(TISSUES).map((t) => [t, muPerMm(t, E)]));
const order = ['air', 'pulp', 'trabecularBone', 'corticalBone', 'cementum',
               'dentin', 'enamel', 'zirconia'];
for (let i = 1; i < order.length; i++) {
  assert.ok(mu[order[i]] > mu[order[i - 1]],
    `${order[i]} (${mu[order[i]].toFixed(4)}) should attenuate more than `
    + `${order[i - 1]} (${mu[order[i - 1]].toFixed(4)})`);
}
assert.ok(mu.pulp === mu.pdl, 'pulp and pdl share the soft-tissue model');
ok('attenuation ordering air < pulp < trabecular < cortical < cementum < dentin < enamel < zirconia');

// Enamel must out-attenuate dentin by enough to SEE. Below about 1.3x the DEJ
// stops being visible and the geometry DRR loses the one thing it should beat
// the volume at.
const ratio = mu.enamel / mu.dentin;
assert.ok(ratio > 1.3 && ratio < 2.5, `enamel:dentin ratio ${ratio.toFixed(3)}`);
ok(`enamel attenuates ${ratio.toFixed(2)}x dentin`);

// --- 5. the zirconium K edge survived the pipeline --------------------------
//
// Zr's K edge is at 17.998 keV, INSIDE the diagnostic range. If the fetcher
// dropped the duplicated energy rows or the interpolation smoothed across them,
// this step disappears and the crowns on 19 and 30 are quietly wrong.
const below = muPerMm('zirconia', 17.5);
const above = muPerMm('zirconia', 18.5);
assert.ok(above / below > 3,
  `zirconium K edge: ${below.toFixed(2)} -> ${above.toFixed(2)} /mm `
  + `(x${(above / below).toFixed(2)}), expected a jump over 3x`);
ok(`zirconium K edge intact: x${(above / below).toFixed(1)} across 18 keV`);

console.log(`\n${checks} checks passed`);
