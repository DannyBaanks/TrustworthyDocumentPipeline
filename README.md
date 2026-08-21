# Trustworthy Document Pipeline

**When an AI approves an invoice, prove what it actually saw.**

[![tests](https://github.com/DannyBaanks/trustworthy-document-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/DannyBaanks/trustworthy-document-pipeline/actions/workflows/tests.yml)

| | |
|---|---|
| Offline demos | ✅ No API key needed |
| Core tests | ✅ 142/142 passing |
| Live integration | ✅ Skips without credentials |
| Evidence verifier | ✅ SHA-256 chain |
| Self-contained auditor | ✅ Single HTML file |
| Attack demo | ✅ `python -m trustdocs attack` |
| Provider swap | ✅ `python -m trustdocs swap` |

Built for the **Nutrient DWS Challenge** — DevNetwork [API + Cloud + AI] Hackathon 2026.

> **Nutrient's role in one line:** the DWS Data Extraction API turns a PDF into
> typed, confidence-scored fields, which is what makes an automated decision
> checkable instead of a guess about pixels.

---

## The problem

Companies are pointing AI at their invoices right now. A model reads the PDF, a
person clicks approve, the number lands in the accounting system.

Six months later something is wrong — a duplicate payment, a vendor that does
not exist, an auditor asking questions. Somebody pulls the log and finds this:

```
2026-03-14 14:32:07  user:accounts-payable-3  action:approve  invoice_id:4471
```

That line says a human approved something. It does not say **what they were
looking at**. Not which fields the model extracted, not how confident it was,
not whether the totals even added up. The document may have been edited since.
The model has been upgraded twice. Nothing can be reconstructed.

The approval is recorded. The *basis* for the approval is gone.

## What this does

It makes the basis part of the record.

```text
document  ->  DWS extraction  ->  validation rules  ->  confidence gate
          ->  human review when needed  ->  evidence you can re-check later
```

Every run emits an evidence record containing the SHA-256 of the document, of
the extraction, and of the decision. Months later, `verify` recomputes that
chain **offline** — no API key, no network, no vendor call — and tells you
whether the record still matches what was decided.

Change one byte of the document and the chain breaks. Edit the stored evidence
and the chain breaks. That is the whole point.

## What it guarantees and what it does not

| Property | Status |
|----------|--------|
| Document integrity recorded | ✅ |
| Extraction integrity recorded | ✅ |
| Decision integrity recorded | ✅ |
| Tampering detected | ✅ |
| Reordering detected | ✅ |
| Insertion detected | ✅ |
| Tail truncation without anchor | ❌ |
| Offline extraction replay | ❌ |
| Offline decision revalidation | ✅ |

This table is what the attack demo proves: run `python -m trustdocs attack`
to see every row verified automatically.

## See it in 60 seconds

```sh
python -m pip install -e .
python -m trustdocs.cli --demo-inconsistent
```

```text
Trustworthy Document Pipeline
----------------------------------
  Status:       ✓ APPROVED_BY_HUMAN
  Document:     sha256:455395037fc90098...
  Fields:       3 extracted
  Reviewed:     yes (human)
  Validation:
    ✗ line-items-reconcile -- line item totals do not reconcile with total
  Evidence:     sha256:3cb4b065b4eec4c2...
  Execution ID: 2d33989d3868a5277a2c81c2815fa291c17e395b739ac18b9f4a8e24a5c4858a
----------------------------------
```

That invoice looked fine. Every field extracted cleanly, with high confidence.

**But the line items do not add up to the total.** The pipeline caught it,
refused to auto-approve, and routed it to a human — and the reason it stopped
is written into the evidence, not just into a log line.

Then verify a decision from months ago, with no credentials and no network:

```sh
python -m trustdocs.cli verify docs/evidence/rejected.json
```

```text
✓ VALID
  Recorded decision: REJECTED
```

## One decision is not an audit trail

A single evidence record proves its own integrity and nothing about its
neighbours. Delete one file from a folder of evidence and every remaining file
still verifies perfectly — which is no help against the first question an
auditor asks: *show me that nothing is missing.*

So decisions are chained. Each ledger entry carries the hash of the one before
it:

```sh
python -m trustdocs.cli --demo              --ledger ledger.jsonl
python -m trustdocs.cli --demo-warning      --ledger ledger.jsonl
python -m trustdocs.cli --demo-inconsistent --ledger ledger.jsonl

python -m trustdocs.cli ledger verify --ledger ledger.jsonl
```

Edit, delete, reorder or insert an entry and verification fails, naming the
entry where the chain breaks.

**And here is what it still cannot do.** Cut entries off the *end* and what
remains is a genuinely intact, genuinely consecutive, shorter chain. No
self-contained log can tell that apart from a log that simply stopped. There is
a test named after this weakness so it cannot quietly disappear from the docs:
`test_LIMITATION_truncating_the_tail_is_not_detectable`.

Closing it needs an anchor kept where the writer cannot reach:

```sh
HEAD=$(python -m trustdocs.cli ledger head --ledger ledger.jsonl --json | jq -r .head)
# ...publish $HEAD from CI, then later:
python -m trustdocs.cli ledger verify --ledger ledger.jsonl --expect-head "$HEAD"
```

```text
! ledger verify: INVALID
  ✗ head mismatch -- ledger ends at '757765d7...' but the published anchor
    says 'f66999ab...'; entries were removed from the end
```

The record leaves the system and comes back in. Without that round trip the
guarantee would be a claim, not a property.

## The auditor console

```sh
python -m trustdocs.cli ledger console --ledger ledger.jsonl --evidence console.html
```

One self-contained HTML file. No server, no network, no build — it opens from a
USB stick in a room with no internet.

It does **not** display a verification result computed by this tool. It embeds
the ledger and recomputes every SHA-256 in the auditor's browser. Anyone asked
to trust a report produced by the system under audit has been given a claim,
not evidence. (`crypto.subtle` is unavailable over `file://`, so the page
carries its own digest implementation, and a test runs that JavaScript under
Node to confirm it agrees with Python — including on non-ASCII values, where
the two languages canonicalise differently and quietly disagreed until that
test was written.)

## Not tied to one extraction vendor

The evidence layer is worth something only if it survives the model underneath
being replaced. So the repo ships a second extractor that shares nothing with
the DWS path except the interface:

```sh
python -m trustdocs.cli process sample/invoice.pdf --extractor local --decision approve
```

It needs no key and no network, and it is deliberately worse — a handful of
regexes that cannot read tables. The interesting part is what it does about
confidence: a regex has no calibrated probability behind it, so it reports
**none**, and the existing policy routes every such document to a human.

**A extractor that admits it cannot say how sure it is degrades into caution
rather than into confident nonsense.** That property was already in the
pipeline; the second adapter just makes it visible.

Two different extractors, one valid chain — that is vendor independence
demonstrated rather than asserted. See [`docs/BUSINESS_CASE.md`](docs/BUSINESS_CASE.md)
for why that is the thing that makes this a business.

## The check no text pipeline can make

`line-items-reconcile` computes `Σ(quantity × unit_price)` and compares it to
the stated total.

Free-form OCR cannot do this. It returns text, and text has no arithmetic. You
need **typed fields with declared types** — `line_items` as an array of objects
with numeric `quantity` and `unit_price`, `total_amount` as a number — which is
exactly what the DWS extraction schema provides.

This is the concrete argument for typed extraction over dumping a page into an
LLM and hoping: a schema lets you write rules that catch documents where every
individual field is right and the document as a whole is wrong.

## Who pays for this

Anyone running automated document decisions under an obligation to explain
them later:

- **Accounts payable teams** automating invoice intake. The failure mode is
  paying an invoice nobody can later justify approving.
- **Regulated industries** — insurance, healthcare, financial services — where
  "the model decided" is not an acceptable answer to a regulator.
- **Anyone deploying document AI in the EU.** Regulations like the AI Act
  require traceability for automated decisions. A log line saying "approved"
  does not meet that bar.

The product is not the extraction; Nutrient does that, and does it well. The
product is the **evidence layer that sits on top of any extraction service** and
survives the model being replaced underneath. That is what makes it a business
rather than a script: it is vendor-agnostic by construction, and the value grows
with how much you automate.

## Every mode, offline

Three fixtures, no API key required:

```sh
python -m trustdocs.cli --demo              # clean invoice, auto-approved
python -m trustdocs.cli --demo-warning      # low confidence -> human review
python -m trustdocs.cli --demo-inconsistent # totals do not reconcile -> human review
```

Output is human-readable by default and shows **which rules fired, never the
extracted values** — the evidence proves what was decided without leaking the
contents of the document. Pass `--json` for machine-readable output.

## The real Nutrient run

The repository ships two sample documents (see [`sample/README.md`](sample/README.md)):
a synthetic invoice for the happy path, and an open-access research paper for
the "wrong document type" path.

```sh
python -m trustdocs.cli process sample/invoice.pdf --decision approve
python -m trustdocs.cli verify sample/invoice.pdf.evidence.json

python -m trustdocs.cli process sample/research-paper.pdf --decision reject
python -m trustdocs.cli verify sample/research-paper.pdf.evidence.json
```

Each real call consumes Nutrient API credits (the free tier includes 5,000 per
month). With a key configured, the live integration suite runs the real
contract end to end:

```sh
python -m unittest tests.test_live_nutrient -v
```

CI runs the full unit suite **without an API key**. The live test ships with the
repo and skips itself when the key is absent, so the public build is
reproducible by anyone and the real path stays exercisable by whoever has
credentials.

## What this deliberately does not claim

Replay of the *extraction* is not advertised. The evidence verifies integrity;
it does not reconstruct the remote extraction without calling Nutrient again.

What replays offline is the **decision**: `verify` recomputes the hash chain and
reports the recorded outcome with no vendor call, so an auditor can re-check an
outcome without credentials or network access.

The evidence is tamper-evident, not tamper-proof. It proves a record was not
altered after the fact; it does not prevent someone from recording a decision
they should not have made. That is a different problem, and pretending
otherwise would undermine the one this actually solves.

## Design requirements

- DWS performs a meaningful core document operation, not a decorative call.
- Low-confidence extraction stops for human review.
- Every decision is verifiable from recorded input and output hashes.
- Each run exposes an `execution_id` derived from document hash, operation, and
  normalized configuration.
- Secrets arrive through environment or deployment configuration.
- No absolute machine path is part of the application contract.

See [`docs/DEMO.md`](docs/DEMO.md) for the offline cases, sanitized evidence
verification, and the real Nutrient run, and
[`docs/CASE_DECISION.md`](docs/CASE_DECISION.md) for the extraction schema.

## Visual Demo

A native GUI wraps the pipeline for non-technical users and hackathon judges.

```sh
pip install -e ".[gui]"
python -m trustdocs.gui
```

The GUI provides:

- **Document selection** — pick a PDF, see its hash
- **Extractor selector** — switch between Nutrient DWS and local
- **Pipeline execution** — process with background thread (no UI freeze)
- **Extraction viewer** — fields, confidence, provenance
- **Validation viewer** — rules fired, pass/warn/fail status
- **Decision viewer** — status, reason, confidence gate
- **Evidence viewer** — full JSON, verification status
- **Tamper demo** — modifies a copy, shows INVALID detection
- **Ledger verification** — chain integrity check
- **Export** — save evidence to any path

The GUI calls the same pipeline API as the CLI. No logic is duplicated.

## License

MIT. See [`LICENSE`](LICENSE).
