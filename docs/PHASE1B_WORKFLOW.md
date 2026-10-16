# Native rasters and manual geographic clues

This workflow uses the installed PyMuPDF and Python standard library. It does not
import ArcPy, invoke OCR, query GIS, install packages or alter the clone. Run from
the repository root in PowerShell with the existing clone interpreter:

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
$env:PYTHONPATH = (Join-Path $PWD 'src')
& $pythonExe -m asbuilt_matcher prepare-rasters src/pdf/s07772.pdf --output outputs/c7-new --regions config/c7-regions.json
& $pythonExe -m asbuilt_matcher prepare-rasters src/pdf/s07773.pdf --output outputs/c8-new --regions config/c8-regions.json
```

Choose a new output directory for every run. Omitting `--regions` exports native
images and the full-page composite without inventing crop locations. Defaults
are 200 DPI and a 40-million-pixel limit **per rendered image**. Use `--dpi` and
`--max-pixels` to adjust them. Requested and actual resolution and any cap are
recorded. Native exports are not resized or constrained by this render cap;
large source images may still require substantial memory. Increasing render DPI
above source detail does not create new information.

## Artifacts and fidelity

Each run writes `raster-manifest.json`, `raster.log`, `RASTER_ASSESSMENT.md` and
one directory per page. Each page directory contains:

- `image-xref-N.ext`: bytes returned by `Document.extract_image`, without a second
  conversion, resizing or recompression by this application. JPEG bytes are
  retained when returned as JPEG. Flate-compressed PDF samples, stencils or other
  encodings can be exported by PyMuPDF as PNG; this is not a claim that the PDF
  originally embedded a PNG file. The manifest records both export format and
  PDF compression/filter, mask/decode information and native dimensions.
- `full-page.png`: visible-page RGB composite including masks, tiles, overlaid
  text, clipping and annotations, rendered by MuPDF. This is always produced
  when rendering succeeds, since a standalone image may not reproduce the drawing.
- `crop-ID.png`: explicit selected region renders from that same composition.

Resources and displayed image occurrences are inventoried separately. A repeated
xref can appear in multiple positions; masks are exported as separate resources
when extractable. Inline images with no discoverable xref are inventoried but use
the page composite for visible evidence. Individual resource errors remain in the
manifest and log while page rendering is attempted. A render failure retains
native exports and subsequent pages continue. `partial` or `failed` runs return
exit code 1; successful runs return 0. Preflight failures report an error before
creating artifacts. Some warning-only MuPDF diagnostics can still appear on stderr.

Image DPI estimates use pixel counts divided by physical placement-axis lengths,
including image rotation/shear in the occurrence transform. They describe nominal
sampling along each image axis, not measured scan quality. Source and extracted
artifact SHA-256 hashes provide provenance. Source hashes are checked again at
run completion and PDFs are never saved or modified.

## Regions and coordinates

Region files are JSON arrays of objects such as:

```json
[
  {"id": "title", "page_number": 1, "kind": "title_block",
   "bbox": [1500, 1470, 2490, 1615], "notes": "Analyst-selected project title"}
]
```

Supported kinds are `title_block`, `location_map`, `plan_view_labels` and
`coordinate_annotations`. Provide actual bounding boxes for regions that exist;
all four kinds can be rendered independently. IDs must be safe filename components
and unique within the page. Out-of-page or zero-area rectangles are rejected.
The C7/C8 configs target their known layouts, not arbitrary engineering drawings.
No location-map inset or survey-coordinate annotations were identified for these
sheets; those categories are recorded as unselected, rather than assigned false
crops. Station ranges are supported as clues, separately from survey coordinates.

All bounding boxes use **unrotated visible-page MuPDF points**, top-left origin,
72 points/inch. The PDF rotation is normalized only in memory during preparation;
its original rotation, rotation matrix and cropbox are retained. These artifacts
can therefore be oriented differently from an ordinary rotated PDF preview.
Cropbox offsets are retained as metadata; boxes are relative to the visible page,
not raw PDF bottom-left coordinates or a geographic CRS.

Each render saves a six-number affine `page_to_pixel` matrix and `pixel_origin`.
For scale `s` and raster origin `(px, py)`, crop-local pixel coordinates are
`(s*x-px, s*y-py)`. Invert these equations to enter a clue box measured in pixels.
Use the recorded matrix rather than assuming the crop begins at pixel zero after
multiplying by its requested DPI, because clipping rounds pixel boundaries.

## Manual clue entry and review

Initialize a registry from a raster manifest, then add evidence using the crop's
page coordinates. These commands create separate editable JSON records; they do
not change source drawings:

```powershell
& $pythonExe -m asbuilt_matcher clues-init outputs/c8-new/raster-manifest.json --registry outputs/c8-new/clues.json
& $pythonExe -m asbuilt_matcher clues-add outputs/c8-new/clues.json --kind street_name --text 'NC 211 - Supply Road' --page 1 --bbox 420 450 620 510 --author 'Analyst name'
```

`clues-add` prints the new clue ID. Use it to correct or review an entry:

```powershell
& $pythonExe -m asbuilt_matcher clues-review outputs/c8-new/clues.json CLUE-ID --text 'NC 211 - Supply Road' --author 'Analyst name' --reason 'Corrected against crop'
& $pythonExe -m asbuilt_matcher clues-review outputs/c8-new/clues.json CLUE-ID --status verified --author 'Reviewer name' --reason 'Transcription and evidence box checked against drawing'
```

`--bbox` can correct the evidence rectangle. `--coordinates` accepts a JSON object
with `x`, `y`, `crs`, `units` for survey-coordinate entries and corrections; CRS
and units must be explicit strings or null when unknown. Do not assume EPSG:2264
from a coordinate-looking label. Northing/easting stationing, elevations and
profile axes must not be entered as ground coordinates without verification.

The [clue schema](geographic_clue.schema.json) supports street/subdivision/project
names, parcels, lots, survey coordinates, landmarks, sheet numbers and station
ranges. Runtime validation uses the standard library; no JSON Schema validator
is installed or invoked. Every clue carries the document hash, page number, box,
extraction method, original/current text, author, verification status and history.
Current CLI entry is manual; embedded-text and OCR methods are schema provisions
for later work. A broad evidence-region box is permitted; it need not trace glyphs.

New clues are `unverified`. Corrections preserve original text and before/after
history and reset verification unless the same action explicitly reviews them.
Statuses are `unverified`, `verified`, `rejected` and `unreadable`; review requires an author and
reason. Verification confirms transcription evidence, not geographic placement
or asset-link approval. Work on one registry sequentially; this local file workflow
does not provide concurrent editing or authenticated reviewer identities.

For multi-clue review bundles, structured reviewer attribution, verified exports
and OCR scoring inputs, use the [Phase 1C workflow](PHASE1C_WORKFLOW.md).

The prepared pilot artifacts are in `outputs/phase1b-final/c7` and `c8`, including
11 preliminary clues attributed to `Codex visual transcription`. They remain
unverified for an analyst to review. Region configs are retained in `config`.
Generated output is ignored by Git, so retain the artifact folders alongside the
source PDFs in an approved local location when moving or archiving the pilot.

## Assessment and checks

The generated assessment describes recorded resolution, masks, crop availability
and errors. It intentionally leaves readability unreviewed: pixel counts alone
cannot establish OCR accuracy. [The pilot assessment](PHASE1B_ASSESSMENT.md) adds
visual observations from inspected C7/C8 crops. No automatic OCR-readiness score
or GIS confidence is claimed.

Run `& $pythonExe -m pytest -q` for the full synthetic suite. Tests cover exact
JPEG byte preservation, dimensions/DPI, repeated/tiled/masked/inline images,
composite fidelity, rotation/crop mappings, resource/render failures, clue
correction history, validation and CLI workflows.

API references used: [PyMuPDF image extraction recipes](https://pymupdf.readthedocs.io/en/latest/recipes-images.html),
[page image inventory and rendering](https://pymupdf.readthedocs.io/en/latest/page.html),
and [document extraction](https://pymupdf.readthedocs.io/en/latest/document.html).
