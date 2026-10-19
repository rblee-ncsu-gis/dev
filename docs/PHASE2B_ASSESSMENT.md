# Phase 2B: read-only geographic localization prototype

Latest continuation: [Phase 2B.1 alias resolution](PHASE2B1_ALIAS_RESOLUTION.md)
recovers one scoped road-corridor candidate for each sheet while preserving the
zero-candidate baseline below. Corridor recovery is separate from independently
verified drawing localization; geographic accuracy remains unmeasured.

## Authoritative integration update — October 19, 2026

All seven county exports are now present and inspected. The analyst confirmed
WGS84 output for all seven and approved GlobalID/FULLNAME (roads),
GlobalID/SubdivisionName (subdivisions) and GlobalID/ST_ADDR (addresses).
The three layers yielded **310,386 usable features**, excluding 509 unnamed
road/subdivision features. Parcels have 1,317 geometry errors; postal zones have
one. Remaining field mappings and original source provenance are pending.

The first actual county run completed for C7/C8. Both sheets returned
**insufficient_evidence with zero candidates**. Their accepted NC 211 / Supply Road
label does not match the approved current road-name field. Related
SOUTHPORT-SUPPLY RD names are inspection findings, not approved aliases or
geographic matches. All eleven clue decisions and original rankings are preserved.

No independent geographic-area decision has been supplied, so top-1/top-3,
correct-area rank, false-match rates and geographic accuracy remain unmeasured.
The suite now passes **159 tests**. Seven-layer import, automatic metadata/history,
mapping proposals/confirmation, address evidence and administrative context are
implemented without new packages, ArcPy or environment changes.

Read [the actual county validation report](PHASE2B_REAL_WORLD_VALIDATION.md) for
counts, errors, frozen outputs and next tasks. Prioritize an authoritative
road-alias/route decision and independent correct-area references before utility
recognition or asset matching.

The following October 16 assessment is retained as the historical synthetic
milestone, before the county exports and the current integration run.

---

Assessment date: October 16, 2026.

## Management outcome

The geographic localization prototype is implemented and exercised against
fabricated road, subdivision and parcel exports. It imports configurable schemas,
preserves native identifiers and provenance, matches accepted labels and ranks
explainable candidate areas. JSON, CSV and offline HTML/SVG review are available.
No dependencies were added and no Python environment or enterprise GIS data changed.

**Real-world geographic success is not yet measured.** No authoritative county
GeoJSON exports were available in this workspace. C7/C8 therefore have zero proposed
locations and `awaiting_reference_data` status. Their existing eleven human
acceptances and correction histories remain unchanged; they were not reopened or
re-approved. Clue transcription acceptance does not establish geographic placement.

## Implementation delivered

| Component | Responsibility |
| --- | --- |
| `geo_reference.py` | Read-only local GeoJSON ingestion, field mappings, identity/provenance retention, CRS/geometry validation, partial/error inventory |
| `geo_names.py` | Case/punctuation/suffix/directional normalization, explicit aliases, conservative fuzzy name matching, exact identifier handling |
| `geo_geometry.py` | County-scale 2D containment/distance/crossing checks with polygon holes and multipart geometry; no reprojection |
| `geolocate.py` | Sheet-level candidate generation, deterministic auditable scoring, conflict/ambiguity/insufficient-evidence handling, cross-sheet label comparison |
| `geo_report.py` | Frozen inputs and implementation hashes, JSON/CSV, offline schematic maps and separate geographic evaluation templates |
| `geo_eval.py` | Independent area/candidate review metrics with run-hash binding and pending-task tracking |

CLI commands: `geo-import`, `localize`, `localization-evaluate`. Existing extraction,
OCR, clue review/export and scoring interfaces are preserved. The implementation
reuses existing document hashes, clue kinds, accepted-export format and
`analyst_accepted` eligibility check; it does not create a duplicate clue registry.

## Synthetic evidence

The reproducible fixture contains four road segments, two subdivision polygons and
two parcel polygons. The same two road names cross in two separated areas. A third
subdivision clue identifies the intended synthetic area. Field names deliberately
differ from canonical names; composite road-name fields and aliases are exercised.
All coordinates, labels, PDF identity and approvals are fabricated and explicitly
labeled as such; these are not Brunswick County GIS test results.

Expected outcomes covered by automated tests:

- Two roads plus the matching subdivision rank the known Alpha intersection first.
- Two equal named-road crossings without the subdivision remain ambiguous.
- A single street remains insufficient; unsupported project/landmark words are not
  converted into street identifiers.
- Approximate OCR spellings remain approximate, while route-number, directional,
  suffix and parcel-ID differences are guarded.
- A nearby different parcel's lot cannot corroborate the specified parcel.
- Polygon holes, multipart features, shared endpoints, parallel/collinear roads,
  differing exported road levels and invalid geometries are handled explicitly.
- Repeated labels/aliases do not inflate corroboration; truncated/partial searches
  cannot establish a definitive location.
- Independent evaluation tracks rank/correct-area appearance, false candidates,
  ambiguous results and insufficient evidence; incomplete evaluation stays pending.
- Input bytes and acceptance records are preserved; output directories cannot be
  reused; HTML is offline and source-derived text is escaped.

The full suite passes **134 tests** (90 existing plus 44 Phase 2B tests). This
establishes implementation behavior on controlled fixtures, not production accuracy.

The generated synthetic example ranks the expected Alpha crossing first and retains
the competing Beta crossing with a subdivision conflict. Distinct candidate areas
are preserved; alternate anchors with identical evidence are consolidated. Scoring
policy, distances, geometry source IDs, limitations and pending analyst status are
visible in the artifacts. No synthetic score is a calibrated probability.

| Synthetic candidate area | Rank | Ranking points | Evidence |
| --- | ---: | ---: | --- |
| Alpha road crossing | 1 | 120.0 | Both streets and subdivision agree |
| Beta road crossing | 2 | 75.9 | Both streets; subdivision conflict |

## C7/C8 evidence and readiness

| Drawing | Accepted clues retained | Supported localizing label | Current result |
| --- | ---: | --- | --- |
| s07772.pdf / C7 | 5 | NC 211 - SUPPLY ROAD | awaiting_reference_data; 0 candidates |
| s07773.pdf / C8 | 6 | NC 211 - SUPPLY ROAD | awaiting_reference_data; 0 candidates |

Both sheets share accepted **NC 211 - SUPPLY ROAD**, **HWY 211 FORCE MAIN**, and
**CAPE FEAR MEMORIAL PARK CEMETERY** labels. This is evidence of shared geographic
and project context beyond filenames/sheet numbering. It does not prove a common
plan-set edition, a continuous route, adjacency or an exact drawing footprint.
C8 additionally contains Sentry Self Storage. All evidence remains tied to its
own sheet/page, document hash, bounding box and review history. No sheet's
candidates or scores are transferred to another sheet.

Only street/subdivision/parcel/lot clues drive localization in this initial
reference interface. Landmarks/projects are context until suitable authoritative
reference support is explicitly added. Sheet IDs and stationing are not absolute
GIS coordinates. Neither drawing currently supplies an accepted second road,
subdivision, parcel or lot clue. Roads alone may identify a broad corridor; they
will not force a qualified drawing-area match. Mapping actual road aliases is
especially important for the composite `NC 211 - SUPPLY ROAD` label.

## Analyst data required next

The complete field/export checklist is in
[PHASE2B_WORKFLOW.md](PHASE2B_WORKFLOW.md#analyst-reference-data-delivery-specification).
Provide:

1. **Road centerlines:** stable segment identifier, complete name or name
   components, route/name aliases where available; optional comparable crossing
   level. Include competing same-named roads and disclose export coverage.
2. **Subdivision polygons, if available:** stable ID, name, optional aliases.
3. **Parcel polygons:** stable feature ID, parcel/PIN string, optional lot and
   address attributes with their definitions and null/scoping conventions.
4. **WGS84 GeoJSON exports and completed mappings:** longitude/latitude decimal
   degrees, all layers in the same documented CRS, with authority, layer/version,
   export time, vintage, filters, source EPSG:2264 and actual export transformation.
   The supplied template contains placeholders, not asserted county field names.
5. **Independent geographic evaluation:** correct candidate-area references and
   analyst classifications in the separate frozen-run evaluation template.

If existing drawing evidence supports further road/subdivision/parcel clues, use
the established manual entry and review process for **new** clues. Current accepted
clues require no repeated approval. If the cemetery/storage labels are the only
practical corroboration, separately scope an authoritative landmark reference layer
and adapter rather than interpreting project/consultant text as a place.

## Limits and unresolved questions

- Geographic output is WGS84 only. NAD83 StatePlane feet must be transformed by an
  approved export workflow first. No automatic CRS conversion, page-to-map
  registration, GIS connection, utility detection or asset matching is implemented.
- A local spherical distance approximation and an exhaustive feature search avoid
  new packages. These are county-pilot tools; benchmark actual data volume and
  distance tolerances before expansion. Export topology needs independent QA.
- A 2D road crossing may be a bridge; missing levels cannot establish connectivity.
  Reference extents/search radii express candidate scope, not measured uncertainty.
- Deterministic thresholds are initial test settings, not empirically calibrated
  acceptance criteria. Candidate review remains pending even when status is
  `proposed_area`.
- Are road alias/route fields present, and do they support the exact compound label?
  Which subdivision/parcel layers and historical vintages are available?
- Can the approved cemetery/storage clues be anchored to authoritative geographic
  references? Are further usable location clues visible on C7/C8?
- Correct-area recall, rank distribution, false geographic matches, ambiguity and
  analyst burden on county drawings remain **unmeasured**. Zero candidates without
  references is not a false-negative accuracy result.

## Next milestone and artifacts

Proceed with an **authoritative-reference pilot evaluation**, starting with C7/C8
and expanding to unrelated projects. Deliver exports/mappings, inspect import
coverage/errors, run localization, and independently review candidate areas using
the new evaluation template. Resolve road aliases and missing corroborating
references before tuning thresholds. Measure geographic localization independently
from the already measured OCR baseline. Utility detection and SDE asset matching
remain deferred until this prototype has been evaluated.

- [Synthetic reference import](../outputs/phase2b/synthetic-reference-001/references.json)
- [Synthetic localization](../outputs/phase2b/synthetic-002/localization.json), [offline map review](../outputs/phase2b/synthetic-002/REVIEW.html)
- [C7/C8 readiness inventory](../outputs/phase2b/c7-c8-readiness-002/localization.json), [review](../outputs/phase2b/c7-c8-readiness-002/REVIEW.html)
- [Input preservation checks](../outputs/phase2b/input-preservation.json)
- [Final artifact validation](../outputs/phase2b/validation.json)
- [Reference configuration example](../config/geographic-reference.example.json), [ranking settings](../config/geographic-ranking.json)
- [Synthetic fixtures](../examples/phase2b/reference-config.json)
