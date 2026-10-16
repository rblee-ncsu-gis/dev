# Phase 2A: controlled local OCR baseline

Latest update: the user's amended review and confirmation provided independent
human acceptance for all 11 references. The existing 66 OCR outputs have now been
scored; see [the measured results](PHASE2A_MEASURED_RESULTS.md). The readiness and
implementation snapshots below describe the earlier state before that acceptance.

## Current readiness update — October 16, 2026

The latest diagnostic found a pre-existing **Tesseract v5.4.0.20240606** installation
at `C:\Users\ricky.lee\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`, with
`eng` and `osd`. This supersedes the earlier absence finding preserved below.
No installation or environment setting was changed during this work.

Using that explicit absolute executable and tessdata directory, an **exploratory,
unscored run completed all 66 recognitions**: 11 targets × six variants. Each
variant returned nonempty text for all 11 targets; that is not a correctness claim.
Actual text and word-level TSV files confirm local English OCR/TSV operation.
All 11 clues still await independent analyst acceptance, so no accuracy, entity
precision/recall or false-positive rate was measured and no winner was selected.
No approval flags or histories changed.

- [Diagnostic](../outputs/phase2a/readiness-diagnostic.json)
- [Visual source-crop / OCR report](../outputs/phase2a/recognition-readiness/REVIEW.html)
- [Attempt inventory](../outputs/phase2a/recognition-readiness/ocr-run.json)
- [Comparison CSV](../outputs/phase2a/recognition-readiness/comparison.csv)
- [Measured-baseline instructions](PHASE2A_FIRST_BASELINE.md)

Baseline/gray/contrast/threshold each produced 43 word records across the targets;
the two scaled variants each produced 45. Those are output counts, not correct-word
counts. Outputs include `ce/|` and `of` on sheet-label crops, and
`STA: 66450 TO STA: 78+75` on a station crop. These warrant analyst inspection for
border/symbol/punctuation confusion; they are not scored errors or confirmed
geographic false positives without accepted references. Candidates remain unreviewed.

The diagnostic can save version/location/language/model provenance to JSON.
Absolute executable overrides bypass PATH lookup, and a bootstrap command avoids
PYTHONPATH changes. Every attempt now directly records engine version, OCR
configuration, source hash, preprocessing, timestamps and word results. The local
HTML report shows source crops, processed images, word boxes, detected text,
confidence and provenance, with variant/status filters. It can be rebuilt without OCR.

Comparison reports now include character accuracy (1 − CER), word accuracy
(1 − WER), typed entity precision/recall/F1 and false positives alongside exact
target accuracy. These remain blank/null without accepted labels. The independent
human-review gate remains enforced. All **90 tests pass**, including the prior 81
and new absolute-path, diagnostics, six-variant unscored recognition, edit-metric
and safe visual-report tests.

The engine prerequisite is satisfied. Actual independent analyst acceptance and
a frozen analyst-only reference/image export are still required for the first
measured baseline. Eleven related targets cannot establish production accuracy.

## Earlier implementation assessment (historical snapshot)

Assessment date: October 16, 2026. Initial evidence: C8 (s07773.pdf) followed by
C7 (s07772.pdf), using the 11 Phase 1C target images.

The local adapter, preprocessing experiment, coordinate mapping and independent
acceptance gate are implemented. **Actual OCR recognition and accuracy comparison
have not run:** Tesseract was not found in the checked locations, and **none of the
11 AI-reviewed references has independent analyst acceptance**. No engine was
installed and no clue was automatically approved. There is no measured best
preprocessing method for the county scans yet.

## Plan and implementation status

| Work item | Result |
| --- | --- |
| Reuse review/evidence infrastructure | Existing registries, reviewer history, source hashes, raster matrices and scorer reused. No duplicate approval system. |
| Check local engine and English data | Read-only probe implemented and executed; executable not found, so operational English-data availability is undetermined. |
| Local configurable OCR adapter | Implemented subprocess-based Tesseract text/TSV adapter, timeout/error capture and engine/model provenance. |
| Preprocessing variants | Six variants prepared for each of 11 targets: 66 derivative images. Original evidence unchanged. |
| OCR boxes to source page | Scale/rotation composed with existing crop/page matrix; word polygons and enclosing boxes mapped back to page points. |
| Independent scoring | Enforced in standalone scorer and baseline runner. All 11 current references excluded. |
| Comparative recognition results | Comparison artifacts generated; recognition/accuracy fields remain unmeasured, with no winner selected. |
| Error and confounder audit | Job failures, empty OCR, diagnostics, low/unavailable word confidence, candidate rules and engineering warnings supported; no real recognitions/false positives observed without an engine. |

## Availability and prerequisites

`ocr-check` searches PATH, Program Files, Program Files (x86), and the user's
LocalAppData `Programs/Tesseract-OCR` and `Tesseract-OCR` locations. None yielded
an executable. The session has no `TESSDATA_PREFIX`. An initial targeted check of
the user's WinGet package directory also found no Tesseract package directory.
This is not an exhaustive disk search: a custom installation may be supplied with
`--tesseract` and `--tessdata-dir`.

With no executable, no version or language list could be obtained. English data
is therefore **unknown**, not proven absent everywhere. The adapter requires a
working executable and listed `eng` data; it captures the English model hash when
the data directory is discoverable. A subsequent recognition smoke test remains
necessary even when a language is listed.

The proposed installation procedure is in [the workflow](PHASE2A_WORKFLOW.md).
It requires separate authorization and an approved standalone Windows build plus
compatible English data/runtime files, without changing the ArcGIS clone. The
official [Tesseract installation guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)
describes Windows distribution options; the official
[command-line documentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)
documents local text/TSV output. No Python OCR wrapper is needed for this adapter.

## Actual experiment artifacts

Final preparation run: [baseline-final](../outputs/phase2a/baseline-final).

- [Complete run inventory](../outputs/phase2a/baseline-final/ocr-run.json)
- [Comparative CSV](../outputs/phase2a/baseline-final/comparison.csv)
- [Comparative report](../outputs/phase2a/baseline-final/COMPARISON.md)
- [Processing log](../outputs/phase2a/baseline-final/ocr.log)
- [Fixed experiment configuration](../config/ocr-baseline.json)

Inputs are composition-correct PNG targets; raw inverted stencil exports were not
used. Six C8 and five C7 targets each received six variants. The run is explicitly
`blocked_engine`, with evaluation `blocked_no_analyst_ground_truth`. No OCR
subprocess was invoked. All image preparation jobs succeeded:

| Variant | Prepared targets | Blocked recognitions | Failed preparation | Exact transcription | Entity precision/recall/F1 |
| --- | ---: | ---: | ---: | --- | --- |
| baseline | 11 | 11 | 0 | not measured | not measured |
| gray | 11 | 11 | 0 | not measured | not measured |
| contrast 1.5 | 11 | 11 | 0 | not measured | not measured |
| threshold 160 | 11 | 11 | 0 | not measured | not measured |
| scale 2× | 11 | 11 | 0 | not measured | not measured |
| scale 2×, threshold 160 | 11 | 11 | 0 | not measured | not measured |

Blank/null metrics do not mean zero accuracy. Preparation success does not predict
recognition accuracy. The input C7/C8 scans have approximately 200-DPI detail;
2× interpolation produces nominal 400-DPI derivatives without new source detail.
Contrast can strengthen or clip faint strokes, and thresholding can remove thin
lettering. Those tradeoffs must be measured, not inferred as improvements.
The official [quality guidance](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
discusses resolution, binarization, skew and borders as OCR considerations.

Explicit clockwise right-angle rotation is supported and tested but not applied
by default to these horizontal target labels. There is no arbitrary-angle deskew
or automatic OSD; full-sheet vertical notes require their own region/orientation
experiments. Full pages and the original nine focused crops can be submitted via
the Phase 1B raster manifests; the completed real preparation run above covers
the 11 small targets only. Whole-page 2× scaling would exceed the default
40-million-pixel budget for these scans and should use region/tile experiments.

## Ground-truth eligibility and audit integrity

Phase 1C's historical `verification_status: verified` records are AI-reviewed
transcriptions. They do **not** meet the Phase 2A ground-truth contract. All
original statuses, values and histories were left unchanged.

Eligibility now requires a verified transcription, an explicitly human reviewer,
an independent-review attestation, reviewer/reason/timestamp metadata, and a
reviewer distinct from the extraction author. The existing review operation records
these fields and preserves before/after history; corrections invalidate acceptance
unless explicitly reviewed again. Local reviewer identity is not authenticated.
Existing human records without explicit independence are also ineligible.

The scorer rejects AI/unspecified/non-independent reference datasets rather than
silently accepting their labels. The baseline runner may prepare/OCR their images,
but filters all such references out of evaluation and records excluded counts.
An actual attempt to score the current AI snapshot was rejected during validation.
`clues-export --analyst-only` can produce an accepted snapshot after a real analyst
reviews it; it produces no accepted references from the current registries.

When accepted references become available, OCR target IDs and image hashes must
match the accepted export before scoring. Source input images are hash-checked
before processing and again after each job, derivatives have their own hashes,
and all transformations/configuration remain separate artifacts. The adapter does
not consume the expected transcription or kind when recognizing text or proposing
candidates. No ground-truth flags were promoted during this phase.

## Capture, mapping and errors

Once an engine is available, each job preserves raw text/TSV and subprocess
diagnostics. Word results include confidence when supported, processed pixel
coordinates, line identifiers and original-page polygons/enclosing boxes. The
mapping inverts preprocessing scale/rotation composed with Phase 1B/1C page/crop
transforms. Actual rounded image dimensions and crop origins are used. Coordinates
remain unrotated visible-page points, never state-plane or GIS coordinates.

Original raw engine text is retained; scoring text excludes one engine-added
terminal newline and normalizes CRLF to LF without correcting words. Low confidence
is retained, unavailable confidence becomes null, and mean confidence is only a
diagnostic. Empty output, timeouts, nonzero engine exit, malformed TSV, pixel-budget
violations and changed inputs remain explicit unsuccessful cases. Jobs continue
after individual failures, while the run reports partial/failure status.

Exploratory rule-based candidates cover limited street, project and landmark
patterns. They are unreviewed, with no GIS lookup or automatic approval. Separate
warnings flag stationing, pipe dimensions/materials and similar engineering text.
Warnings are not confirmed false positives. With accepted reference labels, the
existing scorer now preserves typed false-positive and missed-entity lists in its
per-target audit. Synthetic tests exercise an engineering-like `PVC ROAD` false
positive; that is a software test case, not an observed error on the real drawings.
No actual county OCR false-positive rate can be reported yet.

## Comparative measurement protocol after the prerequisites are met

1. Obtain independent analyst acceptance using the existing manifest, including
   transcription and box corrections. Freeze an analyst-only export and its image
   hashes. Keep unreadable/rejected counts in the audit, outside accuracy denominators.
2. Run the same six variants on that accepted image set using one fixed Tesseract
   build, English model, OEM/PSM configuration and timeout. Do not select settings
   by matching AI-reviewed reference labels. Log engine/model hashes and every
   preprocessing configuration. Run additional segmentation modes separately.
3. Compare strict exact transcription accuracy and character-error rate. Preserve
   case/spacing/line-break/punctuation errors; the declared ASCII dash convention
   can affect exact matches. Failed/missing outputs count as misses on accepted
   references, alongside their execution-error counts.
4. Separately compare typed geographic-entity micro/per-type precision, recall and
   F1 using the inherited explicit entity normalization rules. Run the parser on
   analyst gold text versus real OCR text as separate oracle/end-to-end conditions.
   Do not give the parser the expected entity type or value. Inspect confidence,
   false positives, dimensions/symbols and abstentions without equating confidence
   to correctness.
5. The runner reports best/tied variants separately for exact transcription and
   entity F1 when comparable accepted-reference scores exist. A method may win one
   metric and lose the other. Retain all failure cases and per-kind results before
   choosing a preprocessing default.

The 11 selected targets from adjacent C7/C8 sheets are a small, correlated pilot,
not a production validation set. Seven geographic entity instances include repeated
labels; four targets are sheet/station context. Full-page precision requires more
complete annotations and genuine negative regions, including legends, consultant
addresses, scales and profile grids. Expand to unrelated projects and keep project
groups together for development/held-out splits. Do not set production accuracy
thresholds from this pilot.

## Validation and next steps

All **81 automated tests pass**, including the previous 55 with their evaluation
fixtures updated to explicit synthetic human acceptance. Coverage includes engine
and language probes, variant preparation and budgets, crop/rotation transforms,
pixel-level orientation agreement, TSV geometry/confidence, empty/failed OCR paths,
mocked subprocess outputs, strict AI-reference rejection, accepted-target scoring,
false-positive audit and existing review history behavior. Mocked Tesseract success
is not a live engine or OCR-quality validation. The real target run prepared all
66 derivatives without failures; metrics were withheld for both unmet prerequisites.

Next milestone: **authorized Tesseract setup and independent analyst acceptance,
then the first measured local baseline**. These can proceed independently; exploratory
recognition may run after engine setup, but scores must wait for accepted labels.
No installation should occur without authorization. Before geographic localization,
establish usable road/landmark recovery, error/abstention behavior and approved
offline reference layers. Geographic placement accuracy and GIS asset matching
remain outside this implementation.
