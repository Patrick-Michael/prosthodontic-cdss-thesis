# Pathology wishlist

**Nothing here is built.** There is no pathology code in `src/` as of 0.9.0.
This document exists so the ideas, the constraints and the ruled-out approaches
accumulate in one place instead of being rediscovered, the same way
[wishlist.md](wishlist.md) works for the atlas as a whole.

Opened 2026-09-07 at the operator's request, to track "specific graphical things
or diseases" wanted in the pathology feature.

**Where the seed material came from.** Three sections of `wishlist.md` are the
origin of this one and remain authoritative until something here supersedes
them: [the pathology menu](wishlist.md#3-pathology-menu-shown-on-model-and-radiograph-together),
[the pulpitis timelapse](wishlist.md#1-pulpitis--necrosis--root-canal-as-a-timelapse)
and [the time-varying sliders](wishlist.md#time-varying-sliders--one-mechanism-three-diseases).
Everything they say is restated or extended below; when this file and those
disagree, this file is newer.

**Attribution note.** Items marked **[operator]** were named by the operator.
Everything else is proposed by me and has not been reviewed. Do not treat an
unmarked item as agreed work.

---

## The three rules that govern everything in this file

These are not preferences. Each one already exists in the codebase or in a
decision that has been made, and a pathology feature that breaks one of them
would be a regression against work already done.

### 1. Pathology is `simulated`, and the tier already exists waiting for it

`tools/manifest.mjs` defines four provenance tiers. Three are in use; the fourth
is reserved, and the comment above it says so outright:

> A fourth tier, `simulated`, is reserved for the pathology sliders and the
> anaesthetic diffusion on the wishlist. Nothing uses it yet; it exists so those
> features cannot ship without a tier, because geometry that is neither measured
> nor a literature mean is exactly what needs saying out loud.

`.prov-simulated` is already styled in `src/style.css` (hue `#d97ba4`). So the
badge, the wash and the blurb — "Neither measured nor a literature mean." — all
render the moment a structure claims the tier.

**Why this matters more here than anywhere else in the atlas.** The anatomy is
one real, named, living person's mouth, published with his consent. Every lesion
we author is a false statement about that person's health, sitting inside a
dataset whose whole value is that it is true. The tier is the thing that keeps
those apart. **A pathology object that ships without `tier: 'simulated'` is a
bug, not a missing nicety** — and `tools/build-assets.mjs` already fails the
build for a structure with no provenance, so the guard is in place.

Corollary: **the disease must not be baked into a measured mesh.** Do not
subtract a lesion from `mandible` and re-export it. The measured surface stays
measured and the lesion is its own object, drawn and integrated separately. See
"How a lesion should be represented" below.

### 2. Model it once, see it twice

From the original DRR reasoning, and it was right:

> If a lesion is a parametric perturbation of the *volume* — a density deficit
> at an apex, a concavity on the lingual mandible — then the DRR picks it up for
> free and the 3D model shows the same object. One model, two views, always
> consistent. This is the reason to build pathology volumetrically rather than
> as a decal on a mesh.

The 3D view and the film must never be able to disagree about where a lesion is
or how big it is. **A pathology drawn as a texture on the film is the failure
mode to avoid**, because the moment the user rotates the model the lesson breaks.

### 3. Anchor to measured landmarks, always

We have 48 traced apical foramina, a traced mandibular canal, a traced mental
foramen on both sides, a measured CEJ ring at 36 angles, re-cut interproximal
contacts and a measured crest. A periapical radiolucency sited on **this
patient's real apical foramen of tooth 30** is a better teaching object than one
placed at an arbitrary point, and costs nothing extra now that the foramina are
measured. The lesion's shape is simulated; its *location* can stay anchored to
something true. Keep that split, and say it in the `method` string.

---

## What already exists that pathology can stand on

Worth listing explicitly, because several diseases below are much cheaper than
they look and the reason is always something 0.7.0–0.9.0 already shipped.

| Asset | Where | What it unlocks |
| --- | --- | --- |
| The DRR engine | `src/drr.js`, `drr.html` | Every radiographic sign, for free, if the lesion is volumetric |
| Cone-beam geometry with a real source point | `exposureFor()` | Buccal/lingual object localisation — see SLOB below |
| **Horizontal tube angulation** (new in 0.9.0) | `src/radiograph.js` | The tube-shift manoeuvre, which is the *clinical* resolution for half the mimics in this file |
| Measured trabecular field | `public/`, `trabecular_field.py` | Lesions sit in real bone texture, so a radiolucency has something to be lucent *against* |
| Superimposition fade (floor 0.414) | 0.9.0 | A lesion behind a root will correctly not print at full strength |
| 48 apical foramina | `docs/cbct-landmarks.json` | PARL, condensing osteitis, cementoma anchors |
| Mandibular canal + both mental foramina | `docs/cbct-canal.json`, `cbct-mental.json` | Stafne siting constraint; the mental-foramen mimic; canal displacement by a lesion |
| Re-cut interproximal contacts | 2026-09-02 | Interproximal caries — the contact is the subject |
| Enamel (26 caps), dentin, pulp, PDL, lamina dura, cementum | 0.7.0/0.8.0 | Caries depth staging, loss of lamina dura, widened PDL |
| Measured alveolar crest | `docs/cbct-crest.json` | Periodontal bone loss measured *from* a real crest height |
| Sensor collision + per-tooth ideal placement | 0.9.0 | Case mode can pose a lesion at a placement the user has to earn |
| `simulated` tier + its CSS | `manifest.mjs`, `style.css` | The label, already built |

### And what is missing, with which diseases it blocks

- **The pulp is a lumen boundary, not tissue.** No odontoblast layer, no
  neurovascular core. Blocks the pulpitis stages of the timelapse — inflammation
  is a change in tissue that does not exist yet. Described in
  [phase-3-soft-tissue.md](phase-3-soft-tissue.md).
- **No mucosa, no floor of mouth, no tongue.** `SOFT_TISSUE_STANDIN_MM` is
  holding the sublingual gap and is marked for deletion when the intraoral scan
  lands (~late Sept 2026), not for tuning. Blocks anything soft-tissue: sinus
  tract, swelling, mucous retention pseudocyst against a real sinus lining.
- **Gingiva is derived and deferred to the scan.** Nothing gingival is to be
  tuned before it lands. Blocks periodontal disease as a *soft-tissue* finding —
  though the bone half is not blocked, see below.
- **No condyle, fossa or eminence, and never could have been** — bicondylar
  breadth ~120 mm against an 81.9 mm FOV box. Blocks every TMJ pathology unless
  the deferred small-FOV TMJ scan happens. **His body, his call, do not push.**
- **No third molars.** They are charted as *extracted* — `src/odontogram.js`
  renders all four as disabled cells titled "Third molar — extracted, so not
  present in the scan" — so 28 teeth is a post-extraction dentition, not
  agenesis. Either way the single most common radiographic finding in general
  practice, the impacted lower eight, has no measured host tooth to build on.
  Anything there is authored from nothing. (A *healed extraction socket* at
  those four sites, on the other hand, may well be measurable in his scan — see
  the incidental-findings question.)
- **Grey values are not calibrated HU** and saturate at 3072. Any lesion
  contrast is derived, not measured, exactly as `boneVolumeFraction` is.

---

## The question worth asking before authoring anything

**Does his own scan contain incidental findings?**

Nobody has looked. A torus, an idiopathic osteosclerosis / dense bone island, a
retained root tip, an ankylosed area, a mucous retention pseudocyst on the sinus
floor, a bifid canal, an accessory foramen — these are common enough that a
28-tooth adult CBCT containing none of them would be mildly unusual. The
`maxillary` volume covers sinus walls and nasal anatomy and is **essentially
free of crown artefact** (max 2605 against `centered`'s saturated 3072), so it is
the right place to look for a sinus finding.

**Anything found this way is `measured` pathology**, which is worth
disproportionately more than anything on the authored list below — it is real
disease, in real bone, in a dataset the user can rotate. It also costs a survey
rather than a build.

**Two cautions.** It is his body and his scan: a finding is his to publish or
not, and this file must not treat "look for findings" as agreed. And a survey
that goes looking for pathology will find some — the trabecular ACF work has
already produced two confident false positives that had to be recorded as wrong
(CLAUDE.md's detrending and air-control failures). Any candidate finding needs
his read before it is called anything, per the standing rule that his clinical
read is the evidence and my metric is the thing that is probably blind.

---

## Diseases

Status key: **free** = needs no new geometry, only a DRR perturbation and a
control; **cheap** = one new parametric object on an existing anchor;
**blocked** = waiting on anatomy the atlas does not have.

### A. Mimics and artefacts — the cheapest content and, I think, the best

**[operator, 2026-09-07] — endorsed as a SUBSECTION, not as the headline.**
His correction, and it is recorded because I got it wrong first: "the mimicry
section is a good idea and important to have as a subsection in pathology." I
had promoted the mental foramen to the flagship item and to "build this first"
off the strength of one anecdote. That was my inference, not his instruction.
Mimics belong in pathology as their own section; **what pathology starts with is
still open** — see the open questions.

These
are the findings that are *not* disease but read as it, and a simulator built
from one person's ground-truth anatomy can do something no textbook can:
**toggle the mimic and prove what it was.** The user sees a lucency at the apex
of 29, calls it a PARL, then rotates the model and watches the mental foramen
sit exactly there. None of them need a lesion to be authored at all.

**The audience is not only students.** The operator's words: general dentists
refer patients to his practice "thinking they have a lesion under a mandibular
premolar without first checking that it's the mental foramen." So the mental
foramen mimic is not a teaching curiosity — it is the specific misread that
generates unnecessary referrals, and a tool that settles it in one rotation has
an immediate professional use.

**One thing does follow from it, and it is about audience rather than order:**

- **A referring dentist is a different user from a student**, and wants a
  different thing: not a case to solve but a demonstration to be shown, ideally
  in under a minute and on a phone. That is an argument for the mimics being
  reachable directly (a link that opens *this* film with *this* mimic
  highlighted) rather than only through a case-mode quiz — and it connects this
  to the [phone UI](wishlist.md#the-phone-ui--operator-2026-09-06) item, which
  had no strong driver before now.

**Worth checking early, and it is measured, not authored:** this patient's
mental foramina are already traced on both sides, and their **asymmetry is
already flagged** in the open questions. So "where does it fall relative to the
premolar apices, on each side, in a real mouth" is a question the atlas can
answer today from measured geometry — which is exactly the answer the referring
dentist needed and did not have.

| Mimic | What it is | Status |
| --- | --- | --- |
| **Mental foramen over an apex** | Superimposes on the apices of 28/29 (and 20/21) and is the classic false PARL. Named by the operator as the misread that sends real patients on unnecessary referrals | **free** — the foramen is measured, on both sides, and its asymmetry is already flagged |
| **Nasopalatine canal over 8/9** | The other classic false PARL | **free** if the canal is labelled; needs a look at whether it is |
| **Cervical burnout** | The radiolucent band below the CEJ from the ray passing through less tooth; misread as root caries | **probably already happening** — it is a geometric consequence, so check the shipped films before authoring anything |
| **Mach band at the apex** | A perceptual edge effect, not in the data at all | **free**, and it is a lesson about the *reader*, not the film |
| **Zygomatic process over maxillary molars** | Obscures the apices of 2/3 and 14/15 | **free** — the process ships in `FMA53649U/M` |
| **Superimposed canals on multi-rooted teeth** | The reason horizontal tube shift exists | **free, and already demonstrable** — 0.9.0 shipped the control |
| **Restoration bloom** | The zirconia on 19/30 saturating and inflating its own contour | **already present, unwanted** — but it is a real artefact, honestly labelled, and could become a teaching object instead of only a defect |

**Why they are worth doing first:** every one of them is a DRR consequence rather
than an authored object, so they cannot drift out of agreement with the 3D view,
and none of them require the `simulated` tier because nothing is being invented.
They are the pathology feature's free lunch.

### B. Object localisation — SLOB, and the manoeuvre we can now perform

**Buccal Object Rule / SLOB (Same Lingual, Opposite Buccal).** Place a lesion or
a foreign object buccal or lingual to a root; shift the tube horizontally; see
which way it moves relative to the root. This was flagged in the original
pathology note as an optional variable ("whether the lesion is visible on a given
projection at all, which is itself the lesson"), and 0.9.0 turned it from a wish
into something the engine can already do.

It is **free** — no new geometry, only a marker object and the existing
horizontal angulation control — and it is arguably the single highest
teaching-value-per-line item in this document. Worth building as the *first*
pathology interaction even if the object being localised is a sphere.

### C. Caries and its sequelae

| Finding | Volumetric form | Anchor | Status |
| --- | --- | --- | --- |
| Interproximal caries, staged E1→E2→D1→D2→D3 | Density deficit seeded at the contact, growing toward the pulp, **spreading laterally at the DEJ** | Re-cut contacts, enamel caps | **cheap**, and the flagship — the bitewing exists to show it |
| Occlusal caries | Deficit under the fissure, wider in dentin than enamel | Occlusal surface | **cheap** |
| Root caries | Deficit on exposed root surface below the CEJ | Measured CEJ ring | **cheap** — and note it must not be confused with cervical burnout, which is a *pairing* worth building deliberately |
| Recurrent/secondary caries | Deficit at a restoration margin | 19/30 crowns | **cheap**, but sits inside the restoration-bloom problem |
| **Radiographic vs actual depth** | The lesion is deeper than it prints | — | **free once the above exists**, and it is the point of the whole exercise |

**[operator, via wishlist]** "the relationship between radiographic depth and
pulpal status — the point at which a restorable lesion becomes a pulpotomy
becomes a root canal." That framing should drive the staging, not lesion
millimetres.

**One honest note:** the operator's dentition has no caries anywhere, so every
lesion here is authored departure from a healthy baseline. That is the right way
round and it is rarer than it sounds — most teaching material starts from
diseased or treated teeth.

### D. Pulpal and periapical

| Finding | Volumetric form | Anchor | Status |
| --- | --- | --- | --- |
| Reversible / irreversible pulpitis | **No radiographic sign** | — | **blocked** on pulp-as-tissue, and the teaching point is that the film is normal |
| Necrosis | Tissue change, then the periapical consequence | Pulp lumen | **blocked** on pulp-as-tissue |
| Widened PDL space | Thickening of the measured PDL at the apex | PDL mesh | **cheap**, and it is the *earliest* sign — worth having as its own stage before any lucency |
| Loss of lamina dura | Deletion/thinning of the lamina dura layer at the apex | Lamina dura mesh (ships since 0.8.0) | **cheap**, and it is the sign clinicians actually read |
| Periapical radiolucency | Density deficit centred on an apical foramen | 48 measured foramina | **cheap** — the original item |
| Granuloma vs cyst | *Identical radiographically* | — | **free** — a lesson delivered by refusing to distinguish them |
| Condensing osteitis | Density **excess**, not deficit | Apical foramen, typically 19/30 | **cheap**, and a good check that the DRR handles excess as well as deficit |
| Periapical abscess / sinus tract | Lucency plus a tract to the surface | — | **blocked** on mucosa |
| Root canal treatment | Access cavity, instrumented canal, obturation | Pulp lumen | **blocked** on pulp-as-tissue; and **keep authored canal geometry in a separate tree from the measured pulp** |

### E. Resorption

Grouped separately because it is a family the DRR is unusually good at.

- **Internal resorption** — a balloon-like symmetrical expansion *of the canal
  itself*, so the lesion moves *with* the canal on a tube shift. **cheap**, and
  the differential against external resorption is performed with the horizontal
  angulation control we now have. This is the second-best SLOB demonstration in
  the file.
- **External cervical resorption** — irregular, moth-eaten, at the crest, and
  the canal outline stays intact through it. **cheap**.
- **External apical root resorption** — shortening and blunting of the apex,
  the orthodontic finding. **cheap**, but note it changes a measured tooth
  surface and so must be a separate object, not an edit.
- **Replacement resorption / ankylosis** — loss of the PDL space, the tooth
  fusing to bone. **cheap**, and it is the PDL layer's negative.
- **Hypercementosis** — excess cementum at the apex with the PDL space intact
  around it. **cheap**, and a nice pairing against condensing osteitis.

### F. Periodontal

The bone half is **not** blocked by the gingiva deferral. The soft-tissue half is.

- **Horizontal bone loss** — the crest dropping uniformly. **cheap**: measured
  crest heights exist, so loss can be expressed as millimetres from *his* crest.
- **Vertical / angular defect** — a wedge-shaped infrabony defect at one root.
  **cheap**.
- **Furcation involvement** — lucency in the furcation of 3/14/19/30. **cheap**,
  and it is a bitewing/periapical reading skill.
- **Calculus** — density excess as a spur on the root surface at the crest.
  **cheap** and visually distinctive.
- **Vertical bitewing** — named as the view that shows bone levels. Depends on
  the bitewing frame function, which does not exist yet.
- Probing depths, recession, inflammation — **blocked** on the intraoral scan.

### G. Developmental and anatomic variation

- **Stafne defect** — lingual concavity of the mandible below the canal. **cheap**,
  and its siting constraint (below the canal, posterior, lingual) is a measured
  one. Already on the original list.
- **Enamel pearl, dens invaginatus, dens evaginatus, taurodontism** — tooth-form
  variants. **cheap** individually; low priority.
- **Fusion / gemination, supernumerary (mesiodens)** — authored whole teeth.
  Moderate.
- **Impacted third molar** — the most common real finding in practice and we have
  **no third molars**. Authored from nothing; flagged as the one place where the
  atlas's "it is his real mouth" advantage disappears entirely.
- **Bifid mandibular canal, accessory mental foramen** — would be **measured** if
  present in his scan. See the incidental-findings question above.

### H. Cysts, tumours and bone lesions

Worth having because the radiographic differential is a *border and locularity*
question, and border character is a parameter rather than a shape (see the
graphical section).

- Radiolucent: radicular cyst, residual cyst, dentigerous cyst, odontogenic
  keratocyst, lateral periodontal cyst, nasopalatine duct cyst, ameloblastoma
  (multilocular, "soap bubble"), simple bone cyst (scalloping between roots).
- Radiopaque / mixed: **periapical cemento-osseous dysplasia** (already on the
  original list, and the best of them because it is a genuine *staged* sequence
  from radiolucent through mixed to radiopaque — a real use of the scrubber),
  florid COD, cementoblastoma, compound and complex odontoma, idiopathic
  osteosclerosis, fibrous dysplasia (ground glass, ill-defined).

Most are **cheap** as geometry and expensive as *judgement* — getting the border,
the locularity and the effect on adjacent structures right is where the teaching
value is, and getting them wrong teaches the wrong differential to a dentist.
**Nothing in this group should be authored without his review of each one.**

### I. Trauma and fracture

- **Crown fracture, horizontal root fracture, vertical root fracture.** The VRF
  with its **J-shaped periradicular radiolucency** is already on the wishlist,
  with the right instruction attached: *the J-shape is a consequence of modelling
  the bone loss correctly, not a shape to be drawn. If it emerges from the DRR on
  its own, the simulation is right.* That is the acceptance test for the whole
  feature, and it should be kept as one.
- Luxation, avulsion, alveolar fracture. Moderate.

### J. Time-varying — the scrubber diseases

Three items already grouped in `wishlist.md` because one scrubber buys all of
them. Restated here with what has changed since:

1. **Pulp calcification with age.** The strongest of the three: pulp chamber
   volume has a documented inverse association with age, so the slider can be
   calibrated against published regressions rather than chosen by eye — and it
   runs *backwards* from measured geometry, since his own dentition is a real
   point on the curve. Also add **pulp stones** as a discrete variant.
2. **Dentinal decay.** Covered in section C above.
3. **Fracture progression.** Covered in section I above.

**Add a fourth:** **periodontal bone loss over time**, which is the same
scrubber against the measured crest and is arguably more clinically routine than
the other three.

---

## Graphical wishlist

The "specific graphical things" half. Several of these matter more than which
diseases get built, because they decide whether a lesion *reads* correctly.

### How a lesion should be represented

**Proposal, not agreed.** A lesion is its own closed mesh carrying its own
attenuation contribution, positive or negative, integrated as an extra pass the
way the trabecular field already is. Consequences:

- The measured meshes are never edited, so provenance survives.
- The 3D view and the film read the same object — rule 2 holds.
- Excess (condensing osteitis, calculus, odontoma) and deficit (every lucency)
  are the same mechanism with opposite sign.
- It slots into the existing layer panel as a group, with the `simulated` badge
  on every member.

**The thing to check early:** `src/drr.js` computes path length as back-face
depths less front-face depths, so a lesion mesh must be closed and outward-wound
like everything else — and a lesion *intersecting* a root or the canal is the
normal case, not an edge case. Whether the depth-peel handles overlapping
negative-density objects correctly is the first thing to test, before any disease
is authored.

### Border character is the parameter that matters most

The radiographic differential between a cyst, a granuloma, a tumour and an
infection is largely **border**: corticated vs non-corticated, well-defined vs
ill-defined vs ragged, unilocular vs multilocular, expansile vs infiltrative. A
lesion parameterised by *border and locularity* teaches far more than one
parameterised by shape, and it is the same amount of work.

**A corticated border is a density excess ring around a deficit** — so it falls
straight out of the signed-contribution model above.

### Radiolucency is not binary, and this is a real lesson

A periapical lesion confined to cancellous bone may not print at all; visibility
demands substantial mineral loss and, classically, cortical involvement.
**The state "the lesion exists in the 3D model and is invisible on the film" is
one of the most valuable things this simulator could show**, and it is free — it
happens automatically if the lesion's density deficit is modelled honestly
rather than tuned until it looks obvious.

**Corollary and a warning:** do not tune lesion contrast to make it visible. That
is the same error as tuning the registration to close the FOV seam — trading a
correct model for an appearance.

### The lesion must get the same detector treatment as everything else

0.9.0 shipped superimposition fade (structure behind dense tissue prints at a
floor of 0.414 rather than full strength) because trabeculae printed through
roots too strongly. **A lesion drawn without it will print too crisp** and will
look like an overlay, which is exactly the failure rule 2 exists to prevent. Same
for the point-spread blur. Whatever pass a lesion is added to, it inherits the
detector model or it looks pasted on.

### Colour and labelling in the 3D view

- **Use the `simulated` hue `#d97ba4`** already in `style.css` for lesion
  geometry, so the 3D colour and the provenance badge are the same statement.
  Consistent with arteries red / veins blue / nerves yellow.
- Lesions want **translucency by default** — the anatomy they displace is the
  point, and an opaque blob hides the root it is sitting on.
- A **cutaway or clipping plane** through a lesion, since half of them are
  internal.
- **An annotation overlay on the film**, off by default: outline the lesion,
  name the sign. The whole value of case mode is the moment *before* it is on.

### Two smaller graphical items

- **A side-by-side "with / without" film.** The atlas has ground truth, so it can
  show the same exposure of the same mouth with and without the finding. No
  textbook can do this, and it is the fastest way to teach what a subtle sign
  looks like.
- **Lesion effect on adjacent structures** — canal displacement, root
  divergence, loss of the sinus floor line. These are read *before* the lesion
  itself in practice, and they are what separates aggressive from benign.

---

## Interaction wishlist

- **A pathology menu, per tooth and per site.** The original framing. Selecting a
  tooth in the odontogram and adding a finding to it.
- **Randomisation — [operator, 2026-09-07].** See the section below; this is a
  requirement, not an option.
- **A seeded, shareable case.** `?case=<seed>` so a case reproduces exactly. This
  is what makes it usable for teaching rather than only for demonstration, and
  it is cheap if the randomiser is seeded from the start. **Retrofitting a seed
  later is much more annoying than building with one.**
- **Case mode** — film first, answer hidden, reveal on demand, ground truth in
  the 3D view as the answer key. Depends on the annotation overlay above.
- **"Would you have taken this film?"** — the placement solver already scores a
  placement, so a case can require the user to *find* the lesion by taking a
  better exposure. Ties the 0.9.0 placement work to the pathology work.
- **Multiple simultaneous findings**, since real films have them and a
  single-lesion UI will not extend to it gracefully.
- **One scrubber, reused.** Every staged disease shares it. Build it once.

---

## Randomisation — [operator, 2026-09-07]

**What was asked:** "for a given lesion we have a min and max value for size,
location, etc, so when one is selected it looks different each time."

**Taken as a requirement on the whole feature, not a mode.** Selecting
"periapical radiolucency on 30" should not produce the same picture twice. That
changes the shape of the design: **a pathology is a parameter space with
bounds, and a lesion is one sample from it** — so nothing should be authored as
a fixed object, and every disease in the catalogue above needs its ranges
defined alongside it before it is built.

### Every lesion is a spec, not a shape

The unit to build is a **descriptor**: named parameters, each with a min and a
max, plus which measured anchor it is sited on. Drawing a lesion is then
sampling the descriptor and building geometry from the sample. Doing it this way
round means the randomiser is not a feature bolted on afterwards — it is the
only way lesions are ever made, so a hand-picked case is just a sample with the
bounds pinned.

Parameters that most lesions will want:

- **Size** — a diameter range, and for the non-spherical ones an aspect ratio
  and a long-axis orientation.
- **Location** — *not* a free coordinate. A choice among measured anchors (which
  apex, which contact, which furcation, where along the canal), plus a small
  jitter within an anatomically legal envelope. A PARL jittered off the foramen
  by 4 mm is not a variation, it is a different finding.
- **Stage / progression** — for anything staged, which is most of them.
- **Border character** — corticated or not, sharp to ill-defined, as a
  continuum. Argued above to be the parameter that matters most clinically, and
  it is a natural thing to randomise.
- **Contrast / degree of mineral loss** — which is what decides whether the
  lesion is visible at all.
- **Locularity** — unilocular through multilocular, where the disease admits it.
- **Buccal / lingual position** — which determines what a tube shift does to it,
  and is the SLOB lesson.

### Ranges must be clinical, not arbitrary

**A min and a max are claims about the disease.** "PARL diameter 2–12 mm" is a
statement about periapical lesions that a reader will absorb whether or not we
meant it as one, and a dentist will notice immediately if the range is wrong.
So every range needs a source — literature where it exists, the operator's own
read where it does not — and the source belongs in the descriptor next to the
numbers, the same way `method` strings carry sources today.

**Corollary: a uniform distribution between the bounds is itself a claim, and
usually a wrong one.** Real lesion sizes are not uniform. Where a shape is known,
sample from it; where it is not, say that the distribution is a choice.

### Constrained, not just bounded

Independent sampling of independent parameters will produce impossible
combinations. Bounds are per-parameter; validity is joint. Examples that will
bite:

- A lesion large enough to reach past the mandibular canal has to *do something*
  to the canal — displace it or engulf it — not silently intersect it.
- An interproximal caries lesion cannot be wider than the contact it starts at.
- A lesion sited at the apex of 8 or 9 has the nasopalatine canal to contend
  with; that overlap is a *feature* worth sampling deliberately rather than an
  accident to avoid.
- Two randomised findings on adjacent teeth can overlap into a single blob.

So the sampler needs a **validity predicate per disease**, and the honest
behaviour on failure is to resample, not to clamp — clamping piles probability
mass onto the boundary and quietly makes every "large" lesion the same size.

### Seed it from the very first line of code

**`?case=<seed>`, and the seed is decided before anything else.** Randomisation
that cannot be reproduced is not usable for teaching: the operator cannot send a
case to a student, cannot compare two readings of the same film, and cannot
report a bug in one. Retrofitting a seed after the fact means threading it
through everything that ever calls a random number, which is exactly the kind of
change that gets half-done. Every sample comes from one seeded generator, and
the seed is in the URL.

**And record what was sampled, not just the seed.** A case's answer key should
be able to say "PARL, 6.2 mm, non-corticated, on the mesial apex of 30, lingual"
without re-running the sampler.

### One thing to be careful of

Randomising *how a disease looks* is the goal; randomising *what disease it is*
is a different feature. Keep them apart. A user who picks "condensing osteitis"
and gets something that reads as a cementoma has been taught the wrong thing —
so the bounds have to stay inside the finding's own differential, and where two
findings genuinely overlap radiographically (granuloma and cyst, most obviously)
that overlap should be deliberate and stated rather than a consequence of loose
ranges.

---

## Open questions — for the operator

1. **Where should this start? STILL OPEN.** I recorded this as answered on
   2026-09-07 and it was not — the operator endorsed the mimics as a section
   worth having, which is not the same as naming them first. My own preference
   is still sections A and B, because they need no authored geometry; section C
   (caries) is the obvious "real" first disease but wants the bitewing first.
2. **Demonstration tool or quiz?** Case mode with hidden answers is a different
   product from a menu that shows a finding. Both are buildable; they imply
   different UI.
3. **Has anyone looked for incidental findings in his own scan, and does he want
   them looked for?** Measured pathology beats everything authored. It is his
   scan and his call.
4. **Third molars: author impacted eights or leave the gap?** It is the most
   common finding in practice and the one place we would be inventing wholesale.
5. **Where do the ranges come from?** Every min/max is a claim about the disease
   and you will spot a wrong one instantly. Do you want to set them yourself as
   each lesion is built, or should I propose ranges from the literature for you
   to correct?
6. **How loud should the `simulated` label be?** The badge exists. Does a film
   carrying an authored lesion also need a visible watermark, so a screenshot of
   it cannot be mistaken for his real radiograph? My instinct is yes, given the
   anatomy is a named real person's.
