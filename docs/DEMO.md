# Demo Script

The demo has four layers. Only the last requires a Nutrient API key.

## 1. Offline Warning Case

A low-confidence field creates a warning and routes the decision to a human.
It does not pretend to be a Nutrient result.

```powershell
python -m trustdocs.cli --demo-warning
```

Expected path:

```text
WARNING -> human review -> APPROVED_BY_HUMAN
```

## 2. Offline Inconsistent Case

A typed extraction exposes a line-item table, so validation can check
arithmetic that a raw OCR pass cannot: the row quantities do not reconcile
with the invoice total, the check fails, and the run is routed to a human.

```powershell
python -m trustdocs.cli --demo-inconsistent
```

Expected path:

```text
line_items FAIL -> human review -> APPROVED_BY_HUMAN
```

## 3. Evidence Verification

These are sanitized real-run evidence artifacts. They contain hashes and
decision metadata, not document contents or extracted values. `verify`
recomputes the hash chain and replays the recorded decision offline: no
credentials, no network, no vendor call.

```powershell
python -m trustdocs.cli verify docs/evidence/rejected.json
python -m trustdocs.cli verify docs/evidence/approved.json
```

Both should return `VALID` and report the recorded decision.

## 4. Real Nutrient Run

Configure a Nutrient Data Extraction API key in the environment and use the
committed sample documents:

```powershell
$env:NUTRIENT_EXTRACTION_API_KEY = `
  [Environment]::GetEnvironmentVariable(
    "NUTRIENT_EXTRACTION_API_KEY", "User"
  )

python -m trustdocs.cli process sample/invoice.pdf --decision approve
python -m trustdocs.cli verify sample/invoice.pdf.evidence.json

python -m trustdocs.cli process sample/research-paper.pdf --decision reject
python -m trustdocs.cli verify sample/research-paper.pdf.evidence.json
```

The synthetic invoice exercises the happy path (required fields present,
non-negative total); the research paper is a deliberately wrong document type
and fails validation, demonstrating the rejection path for real.

The same path runs as a live test that skips itself without a key:

```powershell
python -m unittest tests.test_live_nutrient -v
```

Each real call consumes Nutrient API credits (free tier: 5,000/month). The
repository does not claim that a public CI runner has access to a private API
key.

## What This Demonstrates

- Nutrient performs the core document extraction operation.
- The pipeline preserves field-level confidence and citations.
- Typed structured extraction enables cross-field checks that raw text cannot.
- Validation runs before the human decision.
- Decisions are replayable offline: `verify` re-checks the recorded chain and
  decision without the vendor.
- Full remote extraction replay is not claimed: fields are not stored.
