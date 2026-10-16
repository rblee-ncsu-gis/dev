import json
from pathlib import Path
from unittest.mock import patch

import pytest

from asbuilt_matcher.raster import prepare_rasters
from asbuilt_matcher.pdf_extract import file_sha256
from asbuilt_matcher.cli import main


@pytest.fixture
def pdf():
    return pytest.importorskip("pymupdf")


def make_image(pdf, width=120, height=80, alpha=False):
    image = pdf.Pixmap(pdf.csRGB, pdf.IRect(0, 0, width, height), alpha)
    image.clear_with(180)
    return image


def test_native_jpeg_preserves_bytes_and_dimensions(pdf, tmp_path):
    image = make_image(pdf).tobytes("jpeg")
    source = tmp_path / "drawing.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=120, height=80)
        page.insert_image(page.rect, stream=image)
        doc.save(source)
    before = file_sha256(source)
    out = tmp_path / "out"
    report = prepare_rasters(source, out, dpi=144, regions=[
        {"id": "title", "page_number": 1, "kind": "title_block", "bbox": [10, 10, 100, 40]}])
    page = report["pages"][0]
    resource = page["resources"][0]
    assert resource["width"] == 120 and resource["height"] == 80
    assert resource["format"] == "jpeg"
    assert "DCTDecode" in resource["pdf_filter"]
    assert (out / page["directory"] / resource["file"]).read_bytes() == image
    assert page["images"][0]["effective_dpi_x"] == pytest.approx(72)
    crop = page["crops"][0]
    assert crop["width"] == 180 and crop["height"] == 60
    assert crop["page_to_pixel"] == [2, 0, 0, 2, -20, -20]
    assert file_sha256(source) == before == report["source"]["sha256"]
    assert json.loads((out / "raster-manifest.json").read_text())["status"] == "complete"
    assert "Readability is unreviewed" in (out / "RASTER_ASSESSMENT.md").read_text()
    with pytest.raises(FileExistsError):
        prepare_rasters(source, out)


def test_tiled_repeated_and_masked_images_render_complete_page(pdf, tmp_path):
    source = tmp_path / "tiles.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=240, height=80)
        xref = page.insert_image(pdf.Rect(0, 0, 120, 80), pixmap=make_image(pdf))
        page.insert_image(pdf.Rect(120, 0, 240, 80), xref=xref)
        page.insert_image(pdf.Rect(10, 10, 70, 50), pixmap=make_image(pdf, alpha=True))
        page.insert_text((20, 65), "overlay")
        doc.save(source)
    out = tmp_path / "out"
    result = prepare_rasters(source, out, dpi=72)
    page = result["pages"][0]
    assert len(page["images"]) == 3
    assert any(r["soft_mask_xref"] for r in page["resources"])
    assert any(r["xref"] == next(r["soft_mask_xref"] for r in page["resources"] if r["soft_mask_xref"])
               for r in page["resources"])
    actual = pdf.Pixmap(out / page["directory"] / page["full_page"]["file"])
    with pdf.open(source) as doc:
        expected = doc[0].get_pixmap(colorspace=pdf.csRGB, alpha=False)
    assert actual.samples == expected.samples


def test_normalized_rotation_capped_render_and_all_crop_kinds(pdf, tmp_path):
    source = tmp_path / "rotated.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_image(page.rect, pixmap=make_image(pdf))
        page.set_cropbox(pdf.Rect(50, 20, 250, 120))
        page.set_rotation(90)
        doc.save(source)
    kinds = ["title_block", "location_map", "plan_view_labels", "coordinate_annotations"]
    regions = [{"id": kind, "kind": kind, "page_number": 1, "bbox": [10.1, 10.1, 100.1, 50.1]} for kind in kinds]
    result = prepare_rasters(source, tmp_path / "out", dpi=300, max_pixels=10000, regions=regions)
    page = result["pages"][0]
    assert page["original_rotation"] == 90 and page["bounds"] == [0, 0, 200, 100]
    assert page["full_page"]["resolution_capped"]
    assert page["full_page"]["width"] * page["full_page"]["height"] <= 10000
    assert len(page["crops"]) == 4 and not page["unselected_region_kinds"]
    assert all(c["width"] * c["height"] <= 10000 for c in page["crops"])
    with pdf.open(source) as doc:
        assert doc[0].rotation == 90


def test_inline_image_uses_composite(pdf, tmp_path):
    source = tmp_path / "inline.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=100, height=100)
        xref = doc.get_new_xref()
        doc.update_object(xref, "<<>>")
        doc.update_stream(xref, b"q 100 0 0 100 0 0 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID \xff\x00\x00 EI Q")
        page.set_contents(xref)
        doc.save(source)
    result = prepare_rasters(source, tmp_path / "out", dpi=72)
    page = result["pages"][0]
    assert page["images"][0]["xref"] == 0
    assert page["images"][0]["native_status"] == "inline_or_unavailable"
    assert page["full_page"]["width"] == 100


def test_stencil_polarity_uses_page_composite(pdf, tmp_path):
    source = tmp_path / "stencil.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=80, height=80)
        xref = doc.get_new_xref()
        doc.update_object(xref, "<< /Type /XObject /Subtype /Image /Width 8 /Height 8 /ImageMask true /BitsPerComponent 1 /Decode [1 0] >>")
        doc.update_stream(xref, bytes([255, 0] * 4))
        doc.xref_set_key(page.xref, "Resources", f"<< /XObject << /Stencil {xref} 0 R >> >>")
        stream = doc.get_new_xref()
        doc.update_object(stream, "<<>>")
        doc.update_stream(stream, b"q 0 0 0 rg 80 0 0 80 0 0 cm /Stencil Do Q")
        page.set_contents(stream)
        doc.save(source)
    out = tmp_path / "out"
    result = prepare_rasters(source, out, dpi=72)
    page = result["pages"][0]
    resource = page["resources"][0]
    assert resource["pdf_image_mask"] == "true"
    assert resource["width"] == resource["height"] == 8
    actual = pdf.Pixmap(out / page["directory"] / page["full_page"]["file"])
    with pdf.open(source) as doc:
        assert actual.samples == doc[0].get_pixmap().samples


def test_inventory_failure_still_renders_page(pdf, tmp_path):
    source = tmp_path / "drawing.pdf"
    with pdf.open() as doc:
        doc.new_page()
        doc.save(source)
    with patch.object(pdf.Page, "get_image_info", side_effect=ValueError("synthetic inventory error")):
        result = prepare_rasters(source, tmp_path / "out", dpi=72)
    assert result["status"] == "partial"
    assert result["pages"][0]["full_page"]


def test_render_failure_keeps_native_and_continues_next_page(pdf, tmp_path):
    source = tmp_path / "drawing.pdf"
    with pdf.open() as doc:
        for _ in range(2):
            page = doc.new_page(width=120, height=80)
            page.insert_image(page.rect, pixmap=make_image(pdf))
        doc.save(source)
    from asbuilt_matcher.raster import render_region
    calls = 0
    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("synthetic rendering error")
        return render_region(*args, **kwargs)
    with patch("asbuilt_matcher.raster.render_region", side_effect=fail_once):
        result = prepare_rasters(source, tmp_path / "out", dpi=72)
    assert result["status"] == "partial"
    assert result["pages"][0]["resources"]
    assert result["pages"][1]["full_page"]


def test_resource_failure_retains_render_and_errors(pdf, tmp_path):
    source = tmp_path / "drawing.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=120, height=80)
        page.insert_image(page.rect, pixmap=make_image(pdf))
        doc.save(source)
    with patch("asbuilt_matcher.raster.extract_native", side_effect=ValueError("synthetic failure")):
        result = prepare_rasters(source, tmp_path / "out", dpi=72)
    assert result["status"] == "partial"
    assert result["pages"][0]["full_page"]
    assert result["errors"]


@pytest.mark.parametrize("region", [
    {"id": "../escape", "kind": "title_block", "page_number": 1, "bbox": [0, 0, 10, 10]},
    {"id": "title", "kind": "title_block", "page_number": 1, "bbox": [-1, 0, 10, 10]},
    {"id": "title", "kind": "title_block", "page_number": 2, "bbox": [0, 0, 10, 10]},
])
def test_bad_regions_rejected_before_output(pdf, tmp_path, region):
    source = tmp_path / "drawing.pdf"
    with pdf.open() as doc:
        doc.new_page()
        doc.save(source)
    with pytest.raises(ValueError):
        prepare_rasters(source, tmp_path / "out", regions=[region])
    assert not (tmp_path / "out").exists()


def test_cli_raster_and_manual_clue(pdf, tmp_path, capsys):
    source = tmp_path / "drawing.pdf"
    with pdf.open() as doc:
        doc.new_page()
        doc.save(source)
    out = tmp_path / "out"
    registry = tmp_path / "clues.json"
    assert main(["prepare-rasters", str(source), "--output", str(out), "--dpi", "72"]) == 0
    assert main(["clues-init", str(out / "raster-manifest.json"), "--registry", str(registry)]) == 0
    assert main(["clues-add", str(registry), "--kind", "street_name", "--text", "Supply Road",
                 "--page", "1", "--bbox", "0", "0", "100", "100", "--author", "analyst"]) == 0
    clue = json.loads(registry.read_text())["clues"][0]
    assert main(["clues-review", str(registry), clue["id"], "--author", "reviewer", "--reason",
                 "checked image", "--status", "verified"]) == 0
