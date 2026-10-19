# Phase 2B.2: Landmark-based corridor narrowing

Assessment date: October 19, 2026. Read-only C7/C8 pilot.

## Management assessment

The landmarks identify a useful **shared review locality**: one existing 371.19 m
Southport-Supply Road SE segment, compared with the original 94 segments and
24,004.45 m of linework. The retained linework is approximately 1.55% of the
original corridor. This is a smaller inspection target, **not** measured accuracy,
a drawing footprint, or a boundary guaranteed to contain either sheet.

The evidence does **not yet establish separate geographic extents for C7 and C8**.
Accepted station ranges, reciprocal matchline labels and visual plan evidence
support consecutive alignment sections. C7 likely approaches the common locality
and C8 continues past it. Exact geographic endpoints and full sheet coverage remain
unresolved. Both geographic reviews are pending; localization accuracy is unmeasured.

Recommendation: independently establish sheet-specific controls and reference areas
in this locality before fitting a geographic transform or attempting utility matching.

## Sourced landmark investigation

Here, independently sourced means outside the drawing, not independently accepted
drawing ground truth. All 11 previously accepted drawing clues remain unchanged.

### Cape Fear Memorial Park

Page 2 of the county-authored inventory, last updated December 9, 2019, confirms
latitude 33.9549422, longitude -78.063653 and Southport-Supply Road SE. The row and
column headings were checked against the published PDF. Its `EXACT` category is
not a numerical accuracy statement. The publication does not explicitly declare
a datum; WGS84 interpretation follows the user's supplied lead and remains a
source limitation. [County GIS cemetery inventory, hosted by Interment.net](https://www.interment.net/data/us/nc/brunswick/cemeteries-brunswick-county-north-carolina.pdf).

The point lies inside parcel `2200002503`, PIN `208710358303`, GlobalID
`{0CAF7CB8-EA58-4C00-B688-7C7C16B8745B}`. This corroborates a locality, not
ownership, cemetery boundaries, an entrance or a drawing footprint. Its computed
minimum corridor distance is **118.62 m**. An interior landmark point can be well
away from a road; this offset is not a registration residual or source error.

### Sentry Self Storage

The official contact section confirms 4711 Southport-Supply Rd SE, Southport,
NC 28461. No publication date or coordinate is supplied.
[Sentry Self Storage official site](https://www.sentryselfstoragenc.net/).

An exact county lookup using `ST_NUMB=4711`, `ST_NAME=SOUTHPORT-SUPPLY RD SE`,
and `POSTAL=SOUTHPORT` found **11 points**: the unsuffixed address and units A-J.
Other streets with house number 4711 were excluded by their actual attributes.
Units F and G have explicit Sentry storage comments. All unit candidates, native
IDs, attributes and geometries are retained. No centroid or geocoded coordinate
was invented, and units do not count as independent landmarks.

The unsuffixed address, GlobalID `{3A5F419B-8B28-4F56-9C5B-FB027F3544DA}`, is
at `[-78.06169784969501, 33.955139872116064]`, **48.13 m** from the corridor.
Unit distances range from **119.40 m to 449.29 m**. These are candidates within
a deeper site, not interchangeable frontage/control points.

Ten points lie in parcel `22100064`, PIN `208714440973`, GlobalID
`{BD6E5A79-31EA-41C6-AE77-C924A2DDB705}`. Unit H lies in `2210006401`, PIN
`208710451597`, GlobalID `{574927D4-BCC1-482C-92D9-307646B50560}`. These
are containing parcels, not an approved facility outline. The parcel export has
no owner/business-name field to confirm occupancy. This read-only diagnostic does
not approve general parcel field mappings.

## Actual results

| Drawing | Landmark identities | Preserved original | Separate review locality | Ranking points | Review |
| --- | --- | --- | --- | ---: | --- |
| s07772.pdf / C7 | Cemetery | 94 parts; 24,004.45 m | 1 part; 371.19 m | 35.5 | Pending |
| s07773.pdf / C8 | Cemetery and Sentry | 94 parts; 24,004.45 m | 1 part; 371.19 m | 45.5 | Pending |

Both select road GlobalID `{9B40EA86-5075-47D2-83D2-229EB104F47C}`, original
corridor line-part index 60 (zero based), with bbox approximately
`[-78.063994, 33.955219, -78.060132, 33.956135]` in longitude/latitude.
Full coordinates, native lineage and source hashes remain in JSON.

Original candidates are retained verbatim in `candidates`, including IDs, ranks,
geometry and 25.5-point scores. `narrowed_candidates` ranks separately and adds
10 points per distinct source-corroborated landmark identity. Repeated units and
labels add no points. Cross-sheet stationing adds zero points. Scores express
deterministic review priority, not probability, positional accuracy or approval.

No configured spatial conflicts or missing landmark references were found. The
maximum C8 anchor spread is **404.94 m**. These checks do not establish historical
identity, validate every unit or remove the uncertainties below.

## Implementation and spatial safeguards

`landmarks-import` provides an optional supplemental interface alongside the
existing seven-layer catalog. It reuses streaming GeoJSON, geometry validation,
hashing and report utilities. It does not require an eighth county export or
duplicate clue review. The config/inventory retain name, type, explicit aliases,
source/access dates, address or coordinate, accuracy where known, verification
status, unit points and containing parcels. Unknown accuracy is null. The status
`source_corroborated` cannot grant analyst acceptance.

`corridor-narrow` consumes frozen corridor and landmark inventories. Literal
normalized landmark matching uses only independently accepted drawing clues.
Address-only references without coordinates remain unresolved. AI transcriptions
cannot supply landmark or station-range evidence.

Distances use the parent run's bounded **WGS84 ellipsoid local east/north metre
projection**. Outputs remain EPSG:4326. No EPSG:2264 conversion or ArcGIS operation
is performed. Computed centimetre rounding is not a source accuracy claim.

For every matched point, the algorithm finds the nearest original corridor line
parts. Their union becomes a review locality only when it reduces the linework.
Ties within 0.5 m are retained. Default conflict checks reject points over 1,000 m
from the corridor or anchor spreads over 2,000 m. These configurable search policies
are not measurement tolerances. Conflicting or ambiguous references suppress
narrowing; missing evidence stays explicit.

The method preserves whole source line parts. It creates no buffer, artificial
connector, station-based clipping, footprint or drawing overlay. Source road
segmentation controls the extent. The locality **cannot guarantee full drawing
coverage**, especially C7's approach to the common landmark. Its bbox is a display
extent, not an uncertainty interval.

Native lineage requires the original road snapshot hash, identical coordinates
and an ID already in the parent candidate. Missing/stale exports leave lineage
incomplete rather than assigning replacement IDs.

## Stationing and source drawing inspection

Accepted ranges are C7 `STA. 66+50 TO STA. 78+75` and C8
`STA. 78+75 TO STA. 90+25`. They share station 78+75. Numeric spans are 1,225
and 1,150 **station units**; neither has been assigned an exact geographic length.

AI inspection of composition-correct plan images found:

- Reciprocal C7/C8 matchline labels at C7's right and C8's left side. Station
  78+75 comes from accepted title ranges, not a numerical matchline transcription.
- Increasing station labels left to right, repeated FM linework and a station
  78+46 anti-seepage collar near the common ends.
- Graphic scales in feet, with one inch representing 40 feet. This supports plan
  scale interpretation, but does not independently establish station units,
  equations, origin or an exact station-to-ground convention.
- Similar north arrows, suggesting left-to-right is approximately east-southeast.
  This is qualitative inspection, not an azimuth or transform fit.
- Cemetery labels near C7's right and C8's left; storage labels farther right in
  C8. C8 also labels a 16-inch PVC force main.

Six focused crops retain PDF/page hashes, source bboxes, image hashes and pixel
mapping, and are copied into the offline review. These are **AI observations,
independent analyst acceptance pending**, stored separately from approved clues.
Some plan detail extends beyond title station limits; page boundaries do not
establish exact alignment endpoints.

The relationship is recorded as source inspection supporting consecutive alignment
sections, C7 before C8. No geographic endpoint, length, score or approval transfers
between sheets. Distinct sheet extents remain an analyst task.

## Limitations and unresolved questions

The supplemental import scanned **165,966 address features** and **169,265 parcel
features**. Seven parcel envelopes overlapped candidate points and received
detailed validation; none was invalid. The existing **1,317 parcels without
computable bounds** were skipped unchanged. This targeted check does not certify
all parcel geometry. Prior postal/unnamed-feature exclusions remain unchanged.

Export dates, original datum/version metadata and numerical landmark accuracy
remain unknown. The cemetery inventory is from 2019; the business website is
undated and some address edits are much newer than the drawing evidence. The
publication facts were checked through web access. An optional shell attempt to
archive publication bytes encountered refused network connections, recorded in
`source-publications-001/manifest.json`. No remote publication hash or offline copy
is claimed.

The analyst still needs to determine:

1. Whether current facility/parcel relationships match the drawing-era sites, and
   which entrances/frontage points are recognizable on both drawings and GIS.
2. The geographic position of station 78+75 and the documented origin, station
   units and any equations elsewhere in the plan set.
3. Independent controls and a reference area for each sheet, including C7 coverage
   outside this shared anchor locality.
4. Whether current road geometry represents the older alignment adequately, or
   historical road/imagery evidence is needed.

## Artifacts and commands

- [Source configuration](../config/landmarks.brunswick.json).
- [Supplemental JSON](../outputs/phase2b2/landmark-references-002/landmarks.json),
  [CSV](../outputs/phase2b2/landmark-references-002/landmarks.csv),
  [point GeoJSON](../outputs/phase2b2/landmark-references-002/landmark-points.geojson).
- [Candidate JSON](../outputs/phase2b2/county-c7-c8-002/localization.json),
  [candidate CSV](../outputs/phase2b2/county-c7-c8-002/candidates.csv),
  [drawing CSV](../outputs/phase2b2/county-c7-c8-002/drawings.csv),
  [distances](../outputs/phase2b2/county-c7-c8-002/landmark-distances.csv).
- [Offline review](../outputs/phase2b2/county-c7-c8-002/REVIEW.html), including
  original/local maps, landmarks, parcel context, provenance and source crops.
- [Pending observations](../data/reference/supplemental/c7-c8-source-observations.json),
  [crop manifest](../outputs/phase2b2/source-inspection-001/manifest.json).
- [Independent evaluation template](../outputs/phase2b2/county-c7-c8-002/evaluation-template.json),
  [pending evaluation](../outputs/phase2b2/evaluation-002/evaluation.json),
  [preservation/validation audit](../outputs/phase2b2/validation.json).

From the repository root, use unused output directories:

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
& $pythonExe scripts/run_asbuilt.py landmarks-import config/landmarks.brunswick.json --output outputs/phase2b2/landmark-references-next
& $pythonExe scripts/run_asbuilt.py corridor-narrow outputs/phase2b1/county-c7-c8-003/localization.json --landmarks outputs/phase2b2/landmark-references-next/landmarks.json --observations data/reference/supplemental/c7-c8-source-observations.json --output outputs/phase2b2/county-c7-c8-next
```

Optional `--settings` accepts positive metre values `maximum_landmark_offset_m`,
`maximum_anchor_spread_m`, and `nearest_tie_m`. Omitting `--observations` still
runs narrowing and reports title-range continuity as a hypothesis, without
source-inspected matchline support.

Copy the new evaluation template to a separate analyst decision file; preserve
frozen results/templates. Reuse `localization-evaluate`, its hash-bound human
review declarations, and independently established `correct_locations` or legacy
`correct_areas`. All four candidates (two per drawing) require decisions.
Review these coarse localities/corridors under `evaluation_scope: corridor_recovery`.
The evaluator rejects them as geographic-localization hits, and rejects a copied
landmark input point as independent drawing truth. Provenance and independent
declarations remain essential; geometry checks alone cannot prove independence.

```powershell
& $pythonExe scripts/run_asbuilt.py localization-evaluate outputs/phase2b2/county-c7-c8-next/localization.json outputs/phase2b2/independent-review-next.json --output outputs/phase2b2/evaluation-next
```

There are zero independently reviewed locations and two pending drawings.
Top-1/Top-3/Top-5 recall is null. Zero reviewed false matches is an empty denominator,
not perfect precision. Landmark model inputs cannot supply drawing ground truth.

## Validation and next milestone

**207 tests pass**: the existing 176 plus 31 new cases for literal matching,
invalid/swapped coordinates, provenance, unknown accuracy, multiple units, parcel
containment, stale hashes, missing/conflicting references, nearest ties, unforced
narrowing, exact lineage, station continuity, AI exclusion, CSV/HTML output and
independent-evaluation safeguards.

The preservation audit checks 25 protected artifacts, including all seven exports,
original zero-candidate outputs, accepted clues/registries, the alias registry and
the prior corridor package. No dependencies, environment settings, ArcPy/SDE
connections or utility asset changes were introduced.

The next milestone is **independent control and sheet-extent collection**: review
the crops, validate drawing-era identity, establish the matchline and additional
controls independently, and record a separate reference area for each sheet.
Then test a limited placement model using held-out checkpoints. Expand beyond
these two related sheets before reporting general performance.
