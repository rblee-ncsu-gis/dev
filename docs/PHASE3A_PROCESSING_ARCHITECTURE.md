# Phase 3A — Processing architecture

The actual study supports a content-aware standalone analyzer followed by an analyst-operated GIS adapter. Originals remain immutable; each derivative, classification, view, control, transformation and review is traceable to source SHA-256. This phase implements inspection/review, not a toolbox or geographic registration.

## Component A: As-Built PDF Analyzer

`pdf_inspect.py` extracts evidence, `pdf_classify.py` recommends processing paths and `pdf_study.py` manages reports/review snapshots. They reuse the backend loader, SHA-256/JSON/CSV helpers, composition renderer and existing review identity checks. Legacy extraction/batch behavior is preserved.

| Responsibility | Implementation | Evidence boundary |
| --- | --- | --- |
| PDF/page inventory and identity | New `pdf-study`; existing `batch` | Hash identifies source; filename/producer does not establish content |
| Native text, paths, image and annotation separation | `pdf_inspect`; existing raster preparation | Preserve the intact composite; paths have no assumed CAD semantics |
| Select extraction approach by content/coverage | `pdf_classify` | Automated labels remain unreviewed |
| Native images, high-resolution compositions and crops | Existing `prepare-rasters` | Retain source dimensions/format, rotations and page/pixel mappings |
| Optional OCR for scans or outlined labels | Existing OCR adapter/baseline | Keep OCR separate; score only accepted references |
| Geographic/scale candidates | Positioned native-text diagnostics, existing clue workflows | Printed scales are not effective calibration; candidates are not approvals |
| Human corrections/acceptance | Phase 1C/2A evidence infrastructure | Preserve original transcription and full history |
| Locality hints | Existing read-only Phase 2B workflows | Model-input landmarks remain separate from independent location truth |
| Control/checkpoint collection and feasibility | Existing Phase 2B.3 | Independent acceptance and geometric safeguards; do not fit during ingestion |

No new packages are needed. PyMuPDF plus the standard library handle the new study. NumPy remains available for existing optional feasibility diagnostics. The new modules import no ArcPy. Spatial Analyst and Image Analyst are not required.

Two actual findings govern the architecture: selectable plat text should be reused, yet thousands of Calabash paths still contain outlined lettering requiring selective OCR; insurance pages have vectors without engineering relevance. Maintain distinct decisions for **content**, **engineering relevance**, **view**, **markup authority** and **geographic acceptance**.

## Proposed handoff contract

Component B should consume Component A's versioned evidence rather than reimplement inspection or change accepted clue files. Current outputs contain document/page IDs, source/config/artifact hashes, boxes, rotation/matrices, classification evidence, positioned native text, full path arrays, candidate scales and processing recommendations.

Before a toolbox is implemented, add independently reviewed **view records** containing:

- Source PDF/page IDs, accepted content type and engineering relevance.
- Approved plan/profile/inset boundary, crop/image hash and original dimensions, page-to-pixel mapping and reading orientation.
- Native versus OCR provenance and accepted clue references without overwriting source transcriptions.
- Per-view scale evidence, bar endpoints/measurements/units, acceptance and resizing limitations; separate horizontal/vertical values where needed.
- Existing Phase 2B.3 control/checkpoint IDs, fit/check roles, accepted coordinates/CRS and transformation provenance.
- Initial-placement hint/uncertainty, separately from any fitted transform, validated footprint or positional accuracy.
- Revision/history and immutable original links, supporting multiple registered views per sheet and multiple documents per map location.

These are proposed additions, not populated geographic facts. No view polygon, effective scale or control coordinates were invented.

The current coordinate frame is **unrotated visible-page points, MuPDF top-left, 72 points/inch**. Native paths/text/annotations use that frame. Original PDF rotation and page-to-pixel mappings are explicit. Component B must map a selected crop/image through those transforms; it cannot assign an EPSG code to page points. Independently scaled profiles and NTS insets require separate treatment.

## Component B: future ArcGIS Pro Georeferencing Assistant

Build a thin Python toolbox/UI adapter later, inside a licensed ArcGIS Pro session:

1. Validate hashes and analyst-approved view selection. Resolve uncertain engineering scope and per-view scale.
2. Prepare a derivative raster of the full engineering composite at a deliberate resolution, with annotations/masks retained. Native image extraction alone can omit visible modifications.
3. Add derivative and read-only authoritative references to the analyst map. Locality/scale hints may seed an explicitly unregistered overlay.
4. Reuse the Phase 2B.3 workflow or import explicitly reviewed GIS correspondences, including reference feature identity/vintage, datum, units and historical-change concerns. Matchlines/stationing alone cannot supply coordinates.
5. When separately authorized and geometrically feasible, fit suitable transformations and assess spatially distributed independent checkpoints. Fit residuals/RMS are not checkpoint positional accuracy.
6. Save a new derivative/sidecar and accepted transformation/control history. After validation, derive coverage from the approved plan view rather than the page border/title block.
7. In a subsequent authorized milestone, publish a separate verified-coverage document index for map-based PDF retrieval. Its many-to-many document/view coverage records remain independent of utility asset associations and do not require editing existing SDE assets.

Esri describes the same essential progression of control correspondence, transformation, review and saving, with spatially distributed controls. [Esri georeferencing overview](https://doc.esri.com/en/arcgis-pro/latest/help/data/imagery/overview-of-georeferencing.html).

## ArcGIS Pro Basic feasibility

Official documentation checked on 2026-10-20 lists these future operations for **Basic**, without Spatial Analyst or Image Analyst:

| Operation | Documented option |
| --- | --- |
| Render a PDF page to TIFF; optionally retain supported embedded georeferencing | **PDF To TIFF**, including page/map selection for supported geospatial PDFs. [Esri PDF To TIFF](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/conversion/pdf-to-tiff.html) |
| Warp a derivative using established correspondences | **Warp**, including similarity/affine options; apply the project's control/checkpoint safeguards. [Esri Warp](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/data-management/warp.html) |
| Reproject an already referenced derivative | **Project Raster**, with an explicit appropriate geographic transformation for differing datums. [Esri Project Raster](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/data-management/project-raster.html) |

This establishes a plausible Basic path; it does not demonstrate that the local ArcPy product-license initialization problem is resolved, or validate a toolbox against the county's installed Pro version. No ArcPy tool was invoked here. Use Pro's Georeference tab for analyst interaction; validate automation/API support and installed tool parameters before implementation. No extension-based deep-learning tool is necessary for this scope.

Assigning a projection does not align an unregistered drawing. Define Projection changes coordinate-system metadata without changing geometry; it must not replace control-based alignment. [Esri Define Projection](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/data-management/define-projection.html).

## County CRS and datum policy

County map/registered-view output should use **NAD 1983 StatePlane North Carolina FIPS 3200 (US Feet), EPSG:2264**, with easting/northing in **US survey feet**. The exact `1200/3937` metre factor is a unit conversion, not a datum transformation.

Interchange may use **EPSG:4326 longitude, latitude**. Preserve original coordinates/CRS alongside transformed values. Follow the [Phase 2B.3 transformation policy](PHASE2B3_CONTROL_REGISTRATION.md): no implicit 2264/4326 conversion; mixed-CRS controls require explicit transformed-coordinate evidence with operation/parameters, source/output binding, software, datum/grid notes, accuracy and timestamp. Pyproj is not a new prerequisite. The future GIS adapter can perform a documented appropriate conversion in the licensed GIS session.

A printed NAD83(2011) or other grid label requires datum-realization, units and epoch verification; it is not automatic EPSG:2264 confirmation. WGS84 reference-export confirmation from earlier phases does not establish a historical drawing's survey datum. Do not infer control coordinates from scale, north arrows, stationing or the C7/C8 371.19 m review locality.

## Next development gate

Recommend **Phase 3B: Analyst-Reviewed View Selection and Scale Calibration**. Accept/correct study labels; distinguish supporting forms from plats/plans; approve per-view scope/orientation; compare native extraction and selective OCR using accepted transcriptions; validate graphical bars or measured features against applicable printed scales. Expand the real sample with a substantial engineering hybrid and known geospatial PDF.

Then collect distributed approved controls and separate checkpoints for a bounded engineering view through the existing workflow. A subsequent milestone can implement the Basic assistant handoff and derivative registration. Verified-coverage indexing can follow; utility asset matching remains separate.
