# Phase 2A: first measured OCR baseline

Assessment date: October 16, 2026. Sources: s07773.pdf (C8), s07772.pdf (C7).

## Management summary

The user marked all 11 review rows **verified / analyst** and confirmed comparing
the OCR with the drawings. Those explicit human decisions are now recorded, with
the original AI reviews retained in history. This assessment scores the existing
66 OCR attempts against those independently accepted references; OCR was not rerun.

**Baseline and grayscale tied best:** character error rate (CER) **5.69%**, word
error rate (WER) **18.60%**, and 6/11 complete target transcriptions exact. Both
recovered all **7 typed geographic-label instances**, with **0 false positives**
on these annotated targets. Sheet IDs and station labels remain unreliable.

Keep baseline preprocessing as the pilot default; grayscale is equivalent here.
Expand evaluation and test targeted border/segmentation fixes. A limited read-only
geographic candidate-area prototype is reasonable using accepted road/landmark
clues and analyst review. Eleven related targets do not establish production
accuracy, exact geographic registration or asset-matching readiness.

## Acceptance and preserved evidence

| Source | Human-accepted references | Geographic labels | Sheet/station context |
| --- | ---: | ---: | ---: |
| C8: s07773.pdf | 6 | 4 | 2 |
| C7: s07772.pdf | 5 | 3 | 2 |
| Total | 11 | 7 | 4 |

Acceptance is based on the **user-amended rows and chat attestation**, not automatic
promotion of AI decisions. Review attribution is `User analyst`, with human reviewer
type and explicit independence. No personal name was supplied or inferred.
Timestamps record import time; actual manual-review time was not separately given.
These are local attestations, not authenticated signatures.

The amended Markdown's generated heading still stated zero accepted references;
its eleven explicit row decisions and the user's confirmation resolve that stale
summary. The file was archived verbatim and left unchanged. Each current registry
entry retains its original text and two AI events, followed by human acceptance.
No text, type or box changed during import. All eleven freshly exported target
hashes match the images used in the original recognition run.

- [Amended review snapshot](../outputs/phase2a/human-acceptance-001/user-amended-REVIEW.md)
- [Attestation and evidence hash](../outputs/phase2a/human-acceptance-001/attestation.json)
- [C8 decisions](../outputs/phase2a/human-acceptance-001/c8-decisions.json), [C7 decisions](../outputs/phase2a/human-acceptance-001/c7-decisions.json)
- [Current acceptance manifest](../outputs/phase2a/human-acceptance-001/review-after/REVIEW.md)
- [Accepted JSON](../outputs/phase2a/human-acceptance-001/accepted/verified-clues.json), [accepted CSV](../outputs/phase2a/human-acceptance-001/accepted/verified-clues.csv)
- [Previous pending-results report](../outputs/phase2a/human-acceptance-001/previous-PHASE2A_MEASURED_RESULTS.md)

Both pre-import registries are also archived in that acceptance folder. Original
OCR predictions, images, logs and the user-amended source report remain unchanged.

## Method and denominators

Recognition source: run `ee90777f-9c3f-4e6b-a22f-4195b16f6ee7`, October 16, 2026,
19:15:52–19:16:03 UTC (15:15:52–15:16:03 EDT), Tesseract v5.4.0.20240606,
English, OEM 1, PSM 6. The existing scorer was reused after reference acceptance
and input-hash alignment. All 66 nonempty attempts were included.

Each variant uses **211 reference characters and 43 reference words in 11 targets**.
CER/WER are edit distance divided by the corresponding reference count. Case and
punctuation matter; word tokenization uses whitespace. CRLF is normalized to LF;
the adapter excludes one engine terminal newline while preserving raw text.
Character/word accuracy is 1 minus the respective error rate. Whole-target exact
match is a separate metric.

Entity matching uses type plus the existing case/whitespace/dash-normalized full
label. Seven geographic-label instances include repeats across adjacent sheets;
they are not seven unique places. Four sheet/station targets contain no geographic
entity truth. All entity results apply to the annotated targets only, not full-page
precision, landmark identity/location, geographic placement or asset associations.

## Overall transcription comparison

| Variant | Character errors / 211 | CER | Word errors / 43 | WER | Exact targets / 11 |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 12 | **5.69%** | 8 | **18.60%** | 6 |
| gray | 12 | **5.69%** | 8 | **18.60%** | 6 |
| contrast | 13 | 6.16% | 9 | 20.93% | 5 |
| threshold | 13 | 6.16% | 9 | 20.93% | 5 |
| scale2 | 15 | 7.11% | 11 | 25.58% | 5 |
| scale2_threshold | 15 | 7.11% | 11 | 25.58% | 6 |

Baseline/gray have **94.31% character accuracy**, **81.40% word accuracy** and
**54.55% exact-target accuracy**. Twofold scaling did not improve aggregate
transcription on this approximately 200-DPI sample. `scale2_threshold` ties the
best exact-target count but makes more errors in its remaining targets. This does
not establish that scaling or thresholding is generally harmful elsewhere.

## Geographic-entity comparison

| Variant | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 7 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| gray | 7 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| contrast | 7 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| threshold | 7 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| scale2 | 6 | 0 | 1 | 100.00% | 85.71% | 92.31% |
| scale2_threshold | 7 | 0 | 0 | 100.00% | 100.00% | 100.00% |

`scale2` inserts a period after C8's `MEMORIAL`; the strict landmark rule then
rejects the combined phrase, causing one missed entity. This combines an OCR
punctuation error with parser sensitivity. Street dash differences are normalized
for entity matching but still count as transcription errors. Preserve raw text
before testing more tolerant parsing.

Zero observed false positives does not establish a low full-drawing false-positive
rate. Consultant addresses, legends, scales, dimensions and dense profiles were not
comprehensively annotated in this small, selected target set.

## Comparison by document

Cells are **CER / WER**. C7 has 5 targets, 96 characters and 20 words; C8 has
6 targets, 115 characters and 23 words.

| Variant | C7: s07772.pdf | C8: s07773.pdf |
| --- | ---: | ---: |
| baseline | 5.21% / 20.00% | 6.09% / 17.39% |
| gray | 5.21% / 20.00% | 6.09% / 17.39% |
| contrast | 6.25% / 25.00% | 6.09% / 17.39% |
| threshold | 6.25% / 25.00% | 6.09% / 17.39% |
| scale2 | 5.21% / 20.00% | 8.70% / 30.43% |
| scale2_threshold | 5.21% / 20.00% | 8.70% / 30.43% |

Both documents have 100% entity precision/recall in every condition except `scale2`
on C8: precision 3/3 (100%), recall 3/4 (75%). Neither document has an observed
entity false positive. Their different clue mixes and small related samples do
not establish a general quality difference between documents.

## Comparison by clue type

Cells are **CER / WER**. Paired variants have identical type-level results.

| Type (targets) | baseline / gray | contrast / threshold | scale2 | scale2_threshold |
| --- | ---: | ---: | ---: | ---: |
| street_name (2) | 2.50% / 10.00% | 5.00% / 20.00% | 2.50% / 10.00% | 2.50% / 10.00% |
| landmark (3) | 0% / 0% | 0% / 0% | 1.20% / 7.69% | 0% / 0% |
| project_name (2) | 0% / 0% | 0% / 0% | 0% / 0% | 0% / 0% |
| sheet_number (2) | 150% / 100% | 150% / 100% | 200% / 200% | 200% / 200% |
| station_range (2) | 10.42% / 50.00% | 10.42% / 50.00% | 10.42% / 50.00% | 12.50% / 60.00% |

Insertion errors can produce CER/WER above 100%, especially for very short sheet
IDs; values are not clamped. Landmark precision/recall are 100% except `scale2`,
whose recall is 2/3. Street/project entity precision/recall are 100% throughout.
Sheet/station-only entity rates are undefined, not zero, because those context
groups have no geographic entity reference labels.

## Recovered information and manual fallback

For preferred baseline/gray preprocessing:

| Accepted clue | Result | Handling |
| --- | --- | --- |
| NC 211 - SUPPLY ROAD, C7 | Exact text and typed street entity recovered. | Reviewed candidate-area clue. |
| NC 211 - SUPPLY ROAD, C8 | Typed entity recovered; raw em dash differs from accepted ASCII hyphen. | Retain raw and normalized forms separately. |
| Cape Fear Memorial Park Cemetery, C7/C8 | Both multiline labels exact; both landmarks recovered. | Verify candidate identity/location against geographic reference data. |
| Sentry Self Storage, C8 | Exact text and typed landmark recovered. | Same geographic-reference verification requirement. |
| HWY 211 FORCE MAIN, C7/C8 | Both project labels exact. | Project context, not a coordinate or unique asset identifier. |
| Sheet IDs C7/C8 | Neither exact under any tested variant. | Retain analyst transcription; improve border isolation/segmentation. |
| Both station ranges | Neither complete label exact under any variant. | Retain analyst transcription, particularly numeric values and plus signs. |

## Recurring failures and coverage limits

- **Sheet borders:** `ce/|`, `of`, `cs / |` and `1/` show diagonal-box/character
  interference. Scaling increases insertion errors rather than fixing these IDs.
- **Engineering annotations:** `STA.` becomes `STA:`; C7's `66+50` becomes
  `66450` throughout. `scale2_threshold` changes C8's last station to `90+#25`.
  Numeric/symbol transcription is unreliable. These labels did not become false
  geographic entities here; full-page engineering confounders remain untested.
- **Street punctuation:** C8 consistently uses an OCR em dash; contrast/threshold
  also change C7's separator. Strict transcription and normalized name recovery
  answer different questions.
- **Thin/faded lettering:** the readable thin landmark labels generally work,
  but scaling adds punctuation to the C8 cemetery. There is no accepted genuinely
  faded/unreadable target set, so performance on degraded scans remains unknown.
- **Rotated text:** these are horizontal targets and all six variants use
  rotation 0. Vertical notes and arbitrary scan skew were not systematically tested.

## Recommendation and next milestone

**Begin a limited, read-only geographic candidate-area prototype while expanding
OCR evaluation.** Use accepted road/landmark labels, approved offline reference
layers and analyst review. Keep ambiguous candidates unresolved; do not infer exact
coordinates from road names/stationing, modify SDE assets or implement automatic
asset associations from this result. No prototype was started during this assessment.

Grow the pilot toward 10–20 varied PDFs from unrelated projects, including rotated
notes, faded scans, complex layouts and reviewed negative regions. Keep related
sheets in the same evaluation group. Test focused sheet-border crops, suitable
single-line/word segmentation and conservative landmark punctuation handling as
separate ablations. Retain baseline/gray controls; blanket scaling/thresholding is
not supported as the default by these results. Continue manual sheet/station entry.

Eleven correlated targets cannot set production thresholds. The localization pilot
should measure candidate-area correctness, abstentions and analyst burden separately
from OCR/typed-name recovery.

## Measured artifacts and validation

- [Measured run and provenance](../outputs/phase2a/measured-001/measured-run.json)
- [Comparison CSV](../outputs/phase2a/measured-001/comparison.csv), [comparison Markdown](../outputs/phase2a/measured-001/COMPARISON.md)
- [By document](../outputs/phase2a/measured-001/by-document.csv), [by clue type](../outputs/phase2a/measured-001/by-clue-type.csv)
- [Document × type](../outputs/phase2a/measured-001/by-document-and-type.csv), [full grouped scores](../outputs/phase2a/measured-001/grouped-scores.json)
- [Measured visual report with accepted-reference error audits](../outputs/phase2a/measured-001/REVIEW.html)

Each variant folder retains scores, per-target error CSV and original prediction
JSON. Existing tested scoring/report functions were reused; application code and
dependencies were not changed. The prior 90-test implementation remains in use.
Review history was extended with explicit human decisions, not overwritten. No
Python environment, source drawing, SDE asset, original OCR output or amended
review file was modified.
