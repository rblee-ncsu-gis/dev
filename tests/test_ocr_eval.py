import json

import pytest

from asbuilt_matcher.ocr_eval import score_predictions, score_files


def truth():
    data = {"clues": [
        {"clue_id": "road", "text": "SUPPLY ROAD", "kind": "street_name", "source_pdf": "test.pdf", "verification_status": "verified"},
        {"clue_id": "sheet", "text": "C8", "kind": "sheet_number", "source_pdf": "test.pdf", "verification_status": "verified"}]}
    for row in data["clues"]:
        row.update(reviewer_type="human", independent_review=True, reviewer="Synthetic independent reviewer",
                   extraction_author="Synthetic extraction", review_reason="Synthetic accepted label",
                   review_timestamp="2026-10-16T00:00:00Z")
    return data


def test_exact_text_and_entities_are_separate():
    result = score_predictions(truth(), {"predictions": [
        {"clue_id": "road", "text": "Supply Road", "entities": [{"kind": "street_name", "text": "Supply  Road"}]},
        {"clue_id": "sheet", "text": "C8", "entities": []}]})
    assert result["transcription"]["exact_accuracy"] == 0.5
    assert result["transcription"]["character_error_rate"] > 0
    assert result["entities"]["micro"]["f1"] == 1


def test_missing_predictions_penalize_recall_and_exact_accuracy():
    result = score_predictions(truth(), {"predictions": []})
    assert result["transcription"]["exact_accuracy"] == 0
    assert result["entities"]["micro"]["recall"] == 0
    assert result["entities"]["micro"]["precision"] is None


def test_duplicate_entities_are_false_positives():
    result = score_predictions(truth(), {"predictions": [
        {"clue_id": "road", "text": "SUPPLY ROAD", "entities": [{"kind": "street_name", "text": "SUPPLY ROAD"}] * 2},
        {"clue_id": "sheet", "text": "C8", "entities": [{"kind": "street_name", "text": "C8"}]}]})
    assert result["entities"]["micro"]["true_positive"] == 1
    assert result["entities"]["micro"]["false_positive"] == 2


@pytest.mark.parametrize("ids", [["unknown"], ["road", "road"]])
def test_invalid_prediction_ids(ids):
    with pytest.raises(ValueError):
        score_predictions(truth(), {"predictions": [{"clue_id": i, "text": "x", "entities": []} for i in ids]})


def test_file_reports_and_unverified_truth_rejected(tmp_path):
    t, p = tmp_path / "truth.json", tmp_path / "predictions.json"
    t.write_text(json.dumps(truth()))
    p.write_text(json.dumps({"predictions": []}))
    result = score_files(t, p, tmp_path / "out")
    assert result["transcription"]["targets"] == 2
    assert (tmp_path / "out" / "targets.csv").exists()
    data = truth()
    data["clues"][0]["verification_status"] = "unreadable"
    with pytest.raises(ValueError):
        score_predictions(data, {"predictions": []})


@pytest.mark.parametrize("reviewer_type,independent", [("ai", True), ("ai", False), ("human", False), ("unspecified", True)])
def test_ai_and_nonindependent_labels_cannot_be_scored(reviewer_type, independent):
    data = truth()
    data["clues"][0].update(reviewer_type=reviewer_type, independent_review=independent)
    with pytest.raises(ValueError, match="independently analyst"):
        score_predictions(data, {"predictions": []})


def test_engineering_false_positive_is_retained_for_review():
    result = score_predictions(truth(), {"predictions": [
        {"clue_id": "road", "text": "PVC ROAD", "entities": [{"kind": "street_name", "text": "PVC ROAD"}]}]})
    assert result["targets"][0]["false_positive_entities"] == [{"kind": "street_name", "text": "PVC ROAD", "count": 1}]
    assert result["targets"][0]["missed_entities"][0]["text"] == "SUPPLY ROAD"


def test_character_and_word_accuracy_are_edit_based():
    result = score_predictions(truth(), {"predictions": [
        {"clue_id":"road", "text":"SUPPLY LANE", "entities":[]},
        {"clue_id":"sheet", "text":"C8", "entities":[]}]})
    metrics = result["transcription"]
    assert metrics["reference_words"] == 3 and metrics["word_errors"] == 1
    assert metrics["word_error_rate"] == pytest.approx(1/3)
    assert metrics["word_accuracy"] == pytest.approx(2/3)
    assert metrics["character_accuracy"] == 1 - metrics["character_error_rate"]
    assert metrics["exact_accuracy"] == 0.5


def test_insertion_heavy_word_accuracy_is_not_silently_clamped():
    data = truth()
    data["clues"] = [data["clues"][1]]
    result = score_predictions(data, {"predictions":[{"clue_id":"sheet", "text":"C8 EXTRA WORDS", "entities":[]}]})
    assert result["transcription"]["word_accuracy"] == -1
