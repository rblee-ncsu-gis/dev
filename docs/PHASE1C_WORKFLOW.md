# Geographic clue review and OCR evaluation workflow

Phase 2A strengthens the scoring contract: AI review and `verified` status alone
are ineligible. Actual independent human review with explicit attestation is now
required. Follow [the current acceptance and OCR workflow](PHASE2A_WORKFLOW.md)
before generating accuracy results; the Phase 1C AI exports remain historical
provisional records.

Phase 1C extends the existing manual clue commands. It adds no OCR engine or
dependencies and does not import ArcPy. Use the existing clone from the repository
root, as in [Phase 1B](PHASE1B_WORKFLOW.md):

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
$env:PYTHONPATH = (Join-Path $PWD 'src')
```

## Review bundles

The actual pilot's latest [review manifest](../outputs/phase1c/final-review/REVIEW.md)
contains all 11 clues, prioritizing C8 then C7. It links each clue to the smallest
containing composition-correct crop, falling back to the full-page image when
needed. Raw stencil exports are not selected as review images.

To generate a fresh bundle, choose a new output directory:

```powershell
& $pythonExe -m asbuilt_matcher clues-manifest outputs/phase1c/registries/c8.json outputs/phase1c/registries/c7.json --output outputs/review-next
```

The bundle contains `REVIEW.md`, `review.csv`, `review.json` and one
`decisions-NN.json` template per registry. Reports include current/original text,
type, PDF/hash, page, source bounding box, image reference/hash, status, reviewer
and history. JSON also includes image dimensions, DPI and transforms. Missing
evidence is reported explicitly. Review Markdown escapes multiline text and table
separators; CSV uses UTF-8 with BOM and JSON-encoded nested fields.

## Decisions and corrections

Continue using `clues-review` for one entry:

```powershell
& $pythonExe -m asbuilt_matcher clues-review outputs/phase1c/registries/c8.json CLUE-ID --status verified --author 'Reviewer name' --reviewer-type human --reason 'Checked label and box against linked crop'
& $pythonExe -m asbuilt_matcher clues-review outputs/phase1c/registries/c8.json CLUE-ID --text 'Corrected transcription' --author 'Reviewer name' --reviewer-type human --reason 'Corrected against source'
& $pythonExe -m asbuilt_matcher clues-review outputs/phase1c/registries/c8.json CLUE-ID --status rejected --author 'Reviewer name' --reviewer-type human --reason 'Not a location clue'
& $pythonExe -m asbuilt_matcher clues-review outputs/phase1c/registries/c8.json CLUE-ID --status unreadable --author 'Reviewer name' --reviewer-type human --reason 'Cannot reliably decipher label'
```

For several decisions, edit the generated template with a text editor. Leave
`action: null` to skip an entry. Example decision objects:

```json
[
  {"clue_id": "ID-1", "action": "verified", "author": "Reviewer name", "reviewer_type": "human", "reason": "Transcription checked"},
  {"clue_id": "ID-2", "action": "corrected", "text": "SUPPLY ROAD", "author": "Reviewer name", "reviewer_type": "human", "reason": "Corrected spelling"},
  {"clue_id": "ID-3", "action": "rejected", "author": "Reviewer name", "reviewer_type": "human", "reason": "Consultant office address"},
  {"clue_id": "ID-4", "action": "unreadable", "author": "Reviewer name", "reviewer_type": "human", "reason": "Illegible digits"}
]
```

Keep these objects inside the template's existing `decisions` array, preserving
its top-level registry path and hash. `text_for_reference` is informational; use
`text` to correct a value. Optional `bbox` and `coordinates` corrections use the
same validation as `clues-review`. An explicit `verified` action may include edits
when the reviewer has checked those corrected values.

```powershell
& $pythonExe -m asbuilt_matcher clues-apply outputs/phase1c/registries/c8.json outputs/review-next/decisions-01.json
```

Every applied decision requires author and reason. All decisions for that registry
are validated before any are saved. A repeated clue ID, invalid decision or stale
registry hash aborts the operation; regenerate a bundle after registry edits.
This protects one registry at a time, not a multi-file transaction. The workflow
remains sequential and local, without authenticated identities or concurrent edit
locking; the hash check is optimistic protection, not a database lock.

`corrected` is an action, not a verification status: it resets the entry to
`unverified`. `unreadable` means evidence cannot be reliably transcribed; `rejected`
means the candidate is unsuitable or wrong. Neither deletes original evidence.
Original text and before/after histories are retained, including bounding-box and
coordinate changes. Reviewer types are `human`, `ai`, or `unspecified`; existing
records without a type remain compatible. Verification scope is transcription,
not geographic placement. Use real attribution; these fields are not signatures.

## Verified exports and OCR targets

```powershell
& $pythonExe -m asbuilt_matcher clues-export outputs/phase1c/registries/c8.json outputs/phase1c/registries/c7.json --output outputs/verified-next --render-targets
```

This writes `verified-clues.json` and `verified-clues.csv`. Only entries with
status `verified` and complete reviewer metadata are exported. Source PDF hashes,
manifest/run bindings, clue boxes and image availability are checked first;
invalid verified evidence aborts export instead of silently removing rows. Both
formats retain originals, corrections, reviewer type and image/source hashes.
An empty verified set produces an empty JSON list and header-only CSV.

`--render-targets` uses the existing raster renderer to generate one composition-
correct 200-DPI PNG per verified bounding box, with dimensions, affine mapping
and SHA-256 in the export. Target filenames are sequence numbers linked to stable
clue IDs. Omit the flag to export records without rendering. The 40-million-pixel
limit applies to target renders; actual DPI/capping is recorded. A render failure
aborts export and can leave partial artifacts: use a new directory after fixing
the error. Original PDFs and Phase 1B evidence are unchanged.

The actual [verified export](../outputs/phase1c/verified-final/verified-clues.json)
contains 11 entries with `reviewer_type: ai`. It is a **provisional transcription
dataset**, awaiting independent analyst acceptance before use as trusted ground
truth. The individual targets and their text can be re-reviewed without guessing
which title-block substring was intended. Keep related C7/C8 data together for
evaluation; these are not independent projects.

## Score supplied predictions without running OCR

The scorer accepts the verified export and a JSON prediction file:

```json
{
  "run": {"engine": "engine-name", "engine_version": "version", "preprocessing": "none", "mode": "ocr_plus_entities"},
  "predictions": [
    {"clue_id": "ID-1", "text": "NC 211 - SUPPLY ROAD", "entities": [{"kind": "street_name", "text": "NC 211 - SUPPLY ROAD"}]}
  ]
}
```

```powershell
& $pythonExe -m asbuilt_matcher ocr-score outputs/phase1c/verified-final/verified-clues.json outputs/predictions.json --output outputs/ocr-scores-next
```

This command scores supplied data only. It writes `scores.json` and `targets.csv`
and records input hashes. The provided
[`predictions.template.json`](../outputs/phase1c/predictions.template.json) has
`engine: NOT_RUN` and blank placeholders: do not present scores from that template
as an OCR experiment. Fill it with actual outputs and run metadata first.

Transcription scoring uses case-sensitive exact equality with CRLF converted to
LF only, plus character edit distance / reference character count. Whitespace,
line breaks and punctuation otherwise matter. Entity matching separately uses
type plus uppercased, whitespace-collapsed text, mapping en/em dashes to ASCII
hyphen. No address lookup, alias expansion, language model or geocoding is used.
The current road-label ground truth uses an ASCII hyphen annotation convention.

Missing predictions fail exact match and reduce entity recall. Duplicate or
unknown prediction IDs are rejected; duplicate entity detections count as false
positives. Wrong entity types count as both a missed expected entity and a false
positive. `sheet_number` and `station_range` are context targets without geographic
entity truth; geographic detections on them count as false positives. Metrics
report typed entity micro/per-type precision, recall and F1; undefined denominators
are null. Current truth has seven geographic entity instances and four context
targets, rather than eleven independent place names.

Metrics cover only the annotated targets. Do not use this partial dataset to
claim full-page NER precision or actual GIS localization accuracy. For an oracle
text baseline, supply gold text to the recognizer and label the run accordingly;
for end-to-end evaluation, supply real OCR text and recognizer outputs without
showing the expected clue kinds/values to the pipeline. See the experimental
design and open questions in [the assessment](PHASE1C_ASSESSMENT.md).
