# Codex Project Handoff — Utility As-Built PDF to GIS Asset Matching

**Status:** Planning / feasibility pilot. **Purpose:** Provide the context of a ChatGPT planning discussion to Codex in VS Code. This is a summary, **not an exact transcript**.

## Project objective

Build a standalone, primarily Python-based system that:

1. Registers engineering as-built PDF drawings and tracks their sheets and revisions.
2. Determines where each drawing belongs geographically, even if it is not georeferenced.
3. Extracts individual utility assets shown on each relevant plan view, including water mains, valves, hydrants, meters, fittings, etc.
4. Matches each depicted asset against authoritative utility GIS features.
5. Produces explainable candidate associations, with review and approval before publication.
6. Stores a many-to-many PDF/sheet-to-GIS-asset association without duplicating the original PDFs on every asset.

The project is being prepared for a supervisor as a phased **feasibility pilot**, not an immediately committed enterprise deployment.

## Operational and technical context

- Organization: Brunswick County Public Utilities, North Carolina; GIS asset data.
- Current desktop GIS: ArcGIS Pro; enterprise geodatabase in Microsoft SQL Server accessed via SDE connection (`GEOBASE`).
- Traditional geodatabase versioning is used. Integration with the CentralSquare Lucity asset management system matters, but the initial AI pipeline should **not modify authoritative asset geometries**.
- GIS spatial reference: North Carolina State Plane NAD83 feet; `EPSG:2264` (Esri legacy WKID 102719 also encountered).
- Utility feature classes may have `GLOBALID`, `FACILITYID`, and other type-specific attributes; verify actual schema before coding. `FACILITYID` is important for Lucity but may be absent/unassigned on some records.
- PDF collection includes engineering as-builts, some raster/scanned and some vector, with inconsistent quality, file nomenclature and metadata. Some lack explicit coordinate information.
- The county **does not have ArcGIS Pro Image Analyst or Spatial Analyst extension licenses**.
- The ArcGIS Pro Deep Learning Libraries have been installed, and a VS Code workflow is preferred.

## Fundamental licensing decision

**Do not call geoprocessing tools that require Image Analyst or Spatial Analyst** (such as the ArcGIS deep-learning geoprocessing tools). Use permitted general ArcPy data access and spatial operations under the organization's ArcGIS Pro license, plus directly imported third-party Python modules. Installing Esri deep learning libraries does not itself grant extension licenses.

The code should be modular so the AI engine can later run without ArcPy; only the GIS adapter needs ArcPy or approved ArcGIS feature services.

## Recommended Python stack

- `pymupdf` (`fitz` / `pymupdf`): PDF text extraction, page rendering, vector drawing paths (`page.get_drawings()`). Check package/license suitability for organizational use.
- Local OCR such as Tesseract: scanned-PDF text when necessary.
- `torch` / `torchvision` (already possibly installed via Esri libraries): custom point-symbol detection and optional semantic segmentation.
- Optionally experiment with `arcgis.learn` classes **only after verifying installation, version compatibility, callable APIs and licensing conditions**; do not depend on them for the architecture.
- `opencv-python` (`cv2`) + `numpy`: feature alignment, affine/similarity transforms, image processing, geometrical extraction.
- `scipy` / `shapely` / `networkx`: candidate ranking, spatial geometry checks, topology comparison and assignment resolution.
- `arcpy`: read authoritative SDE features, create staging features, conduct basic spatial queries and visualize final results in ArcGIS Pro without unlicensed extensions.
- `sqlite3` or a file geodatabase for early-stage registry, review and candidate records; approved SQL Server design later.

Use a cloned ArcGIS Pro Python environment for experiments. Verify imports, package versions, GPU availability and compatibility before installing any new dependencies.

## Major processing stages

### A. Ingest / classify documents
- Index file paths and SHA-256 hashes; track revision, sheet count, original filenames and provenance.
- Determine raster vs vector per sheet, extract embedded text and drawing paths.
- Identify plan views separately from title blocks, profiles, legends, notes and not-to-scale details.

### B. Text / geographic clue extraction
- Detect road names, subdivision names, lot numbers, coordinate ticks, survey control points, facility identifiers, pipe sizes and drawing title-block locations.
- Resolve candidates with road, parcel and utility GIS layers; ambiguous location clues must not become automatic exact coordinates.

### C. Detect drawing utility assets
- Initially focus on point utility symbols (hydrants, valves, meters, etc.).
- For vector PDFs, attempt direct extraction of useful linework before training a raster-based model.
- For scans, use image preprocessing, segmentation and line skeletonization when appropriate.
- Tile and overlap large drawing images to avoid losing tiny symbols; track page/pixel coordinates and model metadata.

### D. Georeference the drawing
- Use known matched control points where available; optionally test network-pattern-based candidate placement.
- Implement and validate coordinate transformations in OpenCV/NumPy (e.g., affine via RANSAC), independent of spatial/image analyst tools.
- Convert page/pixel or vector PDF coordinates into state plane feet only after registering coordinate conventions and confirming a credible transformation.
- Keep uncertainty estimates, residual errors and independent checkpoint validation.

### E. Match detections to authoritative SDE assets
- Query feature classes on the correctly selected SDE version using approved GIS access methods.
- Score based on proximity, class/subtype, geometry, topology/connectivity, attribute match and drawing contextual clues.
- Distinguish correct asset from nearest asset; resolve collisions/conflicts. Handle point and line features differently.
- Distinguish **existing/installed** from **proposed** or **removed** drawing assets.
- Permit zero candidates; do not force a match.
- Keep explainable evidence and provenance for every proposed association.

### F. Review / publish
- Expose original PDF page, transformed drawing overlay, SDE assets and per-link evidence to an analyst.
- Approve/reject/defer candidates and record reviewer/date/reason.
- Write to association tables only after the appropriate review and governance steps.
- Maintain relationship between original PDF and sheet with one-to-many or many-to-many reference links, not PDF duplication per asset.

## Proposed data model

1. `ASBUILT_DOCUMENT`: document ID, relative/managed path or URI, file hash, issue/revision, metadata, page count, status.
2. `ASBUILT_SHEET`: sheet ID, document ID, page index/sheet number, sheet title, drawing extent/georeference and positional accuracy.
3. `ASBUILT_DETECTION`: sheet ID, geometry in sheet coordinates, asset class, detection score, model version, processing run.
4. `ASBUILT_ASSET_LINK`: link ID, document/sheet IDs, source feature class, asset `GLOBALID`, optional `FACILITYID` snapshot, match score, method/evidence, review status, processing run, timestamps.
5. `ASBUILT_REVIEW`: link ID, reviewer, decision, rationale, timestamp, revision of proposal.

The generic `SOURCE_CLASS` + `ASSET_GLOBALID` link registry is **not** automatically an ArcGIS native relationship class across multiple feature classes. Evaluate separate native relationship classes if ArcGIS-native related-record behavior is required. Respect traditional versioning and avoid directly writing untested SQL into managed versioned geodatabase tables.

## Suggested repository structure

```text
AsBuiltAssetMatcher/
  README.md
  AGENTS.md                 # optional durable development guidance
  docs/
    ASBUILT_CODEX_CONTEXT.md
    design.md
    data_dictionary.md
  config/
    settings.example.yaml
    asset_classes.example.yaml
  src/asbuilt_matcher/
    ingest.py
    pdf_extract.py
    text_extract.py
    detect.py
    geolocate.py
    register.py
    gis_adapter.py
    candidates.py
    scoring.py
    review.py
    publish.py
  scripts/
    check_environment.py
  tests/
    test_ingest.py
    test_georeference.py
    test_candidates.py
  examples/                 # de-identified/synthetic examples only
```

## Development phases

1. **PDF intelligence (no AI):** inspect 10-20 varied representative PDFs, extract text and vector paths, identify layout and quality; establish a reference set of verified links.
2. **Geographic location:** identify possible neighborhoods/subdivisions via labels and road/parcel layers; georeference using verified control points; compute errors and abstain on uncertain documents.
3. **Symbol identification:** prepare labeled symbol examples; test PyTorch detection and conventional vector parsing; record point and line geometries.
4. **Spatial asset matching:** read-only SDE candidate extraction, geometry/topology comparison, confidence ranking and conflict handling.
5. **Review and publishing:** GIS overlay, approvals, auditable link tables, validation on held-out PDFs and production feasibility report.

Success metrics should separately measure drawing-location correctness, individual point/line detection precision-recall, asset-link precision-recall, abstention rates, analyst review burden, and false approved links. Do not treat raw weighted scores as calibrated probabilities without empirical validation.

## Start here: requested coding task for Codex

1. Inspect the current workspace; **do not assume any files or trained model already exist**.
2. Scaffold a small, testable Python package and `check_environment.py` that reports environment, key imports, installed package versions, CUDA/GPU status and ArcPy license availability (without checking out unavailable extensions).
3. Create a CLI command that ingests one engineering PDF, extracts per-page embedded text, vector-path statistics and raster preview(s), generates document/page metadata and logs errors.
4. Add unit tests using synthetic fixture PDFs rather than real county drawings.
5. Document how to run from the cloned ArcGIS Pro Python environment in VS Code on Windows.
6. **Do not access or modify GEOBASE production data, connect to external AI APIs, upload real as-builts, or install dependencies without explicit approval.**

## Important boundary

This file is a curated context handoff from a ChatGPT planning discussion, not a live synchronized chat. The original ChatGPT discussion includes earlier conceptual Python examples and an editable Word management proposal. Verify all third-party library APIs and licenses against the versions actually installed. Treat suggestions and hypothetical thresholds as design ideas rather than approved production policy.
