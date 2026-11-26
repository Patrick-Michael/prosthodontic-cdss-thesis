// mu(E) per tissue, from composition + density against NIST elemental data.
//
// Phase 1 of docs/drr-plan.md. The mixture rule is
//
//     (mu/rho)_compound(E) = sum_i  w_i * (mu/rho)_i(E)
//
// with w_i the mass fractions. It is exact at these energies because
// attenuation is a per-atom process and chemical binding is negligible above a
// few keV. attenuation.test.mjs checks that claim against NIST's OWN published
// compound tables rather than taking it on trust.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TISSUES, COMPONENTS, NIST_MATERIALS, SRC, blend } from './tissues.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
export const NIST = JSON.parse(
  readFileSync(join(HERE, 'xray-mass-attenuation.json'), 'utf8'));

/**
 * Log-log interpolation of a NIST table at `keV`.
 *
 * ABSORPTION EDGES ARE THE WHOLE DIFFICULTY. The tables list an edge energy
 * TWICE, once either side of a jump, and zirconium's K edge at 17.998 keV is
 * inside the diagnostic range. Picking the LAST zero-width-free bracket puts a
 * query above the edge on the upper branch, which is the physically right
 * answer; taking the first would read the crown's attenuation off the wrong
 * side of a factor-of-four step.
 */
export function interpolate(energiesMeV, values, keV) {
  const E = keV / 1000;
  const n = energiesMeV.length;
  if (E <= energiesMeV[0]) return values[0];
  if (E >= energiesMeV[n - 1]) return values[n - 1];
  let lo = -1;
  for (let i = 0; i < n - 1; i++) {
    if (energiesMeV[i] <= E && E <= energiesMeV[i + 1]
        && energiesMeV[i + 1] > energiesMeV[i]) lo = i;
  }
  if (lo < 0) return values[0];
  const [e0, e1] = [energiesMeV[lo], energiesMeV[lo + 1]];
  const [v0, v1] = [values[lo], values[lo + 1]];
  const t = (Math.log(E) - Math.log(e0)) / (Math.log(e1) - Math.log(e0));
  return Math.exp(Math.log(v0) + t * (Math.log(v1) - Math.log(v0)));
}

/** (mu/rho) in cm2/g for a {Z: massFraction} composition at `keV`. */
export function massAttenuation(composition, keV) {
  let sum = 0;
  for (const [z, w] of Object.entries(composition)) {
    const el = NIST.elements[String(z)];
    if (!el) throw new Error(`no NIST data for Z=${z}; add it to fetch_xray_data.py`);
    sum += w * interpolate(el.energy_MeV, el.mu_over_rho_cm2_g, keV);
  }
  return sum;
}

/**
 * A tissue spec -> {composition, density_g_cm3}. Four ways a tissue is built,
 * and each says where its numbers came from:
 *   nist        an ICRU-44 material used whole
 *   component   exact stoichiometry
 *   mineral     hydroxyapatite + soft-tissue remainder, by weight
 *   marrowMix   cortical bone + fatty marrow, by VOLUME
 */
export function resolve(name) {
  const t = TISSUES[name];
  if (!t) throw new Error(`unknown tissue ${name}`);
  const nistComp = (key) => {
    const m = NIST.materials[NIST_MATERIALS[key]];
    if (!m) throw new Error(`NIST material missing: ${NIST_MATERIALS[key]}`);
    return m;
  };

  if (t.nist) {
    return { composition: nistComp(t.nist).composition_by_weight,
             density_g_cm3: t.density_g_cm3 };
  }
  if (t.component) {
    return { composition: COMPONENTS[t.component].composition,
             density_g_cm3: t.density_g_cm3 };
  }
  if (t.mineral !== undefined) {
    return {
      composition: blend([
        { composition: COMPONENTS.hydroxyapatite.composition, weight: t.mineral },
        { composition: nistComp('softTissue').composition_by_weight,
          weight: 1 - t.mineral },
      ]),
      density_g_cm3: t.density_g_cm3,
    };
  }
  if (t.marrowMix) {
    const f = t.marrowMix.boneVolumeFraction;
    const bone = nistComp('corticalBone');
    const marrow = nistComp('marrow');
    // Mix by VOLUME, so each part contributes mass = fraction * its own density.
    const mb = f * bone.density_g_cm3;
    const mm = (1 - f) * marrow.density_g_cm3;
    return {
      composition: blend([
        { composition: bone.composition_by_weight, weight: mb },
        { composition: marrow.composition_by_weight, weight: mm },
      ]),
      density_g_cm3: mb + mm,
    };
  }
  throw new Error(`tissue ${name} says nothing about what it is made of`);
}

/**
 * Effective monoenergetic energy for a tube potential.
 *
 * A RULE OF THUMB, AND FLAGGED AS ONE. A real beam is polyenergetic and hardens
 * as it goes, which this single number cannot express; beam hardening is on the
 * known-gaps list in docs/drr-plan.md. Roughly a third to a half of the peak is
 * the standard approximation for a filtered diagnostic beam, and 0.40 sits in
 * that band. The CBCT itself was taken at 85 kVp (nrrd/volumes.json), and a
 * dental periapical is usually 60-70.
 */
export const EFFECTIVE_FRACTION = 0.40;
export const effectiveKeV = (kvp) => kvp * EFFECTIVE_FRACTION;

/** mu in per-mm for one tissue at one energy. */
export function muPerMm(name, keV) {
  const { composition, density_g_cm3 } = resolve(name);
  return massAttenuation(composition, keV) * density_g_cm3 / 10;  // cm-1 -> mm-1
}

/** The shipped table: every tissue over the diagnostic range. */
export function buildTable({ from = 5, to = 120, step = 1 } = {}) {
  const energies = [];
  for (let e = from; e <= to; e += step) energies.push(e);
  const tissues = {};
  for (const [name, t] of Object.entries(TISSUES)) {
    const { composition, density_g_cm3 } = resolve(name);
    tissues[name] = {
      label: t.label,
      tier: t.tier,
      note: t.note,
      sources: t.sources.map((s) => SRC[s]),
      density_g_cm3,
      composition_by_weight: composition,
      mu_over_rho_cm2_g: energies.map((e) => massAttenuation(composition, e)),
      mu_per_mm: energies.map(
        (e) => massAttenuation(composition, e) * density_g_cm3 / 10),
    };
  }
  return {
    generated: new Date().toISOString().slice(0, 10),
    source: NIST.source,
    model: 'mu(E) = (mu/rho)(E) * rho, mixture rule over mass fractions. '
         + 'Monoenergetic: no beam hardening, no scatter.',
    effective_fraction: EFFECTIVE_FRACTION,
    energies_keV: energies,
    tissues,
  };
}
