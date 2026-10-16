# Phase 1C: geographic clue verification and OCR readiness

Assessment date: October 16, 2026. Priority: s07773.pdf (C8), then s07772.pdf (C7).

Phase 1C has produced a reviewed dataset of **11 transcriptions**, a linked review
manifest, verified JSON/CSV exports, and 11 individual OCR target images. All
verification is explicitly attributed to **Codex image review (AI)**. This is a
provisional transcription dataset; independent analyst acceptance and geographic
confirmation have not occurred. No OCR software was installed or run, and no real
OCR accuracy numbers are available yet.

## Evidence and deliverables

- [Review manifest: all 11 clues](../outputs/phase1c/final-review/REVIEW.md)
- [Machine-readable review inventory](../outputs/phase1c/final-review/review.json)
- [Review CSV](../outputs/phase1c/final-review/review.csv)
- [Verified JSON](../outputs/phase1c/verified-final/verified-clues.json)
- [Verified CSV](../outputs/phase1c/verified-final/verified-clues.csv)
- Reviewed registry copies: [C8](../outputs/phase1c/registries/c8.json),
  [C7](../outputs/phase1c/registries/c7.json)
- [Original review snapshot](../outputs/phase1c/initial-review/REVIEW.md),
  with the preliminary values and unverified statuses retained.
- [Review and scoring instructions](PHASE1C_WORKFLOW.md) and
  [clue schema](geographic_clue.schema.json).

Phase 1B registries, source PDFs, page composites and nine focused crops remain
unchanged. Review operated on separate registry copies. The two source hashes
are `91027547c8455ce5bc7ecda712d84900ec1e8e5815536a91859a80388595fd8b` (C8) and
`6bc0890c9a20468ad08e808e21cc3e3865de3b2be147b5dfbc4fe4aacb373538` (C7).
Exports bind entries to those hashes and their raster manifests; selected image
and target-image hashes allow later experiment snapshots to be checked.

Generated artifacts are ignored by Git. Preserve `outputs/phase1c` and the linked
Phase 1B evidence locally when archiving the study; the report links depend on
those folders. Review templates contain absolute registry paths and must be
regenerated after relocating or changing a registry.

## Review findings and decisions

The two page composites, all nine existing focused crops, and all 11 proposed
target rectangles were inspected visually. Target margins were refined where
needed: the initial C7 station rectangle clipped the tops of letters, the C7
project target included fragments of the station line, and the C8 sheet/road
rectangles benefited from adjusted margins. These issues were corrected before
applying the review decisions and exporting final targets.

| Source / page | Clue type | Reviewed value (line breaks shown as /) | Status |
| --- | --- | --- | --- |
| s07773.pdf / 1 | street_name | NC 211 - SUPPLY ROAD | verified, AI |
| s07773.pdf / 1 | landmark | CAPE FEAR / MEMORIAL / PARK / CEMETERY | verified, AI |
| s07773.pdf / 1 | project_name | HWY 211 FORCE MAIN | verified, AI |
| s07773.pdf / 1 | sheet_number | C8 | verified, AI |
| s07773.pdf / 1 | station_range | STA. 78+75 TO STA. 90+25 | verified, AI |
| s07773.pdf / 1 | landmark | SENTRY SELF / STORAGE | verified, AI |
| s07772.pdf / 1 | street_name | NC 211 - SUPPLY ROAD | verified, AI |
| s07772.pdf / 1 | landmark | CAPE FEAR / MEMORIAL / PARK / CEMETERY | verified, AI |
| s07772.pdf / 1 | project_name | HWY 211 FORCE MAIN | verified, AI |
| s07772.pdf / 1 | sheet_number | C7 | verified, AI |
| s07772.pdf / 1 | station_range | STA. 66+50 TO STA. 78+75 | verified, AI |

All 11 rectangles were tightened. Seven transcriptions changed: two road labels
and three landmarks now retain uppercase lettering and visible landmark line
breaks; two project records now target the literal project title instead of
combining the municipality/facility heading with the project name and an editorial
semicolon. The road's horizontal separator is annotated as an ASCII hyphen, a
declared transcription convention rather than an inferred digital character code.
The original combined project text, including City of Southport context, remains
in `original_text` and history. No source evidence was silently replaced.

Current counts: 11 verified by AI, 0 rejected, 0 unreadable, 0 unverified in the
Phase 1C copies. **Independent analyst approvals: 0.** The unchanged Phase 1B
registries still contain the original 11 unverified entries. Review metadata
distinguishes `ai`, `human` and `unspecified` reviewers and fixes scope to
transcription. A verified landmark spelling is not proof of its ground location.

## Schema and workflow changes

Existing `review_clue` logic remains responsible for validation, before/after
history and correction persistence. It now supports `unreadable` and structured
reviewer type. `corrected` is a review action that resets verification; it is not
a second approval status. Explicitly verified corrections retain both the edit
and review. Original text is immutable through the commands, and previous boxes,
coordinates, status and review metadata are retained in history.

New review bundles supply Markdown/CSV/JSON and blank-action decision templates.
Bulk decisions reuse that same review operation and save once per registry only
after all selected decisions validate. Templates are tied to a registry hash;
stale templates and duplicate decisions fail without partial registry edits.
Review identity fields are attributed local records, not authenticated signatures.

Verified exports exclude rejected, unreadable and pending entries, carry originals
and correction history in both formats, and require available, matching source
and raster evidence. CSV nested values are JSON-encoded. Optional target rendering
reuses the existing raster module; it does not add a separate image pipeline.
The local file workflow is sequential and has no database locking or multi-registry
transaction. The [schema](geographic_clue.schema.json) remains compatible with
earlier clues; old reviewer types are reported as unspecified.

## OCR-readiness assessment

| Input | Resolution / orientation | Contrast and readability | Readiness |
| --- | --- | --- | --- |
| C8 full page | 7200 × 4509 at 200 DPI; PDF rotation 0 | Correct black-on-white composition. Small labels, rotated notes, linework, title borders and a dense profile grid compete with text. | Useful for layout/context experiments; not the first exact transcription benchmark. |
| C7 full page | 7192 × 4500 at 200 DPI; PDF rotation 0 | Similar layout, some faint underlying annotations and small scan skew apparent from borders. | Same qualification; no deskew accuracy measured. |
| Two title crops | 2751 × 404 (C8), 2751 × 390 (C7), 200 DPI | Bold, readable project/sheet/station labels, but multiple boxes and mixed reading order. | Split into individual target rectangles for strict scoring. |
| Two plan crops | Each 6362 × 1820, 200 DPI | Horizontal road labels are readable; linework, vertical notes and faint text complicate full-region recognition. | Good context for entity extraction; focused target crops simplify initial OCR. |
| Two road crops | 557 × 167 (C8), 751 × 167 (C7), 200 DPI | Main label readable; neighboring inverted utility text and underlining can contaminate OCR. | Tightened target rectangles remove most nuisance content. |
| Two cemetery crops | 334 × 195 (C8), 362 × 237 (C7), 200 DPI | Thin, multiline uppercase lettering. Readable by visual review but more fragile than titles. | Test line grouping and dropped/merged strokes explicitly. |
| C8 storage crop | 334 × 126 at 200 DPI | Readable thin two-line text. | Include as a distinct landmark target. |

Native scans are approximately 200 DPI, one-bit stencils. Raw native exports have
the wrong visible polarity for direct use as OCR inputs; page composites correctly
apply PDF stencil semantics. High foreground/background contrast does not restore
thin strokes lost in a binary scan. Some glyphs and borders show scan artifacts.
Upsampling alone cannot recover additional source detail. No thresholding,
denoising, deskewing or polarity rewriting was applied in Phase 1C.

The 11 target images are composition-correct 200-DPI renders of the refined
rectangles. The exact image file, dimensions, page-to-pixel transform and hash are
included in each verified export row. A target may still contain a border or
diagonal sheet divider; evaluation should retain the baseline and compare any
future cleaned version as a separate, logged experiment. All text needed for the
11 current annotations is visually readable; this is not evidence that all
information on the sheets is readable or that OCR will be accurate.

## OCR evaluation strategy

1. **Freeze accepted ground truth.** Obtain independent analyst review of the
   AI-reviewed labels and boxes, then regenerate the verified export. Preserve
   export, registry, source and image hashes. Keep rejected/unreadable records in
   the review inventory and report their counts; do not include them as empty
   strings in accuracy denominators. Keep the original values for comparison.
2. **Baseline on individual target images.** Use the unchanged 200-DPI targets,
   without feeding expected text or clue type to OCR. Record engine/version,
   language, orientation settings, preprocessing, run ID and image hash. Evaluate
   focused targets first, then broader plan/title crops and full pages. Those
   are separate tasks with different annotation completeness.
3. **Measure transcription independently.** The implemented `ocr-score` reports
   exact matches / all verified targets and character edit distance / all
   reference characters. Exact comparison is case-sensitive, preserving spaces,
   punctuation and line breaks, apart from CRLF-to-LF conversion. Missing outputs
   fail exact match. Current evaluation has 11 target instances; report numerator
   and denominator, and break errors down by bold/thin text and clue kind.
   The explicit dash convention and multiline labels can affect strict accuracy;
   retain those errors even when entity recognition succeeds.
4. **Measure typed geographic entities separately.** The current truth has seven
   geographic entity instances (two streets, three landmarks, two projects) and
   four sheet/station context targets. Entity matching uses type plus case- and
   whitespace-normalized full label text with dash normalization. Report micro
   and per-type precision, recall and F1. Missing/wrong/duplicate predictions
   count as false negatives/positives; undefined denominators are null. Alias
   expansion and partial road-name matches are not currently accepted implicitly.
5. **Separate recognition from OCR errors.** Run the same entity recognizer once
   on gold transcriptions (oracle-text baseline) and once on OCR output
   (end-to-end). Label these runs distinctly; differences expose transcription
   effects. Do not use ground-truth clue types as recognition inputs. Recognition
   of a name and successful geographic placement are separate outcomes.
6. **Expand annotations before broader claims.** Current targets are selected
   readable positives from two related sheets, with repeated names. They are not
   an exhaustive full-page entity inventory, a held-out dataset, or seven unique
   places. Full-page precision needs complete geographic/non-geographic annotation,
   including consultant-address and profile/station confounders. Collect unrelated
   projects, unreadable examples and genuine negatives; keep project groups
   together in development/held-out splits.

The standard-library scorer accepts supplied prediction JSON and writes score JSON
and per-target CSV with input hashes. It invokes no engine. No actual OCR prediction
file exists yet; the provided template is explicitly marked `NOT_RUN`. Synthetic
test results are software validation only, not measured OCR performance.

## Validation and unresolved questions

All **55 automated tests pass**, including the prior 38 tests. New tests exercise
unreadable decisions, batch atomicity and stale templates, correction preservation,
AI attribution, crop references, CSV/JSON export, source/evidence validation,
target-image hashing, and separate exact-text/entity scoring. Real artifact checks
confirmed all 11 target hashes/dimensions, linked image hashes and original text
and bounding-box history. No OCR, ArcPy dependency, GIS access or environment
modification was introduced.

Open decisions before treating this as accepted ground truth:

- Who provides independent analyst acceptance, and is a second reviewer required
  for thin/ambiguous labels? AI attribution must remain visible after review.
- Should future project records separately represent municipality/facility
  context instead of relying on the retained original combined label?
- Which alias policy should recognize `NC 211`, `Supply Road` and the combined
  label as the same geographic entity? Current scoring deliberately uses full
  typed-label equivalence and may mark a valid partial name as a miss.
- Which OCR engine/language/configuration will be approved, and which unrelated
  PDFs will form the held-out set? No installation is authorized by this report.
- What minimum exact/entity recovery and analyst correction burden is acceptable
  for the pilot? The 11 targets cannot justify production thresholds.
- Where will immutable experiment snapshots and reviewer identity records live
  beyond these local files? Composite hashes captured here establish a snapshot;
  Phase 1B did not originally record composite hashes at creation time.

## Recommended next milestone

**Phase 1D: analyst acceptance and a controlled local OCR baseline.** First use
the review bundle to accept or correct C8/C7 evidence and freeze the ground truth.
Once an approved OCR engine is available, implement an optional adapter that emits
raw text, boxes, engine metadata and recognition scores without altering source
evidence. Evaluate it with the existing scorer, then add simple typed clue parsing
and compare oracle-text versus end-to-end entity results. Retain abstention and
unreadable outcomes. Geographic candidate search and automatic GIS asset matching
remain subsequent work.
