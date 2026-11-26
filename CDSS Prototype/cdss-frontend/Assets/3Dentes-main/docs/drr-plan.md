# The digitally reconstructed radiograph — plan of record

Work order item 4. Written 2026-09-05, at the start of the work, so that
stopping after any phase leaves a record of what was decided and why rather
than a half-built feature nobody can pick up.

Background and the original design intent are in `wishlist.md` (the DRR section,
"Draggable radiograph simulator", "Pathology menu", and "Enamel, dentin and
cementum"). This document supersedes those on *how*, not on *why*.

Both prerequisites the wishlist named are satisfied: contacts were re-cut
2026-09-02, enamel shipped in 0.7.0 on 2026-09-05.

---

## The decision: labelled geometry, not the voxel volume

Settled by the operator 2026-09-05. The DRR integrates the **closed meshes the
atlas already ships**, each carrying a literature density — not the CBCT volume.

### The evidence that made it possible

Every mesh was edge-tested (weld to 1e-4 mm, count edges used by exactly one
face):

| Kind | Files | With holes | Non-manifold | Boundary edges |
| --- | --- | --- | --- | --- |
| enamel | 26 | **0** | 26 | 0 |
| pulp | 28 | **0** | 13 | 0 |
| other (teeth, bone, nerves, vessels, gingiva) | 68 | **0** | 6 | 0 |
| **pdl** | 28 | **27** | 2 | 1746 |

Non-manifold edges are harmless to ray integration; holes are not. So every
structure that carries a radiographic claim is already closed, and the
wishlist's hope that this "may turn the radiograph simulator from a
volume-shipping problem into a shading problem" is available rather than
aspirational. **Only the PDL needs repair** — and see the PA findings below for
why that is not optional.

### Why not the volume

Measured, so the trade is on the record rather than asserted. Whole `centered`
volume as 8-bit, zlib:

| Resolution | Voxels | Raw | Compressed |
| --- | --- | --- | --- |
| 0.16 mm (native) | 134.2 M | 134 MB | 79.2 MB |
| 0.32 mm | 16.8 M | 16.8 MB | **10.7 MB** |
| 0.48 mm | 5.0 M | 5.0 MB | 3.2 MB |

So a volume DRR is affordable only at 0.32 mm, which discards exactly the
interproximal detail a bitewing exists to show. And the decisive objection is
CLAUDE.md 126, not the byte count: **the volume is not calibrated HU and
saturates at 3072**, where 14-18% of each crowned molar is pegged. A volume DRR
would integrate uncalibrated, clipped intensity and present the result as a
radiograph. Literature densities on labelled geometry can be cited; no amount of
downsampling makes the volume honest.

Storing **composition and physical density**, never a baked µ, is what keeps kVp
a parameter — `wishlist.md` is explicit about this and a pre-integrated volume
cannot do it at all.

### What this costs, stated plainly

No trabecular texture, no sensor noise, no beam hardening, no scatter. See the
PA findings — this is the most conspicuous gap and it is accepted, not hidden.

---

## What the operator's own periapical established

He supplied a real PA of **31, 30 and 29** — same patient, same teeth, same
mouth as the CBCT. Path and how to find it again are in the
`3dentes-operator-periapical` memory. It is the ground truth this work is judged
against, and it corrected two things I had wrong from the data alone:

1. **The PDL is diagnostic, not negligible.** After the crown, the clearest
   features in the image are the thin radiolucent PDL line and the bright
   lamina dura outlining every root. That is what makes a root read as a root.
   The PDL meshes are the one open category, so they must be closed, and the
   **lamina dura does not exist as geometry at all** and has to be built.
2. **Trabeculation is a dominant feature**, filling most of the image below the
   crowns — not a background texture. Homogeneous bone is where our DRR will
   differ most visibly from his radiograph.

Levels, for calibrating a response curve: zirconia ~214 mean at sd 2.8, air ~37,
and **all** dental tissue clustered ~99-145. The crown dominates without blowing
out; structure stays visible beneath it.

**These grey levels are not a physical measurement.** The sensor applies its own
gamma and windowing. They can fit a film-response curve and nothing else, and
that fit must say so in its provenance.

---

## Phases

Numbered so work can stop cleanly at any boundary.

### Phase 0 — the reference image, before any WebGL
Offline Python DRR **through the actual volume**, in the geometry of his PA of
31/30/29. Two purposes: a picture to look at immediately, and the reference
every later phase is checked against. Meshes and the volume share the `centered`
LPS frame exactly (`segment_tooth.mesh` writes world millimetres with no
recentring), so the comparison is pixel-direct and needs no registration.

Note this phase uses the volume *deliberately* — as a reference, where its
uncalibrated intensity is a known limitation rather than a shipped claim.

### Phase 1 — tissue and density model
Composition plus physical density per tissue, cited: enamel, dentin, pulp,
cortical bone, trabecular bone, PDL, zirconia. µ(E) computed at build from mass
attenuation coefficients into a small JSON, so kVp stays a parameter. Fits
beside the manifest's existing `provenance` and `sources`.

### Phase 2 — the missing geometry
- **Prosthetic as its own structure.** Operator's call, 2026-09-05: do it.
  340 mm³ on 19 and 273 mm³ on 30 are already measured by `enamel.py`'s
  `restorations()`; they need meshing, a manifest entry and a literature
  zirconia density. This closes half of open question 6.
- **Close the 27 open PDL meshes.**
- **Lamina dura** as a denser socket-wall shell. New authored geometry —
  `derived`, and it needs its own provenance note, not the PDL's.
- **Emit the build-time centring offset into `teeth.json`.** `build-assets.mjs`
  subtracts a bounding-box centre that it never records, so app space cannot
  currently be mapped back to LPS — which validation needs.
- **Resolve the 30 inverted-winding meshes** (vessels and nerves have negative
  signed volume). Depth accumulation is sign-sensitive.

### Phase 3 — DRR core
Path length through each closed mesh = Σ(back-face depths) − Σ(front-face
depths), accumulated by additive blending into a half-float MRT. **Dentin needs
no CSG**: it is tooth − enamel − pulp − prosthetic, by subtraction of
accumulated depths. Then I = I₀·exp(−Σ µᵢ(E)·Lᵢ) through a response curve fitted
to the PA above.

Signed volumes confirm the subtraction is sane: enamel is 14-31% of each tooth,
and 19 and 30 correctly carry zero.

### Phase 4 — cone beam and receptor
Projection matrix built from a source point plus a receptor quad (generalized
perspective), so foreshortening, elongation and cone cut are consequences of the
geometry rather than authored effects. Paralleling versus bisecting as a mode;
receptor and beam drawn in the 3D view alongside the result.

### Phase 5 — validation
Geometry DRR against the Phase 0 volume DRR against the real PA, same
projection, side by side.

---

## Known gaps, deliberately not in v1

Trabecular texture, sensor noise, beam hardening, scatter, cementum (sub-voxel
and radiographically indistinguishable from dentin). Named here so their absence
is a decision on the record and not an oversight.

## Risk to retire early

Half-float multiple render targets on the operator's phone. If that fails, the
accumulation strategy needs a fallback, so it is worth testing on device
**before** Phase 3 rather than after.

---

## Phase 0 outcome — 2026-09-05

`tools/cbct/drr_volume.py`. Renders a cone-beam DRR through `centered.nrrd` in
the geometry of a named periapical and writes a PNG. Run it with the venv
python, as with every `tools/cbct` script:

    ~/projects/3Dentes-cbct/nnunet-venv/bin/python tools/cbct/drr_volume.py \
        --teeth 31 30 29 --out /tmp/drr.png

**It reproduces the operator's own PA recognisably** — same tooth order, the
zirconia crown bright and uniform, pulp chambers and canals radiolucent,
trabecular bone, crestal bone and the furcations all where his radiograph puts
them. That is Phase 0's whole job: a reference the geometry DRR can be checked
against in Phase 5.

### Three things worth keeping

1. **INTEGRATION MUST STOP AT THE RECEPTOR.** An intraoral sensor is an opaque
   plate: nothing beyond it reaches it. The first version marched the whole
   volume slab, so every ray also collected the CONTRALATERAL mandible on its
   way out and the image washed out to near-white. This is not a windowing
   problem and no display curve fixes it. Each ray now integrates only to its
   own receptor pixel.
2. **Windowing the path integral IS the sensor model.** A sensor records
   transmitted intensity and its software takes the log, which lands back on
   the integral. So a percentile stretch on the accumulated attenuation is
   right, and the exp-then-invert-then-gamma chain tried first is a detour that
   saturates. Dense reads bright, as film does.
3. **Derive the receptor frame from the anatomy, never from world axes.** The
   vertical is the target tooth's own long axis by PCA, the horizontal runs
   along the arch, and buccal is whichever way points away from the arch
   centre. A posterior tooth is tilted lingually, so assuming +z is "up the
   tooth" tilts the whole projection. Framing is also shifted apically by
   default (`--vshift`): a PA is framed crown-at-the-edge to a little past the
   apex, and centring on the tooth's centre of mass catches the opposing arch.

### Where it differs from the real PA, and why

- **Blur.** 0.16 mm CBCT against a sensor resolving perhaps 0.025 mm. Not
  fixable and not worth trying to fix; it is a property of the source data.
- **Weak enamel/dentin contrast.** Clear in his PA with a visible DEJ, much
  softer here — partial-volume averaging at 0.16 mm. Worth noting that the
  GEOMETRY DRR should beat the volume on exactly this point, because enamel is
  an explicit labelled mesh there rather than a density gradient.
- **Magnification and angulation do not match his exposure.** Expected: SRD,
  receptor offset and angulation here are the standard paralleling setup, not
  the ones his exposure happened to use. Phase 5 should fit these to the PA
  before comparing, rather than reading the mismatch as an error.

---

## Phase 1 outcome — 2026-09-05

Five files. `tools/cbct/fetch_xray_data.py` fetches NIST's elemental mass
attenuation coefficients and the ICRU-44 tissue compositions into
`tools/xray-mass-attenuation.json` (committed, ~39 kB, re-runnable).
`tools/tissues.mjs` holds composition and density per tissue,
`tools/attenuation.mjs` the mixture rule, `tools/build-attenuation.mjs` emits
`public/attenuation.json`, and `tools/attenuation.test.mjs` checks the lot.
Wired into `npm test` and `npm run build:assets`.

Nothing here stores a baked µ. The shipped table is µ against energy over
5-120 keV, so **kVp remains a control** rather than a decision already taken.

### The test has an external answer key

This repo has been bitten five times by metrics blind to the defect they were
measuring (CLAUDE.md 120). This test cannot be, because both sides come off NIST
untouched: every tissue is built by summing elemental µ/ρ over mass fractions,
and NIST separately publishes µ/ρ for six of those exact materials as compounds.

**On NIST's own energy grid the worst disagreement over 10-120 keV is 0.048%**,
across water, cortical bone, soft tissue, adipose, muscle and air. Between grid
points it reaches 0.725% at 25 keV, where µ/ρ falls steeply — that is log-log
interpolation on a coarse grid, not a modelling error, and the on-grid figure is
what proves it. The two are asserted separately at 0.1% and 1% so that lumping
them together cannot hide a real regression behind the interpolation residual.

Also checked: hydroxyapatite is 39.894% calcium by weight, every tissue resolves
to a composition summing to 1, and the attenuation ordering runs
air < pulp < trabecular < cortical < cementum < dentin < enamel < zirconia.
That ordering is not a tautology — the values come from independent compositions
and densities, and an inverted pair would produce an image that looks plausible
until a clinician reads it.

**The zirconium K edge survives at 4.2x across 18 keV.** It sits inside the
diagnostic range, so if the fetcher had dropped NIST's duplicated edge rows, or
the interpolation had smoothed across them, the crowns on 19 and 30 would have
been quietly wrong with nothing to show for it.

### µ per mm at the effective energy of each tube potential

| Tissue | ρ (g/cm³) | 60 kVp (24 keV) | 70 kVp (28 keV) | 85 kVp (34 keV) |
| --- | --- | --- | --- | --- |
| enamel | 2.950 | 1.1188 | 0.7264 | 0.4313 |
| dentin | 2.140 | 0.6252 | 0.4092 | 0.2470 |
| cementum | 2.030 | 0.5591 | 0.3667 | 0.2223 |
| cortical bone | 1.920 | 0.4668 | 0.3076 | 0.1881 |
| trabecular bone | 1.192 | 0.1471 | 0.1010 | 0.0666 |
| pulp / PDL / gingiva | 1.050 | 0.0606 | 0.0452 | 0.0342 |
| zirconia (3Y-TZP) | 6.050 | 20.1400 | 13.4174 | 7.9750 |

Enamel out-attenuates dentin by 1.78x and holds that ratio across the range,
which is the DEJ contrast the geometry DRR should render better than the volume.

### Two limitations found by doing the arithmetic

**1. The monoenergetic model makes zirconia infinitely opaque.** Transmission
through 1.5 mm of zirconia at 70 kVp is 1.8e-9 — six orders of magnitude below
a 10 mm dentin path. So the crowns on 19 and 30 will render as flat white
silhouettes with no internal gradation at all. **The operator's own PA does not
look like that**: the crown reads 214 against an image maximum of 229, so there
is real gradation left in it. The cause is the approximation, not the density:
a real beam is polyenergetic and its hard component penetrates, and beam
hardening through a very attenuating material shifts the transmitted spectrum
harder still. A single effective energy cannot express that.

Consequence for Phase 3: **the response curve cannot rescue this**, because the
information is already gone by the time it clips. Either accept a flat crown as
a known artefact, or promote the polyenergetic spectrum from the known-gaps list
into Phase 3. Worth deciding deliberately rather than discovering on screen.

**2. The dynamic range is far wider than any sensor's.** 10 mm of dentin
transmits 0.0167 at 70 kVp while 2 mm of cortical bone transmits 0.5405. The
response curve therefore does most of the visible work, which is the argument
for fitting it to the real PA rather than choosing it by eye.

### Two numbers that are choices, and are flagged as such

- **`EFFECTIVE_FRACTION = 0.40`** in `attenuation.mjs` — the effective energy as
  a fraction of tube potential. A rule of thumb (a third to a half is the usual
  band), named as a constant so Phase 5 can fit it rather than inherit it.
- **`boneVolumeFraction = 0.25`** for trabecular bone. The atlas has no
  trabecular geometry — the mandible is one solid mesh — so this is a bulk
  stand-in, not a measurement from this patient, and it is the parameter to fit
  against the PA in Phase 5.

One approximation is worth restating: the NON-MINERAL fraction of enamel, dentin
and cementum is stood in for by ICRU-44 soft tissue rather than by separate
collagen and water. At diagnostic energies Ca and P dominate µ almost entirely,
so the error is bounded and it sits in the small term — but it IS an
approximation, and it is in the shipped provenance rather than only here.

### Decided 2026-09-05: stay monoenergetic

The operator's call, with the flat-crown consequence above on the table. The
polyenergetic spectrum stays on the known-gaps list. **So the crowns on 19 and
30 rendering as flat white silhouettes is an ACCEPTED ARTEFACT, not a bug** —
whoever meets it next should not go looking for an error in the density model.

---

## Phase 2 outcome — 2026-09-05

All five items done. 150 structures -> 180; the glb goes 13.9 -> 15.5 MB.
`npm test` gains `tools/geometry.test.mjs`, which guards the two invariants the
DRR depends on and which nothing previously checked.

### Every mesh in the atlas is now closed

`marching_cubes` cannot close a surface at the array boundary (CLAUDE.md 203),
but that was NOT why the ligaments were open. `export_soft.py` cut the per-tooth
pieces out of a whole-arch mesh by assigning each FACE to its nearest pulp
centroid, and a face subset of a closed surface is open along every cut. No
amount of padding fixes that; the cut is the cause.

`pdl.py` now meshes each tooth's OWN mask with a 2-voxel pad, so every ligament
is closed by construction, and `export_soft.py` prefers those — falling back to
the old split only for a stale pdl directory, and printing a warning when it
does. The arch outputs are byte-identical to the previous build, so nothing that
already existed moved.

Independent check that the split was not double-counting: the 28 per-tooth
ligament volumes sum to 4169.9 mm³ against a 4253.5 mm³ union — 2.0% BELOW, which
is Taubin shrinkage on a thin shell. Overlap would have pushed it above.

### Every closed mesh is now wound outward

30 of 150 shipped inward-facing — 13 of 15 nerves and 17 of 19 vessels, because
the tube generators wind according to the direction the centreline happens to
run. Double-sided materials render that perfectly happily, which is how it
survived four releases. The DRR could not: path length is accumulated as
back-face depth minus front-face depth, so **an inverted solid subtracts itself
from the image** and reads as a hole in the anatomy rather than as an error.

The asset build now reorients any closed mesh whose signed volume is negative,
and only closed ones — signed volume is meaningless on a surface with holes, so
flipping on that basis would be a coin toss.

### The prosthetic crowns exist as structures

`tools/cbct/export_prosthetic.py`. **344.7 mm³ on 19 and 276.7 mm³ on 30** —
which is exactly what the manifest's own comment already recorded, reached
independently here from the volume. Only the two crowned molars produce a mesh.

Tiered `schematic`, not `measured`, and the tier follows the weaker half:
geometry off the scan, density from the literature, because the volume saturates
at 3072 and cannot measure zirconia (CLAUDE.md 126). The MARGIN is the least
trustworthy part — where the crown thins below a voxel, partial volume drags it
under the threshold, so the outline understates the crown cervically.

**Sub-threshold metal-density voxels are now REPORTED, not dropped silently**
(CLAUDE.md 60). Next to a crown the cause is bloom — 20 beside 19, 29 beside 30.
But **teeth 23 and 24 carry 1.79 and 1.19 mm³ just under the 2 mm³ cut and are
lower incisors nowhere near a crown, which bloom does not explain.** The report
gives the number and does not say what it is. One for the clinician.

### The lamina dura exists

28 meshes, in `pdl.py` beside the ligament that shares its measurement. Position
measured — painted only where the volume holds bone above 600 HU, the same wall
the ligament measurement already walks outward to find — thickness a 0.32 mm
drawing choice, exactly like the ligament's. `derived`.

It is **discontinuous where the scan shows no cortical wall, and that gap is a
finding rather than a defect.** Only the largest connected wall per tooth is
kept, because a threshold on a shell this thin strews specks through the marrow
that would each mesh as their own blob inside the socket.

**It overlaps the mandible and maxilla meshes by construction**, and that is
correct rather than double counting — those are the bulk bone and this is the
cortical part of it. Phase 3 must subtract, exactly as dentin is the tooth less
its enamel and pulp. Volumes 58-156 mm³ per tooth.

### App space can now be mapped back to the scanner

`teeth.json` gains a `frame` block: the Y-up rotation and the bounding-box
centre the build subtracts, as 4x4 row-major matrices both ways, with an exact
round trip. Both were applied to every vertex and NEITHER was recorded, so the
mapping existed only inside `build-assets.mjs` — and Phase 5 cannot compare a
geometry DRR against the volume without it.

### What the sub-threshold voxels are — settled 2026-09-05

The operator: **no restorations anywhere but 19 and 30 — no fillings, no
endodontics, nothing.** So none of the metal-density voxels on the other teeth
are dental work, and two causes separate cleanly:

| | teeth | max HU | position |
| --- | --- | --- | --- |
| **Bloom** | 20, 29 | **saturated at 3072** | beside a crown |
| **Edge overshoot** | 22, 23, 24, 26, 27 | 2621-2871, never saturates | 88-99% of crown-root height, within 0.5 mm of the surface |

The anterior group sits, without exception, at the incisal edges — where a thin
sharp high-contrast boundary drives reconstruction overshoot above the true
value.

**A beam-hardening streak between the two crowns was the first hypothesis and it
is wrong.** The anterior teeth lie 23-28 mm off the 19-30 axis: the mandible
bows forward, so the line between the first molars passes behind the incisors.
Only 20 and 29 are near that axis, at 5.5-5.9 mm, and those are the bloom cases
already accounted for. Measured, not assumed.

**Consequence: `RESTORATION_MIN_MM3` is load-bearing.** Tooth 23's largest blob
is 1.64 mm³ against a 2.0 mm³ cut. The 2600 HU threshold alone does NOT separate
zirconia from incisal enamel — only the connected-blob filter does — and without
it a lower lateral incisor would be meshed a crown it does not have. Anyone
retuning that threshold should re-read this first.

### Three defects the operator saw on screen — fixed 2026-09-05

He looked at the build and found all three in minutes. **Every one was invisible
to the checks written for them**: the meshes were closed, outward-wound,
correctly sized and correctly placed in the manifest. Sixth entry for the
blind-metric list (CLAUDE.md 120).

**1. Ligament INSIDE the pulp chamber.** The real bug. The split labels do not
include the pulp, so the molar masks are hollow — 27.7 mm³ in tooth 18, 18.8 in
31, ~9.5 in 20 and 29. `~tsub` is therefore TRUE inside the chamber, and
dilating the root then subtracting the label painted a ligament down the inside
of the canal.

The mask is now sealed before it is excluded: fill holes, and also fill after a
closing, because a chamber draining through the apical foramen is not an
enclosed cavity and `fill_holes` alone leaves it open. Union with the original
so this can only ever ADD to the tooth.

The fix predicts its own signature, and the prediction held: PDL volume should
fall by about the cavity volume on hollow teeth and not otherwise. Tooth 18 lost
26.1 mm³ against a 27.7 mm³ cavity, 31 lost 20.9 against 18.8, and a tooth with
no cavity lost 0.9 — smoothing noise. Near 1:1, so what came off was the
interior shell and nothing else.

**2. Lamina dura "extremely patchy" — now continuous.** It was intersected with
(volume > BONE_HU), which made the position measured and the mesh ragged:
**median 7 disconnected components per tooth, one tooth with 41.** Now a
continuous shell like the ligament — median 1 component, max 3.

**The measurement was not discarded, it moved to the report.**
`lamina_in_bone_frac` in `pdl.json` records what fraction of each wall actually
sits in bone above 600 HU: median 68.8%, lowest on teeth 15, 2 and 30 at 51-54%.
As a number that is a readable finding about a socket; as a hole in a mesh it
just looked like a rendering fault.

**3. Crowns patchy.** A hard threshold on a SATURATING material is not a solid —
the core pegs at 3072 but occlusal grooves, the margin and any porosity dip
under 2600 and punch holes straight through the mesh. Closed and hole-filled,
bounded by the tooth's own label so it cannot grow outwards past the scan:
344.7 -> 358.6 mm³ on 19, 276.7 -> 284.1 on 30.

### The tunnel on 19 — 2026-09-05, and why nothing here caught it

The operator: *"still a tiny hole on the DL cusp aspect of 19"*. Measured, it is
exactly that and nothing else — **the crown on 19 meshed at GENUS 1, one tunnel
through the distolingual cusp. Tooth 30 was genus 0.** One hole, one tooth,
found by eye.

**`boundaryEdges` cannot see this, and no amount of it would have.** A torus is
every bit as closed as a sphere: the mesh had zero boundary edges, correct
winding, a positive volume and a plausible size. **"Closed" and "no holes" are
different claims** and this file had only ever tested the first. Seventh entry
for the blind-metric list.

The bridging voxels sit at **2500-2599 HU** — crown material reading just under
the 2600 cut, not a void. So closing across them restores the crown rather than
inventing it. 3 iterations (0.48 mm) instead of 2 clears it: 19 goes
358.6 -> 364.3 mm³, 30 goes 284.1 -> 286.5, both genus 0.

Lowering the global threshold to 2500 would also have closed it and was
REJECTED: it would promote the anterior incisal-edge overshoot (up to 2871) into
restorations that do not exist. Hysteresis from a 2600 seed was tried too and
grows the crown 10-31% by eating into the 2000-2500 bloom penumbra.

`topology()` is now in `geometry.mjs` and the test asserts **genus 0, one
component, for the prosthetic layer only.** Deliberately not in general — a
survey across all 180 structures shows higher genus is normal and mostly
legitimate: the mandible carries its own canal (chi -67), and a nerve or vessel
meshed as two branches is two spheres (chi 4), not a defect.

**Two things that survey did turn up, unresolved and NOT part of this fix:**
enamel caps run to genus 17 (chi -32 on FMA55703) and pulps to genus 35
(chi -69 on FMA55688). Some of that is real — a pulp with several canals joined
at the chamber genuinely has handles — but not that much of it. Worth a look
before either is quoted as a measured surface.

**Note for Phase 3: genus does not affect DRR correctness.** Path length
accumulates correctly through a closed surface of any genus, because every ray
still enters and leaves. The tunnel mattered because it was VISIBLE, not because
it would have corrupted a radiograph.

---

## Phase 3, part 1 — the geometry DRR, on the CPU (2026-09-05)

`tools/cbct/drr_mesh.py`. **The first radiograph computed from the atlas's own
meshes and literature densities, rather than from the volume.** 146 meshes into
8 tissue channels, 900x641, about 7 seconds.

Built on the CPU FIRST, deliberately. The browser will do this on the GPU, but
the algorithm is identical and this version can be checked against the Phase 0
volume reference and the operator's own PA — so when the shader disagrees with
this, it is the shader that is wrong.

### It works, and the predicted win showed up

**Enamel-dentin contrast is markedly better than the volume DRR**, which is
exactly what Phase 1 predicted: enamel is an explicit labelled mesh with its own
density here, not a partial-volume gradient at 0.16 mm. The DEJ is crisp, the
chambers and canals are sharp, and the PDL space and lamina dura read as the
paired dark and bright lines they are on a real film.

Path lengths are all physical: enamel to 9.6 mm across several crowns, dentin to
10.7, trabecular bone to 15.4.

### Two bugs, one of them a repeat

**1. The receptor is opaque, and I forgot it again.** The first render doubled
every root: meshes BEHIND the sensor were still projecting onto it. This is the
same defect Phase 0 hit in the volume, arriving again in a different substrate —
and the fix is exact rather than approximate. Path length is a difference of
distances, so clamping every intersection distance to the receptor's own
distance gives R - R = 0 for a solid wholly behind it, leaves one wholly in
front untouched, and yields R - d_front for one that straddles. Dentin fell
19.2 -> 10.7 mm and trabecular bone 36.0 -> 15.4 when it went in.

**2. The metal set the window and crushed the anatomy.** The crown reaches an
optical depth of ~128 while every dental tissue sits between 1 and 5, so a
percentile over the whole image is chosen by the zirconia and leaves the teeth
in the bottom few grey levels. The window is now taken over the 94% of pixels
the metal does not touch, and the crown clips — which is what a real sensor does
and what a clinician does at the console. This is the display standing in for
the polyenergetic beam we chose not to model.

### What it confirms about the shipping design

**No MRT is needed, which removes the phone risk this plan flagged.** Each
tissue writes into one CHANNEL of an RGBA target with additive blending, so four
tissues accumulate per target in a single pass over their meshes; seven tissues
need two targets and no multiple-render-target extension at all. A material with
`side: DoubleSide` that emits `gl_FrontFacing ? -d : +d` does the whole signed
accumulation in ONE draw call per mesh.

**Precision needs care in half float, though.** Distances from the source run
250-350 mm, where half float resolves only ~0.25 mm — useless for a 2 mm path.
Depth must be emitted RELATIVE to a plane through the model (view-space z minus
the distance to the centre), keeping values within +/-50 mm where the resolution
is ~0.03 mm, comfortably under the 0.16 mm voxel.

### Honest differences from the real PA, unchanged

No trabeculation — bone is a flat slab, and it remains the most conspicuous
difference. The crowns clip flat, as accepted. The PDL and lamina dura read
MORE strongly than on the real film, because both are drawn at 0.32 mm rather
than their true ~0.2 mm.

**Still to do in Phase 3:** the WebGL port, and the receptor/response fit to the
operator's PA that Phase 5 needs before any of these differences can be called
errors rather than settings.

---

## Phase 3, part 2 — the DRR runs in the browser (2026-09-05)

`src/drr.js` plus a standalone harness at `drr.html` / `src/drr-page.js`, served
at `/3Dentes/drr.html`. Its own page on purpose: the radiograph can be judged
against the CPU reference and the operator's PA without putting the 3D view at
risk while it is still being built. Phase 4 is where it earns a place in the app.

`vite.config.js` now lists both entry points. Without that the page works in dev
and vanishes from the production build, which is the worst way to find out.

### It agrees with the CPU reference

Rendered headless through SwiftShader and compared against
`tools/cbct/drr_mesh.py` at the same settings:

- **Pearson r = 0.9931**, mean absolute difference 7.9 grey levels in 255.
- Auto-window 0.00-6.77 τ over 94% metal-free pixels, against the CPU's
  0.00-6.04 over the same 94%.

Pearson is invariant to brightness and contrast, so r = 0.993 is a STRUCTURAL
match; the residual is the window difference, which comes from the GPU taking
its percentiles on a 1/8-scale grid rather than the full image.

### No MRT, as designed

Each tissue writes one CHANNEL of an RGBA target, four tissues per target, seven
across two targets, one pass each. A `DoubleSide` material emitting
`gl_FrontFacing ? -d : +d` with additive blending does the signed accumulation
in one draw call per mesh — 146 meshes, two passes, no depth sort, no CSG.

Depth is emitted relative to the source-receptor distance. Subtracting that
constant is EXACT, not an approximation: every solid contributes as many back
faces as front faces, so it cancels in the difference — while keeping values
inside +/-50 mm, where half float resolves ~0.03 mm instead of the ~0.25 mm it
manages at 300.

### One bug, and it argues for saying so out loud

**The film blew out to flat white.** `readRenderTargetPixels` cannot return a
half-float target into a `Float32Array`, so `autoWindow` silently returned
nothing, the window stayed at its compiled-in default, and every tissue clipped.
The rings visible in the corner were half-float quantisation of the one region
still in range.

The tau buffer is now 32-bit float where the device offers it — it needs no
blending, being a single full-screen pass, so `EXT_float_blend` is not required
— and raw halves decoded by hand where it does not. **And a failed auto-window
now SAYS SO on the page** rather than leaving a plausible-looking uncalibrated
image. That was the actual defect: not the readback, but that the failure was
silent and the picture still looked like a radiograph.

### Device capability is reported, not assumed

`capabilities()` reports WebGL2, float and half-float colour buffers, float
blending, max texture size and the GPU string, and the page prints them. Where
the requirements are not met it says which, and says the rest of the atlas is
unaffected, instead of rendering something wrong.

**Still unverified: performance on the operator's phone.** The headless check
ran on SwiftShader, which is software, so it proves the code path and not the
frame rate.

---

## Phase 4 — cone beam and receptor (2026-09-05)

Receptor tilt, tube angulation, aim error and field diameter are controls;
`drr.html` takes URL parameters so a specific exposure can be linked and
reproduced. Presets for paralleling, correct bisecting and under-angled
bisecting.

### The projection is genuinely oblique

A `THREE.PerspectiveCamera` always puts its image plane perpendicular to the
view direction, which can only ever express the PARALLELING technique. Bisecting
tilts the film against the tooth's long axis, so the film is oblique to the
beam — and that obliquity is the whole lesson. The projection is therefore built
from the receptor RECTANGLE and the source point (Kooima's construction): an
orthonormal basis on the film and an off-axis frustum whose extents are its
corners as seen from the source.

Angling the tube MOVES THE SOURCE along an arc, which is what a tube head
physically does. It does not merely re-aim a beam from a fixed point, and if it
did, none of the following would happen.

### The bisecting rule reproduces itself, and nothing encodes it

Measured by projecting the tooth's own long axis through the same matrix the
image used — the length a clinician would measure ON THE FILM against the length
the tooth actually is:

| Setup | Result |
| --- | --- |
| Paralleling, tilt 0°, tube 0° | accurate — 26.6 mm film vs 25.9 true |
| Bisecting, tilt 20°, tube 10° (half the tilt) | accurate — 26.5 vs 25.9 |
| Bisecting, tilt 20°, tube 0° (under-angled) | **ELONGATED 9%** |
| Bisecting, tilt 20°, tube 25° (over-angled) | **FORESHORTENED 7%** |

Too little vertical angulation elongates, too much foreshortens, and aiming at
half the tilt is right. **None of that is written down anywhere in the code.** It
falls out of the projection geometry, which is the test `docs/wishlist.md` set
for this work: *"if the effect emerges from the DRR on its own, the simulation
is right."*

The 2.7% magnification at paralleling is real too, not an error — a divergent
beam magnifies an object held off the film.

### Cone cut is modelled as a cone

The beam axis is NOT the receptor normal — in bisecting the central ray is aimed
at the bisector, so it meets the film obliquely. Where the beam's circular field
misses the film, that region records nothing and reads BLACK, at the opposite
end of the scale from dense tissue. That is why a cone cut is unmistakable on a
real film, and it comes out as a clean arc here.

### A bug worth keeping, because of what it would have cost

The first version of `place()` "corrected" a source behind the receptor plane by
negating the film's horizontal axis. That silently **MIRRORED the radiograph** —
left and right swapped, and the picture still looked like a perfectly good
periapical.

On a radiograph that is not cosmetic. **Laterality is the one thing a film must
never lie about**, and a mirrored periapical points a clinician at the wrong side
of the mouth. `place()` now REFUSES, with a message saying how to order the
corners; callers derive the film's horizontal as cross(up, toSource) so the
question cannot arise.

It was caught only because the same negation also flipped the screen-space
winding, which inverted `gl_FrontFacing`, made every path length negative and
rendered dense tissue BLACK. That was luck. A mirrored image with the correct
polarity would have looked entirely plausible.

**Still open in Phase 4:** drawing the receptor and beam inside the 3D view, so
the geometry and its result can be seen together. The plan lists it as the
"ideally" of this phase and it is not done.

### Film orientation — corrected by the operator, 2026-09-05

**Maxillary films were printing upside down.** The receptor's vertical was being
oriented CROWN-WARD, which is right for the mandible and wrong for the maxilla.

The convention is one rule, not two: **patient-superior is UP on the film, both
arches.** A mandibular film shows crowns at the top and a maxillary film shows
them at the bottom because that is where those crowns actually are. Orienting
crown-ward gets the lower arch right by coincidence and inverts every upper one.

Fixed in `src/drr-page.js`, and the framing slider now means an APICAL shift in
both arches — the receptor's vertical points superior, which is apex-ward in the
maxilla and crown-ward in the mandible, so the sign follows the arch.
`drr_volume.py` already oriented to superior and was correct; its comment said
"crown-ward" and was not, so the comment was the bug there. Both Python
renderers were given the same arch-aware framing.

**A second bug fell out of testing the first.** `?tooth=3` did nothing: the URL
parameters were applied before the tooth `<select>` had any options, and setting
a select's value to a non-existent option is silently ignored. Three "different"
arch checks all rendered the same lower molars and looked consistent. Parameters
are now applied after the list is built.

### The exposure is drawn beside its result

`drr.html` carries a 3D inset: the film in blue, the beam in yellow, the tooth's
long axis in green, orbitable. `docs/wishlist.md` asked for exactly this —
*"display the receptor and beam in the 3D view simultaneously, so the geometry
and its result are visible together"* — and it is the difference between reading
that a film is foreshortened and seeing the tilt that foreshortened it. Both are
driven from the same numbers, so they cannot drift apart.

Two things it took a pass to get right. Only the last 42 mm of the beam is
drawn: at a 300 mm source distance the full cone fills the frame and hides the
anatomy it exists to explain. And the default viewpoint looks DOWN THE ARCH,
because receptor tilt, tube angulation and the tooth's long axis all lie in the
plane perpendicular to the mesiodistal axis — any other viewpoint foreshortens
the very angles being taught.

**Phase 4 is complete.**

---

## Phase 5 — validation against the operator's own PA (2026-09-05)

### The registration FAILED, and that is the finding

`tools/cbct/drr_fit.py` fits tube angulation and receptor tilt by maximising
gradient correlation against the real film. **It does not converge.** Scores
spanned 0.04-0.14 across a coarse grid with no basin, the best parameters were
unstable between neighbouring cells, and the fitted scale implied a **56 mm
sensor** against a real size-2 sensor's 35-41 mm.

Two structural reasons, neither fixable by tuning:

- The real film is full of trabecular texture that our homogeneous bone has
  nothing to match.
- OUR film has strong edges the real one does not: the ligament and lamina dura
  are drawn at 0.32 mm against a true ~0.2 mm, so they dominate our gradient
  image.

Correlating those two gradient fields largely measures their disagreement about
texture, which is a known and accepted difference — so the objective is
measuring the wrong thing, however carefully it is optimised.

**One bug was real and worth keeping.** The first objective scored NCC over the
overlapping region only, so sliding the DRR off the frame shrank the mask until
a handful of pixels could correlate by chance — and it duly reported shifts of
80 and 108 px scoring BETTER than any true alignment. An objective evaluated
over the overlap must hold the overlap roughly fixed, or it will buy its score
by having less of it.

### So ask a question that needs no fit — and that one passes

`tools/cbct/drr_validate.py`. The zirconia crown is the one structure both
images segment trivially and unambiguously: at ~214 against at most ~145 for any
tissue, a cut at 180 needs no tuning. Its **aspect** and **bbox fill** are
invariant to scale, sensor size, source distance and where the film sat.

| | aspect w/h | fill of bbox |
| --- | --- | --- |
| Real PA | 2.089 | 0.819 |
| Geometry DRR at paralleling | 1.825 | 0.784 |

12.6% apart on aspect — but **aspect is strongly angulation-dependent**, so
comparing at an arbitrary paralleling geometry measures the angulation and not
the model. Sweeping (`--sweep`):

| tilt | tube | aspect | vs real | fill | vs real |
| --- | --- | --- | --- | --- | --- |
| 8° | 3° | 2.045 | −2.1% | 0.804 | −1.8% |
| 10° | 4° | 2.120 | **+1.5%** | 0.806 | **−1.6%** |
| 5° | 4° | 2.130 | +1.9% | 0.806 | −1.6% |

**A clinically ordinary bisecting geometry reproduces both scale-invariant shape
measures of the real crown to within about 2%.** Nothing was fitted to get
there: the crown's geometry comes from the segmentation, its outline from the
threshold, and its projected shape from the exposure model.

That is a narrow claim and it is deliberately narrow. It validates the crown's
segmented geometry and the projection, and it says nothing about bone texture,
density or the tissues that do not segment this cleanly.

**Phase 5 is complete, and the plan's six phases with it.**

---

## Integrated into the atlas — 2026-09-05

A **Radiograph** toggle in the top bar opens a right-hand panel with the film,
and puts the sensor and beam in the mouth in the 3D view. `?xray=1` opens
straight into it.

**Selecting a tooth aims the tube at it**, so the radiograph follows what the
user is already looking at instead of needing its own picker. Selecting anything
that is not a tooth leaves the exposure alone — re-aiming because someone
clicked the mandible would be worse than doing nothing.

### Structure

- `src/exposure.js` — where the sensor and tube go, given a tooth. **Shared by
  the standalone harness and the atlas**, so the two cannot compute the exposure
  differently. A simulator whose side panel and whose 3D overlay disagreed about
  where the film was would be worse than having neither. It mirrors `frame()` in
  `drr_volume.py`, which remains the reference.
- `src/radiograph.js` — the mode: panel, sensor rig, and the wiring to selection.
- `drr.html` stays as the harness and the place to develop.

### It shares the atlas's renderer

A second WebGL context would upload all 15 MB of geometry again. Instead the
film renders to an offscreen target and is read back into a 2D canvas — one
readback per control change, against a permanent second copy of the mouth in
video memory.

### Two things that needed a second pass

**The beam has to be nearly invisible.** At any opacity that reads as a solid it
becomes a tan slab lying across the face, hiding the anatomy the atlas exists to
show. It is context, not subject: 0.055 opacity and only the last 30 mm drawn.

**The window is a percentile and needs samples.** At the panel's ~245 px the
1/8-scale tau grid is 30 px across, and the window jittered between renders for
no reason a user could see. Floored at 64 wide — still trivial to read back.

### The caveat now describes what ships

Invariant 4. The panel's source-data note gained the two new structures and the
radiograph's own limits: the crowns are measured in OUTLINE only and take their
density from the literature, the lamina dura is drawn continuous at an
exaggerated thickness wherever the socket runs rather than only where cortex was
resolved, and the simulated radiograph carries no trabecular pattern.

### Four corrections from the operator, 2026-09-05

**1. The panel opened on load.** `.panel { display: flex }` beats the browser's
own `[hidden] { display: none }` on specificity, so a panel marked hidden in the
markup rendered anyway. `.panel[hidden]` now settles it.

**2. The two right-hand panels cut each other off.** They now share the column:
the selection panel is capped at 30vh and the radiograph takes what is left, so
neither can crowd the other however long the selection text runs.

**3. It opened on tooth 30 whatever was selected.** There is no default tooth
now. Opening on a subject the user did not choose states an answer they did not
ask for, and on a simulated radiograph that is worse than showing nothing. It
prompts instead, and entering the mode picks up whatever is already selected.

**4. Clicking a tooth's ENAMEL did nothing.** The real bug, and the operator's
account of why it mattered is the useful part: the enamel cap clads the crown,
so on a crowded arch it is often the only thing a pointer can reach — "I would
only be able to view a DRR if I clicked on tooth which wasn't always possible".

Per-tooth structures carry no notation of their own (`toothNotation` only
answers for the teeth layer), so nothing in the app could ask which tooth an
enamel cap belonged to. `build-assets.mjs` now emits the parent `tooth` on every
per-tooth structure, and selection resolves through it. Verified end to end:
`FMA55703-enamel` aims at 18, `FMA55705-prosthetic` at 30, `FMA55706` at 31.

`?select=<FMA>` deep-links a structure and pairs with `?xray=1`, so a whole
exposure is linkable.

**A TDZ bug fell out of testing this.** `?xray=1` ran beside the rest of the
radiograph wiring, but `setXray` reads the current selection and `selected` is
declared further down — so it threw a temporal-dead-zone ReferenceError that
aborted the rest of `main()`. The panel opened with its static markup intact and
looked merely WRONG rather than broken, which is why it read as a styling
problem. The auto-open now runs at the end of `main()`.

**And a threshold that was lying.** Teeth 18 and 31 reported "elongated 3%" at
PARALLELING, where nothing is wrong. A correct film still magnifies: the tooth
is held off the receptor and the beam diverges, so flawless paralleling comes
back 3-5% long. The band was ±3% and sat exactly on that floor. It is now ±6%
and reports the magnification rather than hiding it — all three teeth read
"accurate — x1.03 magnification".

---

## A real sensor, and it has to fit — 2026-09-05

### The sensor is now a size-2 sensor, to the millimetre

**Active 36 x 25.6 mm; housing 43 x 31.2 x 7.5 mm.** The active area is the
image and the housing is what has to fit in a mouth — 3.5 mm of dead plastic
along each long edge and 2.8 mm along each short one — and that difference is a
large part of why placement is hard. The film shows the active area; collision
tests the housing.

**Independent check on the number:** the active aspect is 36/25.6 = 1.406, and
the operator's own periapical is 2400 x 1708 px = 1.405. The film Phase 5
validates against came off a sensor of exactly this shape. The 40 x 28.5 mm used
until now was a guess and was 11% too wide.

### Anteriors are shot portrait

Canines and incisors turn the sensor 90°. Not a preference: a canine is longer
than the short side of the sensor and would not fit crown-to-apex across it, and
the anterior arch is too tightly curved to take 43 mm of rigid housing sideways.

**One bug here:** the manifest's tooth type is the full descriptor — "central
incisor", not "incisor" — so an equality test matched nothing and every incisor
was still being shot landscape while the canines beside them turned correctly.
Matched as a substring now.

### The sensor cannot pass through anatomy

`src/occupancy.js`. The anatomy is voxelised once at load into a 0.9 mm solid
map — 101 x 100 x 91 cells — and every placement test is an array lookup, which
is what makes collision affordable while a slider moves. `placeSensor` searches
stand-off AND slide along the film's own axis, and reports what it took.

**Tilt is deliberately NOT searched.** Tilting the film is the bisecting
technique — the user's decision and the thing being taught — so finding it
automatically would answer the question the simulator exists to ask.

### Getting the constraint right took four wrong versions

Each failed in a way worth recording, because each looked like the anatomy's
fault rather than the test's.

1. **Zero tolerance against all tissue: nothing fit anywhere.** A real sensor is
   always touching something. Hard and soft were split — bone stops the film,
   mucosa compresses.
2. **Still nothing fit.** The grid marks every voxel a triangle touches, so the
   anatomy was dilated by up to 1.5 mm and genuine CONTACT registered as
   overlap. At 0.9 mm the best overlap on tooth 30 fell from 9 samples to 1.
3. **Maxillary placements got WORSE the more correctly the user tilted.** The
   receptor's vertical points superior in both arches, which is apex-ward in the
   maxilla and crown-ward in the mandible, so the same tilt opens the angle in
   one arch and closes it in the other — rotating the film into the palate. Tilt
   and tube angulation now carry the arch's sign, as framing already did. Same
   family as the upside-down maxillary films.
4. **Then everything fit trivially.** A 2 mm allowance removed the difficulty
   altogether.

### The remaining allowance is a stand-in for tissue the model lacks

A sensor is never placed against bare bone; it rests on mucosa. This atlas has
no palatal or sublingual mucosa — gingiva is a thin collar around the teeth —
so every hard surface sits a few millimetres closer than in a patient. The hard
region is therefore eroded by `mucosaMm` before collision. **It is an explicit
stand-in for a missing structure and should be deleted when the intraoral scan
lands.**

**Chosen against a measured distribution, not by eye.** `drr.html?audit=1`
places the sensor at all 28 teeth and reports the spread:

| mucosa | nominal | needed moving | impossible |
| --- | --- | --- | --- |
| 0 mm | 0 | 4 | **24 of 28** |
| 0.9 mm | 4 | 22 | **2** |
| 1.4 mm | 20 | 8 | 0 |

0 mm says the model has no mucosa. 1.4 mm removes the difficulty. **0.9 mm gives
the clinically right answer:** most teeth need the film adjusted, and the two
that cannot be placed at all are **24 and 25 — the mandibular central incisors.**
At 20° of tilt all 28 place. That the anterior teeth are the ones paralleling
cannot reach, and that tilting rescues them, is exactly why the bisecting
technique exists — and nothing in the code was told to produce it.
