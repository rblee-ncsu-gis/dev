# Controlled local OCR baseline

For current engine discovery, visual review and the first measured run, start with
[the first-baseline instructions](PHASE2A_FIRST_BASELINE.md).

This phase uses Python's standard library and the installed PyMuPDF. No ArcPy,
`pytesseract`, Pillow, OpenCV or OCR installation is required to prepare variants.
Tesseract is an optional external executable, invoked locally without a shell.
See [the current assessment](PHASE2A_ASSESSMENT.md) for actual availability and
measurement limits.

## Probe the engine without changing the environment

Run from the repository root in the existing clone:

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
& $pythonExe scripts/run_asbuilt.py ocr-check
```

An explicitly approved installation can be probed without changing PATH:

```powershell
& $pythonExe scripts/run_asbuilt.py ocr-check --tesseract 'C:\ApprovedTools\Tesseract-OCR\tesseract.exe' --tessdata-dir 'C:\ApprovedTools\Tesseract-OCR\tessdata'
```

The probe checks executable/version, language listing, `eng`, and engine/model
hashes when discoverable. It records the searched locations and existing
`TESSDATA_PREFIX`, but never sets environment variables or downloads files.
Listed English data is a prerequisite; the actual OCR subprocess can still fail
on incompatible/corrupt models. The probe does not test recognition quality.

Use `--output NEW-FILE.json` to save the diagnostic. The bootstrap changes only
its own Python import path. Absolute executable overrides bypass Windows PATH.

## Proposed installation procedure — requires separate authorization

No installation has been performed. If approved later:

1. Have IT select and approve a Windows 64-bit Tesseract build compatible with
   the workstation and the selected English LSTM data. The official
   [installation guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)
   points to Windows builds; review the selected vendor's installer/runtime
   prerequisites and provenance before installing.
2. Install the standalone executable and its bundled runtime dependencies in an
   approved tools directory. Do not install into or alter the ArcGIS Python clone.
   No Python OCR wrapper is needed. Record the approved version and installer
   checksum according to the county's software process.
3. Ensure the installation contains compatible `eng.traineddata` and the `txt`
   and `tsv` output configurations. Use one documented English model for the
   baseline and retain its SHA-256. The official
   [Tesseract documentation](https://tesseract-ocr.github.io/tessdoc/)
   describes model families; changing a model is a separate experiment.
4. Pass executable and tessdata paths explicitly to `ocr-check` and `ocr-run`.
   Check `--version` and `--list-langs`, then validate with a synthetic image
   before processing the local county targets. No source upload is required.
5. Orientation/script detection data (`osd`) is optional future work. This adapter
   supports explicit right-angle correction and does not automatically call OSD.

## Prepare or run the baseline

```powershell
& $pythonExe scripts/run_asbuilt.py ocr-run outputs/phase1c/verified-final/verified-clues.json --output outputs/ocr-next --config config/ocr-baseline.json
```

The historical filename `verified-clues.json` describes a Phase 1C review-status
export; it does **not** make its AI-reviewed contents accepted ground truth. All
11 current references are excluded from scoring. The image inputs may still be
used for exploratory OCR or preprocessing. Reference text/type is not fed into
the adapter or candidate rules.

`ocr-run` also accepts a Phase 1B `raster-manifest.json`: it processes the full-page
composite and each selected crop, never raw native masks. Supply another new
output directory for each evidence/configuration run. Existing outputs are
rejected. `--prepare-only` produces derivatives without recognition, even if an
engine exists. When the engine is absent, normal runs still prepare all variants
and record every OCR job as `blocked_engine`.

After installation approval and engine setup, add `--tesseract` and
`--tessdata-dir` as needed. No changes to scripts or Python packages are required.
For full pages, evaluate a separately recorded `psm: 11` sparse-text configuration;
the supplied target baseline uses `psm: 6` consistently, without selecting modes
from the expected clue kinds. Supported explicit PSMs are 3–13; OSD modes are
excluded from this initial adapter.

## Configurable preprocessing

The [baseline configuration](../config/ocr-baseline.json) compares:

| ID | Operations |
| --- | --- |
| baseline | RGB/source colorspace derivative, no enhancement |
| gray | Grayscale conversion |
| contrast | Grayscale, contrast factor 1.5 around midpoint 127.5 |
| threshold | Grayscale, fixed threshold 160 |
| scale2 | Grayscale, 2× interpolation |
| scale2_threshold | Grayscale, 2× interpolation, then threshold 160 |

Each variant may specify `rotation: 0`, `90`, `180` or `270`, clockwise. Use this
only when image inspection indicates correction is appropriate. The horizontal
C7/C8 targets default to 0; do not choose an angle by matching reference text.
Arbitrary-angle deskew, automatic orientation detection, adaptive thresholds,
denoising and morphology are not implemented. Compare these separately later if
the evidence warrants them.

Operation order is grayscale, contrast, scaling, threshold, rotation. Thresholds
and contrast are deterministic byte lookup tables; scaling/rotation use PyMuPDF.
Original images remain unchanged. Source hashes/dimensions are checked, and new
PNG derivatives include actual dimensions and estimated output DPI. Inputs or
outputs above the configurable pixel budget fail explicitly instead of silently
downsampling. Native-image decode can still consume memory; use focused crops
for initial experiments. Upsampling approximately 200-DPI scans creates no new
source information.

## Results and page-coordinate mapping

Each run writes:

- `ocr-run.json`: input hashes, engine/model probe, configuration, all image jobs,
  source document identifiers, processing statuses, comparisons and evaluation gate.
- `comparison.csv` and `COMPARISON.md`: per-variant preparation/recognition failures
  and independently accepted-reference metrics when available. Unmeasured metrics
  are null/blank, never zero; best variants remain null without qualifying scores.
- `ocr.log`: every job's status and error.
- One variant/image directory with `input.png`, `result.json`, and, when OCR runs,
  raw `ocr.txt`, raw `ocr.tsv` and `engine.log`. Failed/empty recognitions remain
  explicit records and subsequent jobs continue.
- Per-variant `predictions.json` and, when eligible, `scores.json`.
- `REVIEW.html` and `visual-assets.json`: read-only source/processed image,
  word-box and detected-text inspection, with hash-checked image snapshots.

Every attempt directly records its engine version/location, OCR configuration,
preprocessing parameters, source-image hash/reference and timestamps, even when
recognition fails. Word results are empty when recognition did not run. Comparative
reports include character accuracy (1 − CER), word accuracy (1 − WER) and false
positives; see [the metric definitions](PHASE2A_FIRST_BASELINE.md#metric-definitions).

TSV word records retain text, supported confidence (unavailable `-1` becomes null),
processed pixel box, mapped original-page polygon/box and line identifiers. The
adapter composes the existing `page_to_pixel` matrix with preprocessing scale and
rotation and records its inverse. All four corners are mapped; a rotated word
therefore has both a polygon and an enclosing axis-aligned page box. These are
unrotated visible-page points, not GIS coordinates. Crop offsets and integer
rounding use actual raster dimensions and origins.

Raw text is retained verbatim in `ocr.txt` and `raw_text`. Prediction text converts
CRLF to LF and removes exactly one engine terminal newline; it does not correct
spelling/case/punctuation or use the reference values. Confidence means are
diagnostic engine values, not calibrated correctness probabilities.

Exit codes from the Python CLI: 0 for complete/explicit prepare-only runs, 2 when
the engine is unavailable, 1 for failures/partial runs. An exploratory OCR run may
complete while its evaluation remains blocked; always inspect both statuses.
Subprocesses have configurable timeouts. Full logs and raw output are local files.

## Independent analyst acceptance and scoring

Reuse the existing review bundle and commands. A person who actually checks the
source can explicitly attest independent acceptance:

```powershell
& $pythonExe scripts/run_asbuilt.py clues-review outputs/phase1c/registries/c8.json CLUE-ID --status verified --author 'Actual analyst name' --reviewer-type human --independent --reason 'Independently checked transcription and evidence box against composition-correct source'
& $pythonExe scripts/run_asbuilt.py clues-export outputs/phase1c/registries/c8.json outputs/phase1c/registries/c7.json --analyst-only --render-targets --output outputs/analyst-accepted-next
```

Do not run the acceptance command on someone else's behalf. No actual clue was
accepted or reclassified during this phase. Bulk review templates now also have
`independent: false`; only the actual human reviewer should change that to true
along with their reviewer type, name and reason. AI/unspecified review and
same-author attestation cannot qualify. Corrections still invalidate acceptance
until reviewed again. The files record attestations, not authenticated identities.

`ocr-score` now rejects any reference that lacks explicit independent human
acceptance; `verification_status: verified` alone is insufficient. Old reviews
without the new attestation are ineligible. The baseline runner scores only the
accepted subset and records excluded counts. Accepted target IDs **and image
hashes** must match inputs; re-export/rerender after box corrections before
evaluation. Do not copy a human flag onto the historical AI export.

Strict transcription accuracy and character-error rate remain separate from typed
entity precision/recall/F1. Missing predictions and failed jobs count as misses
when eligible references exist. Scoring preserves false-positive and missed typed
entities in per-target audits. Ties and best variants are reported separately for
exact transcription and entity F1, limited to the accepted pilot subset. They
are not a general recommendation for the entire document collection.

Exploratory candidate rules recognize limited road/project/landmark label patterns
from OCR text without reference clues. Every candidate is unreviewed. Separate
engineering-annotation warnings flag stationing, dimensions and material text.
Neither rule matches nor warnings constitute confirmed geographic entities or
false positives. Confirm errors against independently reviewed evidence and retain
bad recognitions rather than deleting them. Full-page entity precision still
requires exhaustive annotations and negative examples.

The inherited [Phase 1C metrics](PHASE1C_WORKFLOW.md) remain otherwise unchanged.
Use gold text versus real OCR text as separate entity-parser experiments after
analyst acceptance. No automatic geographic placement or asset matching runs here.
