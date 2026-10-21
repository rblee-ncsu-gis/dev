# Phase 3B — Analyst-reviewed view selection and scale calibration

Assessment date: 2026-10-21.

## Management assessment

The working pilot contains **nine proposed views on six pages from five PDFs**: seven engineering views, one not-to-scale vicinity map and one supporting-document region. It reuses Phase 3A `study-003`, existing composition rendering/OCR and Phase 2B.3 control validation. Reviewers can drag or enter boundaries, confirm reading orientation, inspect actual native segments, measure raster/pixel bars and export hash-bound decisions into new snapshots.

**No real view or scale has been independently accepted. No effective scale, geographic position or registration accuracy is claimed.** The real handoff therefore contains zero accepted views and nine pending view IDs. This is an evidence gate, not a software failure. Synthetic integration tests demonstrate the accepted-view/calibration/handoff path without approving county drawings.

Selective Tesseract OCR completed **27/27 recognition attempts**: nine focused crops across baseline, grayscale and threshold variants. It recovered useful outlined lettering absent from native extraction, but also symbol/grid noise, fragmented road names and stationing errors. Confidence and nonempty output are not accuracy. No transcription or scale-error scores were calculated without independent reference acceptance.

The first ArcGIS toolbox prototype should be a **preparation-only handoff consumer**: validate an accepted view and hashes, convert its annotated composite to a lossless TIFF, retain page/image mappings, and open the existing control workflow. Do not implement automated placement, registration or asset associations. First complete actual view/scale review and collect independent controls/checkpoints for one bounded view.

## Deliverables and final entry points

The final review bundle is **[review-001](../outputs/phase3b/review-001/REVIEW.html)**. It combines the final pilot preparation and OCR evidence, with **no human decisions applied**. Its parent continuation has an empty operations list; it only assembles the current contract/presentation. Earlier pilot/OCR directories remain development history.

| Artifact | Purpose |
| --- | --- |
| [config/view-pilot.json](../config/view-pilot.json) | Nine proposed boundaries, reading orientations, view types, selection reasons and OCR focuses |
| [views.json](../outputs/phase3b/review-001/views.json), [views.csv](../outputs/phase3b/review-001/views.csv) | Immutable view-level source/frame/review history and results |
| [scales.csv](../outputs/phase3b/review-001/scales.csv) | Literal statements, measured native span, OCR candidates, source references and acceptance states |
| [REVIEW.html](../outputs/phase3b/review-001/REVIEW.html) | Offline visual boundary/scale editor with annotation-preserving full-page images |
| [comparison.html](../outputs/phase3b/review-001/comparisons/498b28d5-926e-4f40-b1b8-6238c322a7eb/comparison.html) | Source focus images beside native versus OCR text; links to existing OCR word-box/confidence report |
| [comparison.json](../outputs/phase3b/review-001/comparisons/498b28d5-926e-4f40-b1b8-6238c322a7eb/comparison.json) | Separate, unmerged transcriptions, source revisions, words/boxes/confidence and pending evaluation |
| [handoff.json](../outputs/phase3b/review-001/handoff.json) | Accepted engineering views only; currently empty, with explicit pending IDs |
| [handoff schema](arcgis_view_handoff.schema.json) | Versioned source, boundary, orientation, composite, mapping, evidence and intended-CRS contract |
| [decisions-template.json](../outputs/phase3b/review-001/decisions-template.json) | Current parent hash and empty operation list |
| [review-effort.json](../outputs/phase3b/review-001/review-effort.json) | Operation counts and self-reported elapsed time/interactions; currently zero actual review effort |
| [validation.json](../outputs/phase3b/validation.json), [tests-final.xml](../outputs/phase3b/tests-final.xml) | Test, schema, image/source hash and preservation audit |

## Pilot selection and evidence scope

All boundaries and view classifications below are AI proposals for analyst review, not accepted extents. Selecting a manageable subset under the authorized pilot does not accept its page/view classifications. The other 69 page records do not need approval before these nine views can be reviewed.

| View | Source | Reason and scale boundary |
| --- | --- | --- |
| `c7-plan` | `s07772.pdf`, p1 | Scan with NC 211/Supply Road, stationing and a graphic scale; existing C7 locality/control frame available |
| `c7-profile` | Same page | Separate longitudinal profile; horizontal/vertical scales must be established separately |
| `c8-plan` | `s07773.pdf`, p1 | Adjacent scan with roadway/landmark labels and graphic scale; no automatic calibration inheritance from C7 |
| `c8-profile` | Same page | Companion profile, independently scoped from the plan above |
| `closeout-p23-plat` | Closeout package, p23 | Native subdivision geometry and outlined labels; footer scale/bar evidence lies outside the proposed main plat boundary |
| `closeout-p23-vicinity` | Same page | Explicit NTS inset tests exclusion from main-plan scale |
| `closeout-p24-support` | Closeout package, p24 | Certificates, tables and survey notes rather than another plan; repeated footer scale must not calibrate this supporting region |
| `calabash-vector-plan` | Rotated Calabash as-built, p1 | Native linework/outlined labels with separate markup; only one of the duplicate base drawings is selected |
| `calabash-redev-plan` | Calabash redevelopment sheet 8, p1 | Raster utility plan with nine PDF annotations, preserving colored construction-review context |

The seven engineering views are unresolved for effective calibration. The vicinity inset is proposed NTS and the supporting region is not applicable to engineering calibration; those recommendations are also unaccepted. Both closeout pages are included without pretending page 24 contains another main plat view.

The pilot is not an archive sample or independent accuracy dataset. Adjacent sheets, multiple views of one page, reused source pixels and preprocessing derivatives must not count as independent references. Calabash's unrotated duplicate and the standalone scans repeated inside the closeout package are not added as new accuracy examples.

## Coordinates, composition and reproducible preparation

Use **unrotated visible-page MuPDF coordinates**, top-left origin, X right/Y down, **72 points/inch**. Record original page rotation, media/crop/other boxes and original rotation/derotation matrices separately. Neither PDF points nor image pixels are geographic coordinates.

The bundle contains six new full-page high-resolution composites and nine view crops, all RGB PNG with visible annotations rendered. Original Phase 3A previews remain separately preserved. Requested preparation is 200 DPI with a 40-million-pixel cap; actual effective DPI and any cap are recorded. The large Calabash vector view is capped, rather than silently treated as a 200-DPI image. Raster display picks should be zoomed/refined and have uncertainty recorded; display scale does not create subpixel accuracy.

Rendering reuses `raster.render_region`. Reading orientation uses the existing OCR adapter's reversible orthogonal rotation, preserving the unrotated composition. Each crop stores page-to-image, image-to-page, unrotated and orientation mappings. Handoffs also distinguish page-origin coordinates from view-local points. Pixel measurements name the exact bound image and hash; they are transformed back to page points before measuring. Measurement endpoints may be in a footer outside the view, but its applicability to the particular view/axis must be independently established.

For C7/C8, references point to the **existing Phase 2B.3 collection and original composition frame**, not substituted crop coordinates. Its source/control validator is reused. Both drawings still have zero control/checkpoint records. The 371.19 m localities remain unverified context/model-input hints. Calabash and closeout views have no matching drawing binding in that control collection; no new control coordinates or GIS references are invented.

## Scale stages and safeguards

The implementation separates:

1. **Detected statement:** literal native/OCR candidate with source position and unverified status.
2. **Analyst-verified statement:** independent transcription acceptance. Ambiguous `FEET` may remain unqualified; accepting the words does not establish their effective scale or foot definition.
3. **Measured graphical scale:** bound native/page/pixel endpoints with stated ground distance and explicit metre, international foot or US survey foot units. Measurements remain unverified until independent acceptance.
4. **Calibrated effective view scale:** derived only when the view, scale scope, resizing/distortion assessment and applicable graphical evidence are independently accepted and consistent.
5. **Unknown/unreliable:** incomplete units/distance, unresolved applicability, NTS, stale scope or conflicting evidence leaves calibration unresolved.

The nominated native segment near the closeout-p23 scale is **216 PDF points long**. Its exact path/item indices and endpoints come from exported native geometry. **Its ground distance is deliberately unknown** until an analyst identifies the intended bar ticks and stated distance. Native precision does not establish physical scale, accuracy or geographic position.

Printed `1 INCH = 60 FEET` and the separate `not to scale` statement are retained for the relevant closeout pages as unaccepted evidence. The same footer can be visible to several view records without becoming applicable to each. OCR adds three unaccepted NTS transcriptions from the vicinity focus. The final bundle has **ten scale-evidence records**: six native statement references, one native measured span and three OCR candidates. Repeated references are not independent corroboration.

Metric conversion for a measured bar is stated-ground-metres / endpoint-distance-in-page-points. Native segment endpoints must match actual exported line coordinates. Isotropic scope requires explicit accepted uniformity/distortion assessment; one bar cannot establish distortion throughout a scan. Engineering profiles require separate horizontal and vertical evidence, with direction checked against reading orientation. Plan scales never transfer automatically to profiles, insets or another sheet.

Accepted current-view scale ratios differing by more than the default **2% consistency tolerance** produce a conflict with no effective scale exported. This tolerance is a diagnostic threshold, not measured accuracy. A reviewer can explicitly classify a resized plot's printed statement as `nominal_only`, or exclude inapplicable evidence with a reason; the software never silently chooses a favorable scale. Accepted evidence with unresolved applicability/units continues to block calibration. Rejected evidence remains in history.

Scale error is calculated only against independently accepted, held-out measurements, with explicit independence from calibration. Reusing calibration endpoints, reversed endpoints or the same source reference is excluded from validation. No real check measurements exist here, so scale error remains unmeasured. Geographic positional accuracy is never derived from a scale-distance check.

## Actual selective OCR observations

The configured run uses installed **Tesseract 5.4.0.20240606**, English, OEM 1, sparse-text PSM 11, baseline/gray/threshold variants, and one focused crop per view. Executable and model hashes, configuration, source-image hash, preprocessing, text, confidence and page-mapped word boxes are retained by the existing OCR adapter. No reference text/type enters OCR inputs.

Native base text was absent in **eight of nine focuses**; the vicinity focus had 36 characters. OCR produced nonempty output for every attempt. Selected observations below are AI inspection of outputs/source imagery, **not independently verified transcription scores**:

- C7 plan: `NC 211 - SUPPLY ROAD` recovered with unrelated noise around linework.
- C7 profile: baseline/gray recovered a run of station labels including `70+50`, `71+00` and `73+50`; thresholding produced examples such as `70+-50` and `73400`.
- C8 plan: graphic-scale words/numerals recovered, but quotes, feet symbols and line ordering fragmented the printed statement. Manual confirmation remains necessary.
- C8 profile: force-main/pipe notes partially recovered with grid interference, including confusion in `INCH` and `C905` strings.
- Closeout p23: outlined road text fragmented (for example `HICKM` / `AN RD.`). Coordinate-looking numbers were recognized but are not accepted survey controls.
- Vicinity map: `VICINITY MAP`, `not to scale` and parts of landmark labels recovered; native and OCR text stay separate.
- Closeout p24: substantial outlined survey/datum/unit notes recovered that native extraction missed. OCR's apparently strong confidence does not verify datum spelling, epoch or units for registration.
- Calabash vector plan: lot/structure numbers, dimensions and part of a street label recovered despite zero native base text.
- Calabash redevelopment: construction/lot/service notes recovered with interference from geometry and markup.

No preprocessing variant is ranked as most accurate. Baseline/gray agree on some text, and thresholding can both change and damage labels. Independently accepted references, per-class coverage and held-out examples are needed to compare accuracy. OCR results are not merged with native text or previously approved geographic clues.

## Analyst workflow

Open the final `REVIEW.html` in a desktop browser; it works offline without a server, JavaScript package or GIS connection.

1. Choose a view, inspect the full composite and proposed oriented crop, then drag a boundary or enter page X0/Y0/X1/Y1. Confirm view type, relevance and clockwise reading orientation. NTS/administrative regions remain separate.
2. Enter actor/type and audit reason; queue a correction if needed. Download decisions and apply to a **new** snapshot. Reopen that snapshot before further measurement to bind the current view revision.
3. Independently accept/reject/unreadable the view. Acceptance requires a human distinct from its latest evidence author, consistent with existing Phase 2B.3 review rules. A correcting analyst needs another independent reviewer for acceptance. This is local attestation, not authenticated identity management.
4. Inspect native/OCR statements, assign their applicable scope (`current_view`, `nominal_only`, `excluded`, `unresolved`) and retain unresolved units where necessary. Statement acceptance alone cannot calibrate.
5. Select an actual native segment or pick/enter raster bar endpoints. For pixel coordinates, choose the bound page/crop image. Enter supported stated ground distance and units, axis, source reference, applicability, distortion assessment and uncertainty notes. Preview the computed relationship; save it as unverified evidence.
6. Independently review the scale evidence in a new snapshot. Calibration status is recomputed from the current accepted evidence. Collect separate independent check measurements only where suitable reference evidence exists.
7. Inspect `handoff.json`; only independently accepted engineering views appear. Unknown scale can remain explicit for a preparation-only package. Calibrated scale remains unrelated to geographic registration.

Boundary edits invalidate **that current boundary acceptance**, retaining its history. Separate scale transcription/measurement approvals are not erased; changed view scope is marked stale until explicitly reconfirmed. Editing one scale affects only that current record. Prior page classifications, geographic clues, control approvals and snapshots remain untouched. Decisions must bind the current registry hash and use unreplayed operation IDs. PDF, study, image, native-evidence and control hashes are checked before processing and source bindings are rechecked after rendering/OCR.

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'

# Reproduce proposed pilot in a new directory.
& $pythonExe scripts/run_asbuilt.py views-init outputs/phase3a/study-003/inspection.json `
  --config config/view-pilot.json --output outputs/phase3b/pilot-next

# Apply downloaded decisions; use the final bundle or the latest resulting snapshot.
& $pythonExe scripts/run_asbuilt.py views-apply outputs/phase3b/review-001/views.json `
  outputs/phase3b/view-decisions.json --output outputs/phase3b/analyst-review-next

# Optional independent recognition run; no scoring or approval.
& $pythonExe scripts/run_asbuilt.py views-ocr outputs/phase3b/analyst-review-next/views.json `
  --config config/view-ocr.json `
  --tesseract 'C:\Users\ricky.lee\AppData\Local\Programs\Tesseract-OCR\tesseract.exe' `
  --output outputs/phase3b/ocr-next
```

Adding another pilot region currently means adding its page/boundary/ID to the configuration and creating a new proposal branch. The editor corrects/reviews the configured views; it does not silently split or reassign their source pages. OCR focuses are deliberate source regions. If a revised boundary excludes its original focus, the runner records the missing focus rather than silently clipping to a different target. Prior OCR applicability must be reconsidered after a view revision.

## ArcGIS handoff and first prototype

Schema version 1 includes source SHA-256/page/drawing identity, accepted boundary/orientation, original rotation/boxes, current prepared composite settings/hash, page/view-local/pixel mappings, native/OCR evidence, full scale records/history, calibration status, limitations, locality hints and existing control-frame references. Its `map_crs` is **null** and `registered` is **false**. **EPSG:2264 is only the intended future output CRS**. EPSG:4326 interchange policy from Phase 2B.3 remains unchanged; no datum conversion is performed.

The package currently provides lossless annotated PNG inputs and a TIFF-preparation specification, not a georeferenced TIFF. A later Basic toolbox can use **Copy Raster** to prepare a new TIFF without dropping annotation pixels, then load the original Phase 2B.3 control frame. Esri documents TIFF conversion and Basic availability. This has not been executed or validated against the local ArcPy licensing problem. [Esri Copy Raster](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/data-management/copy-raster.html).

Do not use Define Projection on page coordinates, create a world file from printed scale alone, or turn a locality into a footprint. Cropping/reading orientation are image preparation, not geographic registration. Reference matrices follow the existing [PyMuPDF affine convention](https://pymupdf.readthedocs.io/en/latest/matrix.html).

## Missing evidence versus software validation

**Remaining real analyst work:** accept/reject nine boundaries/types/orientations; assign applicable scale statements; identify graphical ticks, distances and units; assess resizing and separate profile axes; resolve nominal/current-view conflicts; supply independent check lengths if scale error is to be measured; collect independent geographic controls/checkpoints using the existing workflow. No actual labor-saving estimate is possible while review operations remain zero. Browser interaction counts/time are self-reported active-session observations, not authenticated work measurements.

**Software verification:** **328 tests pass: all 280 prior tests plus 48 new cases**. They cover multiple views, source/annotation preservation, raster/vector bar measurement, all four orthogonal rotations, crop mappings, NTS, profile axes, resizing/conflicts, incomplete/rejected/self/AI reviews, immutable history, stale hashes and evidence, repeated OCR runs, handoff gating and held-out measurement exclusion. Synthetic numeric correctness is not field calibration accuracy.

All **702 protected files** remain unchanged, including the original 204/25. The final bundle's 208 bound files and 39 external bindings validate; CSVs contain nine views and ten scale records. All local report links resolve. The handoff schema passes validation for the actual pending package and a separately labeled synthetic accepted-view example; premature geographic-CRS assignment is rejected. These schema checks used the already installed validator without adding a runtime project dependency. Browser checks passed ten interaction/export safeguards using simulated AI drafts, with no decisions applied. See `validation.json`, `schema-validation.json` and `visual-002/browser-check-result.json` for evidence.

No original PDF/DWG, GIS export or approved evidence was changed. No package/environment change, ArcPy call, enterprise edit, geographic registration, invented control or asset association was made.
