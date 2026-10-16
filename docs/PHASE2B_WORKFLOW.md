# Phase 2B: read-only geographic localization

This prototype ranks geographic **areas**, not utility assets. It reads frozen local
GeoJSON and existing accepted clue exports. All candidate decisions start pending.
It never edits clue registries, connects to SDE, calls ArcPy, or downloads maps.
The existing human approvals remain valid and unchanged.

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

For useful parcel/lot matching, include their corresponding optional fields.
Missing optional mappings disable that matching capability. An unmapped address is
not guessed from other fields. Addresses are preserved as context; the existing
clue schema has no address clue kind, so address matching is not implemented.
No facility IDs, utility geometry or SDE credentials are requested.

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

The kernel uses a local spherical approximation for metre-based proximity only;
geographic output stays WGS84. It limits aggregate reference extent to 250 km,
latitude to +/-80 degrees, and rejects global/antimeridian geometry. This is suitable
for a county feasibility search, not StatePlane survey measurements. CRS labels
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
coordinates stay sheet context in this version. To corroborate actual locations,
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
other. Exact street/subdivision matches contribute 30 points, parcel IDs 40 and
lots 18; normalized matches use a 0.93 multiplier and approximate name matches
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

At least two independent matching groups, or an exact parcel identifier, are
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

Expand beyond C7/C8 to unrelated projects, including ambiguous names, missing
coverage, negative drawings and difficult scans. Freeze reference exports, run
settings, inputs and decisions per evaluation. No real-world localization accuracy
claim is justified until county data and independent area checks are complete.
