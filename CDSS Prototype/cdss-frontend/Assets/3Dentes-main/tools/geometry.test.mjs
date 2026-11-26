#!/usr/bin/env node
// THE GEOMETRY INVARIANTS THE DRR DEPENDS ON.
//
//   node tools/geometry.test.mjs
//
// A digitally reconstructed radiograph integrates path length through each
// structure as (sum of back-face depths - sum of front-face depths). That is
// exact and very cheap, but it asks two things of a mesh that rendering it in
// the 3D view never did:
//
//   CLOSED   every ray that enters a solid must also leave it. A hole lets a
//            ray in and never out, and the tissue behind it integrates to a
//            nonsense depth -- often negative.
//   OUTWARD  an inward-wound solid SUBTRACTS itself from the image instead of
//            adding to it, and looks like a hole in the anatomy rather than
//            like an error.
//
// Neither is visible in the 3D view. Double-sided materials render an inverted
// mesh perfectly happily, which is exactly how 30 of 150 shipped inward-facing
// for four releases without anyone noticing. This check is the reason that
// cannot happen quietly again.

import assert from 'node:assert';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { STRUCTURES, STL_DIR as STL_SUBDIR } from './manifest.mjs';
import { parseBinarySTL, weldExact, boundaryEdges, signedVolume, topology } from './geometry.mjs';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const STL_DIR = join(ROOT, ...STL_SUBDIR);

// EMPTY, AND IT SHOULD STAY EMPTY. The 27 open PDL shells were closed on
// 2026-09-05: pdl.py now meshes each tooth's own mask with a 2-voxel pad
// instead of cutting per-tooth pieces out of a whole-arch mesh, and a face
// subset of a closed surface is open along every cut.
//
// Anything appearing here is a defect in whatever generated it, not a licence
// to add an entry. If you are about to add one, read CLAUDE.md 203 first: a
// mask that reaches its crop wall meshes open and NOTHING PRINTS -- triangle
// and component counts both look normal.
const OPEN_EXPECTED = {};

const open = {};
const inverted = [];
let checked = 0;

for (const s of STRUCTURES) {
  const soup = parseBinarySTL(await readFile(join(STL_DIR, `${s.fma}.stl`)));
  const { positions, indices } = weldExact(soup);
  checked++;
  const holes = boundaryEdges(indices);
  if (holes > 0) {
    open[s.layer] = (open[s.layer] || 0) + 1;
    continue;                     // signed volume is meaningless on an open surface
  }
  if (signedVolume(positions, indices) < 0) inverted.push(`${s.fma} (${s.layer})`);
}

// 1. Openness is exactly what we expect — no more, and no fewer.
assert.deepStrictEqual(open, OPEN_EXPECTED,
  `open surfaces changed.\n  found:    ${JSON.stringify(open)}\n`
  + `  expected: ${JSON.stringify(OPEN_EXPECTED)}\n`
  + '  If a layer was CLOSED, delete it from OPEN_EXPECTED — that is progress.\n'
  + '  If a layer became OPEN, whatever generated it has a defect; see\n'
  + '  CLAUDE.md 203 on masks that reach their crop wall and mesh open.');
console.log(`  ok  ${checked} structures checked; open surfaces are exactly `
  + `${JSON.stringify(OPEN_EXPECTED)}`);

// 2. Nothing inward-wound survives into the source assets unnoticed.
//
// The BUILD reorients these, so this is not a build failure — it is a report
// that the STLs themselves still disagree, and a guard that the build's fix is
// still needed and still working. It asserts only that we KNOW the count.
console.log(`  ok  ${inverted.length} closed meshes are wound inward in the STLs `
  + '(the asset build reorients these)');

// 3. Everything the DRR will actually integrate is closed.
//
// The tissues that carry attenuation: teeth, enamel, pulp, bone. If any of
// these opens, the radiograph is wrong in a way no display curve reveals.
const INTEGRATED = new Set(['teeth', 'enamel', 'pulp', 'mandible', 'maxilla',
                            'midface', 'ramus']);
const badly = [];
for (const s of STRUCTURES) {
  if (!INTEGRATED.has(s.layer)) continue;
  const { indices } = weldExact(parseBinarySTL(await readFile(join(STL_DIR, `${s.fma}.stl`))));
  if (boundaryEdges(indices) > 0) badly.push(`${s.fma} (${s.layer})`);
}
assert.deepStrictEqual(badly, [],
  `these carry attenuation and MUST be closed: ${badly.join(', ')}`);
console.log(`  ok  every attenuating structure (${[...INTEGRATED].join(', ')}) is closed`);

// 4. A crown is a simple solid, so its mesh must be ONE SPHERE.
//
// `boundaryEdges` cannot make this claim: a torus is as closed as a sphere, so
// a tunnel straight through a cusp passes every other check in this file. That
// is exactly what happened -- the crown on 19 shipped GENUS 1 and the operator
// found it by looking, after it had passed closedness, winding and volume.
//
// Asserted for the PROSTHETIC layer only, and deliberately not in general:
// higher genus is legitimate elsewhere. The mandible carries its own canal, and
// a nerve meshed as two branches is two spheres rather than one.
const solids = [];
for (const s of STRUCTURES) {
  if (s.layer !== 'prosthetic') continue;
  const { positions, indices } = weldExact(parseBinarySTL(await readFile(join(STL_DIR, `${s.fma}.stl`))));
  const t = topology(positions, indices);
  if (t.genus !== 0 || t.components !== 1) {
    solids.push(`${s.fma}: genus ${t.genus}, ${t.components} component(s)`);
  }
}
assert.deepStrictEqual(solids, [],
  `a restoration is a simple solid and must mesh as one sphere:\n  ${solids.join('\n  ')}\n`
  + '  A tunnel means the threshold left a gap through the crown. See\n'
  + '  export_prosthetic.py on why the closing is 3 iterations and not 2.');
console.log('  ok  every restoration meshes as a single genus-0 solid');

console.log('\n4 checks passed');
