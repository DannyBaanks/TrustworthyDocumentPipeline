# Demo Script

The demo has three layers. Only the third requires a Nutrient API key.

## 1. Offline Warning Case

This proves that a low-confidence field creates a warning and routes the
decision to a human. It does not pretend to be a Nutrient result.

```powershell
python -m trustdocs.cli --demo-warning
```

Expected path:

```text
WARNING -> human review -> APPROVED_BY_HUMAN
```

## 2. Evidence Verification

These are sanitized real-run evidence artifacts. They contain hashes and
decision metadata, not document contents or extracted values.

```powershell
python -m trustdocs.cli verify docs/evidence/rejected.json
python -m trustdocs.cli verify docs/evidence/approved.json
```

Both should return `VALID`.

## 3. Real Nutrient Run

Configure a Nutrient Data Extraction API key in the environment and use a
non-sensitive PDF:

```powershell
$env:NUTRIENT_EXTRACTION_API_KEY = `
  [Environment]::GetEnvironmentVariable(
    "NUTRIENT_EXTRACTION_API_KEY", "User"
  )

python -m trustdocs.cli process .\document.pdf --decision reject
python -m trustdocs.cli verify .\document.pdf.evidence.json
```

The real path uses Nutrient's `/extraction/extract` operation with a typed
invoice schema and per-field citations. The repository does not claim that a
public CI runner has access to a private API key.

## What This Demonstrates

- Nutrient performs the core document extraction operation.
- The pipeline preserves field-level confidence and citations.
- Validation runs before the human decision.
- Evidence integrity can be verified without storing document contents.
- The demo does not claim full remote extraction replay.
