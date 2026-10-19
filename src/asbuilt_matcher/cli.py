import argparse
import json
import logging

from .environment import check_environment
from .pdf_extract import extract_pdf
from .batch import inventory_pdfs
from .raster import prepare_rasters
from .clues import init_clues, add_clue, review_clue, CLUE_KINDS, STATUSES
from .clue_review import write_review_bundle, apply_decisions, export_verified
from .ocr_eval import score_files
from .ocr import probe_tesseract, run_baseline
from .ocr_report import report_from_file
from .geo_reference import import_references
from .geo_report import localize
from .geo_eval import evaluate_localization
from .geo_inventory import validate_county
from .geo_diagnostics import diagnose_roads
from .geo_landmarks import import_landmarks
from .geo_narrowing import run_narrowing


def read_json(path):
    from pathlib import Path
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local as-built PDF intelligence pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-environment")
    landmark_import = commands.add_parser('landmarks-import', help='Resolve supplemental landmark references from read-only county snapshots')
    landmark_import.add_argument('config')
    landmark_import.add_argument('--output', required=True)
    narrow = commands.add_parser('corridor-narrow', help='Add separate landmark review localities to a frozen corridor run')
    narrow.add_argument('run')
    narrow.add_argument('--landmarks', required=True)
    narrow.add_argument('--observations', help='Pending AI source-inspection observations; never approved clues')
    narrow.add_argument('--settings', help='JSON metre search thresholds; not positional accuracy')
    narrow.add_argument('--output', required=True)
    road_diagnostics=commands.add_parser('roads-diagnose',help='Inspect actual road names/routes and retain source geometries')
    road_diagnostics.add_argument('roads')
    road_diagnostics.add_argument('--id-field',default='GlobalID')
    road_diagnostics.add_argument('--name-field',default='FULLNAME')
    road_diagnostics.add_argument('--route-fields',nargs='+',default=['STATERDNUM'])
    road_diagnostics.add_argument('--output',required=True)
    validate_geo = commands.add_parser("geo-validate", help="Inspect county exports, update metadata and propose field mappings")
    validate_geo.add_argument("--directory", default="data/reference/brunswick_county")
    validate_geo.add_argument("--source-directory", help="Optional existing export location; sources are not moved")
    validate_geo.add_argument("--decisions", help="Analyst-confirmed, hash-bound mapping/CRS/source metadata JSON")
    validate_geo.add_argument("--output", required=True)
    geo_import = commands.add_parser("geo-import", help="Import read-only WGS84 GeoJSON using configured fields")
    geo_import.add_argument("config")
    geo_import.add_argument("--output", required=True)
    geo = commands.add_parser("localize", help="Rank read-only geographic candidate areas from accepted clues")
    geo.add_argument("clues", help="Existing independently accepted clue export")
    geo.add_argument("--references", help="Imported references.json; omit to inventory outstanding reference needs")
    geo.add_argument("--settings", help="JSON geographic ranking settings")
    geo.add_argument('--aliases',help='Explicit scoped road-alias registry; never enabled implicitly')
    geo.add_argument("--output", required=True)
    geo_eval = commands.add_parser("localization-evaluate", help="Measure independently reviewed candidate areas")
    geo_eval.add_argument("run")
    geo_eval.add_argument("review")
    geo_eval.add_argument("--output", required=True)
    extract = commands.add_parser("extract", help="Extract one PDF into a new directory")
    extract.add_argument("pdf")
    extract.add_argument("--output", required=True)
    extract.add_argument("--dpi", type=float, default=100)
    extract.add_argument("--max-pixels", type=int, default=16_000_000)
    batch = commands.add_parser("batch", help="Inventory a directory of engineering PDFs")
    batch.add_argument("directory")
    batch.add_argument("--output", required=True)
    batch.add_argument("--recursive", action="store_true")
    batch.add_argument("--dpi", type=float, default=100)
    batch.add_argument("--max-pixels", type=int, default=16_000_000)
    raster = commands.add_parser("prepare-rasters", help="Export native images, composites and selected crops")
    raster.add_argument("pdf")
    raster.add_argument("--output", required=True)
    raster.add_argument("--regions", help="JSON array of page_number/id/kind/bbox region objects")
    raster.add_argument("--dpi", type=float, default=200)
    raster.add_argument("--max-pixels", type=int, default=40_000_000)
    init = commands.add_parser("clues-init", help="Create a manual clue registry from raster evidence")
    init.add_argument("manifest")
    init.add_argument("--registry", required=True)
    add = commands.add_parser("clues-add", help="Record an unverified manual transcription")
    add.add_argument("registry")
    add.add_argument("--kind", choices=sorted(CLUE_KINDS), required=True)
    add.add_argument("--text", required=True)
    add.add_argument("--page", type=int, required=True)
    add.add_argument("--bbox", nargs=4, type=float, required=True)
    add.add_argument("--author", required=True)
    add.add_argument("--coordinates", help="JSON object with x/y/crs/units for survey coordinates")
    add.add_argument("--notes", default="")
    review = commands.add_parser("clues-review", help="Correct, verify or reject a clue, retaining history")
    review.add_argument("registry")
    review.add_argument("clue_id")
    review.add_argument("--author", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--text")
    review.add_argument("--bbox", nargs=4, type=float)
    review.add_argument("--coordinates", help="JSON object with corrected x/y/crs/units")
    review.add_argument("--status", choices=sorted(STATUSES))
    review.add_argument("--reviewer-type", choices=["human", "ai", "unspecified"], default="unspecified")
    review.add_argument("--independent", action="store_true", help="Human reviewer explicitly attests independent review")
    manifest = commands.add_parser("clues-manifest", help="Write review Markdown/CSV/JSON and decision templates")
    manifest.add_argument("registries", nargs="+")
    manifest.add_argument("--output", required=True)
    apply = commands.add_parser("clues-apply", help="Apply a filled decision template atomically per registry")
    apply.add_argument("registry")
    apply.add_argument("decisions")
    export = commands.add_parser("clues-export", help="Export only verified clues with evidence and review provenance")
    export.add_argument("registries", nargs="+")
    export.add_argument("--output", required=True)
    export.add_argument("--render-targets", action="store_true", help="Render verified clue boxes as 200-DPI OCR targets")
    export.add_argument("--analyst-only", action="store_true", help="Only independently human-accepted references")
    score = commands.add_parser("ocr-score", help="Score supplied OCR/NER predictions; does not run OCR")
    score.add_argument("ground_truth")
    score.add_argument("predictions")
    score.add_argument("--output", required=True)
    check_ocr = commands.add_parser("ocr-check", help="Read-only Tesseract and English-data probe")
    check_ocr.add_argument("--tesseract")
    check_ocr.add_argument("--tessdata-dir")
    check_ocr.add_argument("--output", help="Save a diagnostic JSON snapshot to a new file")
    visual = commands.add_parser("ocr-report", help="Generate an offline visual report from an existing OCR run")
    visual.add_argument("run")
    visual.add_argument("--output", required=True)
    ocr = commands.add_parser("ocr-run", help="Prepare image variants and run optional local Tesseract")
    ocr.add_argument("evidence", help="Phase 1B raster manifest or Phase 1C clue export")
    ocr.add_argument("--output", required=True)
    ocr.add_argument("--config")
    ocr.add_argument("--tesseract")
    ocr.add_argument("--tessdata-dir")
    ocr.add_argument("--ground-truth", help="Only independent human acceptances can be scored")
    ocr.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == 'landmarks-import':
            result = import_landmarks(args.config, args.output)
            print(json.dumps({'landmarks': len(result['landmarks']), 'processing': result['processing'], 'errors': result['errors']}, indent=2))
            return 0
        if args.command == 'corridor-narrow':
            result = run_narrowing(args.run, args.landmarks, args.output,
                                   settings=read_json(args.settings) if args.settings else None, observations_path=args.observations)
            print(json.dumps([{'source_pdf': d['source_pdf'], 'status': d['narrowing_status'], 'narrowed_candidates': len(d['narrowed_candidates'])} for d in result['drawings']], indent=2))
            return 0
        if args.command=='roads-diagnose':
            result=diagnose_roads(args.roads,args.output,id_field=args.id_field,name_field=args.name_field,route_fields=args.route_fields)
            print(json.dumps({k:result[k] for k in ['total_features','related_features','route_211_features','unnamed_count','unnamed_with_route_identifier']},indent=2))
            return 0
        if args.command == "geo-validate":
            result = validate_county(args.directory, args.output, source_directory=args.source_directory, decisions_path=args.decisions)
            print(json.dumps({k:result[k] for k in ["status","missing_datasets","ready_datasets","invalid_datasets","changes"]},indent=2))
            return 1 if result["status"] == "invalid" else 0
        if args.command == "geo-import":
            result = import_references(args.config, args.output)
            print(json.dumps({"status": result["status"], "features": len(result["features"]),
                              "error_count":len(result['errors']),"error_examples":result['errors'][:5],
                              "missing_datasets":result.get('missing_datasets',[])}, indent=2))
            return 1 if result["status"] == "partial" else 0
        if args.command == "localize":
            result = localize(args.clues, args.output, references_path=args.references,
                              settings=read_json(args.settings) if args.settings else None,alias_registry_path=args.aliases)
            print(json.dumps({"status": result["status"], "drawings": [{k: d[k] for k in ["source_pdf", "page_number", "status"]} for d in result["drawings"]]}, indent=2))
            return 0
        if args.command == "localization-evaluate":
            result = evaluate_localization(args.run, args.review, args.output)
            print(json.dumps(result["summary"], indent=2))
            return 0
        if args.command == "ocr-check":
            result = probe_tesseract(args.tesseract, args.tessdata_dir)
            if args.output:
                from pathlib import Path
                from .pdf_extract import write_json
                path = Path(args.output)
                if path.exists():
                    raise FileExistsError(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                write_json(path, result)
            print(json.dumps(result, indent=2))
            return 0 if result["ready"] else 1
        if args.command == "ocr-report":
            print(json.dumps(report_from_file(args.run, args.output), indent=2))
            return 0
        if args.command == "ocr-run":
            result = run_baseline(args.evidence, args.output,
                                  config=read_json(args.config) if args.config else None,
                                  executable=args.tesseract, tessdata_dir=args.tessdata_dir,
                                  ground_truth_path=args.ground_truth, prepare_only=args.prepare_only)
            print(json.dumps({k: result[k] for k in ("status", "engine", "evaluation")}, indent=2))
            return 0 if result["status"] in {"complete", "prepared_only"} else 2 if result["status"] == "blocked_engine" else 1
        if args.command == "check-environment":
            report = check_environment()
            print(json.dumps(report, indent=2, default=str))
            return 0 if report["pdf_ready"] else 1
        if args.command == "clues-init":
            result = init_clues(args.manifest, args.registry)
            print(json.dumps(result, indent=2))
            return 0
        if args.command in ("clues-manifest", "clues-export"):
            result = (write_review_bundle(args.registries, args.output) if args.command == "clues-manifest"
                      else export_verified(args.registries, args.output, render_targets=args.render_targets,
                                           analyst_only=args.analyst_only))
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "clues-apply":
            print(json.dumps(apply_decisions(args.registry, args.decisions), indent=2))
            return 0
        if args.command == "ocr-score":
            print(json.dumps(score_files(args.ground_truth, args.predictions, args.output), indent=2))
            return 0
        if args.command == "clues-add":
            result = add_clue(args.registry, kind=args.kind, text=args.text, page_number=args.page,
                              bbox=args.bbox, author=args.author, notes=args.notes,
                              coordinates=json.loads(args.coordinates) if args.coordinates else None)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "clues-review":
            result = review_clue(args.registry, args.clue_id, author=args.author, reason=args.reason,
                                text=args.text, status=args.status, bbox=args.bbox,
                                reviewer_type=args.reviewer_type,
                                independent=args.independent,
                                coordinates=json.loads(args.coordinates) if args.coordinates else None)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "prepare-rasters":
            result = prepare_rasters(args.pdf, args.output, regions=read_json(args.regions) if args.regions else [],
                                     dpi=args.dpi, max_pixels=args.max_pixels)
        elif args.command == "batch":
            result = inventory_pdfs(args.directory, args.output, recursive=args.recursive,
                                    dpi=args.dpi, max_pixels=args.max_pixels)
        else:
            result = extract_pdf(args.pdf, args.output, dpi=args.dpi, max_pixels=args.max_pixels)
        print(json.dumps({"status": result["status"], "output": args.output,
                          "errors": result["errors"]}, indent=2))
        return 0 if result["status"] in ("complete", "empty") else 1
    except Exception as exc:
        logging.error("%s: %s", type(exc).__name__, exc)
        return 1
