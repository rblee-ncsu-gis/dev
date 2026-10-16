import json

import pytest

from asbuilt_matcher.clues import init_clues, add_clue, review_clue


@pytest.fixture
def registry(tmp_path):
    manifest = tmp_path / "raster-manifest.json"
    manifest.write_text(json.dumps({"source": {"sha256": "a" * 64}, "run_id": "test",
                                   "coordinates": "unrotated page points", "pages": [
                                       {"page_number": 1, "bounds": [0, 0, 300, 200]}]}))
    target = tmp_path / "clues.json"
    init_clues(manifest, target)
    return target


def test_correction_preserves_original_and_resets_verification(registry):
    clue = add_clue(registry, kind="street_name", text="Supp1y Road", page_number=1,
                    bbox=[10, 10, 100, 30], author="analyst")
    assert clue["verification_status"] == "unverified"
    review_clue(registry, clue["id"], author="reviewer", reason="read original", status="verified")
    corrected = review_clue(registry, clue["id"], author="analyst", reason="fix transcription",
                            text="Supply Road", bbox=[9, 9, 101, 31])
    assert corrected["original_text"] == "Supp1y Road"
    assert corrected["verification_status"] == "unverified" and corrected["verification"] is None
    assert corrected["history"][1]["before"]["verification_status"] == "verified"
    assert corrected["history"][1]["after"]["bbox"] == [9, 9, 101, 31]


def test_survey_coordinate_requires_explicit_crs_and_units(registry):
    with pytest.raises(ValueError):
        add_clue(registry, kind="survey_coordinate", text="N 100 E 200", page_number=1,
                 bbox=[0, 0, 50, 50], author="analyst")
    clue = add_clue(registry, kind="survey_coordinate", text="N 100 E 200", page_number=1,
                    bbox=[0, 0, 50, 50], author="analyst",
                    coordinates={"x": 200, "y": 100, "crs": None, "units": None})
    assert clue["coordinates"]["crs"] is None
    corrected = review_clue(registry, clue["id"], author="analyst", reason="unit note",
                            coordinates={"x": 200, "y": 100, "crs": None, "units": "feet"})
    assert corrected["coordinates"]["units"] == "feet"


def test_invalid_entry_does_not_write(registry):
    before = registry.read_bytes()
    for kwargs in [{"kind": "unknown"}, {"bbox": [0, 0, 500, 200]}, {"page_number": 2}, {"text": " "}]:
        args = dict(kind="street_name", text="Supply Road", page_number=1, bbox=[0, 0, 10, 10], author="analyst")
        args.update(kwargs)
        with pytest.raises(ValueError):
            add_clue(registry, **args)
    assert registry.read_bytes() == before
    with pytest.raises(ValueError):
        review_clue(registry, "absent", author="analyst", reason="unknown")
