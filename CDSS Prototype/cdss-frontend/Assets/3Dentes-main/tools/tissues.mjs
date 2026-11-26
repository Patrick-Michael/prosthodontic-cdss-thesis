// Tissue composition and physical density — the substrate the DRR integrates.
//
// Phase 1 of docs/drr-plan.md. Every tissue here stores WHAT IT IS MADE OF and
// HOW DENSE IT IS, never a single attenuation coefficient. That is deliberate
// and docs/wishlist.md is explicit about why: mu is energy-dependent, so a
// bitewing at 60 kVp and a pan at 70 kVp attenuate the same enamel differently.
// Baking one mu in now would make kVp unsimulatable later, and kVp is itself
// worth teaching. attenuation.mjs turns these into mu(E) against NIST data.
//
// THE VOLUME CANNOT SUPPLY ANY OF THIS. It is not calibrated HU and it
// saturates at 3072 (CLAUDE.md 126), which is why the crowned molars are pegged
// and why density here comes from the literature by necessity, not preference.

// IUPAC standard atomic weights. Only the elements that occur above trace level
// in dental tissue or in 3Y-TZP.
export const ATOMIC_WEIGHT = {
  1: 1.008, 6: 12.011, 7: 14.007, 8: 15.999, 11: 22.990, 12: 24.305,
  15: 30.974, 16: 32.06, 17: 35.45, 19: 39.098, 20: 40.078,
  39: 88.906, 40: 91.224,
};

/**
 * Mass fractions from a stoichiometric formula given as {Z: atom count}.
 * Exact chemistry, so anything built this way needs no literature citation
 * beyond the formula itself.
 */
export function fromFormula(atoms) {
  const mass = {};
  let total = 0;
  for (const [z, n] of Object.entries(atoms)) {
    mass[z] = ATOMIC_WEIGHT[z] * n;
    total += mass[z];
  }
  return Object.fromEntries(Object.entries(mass).map(([z, m]) => [z, m / total]));
}

/** Combine components given as [{composition, weight}] into one mass-fraction map. */
export function blend(parts) {
  const out = {};
  let total = 0;
  for (const { composition, weight } of parts) {
    total += weight;
    for (const [z, f] of Object.entries(composition)) {
      out[z] = (out[z] || 0) + f * weight;
    }
  }
  return Object.fromEntries(Object.entries(out).map(([z, f]) => [z, f / total]));
}

export const SRC = {
  nist:
    'Hubbell J.H. & Seltzer S.M., NIST X-Ray Mass Attenuation Coefficients (NISTIR 5632) — elemental mu/rho and the ICRU-44 tissue compositions',
  icru44:
    'ICRU Report 44, Tissue Substitutes in Radiation Dosimetry and Measurement — cortical bone, soft tissue and adipose compositions, via NIST table 2',
  // Cited for the MINERAL / ORGANIC / WATER split by weight, which is the
  // number that actually drives attenuation here. Not cited for an elemental
  // assay, because that is not what it is being used for.
  tenCate:
    "Nanci A., Ten Cate's Oral Histology, 9th ed. — enamel, dentin and cementum as mineral / organic / water by weight, and their physical densities",
  // 3 mol% yttria-stabilised tetragonal zirconia, the standard dental grade.
  ytzp:
    'ISO 13356 / manufacturer data for 3 mol% yttria-stabilised tetragonal zirconia polycrystal (3Y-TZP), the dental full-contour crown material — 6.05 g/cm3',
};

// --- components -------------------------------------------------------------
//
// Hydroxyapatite is exact stoichiometry. The NON-MINERAL fraction of enamel,
// dentin and cementum is stood in for by ICRU-44 SOFT TISSUE rather than by a
// separate collagen and water model.
//
// That approximation is deliberate and worth stating plainly: at diagnostic
// energies the mineral fraction dominates mu almost entirely, because Ca (Z=20)
// and P (Z=15) drive photoelectric absorption and the organic remainder is
// low-Z either way. Splitting collagen from water inside that remainder would
// change the answer far less than the mineral weight fraction does, and would
// need an elemental collagen assay I do not have. So the error is bounded and
// it lives in the small term.
export const COMPONENTS = {
  hydroxyapatite: {
    label: 'Hydroxyapatite, Ca10(PO4)6(OH)2',
    composition: fromFormula({ 20: 10, 15: 6, 8: 26, 1: 2 }),
    source: 'stoichiometry',
  },
  zirconia3Y: {
    // 97 mol% ZrO2 + 3 mol% Y2O3, counted as 97 ZrO2 and 3 Y2O3 formula units.
    label: '3Y-TZP zirconia, 97 ZrO2 + 3 Y2O3',
    composition: fromFormula({ 40: 97, 39: 6, 8: 97 * 2 + 3 * 3 }),
    source: 'stoichiometry',
  },
};

// Filled from tools/xray-mass-attenuation.json at load, so ICRU-44 compositions
// are never retyped here. NAMES MUST MATCH NIST TABLE 2 EXACTLY.
export const NIST_MATERIALS = {
  softTissue: 'Tissue, Soft (ICRU-44)',
  corticalBone: 'Bone, Cortical (ICRU-44)',
  marrow: 'Adipose Tissue (ICRU-44)',
  air: 'Air, Dry (near sea level)',
  water: 'Water, Liquid',
};

// --- tissues ----------------------------------------------------------------
//
// `mineral` is the hydroxyapatite weight fraction; the remainder is the soft
// tissue proxy above. `density_g_cm3` is BULK density, which is a separate
// measurement from composition and does most of the work in mu = (mu/rho)*rho.
export const TISSUES = {
  enamel: {
    label: 'Enamel',
    mineral: 0.96,
    density_g_cm3: 2.95,
    tier: 'derived',
    sources: ['tenCate', 'nist'],
    note: 'The most mineralised tissue in the body, and the reason a crown reads brighter than the root on any radiograph.',
  },
  dentin: {
    label: 'Dentin',
    mineral: 0.70,
    density_g_cm3: 2.14,
    tier: 'derived',
    sources: ['tenCate', 'nist'],
    note: 'The bulk of the tooth. The enamel-dentin contrast this produces is the single feature the geometry DRR should render BETTER than the volume, where partial-volume averaging at 0.16 mm softens it.',
  },
  cementum: {
    label: 'Cementum',
    mineral: 0.65,
    density_g_cm3: 2.03,
    tier: 'derived',
    sources: ['tenCate', 'nist'],
    note: 'Defined for completeness and NOT rendered in v1: 20-50 um at the CEJ is far below the 0.16 mm voxel, and it is barely denser than dentin, so it is radiographically indistinguishable from the dentin beneath it.',
  },
  pulp: {
    label: 'Pulp',
    nist: 'softTissue',
    density_g_cm3: 1.05,
    tier: 'derived',
    sources: ['icru44', 'nist'],
    note: 'Soft tissue in a mineral shell, so it reads as a radiolucency defined by what surrounds it rather than by its own attenuation.',
  },
  pdl: {
    label: 'Periodontal ligament',
    nist: 'softTissue',
    density_g_cm3: 1.05,
    tier: 'derived',
    sources: ['icru44', 'nist'],
    note: "The thin radiolucent line around every root on the operator's own PA. Collagenous rather than generic soft tissue, but at diagnostic energies the difference is far below what the geometry error contributes.",
  },
  gingiva: {
    label: 'Gingiva',
    nist: 'softTissue',
    density_g_cm3: 1.05,
    tier: 'derived',
    sources: ['icru44', 'nist'],
    note: 'Barely visible on an intraoral radiograph; included so a soft-tissue profile exists where the beam clips the arch.',
  },
  corticalBone: {
    label: 'Cortical bone',
    nist: 'corticalBone',
    density_g_cm3: 1.92,
    tier: 'derived',
    sources: ['icru44', 'nist'],
    note: 'Used for the cortical plates and for the lamina dura, which is the bright socket wall outlining each root.',
  },
  trabecularBone: {
    label: 'Trabecular bone',
    // Cortical bone struts with fatty marrow between them, mixed BY VOLUME.
    // The atlas has no trabecular geometry -- the mandible is one solid mesh --
    // so this is a bulk stand-in for a structure the model does not resolve.
    marrowMix: { boneVolumeFraction: 0.25 },
    tier: 'derived',
    sources: ['icru44', 'nist'],
    note: 'THE TUNABLE ONE. boneVolumeFraction is not measured from this patient; it is the parameter to fit against the operator\'s own PA in Phase 5. Note also that no trabecular PATTERN exists in the geometry model, only this bulk average — see the known gaps in docs/drr-plan.md.',
  },
  zirconia: {
    label: 'Zirconia (3Y-TZP)',
    component: 'zirconia3Y',
    density_g_cm3: 6.05,
    tier: 'schematic',
    sources: ['ytzp'],
    note: 'The crowns on 19 and 30. THIS SCAN CANNOT MEASURE THEIR DENSITY: the volume saturates at 3072 and 14-18% of each crowned molar is pegged there (CLAUDE.md 126), so 2500 HU locates the restoration cleanly and says nothing about how dense it is. The figure is the material\'s, from the literature — which is why this is the one tissue here tiered `schematic` rather than `derived`.',
  },
  air: {
    label: 'Air',
    nist: 'air',
    density_g_cm3: 1.205e-3,
    tier: 'derived',
    sources: ['nist'],
    note: 'The background, and the reason an unexposed corner reads black.',
  },
};
