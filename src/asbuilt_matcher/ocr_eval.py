"""Score supplied OCR/NER predictions; never invokes an OCR engine."""

from collections import Counter
import csv
import json
from pathlib import Path

from .clues import CLUE_KINDS
from .pdf_extract import file_sha256, write_json
from .clue_review import analyst_accepted

GEOGRAPHIC_KINDS = CLUE_KINDS - {"sheet_number", "station_range"}


def entity_text(text):
    # This normalization is only for entity matching, never strict OCR accuracy.
    return " ".join(text.upper().replace("–", "-").replace("—", "-").split())


def character_distance(left, right):
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def score_predictions(ground_truth, predictions):
    """One target per clue; missing outputs fail exact match and reduce entity recall.

    Entity truth consists of the typed clue value for geographic kinds. Other clue
    kinds are context targets. Precision is limited to this annotated target set.
    """
    truth = ground_truth["clues"]
    expected = {row["clue_id"]: row for row in truth}
    if len(expected) != len(truth) or not truth:
        raise ValueError("Ground truth must have unique clue IDs and at least one verified clue")
    if any(not analyst_accepted(r) or not r["text"] for r in truth):
        raise ValueError("Ground truth requires independently analyst-accepted nonempty transcriptions; AI/unspecified review is ineligible")
    predicted = {}
    for row in predictions["predictions"]:
        clue_id = row["clue_id"]
        if clue_id not in expected or clue_id in predicted:
            raise ValueError("Prediction IDs must be unique and belong to this ground truth")
        if not isinstance(row.get("text"), str) or not isinstance(row.get("entities"), list):
            raise ValueError("Each prediction requires text and entities (use [] for none)")
        if any(e.get("kind") not in GEOGRAPHIC_KINDS or not isinstance(e.get("text"), str)
               or not e["text"].strip() for e in row["entities"]):
            raise ValueError("Entities require a geographic kind and nonblank text")
        predicted[clue_id] = row
    counts = {"true_positive": 0, "false_positive": 0, "false_negative": 0}
    per_kind, rows, exact, errors, chars = {}, [], 0, 0, 0
    word_errors, reference_words = 0, 0
    for target in truth:
        actual = predicted.get(target["clue_id"], {"text": "", "entities": []})
        reference = target["text"].replace("\r\n", "\n")
        observed = actual["text"].replace("\r\n", "\n")
        matched = observed == reference
        exact += matched
        distance = character_distance(reference, observed)
        errors += distance
        chars += len(reference)
        tokens = reference.split()
        token_errors = character_distance(tokens, observed.split())
        word_errors += token_errors
        reference_words += len(tokens)
        gold = Counter([(target["kind"], entity_text(reference))]) if target["kind"] in GEOGRAPHIC_KINDS else Counter()
        found = Counter((e["kind"], entity_text(e["text"])) for e in actual["entities"])
        good, extra, missed = gold & found, found - gold, gold - found
        for label, counter in [("true_positive", good), ("false_positive", extra), ("false_negative", missed)]:
            counts[label] += sum(counter.values())
            for (kind, _), number in counter.items():
                per_kind.setdefault(kind, dict.fromkeys(counts, 0))[label] += number
        rows.append({"clue_id": target["clue_id"], "source_pdf": target["source_pdf"],
                     "kind": target["kind"], "reference": reference, "prediction": observed,
                     "prediction_missing": target["clue_id"] not in predicted, "exact_match": matched,
                     "character_errors": distance, "word_errors": token_errors,
                     "reference_words": len(tokens), "true_positive": sum(good.values()),
                     "false_positive": sum(extra.values()), "false_negative": sum(missed.values())})
        rows[-1].update(false_positive_entities=[{"kind": k, "text": t, "count": n} for (k, t), n in extra.items()],
                        missed_entities=[{"kind": k, "text": t, "count": n} for (k, t), n in missed.items()])
    def rates(values):
        tp, fp, fn = values["true_positive"], values["false_positive"], values["false_negative"]
        return {**values, "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}
    return {"schema_version": 1, "run": predictions.get("run", {}),
            "scope": "annotated clue targets only; not full-page entity precision or GIS accuracy",
            "transcription": {"targets": len(truth), "exact_matches": exact, "exact_accuracy": exact / len(truth),
                              "character_errors": errors, "reference_characters": chars,
                              "character_error_rate": errors / chars,
                              "character_accuracy": 1 - errors / chars,
                              "word_errors": word_errors, "reference_words": reference_words,
                              "word_error_rate": word_errors / reference_words if reference_words else None,
                              "word_accuracy": 1 - word_errors / reference_words if reference_words else None},
            "entities": {"micro": rates(counts), "per_kind": {k: rates(v) for k, v in per_kind.items()}},
            "targets": rows}


def score_files(truth_path, predictions_path, output):
    truth_path, predictions_path = Path(truth_path), Path(predictions_path)
    result = score_predictions(json.loads(truth_path.read_text(encoding="utf-8")),
                               json.loads(predictions_path.read_text(encoding="utf-8")))
    result["inputs"] = {"ground_truth_sha256": file_sha256(truth_path),
                        "predictions_sha256": file_sha256(predictions_path)}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "scores.json", result)
    with (output / "targets.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, list(result["targets"][0]))
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()}
                         for row in result["targets"])
    return {"transcription": result["transcription"], "entities": result["entities"]}
