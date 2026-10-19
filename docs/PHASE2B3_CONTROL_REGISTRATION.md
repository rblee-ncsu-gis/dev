# Phase 2B.3: Independent control collection and registration preparation

Assessment date: October 19, 2026.

## Current decision

The analyst-controlled workflow is implemented. **Neither C7 nor C8 can currently
be registered**: each has zero geographic controls, zero independent checkpoints
and zero independently approved image ties. No real point coordinates,
transformation, footprint or registration accuracy have been invented. The
371.19 m locality remains a reference search aid.

The next milestone is actual analyst collection, independent review and a frozen
checkpoint split. Consider similarity registration first where appropriate, and
affine only after collecting distributed controls and checking scan distortion.
Utility matching remains outside this milestone.

## Deliverables

- [Offline control collection](../outputs/phase2b3/c7-c8-control-collection-002/REVIEW.html):
  original composition drawing beside selectable geographic reference vertices.
- [Geographic context review](../outputs/phase2b3/c7-c8-control-collection-002/GEOGRAPHIC_REVIEW.html):
  original corridor/locality results, provenance, stationing and six source crops.
- [Empty real registry](../outputs/phase2b3/c7-c8-control-collection-002/controls.json),
  [decision template](../outputs/phase2b3/c7-c8-control-collection-002/decisions-template.json),
  [control CSV](../outputs/phase2b3/c7-c8-control-collection-002/controls.csv),
  [tie CSV](../outputs/phase2b3/c7-c8-control-collection-002/ties.csv).
- [JSON Schema](geographic_control.schema.json),
  [coordinate-free sample decision format](../examples/phase2b3/control-decisions.template.json),
  [collection configuration](../examples/phase2b3/c7-c8-collection.json).
- [StatePlane feasibility report](../outputs/phase2b3/registration-feasibility-002/FEASIBILITY.md),
  [JSON](../outputs/phase2b3/registration-feasibility-002/registration.json),
  [CSV](../outputs/phase2b3/registration-feasibility-002/registration.csv),
  [residuals](../outputs/phase2b3/registration-feasibility-002/residuals.csv).
- [EPSG:4326 readiness](../outputs/phase2b3/geographic-interchange-readiness-002/registration.json),
  [pending geographic evaluation](../outputs/phase2b3/geographic-evaluation-002/evaluation.json),
  [validation/preservation audit](../outputs/phase2b3/validation.json).

Earlier development snapshots are retained; these links identify the final
collection. Open the review in a current desktop browser. It works offline without
a server, map service, JavaScript package or GIS connection.

## Schema and evidence binding

Controls use a separate schema because they describe physical point identity,
rather than clue transcription. They reuse the existing review identity checks,
analyst-acceptance predicate, timestamps, hashing, CSV utilities, geographic maps
and independent localization reference validator.

| Evidence | Recorded information |
| --- | --- |
| Drawing | PDF identifier/name, SHA-256, sheet, page and drawing ID |
| Original image | Composition PNG hash/dimensions, source bbox, DPI and page-to-pixel mapping; byte-preserved PDF/PNG copies |
| Image point | Continuous pixel X/Y; top-left edge origin, X right/Y down; pixel centres are column+0.5,row+0.5 |
| Geographic point | Original X/Y, EPSG code and units; optional explicitly transformed coordinate with operation provenance |
| Feature identity | Type, description, native GIS feature ID, source/reference and same-physical-point rationale |
| Evidence vintage | Source date, explicitly null when unknown; historical consistency and change notes |
| Accuracy | Estimated reference accuracy in metres, null when unknown |
| Purpose | Fit control or held-out checkpoint; checkpoint independence declaration |
| Review | Human/AI origin, status, reviewer/type, independent declaration, reason and timestamp |
| Audit | Immutable original, before/after correction history, operation IDs and parent registry/decision hashes |

Incomplete proposals may contain null image/geographic coordinates, but cannot be
approved or fitted. Every evidence edit, including a role change, resets acceptance.
Source drawing/image identity is immutable; an existing point cannot be moved to
another sheet by editing its identity.

C7 uses its original **7192 x 4500** composition PNG; C8 uses **7200 x 4509**.
These are Phase 1B page composites, not OCR derivatives or extracted stencil masks.
The original raster manifests remain available. Browser zoom changes display size
only; SVG screen transforms return picks to original pixels. A coarse display pick
is not a subpixel measurement: zoom/refine and document uncertainty where known.

Review decisions are local attestations, not authenticated signatures. Approval
requires a human distinct from the latest evidence author, explicit independence,
complete source evidence and point-identity/historical-consistency rationale.
AI suggestions remain unverified until reviewed. Text-clue acceptance does not
accept a geographic control.

## Analyst collection workflow

1. Select C7 or C8 and inspect the linked context/source crops. The orange locality
   extent is not a drawing footprint.
2. Zoom and click an identifiable physical point: a stable corner, surveyed point,
   culvert endpoint or another independently locatable feature. A station label or
   vague landmark interior needs additional evidence before it can be a control.
3. Independently identify the GIS counterpart. Purple vertices populate exact
   source coordinates in EPSG:4326, native ID and provenance. Connecting geometry
   is displayed, but selection does not establish physical identity. Alternatively,
   enter authoritative EPSG:2264 X/Y from the analyst's read-only GIS investigation.
4. Choose fit or held-out checkpoint **before fitting**. For checkpoints, attest
   independence from fitting. Record source date or leave it unknown, explain
   identity and historical consistency, and supply accuracy only if supported.
5. Enter actor/type and audit reason, then queue the proposal. Existing records can
   be edited, rejected or marked unreadable. Editing resets approval. Independent
   approval needs a separate human identity and explicit review checkbox.
6. Download the decision JSON and apply it with the Python command into a **new**
   bundle. Browser operations are drafts; reopen the new review for committed
   statuses and correction history.
7. Collect distributed controls and reserve separate checkpoints. Low training
   residuals cannot replace checkpoint evidence.

The UI can reload a draft for export; imported operations remain in its queue.
Apply that draft and reopen its resulting bundle before editing resulting records.
Use the latest bundle's hash-bound template, rather than the generic blank sample.

Landmark input points remain context and cannot be selected as controls. The
backend also rejects direct reuse of known input coordinates and requires an
independent-evidence declaration. These checks supplement provenance; they cannot
prove independence of an incorrectly asserted manual investigation.

## Cross-sheet ties

The accepted title ranges meet at station 78+75. Existing source inspection found
reciprocal C7/C8 matchlines, increasing labels, similar north arrows, FM annotations
and the nearby station 78+46 collar. That inspection remains AI-reviewed evidence,
not an independently accepted point correspondence.

In adjacent-sheet tie mode, click a feature in one drawing and use the left-pick
button, then select the other drawing and use the right-pick button. Describe the
matched feature and retain both source identities and image positions. Station text
is optional. Assigning station 78+75 requires actual verification of that feature's
station on both sheets; title continuity alone is insufficient.

Ties have **no geographic-coordinate field**. They support ordering/consistency,
but never augment geographic controls, propagate extents or manufacture station
coordinates. Each sheet is fitted independently. The real tie list remains empty.

## Coordinate systems and transformation policy

- **EPSG:2264** retains county easting/northing in **US survey feet**. Calculations
  multiply native coordinates by exactly **1200/3937** for metres, and divide by
  that factor for predicted native output. This is a unit conversion, not a datum
  conversion. Preserve legacy CRS units; international feet differ.
  [NIST survey-foot definition](https://www.nist.gov/pml/us-surveyfoot).
- **EPSG:4326** uses longitude, latitude in degrees. Accepted controls are projected
  to the existing WGS84 ellipsoid east/north metre frame, with origin at the fit
  controls' mean longitude/latitude. Origin, matrix and inverse mapping are recorded.
  The frame is bounded to county distances within 250 km. Affine fitting and metre
  residuals are not calculated directly in degrees.
- **Cross-datum conversion is explicit and external.** pyproj is absent; no converter
  or dependency was installed. Retain the original coordinate and optionally supply
  transformed X/Y with a transformation object containing source_crs, target_crs,
  exact input_xy/output_xy, axis_order of x,y, operation name, software/version,
  evidence source, timezone-qualified performed_at, datum/grid notes and ballpark
  set to false. Operation accuracy may be known or null. Independent review covers
  this conversion evidence too.
  [PROJ datum-transformation guidance](https://proj.org/en/stable/usage/transformation.html).

Mixed CRS points without documented alternate coordinates are excluded with an
explicit reason. Do not relabel NAD83 as WGS84 or survey feet as metres. Prior user
confirmation of the WGS84 context exports does not establish the datum/epoch or
operation for a newly supplied StatePlane control.

## Registration methods and validation gates

NumPy **2.3.5** is already installed and is loaded for sufficiently constrained fits.
Another environment without NumPy receives a capability diagnostic. No mandatory
dependency was added.

| Method | Minimum usable fit points | Additional requirement |
| --- | ---: | --- |
| Rigid | 2 distinct | Independently accepted fixed metres-per-pixel scale; rotation/translation after unit scaling |
| Similarity | 2 distinct | Nonzero image/ground separation; positive uniform scale, rotation and translation |
| Affine | 3 | Non-collinear, adequately distributed image and ground coordinates |

Fit points closer than 0.001 pixel or 0.001 m are rejected as duplicates. Image
span must reach one pixel and ground span 0.001 m. Affine source/target condition
numbers must not exceed the pilot limit of 1000; near-line sets request
off-alignment controls. These are numerical guards, not recommended spacing or
accuracy tolerances.

Rigid/similarity fitting negates row-down image Y internally. The exported 3x3
matrix incorporates this convention and accepts original row-down pixels. Affine
uses centred/scaled least squares; rigid/similarity use SVD. Diagnostics retain
spans, condition numbers, image bbox coverage, orientation and whether a fit is
exactly determined. [NumPy least squares](https://numpy.org/doc/2.3/reference/generated/numpy.linalg.lstsq.html),
[NumPy SVD](https://numpy.org/doc/2.3/reference/generated/numpy.linalg.svd.html).

Minimum-point similarity/affine fits can have nearly zero training error by
construction. Prefer more controls, spread along and across the plan. A line of
controls cannot establish general two-dimensional scan distortion.

Outputs include parameters, fit/checkpoint residuals (predicted minus observed X/Y
and radial error) and radial RMS: the square root of the mean of dx squared plus
dy squared, in metres. This is not a degrees-of-freedom-adjusted survey uncertainty.
Outliers are never silently deleted.

Summary validation requires **at least two distinct independently approved
checkpoints**, unused for fitting. Duplicate fit locations/pixels and duplicate
checkpoints do not count. A model may fit without checkpoints; checkpoint RMSE then
stays null and validation remains pending. Unknown reference accuracy allows
qualified agreement reporting, not a positional-accuracy claim. Even known-accuracy
results describe agreement with those references, not survey certification,
production accuracy or confidence intervals. The small minimum is a pilot gate.

No image is warped, PDF rewritten or fitted footprint accepted. Historical road
realignment, parcel revisions, facility relocation and ambiguous physical identity
remain potential systematic errors.

## Actual C7/C8 feasibility

| Sheet | Proposed controls | Approved fit points | Approved checkpoints | Approved ties | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| C7 / s07772.pdf | 0 | 0 | 0 | 0 | Not fitted |
| C8 / s07773.pdf | 0 | 0 | 0 | 0 | Not fitted |

For **each sheet**, similarity needs two complete independently approved fit
controls; affine needs three well-distributed controls. Rigid additionally needs
independent scale evidence. Each method separately needs two held-out approved
checkpoints for summary validation. Both EPSG:2264 and EPSG:4326 assessments
report these gaps explicitly.

All real models, fit RMS and checkpoint RMSE remain null. Existing AI observations,
11 accepted text clues and landmark coordinates do not substitute for controls.
No real registration accuracy is reported.

## Commands and independent evaluation

Run from the repository root using unused output directories:

    $pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
    & $pythonExe scripts/run_asbuilt.py controls-init outputs/phase2b2/county-c7-c8-002/localization.json --config examples/phase2b3/c7-c8-collection.json --output outputs/phase2b3/control-collection-next
    & $pythonExe scripts/run_asbuilt.py controls-apply outputs/phase2b3/c7-c8-control-collection-002/controls.json path/to/downloaded-control-decisions.json --output outputs/phase2b3/control-review-next
    & $pythonExe scripts/run_asbuilt.py registration-assess outputs/phase2b3/control-review-next/controls.json --methods similarity affine --target-crs EPSG:2264 --output outputs/phase2b3/registration-next

Use the optional rigid-scale JSON argument only with an independently accepted
scale record: metres_per_pixel, source, last_evidence_author, verified status and
the existing independent human verification fields. AI interpretation of the
printed scale alone is insufficient.

Applying controls checks registry/file hashes, validates the entire batch in memory,
and creates a new snapshot retaining parent registry, decisions, source files,
history, CSVs, accepted-only JSON and updated review. Replayed operation IDs on the
same branch and stale hashes are rejected. Do not hand-edit frozen registries or
overwrite earlier output directories.

The existing localization evaluation template and command are reused. The preserved
context run and hash-bound geographic-evaluation-template retain null decisions.
Input landmarks and fitted predictions cannot supply independent truth. Approved
checkpoint observations can pass the existing control-point reference validator
only with documented EPSG:4326 and known accuracy; duplicated fit evidence is
excluded. Human drawing-area/candidate decisions remain separate.

    & $pythonExe scripts/run_asbuilt.py localization-evaluate outputs/phase2b3/control-review-next/localization-input.json path/to/independent-geographic-review.json --output outputs/phase2b3/geographic-evaluation-next

Current evaluation has two pending drawings and null Top-1/Top-3/Top-5 recall.
Neither text acceptance nor point collection alone verifies a footprint.

## Verification and next session

**240 tests pass**, preserving the previous 207 and adding 33 cases covering
source/pixel/CRS validation, history, correction resets, AI/self-approval rejection,
stale/tampered evidence, ties, synthetic transforms, poor/duplicate geometry,
checkpoint leakage, mixed CRS abstention and safe offline payloads.

An installed-browser check on **synthetic-only drawings** passed eight interaction
checks, including zoom/scroll mapping, GIS picks, edits, sheet binding and image-only
ties. Its draft applied into a separate synthetic snapshot. No synthetic point
entered C7/C8. The real page was visually checked without entering controls.

The audit preserves **91 existing files**, including the original 25 protected
artifacts, the Phase 2B.2 output tree, approved clues, original images, reference
exports and landmark/alias evidence. All remain unchanged. No packages, ArcGIS
Python settings, SDE features or PDF-to-asset links were modified.

For the first session, collect at least **three distributed candidate fit points
and two separately reserved checkpoints per sheet**, with more if affine distortion
needs assessment. Seek across-plan separation, corroborate historical identity,
and record a real shared image tie only where verified on both sheets. Review
independently before fitting; keep sheet extents independent and expand the
dataset before broader accuracy claims.
