# Phase 2B: authoritative county integration and C7/C8 validation

Assessment date: October 19, 2026.

## Management summary

All seven supplied county exports have been inspected. The analyst confirmed
WGS84 longitude/latitude for all seven and approved the initial road, subdivision
and address mappings. Those layers yielded **310,386 usable reference features**.
The first real county localization run completed for C7 and C8: **both returned
zero candidates and `insufficient_evidence`**. This is an observed generation
outcome, not an independently measured geographic accuracy result.

The principal immediate gap is the street label: accepted `NC 211 - SUPPLY ROAD`
does not match the approved county `FULLNAME` values. Related county names include
`SOUTHPORT-SUPPLY RD SE`; the engine does not silently discard route numbers or
declare a historical alias. The drawings supply no accepted subdivision, parcel,
address or administrative-name clues to corroborate the street. Landmark/project
labels remain context without a supported authoritative landmark reference.

Resolve the road-label/route relationship and establish independent correct-area
references before changing matching thresholds or advancing to utility assets.
All eleven clue acceptances, original transcriptions, corrections and histories
are unchanged. No dependencies, Python environment settings or SDE records changed.

## Source files and metadata

The supplied files reside in `reference/brunswick_county/`. They are read in place;
no source file was moved, rewritten or repaired. The requested canonical manifest
is [data/reference/brunswick_county/export_metadata.json](../data/reference/brunswick_county/export_metadata.json).
Validation supports both the requested directory and an explicitly supplied source
directory, so future exports can arrive incrementally without copying these files.
Raw GeoJSON files are excluded from Git; local processing artifacts remain local.

| Dataset | Features | Observed geometry | Geometry-validation errors | Current mapping status |
| --- | ---: | --- | ---: | --- |
| Roads | 21,166 | LineString | 0 | GlobalID / FULLNAME approved |
| Subdivisions | 123,763 | Polygon, MultiPolygon | 0 | GlobalID / SubdivisionName approved |
| Parcels | 169,265 | Polygon, MultiPolygon | 1,317 | Pending; PIN versus PARCEL_ID needs a decision |
| Addresses | 165,966 | Point | 0 | GlobalID / ST_ADDR approved |
| Town limits | 26 | Polygon, MultiPolygon | 0 | Pending; no obvious municipal-name field |
| Townships | 6 | Polygon | 0 | Pending; TOWNNAME is proposed |
| Postal zones | 15 | Polygon, MultiPolygon | 1 | Pending; ZipCode is proposed |
| Total | 480,207 | | 1,318 | |

Parcel errors include empty geometries. The postal-zone error at zero-based feature
index 3 is a ring with too few positions. No repair was attempted. Invalid parcel
and postal datasets remain outside the approved initial import. Missing datasets
are not errors; this delivery happens to include all seven.

The manifest records file paths, exact sizes and SHA-256 hashes, complete feature
counts, geometry types, valid-geometry extents, actual field names/types, per-field
present/null/blank/missing counts, candidate-ID uniqueness, bounded error examples
and complete error totals. `extent` covers geometries that passed validation;
invalid geometries are not assigned invented geographic extents. Detailed schema
and attribute quality are in [fields.csv](../outputs/phase2b/county-readiness-003/fields.csv).

Latest validation compared source hashes, schemas, feature counts and geometry
types against the prior inventory and found **no source changes**. Previous
manifests remain in `metadata_history/`; the first scan and each readiness snapshot
are retained separately. The aggregate validation exit code remains 1 because of
the two invalid optional datasets, while the confirmed configuration explicitly
permits the three ready datasets to be imported.

## Coordinate and provenance decisions

The GeoJSON files contain no explicit CRS declarations. WGS84-compatible numeric
ranges were recorded as compatibility evidence only. On October 19 the analyst
explicitly confirmed **all seven exports use WGS84 / EPSG:4326, longitude first**.
That confirmation is bound to each file hash in
[the recorded decisions](../outputs/phase2b/county-analyst-decisions-001/decisions.json).
Geometry errors do not erase that CRS attestation; they remain separate blockers
for clean feature use.

Original SDE feature-class names, original per-layer CRS, database version,
source export timestamps and data-owner metadata were **not supplied** and remain
null. General knowledge that county GIS uses EPSG:2264, file modification times
and filenames were not substituted for these source facts. The analyst can supply
them through `source_metadata` in a new decisions file.

Distance comparisons now use a WGS84 ellipsoidal local east/north tangent-plane
projection, in metres, with the recorded catalog origin and a 250-km extent limit.
The implementation uses standard-library math; it adds no projection dependency.
It does not transform StatePlane source data or register a drawing. Geographic
report coordinates remain WGS84. The local frame is appropriate for county-scale
candidate proximity; it is not a survey-accuracy guarantee. Mathematical reference:
[PROJ topocentric coordinates](https://proj.org/en/stable/operations/conversions/topocentric.html).

## Approved schemas and actual import

| Layer | ID mapping | Label mapping | Imported | Rejected during import |
| --- | --- | --- | ---: | ---: |
| Roads | GlobalID | FULLNAME | 21,164 | 2 null road names |
| Subdivisions | GlobalID | SubdivisionName | 123,256 | 507 null subdivision names |
| Addresses | GlobalID | ST_ADDR | 165,966 | 0 |
| Total | | | 310,386 | 509 |

Each approved layer's GlobalID values are nonnull and unique in this snapshot.
The import is marked **partial** because unnamed features cannot provide label
matches. All exclusions and their source feature indices are retained in
[the import log](../outputs/phase2b/county-reference-001/import.log) and catalog.
An import exit code of 1 here means a retained partial result; it does not erase
the usable catalog. Partial reference coverage prevents definitive proposals.

Unconfirmed mappings were not substituted. Town limits expose TYPE/STATUS but no
obvious name attribute; those columns were not assumed to be municipal names.
Parcel PIN and PARCEL_ID both exist, with no supplied lot field. Proposed road
components, subdivision phases and historical aliases still need actual field
semantics before use. The approved full-name mappings avoid guessing TYPE/SUFFIX
meaning. The proposal/decision workflow is distinct from existing clue approval.

SubdivisionName has **6,231 nonblank distinct values** across 123,256 named
features. The export includes PARCEL_ID and repeated names; one name spans 917
polygons. This requires clarification of parcel-associated versus area-boundary
semantics. No dissolve or grouping was invented. Future high-cardinality names
can trigger the existing 200-feature safety cap and require an explicit region
grouping strategy, not an arbitrary threshold increase.

## Frozen real-world localization results

| Drawing | Accepted clues retained | Localizing clues | Road reference matches | Candidates | Algorithm outcome | Independent geographic outcome |
| --- | ---: | --- | ---: | ---: | --- | --- |
| s07772.pdf / C7 | 5 | NC 211 - SUPPLY ROAD | 0 | 0 | insufficient_evidence | Pending |
| s07773.pdf / C8 | 6 | NC 211 - SUPPLY ROAD | 0 | 0 | insufficient_evidence | Pending |

The original run, input hashes, reference snapshot, ranking configuration, source
PDF hashes, sheet evidence and implementation hashes remain frozen in
[county-c7-c8-001](../outputs/phase2b/county-c7-c8-001/localization.json).
No rankings were adjusted to fit an expected location. CSV outputs preserve both
zero-candidate sheets in [drawings.csv](../outputs/phase2b/county-c7-c8-001/drawings.csv);
[candidates.csv](../outputs/phase2b/county-c7-c8-001/candidates.csv) contains only its header.
The [offline geographic review](../outputs/phase2b/county-geographic-review-001/REVIEW.html)
adds matching diagnostics without modifying the frozen run or the original HTML.

Inspection of the confirmed road-name field found:

| Related county FULLNAME | Segments | Interpretation |
| --- | ---: | --- |
| SOUTHPORT-SUPPLY RD SE | 75 | Related text for analyst investigation only |
| SOUTHPORT-SUPPLY RD | 19 | Related text for analyst investigation only |
| SUPPLY ST SE | 4 | Different suffix; not assumed equivalent |

These are **not ranked candidates or accepted aliases**. Road IDs and source hash
are retained in [label diagnostics](../outputs/phase2b/county-label-diagnostics-001/diagnostics.json).
STATERDNUM exists but its semantics and a route/name relationship were not approved;
it was not used for matching. Numeric/directional/suffix guards remain active.
Neither the NC 211 route token nor SOUTHPORT/SE was silently removed to force a hit.

The eleven accepted clues contain no subdivision, parcel/lot, full address or
municipal/township/postal clue. Therefore merely loading those layers cannot add
new drawing evidence. The cemetery and storage labels cannot be matched to the
approved address field simply because address points are available.

## Cross-sheet reasoning

C7/C8 share three accepted labels: **NC 211 - SUPPLY ROAD**, **HWY 211 FORCE MAIN**,
and **CAPE FEAR MEMORIAL PARK CEMETERY**. This is meaningful textual project/area
context independent of filename or sheet order. C8 also names Sentry Self Storage.
The engine retains separate sheet clue IDs, boxes, hashes and histories; it neither
asserts a shared plan-set revision nor transfers candidate scores/acceptance.

## Geographic evaluation status

Existing clue acceptance is complete. A correct geographic area and candidate
outcome have not yet been independently supplied. The separate
[geographic evaluation report](../outputs/phase2b/county-evaluation-002/evaluation.json)
records **two pending geographic reviews**, zero independently evaluated drawings,
and null candidate-recall/top-k metrics. Zero reviewed false matches is not evidence
of a zero false-match rate. The two observed insufficient-evidence outcomes are
recorded separately from truth-dependent evaluation denominators.

For **each** sheet the following remain unknown: whether the true area is ranked
first, within the top three, or absent from the results; correct-area rank; geographic
recall and false-match performance. No success rate or geographic accuracy score
is claimed. Zero generated candidates is reported as an algorithm outcome only.

After independent GIS investigation, copy the existing frozen-run evaluation
template, enter the true area/source, reviewer/time/reason and candidate decisions,
and run `localization-evaluate`. A zero-candidate run can be recorded as a miss only
after a localizable truth area is independently established. Preserve this initial
run when new alias handling or references produce later candidates.

## Next development and analyst tasks

1. Confirm the relationship, if any, between the drawing's NC 211 / Supply Road
   label and current SOUTHPORT-SUPPLY RD naming. Supply authoritative full aliases
   or approve a documented route-field mapping with historical semantics. Keep
   original accepted transcription unchanged; store reference interpretation as
   separate evidence.
2. Establish an independent C7/C8 correct-area reference. Inspect the accepted
   cemetery/storage/project evidence against approved GIS sources. If necessary,
   scope a landmark reference adapter, or add genuinely visible new clues through
   the existing manual review process. Do not re-approve the existing eleven clues.
3. Confirm subdivision granularity and field semantics; decide how repeated
   parcel-associated polygons should form candidate regions while retaining IDs.
4. Resolve 1,317 parcel geometry errors, the postal-zone ring error, and unnamed
   features using new analyst-prepared local exports or explicit exclusion policy.
   Original exports and enterprise records remain unchanged. Confirm remaining
   parcel/admin mappings and supply missing source provenance.
5. Rerun against a new snapshot, preserve the initial rankings, independently review
   candidate areas, and measure top-1/top-3 appearance, false matches, ambiguity and
   abstentions. Expand beyond two related drawings before setting acceptance rules.

Utility recognition, PDF-to-asset associations and SDE writes remain deferred.

## Validation

The full suite passes **159 tests**, preserving the original 134 and adding 25
metadata/integration tests. Coverage includes streamed county-scale input, schema
and hash changes, missing layers, actual null counts, CRS provenance, guarded
human mapping approval, address-point evidence, administrative context, phase/number
conflicts, local projected distances and pending geographic outcomes. The real
data findings above are separate from synthetic test outcomes.

See [integration validation](../outputs/phase2b/county-integration-validation.json)
for source/approval hash preservation and report checks. Prior Phase 2B documents
are archived in `outputs/phase2b/county-integration-audit-001/`.
