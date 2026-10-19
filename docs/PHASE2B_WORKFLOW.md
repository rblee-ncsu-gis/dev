# Phase 2B: read-only geographic localization

For independent controls and registration preparation, see
[Phase 2B.3 control collection](PHASE2B3_CONTROL_REGISTRATION.md).
Point proposals, independent acceptance, fitting and held-out checkpoint validation
are separate steps. Landmarks and station values do not become controls automatically.

For the current landmark experiment, see
[Phase 2B.2 landmark narrowing](PHASE2B2_LANDMARK_NARROWING.md).
`landmarks-import` resolves supplemental references from read-only exports;
`corridor-narrow` adds separate review localities to a frozen corridor run.
Original candidates and clue approvals are preserved. Landmark input points and
coarse review localities cannot establish independent drawing ground truth.

For the current corridor experiment, see
[Phase 2B.1 alias resolution](PHASE2B1_ALIAS_RESOLUTION.md). `localize --aliases`
opts into a hash/feature/field-scoped registry. The original no-alias workflow is
preserved. `roads-diagnose` exports actual matching field values and geometries.
Corridor outcomes are reviewed separately from narrowed candidate areas; independent
references can now include areas, intersections, control points and footprints.

This prototype ranks geographic **areas**, not utility assets. It reads frozen local
GeoJSON and existing accepted clue exports. All candidate decisions start pending.
It never edits clue registries, connects to SDE, calls ArcPy, or downloads maps.
The existing human approvals remain valid and unchanged.

## County validation and approved imports

The October 19 delivery has all seven files in `reference/brunswick_county/`.
The canonical manifest is generated in `data/reference/brunswick_county/` without
moving or editing source exports. The analyst has confirmed their WGS84 coordinate
order and approved the initial road, subdivision and address mappings; those
decisions are retained in `outputs/phase2b/county-analyst-decisions-001/decisions.json`.
The actual run and remaining review tasks are in
[PHASE2B_REAL_WORLD_VALIDATION.md](PHASE2B_REAL_WORLD_VALIDATION.md).

Run from the repository root with a new output directory:

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
& $pythonExe scripts/run_asbuilt.py geo-validate --directory data/reference/brunswick_county --source-directory reference/brunswick_county --decisions outputs/phase2b/county-analyst-decisions-001/decisions.json --output outputs/phase2b/county-readiness-next
```

Omit `--source-directory` if files arrive in the requested directory itself. Omit
`--decisions` for an initial unapproved inventory. Missing files are listed and
do not make validation fail. Invalid geometry/JSON/CRS is reported and returns 1;
the manifest and usable mapping decisions are still retained. Current parcel and
postal geometry errors produce this nonzero outcome, separately from the three
ready layers. Inspect `ready_datasets`, `invalid_datasets`, errors and warnings.

Validation writes/updates `export_metadata.json` atomically, archives the previous
manifest under `metadata_history/`, and freezes a copy in the new output folder.
Hashes, fields/types, counts and geometry types are compared across runs. All
actual property fields receive present/null/blank/missing counts. Candidate-ID
fields also receive uniqueness/duplicate counts. Only validated geometries
contribute to reported geographic extents. No source SDE provenance is inferred
from file names, file timestamps or the county's usual CRS.

The output folder also contains `READINESS.md`, `fields.csv`,
`mapping-proposals.json`, `mapping-decisions.template.json`,
`reference-config.confirmed.json` and `validation.log`. Standard-library streaming
handles the supplied large exports without decoding the entire source file at
once. The imported feature catalog remains memory-resident during matching;
large candidate workloads are not yet performance validated.

For **new or changed** exports, copy the decision template to a new file. Review
all suggested fields and alternatives, then explicitly fill each approved layer's
`fields`, `status: "confirmed"`, `reviewer_type: "human"`, reviewer, time and reason.
Keep `dataset_sha256`. Set `crs_confirmed: true` / `output_crs: "EPSG:4326"` only
when export provenance supports it. Unconfirmed layers stay pending. Supply known
`source_metadata` keys: `source_feature_class`, `source_crs`, `database_version`,
`exported_at`, `data_owner`; leave unavailable facts null. Revalidate with this
decision file. Proposals alone never become confirmed mappings; altered source
hashes or altered approved field assignments invalidate their reuse. This is
reference-schema review, not repeated review of the eleven accepted clues.

`reference-config.confirmed.json` includes only layers with approved hash-bound
human mappings, CRS evidence and valid geometry. The importer checks the same
field assignments against the approval. Explicit file CRS declarations are
recorded as declarations; coordinate ranges alone never confirm CRS. The present
files rely on the separately recorded analyst attestation. Geometry validity and
CRS provenance remain distinct facts.

Then import the ready subset and run the existing localization/evaluation workflow:

```powershell
& $pythonExe scripts/run_asbuilt.py geo-import outputs/phase2b/county-readiness-next/reference-config.confirmed.json --output outputs/phase2b/county-reference-next
& $pythonExe scripts/run_asbuilt.py localize outputs/phase2a/human-acceptance-001/accepted/verified-clues.json --references outputs/phase2b/county-reference-next/references.json --settings config/geographic-ranking.json --output outputs/phase2b/county-c7-c8-next
```

Read the import summary before continuing. A partial import returns 1 but retains
the usable catalog and all exclusion reasons. Current data exclude 509 unnamed
features; partial status prevents definitive proposals. Keep the original county
run when testing later aliases or region grouping. Never fill geographic evaluation
decisions from schema approval or an expected location.

## Run the synthetic example

From the repository root, using the existing clone and bootstrap (no installation
or environment-variable changes):

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
& $pythonExe scripts/run_asbuilt.py geo-import examples/phase2b/reference-config.json --output outputs/phase2b/demo-reference-next
& $pythonExe scripts/run_asbuilt.py localize examples/phase2b/accepted-clues.json --references outputs/phase2b/demo-reference-next/references.json --settings config/geographic-ranking.json --output outputs/phase2b/demo-next
```

Open `outputs/phase2b/demo-next/REVIEW.html` in an ordinary browser. The SVG maps
work offline without extra software, JavaScript libraries, API keys or tile servers.
Expand a candidate to inspect reference IDs, geometry, raw accepted text, match
types, ranking points, conflicts and limitations. Orange dashed extents indicate
reference/search areas, not drawing footprints. Expandable evidence is read-only.
Every example feature and approval is fabricated; these are not county locations.
Always use **new output directories** to preserve earlier runs.

## Analyst reference-data delivery specification

Provide local UTF-8 **RFC 7946 GeoJSON FeatureCollections**, one dataset per file,
plus a completed copy of [the field-mapping template](../config/geographic-reference.example.json).
Actual field names are supplied by the analyst; placeholders are not inferred.

| Dataset | Geometry | Required mapped attributes | Optional mapped attributes |
| --- | --- | --- | --- |
| Road centerlines | LineString / MultiLineString | `id`: stable unique segment ID; `name`: full street name, or list of component fields | `aliases`: one or more fields containing alternate names/route labels (strings or arrays); `level`: comparable numeric/string crossing level |
| Subdivisions, where available | Polygon / MultiPolygon | `id`: stable unique boundary ID; `name`: subdivision name | `aliases`: approved alternate subdivision-name fields |
| Parcels | Polygon / MultiPolygon | `id`: stable unique feature ID | `parcel_id`: parcel identifier; `lot`: lot label/number; `address`: full address or list of component fields |
| Addresses | Point / MultiPoint | `id`: stable unique point ID; `address`: full address, or `address_number` plus `street_name` | Street components, municipal/township/postal fields, aliases |
| Town limits | Polygon / MultiPolygon | `id`: stable ID; `name`: municipal name | aliases |
| Townships | Polygon / MultiPolygon | `id`: stable ID; `name`: township name | aliases |
| Postal zones | Polygon / MultiPolygon | `id`: stable ID; `name`: postal-zone identifier | aliases |

For useful parcel/lot matching, include their corresponding optional fields.
Missing optional mappings disable that matching capability. An unmapped address is
not guessed from other fields. The schema now supports `address`, `municipal_name`,
`township_name` and `postal_zone` clues through the established manual review flow.
No new clues are fabricated from reference attributes.
No facility IDs, utility geometry or SDE credentials are requested.

Road component roles are `prefix_direction`, `street_prefix`, `street_name`,
`street_suffix`, `suffix_direction`; addresses can add `address_number`. A full
`name`/`address` mapping takes precedence over component composition. Subdivision
`phase` can support an explicit `name PHASE value` label; phase digits remain
significant. Field-name hints are proposals only: TYPE/SUFFIX, for example, can
mean different things in different actual schemas.

Supply an attribute dictionary explaining IDs, road-name components, aliases,
route conventions, lot uniqueness/scoping, null values and road levels. Preserve
identifiers such as GlobalID, road ID and PIN as strings when appropriate. Preserve
leading zeroes and hyphens. Do not rely on regenerated row numbers for durable IDs.
Native properties, GeoJSON feature IDs and geometry are retained in the catalog.

For each dataset provide metadata: `authority`, `source_layer`, export UTC time,
data vintage, source CRS, output CRS, geographic transformation used, county/area
filter or selection, omissions, source version and whether data are synthetic.
The importer requires authority/source layer and records all supplied metadata;
the analyst must complete the remaining provenance fields for real evaluation.
File paths resolve relative to the configuration file; URL inputs are unsupported.

Start with countywide road coverage or a documented sufficiently broad study
region containing **all competing road names**, not just an assumed correct site.
Provide matching subdivision/parcel coverage. Disclose clipped features, gaps,
duplicate names and historical differences from the plan date. A clipped search
can make the correct place disappear or create false uniqueness. An optional
`area_of_interest_bbox` in the config constrains exports; out-of-bounds features
are rejected, never silently clipped by this tool. The fixture bbox is fictional,
not an authoritative Brunswick County boundary.

## Coordinate-system and export requirements

All layers must contain **WGS84 longitude, latitude in decimal degrees**, recorded
as `EPSG:4326` in the config. GeoJSON coordinate order remains longitude first,
consistent with [RFC 7946 sections 3.1.1 and 4](https://www.rfc-editor.org/rfc/rfc7946.html#section-4).
Do not relabel StatePlane feet as WGS84 or mix EPSG:2264/3857 geometry with 4326.
This module performs **no reprojection**. Original source CRS and transformation
details belong in metadata, not in the output coordinates.

An analyst can prepare a separate local export using an existing approved GIS
application. ArcGIS Pro's [Features To JSON](https://pro.arcgis.com/en/pro-app/latest/tool-reference/conversion/features-to-json.htm)
supports GeoJSON and a Project to WGS84 option. Select GeoJSON, use actual field
names rather than aliases, and record the applicable NAD83-to-WGS84 transformation.
Alternatively project a **local copy** to WGS84 with an analyst-selected suitable
transformation before export. Check exported coordinate values and placement in
the GIS application. This is a proposed analyst export procedure; the prototype
does not run geoprocessing or change the Python environment.

Deliver linearized, valid simple geometry; curves and GeometryCollections are not
accepted. Prefer 2D exports; a third Z ordinate is retained but ignored in 2D
analysis, and M ordinates are unsupported. Preserve polygon holes and multipart
features. Check topology upstream; the small geometry kernel checks shape/range,
closure and degeneracy, not complete GIS topology validity. Null/invalid features
are reported individually in `import.log`/`errors`; duplicate native IDs and
conflicting CRS declarations stop import. Partial imports cannot yield a definitive
`proposed_area` status.

The kernel uses a WGS84 ellipsoidal local east/north tangent-plane projection for
metre-based comparisons; geographic output stays WGS84. The recorded origin and
250-km aggregate-extent limit bound its use to a county search. Latitude is limited
to +/-80 degrees; global/antimeridian geometry is rejected. This is not a datum
transformation or StatePlane survey registration. CRS labels
and number-range checks cannot detect every mislabeled but plausible coordinate;
independent export QA remains necessary.

## Import county data and process C7/C8

Replace mappings/paths in a new config. Remove unavailable optional layers/fields,
rather than leaving placeholders or inventing values.

```powershell
& $pythonExe scripts/run_asbuilt.py geo-import config/county-reference.local.json --output outputs/phase2b/county-reference-next
& $pythonExe scripts/run_asbuilt.py localize outputs/phase2a/human-acceptance-001/accepted/verified-clues.json --references outputs/phase2b/county-reference-next/references.json --settings config/geographic-ranking.json --output outputs/phase2b/county-c7-c8-next
```

Reuse the existing accepted snapshot. No repeated clue approval is required.
New clue exports can be produced with the existing `clues-export --analyst-only`
workflow if references later expand; do not replace previous snapshots.

Without county data, omit `--references` to produce a readiness report with
accepted sheet evidence, cross-sheet comparisons and **no fabricated candidates**:

```powershell
& $pythonExe scripts/run_asbuilt.py localize outputs/phase2a/human-acceptance-001/accepted/verified-clues.json --output outputs/phase2b/c7-c8-readiness-next
```

Current C7/C8 have one accepted street label each and no subdivision/parcel/lot
clues. `NC 211 - SUPPLY ROAD` must match a real mapped name/alias; the engine does
not discard the route number or invent a composite alias. A road-only match can
show corridor candidates but remains insufficient to establish a drawing area.
Project names, cemetery/storage landmarks, sheet IDs, station ranges and survey
coordinates stay sheet context in this version. Address and administrative layers
can use newly accepted typed clues, but C7/C8 currently have none. To corroborate actual locations,
add independently reviewed second-road/subdivision/parcel clues where supported by
the drawings, or separately scope an authoritative landmark-layer adapter. Do not
invent extra clues. County landmark reference locations would be useful for the
cemetery/storage labels but are not yet a supported reference dataset kind.

## Ranking and output interpretation

Street normalization handles case, punctuation, common suffixes and directionals.
Aliases are explicit reference data. Fuzzy matching uses Python `SequenceMatcher`
with default threshold 0.86 and minimum five-character labels. Numeric tokens,
directional qualifiers and differing known road suffixes are guarded. Parcel/lot
identifiers match exactly after conservative case/whitespace normalization; lot
prefix `LOT` is optional. Numbers/punctuation are not fuzzy-corrected.

Each unique accepted `(kind, normalized text)` group contributes at most once.
Repeated road aliases resolving to the same feature set cannot corroborate each
other. Exact street/subdivision matches contribute 30 points, parcel IDs 40,
addresses 35 and lots 18. Municipal/township/postal clues contribute 6/4/4 supporting
points; they cannot seed a candidate or independently qualify a single-street area.
Derived administrative overlaps have zero points and are recorded separately as
`spatial_context`, without inventing verified drawing clues. Normalized matches
use a 0.93 multiplier and approximate name matches
use `0.65 * similarity`. Multiple independent groups at a shared reference
area/neighborhood add 10; two distinct named road geometries crossing add 20.
A conflicting group matching elsewhere deducts 12; an unmatched group deducts 6.
All policy/settings and per-candidate contributions are saved, not represented
as statistical probabilities.

Candidates use reference-feature extents or 75-m default neighborhoods of geometric
road crossings. Geometry checks include polygon holes, containment, segment
crossings and distances. Different known road levels suppress intersection seeds;
equal or missing levels do not prove connectivity. Lot corroboration with a parcel
ID must refer to the **same parcel feature**, not a neighboring parcel. Long roads
can still yield broad corridors; no drawing footprint or survey registration is
inferred. Alternate anchors for identical evidence are consolidated; distinct
crossing neighborhoods survive.

At least two independent primary matching groups, an exact parcel identifier,
or an exact/normalized complete address are
needed for a qualified candidate, with default area diagonal <=5 km. A top score
gap below 10, unresolved conflicts/missing clues, broad-label safety limits or
partial import produces ambiguity. A single street, no matches or overbroad area
produces insufficient evidence. Configurable caps (200 matches per clue / 2,000
seeds) are explicit; truncated/broad searches cannot yield a definitive proposal.
The implementation is a small exhaustive search, not a countywide spatial index;
record runtime/coverage before larger deployment.

Outputs:

- `localization.json`: complete per-sheet accepted evidence/history, source PDF
  hash, candidate ranks/IDs, native reference IDs, scoring, CRS, limitations,
  cross-sheet labels, input and implementation hashes, reference provenance.
- `drawings.csv`: one row per sheet, including sheets with zero candidates.
- `candidates.csv`: one row per proposed/weak candidate, with evidence JSON cells.
  Zero candidates yields a header-only file, not a fabricated null location.
- `REVIEW.html`: offline schematic maps and evidence inspection.
- `clues-input.json`, optional `references-input.json`: byte-preserved snapshots.
- `evaluation-template.json`: separate **geographic** review tasks, initially null.
- `localization.log`: per-sheet processing outcome. `geo-import` separately writes
  `references.json`, `datasets.csv` and `import.log`.

Reference-feature extents are not measured uncertainty intervals. Neighborhood
radii and size limits are pilot search parameters. Cross-sheet shared labels are
reported with each sheet's clue IDs; no candidate, score or acceptance is pooled
because of filenames, numbering or shared project context.

## Independent geographic evaluation

Clue transcription acceptance is complete; **geographic-area acceptance is a new
and separate task**. In an independent GIS review, establish correct areas from
authoritative references and source drawings before inspecting rankings where
practical. Keep related sheets in the same evaluation group.

Copy `evaluation-template.json` to a new decision file. For each sheet fill reviewer,
`reviewer_type: "human"`, `independent_review: true`, timezone-qualified `reviewed_at`,
reason, and `truth_status`: `localizable`, `insufficient_reference`, or
`ambiguous_truth`. Localizable truth requires `correct_areas` objects with
`bbox: [west,south,east,north]`, `crs: "EPSG:4326"`, and an independent `source`
(reference IDs/method, not a copied predicted box). Classify **every** candidate
`correct`, `false_match`, or `ambiguous`, then set `complete_candidate_review: true`.
Candidate correctness is the analyst's area judgment; bbox overlap is not
automatically equated to success, particularly for broad corridors.

```powershell
& $pythonExe scripts/run_asbuilt.py localization-evaluate outputs/phase2b/county-c7-c8-next/localization.json outputs/phase2b/county-geographic-review-next.json --output outputs/phase2b/county-evaluation-next
```

The frozen run hash must agree. Incomplete, AI or unaffirmed evaluations stay
pending; no-reference runs cannot produce measured geographic success. Reports
include correct-area-in-candidates, best correct rank, top-1/3/5 recall for
localizable sheets, false-match counts, ambiguous candidates/results, insufficient
evidence results and pending denominators. Metrics use independently classified
candidates, never ranking scores as truth. These are local attestations, not
authenticated signatures; synthetic test reviews remain clearly fictional.

`generated_results` reports algorithm statuses before area review;
`metric_status` distinguishes pending, partially reviewed and reviewed outcomes.
Truth-dependent metrics use only independent geographic decisions. With no
candidate, establish a correct area independently before calling the run a miss.
Empty reference results and zero reviewed false matches are not accuracy claims.

Expand beyond C7/C8 to unrelated projects, including ambiguous names, missing
coverage, negative drawings and difficult scans. Freeze reference exports, run
settings, inputs and decisions per evaluation. No real-world localization accuracy
claim is justified until county data and independent area checks are complete.
