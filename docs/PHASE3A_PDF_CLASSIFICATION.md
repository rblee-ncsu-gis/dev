# Phase 3A — Representative PDF classification and ingestion assessment

2026-10-20. Technical extraction plus AI inspection of selected previews. **No classifications, geographic controls or scale calibrations have received independent analyst acceptance in this study. Classification and positional accuracy are not measured.**

## Management assessment

The analyst approved all **26 PDFs in `src/pdf`**, with the original four explicitly labeled prior-pilot comparisons. All **75 pages** were inspected without extraction errors or source-byte changes. The collection contains **69 predominantly raster pages (92%) and six predominantly vector pages (8%)**. Only two pages have base native text; three pages retain separate PDF annotations.

Vector content does not eliminate OCR. Much visible engineering lettering is drawn as outlines, and two vector pages are insurance forms rather than plans. Conversely, native text and geometry on the subdivision plats should be reused before rasterizing everything. A single raster/OCR path would lose useful information.

Recommend **Phase 3B: Analyst-Reviewed View Selection and Scale Calibration**: accept/correct these classifications; separate paperwork, plans, profiles and insets; compare native extraction with selective OCR; verify applicable graphical scales; and collect independent controls/checkpoints through Phase 2B.3. Build a thin ArcGIS Pro Basic assistant only after that evidence gate. Automatic registration and asset matching are not justified by this study.

These figures describe the selected sample, not the county archive. The 50-page closeout package supplies two-thirds of the page denominator. Repeated scans and rotated duplicates reduce independence. No random-sample or accuracy inference is made.

## Inputs, commands and deliverables

The single input-directory setting is `input_directory` in [config/pdf-study.json](../config/pdf-study.json), resolved relative to that file. It selects `../src/pdf` nonrecursively, including all case-insensitive `.pdf` files. `prior_pilot_files` labels `s07770.pdf`–`s07773.pdf`, rather than excluding them. The three accompanying DWGs have size/hash/exclusion records but are not parsed or counted as PDFs.

The final run is **[study-003](../outputs/phase3a/study-003/ASSESSMENT.md)**. Earlier discovery/study directories remain development observations. Study-001 used layout-sorted text and had an annotation image-cache issue; both were corrected before the final run.

| Artifact | Contents |
| --- | --- |
| [inspection.json](../outputs/phase3a/study-003/inspection.json) | Full inventory, source/config hashes, backend version, criteria, cohorts, page evidence, errors and repeated-content diagnostics |
| [documents.csv](../outputs/phase3a/study-003/documents.csv) | 26 document records with size, PDF version/metadata, restrictions and recommendations |
| [pages.csv](../outputs/phase3a/study-003/pages.csv) | 75 classifications, page boxes/dimensions, rotations, counts, quality indicators and processing paths |
| [native-text.csv](../outputs/phase3a/study-003/native-text.csv), [vectors.csv](../outputs/phase3a/study-003/vectors.csv) | Text distribution/quality and vector summaries |
| [raster-hybrid.csv](../outputs/phase3a/study-003/raster-hybrid.csv), [annotations.csv](../outputs/phase3a/study-003/annotations.csv) | Image coverage/DPI and markup diagnostics |
| [scales.csv](../outputs/phase3a/study-003/scales.csv), [registration-readiness.csv](../outputs/phase3a/study-003/registration-readiness.csv) | Unverified statements/bar candidates and remaining preparation needs |
| [REVIEW.html](../outputs/phase3a/study-003/REVIEW.html), [classification-review.csv](../outputs/phase3a/study-003/classification-review.csv) | Offline visual report and analyst worksheet |
| [classification-decisions.template.json](../outputs/phase3a/study-003/classification-decisions.template.json) | Hash-bound decisions, all initially unreviewed |
| `documents/document-NNNN/page-NNNN/` | Intact composite PNG, base native text, positioned words/lines/spans, full native vector operation arrays and page JSON/artifact hashes |
| `inspection.log` | Progress, exceptions and completion status |

Run from the project root without package installation or environment-variable changes:

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
& $pythonExe scripts/run_asbuilt.py pdf-study config/pdf-study.json --output outputs/phase3a/study-next
```

Output must be new and outside the PDF input tree. Invalid settings/missing input paths fail preflight. Failed documents/pages remain in reports; partial runs return exit code 1. Empty selections produce header-only CSVs. Password-required PDFs are reported as failures, with no bypass. None occurred in the actual run.

## Actual composition

| Files | Documents / pages | Observed content |
| --- | ---: | --- |
| `17-0221_SWPhase7A_Water&Sewer_Rec_Dwgs.pdf` | 1 / 1 | Full-page raster |
| Four `31725-Phase 3 WS-(signed)` PDFs | 4 / 4 | Full-page raster despite electronic-looking filenames |
| `31725.500 2026-08-19 BC W&S closeout.pdf` | 1 / 50 | 46 raster pages; vector pages 13, 14, 23, 24 |
| `Calabash Lakes Redev Plans Sheet 8.pdf` | 1 / 1 | Raster plan plus nine PDF annotations |
| Two `Calabash Lakes_Asbuilt_Randy Ward PLS_08192016` variants | 2 / 2 | Same base drawing fingerprint; native vectors, no base text, six annotations each |
| `s05990.pdf`–`s05992.pdf` | 3 / 3 | Raster; producer metadata absent |
| `s07770.pdf`–`s07773.pdf` | 4 / 4 | Raster, prior-pilot comparisons |
| `s07774.pdf`–`s07783.pdf` | 10 / 10 | Raster, new representative files |

| Automated overlapping category | All 75 pages | New sample: 71 pages | Prior pilot: 4 pages |
| --- | ---: | ---: | ---: |
| Predominantly raster | 69 (92.00%) | 65 (91.55%) | 4 (100%) |
| Predominantly vector | 6 (8.00%) | 6 (8.45%) | 0 |
| Text-rich digital threshold met | 2 (2.67%) | 2 (2.82%) | 0 |
| Separate PDF annotations | 3 (4.00%) | 3 (4.23%) | 0 |
| Substantial raster/vector hybrid | 0 | 0 | 0 |
| Possible geospatial dictionaries detected | 0 | 0 | 0 |
| Indeterminate / failed pages | 0 | 0 | 0 |

The absence of substantial page hybrids does not mean an absence of mixed content. The closeout mixes page types; a vector form has a small raster signature image; Calabash vector drawings include raster stamp appearances. These differ from substantial raster engineering views combined with substantial base vector linework.

Twenty-four documents contain raster pages; three contain vector pages, with the closeout in both groups. One document has base native text. The two Calabash variants remain separate hash records, not independent extraction examples.

Technical totals: **91,428,343 PDF bytes**; PDF headers 1.3, 1.4, 1.6 and 1.7; 67 pages at rotation 0°, five at 90°, one at 180° and two at 270°. No password requirement, permission restrictions, in-memory repair or optional-content groups were observed. Metadata is retained, never used as classification truth.

## Criteria and coordinate conventions

`pdf_classify.py` supplements the older presence-only `batch.classify_page`; legacy behavior is preserved. Criteria are configurable, validated and copied into every report:

| Criterion | Default |
| --- | --- |
| Dominant raster coverage | At least 65% of visible page |
| Substantial image coverage for hybrid | At least 15% |
| Incidental image candidate | At most 5% |
| Substantial base vectors for hybrid | At least 20 non-border/background paths |
| Text-rich flag | At least 200 non-whitespace base characters; less than 15% raster |
| Usable native-text candidate | At least 30 non-whitespace characters; at most 5% replacement/private-use/control characters |

Hybrid takes precedence when substantial base vectors and image area coexist. A dominant raster with only searchable text, a border or minor overlays stays raster. Native paths below the substantial raster threshold receive vector classification. A text-only page can be text-rich digital; insufficient/unsupported evidence is indeterminate. Annotation and geospatial indicators overlap the primary class. Text-rich is a count/quality flag, not proof of selectable labels throughout a plan.

Image coverage is the clipped **union of occurrence bounding boxes**, avoiding double-counted overlaps/tiles. It overestimates visible ink for skew, masks, clipping and occlusion. An obvious border/background candidate has at most five operations and a box covering at least 90% of page area. All original paths remain exported; path count does not establish engineering semantics.

Coordinates are **unrotated visible-page points, MuPDF top-left, 72 points/inch**. Page media/crop/trim/bleed/art boxes, original rotation, displayed rectangle and rotation/derotation matrices are retained. Previews share this unrotated frame and record exact page-to-pixel mappings. PDF physical dimensions are not ground dimensions.

## Native text and geographic clues

Only closeout **p23/p24** contain base native text: **500/530 characters**, **82/83 words**, **407/432 non-whitespace characters**. Positioned text occupies only **four/five of 16 layout cells**, largely title/plot information and vicinity-map headings. Recoverable strings include `CALABASH POINTE`, `PHASE 3`, `SHALLOTTE TOWNSHIP`, `BRUNSWICK COUNTY, NORTH CAROLINA`, consultant details, sheet information and scale statements. Spaced headings and wrapped sheet identifiers require review. No suspect replacement/private-use/control characters were detected; Unicode bullet characters are valid.

Visible road names, lot numbers, bearings, dimensions and coordinate annotations are substantially represented as vector outlines. Calabash base plans have **zero native text despite visible lettering**. Selective high-resolution OCR remains useful even on vector PDFs. Zero text alone does not establish raster origin.

Each page stores `native-text.txt`, positioned words/lines/spans in `native-text.json`, and separate intact `composite-text.txt`. Source-order text supplies character counts: layout-sorted extraction can synthesize whitespace. OCR was not executed or merged here. Future OCR must use the existing composition/crop preparation and adapter, not resolution-capped study thumbnails.

Each Calabash vector file has **182 characters only in annotation appearances**, including received/project/source notes and “New Manhole.” These are separate evidence, not native base labels or accepted geographic clues. Lexical project/road/station/pipe/scale candidates retain page positions and unverified status. They do not overwrite or promote any earlier accepted clue registry.

## Vector, imagery and modification assessment

The six vector pages contain **55,528 base paths**:

| Source / page | Paths | AI visual assessment; not analyst acceptance |
| --- | ---: | --- |
| Closeout p13 | 247 | Insurance certificate with outlined text/tables and a small image |
| Closeout p14 | 27 | Insurance continuation, not an engineering plan |
| Closeout p23 | 18,798 | Subdivision plat: plan, title, vicinity map, symbols, hatching and outlined text |
| Closeout p24 | 26,530 | Companion subdivision plat |
| Each Calabash vector variant | 4,963 | Native plan/alignment/lot graphics and outlined lettering, with separate annotations |

Exports retain lines, curves, rectangles, quadrilaterals, fills, coordinates/extents, stroke widths, dashes, colors, opacity and PDF layer names where present. Each Calabash base plan includes **133,902 line operations**; each plat has tens of thousands of lines plus curves. Fractional page coordinates survive extraction, supporting page-space measurement and scalable rendering. This is not CAD identity/topology, verified geometric tolerance or geographic accuracy.

Style/border/rectangle diagnostics nominate review areas; they cannot reliably separate utilities from outlined lettering, hatching, parcels, symbols or title blocks. The insurance pages demonstrate this directly. No AutoCAD layer/object/block or geodatabase attributes are assumed.

There are **70 base image occurrences**: 69 full-page scans and the closeout-p13 image occupying about **0.417%** of its page. PDF filters include CCITT Fax, DCT/JPEG and Flate. Native dimensions, masks, transforms, resource references, decoded-pixel digests and estimated effective DPI are recorded. Placement-based resolution spans roughly **200–474 DPI** across image axes. DPI describes pixels per printed inch, not ground resolution or guaranteed readability; generic image `xres` metadata is not used as effective resolution.

Two additional composite-only images belong to Calabash stamps. PyMuPDF caches `get_image_info` on Page objects, so pages are reloaded after annotation removal **in memory** to prevent stamp images contaminating base counts. No source PDF is saved.

The **21 separate annotations** comprise nine Polygon/Square objects on redevelopment p1 and six Stamp/FreeText/Polygon objects on each Calabash variant. Comments, author/date strings, rectangles, vertices, flags, colors and appearance references are retained. Intact composition is rendered before separation. Red/orange objects are modification-review candidates, not approval of construction authority. No red base paths met the RGB heuristic. Flattened or raster redlines cannot reliably be separated into original versus modified geometry, especially after grayscale scanning.

The signed standalone scans repeat as identical base-content fingerprints on closeout **p47–p50**. The two Calabash variants also share a base fingerprint despite different source hashes/rotations. Decoded-image MD5 supports repetition diagnostics only; source evidence uses SHA-256. Duplicates must not inflate evaluation sample sizes.

## Scale and georeferencing readiness

Closeout p23/p24 each yield **`1 INCH = 60 FEET`** plus a distinct **`not to scale`** vicinity-map statement. Both boxes are preserved; view scope remains unknown. Nearby native geometry produces **20 horizontal segment candidates per plat**, a shortlist rather than 20 detected bars. Visual inspection shows a graphical bar in the title area. Native endpoint distances can support later analyst-confirmed calibration once endpoints, units and the applicable view are accepted.

Scanned scales/bars require OCR or manual transcription. The redevelopment preview visibly contains a scale and graphic region but has no native scale transcription; no value was promoted. Outlined scale text has the same limitation. No OCR-based scale accuracy is claimed.

The plats are **24 × 18 PDF inches**; the Calabash vector files are **36 × 48 inches** unrotated. Variation in sheet dimensions, placement DPI and metadata cannot establish original plot size or rule out reduction, resizing and scan distortion. Different plan/profile/inset views can have different horizontal and vertical scales. **A recognized statement is not verified effective page scale.** No page-wide ground resolution, placement, footprint or transform was assigned.

Page/catalog `LGIDict` and `VP`/`Measure` `/Subtype /GEO` structures were checked; **no candidates were detected**. A viewport alone is not geospatial. The bounded check cannot certify absence of proprietary/unusual nested referencing, and XMP presence alone is not georeferencing. Detected structures would remain unverified pending declared-CRS/control validation.

Visible plat coordinate/grid labels are future evidence candidates, not control coordinates. A printed datum realization must not be silently equated with EPSG:2264. A locality plus independently checked view scale could eventually initialize an approximate analyst overlay; it would not establish position/orientation. Existing C7/C8 371.19 m localities remain context hints, not sheet extents. No Phase 2B.3 controls/checkpoints or feasibility findings were altered.

## Analyst workflow and unresolved questions

Open `REVIEW.html` locally, inspect composites and original PDFs, and choose confirm/correct/reject/unreadable. Adjust primary/overlapping labels and enter evidence/reasons. Identify reviewer/type and explicitly attest independent review where applicable; download decisions. Every page initially stays unreviewed. The CSV is a worksheet; apply uses the JSON template or HTML download:

```powershell
& $pythonExe scripts/run_asbuilt.py pdf-study-review `
  outputs/phase3a/study-003/inspection.json `
  outputs/phase3a/classification-decisions.json `
  --output outputs/phase3a/analyst-review-next
```

Review reuses `clues.review_identity`, validates source/page-artifact and inspection/run hashes, then creates a **new** snapshot. Automated labels and prior approvals remain untouched. AI/unspecified reviews can be recorded but are not independent acceptance. Attestations are local, not authenticated identity management. To correct a previous snapshot, pass its `classification-review.json` and add `parent_snapshot_sha256` to the decisions; all events and original classifications remain in history. Reviews do not automatically produce accuracy scores.

Remaining analyst tasks:

1. Identify utility plans, plats, supporting correspondence and forms inside the closeout package; content type alone cannot establish relevance.
2. Accept view boundaries and reading orientations, including profiles and NTS insets. Coordinate normalization does not determine intended reading orientation.
3. Select outlined/native labels for an OCR comparison and independently accept transcriptions; check graphical bars and resized-plot risks by view.
4. Establish which annotations/flattened edits describe installed, proposed, removed or corrected infrastructure.
5. Verify datum realization, units/epoch and stable corresponding features before collecting geographically distributed controls and separate checkpoints.
6. Expand with selectable-text CAD plans, a substantial engineering hybrid and a known geospatial PDF. Those positive cases are absent here; synthetic tests are not actual prevalence or accuracy evidence.

## Testing and preservation

The pre-change baseline was **240 passing tests**, including the earlier 207. Actual-file regressions cover annotation/base separation and the closeout plat when supplied PDFs are available. Missing combinations/error paths use clearly labeled synthetic fixtures: searchable scans, hybrids, text-only/blank pages, geospatial measures, misleading producers, multi-scale text, encryption/corruption, failed extraction, stale evidence and correction histories. They never enter the actual sample counts. Real-source tests skip explicitly if analyst files are unavailable.

Final validation: **280 tests pass (240 preserved + 40 new)**; **all 204 protected files, including the original 25 artifacts, remain unchanged**. The 375 page-artifact hashes and all consolidated/standalone JSON records agree. CSVs contain 26 document rows and 75 rows per page report. The installed-browser check passed six review/export safeguards without applying any simulated decisions; its isolated copy/profile is separate from the study.

Hashes/details are in [validation.json](../outputs/phase3a/validation.json), with [tests.xml](../outputs/phase3a/tests.xml). The protection audit extends earlier lists to source PDFs/DWGs and Phase 2B.3 records. Prior evidence/approvals remain byte-preserved. No dependencies were installed, environment settings changed, ArcPy/SDE/asset operations performed or geographic registration attempted.

Inspection uses the existing [PyMuPDF page APIs](https://pymupdf.readthedocs.io/en/latest/page.html). See [PHASE3A_PROCESSING_ARCHITECTURE.md](PHASE3A_PROCESSING_ARCHITECTURE.md) for the standalone/GIS responsibilities and documented Basic licensing options.
