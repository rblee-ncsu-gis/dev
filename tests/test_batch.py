import csv
import json
from unittest.mock import patch

import pytest

from asbuilt_matcher.batch import classify_document, classify_page, inventory_pdfs
from asbuilt_matcher.cli import main
from asbuilt_matcher.pdf_extract import file_sha256


def make_pdf(pdf, path, kind, rotation=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=200)
        if kind in ("vector", "mixed"):
            page.insert_text((20, 30), "SYNTHETIC valve 12 inch")
            page.draw_line((20, 60), (250, 60))
        if kind in ("scanned", "mixed"):
            image = pdf.Pixmap(pdf.csRGB, pdf.IRect(0, 0, 10, 10), False)
            image.clear_with(180)
            page.insert_image(pdf.Rect(20, 80, 120, 180), pixmap=image)
        page.set_rotation(rotation)
        doc.save(path)


@pytest.mark.parametrize("images,paths,text,expected", [
    (0, 2, False, "vector"), (1, 0, False, "scanned"),
    (1, 1, False, "mixed"), (1, 0, True, "mixed"),
    (0, 0, True, "vector"), (0, 0, False, "empty"),
])
def test_classification(images, paths, text, expected):
    assert classify_page({"image_instances": images, "vector_paths": paths,
                          "text_characters": int(text), "has_embedded_text": text}) == expected


def test_document_combines_page_evidence():
    assert classify_document([{"classification": "scanned"}, {"classification": "vector"}]) == "mixed"
    assert classify_document([{"classification": "empty"}]) == "unknown"
    assert classify_page({"status": "error"}) == "unknown"


def test_batch_reports_and_continues_after_corrupt_pdf(tmp_path):
    pdf = pytest.importorskip("pymupdf")
    source = tmp_path / "inputs"
    source.mkdir()
    (source / "00-bad.pdf").write_bytes(b"broken")
    make_pdf(pdf, source / "valve,plan.PDF", "vector", rotation=90)
    make_pdf(pdf, source / "scan.pdf", "scanned")
    make_pdf(pdf, source / "nested" / "valve,plan.PDF", "mixed")
    (source / "notes.txt").write_text("not a drawing")
    hashes = {str(p): file_sha256(p) for p in source.rglob("*") if p.is_file()}
    output = tmp_path / "results"
    report = inventory_pdfs(source, output, recursive=True, max_pixels=30_000)
    assert report["status"] == "partial"
    assert report["totals"]["documents"] == 4
    assert report["totals"]["pages"] == 3
    by_path = {d["relative_path"]: d for d in report["documents"]}
    assert by_path["00-bad.pdf"]["status"] == "failed"
    assert by_path["00-bad.pdf"]["sha256"] == hashes[str(source / "00-bad.pdf")]
    assert by_path["00-bad.pdf"]["page_count"] is None
    assert by_path["scan.pdf"]["classification"] == "scanned"
    assert by_path["nested/valve,plan.PDF"]["classification"] == "mixed"
    vector = by_path["valve,plan.PDF"]
    assert vector["classification"] == "vector" and vector["page_count"] == 1
    page = next(p for p in report["pages"] if p["relative_path"] == "valve,plan.PDF")
    assert (page["width_points"], page["height_points"], page["orientation"]) == (200, 300, "portrait")
    text = (output / page["text_file"]).read_text(encoding="utf-8")
    assert "SYNTHETIC valve" in text
    assert len(text) == page["text_characters"] == vector["text_characters"]
    assert page["vector_paths"] > 0 and page["image_instances"] == 0
    assert json.loads((output / "inventory.json").read_text(encoding="utf-8")) == report
    with (output / "documents.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4 and any(r["filename"] == "valve,plan.PDF" for r in rows)
    with (output / "pages.csv").open(encoding="utf-8-sig", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 3
    assert "Finished inventory: partial" in (output / "batch.log").read_text()
    assert hashes == {str(p): file_sha256(p) for p in source.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        inventory_pdfs(source, output)


def test_nonrecursive_empty_and_input_validation(tmp_path):
    pdf = pytest.importorskip("pymupdf")
    source = tmp_path / "inputs"
    source.mkdir()
    make_pdf(pdf, source / "nested" / "hidden.pdf", "vector")
    report = inventory_pdfs(source, source / "results")
    assert report["status"] == "empty" and report["documents"] == []
    assert (source / "results" / "pages.csv").read_text(encoding="utf-8-sig").startswith("relative_path,")
    with pytest.raises(NotADirectoryError):
        inventory_pdfs(tmp_path / "absent", tmp_path / "out")
    with pytest.raises(ValueError):
        inventory_pdfs(source, source)


def test_unexpected_document_error_is_reported(tmp_path):
    pytest.importorskip("pymupdf")
    source = tmp_path / "inputs"
    source.mkdir()
    (source / "test.pdf").write_bytes(b"synthetic")
    with patch("asbuilt_matcher.batch.extract_pdf", side_effect=OSError("synthetic failure")):
        report = inventory_pdfs(source, tmp_path / "out")
    assert report["status"] == "partial"
    assert "synthetic failure" in report["errors"][0]["error"]


def test_batch_cli(tmp_path, capsys):
    pdf = pytest.importorskip("pymupdf")
    source = tmp_path / "inputs"
    make_pdf(pdf, source / "plan.pdf", "vector")
    assert main(["batch", str(source), "--output", str(tmp_path / "out"),
                 "--max-pixels", "30000"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "complete"
    (source / "bad.pdf").write_bytes(b"bad")
    assert main(["batch", str(source), "--output", str(tmp_path / "out2")]) == 1
