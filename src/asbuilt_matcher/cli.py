import argparse
import json
import logging

from .environment import check_environment
from .pdf_extract import extract_pdf
from .batch import inventory_pdfs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local as-built PDF intelligence pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-environment")
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
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "check-environment":
            report = check_environment()
            print(json.dumps(report, indent=2, default=str))
            return 0 if report["pdf_ready"] else 1
        if args.command == "batch":
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
