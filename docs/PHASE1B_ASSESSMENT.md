# Phase 1B raster and geographic clue assessment

Prepared October 16, 2026. All four source PDFs were processed with PyMuPDF 1.28.2
without changing the Python environment. Output is under
[`outputs/phase1b-final`](../outputs/phase1b-final). Every run completed with an empty
error list and unchanged source SHA-256. C7 and C8 received focused region crops
and preliminary manual clue entries; C5/C6 received native exports and composites.

## Raster recovery and fidelity

| Source / sheet | Native pixels | Estimated placement DPI, X / Y | 200-DPI page composite | Focused crops | Preliminary clues |
| --- | --- | --- | --- | ---: | ---: |
| s07770.pdf / C5 | 7192 × 4487 | 200.01 / 200.04 | 7192 × 4487 | 0 | 0 |
| s07771.pdf / C6 | 7192 × 4508 | 200.01 / 200.11 | 7192 × 4506 | 0 | 0 |
| s07772.pdf / C7 | 7192 × 4502 | 200.01 / 200.09 | 7192 × 4500 | 4 | 5 |
| s07773.pdf / C8 | 7200 × 4510 | 200.00 / 200.07 | 7200 × 4509 | 5 | 6 |

Each page has one full-page image occurrence, xref 6, encoded with `/FlateDecode`.
All four image resources are **one-bit stencil images** (`ImageMask: true`), not
ordinary RGB photographs. Native export produces PNGs at their original pixel
dimensions. This retains PyMuPDF's extracted image bytes and format; it does not
claim that the PDF originally contained a PNG file.

Inspection of C8's raw export showed white linework on a black background. The
PDF's stencil painting semantics yield the intended black-on-white drawing when
rendered as a page. Therefore use the **page composite and its crops** as the
visible evidence for transcription and future OCR, while preserving raw exports
as source evidence. The implementation also exports soft/explicit mask image
resources when present and delegates their displayed composition to MuPDF.

The 200-DPI composites contain about four times as many pixels as the earlier
100-DPI previews. No render was capped by the new 40-million-pixel limit. Tiny
height differences from native dimensions reflect nominal 200-DPI rendering of
page-point dimensions and integer pixel rounding; native files retain every
source row. The source was already approximately 200 DPI, so rendering at 300–600
DPI alone would interpolate existing detail rather than recover missing scan
information. Native export is not constrained by the rendering pixel limit.

Raster manifests retain source and native-artifact hashes, native dimensions,
export format, PDF filters/mask/decode fields, image occurrence positions and
transforms, effective resolution, original PDF rotation/cropbox, crop selection,
and page-to-pixel matrices. The coordinate convention is unrotated visible-page
points; neither evidence boxes nor image dimensions are GIS coordinates.

## Visual readability review of C7/C8

The title, road, cemetery and storage crops were inspected directly at the new
resolution. The plan-view crop is a broader context region for those labels,
excluding the longitudinal profile. These are visual observations, not OCR scores.

| Region | C7 evidence | C8 evidence | Readability and OCR preparation |
| --- | --- | --- | --- |
| Title | City of Southport Transmission Facilities; Hwy 211 Force Main; C7; STA. 66+50 to STA. 78+75 | Same project; C8; STA. 78+75 to STA. 90+25 | Bold title and station labels are clearly legible. Borders and adjoining seals may distract an OCR engine; use focused crops. |
| Road label | NC 211 - Supply Road | NC 211 - Supply Road | Clearly legible, with nearby linework and an inverted adjacent utility label; avoid treating nearby text as part of the road name. |
| Cemetery | Cape Fear Memorial Park Cemetery | Cape Fear Memorial Park Cemetery | Readable but thin lettering, split over four lines. Future OCR needs multiline phrase reconstruction and a reviewer check. |
| Storage | No dedicated crop selected | Sentry Self Storage | Readable two-line label; a distinctive candidate landmark requiring later reference-data verification. |
| Location-map inset | None identified in the inspected sheet layout | None identified in the inspected sheet layout | No false location-map crop generated. The general workflow supports explicit location-map regions when present. |
| Survey-coordinate annotations | None identified for selection | None identified for selection | No survey-coordinate clues or crops fabricated. Stationing and profile elevations are not ground survey coordinates. The workflow supports explicit coordinate regions on other sheets. |

The crops are suitable inputs for a local OCR feasibility experiment once an engine
is approved and available. They do **not** establish OCR accuracy or full-sheet
readability. Thin/faint text, one-bit scan artifacts, rotated utility notes, dense
linework, profile grids and subtle scan skew remain potential difficulties.
No denoising, deskewing, polarity rewriting of raw evidence or automatic enhancement
was applied. Layout-specific crop boxes should be reviewed before reuse elsewhere.

## Manual geographic clue records

Preliminary registries:

- [C7 clues](../outputs/phase1b-final/c7/clues.json): road, cemetery, project, sheet,
  and station range (5 entries).
- [C8 clues](../outputs/phase1b-final/c8/clues.json): the same types plus Sentry Self
  Storage (6 entries).

All 11 clues are attributed to `Codex visual transcription` and remain
**unverified**. Their bounding boxes enclose inspected evidence regions, not exact
text glyphs. They contain source document hashes and one-based page numbers,
manual extraction method, original/current text, notes, status and correction
history. Project/sheet/station entries share the title-region box and retain
their distinct semantic types. No parcel IDs, lot IDs, subdivision names or survey
coordinates were inferred from this sample; the schema supports their later entry.

Use `clues-review` to correct, verify or reject each record with a named reviewer
and reason. Corrections reset prior verification unless explicitly reviewed again.
Here, verified means the transcription and evidence location have been checked;
it does not imply that the landmark's ground location, GIS feature, or any asset
association has been approved. See [the manual workflow](PHASE1B_WORKFLOW.md).

## Results, limitations and next milestone

Phase 1B provides native source evidence, composition-correct high-resolution
page images, nine selected C7/C8 crops, and an auditable starting set of geographic
clues. Rendering, mask handling and provenance were exercised on the real scans;
the four real documents do not test tiled/multiple-image layouts, so synthetic
tests cover repeated images, tiles, soft masks, stencil polarity and inline images.

All **38 automated tests pass**, including the original 23 tests. Added coverage
also verifies original JPEG bytes and dimensions, DPI/mappings and rotated pages,
bounded rendering, invalid regions, failure recovery, CLI entry and clue corrections.
The human-readable per-run report deliberately marks readability unreviewed; this
document supplies the separate visual assessment for C7/C8. No OCR or GIS accuracy
evaluation has run. Prepared outputs are ignored by Git and should be retained in
approved local storage with the source PDFs; the configs and instructions permit
regeneration.

The next milestone is **analyst verification of C7/C8 clues and a read-only
geographic candidate-area pilot using approved offline reference data**. First
review the 11 entries, confirm landmark identity and collect known locations as
evaluation evidence. Keep ambiguous place names unresolved; the consultant address
is not the drawing location. Preserve station continuity as project context,
not a direct spatial transform.

An optional local OCR adapter can then be evaluated against those corrected
transcriptions when an OCR engine is available through the approved process.
Measure clue-phrase recovery and correction effort before training any model.
Expand to varied documents before estimating collection-wide performance. ArcPy
licensing and data access remain separate; no GEOBASE access or automatic GIS
asset matching is part of this implementation.

## Artifact references

| Sheet | Raster manifest | Generated assessment | Full-page composite |
| --- | --- | --- | --- |
| C5 | [manifest](../outputs/phase1b-final/c5/raster-manifest.json) | [report](../outputs/phase1b-final/c5/RASTER_ASSESSMENT.md) | [image](../outputs/phase1b-final/c5/page-0001/full-page.png) |
| C6 | [manifest](../outputs/phase1b-final/c6/raster-manifest.json) | [report](../outputs/phase1b-final/c6/RASTER_ASSESSMENT.md) | [image](../outputs/phase1b-final/c6/page-0001/full-page.png) |
| C7 | [manifest](../outputs/phase1b-final/c7/raster-manifest.json) | [report](../outputs/phase1b-final/c7/RASTER_ASSESSMENT.md) | [image](../outputs/phase1b-final/c7/page-0001/full-page.png) |
| C8 | [manifest](../outputs/phase1b-final/c8/raster-manifest.json) | [report](../outputs/phase1b-final/c8/RASTER_ASSESSMENT.md) | [image](../outputs/phase1b-final/c8/page-0001/full-page.png) |
