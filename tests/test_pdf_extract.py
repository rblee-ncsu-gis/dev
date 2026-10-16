import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from asbuilt_matcher.pdf_extract import extract_pdf, file_sha256, load_pdf_backend


def test_hash(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"synthetic")
    assert file_sha256(source) == hashlib.sha256(b"synthetic").hexdigest()


def test_missing_backend():
    with patch("asbuilt_matcher.pdf_extract.importlib.import_module", side_effect=ImportError):
        with pytest.raises(RuntimeError, match="approval"):
            load_pdf_backend()


@pytest.mark.parametrize("dpi,pixels", [(0, 100), (float("nan"), 100), (100, 0)])
def test_invalid_render_options(dpi, pixels, tmp_path):
    with pytest.raises(ValueError):
        extract_pdf(tmp_path / "absent.pdf", tmp_path / "out", dpi=dpi, max_pixels=pixels)


def test_page_failure_continues_with_auditable_manifest(tmp_path):
    """Exercise orchestration without requiring a native PDF dependency."""
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"synthetic backend input")
    class Rect(list):
        width = 300
        height = 200

    rect = Rect([0, 0, 300, 200])
    pixmap = SimpleNamespace(width=300, height=200, x=0, y=0,
                            save=lambda path: Path(path).write_bytes(b"preview"))
    page = SimpleNamespace(
        rect=rect, cropbox=rect, mediabox=rect, rotation=0,
        rotation_matrix=[1, 0, 0, 1, 0, 0],
        get_text=lambda *a, **kw: "synthetic text", get_drawings=lambda: [],
        get_image_info=lambda: [], get_pixmap=lambda **kw: pixmap,
    )
    class Document:
        is_pdf = True
        needs_pass = False
        metadata = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __len__(self): return 3
        def __getitem__(self, index):
            if index == 1:
                raise ValueError("synthetic damaged page")
            return page

    backend = SimpleNamespace(open=lambda path: Document(), Matrix=lambda *args: args, csRGB="RGB")
    with patch("asbuilt_matcher.pdf_extract.load_pdf_backend", return_value=backend):
        report = extract_pdf(source, tmp_path / "out", dpi=72)
    assert report["status"] == "partial"
    assert [p["status"] for p in report["pages"]] == ["ok", "error", "ok"]
    assert report["errors"][0]["page_index"] == 1
    assert (tmp_path / "out" / "page-0003.txt").read_text() == "synthetic text"


@pytest.fixture
def pdf():
    return pytest.importorskip("pymupdf", reason="PyMuPDF not installed; no dependencies installed automatically")


def test_synthetic_mixed_pdf(pdf, tmp_path):
    source = tmp_path / "synthetic.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((20, 30), "SYNTHETIC WATER MAIN")
        page.draw_line((20, 60), (250, 60))
        page.set_rotation(90)
        page = doc.new_page(width=300, height=200)
        # Generated local RGB pixels: no county drawings or external fixtures.
        image = pdf.Pixmap(pdf.csRGB, pdf.IRect(0, 0, 10, 10), False)
        image.clear_with(180)
        page.insert_image(page.rect, pixmap=image)
        doc.new_page(width=300, height=200)
        doc.save(source)
    before = source.read_bytes()
    output = tmp_path / "out"
    report = extract_pdf(source, output, dpi=144, max_pixels=100_000)
    assert report["status"] == "complete"
    assert report["page_count"] == 3
    first, second, third = report["pages"]
    assert first["vector_paths"] > 0
    assert first["rotation"] == 90
    assert first["preview"]["width"] * first["preview"]["height"] <= 100_000
    assert "SYNTHETIC WATER MAIN" in (output / first["text_file"]).read_text()
    assert second["content_hint"] == "raster" and second["ocr_recommended"]
    assert third["content_hint"] == "empty"
    assert json.loads((output / "manifest.json").read_text())["source"]["sha256"] == file_sha256(source)
    assert source.read_bytes() == before
    with pytest.raises(FileExistsError):
        extract_pdf(source, output)


def test_corrupt_pdf_has_failure_manifest(pdf, tmp_path):
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"not a PDF")
    report = extract_pdf(source, tmp_path / "out")
    assert report["status"] == "failed" and report["errors"]
    assert (tmp_path / "out" / "extraction.log").read_text()


def test_encrypted_pdf(pdf, tmp_path):
    source = tmp_path / "encrypted.pdf"
    with pdf.open() as doc:
        doc.new_page()
        doc.save(source, encryption=pdf.PDF_ENCRYPT_AES_256,
                 owner_pw="synthetic-owner", user_pw="synthetic-user")
    report = extract_pdf(source, tmp_path / "out")
    assert report["status"] == "failed"
    assert "password" in report["errors"][0]["error"]
