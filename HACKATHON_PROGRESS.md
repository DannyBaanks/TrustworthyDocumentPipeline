# Hackathon Progress

Verifiable via `git log --oneline --date=short`. Every claim below maps to a
commit hash; nothing is asserted that the repository cannot prove.

## Timeline

| Date | Commit | What landed |
|------|--------|-------------|
| Aug 12 | `1735060` | Initial pipeline: Nutrient extraction adapter, evidence core, typed fields |
| Aug 12 | `a55656a` | Validation rules and explicit approve/reject decisions |
| Aug 12 | `5184ed5` | Verifiable provenance evidence (SHA-256 chain) |
| Aug 12 | `107c1a0` | Sample fixtures, line-item consistency rule, optional live test |
| Aug 13 | `952a10c` | Pretty CLI output, `--json` for scripting, CI badge |
| Aug 20 | `8e9f1ac` | Forensic ledger (chained JSONL), local extractor (no API key), auditor console (self-contained HTML) |
| Aug 20 | `9174aa5` | Error branch coverage, lint clean, Windows/Linux CI matrix |
| Aug 21 | `f9388c5` | GUI (PySide6), attack demo (8 scenarios), provider swap demo, threat model |
| Aug 21 | `b2b94ac` | 68 lint errors resolved |
| Aug 21 | `ff731bc` | GUI tests skip gracefully without PySide6 |
| Aug 21 | `5ace252` | Export button, build spec, docs updated |
| Aug 21 | `e5ec3d0` | README leads with the auditor console running |
| Aug 21 | `774a124` | README test count enforced by automated test (no hand-written numbers) |
| Sep 2 | (this session) | FieldConfidencePolicy (per-field gate, no aggregate invention), ReviewRecord (human review hash in evidence chain), DWS citation display in GUI, video script corrections |

## What each layer proves

| Layer | Git origin | What it does |
|-------|-----------|--------------|
| Evidence core | Aug 12 (`5184ed5`) | SHA-256 of document, extraction, and decision; tamper-evident record |
| Validation rules | Aug 12 (`a55656a`) | Required fields, non-negative numbers, confidence warnings |
| Line-item arithmetic | Aug 12 (`107c1a0`) | Computes quantity x unit_price, compares to stated total |
| Chained ledger | Aug 20 (`8e9f1ac`) | Append-only JSONL; edit/delete/reorder/insert all detected |
| Tail anchor | Aug 20 (`8e9f1ac`) | Publish head hash externally; truncation becomes visible |
| Auditor console | Aug 20 (`8e9f1ac`) | Single HTML file; recomputes every hash in the browser |
| Local extractor | Aug 20 (`8e9f1ac`) | Vendor-independent; no API key; deliberately worse, intentionally honest about confidence |
| Attack suite | Aug 21 (`f9388c5`) | 8 scenarios: document swap, extraction tamper, decision forgery, ledger edit/delete/reorder, truncation, anchor detection |
| Provider swap | Aug 21 (`f9388c5`) | Same document, two extractors, same evidence contract |
| GUI | Aug 21 (`f9388c5`) | Desktop app wrapping the same pipeline API |
| CI matrix | Aug 20 (`9174aa5`) | Windows + Linux, Python 3.11/3.12/3.13 |
| FieldConfidencePolicy | Sep 2 | Per-field threshold gate; no aggregate confidence invented |
| ReviewRecord | Sep 2 | Human review hash enters the evidence chain |
| DWS citations | Sep 2 | Per-field confidence + source location shown in GUI |

## Test count

The README test count is enforced by `tests/test_readme_claims.py`: if someone
writes a number that does not match the actual suite count, the test fails.
This is the project's own evidence principle applied to its own claims.

## The诚实 sentence

> The product doesn't ask auditors to trust its AI.
> It doesn't ask judges to trust its business claims either.
>
> Measured facts are reproducible.
> Assumptions are labeled.
> Unknowns remain unknown.
>
> That is the mark of Trustworthy.
