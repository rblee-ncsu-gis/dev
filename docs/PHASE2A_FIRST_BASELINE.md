# First measured OCR baseline

The live check now finds **Tesseract v5.4.0.20240606**, with `eng` and `osd`.
Nothing was installed or changed in the environment during readiness work.
Following the user's amended review and confirmation, all 11 references now have
recorded independent human acceptance, and the existing 66 outputs have been scored.
See [the first measured results](PHASE2A_MEASURED_RESULTS.md).
The instructions below remain applicable to future review/baseline snapshots.

Inspect the [visual report](../outputs/phase2a/recognition-readiness/REVIEW.html),
[attempt inventory](../outputs/phase2a/recognition-readiness/ocr-run.json) and
[comparison CSV](../outputs/phase2a/recognition-readiness/comparison.csv).
`recognized` means nonempty output, not correct transcription.

## 1. Confirm the engine

Run from the repository root. These are local PowerShell variables, not environment
settings. The bootstrap adds `src` only to its own process's import path; no
installation, PATH change or PYTHONPATH setting is needed:

```powershell
$pythonExe = 'C:\Users\ricky.lee\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone\python.exe'
$tesseractExe = 'C:\Users\ricky.lee\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
$tessdataDir = 'C:\Users\ricky.lee\AppData\Local\Programs\Tesseract-OCR\tessdata'
& $pythonExe scripts/run_asbuilt.py ocr-check --tesseract $tesseractExe --tessdata-dir $tessdataDir --output outputs/engine-check-next.json
```

Use a new output filename. Absolute overrides bypass PATH entirely; an invalid
override never falls back to another installation. The diagnostic reports the
resolved executable, version, languages, English availability and binary/model
hashes. It does not itself recognize an image. The completed exploratory run
separately confirms local English text and word-level TSV operation.

## 2. Inspect recognition independently of scoring

```powershell
& $pythonExe scripts/run_asbuilt.py ocr-run outputs/phase1c/verified-final/verified-clues.json --output outputs/exploratory-next --config config/ocr-baseline.json --tesseract $tesseractExe --tessdata-dir $tessdataDir
```

The historical export supplies images/transforms; its AI-reviewed text/types are
not fed into OCR. No ground-truth argument is needed. All six configured variants
run and `REVIEW.html` is generated automatically. Open it locally in a browser:
each result shows the original crop, processed image, word-box overlay, detected
text, confidence, page boxes and provenance. Variant/status filters help inspection.
The report is read-only and provides no clue approval or editing controls.

To create a portable report from an existing run without invoking OCR:

```powershell
& $pythonExe scripts/run_asbuilt.py ocr-report outputs/phase2a/recognition-readiness/ocr-run.json --output outputs/visual-review-next
```

Use new output directories. The HTML uses no external services/assets. External
source/processed images are snapshotted with hash checks; missing/changed evidence
is flagged rather than shown as original. Copy the whole report folder when sharing.

## 3. Obtain independent analyst acceptance

A real analyst must use the existing [review manifest](../outputs/phase1c/final-review/REVIEW.md)
and [acceptance workflow](PHASE2A_WORKFLOW.md#independent-analyst-acceptance-and-scoring)
to verify transcriptions and boxes with their actual identity, human reviewer type,
independence attestation and reason. Correct, reject or mark unreadable as needed.
Do not approve clues automatically from OCR similarity or copy acceptance flags
onto the historical AI export. No clue has been approved during this readiness work.

After that review, export accepted references using the existing command:

```powershell
& $pythonExe scripts/run_asbuilt.py clues-export outputs/phase1c/registries/c8.json outputs/phase1c/registries/c7.json --analyst-only --render-targets --output outputs/analyst-accepted-next
```

Check the accepted count. Empty exports cannot be scored; partial acceptance supports
only a labeled subset evaluation. Unreadable/rejected clues remain in history,
outside accuracy denominators. Box corrections require freshly rendered targets.

## 4. Run the measured baseline after both prerequisites are met

When the engine is operational and independently accepted references exist:

```powershell
& $pythonExe scripts/run_asbuilt.py ocr-run outputs/analyst-accepted-next/verified-clues.json --output outputs/measured-baseline-next --config config/ocr-baseline.json --tesseract $tesseractExe --tessdata-dir $tessdataDir --ground-truth outputs/analyst-accepted-next/verified-clues.json
```

Do not use the AI-reviewed Phase 1C export as measured ground truth. Evaluation
checks human independence and target ID/image-hash alignment. Inspect
`evaluation.status` separately from recognition status and exit code.

- `comparison.csv` / `COMPARISON.md`: all six variants, failures, exact target
  accuracy, character/word accuracy, geographic-entity precision/recall/F1 and
  false-positive counts. Unmeasured fields stay blank/null, not zero.
- `ocr-run.json` / individual `result.json`: engine version/location, language,
  OEM, PSM, timeout, variant parameters, source-image hash/path, timestamps,
  detected/raw text, word confidence and processed/page-coordinate bounding boxes.
  Configuration is retained even on failed attempts.
- `REVIEW.html`: source and OCR evidence side by side; accepted-reference audits
  appear only for results eligible for scoring.
- Per-variant `scores.json`, predictions, raw `ocr.txt` / `ocr.tsv` and diagnostics:
  inspect failed recognitions, typed false positives and missed entities.

## Metric definitions

Exact accuracy is entire-target match rate. Character error rate (CER) is character
edit distance / reference characters; **character accuracy = 1 − CER**. Word error
rate (WER) is token edit distance / reference words; **word accuracy = 1 − WER**.
Words are whitespace-separated, with case and punctuation significant. Character
scoring retains spacing/line breaks except CRLF-to-LF conversion. The adapter
separately preserves raw text and removes one engine terminal newline for predictions.
Insertions can make CER/WER exceed 1 and edit-based accuracy negative; values are
not clamped. These metrics differ from exact-target accuracy and engine confidence.

Typed geographic-entity precision/recall/F1 retain their separate normalization.
False-positive counts and per-target false-positive/missed-entity lists remain
auditable. Missing/failed outputs count as misses on accepted references; undefined
denominators are null. Do not rank methods by confidence or similarity to unaccepted
AI clues. Eleven targets from related sheets are insufficient for general production
accuracy; inspect border/symbol confusion, station punctuation and thin multiline
labels before expanding the reference collection.
