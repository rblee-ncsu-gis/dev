# Utility as-built matcher feasibility pilot

Phase 3B adds a nine-view pilot with offline boundary/orientation review, separate
scale evidence and guarded calibration, selective OCR comparisons, and a versioned
unregistered ArcGIS handoff. No real views/scales have been accepted. Start with the
[view and scale workflow](docs/PHASE3B_VIEW_SCALE_CALIBRATION.md).

Phase 3A adds coverage-aware classification and native text/vector/annotation
inspection, preserving legacy extraction and prior geographic evidence. The selected
26 PDFs contain 75 pages: 69 predominantly raster and six predominantly vector.
Start with the [study findings and commands](docs/PHASE3A_PDF_CLASSIFICATION.md),
[processing architecture](docs/PHASE3A_PROCESSING_ARCHITECTURE.md), and
[sample input configuration](config/pdf-study.json). Classifications and scale
candidates await independent analyst review; no geographic registration is performed.

Phase 2B.3 adds offline independent control collection, audited review decisions,
image-only cross-sheet ties, and gated rigid/similarity/affine feasibility checks.
C7/C8 have no approved controls or checkpoints and remain unregistered. Start with
the [control collection guide](docs/PHASE2B3_CONTROL_REGISTRATION.md).

Phase 2B.2 adds supplemental landmark references and a separate corridor-narrowing
review. C7/C8 share a 371 m landmark-anchored road section; full sheet extents and
geographic accuracy remain unverified. See the
[landmark assessment and commands](docs/PHASE2B2_LANDMARK_NARROWING.md).

Phase 2B.1 adds opt-in, source-scoped road aliases and corridor recovery. C7/C8 now
recover a road-corridor candidate each; precise localization remains unverified.
See [alias resolution and current results](docs/PHASE2B1_ALIAS_RESOLUTION.md).

Phase 2B adds read-only geographic candidate-area localization from accepted
clues and seven configurable WGS84 GeoJSON reference layers, with CSV, JSON and
offline map review. County exports are now inspected, and approved road/subdivision/
address layers have been processed for C7/C8. The original strict run returned
insufficient evidence; geographic accuracy remains pending independent area review.
See the [actual county validation](docs/PHASE2B_REAL_WORLD_VALIDATION.md),
[metadata/mapping workflow](docs/PHASE2B_WORKFLOW.md) and
[Phase 2B assessment](docs/PHASE2B_ASSESSMENT.md). Existing clue approvals are preserved.

For the first measured OCR baseline, follow
[these instructions](docs/PHASE2A_FIRST_BASELINE.md). The local runner supports
side-by-side visual OCR review, character/word accuracy and explicit executable
paths without environment-variable changes. Recognition can run before analyst
acceptance; accuracy scoring cannot.

Phase 2A adds optional local Tesseract OCR, reproducible preprocessing and word-box
mapping. Accuracy scoring now requires independent human acceptance; AI-reviewed
clues are ineligible. See [the OCR workflow](docs/PHASE2A_WORKFLOW.md) and
[the current Phase 2A assessment](docs/PHASE2A_ASSESSMENT.md).

Phase 1C adds review manifests, unreadable decisions, verified clue exports and
separate OCR/entity scoring without invoking OCR. See
[the review workflow](docs/PHASE1C_WORKFLOW.md) and
[the Phase 1C assessment](docs/PHASE1C_ASSESSMENT.md).

Phase 1B now supports native raster preparation and reviewed manual clue records.
See [the workflow](docs/PHASE1B_WORKFLOW.md) and
[C7/C8 raster assessment](docs/PHASE1B_ASSESSMENT.md) for commands and actual results.

Phase 1 extracts local PDF evidence for analyst inspection. The project scope is
[ASBUILT_CODEX_CONTEXT.md](docs/ASBUILT_CODEX_CONTEXT.md). No GIS connection,
asset matching, model inference, or publication is implemented. Optional local OCR
and geographic localization now use the later-phase workflows above.

Use a cloned ArcGIS Pro Python environment in VS Code. Select **Python: Select
Interpreter**, then choose the clone's `python.exe`. Do not experiment in the
base ArcGIS environment. PowerShell commands below run from this repository:

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
& $pythonExe scripts/check_environment.py > environment-report.json
$env:PYTHONPATH = (Join-Path $PWD 'src')
& $pythonExe -m asbuilt_matcher check-environment
& $pythonExe -m asbuilt_matcher extract 'C:\approved-input\drawing.pdf' --output 'outputs\pilot-001'
& $pythonExe -m pytest -q
```

The environment report includes interpreter, import errors, package versions,
CUDA build/device availability, ArcPy product and extension availability, and
the local Tesseract executable path. Exit code 1 means the PDF dependency is not
ready; optional GIS/AI import failures remain visible but do not block extraction.
Extension availability is queried without checking out either extension.

No dependencies are installed automatically. PyMuPDF is required for extraction;
pytest is required for tests. After explicit approval for dependencies and package
license suitability, install into the clone using the organization's approved
package workflow. `pyproject.toml` declares the package and console command;
running from `src` as above avoids installing this project or fetching build tools.
The declared PyMuPDF range is a starting compatibility constraint, not a verified
lockfile. Do not install the unrelated package named `fitz`.

Each extraction requires a new output directory. It records SHA-256 identity,
original path/name, run ID, UTC timestamps, PDF metadata, page count, settings and
backend version in `manifest.json`. Each successful page gets UTF-8 text, a PNG
preview, and JSON with text/image/vector statistics, boxes, rotation and preview
scale. Preview default is 100 DPI capped at 16 million pixels; use `--dpi` and
`--max-pixels` to adjust. Sources are opened read-only and are not copied.

Coordinates are MuPDF page points with a top-left origin, not EPSG:2264.
Extraction coordinates are unrotated; previews reflect page rotation. The saved
rotation matrix, preview scale and pixel origin support later alignment.
See the [PyMuPDF page API](https://pymupdf.readthedocs.io/en/latest/page.html).
Vector operation counts describe PDF drawing instructions, not detected assets.
Content hints are coarse image/path presence indicators; text can be outlined,
and scanned sheets can contain an OCR text layer. `ocr_recommended` is only a hint.
Layout detection, actual vector geometry export, revisions and verified-link
reference sets remain future Phase 1 work.

Failures are logged in `extraction.log` and retained in the manifest. Page errors
allow subsequent pages to continue and yield `partial`; document failures yield
`failed`. Both return exit code 1. Preflight failures (missing dependency/input,
invalid settings or existing output directory) print an error before extraction.
Review partial artifacts before reuse. Password-protected PDFs are rejected.
Synthetic tests generate PDFs locally; backend integration tests skip explicitly
when PyMuPDF is absent. No production data or external AI services are accessed.

To assess a collection of approved local engineering drawings:

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')
& $pythonExe -m asbuilt_matcher batch 'C:\approved-input\drawings' --output 'outputs\assessment-001' --recursive
```

Omit `--recursive` to inspect only the immediate directory. PDF extensions are
case-insensitive. Input files are processed sequentially in relative-path order;
each receives a separate numbered directory, so duplicate filenames and identical
documents remain separate inventory entries. Output must be a new directory.
`--dpi` and `--max-pixels` control previews as for single-document extraction.
No ArcPy imports, OCR, AI calls or additional packages are needed for the batch.

The batch output contains:

- `inventory.json`: structured documents, pages, run settings, counts and errors.
- `documents.csv`: filename, relative path, SHA-256, page count, observed totals,
  classification, extraction status and per-document artifact directory.
- `pages.csv`: page number/index, displayed dimensions in points and inches,
  orientation, rotation, character/path/image counts, classification and text path.
- `documents/document-NNNNN/`: individual page text files, previews, page JSON,
  document manifest and extraction error log.
- `batch.log`: processing progress and document failures.

Text file paths in summary reports are relative to the batch output directory.
JSON uses UTF-8 and CSV uses UTF-8 with a BOM for Windows Excel. CSV page indices
start at zero; page numbers start at one. Character counts include whitespace and
newlines returned by PyMuPDF. Dimensions describe the displayed page after rotation,
not the engineering plan-view extent or drawing scale. Image counts count displayed
image instances, including repeated placements, rather than unique image resources.

Preliminary page classification uses these presence rules:

| Evidence | Classification |
| --- | --- |
| Paths or nonblank embedded text, no images | `vector` |
| Images, no paths or nonblank text | `scanned` |
| Images plus paths or nonblank embedded text | `mixed` |
| No images, paths or nonblank text | `empty` |
| Evidence could not be extracted | `unknown` |

Document classification combines page evidence: vector and scanned pages together,
or any mixed page, yield `mixed`. Blank and unknown pages do not add evidence;
documents with no usable evidence are `unknown`. These are triage labels: logos
can trigger mixed content, scans with OCR text layers are mixed, and vector paths
may be decorative rather than utility assets. Inspect the previews and recovered
text before deciding whether OCR or symbol detection is necessary.

Corrupt, encrypted or unreadable PDFs remain in the inventory with errors while
other files continue. Unknown page counts are blank in CSV and null in JSON.
Totals reflect only recovered evidence; check `status`, `measured_pages` and errors
before interpreting low or zero counts. Incomplete document classification describes
only the pages measured. Batch status is `partial` and exit code is 1 if any document
is incomplete; complete runs return 0. Empty collections produce header-only CSVs,
status `empty` and exit code 0. Reports contain extracted source information and
should be kept in an approved local location.
