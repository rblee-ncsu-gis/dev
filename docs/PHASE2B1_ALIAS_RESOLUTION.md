# Phase 2B.1: road alias resolution and candidate recovery

Assessment date: October 19, 2026.

## Management result

C7 and C8 each recover **one road-corridor candidate**, compared with zero
candidates in the initial county run. Each candidate contains the same 94
Southport-Supply Road reference segments, approximately **24.00 km of linework**.
The score is **25.5 ranking points**, not a probability. Each sheet remains
independently reviewable; no drawing footprint or exact position is established.

The fix is an opt-in, source-corroborated, geographically scoped alias registry.
It preserves `NC 211 - SUPPLY ROAD` exactly as accepted and interprets it only
within a documented county road-name/route subset. Alias evidence is not labeled
human-approved. All eleven clue approvals, their histories, original source
exports, reference metadata and initial zero-candidate results remain unchanged.

No independent geographic reference has been supplied, so **Top-1/Top-3
localization accuracy remains unmeasured**. Rank 1 in a recovered candidate list
does not establish that the drawing is correctly located. Utility asset matching
and SDE modification remain outside scope. No packages or environment settings changed.

## Diagnosis using actual county attributes

The approved road import maps `GlobalID` to native identity and `FULLNAME` to the
official reference label. No route/alias field had been enabled for matching.
Inspection used actual `FULLNAME`, `NAME`, `PREFIX`, `TYPE`, `SUFFIX`, and
`STATERDNUM` values. No alternate/historical-name field was asserted to exist.

| Actual FULLNAME | STATERDNUM | Features |
| --- | --- | ---: |
| SOUTHPORT-SUPPLY RD SE | 211 | 75 |
| SOUTHPORT-SUPPLY RD | 211 | 19 |
| N HOWE ST | 211 | 32 |
| E MOORE ST | 211 | 24 |
| GREEN SWAMP RD | 211 | 18 |
| FERRY RD SE | 211 | 3 |
| SUPPLY ST SE | null | 4 |

There are **171** route-field values equal to `211`. Only **94** also have one
of the two Southport-Supply official names. The other **77** route-211 segments
remain in the catalog but are outside this alias's geographic/name scope.
SUPPLY ST SE is not treated as Supply Road. A total of 175 diagnostic search
features includes those four unrelated-suffix features, visibly labeled as
inspection findings rather than matches.

For the selected 94, actual component values include `NAME=SOUTHPORT-SUPPLY`,
`TYPE=RD`, `PREFIX=null`, `SUFFIX=SE` or null; all have `STATUS=BUILT`. This inspection
does not change previously approved full-name mappings or infer that TYPE/SUFFIX
have the same meaning in other datasets.

The original whole-label comparison failed for three reasons:

1. `FULLNAME` has no `211` token. The strict numeric guard intentionally prevented
   fuzzy matching a route-bearing clue to a name lacking its number.
2. Expanding abbreviations/punctuation alone cannot supply the omitted SOUTHPORT
   component, relate a route to a name, or resolve the SE directional variant.
3. A single matched street did not previously have a distinct corridor output mode.
   Multiple apparent segment extents must not become falsely precise drawing areas.

The correct response was a scoped reference interpretation and a coarser candidate
level, rather than lowering fuzzy thresholds or removing numeric/directional guards.

The diagnostic artifacts retain **every matching source value, source field,
native ID and corresponding original geometry**:

- [Diagnostic report](../outputs/phase2b1/road-diagnostics-001/REPORT.md)
- [Source values CSV](../outputs/phase2b1/road-diagnostics-001/source-values.csv)
- [Related-road geometries](../outputs/phase2b1/road-diagnostics-001/related-roads.geojson)
- [Unnamed-road evidence](../outputs/phase2b1/road-diagnostics-001/unnamed-roads.geojson)
- [Alias validation facts](../outputs/phase2b1/road-diagnostics-001/alias-validation.json)

## Authoritative support and controlled interpretation

County meeting records associate Southport-Supply Road with NC 211.
[Brunswick County Board of Adjustment minutes, April 8, 2021](https://www.brunswickcountync.gov/Archive/ViewFile/Item/1882).
NCDOT publications independently connect the route and road names in the Brunswick
County corridor, including the southeastern directional form.
[NCDOT June 2026 notice](https://www.ncdot.gov/news/press-releases/Pages/2026/2026-06-17-nc211-construction-temporary-closures-brunswick-co.aspx),
[NCDOT US 17 / NC 211 interchange information](https://www.ncdot.gov/news/public-meetings/Pages/U-5932-2019-05-16.aspx).
These publications support a name/route relationship; they do not locate either
drawing or establish historical drawing-era centerline geometry.

Combined with the actual county attributes and source linework, this supports a
**candidate** interpretation of the full drawing label. The shortened Supply Road
wording is not promoted into a universal or independently approved historical alias.

[config/road-aliases.brunswick.json](../config/road-aliases.brunswick.json) records:

- Separate categories for official names, route numbers, historical names,
  abbreviations, analyst-approved aliases and candidate relationships.
- Explicit labels, including `NC 211 - SUPPLY ROAD`, `NC 211`, and
  `NC HIGHWAY 211`; no unrestricted SUPPLY, ROAD or SUPPLY ROAD entry.
- `source_corroborated` status, publication sources, and no analyst approval.
  Historical-name and analyst-approved-alias lists remain empty.
- The exact county road source SHA-256, dataset ID, all 94 native feature IDs,
  a geographic bbox, and **both** `FULLNAME` and `STATERDNUM` constraints.

An alias is used only when its literal normalized label and all source constraints
agree. A changed source hash, missing feature, conflicting field value or out-of-scope
geometry stops application. Normal exact/normalized/fuzzy matching remains separate;
`scoped_alias` evidence retains the alias ID, label/category, sources, status and
actual source field values. No transitive or fuzzy word equivalence is introduced.
Registry loading is opt-in through `--aliases`; omitting it preserves the strict
baseline behavior. A human-approved alias status requires a separate human review
record and is never inferred from existing clue acceptance.

The route-only labels also refer only to this **named subcorridor**, not all 171
county route segments or the statewide NC 211 route. Any broader registry entry
requires its own validated scope. This explicit limit avoids equating Howe Street,
Moore Street, Green Swamp Road or Ferry Road with the drawing's shortened road label.

## Corridor method and resolution levels

Road line parts are grouped by endpoint proximity in the existing WGS84 local
metre projection. The default endpoint gap is **5 m**, configurable as
`corridor_gap_m`. Disconnected components remain distinct alternatives. Different
known levels suppress joining; missing levels do not prove at-grade connectivity.
The source linework is preserved as MultiLineString parts. No dissolve, geometry
repair, corridor buffer, gap connector or drawing registration is invented.

Repeated labels for the same component are consolidated without increasing score.
Additional independently accepted streets, subdivisions, parcels or addresses can
still drive the existing area/intersection ranking. Broad-corridor overlaps are
recorded separately from narrowed area evidence. Conflicting and missing evidence
remain explicit. No new location clues were fabricated for these two drawings.

| Level | What the current result supports |
| --- | --- |
| Geographic name recognized | Yes, through the scoped source relationship |
| Roadway/route subset matched | Yes, 94 reference segments |
| Candidate drawing area narrowed | No; corridor only |
| Drawing footprint accurately localized | No; independent evidence required |

Corridor candidates always have `qualified=false` for drawing-area purposes,
`localization_level=road_corridor`, and pending analyst review. A single component
yields `corridor_identified`; multiple/conflicting components yield
`ambiguous_corridors`. Candidate-area generation and footprint verification are
separate fields. Unrelated words and unsupported landmark/project labels do not
become extra spatial evidence.

## Independent C7 and C8 results

| Drawing | Accepted clues retained | Baseline candidates | Recovered candidates | Rank | Score | Result / review |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| s07772.pdf / C7 | 5 | 0 | 1 | 1 | 25.5 | corridor_identified / pending |
| s07773.pdf / C8 | 6 | 0 | 1 | 1 | 25.5 | corridor_identified / pending |

Both use their own accepted street clue and preserve every sheet-specific source
ID, PDF hash, bounding box and correction history. The score is `30 * 0.85` for
one scoped-alias clue group. No independent-group or intersection bonus is added.
No scored conflicting localizing clue was found; this does not establish the
absence of conflicts in the drawing or corroborate its exact geographic placement.

Each recovered component contains **94 line parts / 94 source features** with
approximately **24,004.45 m** of reference linework. Its WGS84 bbox is approximately
`[-78.273088, 33.946671, -78.032675, 34.017215]` (west, south, east, north).
That box encloses a long roadway and unrelated intervening areas. It is **not a
drawing footprint, positional estimate or uncertainty interval**. Linework length
can include overlapping/parallel reference geometry; it is not measured plan coverage.

C7/C8 share the recovered reference corridor and their accepted street, project
and cemetery labels. Their document-specific candidate IDs remain different.
Shared corridor evidence does not establish the same location along that corridor,
adjacency, a common plan-set edition or identical drawing footprints. C8's storage
landmark and the shared cemetery still need appropriate independent reference data.

Final artifacts:

- [Frozen Phase 2B.1 run](../outputs/phase2b1/county-c7-c8-003/localization.json)
- [Drawings CSV](../outputs/phase2b1/county-c7-c8-003/drawings.csv), [candidates CSV](../outputs/phase2b1/county-c7-c8-003/candidates.csv)
- [Offline geographic review](../outputs/phase2b1/county-c7-c8-003/REVIEW.html)
- [Baseline comparison JSON](../outputs/phase2b1/comparison-002/comparison.json), [CSV](../outputs/phase2b1/comparison-002/comparison.csv)
- [Unchanged initial zero-candidate run](../outputs/phase2b/county-c7-c8-001/localization.json)

The CSV summarizes corridor geometry and alias evidence, with a JSON-pointer
reference to full candidate details. Complete source linework and every alias
match remain in JSON; they are not placed in oversized CSV cells. Earlier recovery
snapshots are retained, and the final report uses the compact-CSV run above.

## Independent geographic reference workflow

Reuse the existing `evaluation-template.json`; no additional clue registry or
approval process is introduced. Correct geographic references start empty. Fill
each sheet independently from an analyst investigation that does not use the
algorithm's first candidate as its source of truth.

In `correct_locations`, supply `kind: area`, `intersection`, `control_point`, or
`footprint`, with WGS84 GeoJSON `geometry`, `crs: EPSG:4326`, an independent `source`,
and `independently_determined: true`. Areas/footprints accept Polygon/MultiPolygon.
Intersections/control points accept Point and require a positive `accuracy_m`.
Record reviewer, human reviewer type, independence, timestamp and reason using
the existing fields. Legacy `correct_areas` bounding-box references remain supported.
StatePlane measurements require an independently documented conversion before
entry; the prototype does not transform EPSG:2264 control coordinates.

Set `evaluation_scope: corridor_recovery` when judging these corridor candidates.
The evaluator rejects a correct corridor decision labeled as precise
`geographic_localization`. Corridor recovery is reported separately from
localization Top-1/Top-3 denominators. A later narrowed-area run can use
`geographic_localization` once independent references and candidate decisions
support that level. Candidate correctness remains an analyst decision; bbox
overlap alone is not accepted as proof.

Until then, both geographic reviews remain pending and accuracy metrics are null.
The independent reference can be recorded now without approving the algorithm.
Do not overwrite the frozen run when recording decisions or testing refinements.

## Commands

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
& $pythonExe scripts/run_asbuilt.py roads-diagnose reference/brunswick_county/roads.geojson --output outputs/phase2b1/road-diagnostics-next
& $pythonExe scripts/run_asbuilt.py localize outputs/phase2a/human-acceptance-001/accepted/verified-clues.json --references outputs/phase2b/county-reference-001/references.json --aliases config/road-aliases.brunswick.json --settings config/geographic-ranking.json --output outputs/phase2b1/county-c7-c8-next
& $pythonExe scripts/run_asbuilt.py localization-evaluate outputs/phase2b1/county-c7-c8-next/localization.json outputs/phase2b1/independent-review-next.json --output outputs/phase2b1/evaluation-next
```

Use a new output directory and a separately filled evaluation decision file.
Source exports are never rewritten. When a source hash changes, diagnose and
revalidate the alias scope; do not simply replace its hash to force reuse.

## Reference quality and verification

The existing **1,317 invalid parcel geometries**, **one invalid postal geometry**
and **509 unnamed import exclusions** are retained unchanged. Of the unnamed
features, **2 are roads** and **507 are subdivisions**. Both unnamed roads have
null STATERDNUM: one has `NAME=PRIVATE` and planned status; the other has
`NAME=SE 31ST STREET SCENIC WALKWAY` and built status. Their IDs and geometries are
in the diagnostic export. Neither supplies a usable route identifier for NC 211.
Neither was silently restored or reinterpreted; no new source features were discarded.
These unrelated repairs remain deferred.

All **176 tests pass**, preserving the previous 159 and adding 17 alias/corridor
tests. Tests cover scoped provenance, stale snapshots, field/geometry constraints,
generic-alias rejection, disconnected and conflicting corridors, repeated aliases,
source preservation, all four independent reference types, compact CSV with complete
JSON evidence, and the guard against scoring corridor recovery as drawing localization.

See [validation and audit checks](../outputs/phase2b1/validation.json). The next
milestone is independent reference collection plus a focused narrowing experiment
using verified landmark/intersection/control evidence. Expand to unrelated drawings
before assessing production accuracy. Utility detection and PDF-to-asset linking
remain deferred.
