from types import SimpleNamespace
from unittest.mock import patch

from asbuilt_matcher.environment import check_environment
from asbuilt_matcher.cli import main


def test_missing_imports_are_reported():
    with patch("asbuilt_matcher.environment.importlib.import_module", side_effect=ImportError("missing")):
        report = check_environment()
    assert not report["pdf_ready"]
    assert all(p["status"] == "error" for p in report["packages"].values())


def test_license_checks_do_not_checkout():
    calls = []
    arcpy = SimpleNamespace(
        GetInstallInfo=lambda: {"Version": "synthetic"}, ProductInfo=lambda: "ArcInfo",
        CheckExtension=lambda name: calls.append(name) or "NotLicensed",
    )

    def fake_import(name):
        if name == "arcpy":
            return arcpy
        raise ImportError(name)

    with patch("asbuilt_matcher.environment.importlib.import_module", side_effect=fake_import):
        report = check_environment()
    assert calls == ["Spatial", "ImageAnalyst"]
    assert report["packages"]["arcpy"]["extensions"]["Spatial"] == "NotLicensed"


def test_cli_reports_failure(capsys):
    assert main(["extract", "absent.pdf", "--output", "unused"]) == 1
