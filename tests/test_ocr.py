import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from asbuilt_matcher.ocr import (DEFAULT_CONFIG, probe_tesseract, load_images, preprocess,
                                parse_tsv, geographic_candidates, run_baseline, validate_config)
from asbuilt_matcher.pdf_extract import file_sha256
from asbuilt_matcher.raster import prepare_rasters


@pytest.fixture
def evidence(tmp_path):
    pdf = pytest.importorskip("pymupdf")
    source = tmp_path / "source.pdf"
    with pdf.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((50, 60), "NC 211 - SUPPLY ROAD")
        doc.save(source)
    out = tmp_path / "raster"
    prepare_rasters(source, out, dpi=72, regions=[
        {"id": "road", "kind": "plan_view_labels", "page_number": 1, "bbox": [40, 30, 240, 130]}])
    return out / "raster-manifest.json"


def test_engine_missing_reports_unknown_language():
    with patch("asbuilt_matcher.ocr.shutil.which", return_value=None), patch.object(Path, "is_file", return_value=False):
        report = probe_tesseract()
    assert not report["ready"] and report["english_available"] is None


def test_engine_probe_lists_english_and_hashes_model(tmp_path):
    exe = tmp_path / "tesseract.exe"
    exe.write_bytes(b"synthetic executable")
    data = tmp_path / "tessdata"
    data.mkdir()
    (data / "eng.traineddata").write_bytes(b"synthetic model")
    def fake(args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="tesseract 5.synthetic" if "--version" in args
                               else f'List of available languages in "{data}" (1):\neng\n', stderr="")
    with patch("asbuilt_matcher.ocr.shutil.which", return_value=str(exe)), patch("asbuilt_matcher.ocr.subprocess.run", side_effect=fake):
        report = probe_tesseract(exe, data)
    assert report["ready"] and report["languages"] == ["eng"]
    assert report["english_model"]["sha256"] == file_sha256(data / "eng.traineddata")


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_preprocessing_maps_roundtrip_with_crop_and_rotation(evidence, tmp_path, rotation):
    pdf = pytest.importorskip("pymupdf")
    image = load_images(evidence)[1]
    before = file_sha256(image["path"])
    result = preprocess(image, {"id": "test", "grayscale": True, "contrast": 1.5,
                                "scale": 1.5, "threshold": 160, "rotation": rotation},
                        tmp_path / "processed.png", 100000)
    for point in [(40, 30), (240, 130), (100, 60)]:
        pixel = pdf.Point(*point) * pdf.Matrix(result["page_to_processed"])
        restored = pixel * pdf.Matrix(result["processed_to_page"])
        assert list(restored) == pytest.approx(point, abs=0.0001)
    assert (result["width"], result["height"]) == ((150, 300) if rotation in (90, 270) else (300, 150))
    pix = pdf.Pixmap(result["file"])
    assert set(pix.samples) <= {0, 255}
    assert file_sha256(image["path"]) == before


def test_budget_and_bad_config_rejected(evidence, tmp_path):
    with pytest.raises(ValueError, match="pixel budget"):
        preprocess(load_images(evidence)[0], {"id": "big", "scale": 8}, tmp_path / "big.png", 1000)
    for variant in [{"id": "../escape"}, {"id": "x", "rotation": 1}, {"id": "x", "scale": 0}]:
        with pytest.raises(ValueError):
            validate_config({**DEFAULT_CONFIG, "variants": [variant]})


def test_word_boxes_and_unknown_confidence_map_to_page():
    pytest.importorskip("pymupdf")
    tsv = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t-1\tNC\n"
    result = parse_tsv(tsv, {"width": 100, "height": 100, "processed_to_page": [0.5, 0, 0, 0.5, 100, 200]})
    assert result[0]["bbox_page"] == [105, 210, 120, 215]
    assert result[0]["confidence"] is None


def test_no_engine_prepares_and_records_every_job(evidence, tmp_path):
    with patch("asbuilt_matcher.ocr.probe_tesseract", return_value={"ready": False, "error": "not installed"}):
        result = run_baseline(evidence, tmp_path / "run", config={"variants": [{"id": "baseline"}]})
    assert result["status"] == "blocked_engine"
    assert len(result["results"]) == 2
    assert all(r["status"] == "blocked_engine" and "processed" in r for r in result["results"])
    assert result["comparison"][0]["metrics"] is None
    assert (tmp_path / "run" / "comparison.csv").exists()


def test_subprocess_adapter_keeps_raw_outputs_and_boxes(evidence, tmp_path):
    engine = {"ready": True, "executable": "synthetic", "version": "synthetic", "languages": ["eng"]}
    def fake(args, **kwargs):
        base = Path(args[2])
        base.with_suffix(".txt").write_text('NC 211 - SUPPLY ROAD\nSTA. 12+00 16 INCH PVC\n', encoding="utf-8")
        base.with_suffix(".tsv").write_text("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t10\t20\t10\t87.5\tNC\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="synthetic diagnostic")
    with patch("asbuilt_matcher.ocr.probe_tesseract", return_value=engine), patch("asbuilt_matcher.ocr.subprocess.run", side_effect=fake):
        report = run_baseline(evidence, tmp_path / "run", config={"variants": [{"id": "baseline"}]})
    assert report["status"] == "complete"
    row = report["results"][1]
    assert row["raw_text"].endswith("\n") and not row["text"].endswith("\n")
    assert row["confidence_mean"] == 87.5
    assert row["words"][0]["bbox_page"] == [50, 40, 70, 50]
    assert row["engineering_warnings"]
    assert row["entities"][0]["review_status"] == "unreviewed"


def test_timeout_keeps_failed_case_and_continues(evidence, tmp_path):
    engine = {"ready": True, "executable": "synthetic", "languages": ["eng"]}
    with patch("asbuilt_matcher.ocr.probe_tesseract", return_value=engine), patch(
        "asbuilt_matcher.ocr.subprocess.run", side_effect=subprocess.TimeoutExpired("synthetic", 1)):
        report = run_baseline(evidence, tmp_path / "run", config={"variants": [{"id": "baseline"}]})
    assert report["status"] == "partial" and len(report["results"]) == 2
    assert all(r["status"] == "failed" and "timeout" in r["error"] for r in report["results"])


def test_candidate_rules_have_no_reference_text_or_type_input():
    candidates, warnings = geographic_candidates("NC 211 - SUPPLY ROAD\nSTA. 10+00 16 INCH PVC")
    assert candidates[0]["kind"] == "street_name"
    assert warnings and warnings[0]["status"] == "review_required"
    assert geographic_candidates("16 INCH PVC")[0] == []


@pytest.mark.parametrize("rotation,location", [(0,(0,0)), (90,(1,0)), (180,(2,1)), (270,(0,2))])
def test_orientation_pixels_agree_with_inverse_word_boxes(tmp_path, rotation, location):
    pdf = pytest.importorskip("pymupdf")
    path = tmp_path / "source.png"
    pdf.Pixmap(pdf.csGRAY, 3, 2, bytes([0,255,255,255,255,255]), False).save(path)
    image = {"path": str(path), "width": 3, "height": 2, "effective_dpi": 72,
             "page_to_pixel": [1,0,0,1,0,0]}
    result = preprocess(image, {"id":"rotate", "rotation":rotation}, tmp_path / "output.png", 100)
    assert pdf.Pixmap(result["file"]).pixel(*location) == (0,)
    tsv = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    tsv += f"5\t1\t1\t1\t1\t1\t{location[0]}\t{location[1]}\t1\t1\t90\tX\n"
    assert parse_tsv(tsv,result)[0]["bbox_page"] == pytest.approx([0,0,1,1])


def test_missing_tsv_columns_rejected():
    pytest.importorskip("pymupdf")
    with pytest.raises(ValueError, match="TSV columns"):
        parse_tsv("broken\n", {})


def test_scoring_only_runs_on_accepted_aligned_targets(evidence, tmp_path):
    from asbuilt_matcher.clues import init_clues, add_clue, review_clue
    from asbuilt_matcher.clue_review import export_verified
    registry = tmp_path / "clues.json"
    init_clues(evidence, registry)
    clue = add_clue(registry, kind="street_name", text="NC 211 - SUPPLY ROAD", page_number=1,
                    bbox=[40,30,240,130], author="Synthetic extraction")
    review_clue(registry, clue["id"], author="Synthetic analyst", reason="independent test acceptance",
                status="verified", reviewer_type="human", independent=True)
    export_verified([registry], tmp_path / "truth", render_targets=True, analyst_only=True)
    truth = tmp_path / "truth" / "verified-clues.json"
    engine = {"ready":True,"executable":"synthetic","languages":["eng"]}
    def fake(args, **kwargs):
        base = Path(args[2])
        base.with_suffix(".txt").write_text("NC 211 - SUPPLY ROAD\n")
        base.with_suffix(".tsv").write_text("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t10\t20\t10\t90\tNC\n")
        return SimpleNamespace(returncode=0,stdout="",stderr="")
    with patch("asbuilt_matcher.ocr.probe_tesseract",return_value=engine), patch("asbuilt_matcher.ocr.subprocess.run",side_effect=fake):
        report = run_baseline(truth, tmp_path / "run", ground_truth_path=truth, config={"variants":[{"id":"baseline"}]})
    assert report["evaluation"]["status"] == "scored"
    assert report["comparison"][0]["metrics"]["transcription"]["exact_accuracy"] == 1
    assert report["comparison"][0]["metrics"]["entities"]["micro"]["f1"] == 1
    assert report["best_variants"]["exact_accuracy"] == ["baseline"]


@pytest.mark.parametrize("exit_code", [0, 1])
def test_empty_and_unsuccessful_recognitions_are_audited(tmp_path, exit_code):
    pytest.importorskip("pymupdf")
    from asbuilt_matcher.ocr import recognize
    def fake(args, **kwargs):
        base = Path(args[2])
        base.with_suffix(".txt").write_text("\n")
        base.with_suffix(".tsv").write_text("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n")
        return SimpleNamespace(returncode=exit_code, stdout="", stderr="synthetic stderr")
    processed = {"file":"synthetic.png", "dpi":200, "width":100, "height":100,
                 "processed_to_page":[1,0,0,1,0,0]}
    with patch("asbuilt_matcher.ocr.subprocess.run",side_effect=fake):
        if exit_code:
            with pytest.raises(RuntimeError, match="exited 1"):
                recognize(processed,tmp_path/'ocr',{"executable":"synthetic"},DEFAULT_CONFIG)
        else:
            result = recognize(processed,tmp_path/'ocr',{"executable":"synthetic"},DEFAULT_CONFIG)
            assert result["status"] == "empty" and result["confidence_mean"] is None
    assert "synthetic stderr" in (tmp_path / "engine.log").read_text()


def test_explicit_absolute_executable_bypasses_path_lookup(tmp_path):
    exe = tmp_path / "Approved Tools" / "tesseract.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"synthetic")
    calls = []
    def fake(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="tesseract 5.synthetic" if "--version" in args else "List of languages:\neng\nosd\n", stderr="")
    with patch("asbuilt_matcher.ocr.shutil.which", side_effect=AssertionError("PATH must not be used")), patch(
        "asbuilt_matcher.ocr.subprocess.run", side_effect=fake):
        report = probe_tesseract(str(exe.resolve()))
    assert report["ready"] and report["executable"] == str(exe.resolve())
    assert all(args[0] == str(exe.resolve()) for args in calls)
    assert report["version"] == "tesseract 5.synthetic" and "eng" in report["languages"]
    assert "word-level tsv" in report["adapter_outputs"]


def test_missing_absolute_override_never_falls_back_to_path(tmp_path):
    with patch("asbuilt_matcher.ocr.shutil.which", side_effect=AssertionError("No fallback")):
        report = probe_tesseract(str((tmp_path / "absent.exe").resolve()))
    assert not report["ready"] and report["executable"] is None


def test_all_six_variants_recognize_without_ground_truth(evidence, tmp_path):
    engine = {"ready":True,"executable":"synthetic","version":"tesseract synthetic","languages":["eng"]}
    calls = []
    def fake(args, **kwargs):
        calls.append(args)
        base = Path(args[2])
        base.with_suffix(".txt").write_text("NC 211 - SUPPLY ROAD\n")
        base.with_suffix(".tsv").write_text("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t10\t20\t10\t90\tNC\n")
        return SimpleNamespace(returncode=0,stdout="",stderr="")
    with patch("asbuilt_matcher.ocr.probe_tesseract", return_value=engine), patch("asbuilt_matcher.ocr.subprocess.run",side_effect=fake):
        report = run_baseline(evidence, tmp_path / "run")
    assert len(calls) == len(report["results"]) == 12  # two synthetic images, six variants
    assert report["status"] == "complete" and report["evaluation"]["status"] == "not_requested"
    assert {r["variant"] for r in report["results"]} == {v["id"] for v in DEFAULT_CONFIG["variants"]}
    for record in report["results"]:
        assert record["tesseract_version"] == engine["version"]
        assert record["ocr_configuration"]["language"] == "eng"
        assert record["source_image_sha256"] and record["preprocessing"]["id"] == record["variant"]
        assert record["command"][-2:] == ["txt", "tsv"] and record["words"]
    assert all(c["metrics"] is None for c in report["comparison"])
    assert (tmp_path / "run" / "REVIEW.html").read_text().count('<article ') == 12


def test_cli_saves_diagnostic_without_running_ocr(tmp_path, capsys):
    from asbuilt_matcher.cli import main
    path = tmp_path / "diagnostic.json"
    with patch("asbuilt_matcher.cli.probe_tesseract", return_value={"ready":False,"executable":None}):
        assert main(["ocr-check", "--output", str(path)]) == 1
    assert json.loads(path.read_text())["ready"] is False
