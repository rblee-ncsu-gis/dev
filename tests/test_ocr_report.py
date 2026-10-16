import json
from pathlib import Path

import pytest

from asbuilt_matcher.ocr_report import write_visual_report, report_from_file
from asbuilt_matcher.pdf_extract import file_sha256


@pytest.fixture
def report(tmp_path):
    pdf = pytest.importorskip("pymupdf")
    source, processed = tmp_path / "source.png", tmp_path / "processed.png"
    pix = pdf.Pixmap(pdf.csGRAY, 2, 2, bytes([0,255,255,0]),False)
    pix.save(source)
    pix.save(processed)
    return {"run_id":"synthetic", "status":"complete", "evaluation":{"status":"not_requested"},
            "images":[{"id":"target", "path":str(source), "sha256":file_sha256(source)}],
            "engine":{"version":"synthetic"}, "config":{}, "comparison":[],
            "results":[{"image_id":"target","source_pdf":"synthetic.pdf","page_number":1,"variant":"baseline",
                        "status":"recognized","source_image_sha256":file_sha256(source), "text":"<script>alert('bad')</script>",
                        "words":[{"text":"X", "confidence":90, "bbox_processed":[0,0,1,1],"bbox_page":[10,20,11,21]}],
                        "processed":{"file":str(processed), "sha256":file_sha256(processed),"width":2,"height":2}}]}


def test_visual_report_snapshots_images_and_escapes_ocr_text(report, tmp_path):
    out = tmp_path / "report"
    before = file_sha256(report["images"][0]["path"])
    write_visual_report(report,out)
    document = (out / "REVIEW.html").read_text()
    assert "Original source crop" in document and "Detected text" in document
    assert "&lt;script&gt;" in document and "<script>alert('bad')</script>" not in document
    assert "Original page points" in document and "[10, 20, 11, 21]" in document
    assert '<svg ' in document and '<rect ' in document
    assert file_sha256(out / "source-images" / "image-0001.png") == before
    assert file_sha256(report["images"][0]["path"]) == before


def test_changed_source_is_not_presented_as_original_evidence(report, tmp_path):
    Path(report["images"][0]["path"]).write_bytes(b"changed")
    out = tmp_path / "report"
    write_visual_report(report,out)
    assert "Image hash mismatch" in (out / "REVIEW.html").read_text()
    assert json.loads((out / "visual-assets.json").read_text())["sources"]["target"]["url"] is None


def test_existing_blocked_runs_can_be_rendered_without_an_engine(report, tmp_path):
    report["status"] = "blocked_engine"
    report["results"][0].update(status="blocked_engine", text=None, words=[])
    run = tmp_path / "ocr-run.json"
    run.write_text(json.dumps(report))
    result = report_from_file(run,tmp_path / "visual")
    assert result["results"] == 1
    assert "No recognition output (blocked_engine)" in Path(result["report"]).read_text()
    with pytest.raises(FileExistsError):
        report_from_file(run,tmp_path / "visual")
