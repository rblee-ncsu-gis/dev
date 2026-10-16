# Phase 1: first real-world PDF extraction assessment

Assessment date: October 16, 2026 (America/New_York).

The batch successfully recovered page images and document structure from four
drawings, but recovered **no embedded text and no vector drawing paths**. All four
require OCR or manual transcription before a text-based geographic localization
pipeline can use their labels. This is a successful extraction of raster-only
documents, not evidence of a processing failure.

## Evidence and verification

Assessed run: `480cf227-e120-4c3a-bf00-ef46cecf9f58`, recorded from
17:30:18.647257 to 17:30:19.824929 UTC on October 16, 2026
(13:30:18–13:30:19 EDT). Sources were `src/pdf`; extraction used PyMuPDF 1.28.2,
100 DPI previews and a 16-million-pixel preview cap.

Primary evidence:

- [Document CSV](../src/outputs/assessment-001/documents.csv)
- [Page CSV](../src/outputs/assessment-001/pages.csv)
- [JSON inventory](../src/outputs/assessment-001/inventory.json)
- [Batch log](../src/outputs/assessment-001/batch.log)
- Per-document manifests, text files, previews and error logs under
  `src/outputs/assessment-001/documents/document-00001` through `document-00004`.

The review compared every shared CSV/JSON field and row order, verified the four
current source SHA-256 hashes against their inventory and manifest values, checked
page counts and actual text-file lengths, and inspected all four previews.
Read-only inspection of the source PDFs also confirmed native image dimensions
and full-page image placement. No OCR, external geocoding, GIS lookup or coordinate
registration was performed. No dependencies or environment settings were changed.

## Recovery results

Each document contains one page. All pages are landscape with PDF rotation 0.
Dimensions below are displayed paper dimensions, not geographic extents.

| Document | Pages | Page size, points | Size, inches (rounded) | Text characters | Vector paths | Image instances | Classification | Status |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- | --- |
| s07770.pdf | 1 | 2589 × 1615 | 35.96 × 22.43 | 0 | 0 | 1 | scanned | complete |
| s07771.pdf | 1 | 2589 × 1622 | 35.96 × 22.53 | 0 | 0 | 1 | scanned | complete |
| s07772.pdf | 1 | 2589 × 1620 | 35.96 × 22.50 | 0 | 0 | 1 | scanned | complete |
| s07773.pdf | 1 | 2592 × 1623 | 36.00 × 22.54 | 0 | 0 | 1 | scanned | complete |

- **Extractable vector geometry: 0 of 4 drawings (0%).** Neither drawing paths
  nor vector operations were recovered. Visible pipes, symbols and profile grids
  are pixels; they cannot be recovered as utility features through direct PDF
  path extraction in this sample.
- **Meaningful embedded text: 0 of 4 drawings (0%).** All four page text files
  exist and are empty, so this conclusion does not depend on a character-count
  threshold. Labels visible to a person are not embedded searchable text.
- **OCR candidates: 4 of 4 drawings (100%):** s07770.pdf, s07771.pdf,
  s07772.pdf and s07773.pdf. Their manifests all set `ocr_recommended: true`.
  OCR is needed for automated label recovery; manual transcription remains an
  option for a small localization reference set. OCR is not needed merely to
  display the drawings.
- Four image instances were recovered across four pages; all four source hashes
  are distinct. No vector or mixed-content documents occurred in this batch.

## Geographic localization suitability

**None is ready for unattended text-based localization from the current extracted
artifacts.** Nevertheless, the previews contain useful geographic evidence.
The following labels are human visual observations, not OCR results or verified
GIS matches. All sheets show the project title “City of Southport Transmission
Facilities” and “Hwy 211 Force Main,” with NC 211 / Supply Road labels. The
previews show consecutive sheets C5–C8 and adjoining station ranges, supporting
review as one drawing sequence rather than four independent projects.

| Priority after label recovery | Document / visible sheet | Visible localization evidence | Assessment |
| --- | --- | --- | --- |
| 1 | s07773.pdf / C8 | NC 211 / Supply Road; Cape Fear Memorial Park Cemetery; Sentry Self Storage; STA. 78+75 to 90+25 | Strongest initial candidate: multiple named landmarks plus road alignment and station context. Landmark names and historical locations require verification. |
| 2 | s07772.pdf / C7 | NC 211 / Supply Road; Cape Fear Memorial Park Cemetery; STA. 66+50 to 78+75 | Strong companion candidate; cemetery and adjoining C8 station range can help constrain a corridor segment. |
| 3 | s07770.pdf / C5 | NC 211 / Supply Road; Regency Crossing; STA. 42+75 to 55+00 | Additional named crossing may constrain a segment once its identity is verified against reference data. |
| 4 | s07771.pdf / C6 | NC 211 / Supply Road; STA. 55+00 to 66+50; adjoining-sheet match lines | Useful for continuity, but fewer distinctive named geographic anchors were apparent in the preview. |

This order is qualitative pilot selection, not a computed confidence score. Road
names and the project municipality constrain a search area but do not establish
exact coordinates. Stationing is project-relative and needs an anchored alignment;
it is not a state-plane coordinate. North arrows and graphic scales provide
orientation/scale clues, not geographic position. The engineering consultant's
Wilmington address in the title block must not be used as the asset location.

The top portions contain plan views and the lower portions contain longitudinal
profiles. Geographic registration should target the plan view, excluding profile
grids, title blocks and marginal notes. The apparently adjoining station ranges
provide a useful consistency check but do not prove spatial registration.

## Limitations and extraction errors

**No reported extraction errors:** batch status is `complete`, all four documents
are `complete`, all four page records are `ok`, JSON errors are empty and CSV error
fields are blank. All four per-document extraction logs are zero bytes, consistent
with their error-only logging; the batch log records all four processing steps.
There were no reported encrypted, corrupt, skipped or partially extracted PDFs.

The principal limitations are informational:

1. **Raster-only input.** The inventory's scanned classification is consistent
   with source inspection: each image fills its page. All four PDFs identify
   themselves as PDF 1.3 with producer `ImageMill Imaging Library v2.021 2011`.
   Title, author, subject, keywords and creation/modification date metadata are
   blank. Those fields cannot currently supply location or revision evidence.
2. **Preview resolution loses available detail.** Source images are
   7192 × 4487, 7192 × 4508, 7192 × 4502 and 7200 × 4510 pixels respectively,
   approximately 200 effective DPI at their PDF placement sizes. Generated
   previews are 3596 × 2244, 3596 × 2253, 3596 × 2250 and 3600 × 2255 at 100 DPI.
   The preview cap did not bind, but default rendering approximately halved each
   dimension. Full-resolution sources may improve small-label OCR; upsampling
   beyond source resolution does not restore missing detail.
3. **Image presence is not OCR quality.** A count of one image says nothing about
   legibility, skew or recognition accuracy. Some labels are faint, small,
   vertical or overlapped by linework. Dense profile grids create distractions.
   Preview readability does not establish OCR performance.
4. **No geographic transform is established.** Manifests contain page geometry
   and preview transforms, with `gis_transform: null`. This assessment does not
   certify whether other PDF geospatial structures exist; it establishes that
   this extraction produced no validated map-to-ground registration.
5. **Limited sample diversity.** Four visually related sheets of one project
   cannot establish collection-wide raster/vector proportions, OCR accuracy,
   location success rates or asset-matching feasibility. The planned 10–20
   varied-document sample has not yet been reached.
6. **Current output is an inventory.** It has no text bounding boxes, road-name
   candidates, plan-view masks, native raster export, reviewed geographic links
   or calibrated scores. Zero extracted paths does not mean there are no utilities
   depicted; zero text does not mean there are no readable geographic labels.

## Changes before geographic localization development

Retain the existing ingestion and batch modules. These results do not justify a
new AI framework or a change to the ArcGIS Pro environment. Prioritize:

1. **Preserve native raster evidence using the existing PDF dependency.** Add
   optional native-image export and record image dimensions, placement transform,
   effective DPI and provenance. Support bounded high-resolution plan/title-block
   crops or tiles rather than relying on the 100-DPI review preview for OCR.
   A full native sheet here is about 32 million pixels, above the current preview
   cap; raising DPI alone does not guarantee native resolution under that cap.
2. **Record reviewed regions and clues.** Add plan/profile/title-block region
   annotations in page coordinates, manual transcription fields, and evidence
   locations. Start with the road, cemetery, storage landmark, sheet IDs and
   station ranges above. Keep consultant addresses separate from plan geography.
3. **Provide an optional OCR interface, not a mandatory dependency.** Define
   outputs for recognized text, bounding boxes, engine/version, recognition scores,
   crop/rotation transforms and reviewer corrections. Leave OCR unavailable when
   no approved engine exists. Any later installation requires separate approval;
   this assessment does not authorize one. Manual entry can validate the interface
   and localization logic in the meantime.
4. **Broaden and label the reference set.** Inspect 10–20 varied PDFs including
   vector originals, mixed pages, multi-page sets and difficult scans. Establish
   analyst-verified geographic clues and known drawing locations before scoring
   automated candidates. Keep related sheets together when designing evaluation
   splits so project continuity does not inflate apparent generalization.
5. **Keep localization candidates reviewable and GIS access separate.** Start
   with approved offline road/parcel reference extracts when available, retaining
   source/version and CRS metadata. Permit ambiguous or absent candidates. Resolve
   ArcPy licensing independently; do not access GEOBASE or publish links as part
   of this preparation.

## Recommended next milestone

**Phase 1B: raster evidence preparation and verified geographic clue recovery.**
Use C8 (s07773.pdf) first, followed by C7, to test recovery of road and landmark
labels from native-resolution plan/title-block regions. Begin with manual
transcription under the current environment constraints; evaluate local OCR only
after an approved engine is available. Deep learning and direct vector parsing
are not supported as the next priority by this sample.

Deliverables should include native raster/crop provenance, page-to-pixel mappings,
reviewed plan-view regions, corrected label evidence and a broader verified
reference set. Measure correct recovery of geographic clue phrases and analyst
correction effort, not just total OCR characters. Report unanswered clues rather
than filling them by inference.

Proceed to geographic localization once these labels can be supplied reproducibly
and suitable approved geographic reference data are available. Evaluate C8/C7
candidate corridor placement against analyst-verified locations, then test the
less distinctive sheets and unrelated projects. Exact georeferencing requires
verified controls and independent checkpoint errors; the present assessment
supports candidate-area research, not exact asset association or publication.
