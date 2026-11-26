# Wishlist

Ideas captured for later. Nothing here is scheduled, and nothing here should be
built before the Phase 3 anatomy it depends on exists. Recorded so they are not
lost, with a note on what each actually needs.

---

## NEXT UP — named by the operator 2026-09-05, extended 2026-09-06

Both are refinements of the radiograph simulator that shipped in 0.8.0, and both
were left undone deliberately rather than missed. **Read
[drr-plan.md](drr-plan.md) first**; it holds the measurements, the decisions and
what has already been ruled out.

**Added 2026-09-06.** The operator named two specifics inside item 2 — round the
housing, and give every tooth an ideal starting placement — and four further
items, recorded lower down: the [bitewing](#bitewing-bwx--the-view-that-needs-both-arches-at-once),
[cleaning up enamel](#clean-up-enamel--operator-2026-09-06-gingiva-half-withdrawn-same-day)
[the phone UI](#the-phone-ui--operator-2026-09-06) and
[the seam between the fields of view](#the-seam-between-the-fields-of-view--operator-2026-09-06).
**Trabeculation is still first**; the order of the rest is not set.

### 1. Trabecular bone

**The most conspicuous difference between our radiograph and a real one.** On
the operator's own periapical the trabecular pattern fills most of the film below
the crowns; ours is a flat homogeneous slab, because the model has no trabecular
geometry — the mandible is one solid mesh carrying one bulk density.

It was named as an accepted cost of choosing labelled geometry over the voxel
volume as the DRR substrate. That decision still looks right for everything else
it bought, but the gap is the one a clinician sees first.

**Approaches worth weighing before writing anything:**

- **Modulate the bone's density along the ray from the volume itself.** The CBCT
  measured this patient's trabeculae; a coarse 3D texture sampled in world space
  would carry the real pattern rather than an invented one. The honest question
  is what tier that earns — the pattern would be measured, its use as a density
  modulation would not.
- **Generate a pattern procedurally.** Cheap and shippable, and `simulated` at
  best. It would make the film look right and tell a reader nothing true.
- **Segment trabeculae as geometry.** Most faithful, almost certainly too much
  at 0.16 mm, and it would multiply the mesh budget.

**Do not let "it looks more like a radiograph" settle this.** A procedural
pattern scores well on exactly that and is an invented texture over a real
patient. Decide the provenance question first.

### SHIPPED STATE 2026-09-06 — good in the mandible, KNOWN BAD on upper anteriors

The field is built (`tools/cbct/trabecular_field.py`, 4.00 MB at 0.48 mm) and
wired into the DRR as its own ray-march pass. Against the operator's own
periapical it matches to **0.99x** on bone contrast, with show-through over root
dentin at 0.414. Verified good on teeth 30, 31 and 3.

**Upper anteriors are wrong and are shipping wrong.** Tooth 9 is unreadable with
the field on and clean with it off. The cause is NOT the field — see CLAUDE.md
226 for the three hypotheses that were tested and failed — it is that
`autoWindow()` fits a percentile stretch per film, and a low-contrast
upper-anterior view amplifies everything faint in it. **The fix is the exposure
model in item 2b above, not another coefficient here.** Until then, either accept
it or gate the field to the mandible.

### MEASURED 2026-09-06 — the pattern is there, and it is the patient's

The operator called it: measure, do not synthesise. `tools/cbct/trabecular_isolate.py`
removes teeth (+1.25 mm, which covers PDL, lamina dura and the tooth's own
point-spread halo), canals and the restoration halo; the residual is detrended
by depth and high-passed with a 2 mm box; autocorrelation is then compared
against soft tissue and air put through the identical filter.

**Excess autocorrelation over the matched soft-tissue control, per axis:**

           0.16   0.32   0.48   0.64   0.80   0.96   1.28   1.60   2.08 mm
      z  +0.249 +0.307 +0.262 +0.205 +0.165 +0.137 +0.096 +0.065 +0.032
      y  +0.114 +0.059 -0.055 -0.144 -0.182 -0.179 -0.122 -0.082 -0.068
      x  +0.218 +0.271 +0.184 +0.070 -0.011 -0.051 -0.087 -0.102 -0.098

Bone is elongated along **z** — sustained positive excess at every lag — and
**anticorrelated in the transverse plane** at 0.8-2 mm, where both controls stay
positive. Structure continuous along its length and alternating across it, with
a transverse scale of about a millimetre, is a trabecular network; and vertical
orientation is what alveolar bone should show, since those struts align with
occlusal loading.

**THE ANISOTROPY IS NOT THE SCANNER, and this is the load-bearing check.** FDK
reconstruction correlates noise along the rotation axis, so an axis preference
in bone proves nothing on its own. But the controls' own preference runs
**y > z > x** (soft tissue at 0.48 mm: 0.284, 0.167, 0.046) while bone's runs
**z > y = x** (0.429, 0.229, 0.230). Bone's preferred axis is the scanner's
middle one, and the scanner's preferred axis is where bone shows its strongest
NEGATIVE excess. The reconstruction cannot produce that.

Fine-scale amplitude is **sd 198.5** against a bulk sd of 316, so this is a
large share of the variation rather than a trace.

**Two cautions that ride with it.** The 2 mm high-pass box mechanically induces
some anticorrelation near its own scale; the controls went through the same
filter and did not go negative, but "same filter" is not "same filter artefact",
so the transverse periodicity is suggestive rather than settled and wants a
filter-scale sweep. And the grey values are **not calibrated HU**
(`nrrd/volumes.json` says so outright), so the honest tier is **pattern measured,
absolute scale derived** — `boneVolumeFraction` still comes from literature.

**Two earlier attempts at this test were wrong and are recorded so they are not
repeated.** Detrending by a per-depth-bin GLOBAL mean leaves every
centimetre-scale variation in place, so the ACF measured anatomy, not
trabeculae. And an air control that is not locally detrended carries the cupping
gradient and plateaus around 0.5, which cannot falsify anything. Both looked
like strong positive results.

**Also unresolved and related:** `boneVolumeFraction = 0.25` in `tissues.mjs`
is a bulk stand-in that nothing has fitted to this patient.

### 2. Sensor geometry and placement

The sensor is a real size-2 — 36 × 25.6 mm active in a 43 × 31.2 × 7.5 mm
housing — and it cannot pass through bone. What is still crude:

- ~~**Nothing models the patient's posture.**~~ **DONE 2026-09-06.** The
  occupancy grid was built from every hard mesh INCLUDING the opposing arch, on
  one frozen frame with the teeth together, so collision was answering "does
  this fit with the mouth shut" — and a periapical is not taken that way. There
  are now two grids, one per arch being filmed, with the OPPOSING arch held
  `INTEROCCLUSAL_MM` away; the arch being filmed never moves, because the sensor
  is placed against it. Measured effect across all 28 teeth:

      opening   total |adjustment|   pinned at the 7 mm limit
       0 mm          165.0 mm                 5
       5 mm          108.5 mm                 2
      10 mm           80.5 mm                 1
      20 mm           80.5 mm                 1

  Five teeth had been PINNED at the slide search's 7 mm limit — those placements
  were not found, they were abandoned at the edge of the search. The effect
  saturates at 10 mm, so the default is 12: past saturation a rigid translation
  only gets more wrong at the condyle while changing nothing at the teeth. It is
  a pure inferior translation and that is NOT how a mandible opens; replace it
  when the TMJ exposures land, do not tune it.

- **`mucosaMm` in `src/occupancy.js` stands in for tissue the model does not
  have.** There is no palatal or sublingual mucosa, so every hard surface sits
  millimetres closer than in a patient, and collision leans on an eroded hard
  region to compensate. **Delete it when the intraoral scan lands** rather than
  leaving a constant nobody can account for.
- ~~**Placement searches stand-off and slide only.**~~ **DONE 2026-09-06.** Film
  roll and arch shift are searched (hierarchically, least-contorted first), and
  the slide range went from ±7 mm to ±20 mm — it had been smaller than the 43 mm
  housing it was moving. Horizontal TUBE angulation was added at the same time
  and matters more: the operator's view is that "the flexibility of dental xrays
  comes from the positioning of the tube head less so the placement of the
  sensor", and it is the manoeuvre endodontics uses most.

  With bone absolute, failures went 21 → 17 (slide) → **5** (roll and arch
  shift). The five are teeth 8, 23, 24, 25 and 26 — the upper right central and
  the lower incisors, which is where a size-2 sensor genuinely is hardest.
- **The housing is a plain box.** Real sensors have rounded corners, a cable
  exit and a bite-block or holder, all of which decide what is reachable.
  **Promoted to a job of its own by the operator 2026-09-06 — see 2a below.**
- **Nothing models the patient.** No tongue, no floor of mouth, no gag reflex,
  no ability to open only so far. The simulator will happily place a film where
  a person would not tolerate one.
- **The collision allowance was set against a measured distribution** (0.9 mm,
  `drr.html?audit=1`) and should be re-derived, not nudged, if it moves.

#### 2a. Round the housing — operator, 2026-09-06

Round the corners and break the edges of the sensor body, in both the drawn rig
and the collision test.

**This is not cosmetic, and the collision half matters more than the render.**
`sensorFits` in `src/occupancy.js` samples the housing on a 13 x 9 lattice over
its two flat faces — 234 points — and the hard-contact budget is
`hardAllowance = 0.025`, so **at most 5 of those 234 may land in bone or tooth**.
The four corners of each face are 8 samples. Corner contact alone therefore
exceeds the entire budget and can be the whole reason a placement is refused,
and those corners are exactly the geometry a real sensor does not have. A
size-2 housing carries roughly a 3–4 mm corner radius; masking the lattice with
a rounded-rectangle test, or insetting the corner samples, is a small change
that makes the fit test describe the object.

#### DONE 2026-09-06 — and it rescued the incisors, which was the warning sign

Built: `CORNER_MM = 3.5` in `occupancy.js` masks the sample lattice with a
rounded-rectangle test, and `housingGeometry()` in `exposure.js` draws the same
shape (with a bevel breaking the edge in thickness) for both the atlas and the
harness, so the two cannot disagree about the object.

**The measured effect, `drr.html?audit=1&corner=<mm>`:**

    corner    nominal   moved   fail
     0 mm        4        22      2    <- teeth 24 and 25
     2 mm        4        23      1    <- tooth 25
     3.5 mm      4        24      0
     5 mm        4        24      0

**I WAS WRONG ABOUT WHERE THE INCISORS FAIL.** The caution written above said
they fail on the film's long edges rather than its corners, so rounding should
not rescue them, and that if it did the geometry was wrong somewhere else. It
rescued both — teeth 24 and 25, the lower centrals — because their failures were
corner-driven after all. That claim was reasoning, not measurement, and the
measurement contradicts it.

**`hardAllowance` did NOT need re-deriving**, and the reason is worth stating
rather than assuming: it is expressed as a FRACTION of the sample count, and
dropping the corner samples lowers the count and the absolute budget together.
The rationale for the number — that the occupancy grid dilates anatomy by up to
a voxel, so genuine contact registers a few hits — is a property of the grid,
not of the sensor's outline, and rounding the corners does not touch it.

**What DID dissolve is the calibration point for `mucosaMm`.** That 0.9 mm was
chosen because it made "the failures are exactly the incisors" come out true.
With rounded corners the audit returns zero failures at 0.5, 0.7 AND 0.9 mm — the
sweep no longer discriminates at all, so the number is now unconstrained by the
evidence that set it. It is still due for deletion when the intraoral scan lands.

**THE OPEN QUESTION IS CLINICAL, and it is the operator's.** The simulator now
says all 28 teeth can be filmed, and never returns "will not fit". The original
note argued a simulator that always finds room has removed the difficulty it
exists to teach. Against that: refusing a placement because of plastic the
sensor does not have was teaching a false difficulty, and the readout still
reports how far the film had to be moved — teeth 24 and 25 need large slides,
which is the honest signal. Whether a size-2 at the lower centrals should read
as *hard* or as *impossible* is a judgement about real technique.

The cable exit and the bite-block are the same item's remaining half and are
**harder**: a holder is what actually fixes the beam to the receptor, so it is
entangled with 2b below rather than with the housing shape. Keep them separate.

#### 2b. An ideal placement per tooth, restored on every selection — operator, 2026-09-06

**What is asked:** each tooth opens at a preset ideal receptor position — the
whole root visible, minimal angulation — which the user may then push around to
see what goes wrong. Selecting a different tooth restores that tooth's ideal.

**What exists already.** Half of this is built and it is worth being precise
about which half, because it changes the size of the job:

- `frameFor()` in `src/exposure.js` already derives a per-tooth receptor frame
  from the anatomy — long axis by PCA, horizontal along the arch, buccal away
  from the arch centre — and `sensorFor()` already turns the sensor portrait for
  incisors and canines. That part is per-tooth and correct.
- `placeSensor()` already searches stand-off and slide for a placement that
  clears tissue, so the film is already moved per tooth.
- **What is NOT per-tooth is the state.** `src/radiograph.js` holds one
  `state = { kvp, tilt, vert, vshift: -4, gamma, field }` for the whole session,
  and `setTooth()` changes `state.tooth` and nothing else. So the controls the
  user has moved carry over to the next tooth, which is the behaviour the
  operator is asking to end.

**So the job is two pieces**, and only the second is research:

1. ~~**Reset on selection.**~~ **DONE 2026-09-06.** `setTooth()` applies the
   incoming tooth's ideal, and an **Ideal** button restores it after the user
   has moved things. This is the half that actually changes behaviour today:
   the angles used to carry over, so a 20-degree tilt chosen for a molar became
   an incisor's starting point.
2. ~~**Compute the ideal.**~~ **DONE 2026-09-06 — and the definition written
   here first was wrong.** It said "minimise |ratio - 1| subject to `fits`".
   Forced to actually run, that objective picks **20-25 degrees of tilt at
   nearly every tooth**, usually pinned at the boundary of the sweep, to buy
   less than one percent of magnification. Nobody would take that exposure.

   Accuracy is a THRESHOLD to clear, not a quantity to maximise: a correct film
   already magnifies 3-5% from stand-off and beam divergence alone, and the last
   fraction of a percent is not worth any angulation. The operator's brief said
   so — "shows full root structure, **minimal angulation**" — and angulation had
   been given zero weight. `idealFor()` in `exposure.js` now orders it:

       1. the sensor must FIT
       2. the tooth must measure within `accurateWithin` (6%)
       3. subject to those, |tilt| as SMALL as possible

   Tilts are tried in increasing magnitude, so the first that clears (1) and (2)
   is by construction the least-angulated one that does.

   **The result for this mouth: paralleling at ALL 28 teeth**, magnification
   1.030-1.043, and the same answer with the mouth closed. The per-tooth ideal
   is currently identical to the old fixed default everywhere — which is a real
   finding rather than a failure, and it is what a correctly-placed size-2
   sensor in an unremarkable dentition should give. The machinery earns its
   place when the anatomy stops being unremarkable.

   **The search is exercised, not merely present.** With the threshold tightened
   to 3.2% (`drr.html?ideal=1&tol=0.032`) 14 teeth need tilt and each picks the
   smallest that works — tooth 6 takes -12.5 degrees, tooth 7 takes 10, and
   teeth already accurate stay flat. Without that check the zero-tilt exit fires
   at every tooth and the sweep below it would have shipped untested.

**Two things to decide before building piece 2:**

- **Precompute or solve live?** 28 teeth is small enough to solve at load, but
  the solve calls the DRR's projection for `ratio`. Cheaper: score `ratio`
  analytically from the frame and the source position — it is a projection of
  two known points and needs no ray-cast. Prefer that.
- **"Minimal angulation" and "full root visible" can conflict.** For a tooth
  where nothing fits at zero tilt, showing the whole root REQUIRES a tilt, and
  that is the bisecting technique doing its job. The preset should take the
  tilt and **say so in the readout** rather than silently presenting a
  compromise as ideal. The readout already reports placement adjustments in
  exactly this spirit; extend it, do not add a second voice.

**Also: the user needs a way back.** Once they have modified the placement, a
"restore ideal" control for the current tooth, so the reset is not only reachable
by selecting away and back.

##### Exposure is part of the ideal, and the simulator has no exposure control

**Operator, 2026-09-06:** he adjusts impulses by region — **less exposure for
anteriors, more for posteriors** — because there is more bone and more tissue to
get through at the back of the mouth. That is a real part of the technique and
it belongs in "the ideal view" alongside the geometry.

**It is also a gap that is already causing trouble.** The simulator has kVp but
no exposure time, and `autoWindow()` — a percentile stretch over each film — is
silently standing in for the operator's exposure choice. That is not the same
thing: an operator picks exposure per REGION and lives with the result, while a
percentile stretch renormalises every image to fill its own range. So a view of
thin, low-contrast anterior anatomy gets stretched exactly as hard as a molar
view, and anything faint in it is amplified. This is what made the trabecular
field unreadable on upper anteriors while it was correct on molars.

**Backed by measurement in this patient**, and it corrects an assumption worth
recording: **mandibular alveolar bone is 42% DENSER than maxillary** here — mean
806 against 566 in the isolated bone, ±15 mm of the occlusal plane, same
exposure so directly comparable. That is the way round the Lekholm-Zarb types
run (maxilla tending III/IV, mandible I/II). The operator's instinct that
maxillary films legitimately look different is right; the direction of the
density difference is the other way, and the visibility problem follows from the
LOW density rather than a high one.

**What it needs:** an exposure control that is set per exposure rather than a
window fitted per image — or at minimum, an auto-window whose range is derived
once for the whole mouth instead of per film. Worth doing WITH 2b, since "the
ideal placement" and "the ideal exposure" are the same lesson.

###### MEASURED 2026-09-07: the "at minimum" half is a NO-OP, and this is a feature not a fix

`drr.html?window=1` across all 28 teeth, after 0.9.0 fixed the latitude:

    fitted window OFFSET      -0.14 .. 0.00     against a latitude of 7.20
    spread                     0.14  =  1.9% of the latitude
    anteriors  mean           -0.037
    posteriors mean           -0.061
    difference                 0.024 =  0.3% of the latitude

**The offset is already constant across the whole mouth.** Deriving it once
instead of per film would change every image by under 2% of the range, and
would change the anterior/posterior relationship by 0.3%. It cannot be what
makes upper anteriors unreadable, and it is not worth writing.

**Why it is pinned:** `lo` is the 2nd percentile of tau over pixels below the
metal cut, and every periapical has AIR in the field, so the 2nd percentile sits
at ~0 on every film regardless of the anatomy. The offset is anchored by air,
not by the tissue. 0.9.0's fixed latitude had already removed the part that
varied — the WIDTH, which used to run 3.95 to 7.19.

**Two consequences.**

1. **This item is a FEATURE, not a bug fix.** There is nothing being silently
   re-decided that matters. Simulating "fewer impulses for anteriors" means
   DELIBERATELY choosing a different window per region, which changes how every
   film looks and implies a control the operator can move. That is a minor
   version, not a patch.
2. **The windowing hypothesis for the upper-anterior limitation is dead.** The
   0.9.0 changelog proposed per-region exposure as the fix on the reasoning that
   the window was standing in for the operator's exposure choice. It is standing
   in for it, but it is standing in *identically* on every tooth — so whatever
   makes upper anteriors unreadable with the trabecular field on, it is not the
   display window. That eliminates a sixth hypothesis after the five in
   CLAUDE.md 226, and it points at the field's own gain against maxillary bone
   measured 42% less dense than mandibular.

**One thing that IS a fix and is worth doing on its own:** `autoWindow()` is
called inside `update()`, so it does a full GPU render-target readback on EVERY
render — every slider move re-derives a number that never changes. Replacing it
with a constant would be identical on screen (see the spread above) and would
remove a readback per frame, which matters most on the weakest target, the
phone. Small, safe, and independent of the design question.

###### kVp persisted across tooth selection — operator 2026-09-06, FIXED 2026-09-07

**The operator found the same bug one control over.** 0.9.0 fixed horizontal
angulation carrying from one tooth to the next; **kVp was doing exactly the
same thing** and was missed, because `applyIdeal()` reset every geometric
parameter — tilt, vert, vshift, opening, horizAngle, roll, along, offset — and
no exposure one. A tube potential dialled up for a molar silently became an
incisor's starting point.

**Reproduced and fixed on the real code path**, driven through the atlas's own
DOM in headless Chrome rather than through a harness: select 30 (70 kVp), move
the slider to 85, select 8. Before the fix the slider and its label both still
read 85, and still did on returning to 30. After, both are back to 70.

**What the fix commits us to, and it is the useful part.** kVp is now carried
*in the ideal* (`IDEAL_KVP` in `src/exposure.js`, on the candidate objects in
both `idealFor()` and `solveQuick()`) rather than living beside it as a session
setting. So exposure is now structurally part of "the ideal view", which is what
this whole section argues it should be — and **when per-region exposure is
built, one constant becomes a function of the tooth and every caller already
reads it from the right place.**

**Two things deliberately still persist**, and they are not the same bug:
`field` is the collimator, a property of the machine rather than of the
exposure; `gamma` is a display control on the rendered film. Both are correct to
carry across teeth.

##### Does this need jaw articulation first? No — and gating it on articulation would be a mistake

**Short answer: no.** Nothing in the exposure geometry touches the opposing
arch. `frameFor()` builds the frame from the target tooth and its two
neighbours; `exposureFor()` places the receptor lingual to that tooth and the
source buccal to it. Both are single-arch. The preset is a change to the
defaults in `radiograph.js` plus a per-tooth solve over machinery that already
exists, and it would work identically in an articulated model.

**And gating it would be a bad trade**, because articulation is blocked on data
this scan does not contain. `tools/fov-audit.mjs` found the mandible **cut
through both rami** — full width 82.0 mm against an 81.9 mm FOV — so the
condyles, the glenoid fossa and the articular eminence were never in the box.
There is no measured condylar path to derive an opening from; it would have to
be published and labelled schematic, and the muscles that deform through the
opening are Phase 3 step 5. See
[Open and close the mouth](#open-and-close-the-mouth). Putting a small, fully
supported UI change behind that is putting it behind a year.

**But the operator's instinct is pointing at something real, and it is not
articulation.** The occupancy grid in `src/occupancy.js` is built from *every*
`HARD` mesh, which includes **the opposing arch**, and the model is one frozen
CBCT frame with the teeth together. So the collision test is currently
answering *"does this sensor fit with the mouth closed"* — and a periapical is
not taken with the mouth closed. This is already visible in the design:
[drr-plan.md](drr-plan.md) records that the default apical `vshift` exists
partly because "centring on the tooth's centre of mass catches the opposing
arch". A constant is absorbing a posture.

**The cheap fix is not articulation.** Either exclude the opposing arch from the
hard set for the duration of an exposure, or translate the mandible down by a
fixed interocclusal opening before voxelising. Both are hours, neither needs a
condylar path, and either makes the fit test answer the right question. **Do
this before fitting the ideals**, or every ideal gets fitted against a closed
mouth and has to be refitted later. Note it will also interact with the 0.9 mm
`mucosaMm` stand-in and with `hardAllowance`, both of which were fitted with the
opposing arch present — so re-run `drr.html?audit=1` after, and change one thing
at a time.

---

**Two ordering constraints, added 2026-08-31 — these are not free to
reshuffle:**

- ~~**Enamel, dentin and cementum come before the radiograph simulator.**~~
  **Done, and the ordering was right.** Enamel shipped in 0.7.0 and the tissue
  and density model in 0.8.0; the DRR integrates labelled geometry against
  cited densities, which is what that constraint existed to make possible.
- ~~**Provenance labels come before anything simulated.**~~ **Done 2026-08-31.**
  Anaesthetic diffusion and the pathology sliders generate geometry that is
  neither measured nor a literature mean; there is now a per-structure tier to
  say so, and a `simulated` tier waiting for them.

Both are now done.

And one item is genuinely **scheduled**: an intraoral scan of the operator's own
arches, around late September 2026, which would move the gingiva from derived to
measured. See [Scan the gingiva](#scan-the-gingiva-and-stop-deriving-it--scheduled-late-sept-2026).

---

## ~~The unifying idea: a digitally reconstructed radiograph~~ — BUILT, 0.8.0

**Everything in this section is done**, and what actually happened is recorded
in [drr-plan.md](drr-plan.md), which supersedes it on every point of method.
Kept here because item 3 below still depends on it and because the reasoning was
right: cone-beam geometry rather than parallel projection, and pathology modelled
once in the volume so the 3D view and the film cannot disagree.

The one prediction worth marking as CORRECT: tissue-labelled geometry carrying
its own density did turn the radiograph from a volume-shipping problem into a
shading problem. Nothing of the 185 MB volume ships.

The original text follows.

Items 2 and 3 below both hinge on one capability, and it is worth stating
separately because it changes how hard they are.

A simulated periapical or bitewing radiograph is a **digitally reconstructed
radiograph (DRR)** — a ray-cast integral of attenuation through a volume. We
already have the volume, at 0.16 mm isotropic, of *this patient*. So a simulated
radiograph would not be a generic illustration: it would show the same anatomy as
the 3D model, because it is computed from the same data.

That has two consequences worth designing around:

- **Cone-beam geometry, not parallel projection.** Foreshortening and elongation
  are exactly what receptor angulation teaches, and a parallel projection cannot
  show them. Model a source point, a receptor plane, and the bisecting angle.
- **Pathology modelled once, seen twice.** If a lesion is a parametric
  perturbation of the *volume* — a density deficit at an apex, a concavity on the
  lingual mandible — then the DRR picks it up for free and the 3D model shows the
  same object. One model, two views, always consistent. This is the reason to
  build pathology volumetrically rather than as a decal on a mesh.

Feasible in the existing stack (WebGL ray-marching in three.js), but the volume
is ~185 MB per arch and would need aggressive downsampling or a cropped region of
interest to ship to a browser. That is the main engineering question.

**Prerequisite, added 2026-09-01: fix the inter-tooth contact boundaries first.**
The arch split ends each tooth at its contacts, and at a true contact the two
crowns' enamel is one contiguous mass with no separating feature, so the
boundary currently lands as a near-planar chord through the crown. Nothing is
lost from the mouth — the wedge cut off one tooth is labelled as its neighbour —
so the assembled atlas renders correctly and this is invisible until something
integrates density PER TOOTH. That is exactly what a DRR does, and the bitewing,
its flagship view, is *about* the interproximal contact. Shipping a simulator
whose contact geometry is arbitrary would fail at the one thing it exists to
teach. See [Fix the inter-tooth contact boundaries](#fix-the-inter-tooth-contact-boundaries--prerequisite-for-the-drr).

**Prerequisite, added 2026-08-31: split the hard tissue into enamel, dentin and
cementum first** — see that section below. Tissue-labelled geometry carrying its
own density is a second, much lighter substrate for the ray-cast, and it may
remove the shipping problem entirely rather than mitigating it.

---

## 1. Pulpitis → necrosis → root canal, as a timelapse

**A dedicated tracker now exists: [pathology-wishlist.md](pathology-wishlist.md)**,
opened 2026-09-07 at the operator's request. It carries the disease catalogue,
the graphical and interaction items, and the provenance rules that govern all of
them. This section is the seed it grew from; the tracker is newer where they
disagree.

A progression the user can scrub through:

1. Intact tooth.
2. Insult — trauma, or restoration placement with its thermal and mechanical
   history.
3. Reversible pulpitis, then irreversible.
4. Necrosis, with the periapical consequence appearing (see PARL, item 3).
5. Cross-section of the complete root canal procedure: access cavity, working
   length, cleaning and shaping, obturation.

**What it needs:** the pulp as *tissue* with internal structure, not just a lumen
boundary — the odontoblast layer and neurovascular core described in
[phase-3-soft-tissue.md](phase-3-soft-tissue.md). Inflammation and necrosis are
changes in that tissue, so the tissue has to exist first.

**Worth noting:** the operator's dentition has **no endodontic treatment
anywhere**, so all 28 pulps are native and unobturated. The atlas therefore shows
the *healthy* baseline from real measured anatomy, and the diseased states are
authored departures from it. That is the right way round, and rarer than it
sounds — most endodontic teaching material starts from treated teeth.

The access cavity and instrumented canal are *authored* geometry, not measured.
Keep them in a separate tree from the measured pulp.

---

## ~~2. Draggable radiograph simulator~~ — BUILT, 0.8.0

Shipped as radiograph mode in the atlas plus a standalone harness at
`/3Dentes/drr.html`. Receptor tilt, tube angulation, aim error and field
diameter are controls; the receptor and beam are drawn in the mouth beside the
film; foreshortening, elongation and cone cut all fall out of the projection
rather than being authored. The film reports what the tooth measures on it
against its true length. See [drr-plan.md](drr-plan.md).

What is NOT done and is now item 2 of "Next up" above: the sensor geometry and
placement refinements. What was never started: the BITEWING, which needs a
receptor spanning both arches with the patient in occlusion.

The original text follows.

A side panel showing a simulated PA or bitewing. The user drags a receptor around
the arch and sees what that placement would produce.

- Receptor position and angulation as the controls; paralleling versus bisecting
  technique as a mode.
- Show the resulting cone cut, foreshortening, elongation, and overlap — the
  actual failure modes of the technique.
- Ideally: display the receptor and beam in the 3D view simultaneously, so the
  geometry and its result are visible together.

**What it needs:** the DRR above. Nothing else — this one is buildable on the
existing volume without any further anatomy.

**Why it is the strongest item here:** it teaches something no static atlas can,
and the data to do it honestly already exists.

---

## 3. Pathology menu, shown on model and radiograph together

**A dedicated tracker now exists: [pathology-wishlist.md](pathology-wishlist.md)**,
opened 2026-09-07 at the operator's request. It carries the disease catalogue,
the graphical and interaction items, and the provenance rules that govern all of
them. This section is the seed it grew from; the tracker is newer where they
disagree.

Select a pathology; it appears on both the anatomical model and the simulated
radiograph, consistently, because both read the same volumetric perturbation.

Initial candidates:

| Pathology | Volumetric form | Ties to |
| --- | --- | --- |
| Periapical radiolucency | Density deficit centred on an apical foramen | Item 1's necrosis stage |
| Stafne defect | Lingual concavity of the mandible, below the canal | — |
| Cementoma / periapical cemento-osseous dysplasia | Mixed deficit and excess at apices, staged | Progression variable |

**Randomizable variables**, so the same pathology yields unlimited practice cases:

- Size.
- Location, constrained to a defined set of anatomically valid points — for a
  PARL, the measured apical foramina; for a Stafne defect, the lingual mandible
  below the canal.
- Disease progression / stage, which for a cementoma is a genuine radiographic
  sequence from radiolucent through mixed to radiopaque.
- Optionally: whether the lesion is visible on a given projection at all, which
  is itself the lesson — a buccal lesion hidden by the root on one angle.

**What it needs:** the DRR, plus the measured apical foramina (**already have
these — 48 of them**) as anchor points, plus the mandibular canal as an anatomical
constraint for anything sited near it.

**Design note:** the anchors should be the *measured* landmarks wherever possible.
A PARL placed on a real apical foramen at a real position is a better teaching
object than one placed at an arbitrary point, and costs nothing extra now that the
foramina are measured.

---

## Bitewing (BWX) — the view that needs both arches at once

**Operator, 2026-09-06.** Named as its own view alongside the periapical.

It was flagged as never-started in the 0.8.0 note above, and it is genuinely a
different exposure rather than a periapical with different numbers:

- **The receptor spans both arches**, held between them with the patient in
  occlusion, and the beam runs horizontally through the interproximal contacts.
  Nothing in `exposureFor()` is shaped for this — the whole frame is built
  around one target tooth's long axis, and a bitewing has no single target
  tooth. It needs its own frame function: the occlusal plane as the horizontal,
  a segment of the arch as the extent, and the beam in the plane rather than
  angled to a tooth.
- **It is the one view where the contact geometry is the subject**, which is
  why fixing the inter-tooth contact boundaries was made a DRR prerequisite in
  the first place — see the note in the 0.8.0 section above. Those were re-cut
  2026-09-02, so this is no longer blocked on them.
- **It wants a horizontal-angulation control**, because overlapped contacts are
  the classic bitewing failure and they are produced by horizontal angulation,
  not vertical. The current controls are `tilt` and `vert`, which are the
  periapical's freedoms. Overlap is what a bitewing exists to teach the way
  foreshortening is what a periapical teaches.
- **Vertical and horizontal bitewings are a real distinction**, and a vertical
  BWX to show bone levels is a small addition once the horizontal one exists.

**What it needs.** The DRR engine, which exists. A second frame function and a
second control. **Not** trabecular bone strictly speaking — but a bitewing whose
whole lower half is a flat homogeneous slab will read as wrong faster than a
periapical does, because bone level against a plain crest is a large part of
what a clinician reads off one. **Suggest ordering it after item 1.**

**One thing it inherits and one it does not.** It inherits the sensor housing
and the collision test, so 2a helps it. It does **not** need the per-tooth ideal
of 2b, because a bitewing is framed to a segment, not a tooth — but it does need
the same closed-mouth question answered the other way round: a bitewing is the
one exposure where the mouth genuinely IS closed, so the opposing arch belongs
in its collision test even after it is removed from the periapical's.

---

## Time-varying sliders — one mechanism, three diseases

**A dedicated tracker now exists: [pathology-wishlist.md](pathology-wishlist.md)**,
opened 2026-09-07 at the operator's request. It carries the disease catalogue,
the graphical and interaction items, and the provenance rules that govern all of
them. This section is the seed it grew from; the tracker is newer where they
disagree.

All three below are the same interaction: a scrub bar the operator drags, with
the model and (once the DRR exists) the simulated radiograph both updating. They
are grouped because building the scrubber once buys all of them, and because
each is a process a patient actually walks through over years rather than a
static finding.

### Calcification with age

Secondary dentin deposits throughout life, so the chamber and canals narrow and
the pulp horns recede. This is the single most useful one for teaching, because
it is what makes an endodontic access on a 70-year-old different from the same
tooth at 20, and it is measurable rather than invented: pulp chamber volume has a
well-documented linear inverse association with age, which is the basis of the
CBCT age-estimation literature. It also runs *backwards* from the model we have
— the operator's own dentition is a real point on the curve, so the slider
interpolates from measured geometry rather than from an average.

**What it needs:** an erosion of the pulp surface parameterised by age, with the
apical foramen narrowing faster than the chamber; ideally calibrated against
published pulp-volume-versus-age regressions rather than chosen by eye.

### Dentinal decay

A caries lesion advancing from the enamel surface through dentin toward the
pulp, with the slider being lesion depth. The teaching value is the relationship
between radiographic depth and pulpal status — the point at which a restorable
lesion becomes a pulpotomy becomes a root canal.

**What it needs:** a lesion volume seeded on a tooth surface and grown along
dentinal tubule direction (toward the pulp), subtracted from the dentin. Should
respect the enamel-dentin junction, where real lesions spread laterally.

### Fracture progression

From a small coronal crack extending apically to a full root-length fracture,
with the **J-shaped radiolucency** appearing on the simulated radiograph as it
progresses — the halo that wraps the apex and runs up one side of the root,
which is the classic sign and the reason this belongs with the DRR work.

**What it needs:** a fracture plane through the tooth with a controllable apical
extent, plus the associated bone loss pattern. The J-shape is a *consequence* of
modelling the periradicular bone loss correctly, not a shape to be drawn — if it
emerges from the DRR on its own, the simulation is right.

**Note on all three:** these are the first features that would show *disease*
rather than anatomy. Everything shipped so far is measured or modelled from one
healthy dentition, and the provenance tiers say so. A pathology slider produces
geometry that is neither measured nor a literature mean but a *simulation*, and
it needs a fourth tier or a very loud label, or the atlas quietly starts
asserting things about a real person's mouth that are not true of it.

---

## Vascular structures — arteries and veins

**Arteries red, veins blue**, matching the yellow now used for nerve tissue, so
the neurovascular bundle reads at a glance.

The bundle in the mandibular canal is not a nerve alone: the inferior alveolar
**artery** (from the maxillary artery) and **vein** run with the IAN and share
its course, so the geometry already built for the trunk carries all three — the
canal lumen is the measured part and the split between its contents is not
resolved at 0.16 mm. The same is true of the incisive and mental branches. In
the maxilla the posterior, middle and anterior superior alveolar arteries
accompany their nerves, and the infraorbital artery runs with the infraorbital
nerve in its canal.

**What it needs:** a `vessels` layer with two materials; arterial and venous
courses derived from the nerve centrelines where they are genuinely companion
vessels, and separate geometry where they are not (the greater palatine and
sphenopalatine vessels have no nerve twin in this model). Provenance is the
usual problem — the canal is MEASURED, its division between artery, vein and
nerve is SCHEMATIC, and the atlas must not draw three tubes in a canal it only
ever saw as one lumen and imply otherwise.

---

## ~~Fix the inter-tooth contact boundaries~~ — RE-CUT 2026-09-02, one half left

`split_teeth.py` partitions the arch by arc position and then `refine_boundaries()`
moves the cuts off the sector planes and onto the necks with a watershed. That
function's own comment names where it still fails: *"Where two teeth are in true
contact the distance transform has no minimum to cut at."* With no waist to
settle into, the watershed boundary lands wherever the eroded seeds happen to
meet — a near-planar chord, sometimes well inside the crown.

**What it does and does not break.** It does not lose tissue: the wedge taken off
one tooth is labelled as its neighbour, so the assembled model is right and the
error exists only per tooth. It does distort anything measured PER TOOTH from the
mask — the CEJ ring is the live example, and a chord through the crown is the
most likely cause of the implausible 3.84 mm cervical scallop measured on tooth
29, which matters because the gingival margin is lofted from that ring.

**Why it gates the DRR** is in that section above.

**It gates ENAMEL too — settled by the operator 2026-09-02.** This document used
to say enamel was not blocked, on the grounds that `enamel.py`'s `outer_depth()`
measures against the tooth *union its neighbours*, so a contact face is interior
and no enamel is painted onto the cut. That is still true and it is not enough:
it only stops enamel being painted ONTO a bad cut, while the cap's extent, the
CEJ ring it is bounded by, and every per-tooth thickness figure are all measured
from a mask whose proximal surface the cut defines. CLAUDE.md always said enamel
was gated; the two documents contradicted each other and the operator resolved it
in favour of gating.

**What it needs.** A boundary criterion that does not depend on a distance
minimum — the midsurface between the two teeth's own bodies, or the intensity
dip where one resolves. Cost is compute, not hand work: the pulp tracings are
stored against `crop_origin_zyx` in VOLUME space, not against the split labels,
and the pulp is nowhere near the contacts, so a re-split does not invalidate
them.

**The honest caveat.** At a true contact the two enamel surfaces touch, and at
0.16 mm the scan may not resolve a boundary at all. Some of "the correct split"
there is a modelling choice rather than a measurement, which makes it a
provenance question as much as a geometric one. Decide that deliberately instead
of tuning until it looks right.

### What was done, 2026-09-02

`refine_boundaries()` now cuts each adjacent pair under an ADDITIVE cost metric
in a local crop, seeded from cores scaled to each tooth's own depth. The rules
are CLAUDE.md 120-126; the short version is that the old distance watershed had
no minimum to cut at, an intensity watershed fails by landslide instead, and an
additive cost has neither failure. Sheets are `tools/cbct/contact_tune.py`.

**The caveat above was decided, not tuned around.** Where no embrasure is open
the intensity term is flat and the metric degrades to the midsurface between the
two tooth bodies. That is a modelling choice and it is now a CONSISTENT one,
rather than wherever two erosions happened to meet — but it is still a choice,
and a per-tooth mask at a true contact remains derived-at-the-contact even
though the tooth either side of it is measured. If contact geometry ever carries
a claim of its own — and the bitewing is exactly that — this needs its own
provenance note rather than inheriting the tooth's.

### Gingival accuracy is DEFERRED to the intraoral scan — operator, 2026-09-02

The re-split rebuilt the collar and the result is mixed by the refit metric:
mean CEJ drop 1.60 -> 1.73 mm, teeth over 3 mm 4 -> 7, with 5 and 12 much better
and 13, 14, 15 and 18 worse. On screen the posterior margin actually scallops
MORE than before, so the metric and the render disagree — the drop measures how
hard the refit had to drag the raw ring, which is a statement about the input,
not the output.

The operator looked and accepted it as-is. **Do not spend more effort tuning the
gingiva before the intraoral scan lands**: it moves gingiva from derived to
measured and resolves this immediately, so work now is work twice. CEJ-to-crest
also barely moved (4.50 -> 4.46 mm against a healthy 1-2 mm), which is the
evidence that the contact chord was NOT the cause of the margin error — that
hypothesis in open question 2 is disproved, and the cause is still unknown.

### The half that is left: restoration bloom

Not a boundary-criterion problem, and re-cutting contacts does not touch it. The
zirconia on 19 and 30 saturates the volume's 3072 ceiling and its halo is
labelled as tooth, so the crowned teeth's OUTER contour is inflated against bone
and background. Restoration-density voxels are no longer divided with the
neighbour — they are claimed by the tooth the crown is cemented onto — but the
2000–2500 penumbra around them is still whatever DentalSegmentator made of it.

Fixing it means going back to the segmentation, not the split. Note before
trying: the ceiling means the restoration cannot be unmixed from the tooth by
intensity alone, because both are clipped to the same value.

### And a note for whoever generates a natural crown

The usual move — mirror the contralateral tooth — **does not work here**. 19 and
30 are BOTH crowned, so a natural crown on either would have to come from the
second molars or from population morphology. `derived` at best, arguably
`schematic`. The operator's intraoral scan (below) does not solve this either:
it measures the crown's surface as it sits, not the natural tooth underneath.

---

## ~~Enamel, dentin and cementum — before the DRR, not after~~ — MOSTLY DONE

Enamel shipped in 0.7.0 as 26 caps. Dentin exists in the radiograph as the tooth
less its enamel, pulp and crown, subtracted per pixel — no dentin MESH is drawn,
and none is needed for the DRR. Density per tissue shipped in 0.8.0 as
composition plus ρ, with µ(E) computed from it, exactly as this section asked.

**CEMENTUM IS STILL NOT BUILT**, and the reasoning below for why it must be
`derived` rather than measured stands unchanged. It is deliberately absent from
the radiograph: sub-voxel at 0.16 mm and barely denser than dentin, so it is
radiographically indistinguishable from what surrounds it.

The original text follows.

## Enamel, dentin and cementum — before the DRR, not after

Split the hard tissue into its actual constituents, each carrying a density. The
model currently treats a tooth as one homogeneous solid with a lumen cut out of
it, which is why the README's "what it is not" still says *no enamel/dentin
split*.

**This is sequenced deliberately ahead of the radiograph simulator.** A DRR is an
integral of attenuation along a ray. If every structure already carries a tissue
identity and a density, the ray can be integrated against *labelled geometry*
instead of against the 185 MB voxel volume — which is the one engineering problem
the DRR section flags as unsolved. Doing this first may turn the radiograph
simulator from a volume-shipping problem into a shading problem. Doing it
afterwards means building the DRR twice.

It also pays off immediately in the atlas itself, independent of any radiograph:
the enamel cap, the dentin bulk and the DEJ between them are what a tooth
cross-section is actually *about*, and caries depth (in the sliders above) is
meaningless without them.

### What separates and what does not

| Tissue | How it comes out | Standing |
| --- | --- | --- |
| **Enamel** | Thresholds. Densest tissue in the body, and well clear of dentin at 0.16 mm — the CBCT plan lists enamel/dentin separation as one of the reasons for this data. | **Measured** |
| **Dentin** | The remainder of the tooth solid once enamel, pulp and any prosthetic are removed. | **Measured** |
| **DEJ** | Falls out as the shared boundary. Not drawn separately, but it is the surface caries spreads along. | **Measured** |
| **Cementum** | **Will not threshold.** 20–50 µm at the CEJ, thickening to perhaps 150–200 µm apically — every part of it is sub-voxel at 0.16 mm, and it is barely denser than dentin besides. Build it as a thin shell on the root surface, CEJ to apex, thickening apically. | **Derived / exaggerated**, exactly like PDL thickness |
| **Zirconia on 19 and 30** | Thresholds far above enamel; already flagged in the artifact map as a separate `prosthetic` label. | **Measured, but lab work — not anatomy** |

The CEJ is already measured per tooth (Phase 3, step 3), so the cementum shell
has a real upper boundary to start from. The **cementodentinal junction has no
measured position at all** — it is wherever the authored shell thickness puts it.
Same failure mode as the PDL: measured in position, drawn thicker than the truth.

### Density, and how to store it

Store **composition and physical density per tissue**, not a single attenuation
coefficient. µ is energy-dependent, so a bitewing at 60 kVp and a pan at 70 kVp
attenuate the same enamel differently; baking one µ in now makes kVp
unsimulatable later, and kVp is itself a thing worth teaching.

Rough physical densities to start from — to be sourced properly, not left as
these numbers: enamel ~2.9–3.0 g/cm³, dentin ~2.1–2.2, cementum ~2.0, cortical
bone ~1.9, trabecular bone much lower and heterogeneous, pulp ~1.0, zirconia
~6.0. Whatever is used, cite it, and let the provenance labels below carry the
citation.

**What it needs:** nothing new from the scan. Enamel is a threshold within the
existing per-tooth masks, which already exist for all 28. Cementum is a script,
like the gingival collar. This is the most immediately buildable large item here.

---

## ~~Provenance label on every structure, in the UI~~ — DONE 2026-08-31

Every structure should state **how it was generated**, in the app, at the point
of selection — not only in the README and the docs.

The distinction already exists and is already carefully maintained in prose: the
README's measured / derived / schematic table, the Phase 3 provenance summary,
and Invariant 4's caveat block. What is missing is that **the model itself does
not carry it**. In `tools/manifest.mjs` provenance survives only as a
`(schematic)` suffix inside a display name, which cannot be filtered, cannot be
styled, cannot be cited, and quietly disappears the moment someone tidies the
names.

### The shape of it

A `provenance` field on every manifest entry — manifest is already the single
source of truth for layer, side and notation, and this belongs beside them:

- **`tier`** — measured / derived / schematic / simulated. (The fourth tier the
  pathology sliders will need is the same field; add it once.)
- **`method`** — one line, specific. Not "measured" but *how*: "hand-traced on
  axial slices, 0.16 mm CBCT"; "thresholded, then watershed out of its socket";
  "lofted from the measured CEJ, refitted to published cervical-line curvature";
  "centreline through the mandibular canal — the canal is measured, its contents
  are not".
- **`sources`** — citations, required for anything approximated. The maxillary
  nerve courses are textbook, and the atlas should say *which* textbook.

Worked examples of what each would say:

| Structure | Tier | Method |
| --- | --- | --- |
| Teeth, mandible, maxillae | Measured | Segmented from 0.16 mm CBCT |
| Pulp | Measured | Hand-traced per slice — no threshold separates it from dentin at this resolution |
| Apical foramina | Measured | Intensity-deficit integration across the canal cross-section |
| Inferior alveolar nerve | Measured *course*, schematic *content* | The canal void was traced foramen to foramen; the nerve inside it is drawn, not seen |
| Mental / incisive branches | Schematic | Course inferred; the foramen is now MEASURED from the traced mental canal (2026-09-03) |
| Infraorbital and mental terminal branches | **Derived** | Foramen and skin both measured; the path between them is Gray's, and only a stub is drawn (2026-09-03) |
| PSA, MSA, ASA | Schematic | Textbook course; superior alveolar canals not resolved at 0.16 mm. Cite the source |
| Infraorbital | **Derived** | Follows the hand-traced canal (2026-09-02); a tube of chosen calibre on a measured centreline |
| Gingiva | Derived | Collar lofted from measured CEJ |
| PDL | Measured position, exaggerated thickness | Both walls measured; drawn far thicker than ~0.2 mm, which is one voxel |
| Cementum *(once built)* | Derived | Authored shell on the measured root surface |

### Why it matters more than it looks

This is the machine-readable form of Invariant 4. A caveat paragraph describes
the *build*; a per-structure field describes the *object the user just clicked*,
which is where the question actually arises. It also unlocks small things that
are otherwise impossible: filtering the view to measured anatomy only, or tinting
schematic structures so the eye is told the same thing the text says.

**Built 2026-08-31**, as described: `provenance()` in `tools/manifest.mjs`
returns a `tier`, a `method` and `sources`, the detail panel renders it as a
coloured block under the selected structure, and invariant 6 fails the build if
any structure lacks one. 58 measured, 32 derived, 4 schematic.

Two things worth knowing that only appeared in the building:

- **The tier had to describe the geometry AS DRAWN**, not the best evidence
  behind it. The inferior alveolar nerve was the test case: its course is the
  measured canal, but what is rendered is a tube of chosen calibre on that
  centreline, so it is `derived` rather than `measured`, with the method saying
  which half was seen. Tiering by the strongest input would have quietly promoted
  half the atlas.
- **The `(schematic)` name suffixes are gone.** They were the only carrier of
  provenance before, and keeping them alongside a real tier meant saying it
  twice. The nerve layer's comment used to warn against removing them; the tier
  is what protects that distinction now, and it protects it better, because the
  build enforces it.

The `simulated` tier is defined and unused, so the anaesthetic diffusion and the
pathology sliders cannot ship without choosing a tier.

---

## Shade the landmark, do not invent the point — a rule for the whole atlas

**Operator's idea, 2026-09-01, and it generalises well beyond anaesthesia.**
Where a landmark is not resolved in this scan, do not place a point. Render the
REGION the literature says it is most commonly found in, and let its size carry
the uncertainty.

This came up because the anaesthesia item needs targets the scan does not give.
Tonight established that two of Malamed's constructions cannot be anchored here
at all: the infraorbital canal does not resolve, and the mandibular foramen's
landmarks need the ramus's posterior border and a coronoid notch that no field
of view ever contained. The alternatives had been (a) place a point anyway from
a published mean, which draws a confident dot on anatomy nobody measured, or
(b) omit the landmark, which teaches nothing. A shaded region is the honest
third option, and it is *more* useful for teaching than a point: the spread is
the clinically important part. A needle aimed at a mean is aimed at a place the
foramen is, in most people, not.

**Why it fits the provenance system rather than fighting it.** Every structure
already declares how it was made. A region says the same thing in geometry: its
extent IS the claim. A 2 mm blob and a 12 mm blob are different assertions, and
the reader does not have to open a panel to see which one they are looking at.

**How to build it, in the order the honesty degrades:**

1. **From a published dispersion.** Where a morphometric series gives a mean and
   an SD relative to a landmark THIS scan measured, the region is that
   distribution mapped onto measured bone. The infraorbital foramen is the clean
   case: 5.8–7.3 mm below the inferior orbital margin across several series, and
   the orbital rim is measured. That is a band, not a point, and drawing it as a
   band is simply telling the truth.
2. **From a landmark-relative construction with no dispersion quoted.** Malamed's
   mandibular foramen is here — ~19 mm below the coronoid notch, ~2.75 mm behind
   the ramus midpoint, with no spread given and, on this scan, without either
   reference. The region has to be sized from a separate anatomical series, and
   the structure must say that its *anchor* was unavailable, not just its
   position uncertain.
3. **From nothing but a textbook picture.** Do not draw it.

**What it needs:** a `region` tier alongside `measured` / `derived` /
`schematic` / `simulated`, rendered as a translucent volume rather than a
surface, and a UI convention that reads as "somewhere in here" at a glance —
probably a soft-edged isosurface rather than a hard shell, since a hard shell is
itself a false precision. The `simulated` tier is already defined and unused;
this is a sibling to it, not a special case of it.

**Do this before the anaesthesia item, not during it.** That feature will want
several of these, and inventing the convention while also modelling diffusion
would mean deciding twice.

---

## Local anaesthetic delivery, from needle to numb tooth

Show the injection techniques as *three-dimensional geometry*: the needle in the
soft tissue, the solution leaving the bevel, its spread through tissue, and which
nerves — and therefore which teeth — that spread actually reaches.

### Techniques worth covering

| | Target | Why it is worth drawing |
| --- | --- | --- |
| **Maxillary infiltration** (supraperiosteal) | Apex of the target tooth | The whole technique depends on the maxillary plate being thin and porous — the one place diffusion through bone works |
| **PSA, MSA, ASA / infraorbital** | Regional maxillary blocks | Their target nerves are already in the model, schematically |
| **Greater palatine, nasopalatine** | Palatal soft tissue | Both foramina are potentially measurable in the volume |
| **IANB** (Halstead) | Mandibular foramen, above the lingula | The classic, and the classic failure |
| **Gow-Gates** | Neck of the condyle | Higher target, larger bony landmark, catches branches the IANB misses |
| **Vazirani-Akinosi** | Closed-mouth, pterygomandibular space | The technique for a patient who cannot open — ties directly to the mouth-opening item below |
| **Long buccal, mental / incisive** | Terminal and soft-tissue supply | Explains why an IANB alone does not get you a mandibular extraction |
| **Intraligamentary, intraosseous** | PDL space, cancellous bone | Both target structures already exist in the model |

### Why this model is unusually well placed to do it

**The bony targets are measured.** The mandibular foramen and lingula, the
condylar neck, the mental foramen, the apices of every maxillary tooth, and the
mandibular canal itself are all real geometry from this patient's scan — so
"where the needle goes" is not an illustration, it is a position relative to
measured bone. Very little teaching material can say that.

**The failures are geometric, and therefore showable.** An IANB deposited too low
or too anterior misses because of where the foramen actually is. Contacting bone
too early means the wrong angle of approach. A buccal infiltration failing in the
adult mandible is a cortical-plate thickness fact, and the plate thickness is
*in the scan*. These are the things that are hard to teach from a diagram and
easy to show from a model.

### What it needs

- **Soft tissue that does not exist yet** — oral mucosa, the pterygomandibular
  space and raphe, buccinator, medial pterygoid. This is Phase 3 tier-3 work and
  gates the whole item. The maxillary infiltrations need much less of it than the
  mandibular blocks do.
- **A needle** as a positioned rigid body: insertion point, angulation, depth,
  bevel orientation. Gauge and length matter (25 mm long vs 20 mm short changes
  which techniques are even possible).
- **A diffusion field** from the deposition point — a scalar spreading through
  tissue, blocked by cortical bone, permeable where the plate is thin. This is
  the actual mechanism of the lesson and the reason the item is not just a video.
- **A nerve-territory map**, so a nerve inside the anaesthetised field marks its
  teeth numb. Partly present already: there is a measured branch to all 14 lower
  apices.
- **Aspiration** would want vessels — see the vascular item below. The inferior
  alveolar artery and vein share the canal, which is exactly why aspiration is
  taught.

**Provenance warning, and it is a serious one:** the needle path is authored, the
soft tissue it passes through is authored, and the diffusion is a *simulation* —
not measured, not a literature mean. This is the same fourth-tier problem the
pathology sliders raise, and here it is sharper, because a plausible-looking
depth-and-angle animation reads as clinical instruction. It needs the provenance
labelling above to exist first, and it needs to be loud.

---

## Open and close the mouth

Once there is enough soft tissue for it to mean anything, let the mandible move.

**It is not a hinge.** Mandibular opening is rotation in the lower joint
compartment for roughly the first 20–25 mm, and then translation as the condyle
runs forward and down the articular eminence. Animating a pure hinge through a
full opening puts the condyle through the eminence and is wrong in exactly the
way the TMJ is interesting.

### What it needs

- **A mandibular group in the scene graph.** Everything mandibular has to move
  together: the mandible, the 14 lower teeth, their pulp and PDL, the lower
  gingiva, the inferior alveolar nerve with its dental, mental and incisive
  branches. Today these are flat siblings in one glTF, so this is a real
  restructuring of the scene, not a transform on one node. Worth designing before
  the tree gets larger.
- **A condylar path — and it will have to be generic.** *Answered 2026-08-31 by
  `tools/fov-audit.mjs`:* the mandible is **cut through both rami**, with a
  172 mm² planar cap on the right FOV wall, 191 mm² on the left, and 156 mm²
  where the posterior wall slices the ramus coronally. Its full width is 82.0 mm,
  which is the 81.9 mm FOV exactly. A bicondylar breadth is around 120 mm, so the
  condyles were never in the box — and neither were the glenoid fossa or the
  articular eminence. There is no measured eminence slope to derive an opening
  path from, and the Gow-Gates target in the anaesthesia item above sits in bone
  this scan never saw. Use a published condylar path and label it schematic.
- **Muscles that deform rather than translate.** This is the real reason to wait:
  masseter, medial pterygoid and lateral pterygoid all change shape through the
  opening, and rigidly transforming a static belly with the mandible will look
  broken. Phase 3 step 5 fits the muscles to measured attachments; do that first.
  The lateral pterygoid is the one that *produces* translation, so it is the one
  that has to be right.

### What it buys

- **The mandibular anaesthesia techniques above.** IANB and Gow-Gates are given
  with the mouth wide open; Vazirani-Akinosi is defined by being closed. The
  techniques cannot be shown honestly in a fixed-occlusion model.
- **Occlusion**, eventually — contacts, excursions, and the difference between
  centric relation and maximum intercuspation.
- **The scan itself is a single frame**, so all of this is authored motion over
  measured geometry. Note also that the three CBCT exposures caught the mandible
  in different positions, which is a caution about the source data rather than a
  source of motion data.

---

## The rest of the skull — generating what the FOV never saw

Everything in the atlas stops at the edge of an **8 cm cube**. All three volumes
are 81.9 × 81.9 × 81.76 mm at 0.16 mm isotropic (see
[cbct-survey.md](cbct-survey.md) §2), aimed at three different places. Their
union is a dentition and its immediate surroundings — it is nowhere close to a
skull.

So the maxillary nerves currently run through empty space, the mandible ends
where the box ends, and there is no cranial context to orient any of it against.
For an atlas whose whole argument is *this is measured*, the boundary of what was
measured is presently invisible.

### What is missing, and why each matters

| Structure | Why it is wanted |
| --- | --- |
| **Glenoid fossa and articular eminence** | The mouth cannot open correctly without the eminence — see [Open and close the mouth](#open-and-close-the-mouth). **Confirmed outside every FOV** by the audit below. No longer necessarily generated: a small-FOV TMJ volume would measure it, though the fossa is the harder of the two to register — see below. |
| **Condyle and upper ramus** | The Gow-Gates target is the condylar neck. The audit below shows both rami sliced by the FOV walls, so the condyle is absent outright. **A TMJ volume would measure this cleanly**, registering on the mandible via the shared ramus. |
| **Pterygopalatine fossa, foramen rotundum, pterygoid plates** | V2's course. The maxillary nerves are drawn schematically already; without this bone they are schematic *and* floating. |
| **Infraorbital canal and rim, orbital floor** | The ASA and infraorbital nerve terminate here. Also the roof of the maxillary sinus, which *is* well resolved. |
| **Zygomatic arch and zygomaticomaxillary complex** | Masseter origin — needed the moment muscles are fitted to attachments. |
| **Cranial vault, base, nasal bones, hyoid, cervical spine** | Orientation and context only. Cheapest to fake, least at stake. |

### The FOV audit — done 2026-08-31

`tools/fov-audit.mjs` measures every shipped mesh and detects where the FOV cut
it, by finding planar caps sitting on a bounding-box face: truncated anatomy ends
in a flat wall, intact anatomy closes over smoothly. Results:

| | |
|---|---|
| **Measured anatomy spans** | 85.6 × 73.5 × 80.1 mm — against an 81.9 mm box per volume. It exceeds one FOV in x only because the mandibular volume is registered in alongside `centered`. |
| ~~**Mandible: cut through both rami**~~ | 172 mm² cap on the right wall, 191 mm² on the left, 156 mm² posteriorly. Width 82.0 mm = the FOV exactly. **Fixed 2026-09-01** by registering the mandible-focused exposure in: `FMA52748M` adds 12.0 cm³ and the rami are no longer truncated. |
| **Condyle, fossa, eminence** | **Not measured, and never could have been.** Bicondylar breadth is ~120 mm against an 81.9 mm box. |
| **Upper skull: NOT cut** | Caps of 4–18 mm² only, i.e. it closes smoothly. Its extent is a *segmentation* crop by DentalSegmentator, not an FOV limit. |

That last row is the useful one, and it changes the shape of this item.

**Some of the missing bone is not missing — it is unexported.** The upper skull
mesh stops where the label stops, not where the data stops, so there is measured
bone in the volumes above and lateral to it that has never been meshed. The
`maxillary` volume is the clearest case: [cbct-survey.md](cbct-survey.md) §3
found it to be a **sinus / root-apex / nasal-anatomy volume** whose upper crowns
fall below the FOV floor, which is why it was set aside as an arch source — and
it is currently used for nothing at all. It covers a good part of the mid-face
wanted in the table above: orbital floor, infraorbital canal and rim, sinus
walls, nasal bones.

**Partly done, 2026-09-01.** The `centered` volume's share of this is recovered:
`FMA53649U` ships the 3.6 cm3 the maxilla's 22 mm crop was discarding — posterior
mid-face and pterygoid region, plus the infraorbital rim and zygomatic process
bilaterally. Two things were measured while doing it and are worth not
rediscovering:

- **There is no large body of unlabelled bone in `centered`.** Tissue at or above
  400 HU carrying no label at all comes to 3.7 cm3 scattered across 1,979
  components, the largest 286 mm3 — noise, not a zygomatic arch. The nnU-Net
  label had already found essentially all of it; the loss was at EXPORT, not at
  segmentation.
- ~~**The remaining prize is the `maxillary` volume**~~ **Done 2026-09-01.** It
  is registered in (`docs/transform-maxillary-to-centered.json`) and ships 23.0
  cm3 as `FMA53649M`. Its upper-skull label holds 54.0 cm3 against `centered`'s
  31.3, and the atlas now reaches 75 mm above the occlusal plane instead of 37.
  It remains **essentially free of crown artefact** (max 2605 HU against
  `centered`'s saturated 3072) because the zirconia sits outside its field of
  view — worth remembering for anything that needs clean mid-face intensities.
  Its own label still stops before the field of view does, so there is more.
- **The mandibular exposure is in too**, on the same pattern
  (`docs/transform-mandibular-to-centered.json`, already fitted for the arch
  work): 32.1 cm³ of mandible against `centered`'s 21.6, contributing 12.0 cm³
  as `FMA52748M`. All three volumes now supply geometry.

**So the order is: export what was already measured, then generate only the
remainder.** Re-segmenting the upper skull to the full FOV and bringing the
`maxillary` volume into the build is Fedora work on data already in hand, and
every millimetre it recovers is one that does not have to be invented. Do it
before fitting any template.

### A TMJ scan would MEASURE the part that matters — noted 2026-09-01

The operator's machine offers a small-FOV TMJ volume, left and right. That
captures the condyle and the coronoid process — precisely the anatomy this
section exists because we do not have, and the only part of the missing skull
with real clinical function. **It supersedes generating them.** The operator is
deliberately spacing the exposure out, which is the right call; nothing here is
urgent and everything below is about making sure that when it is taken it is
right the first time, so it never has to be taken twice.

**The trap, and it is not obvious: one TMJ volume contains two structures with
DIFFERENT rigid parents.** The condyle belongs to the mandible; the glenoid
fossa and articular eminence belong to the temporal bone, and so to the cranium.
CLAUDE.md's rule that one transform cannot serve both jaws applies here exactly:
that volume will need **two** registrations, and each needs its own overlap.

- **The condyle registers on the mandible**, and its handle is the RAMUS. So the
  FOV should be positioned to include as much ramus below the condyle as it can
  — that shared bone is the entire basis of the fit. A volume containing a
  beautifully resolved condyle and no ramus is unregisterable and therefore
  worthless to this atlas.
- **The fossa and eminence register on the cranium**, and that is the harder
  one, because the cranial bone we have is MID-FACE — anterior — while the fossa
  is posterior-superior. The overlap may be poor or absent. If the machine
  allows any latitude in positioning, favour including the zygomatic arch: it
  runs between the two and is the only plausible bridge.

**Measured now, so the FOV can be positioned rather than guessed** (atlas frame,
LPS mm — the point is the shape of the requirement, not the numbers themselves):

- The mandible plus ramus currently reaches **z 16.6** at the top, and the bone
  within 10 mm of that top sits at **y 12.4–23.5**, laterally around
  **|x| 35–45**. So a TMJ volume needs to reach INFERIORLY far enough to take in
  roughly the **top 10–15 mm of ramus below the condylar neck**. That is the
  whole mandibular registration handle; without it the condyle cannot be placed.
- For the fossa, the bridge exists: there are **18.5 k mesh vertices of cranial
  bone lateral of |x| > 32 mm**, spanning y −21.9 to 28.8 and z −7.1 to 67.3 —
  the zygomatic process region and posterior enough to be plausible overlap. So
  favour a position that catches the **zygomatic arch**, and the fossa has
  something to register against rather than nothing.

**Worth settling before the appointment:**

- **Match 0.16 mm isotropic** if the Vol. 1 protocol offers it, so it composites
  with the existing three without a resampling step.
- **Record the jaw position** — maximum intercuspation or rest — explicitly, and
  prefer whatever the existing volumes were taken in. Condyle-to-ramus is rigid
  either way, so the mandibular registration is safe; condyle-to-FOSSA is not,
  and two volumes in different positions would place the joint differently. That
  is interesting rather than fatal — it would show the joint in two positions,
  which is exactly what [Open and close the mouth](#open-and-close-the-mouth)
  wants — but it must be RECORDED, never averaged.
- **Both sides**, and note the mental foramen asymmetry already on record: the
  right mandibular canal centreline is the weaker of the two, so the right joint
  is the more valuable of the pair if only one were possible.
- **Export DICOM, not the vendor's viewer file.** The survey already found a
  Windows `.exe` shipped alongside the imaging data and correctly refused it.

**If it happens, this section shrinks to the cranial vault and the zygomatic
arch** — orientation context, the part the wishlist already calls cheapest to
fake and least at stake. The generation options below stay for that remainder.

### How to generate the remainder, in order of preference

*(For the condyle, fossa and eminence, see the TMJ scan above first — measuring
beats all three of these, and the whole argument of this atlas is that measured
anatomy is the point.)*

1. **Template morphed to the measured boundary.** Take a skull mesh and fit it so
   that where it overlaps measured bone it *matches* — then extrapolate outward
   from that fit. The generated skull is then this patient's size, proportion and
   asymmetry rather than a generic one, and it joins the measured mandible and
   maxillae without a seam. This is the only option that is genuinely
   "generative" rather than "borrowed", and it is the one worth the effort.
2. **A permissively licensed skull, registered and scaled.** Faster, and honest
   if labelled. **Licence trap:** BodyParts3D is CC BY-SA, and Invariant 3 means
   anything derived from it inherits ShareAlike. Pulling a skull from there would
   re-infect a tree the CBCT work deliberately freed. Source something
   public-domain or permissive instead, and keep it in the atlas-derived tree.
3. **Authored from scratch.** Most work, least benefit — a hand-modelled cranial
   vault teaches nothing the other two do not.

### The provenance problem is worse here than anywhere else

Every other structure in the atlas is measured, derived or schematic *as a
whole*. A generated skull is **measured and invented in the same mesh**, with the
join running through the middle of the mandible. Per-structure provenance is not
enough; this needs provenance **per region**, or the mandible starts asserting a
ramus height nobody ever measured.

Two things follow, and they are the interesting part of this item:

- **Draw the FOV boundary.** The extent of each 8 cm box is a real, knowable
  surface. Showing it — as a clip plane, a fade, or an outright change of
  material — turns "where the data stops" from a caveat into something visible.
  That is a better answer than a footnote, and it is the honest version of a
  feature that is otherwise pure decoration.
- **Never feed a generated skull into an extraoral DRR unlabelled.** A simulated
  panoramic or cephalometric radiograph needs far more skull than 8 cm, so it
  would be computed largely from invented bone — a fabricated radiograph of a
  real, identifiable person. Intraoral projections stay inside measured data and
  are fine; extraoral ones are not, and the difference must be enforced in code,
  not left to a label.

**What it needs:** the FOV audit (cheap, and possible today); then a skull source
with a licence that does not contaminate; then a fitting script. No new imaging —
the missing anatomy is missing permanently, since re-scanning to fill it would
mean irradiating a healthy person for an atlas.

---

## Re-derive the nerve courses from a primary anatomical source

The maxillary and terminal mandibular nerve courses were built against the
Wikipedia anatomy articles, and `provenance()` cites exactly that, because
citing what was actually used is the whole point of the field.

Upgrading the source is worth doing. **The trap is that it is not a citation
change.** Swapping `SRC.wikiSA` for a better reference without re-deriving the
geometry would be false attribution — it would credit a book for a course it did
not produce, which is worse than an honest citation of a weaker source. The work
is: re-check each course against the reference, adjust the geometry where they
disagree, *then* change the citation.

Candidates, and they are not equivalent:

| Source | Why |
| --- | --- |
| **Gray's Anatomy** | The obvious upgrade, and the 1918 edition is public domain — but it is a general anatomy, thin on the dental branches, and its plates predate the imaging that settled several of these courses. |
| **Netter's Head and Neck Anatomy for Dentistry** (Norton) | Written for this exact purpose. Almost certainly the better reference for the superior alveolar plexus and the infraorbital canal. |
| **Malamed, Handbook of Local Anesthesia** | The one to use if the [anaesthetic delivery](#local-anaesthetic-delivery-from-needle-to-numb-tooth) item is built, because it describes these nerves in terms of where a needle goes — which is what that feature needs and what a general anatomy does not give. |

Doing this *with* the anaesthesia item rather than before it would mean deriving
each course once, against the source that item needs anyway.

**Decided 2026-08-31: that is the plan.** The operator wants the courses
re-derived *before* the anaesthesia modelling rather than after, so the
derivation happens once against Malamed — the reference that feature needs — and
the citation follows the work instead of preceding it.

### Partly done 2026-09-01 — and the shape of the rest has changed

The maxillary trunks were re-derived against Malamed and are now **confined to
measured bone**. They had never been tested against bone at all: 72% of that
mesh lay outside it, a median of 3.5 mm and up to 10.1 mm out, floating in the
sinus. It is now 0.5 mm median and 1.2 mm maximum, which is the tube's own
radius — the centrelines are in bone. `SRC.malamed` is cited on that structure
only, because that is the only geometry actually re-derived against it. The tier
stays `schematic`: bounded by measured bone is not the same as observed.

**Two of Malamed's landmark constructions cannot be anchored to this scan, and
both were checked, so nobody spends the time again:**

- **The infraorbital canal does not resolve.** Filling the upper-skull label per
  slice and taking the interior voids returns the sinuses and the nasal cavity
  (aspect ratios 1.1–1.7) and no thin tube anywhere. The infraorbital foramen
  therefore cannot be measured; placing it from the orbital rim plus a published
  5.8–7.3 mm offset is the best available, and would be *derived*, not measured.
- **The mandibular foramen construction needs bone that is not there.** Malamed
  places it ~19 mm below the coronoid notch and ~2.75 mm behind the ramus's
  anteroposterior midpoint. Both need the ramus's posterior border, and the
  ramus is still cut by the field of view at y 23.7 against a box edge of 23.85
  *even with the mandibular exposure registered in*; the condyle was never
  inside any of the three FOVs. The superior-border profile rises to the
  coronoid and then stops, so there is no second peak to put a notch between.

**What is left of this item** is the mandibular terminal branches and the
palatal nerves, plus deciding whether an offset from a measured orbital rim is
worth having for the infraorbital foramen. The maxillary trunk topology is done.

---

## The proximal nub — the arch split re-cut, then CLOSED, 2026-09-03

**What it was.** Every premolar and molar, worst in the maxilla, carried a
compact mushroom on its proximal surface at the cervical. It was in the label,
not the mesher.

**What caused it.** The contact cut. `_cut_pair()` grew each tooth from its own
core under a cost that is cheap through bright tissue and dear through dark, so
the boundary would settle in the interproximal embrasure. Enamel is the
brightest tissue there is — so a rim of it is the cheapest path in the crop, and
a front that reached the contact could race along the OUTSIDE of its neighbour's
enamel for less than the neighbour paid to cross its own dentin and get there.
One tooth ended up wearing a rind of the other.

**The fix.** A second cost term: depth in the union of the two teeth. At a true
contact the union is locally thick, so the interior stays cheap and the boundary
is still free to settle in the embrasure — but a path hugging the outer surface
is shallow along its whole length and now pays for it. Plus a guard: no voxel
may be kept by a tooth when the other's core is nearer in a straight line by
more than 1 mm.

**Result.** The nubs are much smaller and the arch reads cleanly, but they are
NOT entirely gone. Only teeth 12 and 13 moved by more than 4% (−5.9% and +5.1%),
which is the contact that was worst; everything else is within 4% and 0.5 mm.

**CLOSED, 2026-09-03 (same evening).** A seventh attempt was made and reverted
by the operator on sight — "it looks worse now" — and it settled the question
this section had been leaving open. The nub was isolated at last: rebuild each
crown's contour from the part of its surface that is not at a contact, and
clip to it. That removes the nub. It also proves the nub cannot be removed.

- The clipped material lies 3.2–4.0 mm below the occlusal end; the measured
  contacts lie at 2.9–5.6 mm. One band. There is no height at which the two
  can be separated.
- Give a pair its contact back after clipping and the nub returns exactly, as
  a peg — from voxels the clip had itself taken.
- The clip opens every interproximal contact from 80 µm to 1.68 mm.

It is also **not** a mislabelled neighbour cusp, which was the standing
hypothesis: flood each tooth from its own core through dense tissue (>500 and
>700 HU, face connectivity) and 0.0 mm³ is unreachable on all 28. The earlier
probe that seemed to show an air gap between the nub and its own tooth was a
single straight ray through a fissure.

Worth recording because all three proxies IMPROVED — mesiodistal crown width
against Wheeler went from +1.08 mm to +0.16 mm mean error, contralateral
asymmetry from 3.48% to 3.06%, interpenetration held at 0.0000 mm³ — and the
build was still worse. See CLAUDE.md 183–185. **Do not attempt an eighth fix.**
This is the intraoral scan's job.

## Every posterior contact is bridged in the segmentation — 2026-09-03

Found by the operator: isolate an upper premolar or molar and a disc about 3 mm
across is stuck to its proximal surface at the cervical. The neighbour has a
matching one 0.3–1.4 mm away — at teeth 3 and 4 both sit at (-17.6, -18.5,
-10.1) — so the two teeth appear to share material.

**It is in the mask, not the mesher.** Meshing the split label alone, with no
grey-level blending at all, reproduces the disc exactly. 2.5–7.3 mm³ per tooth,
HU 930–1750, and nnU-Net labels every voxel of it `upper teeth`.

Two mesher-side fixes were tried, measured, and reverted:

- clamping the surface to a 3-voxel band around its own mask changed **nothing**
  (0.0% difference) — the surface never strays that far;
- widening the grey/shape blend ramp across the embrasure moved tooth volumes by
  0.4% and left the disc untouched.

The cause is resolution. DentalSegmentator infers at 0.43 mm; two enamel
surfaces in contact are one voxel apart; the label bridges them wider than
either crown, and the arch split then divides the bridge rather than removing
it. **There is no gap to find at any threshold, because the teeth really do
touch.** Shaping the proximal contour by hand would be inventing it, which is
what everything else in this atlas exists not to do.

**Wait for the intraoral scan.** It measures the crown surface directly, at a
resolution where a contact is a contact, and it is the only thing that can
settle this. Until then the atlas is honest about it: the contact region is
segmented, not observed.

Do NOT try to shave the protrusions off. The erosion test that isolates them
finds every cusp tip too, at the same size and the same density.

## Machine-assisted pulp: the correction loop works — 2026-09-03

`tools/cbct/pulp_learn.py`. Predict a tooth's pulp, the operator corrects it in
the slicer, retrain on the correction, predict the next.

**Round one.** Trained on his dense tracing of tooth 31 (plus six older sparse
ones), predicting tooth 30. He kept 70% of it, deleted 30%, and added another
24% — and where he edited is exactly where the diagnostics said it was weak:

| band | predicted | he corrected to | old 2026-08-30 trace |
| --- | --- | --- | --- |
| coronal third (crowned) | 28.9 mm³ | **14.8** | 7.7 |
| middle third | 59.2 | 56.1 | 32.8 |
| apical third | 7.2 | **16.8** | 12.2 |

Over-generous under the crown and half too thin apically, as measured before he
touched it. His correction also settles a question the numbers could not: in the
crowned third the model's 28.9 mm³ was too much and the old trace's 7.7 too
little, and the answer is 14.8.

**Round two.** With tooth 30 corrected, held-out tooth 19 improves sharply:

| training set | Dice on held-out 19 |
| --- | --- |
| his 31 only | 0.306 |
| his 31 + 6 older sparse traces | 0.398 |
| **his 30 + 31, both dense** | **0.470** |
| his 30 + 31 + the 6 old ones | 0.464 |

Two corrected teeth beat one dense plus six sparse, and past that point the old
sparse traces cost more than they add. Against the ~0.563 that two careful
human tracings of one tooth score against each other, 0.470 is about five sixths
of the way there. `--also` is scaffolding to drop after the third tooth.

**Do not read Dice(prediction, his correction) = 0.727 as accuracy.** He started
from the prediction, so it is anchored to it. The held-out number is the honest
one.

## Where the pulp stands after 0.7.0 — 2026-09-05

Four teeth are now hand-traced or hand-corrected in the slicer: **31, 18, 3 and
30**. Twelve are machine predictions from `pulp_learn.py` trained on those four,
with the growth threshold split at the CEJ. The twelve ANTERIOR pulps are
untouched and still ship from `pulp-v2`.

**The operator's read of 0.7.0:** teeth **18 and 19 look fantastic**; the
**PREMOLARS are "a bit silly all around"** and he wants to trace them by hand
later — explicitly NOT now, and they are acceptable as shipped. That is teeth
4, 5, 12, 13, 20, 21, 28 and 29. Do not spend effort tuning them; the answer he
has already chosen is tracing, not parameters.

**Tooth 30 is the last suspect label.** It is the only remaining 2026-09-04
tracing, at 86.77 mm3, and it differs from its predicted contralateral (19, at
68.0) by 22% — the same direction and rough magnitude that tooth 31 turned out
to be wrong before it was retraced (97.82 → 72.08). If it is fat by 31's factor
its true volume is ~64 mm3, which would bring the pair to within about 5%.
Retracing it is the single highest-value pulp job left.

**Directories, as of 0.7.0:** `traced-pulp-v2/` holds the four tracings (plus
`provenance.json` and a timestamped backup of the pre-retrace tooth 31);
`predicted-pulp-v8/` holds the twelve predictions; `pulp-ship-070/` is the
assembled sixteen that were meshed, and `pulp-stl-070/` the meshes. Note that
`pulp_learn.py` writes `U<universal>-pulp.npy` unless `--fma` is passed, which
is CLAUDE.md 202 and cost a silently wrong build.

## THE OPERATOR'S READ OF THE PULPS — 2026-09-09, and it reorders the job

**He looked at the shipped pulps and told me what he sees. This is evidence, and
it overrides the volume metrics below wherever the two disagree** — the standing
rule of this project is that his clinical read is the measurement and my number
is the thing that is probably blind.

| Tooth | His read | Status in the pipeline |
| --- | --- | --- |
| **19** | **"the best looking pulp of all the molars and premolars"** | **a PREDICTION**, never hand-traced |
| 18 | "isn't too far off" | hand-traced 2026-09-05 |
| **30, 31** | **"need some help"** | **BOTH hand-traced — and they are the TRAINING SET** |
| 2, 3, 14, 15 | "all the maxillary molars" need help | 3 is a light traced pass; the rest predicted |
| The eight premolars | **"need a TON of help, they look not good at all"** | all predicted |

### Three things follow, and the third is the important one

**1. It confirms the tooth 30 suspicion, from the opposite direction.** The
metric flagged the 30/19 pair as 22% apart and guessed 30 was fat. His eye says
19 is the best pulp in the mouth and 30 needs help. Same conclusion — but the
metric could only see that the PAIR disagreed, and could not say which member
was wrong. He can. Do not read the 22% as a fact about tooth 30 again; read it
as a fact about the pair.

**2. "The reference tracing that 31 is" is no longer safe to say.** That phrase
is in `traced-pulp-v2/provenance.json` and it is load-bearing — tooth 3 was
weighted against it. Tooth 31 was already retraced once (97.82 → 72.08 mm³) and
he is saying it *still* needs help, so the retrace improved it without
finishing it. Nothing should be described as the reference until he says it is.

**3. THE TRAINING SET IS THE WEAK LINK, AND THAT IS LEVERAGE.**
`pulp_learn.py` trains on the hand-traced labels — its documented shape is
`--train 30,31`. So the two teeth he says need help are the two teeth every one
of the twelve predictions was learned from, and each prediction inherits their
error. That changes what the tracing time buys:

- **Retracing 30 and 31 improves all twelve predictions at once**, because they
  are re-learned from better labels.
- **Correcting a prediction improves one tooth**, and if the labels are still
  wrong the next prediction is still wrong.

So the order that follows from his read is **30 and 31 first, then re-run the
prediction and LOOK before tracing anything else.** The maxillary molars and the
premolars may improve on their own, and whatever is still wrong after that is a
much better-informed target than it is today. It also means the premolars —
which he rates worst — may be the *last* thing worth tracing by hand rather than
the first, despite being the worst-looking, because they are the furthest
downstream of the labels.

### Tooth 19 has NEVER been traced — checked 2026-09-09, and here is why it feels
### like it was

He recalled hand-tracing "the lower left molars 19 and 18" and doubted the
record. **Half of that is right, and the check is worth keeping so nobody
re-runs it.** Verified directly against the label volumes rather than the
filenames:

- **Tooth 18 IS his tracing** (2026-09-05) and it is a lower LEFT molar, so that
  half of the memory is correct.
- **Teeth 30 and 31 are lower RIGHT molars** — that is the pair he was thinking
  of as 18/19.
- **There is no tooth 19 pulp tracing anywhere in the CBCT tree.** Tooth 19 is
  `FMA55704`; the only "traced" directories (`traced-pulp-v3`,
  `pulp-final-traced`, `pulp-stl-traced`) hold `FMA55705` and `FMA55706`, which
  are teeth **30 and 31**.
- **Why 19 feels traced: it was the target of the very first `pulp_learn.py`
  pilot.** `predicted-pulp/pulp-19.json` records `train: 30, predict: 19`, and
  its own provenance string says "Open it in slicer.py and correct it before it
  is used for anything." So 19 is the tooth he spent the most slicer time
  *looking at* — reviewing the first prediction the tool ever produced. Review
  time, not tracing time.

**A methodological note, because I got this wrong first.** My initial check said
all four label files were mislabelled. That was my own bug: I assumed the label
index in `split-v3/lower_labels.npy` matched `split.json`'s list order, and it
runs REVERSED. Solving the voxel→world transform properly (array axes `(2,1,0)`,
world = origin + 0.16·voxel) matches all 14 lower teeth to 0.01 mm mean
residual, and under that map **all four files are correctly named.** Do not
trust a label index against this JSON without solving the transform first.

### THE RISK IN RETRACING 30: it may take 19 with it

Current volumes: **19 = 68.02 mm³** (prediction, v8), **30 = 87.70**,
**31 = 72.08**, **18 = 64.95**. Tooth 19 is his best-looking pulp and it is the
contralateral of tooth 30, which he says needs help — and 30 is a training
label. So retracing 30 thinner and re-running the model **will change 19**, and
19 is currently the thing most worth not breaking.

**Snapshot tooth 19 before retraining and compare after.** If the new 19 is
worse, that is evidence about the model rather than about tooth 30, and it needs
his eye either way. The pilot's first 19 was 108.16 mm³ against today's 68.02,
so this pulp has already moved a long way across versions.

**Not yet asked:** whether he wants to spend the weekend that way. The premolars
are the ugliest and there is a real argument for just tracing them. This is his
call and the answer is not obvious from here.

## Correct the TWELVE predicted pulps — the standing job

**Corrected 2026-09-09: this section said fourteen, said only 30 and 31 were
traced, and said to start with tooth 18. All three were stale** — superseded by
[the section directly above](#where-the-pulp-stands-after-070--2026-09-05),
which is authoritative. Tooth 18 was traced on 2026-09-05 and tooth 3 the same
day. Anyone following the old text would have re-traced work already done.
Verified against `traced-pulp-v2/` in the CBCT tree: `pulp-18`, `pulp-30`,
`pulp-31` and `pulp-3` all present.

Every molar and premolar pulp is in the atlas. **Four are hand-traced — 31, 18,
3 and 30.** The other **twelve** are predictions nobody has reviewed, and they
are the only structures here in that position. Correcting each one in
`slicer.py` takes it from `derived` to `measured` AND makes the next prediction
better — the loop measured 0.306 → 0.398 → 0.470 as labels were added.

**The twelve are teeth 2, 14, 15, 19 and all eight premolars** (4, 5, 12, 13,
20, 21, 28, 29).

**Start by RETRACING tooth 30, not by correcting a prediction.** It is the
highest-value pulp job left and the reasoning is in the section above: it is the
last remaining 2026-09-04 tracing, 22% adrift of its predicted contralateral in
the same direction tooth 31 proved wrong before *it* was retraced.

    slicer.py nrrd/centered.nrrd traced-pulp-v2 --tooth 30 \
        --mask traced-pulp-v2,predicted-pulp-all

**Then the upper molars — 2, 14 and 15** (not 3; it is done), whose predictions
sit at 75-79% inside their own tooth masks, the lowest of the set. Then tooth 19.

**The eight premolars come last and are NOT a parameter problem.** He has
already chosen tracing as their fix and has explicitly deferred it — "a bit
silly all around but we'll go through tracing on them later, not worth it at the
moment". Do not tune them.

**A record-keeping problem worth fixing while in here:** `traced-pulp-v2/`
carries a `traced.json` describing only `pulp-31` and a `provenance.json`
describing only `pulp-3`. Teeth 18 and 30 have label files and no entry in
either. That gap is what let this section go stale unnoticed — **write the
provenance entry as each tracing is finished**, not afterwards.

## The ML did not help the mental canals, and here is why — 2026-09-03

Worth recording so nobody repeats it. Trained on the operator's complete LEFT
mental canal and asked for the right — a genuine held-out test, since the 24
sections he did manage on that side were never shown to the model — it scored
Dice 0.483 with recall 0.662, and added 103 mm³ of canal.

**None of it was where it was needed.** His right-side blanks are sections 20-32
and 37-43, and the last seven are the anterior end at the foramen. The model
filled the middle gap and extended the canal 18 mm POSTERIORLY, and moved the
anterior end by 0.2 mm. The anterior sections are blank because the canal is
genuinely not visible there — the same data defeats the model that defeated the
operator, which is the one failure mode a classifier trained on this scan cannot
argue its way out of.

It also exposed a real bug in `buccal_foramen`: given the longer canal it put
the "mental foramen" 18 mm posteriorly, where the mandibular canal legitimately
runs close to the buccal cortex under the external oblique ridge. Only the
anterior third is searched now (CLAUDE.md 150). The shipped landmark is
unchanged.

The mental canal in the atlas therefore remains the operator's tracing alone.

## The pulp is worth redoing on the slicer — 2026-09-03

The pulp is the atlas's most laboriously hand-made structure: 28 teeth, three
rounds, 723 mm3, and it is `measured` on the strength of that work. It was also
traced under the worst version of the old workflow — sparse axial sections,
1.6 mm apart, which leave-one-out scored at Dice 0.076 because consecutive
outlines of a wandering canal do not overlap. What shipped is good because the
operator worked around the tool, not because the tool was adequate.

`slicer.py --tooth 30,31` crops to a tooth, names the structures `pulp-<n>` and
lets every slice be painted with the coronal and sagittal views live alongside.
His own read: "we could really overhaul that modelling with the new tool."

~~Outstanding from the original pulp work: tooth 31 shows two distal canals in
the tracing.~~ **RESOLVED 2026-09-05, and this entry had it backwards.** It was
never an anatomical finding to carry — it was the operator reporting a DEFECT.
His words: *"our model at the time was fundamentally flawed BECAUSE it showed 2
distal canals. There is clearly 1 canal in the distal root of 31."* Recording a
defect report as an open question about the anatomy sent it to the wrong list
and left it sitting for two days.

He retraced 31 on the slicer on 2026-09-05 and it is fixed. Below the chamber
floor the old tracing had FIVE components — the two real canals, a spurious
third branch of 3.94 mm3 running z 72-109, and two fragments — against the new
tracing's TWO, one per root, both full length. One canal in the distal root, as
he said.

**Tooth 18 traced on the slicer — 2026-09-05, and it carries a LATERAL CANAL.**
The operator's read: a lateral canal leaves the **mesiolingual root just below
mid-root and runs toward the distal aspect** of the tooth. It is his finding
from scrubbing the volume, and it is the anatomy — see the memory rule that his
clinical read is evidence, not preference. Two things follow. It is a real
endodontic feature the atlas should carry rather than smooth away, and it is
exactly the structure no voxel classifier here will ever propose: a lateral
canal is one to two voxels across, branching off-axis, and rule 160's
chamber-classify/canal-track scheme routes between the chamber and the MEASURED
apical foramina — a lateral canal ends at neither, so nothing in the current
pipeline is even looking for it.

His tracing is 64.95 mm3 against the prediction's 144.9. He deleted roughly
seventy per cent of what the model proposed, most of it in the middle third,
which is the same region the lateral canal is in.

## The mental foramen — traced 2026-09-03, and my diagnosis was wrong

**Correction first.** On 2026-09-02 this section said the mental foramen sat
0.5 mm outside the mandible and about 4 mm too low. It did not. I measured it
against the mandible as the CENTRED volume reconstructs it, and that
reconstruction stops at z -44.5 and cuts the bone off; the real inferior border
is at z -59, in the mandibular exposure, which the atlas has carried as
`FMA52748M` since 0.4.0. Against the whole mandible the old landmark sat 14 mm
above the inferior border, inside the bone, roughly where a mental foramen
belongs. See CLAUDE.md 141.

What was true is that the segmented canal does not reach the foramen — on the
right it stops 11 mm short of the premolar window — so the landmark was the end
of a curve rather than a foramen.

**Now traced.** Both canals, 80.3 and 87.2 mm³, within 8% of each other and
traced independently. The foramina come out 15.6 and 15.0 mm above the inferior
border and 19.0 and 20.9 mm from the dental midline, which is symmetric and
where the literature puts them, and 3.0 and 2.8 mm from the projected points.
`docs/cbct-mental.json`; both `nerve.py` and `nerve_face.py` read it.

The operator flagged low confidence — the trabeculation makes the sections hard
to read — and one consequence is visible: the last few millimetres of the right
tracing hook medially, which is why the facial normal is no longer searched
about the canal's own tangent.

**Round 2 is traced and shipped (2026-09-03).** 24/44 sections on the right and
39/39 on the left — he reported several right-side slices where nothing was
discernable. It also settled what the landmark is: the anterior end of a
mandibular-canal tracing is NOT the mental foramen, because the canal continues
forward as the incisive canal. The foramen is the canal's closest approach to
the buccal plate, which lands at z -42.7 and -43.3, 23.6 and 21.8 mm from the
dental midline, and makes the two sides' facial branches agree for the first
time. See CLAUDE.md 150.

**The scrollable slice viewer is built** (`tools/cbct/slicer.py`), which retires
the contact sheet for everything from here. He chose it over exporting to
imaging software he already knows, deliberately: that software is not available
on Linux, and the precedent is worth setting in our own tool.

**Round 2 sheets were cut on his round-1 tracing** (`trace-mental/`, round 1
archived in `trace-mental/round1/`). The sections are now perpendicular to the
canal's local tangent rather than to a straight chord, which is what made round
1 hard: measured against his own tracing, round 1 put the canal a median 3.3 and
3.6 mm off tile centre, round 2 puts it 0.40 and 0.20 mm. Tiles are 12.2 mm at
4x rather than 16.2 mm at 3x, and the frame no longer rotates between sections.
When it comes back, re-import and everything downstream moves on its own.

### The face itself is measured and not in the atlas — the next real step

Every terminal branch's true termination has been measured on the operator's own
skin and is recorded in `docs/cbct-nerve-face.json`, but nothing renders that
surface, so the branches are drawn as 5–7.5 mm stubs instead of running their
full 12–33 mm. A soft-tissue surface would be `measured`, is already present in
both focused exposures, and would let the whole facial nerve supply be drawn to
its real extent — one constant, `STUB_MM`, is all that stands in the way.

It is also this person's FACE, which is his call and nobody else's.

## The nasolacrimal ducts are NOT in the atlas, deliberately — 2026-09-02

They came up while hunting the infraorbital canal: a tube detector found both of
them unprompted, 19-34 mm long, at bone fractions of 0.36-0.52, in the right
place bilaterally. The operator asked for resolved structures to be added, and
these were not added. Two reasons, and the second is the one that decides it:

- **My extraction was fragmentary.** The detector that found them was tuned for a
  nerve canal, whose lumen is soft tissue. A nasolacrimal duct drains into the
  inferior meatus, so its lumen carries AIR — the wrong band entirely, and the
  masks it produced caught slivers. Ring detection in axial planes, which is the
  correct geometry for a vertically-running duct, returned nothing at any
  threshold from 350 to 650 with or without closing.
- **The operator declined to trace them**, saying he does not know the anatomy
  well enough to be comfortable marking them. That is the answer, not a gap to
  work around. Everything in this atlas carries a provenance claim, and nobody
  can vouch for these — so they stay out until somebody can.

Trace sheets exist (`trace-canal/nld-{left,right}.png`) if that changes. Note
before retrying: the sheets were cut perpendicular to a prior axis derived from
the fragmentary masks, so if the duct is off-centre in them the prior is what is
wrong, not the duct.

## Build the enamel cap FROM the tooth surface, not beside it

**The operator photographed this 2026-09-06**: crowns rendering as a blotchy
patchwork of white islands over the tooth beneath. It is not fragmentation --
each cap is one connected piece -- and it is not z-fighting.

**The two surfaces INTERPENETRATE.** Enamel's outer surface and the crown
surface are the same anatomical boundary, but the cap and the tooth were meshed
independently from the same volume, so they sit a median **0.23 mm** apart
(p10 0.10, p90 0.58) and cross each other repeatedly. Where the tooth wins you
see tooth, where the cap wins you see enamel, and the islands are the
intersection curves.

**Shipped now: a display shim.** `ENAMEL_LIFT_MM = 0.35` in
`tools/build-assets.mjs` pushes the cap out along its own normals at build time,
by less than the disagreement between the two meshings — so thickness, extent
and position all still stand, and nothing measured moves. It is named as a shim.

**The real fix is in `enamel.py`**: the cap's outer boundary should BE the
tooth's surface rather than a second thresholding of it. Take the tooth's own
outer surface as the cap's outer surface and solve only for the DEJ underneath.
Then the two cannot disagree, the shim goes, and the enamel is one boundary
described once. Needs an asset rebuild.

## Model the sublingual and palatal soft tissue — the sensor rests on it

**This item exists because of a number**, `SOFT_TISSUE_STANDIN_MM = 2.5` in
`src/occupancy.js`, and it should end by deleting it.

**What forced it, 2026-09-06.** The collision test was rebuilt as a solid one --
the previous version sampled only the housing's two flat faces and could not
detect a cortical plate passing through the middle of it -- and bone was made
absolute, on the operator's rule: "the sensor cannot clip through BONE. At this
point I don't care about the soft tissue compression because we don't have it
modeled."

Correct, and the result was that **5 of 28 teeth could be placed at all**.

That is not a tolerance problem. A sensor rests on mucosa over bone; strip the
mucosa and a rigid 43 x 31.2 x 7.5 mm slab in a curved arch has nowhere to go.
The palate vaults, the lingual plate curves in, and the housing meets both. What
the atlas is missing is not slack — it is **anatomy**:

- **The floor of the mouth and sublingual space**, which is what a lower film
  actually rests in, and which is why lower placements are limited by tongue and
  mylohyoid rather than by bone.
- **The palatal mucosa and submucosa**, thickest at the rugae and thinning over
  the midline, which is what an upper anterior film rests against.
- **The vestibule and cheek**, which bound how far buccally the tube can come.

**Measured**, so the scale of the stand-in is on record: with no allowance 5 of
28 place; at 1.5-2.0 mm, 17 fail; at **2.5 mm, 26 of 28 place at paralleling
with none failing**. The cliff between 2.0 and 2.5 is sharp, and 2.5 mm is
roughly the compressible depth the housing has to find.

**Where it would come from.** The intraoral scan already scheduled for ~late
September measures the mucosal SURFACE, which with the CBCT's bone underneath
gives a measured thickness over the palate and the lingual alveolus — the two
places that matter most. The floor of mouth proper is not in either dataset and
would be `derived` at best.

**Do not tune the stand-in in the meantime.** It is a placeholder for missing
anatomy, and the moment it becomes a knob that gets nudged when a placement
looks wrong, it stops being honest about what it is. The same thing already
happened once: `mucosaMm` was documented as a soft-tissue stand-in when it was
really eroding exactly the one voxel the marking pass dilates, and it was
treated as a clinical allowance for months on that basis.

---

## Scan the gingiva, and stop deriving it — SCHEDULED, ~late Sept 2026

The gingiva is currently a collar lofted from the measured CEJ, and its
provenance says plainly that the gingiva itself was never imaged. It does not
have to stay that way: unlike the condyles, this tissue is *available* — it is in
the operator's mouth, and CBCT's inability to see it is a contrast limitation,
not a geometric one.

### Planned, not hypothetical

**Agreed 2026-08-31: an intraoral scan is happening.** Chairside access to a
scanner is arranged for roughly **late September 2026**, so this is planned work
rather than a wish. The photogrammetry section below stays as the fallback if the
scanner is unavailable on the day.

Worth settling before then, because a second attempt is a month behind the first:
export **STL or PLY, not a proprietary case file**, capture both arches fully
including the vestibular depth rather than stopping at the gingival margin, and
take the scan **before any scaling or polishing** — both inflame marginal tissue,
and the atlas wants the gingiva at rest.

### An intraoral scan beats photographs, by a lot

If a chairside scanner is reachable — Trios, iTero, Primescan — **that is the
answer**. It captures teeth and gingiva together as one surface at 20–50 µm,
which is better than the CBCT's own 160 µm, and it exports STL directly into the
existing pipeline. Crucially it captures the **gingival margin**, which is the
clinically loaded part and the thing the lofted collar can only approximate.

Registration is already solved by the data: the tooth crowns appear in both the
scan and the CBCT, and the crowns are measured in both. Fit crown to crown by ICP
and the gingiva arrives in the atlas frame for free, correctly scaled. That is a
far better-posed problem than the volume-to-volume registrations already done.

### Photographs are the fallback, and still worth it

Multi-view photogrammetry would work, with caveats worth knowing before shooting:

- **Cross-polarise if possible.** Wet gingiva is specular, and specular
  highlights move with the camera, which is exactly what breaks feature matching.
  A polarising filter plus a polarised light source removes them.
- **Many overlapping views**, 30–60 around the arch, rather than a few good ones.
- **Scale comes from the teeth**, not from a ruler — photogrammetry is
  scale-free, and the crowns are already measured.
- **Retraction changes the answer.** Pulling the lip to see the gingiva moves the
  vestibule and can blanch and displace the marginal tissue. The attached gingiva
  is fairly safe; alveolar mucosa photographed under retraction is not the shape
  it has at rest.
- **Only the visible surface.** Neither photographs nor an intraoral scan see
  below the margin — the sulcus, the attachment and the biologic width stay
  underived. The CEJ is measured and the margin would be measured; what is
  between them remains an inference.

### What it would change

- **Gingiva moves from `derived` to `measured`**, with a method naming the
  modality and the crown-based registration — the first structure in the atlas
  measured by something other than the CBCT, which the provenance field is
  already shaped to express.
- **Real colour.** The gingiva is a flat pink material today. Photographs carry
  actual tissue colour, and in a dental atlas that is anatomy, not decoration:
  biotype, pigmentation and the difference between attached gingiva and alveolar
  mucosa are all visible and all teaching material.
- **Recession and papilla fill become observed** rather than lofted, which is the
  difference between an atlas that shows a gingival margin and one that shows
  *this* gingival margin.

**What it needs:** the imagery, then a photogrammetry or mesh-registration step
and an ICP fit to the measured crowns. No new radiation, which is the other
reason this is a good trade — [the skull item](#the-rest-of-the-skull--generating-what-the-fov-never-saw)
notes that the missing hard tissue is missing permanently, because re-scanning to
fill it would mean irradiating a healthy person for an atlas. Soft tissue has no
such constraint.

---

## Clean up enamel — operator, 2026-09-06 (gingiva half WITHDRAWN, same day)

**The gingiva half is off this list.** Asked and withdrawn the same day: the
operator confirmed 2026-09-06 that it falls under his own 2026-09-02 deferral to
the intraoral scan, and had forgotten the deferral when he named it. **Nothing
gingival is to be tuned before the scan lands** (~late Sept 2026) — see
[Scan the gingiva](#scan-the-gingiva-and-stop-deriving-it--scheduled-late-sept-2026).
The exception that survives, and it was never the part he meant: if a gingival
defect turns out to be *appearance* rather than *accuracy* — shading, opacity, a
seam, z-fighting against the teeth — that is a material and topology question,
it survives the scan, and it is not covered by the deferral. Do not go looking
for one; raise it only if it appears on its way past.

**The enamel half stands, and is NOT yet diagnosed.** He reads imaging fluently
and his visual read is evidence, so this is a real defect; but "cleaned up" has
not been resolved into which defect, and **guessing at it before he points would
be inventing the job**. Draw his view first, then measure — the metric has
answered the wrong question here before. **Ask what he is seeing, on screen,
before touching the mesh.**

Candidates already on record, so the question can be asked concretely:

**Enamel** — shipped in 0.7.0 as **26 caps, not 28**: 19 and 30 are crowned and
have no enamel cap. Known and suspected defects:

- **Restoration bloom.** The zirconia on 19 and 30 saturates the volume's 3072
  ceiling and its halo is labelled as tooth, so those two crowns' outer contour
  is inflated. Documented above as the remaining half of the contact re-cut, and
  fixable only back in the segmentation — intensity cannot unmix it, because
  restoration and halo are clipped to the same value.
- **Apical spikes** on the tooth surfaces, already in "Smaller things" below —
  an imaging limit rather than a code bug, but it reads as a defect, which is
  precisely the operator's complaint here.
- **The enamel/dentin boundary is soft.** Partial-volume averaging at 0.16 mm;
  clear with a visible DEJ on his own PA, much softer in ours. Recorded in
  [drr-plan.md](drr-plan.md) as expected and not a fault to chase.
- **Incisal edge overshoot**, which the operator has already identified as a
  source of spurious metal-density voxels.

**Note two of those four are not fixable here.** Restoration bloom goes back to
the segmentation, and the soft DEJ is a property of a 0.16 mm source. If what he
is seeing is either of those, the honest answer is to say so rather than to
smooth the mesh until the complaint goes away.

**Precedent for the same mistake in the other direction:** this item was named
alongside the gingiva and the gingiva turned out to be already-deferred work he
had forgotten. Check the enamel half against the record the same way before
starting.

---

## The seam between the fields of view — DIAGNOSED 2026-09-07, NOT fixed

**Nothing from this section ships.** Four constructions were built on
2026-09-07 and all four were reverted; 0.9.1 contains no mesh change. What is
below is the diagnosis and the measurements, which are the deliverable.

**The pad was the seam, and the pad was never fitted.** `export_extra_bone.py`
removed the centred volume's own bone *dilated by `OVERLAP_PAD_VOX = 2`* before
meshing what was left — so at 0.16 mm the focused exposure's surface started
0.32 mm outside the centred one **by construction**, before marching cubes put
each surface another half-voxel inside its own mask. That is why it printed
dark: a ray crossing the join passed through less bone than the patient has.

**`OVERLAP_PAD_VOX` is now 0, which is not a tuned value but the absence of
one.** `moving & ~have` with no dilation is the exact partition of the two
measurements — the focused exposure contributes precisely the bone the centred
one does not have.

### What the sweep measured, and what settled it

Rebuilt at every pad from +2 to −3 and measured surface-to-surface
(`tools/cbct/seam_sweep.py`, `tools/cbct/seam_audit.py`), mandible:

    pad   bone mm3   median gap   join in contact   overlapping   depth
     +2     11974      0.765 mm         0.4%            0.00%     0.00 mm   <- shipped in 0.9.0
     +1     12207      0.549 mm        14.8%            0.29%     0.09 mm
      0     13563      0.142 mm        62.6%           23.29%     0.50 mm   <- now
     -1     17226      0.168 mm        60.1%           74.74%     1.45 mm
     -2     21107      0.367 mm        35.1%           69.20%     1.63 mm
     -3     24343      0.391 mm        39.6%           65.09%     1.85 mm

Maxilla runs the same shape: median 0.864 → 0.236 mm, contact 1.9% → 44.3%,
overlap 0% → 15.3% at up to 0.42 mm.

**Going negative does not keep closing it.** The median stops improving at pad 0
and gets *worse* again while the overlap explodes. So the residual is **not a
uniform offset a constant could dial out** — it is spatial variation from a
rigid registration sitting at Dice 0.708, and no single number can serve it.
That answers the question the previous note left open, and it rules out "fit the
pad locally" as a cheap win too: what varies is the registration residual, not
the pad.

**The pad was also throwing measured bone away** — 1,589 mm³ in the mandible and
1,554 mm³ in the maxilla, the same class of loss as CLAUDE.md 115, bone lost at
EXPORT rather than at segmentation.

### The measurement itself was wrong before, in a way that mattered

The earlier figures were **vertex-to-nearest-VERTEX**, which on a ~1 mm
triangulation is systematically larger than the true surface separation — two
surfaces can touch exactly while their nearest vertices are half an edge apart.
Point-to-triangle puts the shipped mandible seam at **closest 0.097 mm, p5
0.300, median 0.765**, against the recorded 0.20 / 0.67 / —. Same conclusion,
different numbers, and the old method could not have detected an overlap at all.

**Confirmed: there was no overlap anywhere.** 0.00% of near-join vertices lay
inside the other mesh at pad 2. It was purely a gap.

### What this did NOT fix, and must not be claimed as fixed

**23% of the mandible join and 15% of the maxilla join now interpenetrate**, by
up to 0.50 and 0.42 mm. On the DRR that double-counts path length and prints
bright, which is an error of the same kind as the gap, in the other direction.
What has changed is that the error is **smaller and no longer biased one way**.

**Measured on the film**, pad 2 vs pad 0, periapicals at the tooth's ideal
placement: teeth 31, 30, 29 and 14 change over 3.7%, 3.6%, 2.9% and 1.4% of
their pixels, **100% of it brighter** — the dark seam filling in, which is the
expected direction. Peak change 0.09 of the greyscale range. Tooth 3 does not
change at all; its beam never reaches the extra bone. (Every tooth's readout —
tilt, tube angle, magnification — is identical across the two builds, so the
placement solver did not re-solve and the change is the geometry, not a
different exposure.)

### THE VISIBLE CREASE ON THE MODEL IS STILL THERE, and that is the real lesson

**On the 3D view, with the camera held fixed, only ~1% of pixels change and
they split evenly brighter and darker.** Side by side, the two builds look the
same and the crease down the ramus is still plainly visible in both.

**So the DRR defect and the visible defect were not the same defect.** Closing
the gap from 0.77 mm to 0.14 mm fixes what the *ray* sees, because a ray only
cares how much bone is on it. It does almost nothing for what the *eye* sees,
because a crease is a discontinuity in surface normals between two independently
triangulated meshes meeting at an angle — and two surfaces 0.14 mm apart crease
exactly as visibly as two 0.77 mm apart.

### Option 3 was tried the same day, and it does not work — here is why

`tools/cbct/seam_stitch.py` welds cross-mesh adjacency across the rim (rejecting
the pairs whose normals oppose, which are the facing walls and must stay as two
coincident surfaces for the DRR's path length to add up), splits the measured
ledge symmetrically between the two meshes, and Taubin-smooths a feathered band.

    metric                       pad 0 alone      pad 0 + stitch
    ---------------------------------------------------------------
    median separation             0.142 mm         0.146 mm
    join within 0.2 mm            62.6%            63.0%
    ledge at the rim (median)    +0.187 mm        +0.051 mm    <- the one win
    NORMAL BREAK at the rim        31.5 deg         27.7 deg    <- barely moved
    join interpenetrating          23.3%            39.8%       <- WORSE
    overlap depth                 0.496 mm         0.799 mm     <- WORSE

**Not shipped.** It moves 10,793 vertices of measured mesh, the crease looks
identical, and the DRR's double-count gets worse. The tool is kept because it is
what produced the diagnosis.

### THE DIAGNOSIS: the crease is a normal break, and it is structural

Three things were measured at the rim and they rule out everything cheap:

- **It is not a gap.** 0.77 mm → 0.14 mm changed under 1% of pixels.
- **It is not mainly a ledge.** The focused exposure does sit proud of the
  centred one 83-90% of the time by a median +0.19 mm — a real, systematic,
  measurable step — but removing 73% of it leaves the line exactly as visible.
- **It is a ~30° discontinuity in surface normals** (median 31.5°, p95 66.5°),
  and the cause is structural: **each mesh's outer surface rolls over into its
  own FOV wall** across the voxel or two marching cubes needs to turn a corner.
  Band smoothing cannot remove that, because the rim vertices belong to the wall
  as well as to the outer surface and averaging pulls them back into the corner.

**So the corner is the defect, and the corner is created at BUILD time.** Every
remaining fix changes how the join is constructed, not how it is finished — and
each has a cost that is the operator's to weigh, not mine:

1. **Mesh the union once**, in a grid covering both exposures, and ship one mesh
   per jaw. No corner, no seam, no double counting, by construction. **Cost:
   `ramus` and `midface` stop being layers, and which exposure measured what is
   erased from the geometry.**
2. **Give both meshes one shared, coincident wall.** **CHOSEN BY THE OPERATOR
   2026-09-07, and PARTLY BUILT — see below. It works, and one sub-problem is
   unsolved.**
3. **Let the focused mesh deliberately overlap** so its continuous surface
   covers the centred mesh's rim. The crease disappears because only one surface
   is ever outermost. **Cost: the DRR double-counts the overlap** — measured
   above as the thing that makes the film wrong in the other direction.
4. **Ship two representations**: the union mesh for DISPLAY, the two separate
   meshes for the DRR. Each is correct for its own job and neither compromises.
   **Cost: one extra mesh in the bundle, and the layer toggles need a story for
   what they mean when the display geometry is a union.** This did not exist as
   an option before the two defects were shown to be different defects, and it
   is the only one that pays no anatomical price.

**Do not re-register to close it.** The transform is fitted on a held-out
structure at Dice 0.708 against a 0.728 ceiling; tuning it to close a seam would
trade a measured alignment for an appearance.

**A caution that came out of measuring this.** The first pass at this comparison
framed the camera from the changed mesh's own bounding box, so the viewpoint
moved between builds and the difference read 9-13% — nearly all of it parallax.
Pin the camera to constants when comparing two builds. See CLAUDE.md 240-241.

## The seam between the fields of view — original note, operator, 2026-09-06

**Smooth the join where the focused exposures meet the centred one in the
render.** The operator named this looking at the model, and it is a render
defect with a known cause rather than a mystery.

**Why there is a seam at all.** Three exposures were acquired. The centred one
supplies `mandible` and `maxilla`; the two focused ones supply `midface` and
`ramus`, which are the bone the centred field of view cut off — 172 mm² and
191 mm² of flat cap through both rami, and an upper skull that simply stops.
`tools/cbct/export_extra_bone.py` builds those two, and the way it builds them
is what produces the seam:

- Each focused exposure is **meshed in its own grid** and only its finished
  vertices are transformed into the atlas frame. That decision is right and must
  not be undone — resampling the label onto the centred grid would discard
  exactly the new anatomy, since the exposures sit ~35 mm apart in x. It does
  mean the two surfaces are **independently marching-cubed, independently
  Taubin-smoothed and independently decimated**, so they do not share vertices
  along the join and their triangulations do not line up.
- The overlap is removed by subtracting the centred volume's own bone dilated by
  `OVERLAP_PAD_VOX = 2`. That pad exists because the two exposures disagree by
  up to a voxel and a raw subtraction leaves a shell of duplicate surface. A
  fixed pad cannot be right everywhere: too little leaves a double wall, too
  much opens a gap, and the same constant is doing both jobs at different points
  along a long boundary.
- The registration is **rigid and fitted on the upper skull**, at Dice 0.708
  against a 0.728 ceiling. Good, but not exact — so residual misalignment along
  the seam is expected and is not a bug to be chased to zero.

**Approaches, in the order worth trying:**

- **Cheapest and probably enough: stitch in mesh space.** Weld vertices across
  the join within a tolerance, then run a few Taubin iterations restricted to a
  band around the seam. This changes nothing about where the surfaces are and
  only fixes how they meet.
- **Fit the pad instead of fixing it.** Make `OVERLAP_PAD_VOX` a measured local
  quantity — the actual disagreement between the two surfaces at each point
  along the boundary — rather than one constant. More honest and more work.
- **Do not re-register to close it.** The transform is fitted on a held-out
  structure and is already near its ceiling; tuning it to make one seam look
  better would trade a measured alignment for an appearance.

**Provenance caution.** Whatever is done must not move measured surfaces to make
them meet. Welding and smoothing a seam band is a rendering fix and stays inside
the tier the structures already carry; dragging one exposure's bone onto another's
to close a gap is inventing geometry at the join, and would need saying so.

**Note this is cosmetic and safe to schedule late** — both layers are off by
default since 0.6.0, so the seam is only visible to a user who turned `midface`
or `ramus` on.

---

## The phone UI — operator, 2026-09-06

**Make the atlas navigable on a phone.** The iPad is already a first-class
target — install to the home screen, works offline, and `npm run dev -- --host`
exists to reach it — but a phone is not a small iPad, and nothing here has been
designed for one.

**What is likely to be wrong**, to be checked on a real handset rather than in a
narrow browser window, because the two differ on exactly the things that matter
(touch target size, safe areas, the on-screen keyboard, GPU budget):

- **The odontogram is 32 targets in a fixed clinical layout**, and that layout
  is not negotiable — upper arch on top, patient's right on the viewer's left is
  how it is read, and reflowing it would break the thing it exists to be. So the
  answer is pan/zoom or a larger drawn chart, **not** a responsive re-flow.
- **Radiograph mode is a side panel plus a film canvas plus sliders.** On a
  phone that is a second full screen, not a panel. The canvas already sizes off
  `dom.canvas.clientWidth`, clamped to 64–520 px, so the film itself will adapt;
  the controls are the problem.
- **Layer opacity and structure selection compete for the same edge** as the
  system gestures. `viewport-fit=cover` and the translucent status bar are
  already set in `index.html`, so safe-area insets need to be honoured in the
  CSS, not just declared.
- **Orbit, pan and zoom on one finger versus two.** Three.js orbit controls on a
  small screen with a model this dense is the usual source of "I cannot get
  where I want to look".
- **GPU and memory.** 15 MB of geometry and a WebGL2 float target. The
  radiograph already degrades honestly where the float buffer is missing (see
  the WebGL2 check in `src/radiograph.js`); whether a mid-range phone clears
  that bar is unknown and should be measured, not assumed.

**What it needs:** a real phone, and a decision about whether the phone gets the
same UI at a different size or a genuinely different one. Do not guess that from
a desktop window.

**Note it is cheap to start**: `npm run dev -- --host` already serves to the
network, so the first hour is looking at it, not building.

---

## UI polish — operator, 2026-09-09

A section for interface work that is not anatomy and not a new feature. Nothing
here changes what the atlas claims; it changes how it feels to use, which has
mattered more since the first outside visitors arrived.

### The scrollbars — **[operator]**, and there is a real cause

**His words: he does not love them and they want an overhaul at some point.**
Not filed as urgent. But the cause is already found and it is smaller than the
complaint suggests.

**`src/style.css` never declares `color-scheme`, and `drr.html` does.** Line 8
of `drr.html` carries `:root { color-scheme: dark; }`; the stylesheet the atlas
loads has no such declaration anywhere. So the radiograph page gets dark
browser-drawn scrollbars and **the atlas gets the default LIGHT ones, painted
against `--bg: #14161a` and a `--panel` of `rgba(26, 29, 35, 0.92)`.** The two
pages of the same app disagree, and the atlas is the one that is wrong. That is
almost certainly the thing being reacted to.

**One line fixes most of it.** Adding `color-scheme: dark` to `:root` in
`style.css` hands the browser the right palette for every native control, not
only the scrollbar. Do that first and look again before designing anything —
the remaining complaint may be small enough to stop there.

**What actually scrolls,** so an overhaul knows its targets: `.panel`
(`overflow-y: auto`, `max-height: calc(100vh - 12rem)`, style.css:88-93) and its
narrow-viewport variants at `40vh`, `30vh` and `62vh`. That is the layer panel
and the detail panel, and on a phone the radiograph panel too.

**If it does go further than the one line, four constraints:**

- **The panel is 15.5rem wide** and a classic scrollbar takes layout width out of
  it. `.layer-toggle span` already truncates with an ellipsis (style.css:148), so
  a wider scrollbar eats structure names. `scrollbar-gutter: stable` prevents the
  content shifting when the bar appears, at the cost of always reserving it.
- **`--radius: 10px` on the panel.** A classic scrollbar squares off the rounded
  corner it sits in. This is the detail that makes styled bars look bolted on.
- **Do not hide them.** A panel that scrolls with no visible affordance is worse
  than an ugly bar — the layer list is exactly the place where a user needs to
  know there is more below. Overlay scrollbars that fade out have this problem on
  desktop, where there is no touch gesture to reveal them.
- **Two mechanisms, and they are not the same.** `scrollbar-width` and
  `scrollbar-color` are standard and work in Firefox and Chrome; `::-webkit-
  scrollbar` gives far finer control but is non-standard and Firefox ignores it
  entirely. Using both means two sources of truth for one appearance. Prefer the
  standard properties and accept the coarser control unless something specific
  needs more.

**Not yet reviewed by him:** whether the fix is the one line or a designed
scrollbar. Ask before building the second.

### Room for the rest

Other interface complaints belong here as they are named, rather than being
scattered. Nothing else is filed yet.

---

## Smaller things

- Retopologise the apical spikes on the tooth surfaces — an imaging limit, not a
  code bug, but it looks like a defect.
- The coronal pulp chamber is under-represented in multi-canal teeth: it is one
  space split between canal basins. Model it explicitly.
- Per-basin dentin reference in the pulp tracker, to close the systematic bias
  documented in [cbct-whole-mouth.md](cbct-whole-mouth.md).

---

## The shared wall — option 2, built and REVERTED 2026-09-07

**The construction works on the lateral ramus and was still wrong.** It removes
the crease there, and the operator — looking at the ANTERIOR INFERIOR border,
which is where the seam actually is — reported the seam and the jaggedness both
still present. Reverted. `tools/cbct/join_grid.py`
and `tools/cbct/export_joined_bone.py` build it:

1. **One grid holding both exposures.** Built in the centred (atlas) frame and
   extended by however far the focused exposure sticks out. The centred label
   round-trips at **100.0%**; the focused one costs **0.3%**, a sub-voxel shell
   lost to thresholding an interpolated binary. Nothing is clipped — which was
   the whole objection to putting them in one grid, and it is answered by
   sizing the grid to both labels instead of reusing either volume's.
2. **Mesh the union ONCE.** The outer surface is then a single marching-cubes
   surface with no corner anywhere on it. **This is what kills the crease.**
3. **Classify each triangle by exposure**, then cap the boundary between the two
   classes once and give the same cap to both meshes with opposite winding.

**Rendered, the rectangular step across the ramus is gone.** That is the
operator's original complaint and it is the thing none of the cheaper fixes
touched.

### SOLVED 2026-09-07 by meshing the wall as a MATERIAL — `export_material_bone.py`

**The crease is gone, and the volumes add up.** Rendered side by side, the
rectangular step across the ramus has disappeared, with no cap, no flap and no
ledge.

**The construction is three lines of arithmetic, not an algorithm:**

    fU = smoothed indicator of the UNION       (the outer surface is fU = 0.5)
    gA = smoothed indicator of A's TERRITORY   (the wall is gA = 0.5)

    A' = marching cubes of min(fU,     gA) at 0.5
    B' = marching cubes of min(fU, 1 - gA) at 0.5

`min` is intersection. Along a wall edge the active field is `gA` for A' and
`1 - gA` for B', and those cross 0.5 at the same parameter on the same grid
edge — so marching cubes places the same vertex. **The wall is not made to
agree; it cannot disagree.** Measured at full resolution: 84.9% of wall vertices
coincide bit-exactly, median separation 0.000000 mm. And because it is an
isosurface of the voxel data rather than a triangulation spanning a loop, **it
follows the bone** — which is the property all three caps failed.

**Volume conservation is the check that replaces `seam_audit` here.** With a
shared wall "how far apart are the surfaces" is meaningless; what matters is the
arithmetic the DRR does. Mandible: centred 23,629 + focused 11,544 = 35,174 mm³
against a union mask of 35,294 — **−0.34%**, which is ordinary smoothing
shrinkage, not a gap and not a double count. Maxilla: −1.30%.

**Decimation is handled by decimating the two as ONE object** (weld — the wall
vertices are bit-identical so there is no tolerance to choose — de-duplicate the
shared wall faces, decimate, then split). **The split has to be recovered
topologically, not by threshold**: classifying each triangle by sampling the
fields at its centroid left 3,712 holes, because a per-face threshold does not
respect the junction curve. But the structure is already in the mesh — three
sheets meet along one curve, and that curve is exactly the set of edges with
three incident faces. Cutting there drops the sheets out with matching
boundaries whatever the decimator did to them: 3,712 holes → 0.

### Three reasons it is NOT shipped yet, and the first is the operator's call

1. **IT REBUILDS THE WHOLE JAW, not just the join.** This is the important one.
   `FMA52748` is no longer "the centred exposure's mandible meshed in its own
   grid" — it is "the part of the union lying in the centred exposure's
   territory", and where the two exposures overlap its surface is now the
   union's envelope rather than the centred scan's alone. Measured on film,
   periapicals of 29, 30 and 31 change over **43%, 52% and 59% of their pixels**
   (max 0.41 of the greyscale range, about half brighter and half darker). That
   is a far larger change than fixing a seam, it changes what the mesh CLAIMS,
   and the manifest's `method` strings would have to be rewritten. **Whether the
   primary mesh should be the union's envelope or the centred scan alone is a
   provenance decision and is the operator's, not mine.**
2. **The maxilla leaves 1-6 dangling open edges** depending on the triangle
   budget (3 at 40k and 42k, 1 at 46k, 6 at 48k, 3 at 44k). They are not cycles
   — two fragments, a path and an isolated edge — so they are not holes that can
   be ear-clipped; a triangle is missing next to a junction. Systematic, not
   tunable. The mandible is clean.
3. **The float32 STL round-trip reopens 2 holes on the mandible** that are not
   there in float64. The tool's own check was reading the wrong artefact — the
   shipped `.stl` is what matters, and it must be checked after writing, not
   before.

### The earlier attempt, kept because it is how the diagnosis was reached

`export_joined_bone.py` meshes the union once and RECOVERS the wall by
classifying triangles, dissolving islands, walking the boundary into loops and
capping each. Everything works except the cap, and the reason is worth keeping:

| cap method | buried | holes |
| --- | --- | --- |
| planar ear clip | 72.0% | 0 |
| fan to an interior apex | 59.4% | 0 |
| split into planar arcs | 60.1% | 27 |

**The cause is one loop.** The mandible's wall is 4 clean loops of 368, 135, 130
and 11 vertices; three are flat (planarity 0.03-0.05) and cap perfectly. The
368-vertex one has planarity 0.274 because **it follows bone around a corner of
the field-of-view box**, and no single plane spans it without chording through
the jaw. That is what `export_material_bone.py` removes: the mesher emits the
material interface directly, so there is no loop to triangulate.

### The old note on the sub-problem, superseded

The cap's SHAPE does not matter for the radiograph — whatever it is, a ray
leaves one mesh exactly where it enters the other, so it cancels. It only has to
be **shared**, to **close both meshes**, and to **stay buried**. The third is
where it stands:

| cap method | buried | holes | note |
| --- | --- | --- | --- |
| planar ear clip | 72.0% | 0 | the 28% renders as a flat plate across the ramus |
| fan to an interior apex | 59.4% | 0 | worse — the apex of a wrapping loop is a bad centre |
| split into planar arcs | 60.1% | 27 | broke closure too; the arcs do not tile the loop |

**The cause is one loop.** The mandible's wall is 4 clean loops of 368, 135, 130
and 11 vertices. Three are flat (planarity 0.03-0.05) and cap perfectly. The
368-vertex one has planarity 0.274 because **it follows bone around a corner of
the field-of-view box**, and any triangulation of it in one plane chords
straight through the jaw.

**The right fix is not another triangulation of the loop.** It is to mesh the
wall FROM THE VOXEL DATA — the `grown(A)` isosurface clipped to the union —
so it follows the bone by construction instead of being interpolated across it.
That is a **multi-material marching cubes**, a known and solved problem in the
literature, and it is a real piece of work rather than a patch. It would also
remove the classification and island-dissolving steps entirely, since the
material boundary would come out of the mesher rather than being recovered from
it afterwards.

### Three things worth not rediscovering

- **"Is the centroid inside A" is not the classification you want.** Over most
  of the jaw BOTH exposures measured the same outer surface, so the union
  surface sits exactly on A's own boundary and the inside test is a coin flip:
  it produced **356 boundary loops**. Attributing by DISTANCE — a triangle
  belongs to the centred exposure if it is within a few voxels of its bone —
  gives 4. Coincident surfaces should attribute to the centred volume, which is
  the primary acquisition and the frame the atlas is in.
- **Small misclassified patches must be dissolved before the wall is walked**,
  or each one adds a loop, and an uncapped loop is a hole: 473 open edges before
  dissolving, 15 after.
- **Delaunay is the wrong triangulation for a cap.** It does not guarantee the
  polygon's own edges appear — that needs a constrained triangulation — so the
  cap's boundary came out different from the loop it was closing. Ear clipping
  consumes the boundary by construction, which is the property that makes both
  meshes closed.
- **Distinguish holes from non-manifold edges when reporting.** `closed()`
  originally counted every edge not used exactly twice and reported "375 open
  edges" when all of them were used FOUR times — two surfaces meeting along an
  edge, which `boundaryEdges` in `tools/build-assets.mjs` deliberately ignores.
  Not one of them was a hole.

### The three things that defeated every attempt, 2026-09-07

Recorded together because each was found only after building something on the
assumption it was false.

1. **The centred label FADES OUT over the last 1.6 mm** rather than ending: 1.1,
   14, 76, 169, 243, 349, 406, 516, 586, 643 mm2 across ten slices before
   settling at ~660. Meshing that fade IS the torn inferior border, and every
   handover keyed to the field-of-view boundary sits inside it.
2. **The centred scan is truncated on THREE faces, not one.** Its mandible
   reaches exactly x = -41.0 and +40.8 at every level -- its own side walls at
   +/-40.96. The floor is not a special case, it is one of three.
3. **NEITHER EXPOSURE IS A SUPERSET OF THE OTHER.** At the level where a cut
   would go, the focused scan stops 4.6 mm short of bone the centred scan has.
   So a single clean plane -- which is otherwise exactly the right idea, and the
   join really is one plane -- trades one truncation for another.

**And one measurement trap worth keeping.** Whole-area IoU between the two
labels at the cut level is 0.71, which reads as catastrophic; the OUTER BOUNDARY
agrees to a median of 0.16 mm, one voxel. The difference is interior marrow
space that no surface mesh ever sees. Score the filled outline, not the label.
