# Demo script

Seven layers. **Only the last needs a Nutrient API key** — everything before it
runs offline, which is also the path a reviewer without credentials will take.

The order is deliberate: each layer answers the objection the previous one
raises. It matches [`VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md), so this file can be
followed while recording.

---

## 1. A clean document

```sh
python -m trustdocs.cli --demo
```

Extraction is confident, validation passes, and it auto-approves. Note the two
hashes: one for the document, one for the evidence record of the decision.

## 2. A document that looks clean and is not

```sh
python -m trustdocs.cli --demo-inconsistent
```

```text
  Status:       ✓ APPROVED_BY_HUMAN
  Validation:
    ✗ line-items-reconcile -- line item totals do not reconcile with total
```

Every field extracted cleanly at high confidence. The line items still do not
add up to the stated total.

**This is the point of typed extraction.** Free-form OCR alone does not provide
Comparing `Σ(quantity × unit_price)` against the total needs line items as
*numbers*, which is what the DWS schema provides. Every individual field can be
right while the document as a whole is internally inconsistent.

## 3. Low confidence stops for a human

```sh
python -m trustdocs.cli --demo-warning
```

The confidence gate routes the decision to a person rather than guessing.

## 4. Verifying a decision months later

```sh
python -m trustdocs.cli verify docs/evidence/rejected.json
```

```text
✓ VALID
  Recorded decision: REJECTED
```

No API key. No network. The hash chain is recomputed locally and the recorded
outcome reported.

To see it fail, copy that file, change one character of any hash, and verify the
copy.

## 5. One decision is not an audit trail

A single record proves its own integrity and nothing about its neighbours:
delete one file and the rest still verify perfectly. So decisions are chained.

```sh
python -m trustdocs.cli --demo              --ledger ledger.jsonl
python -m trustdocs.cli --demo-warning      --ledger ledger.jsonl
python -m trustdocs.cli --demo-inconsistent --ledger ledger.jsonl

python -m trustdocs.cli ledger summary --ledger ledger.jsonl
python -m trustdocs.cli ledger verify  --ledger ledger.jsonl
```

Editing, deleting, reordering or inserting an entry breaks verification and
names the entry where the chain fails.

### The limitation, and how it closes

Cutting entries off the **end** leaves a shorter chain that is genuinely intact.
No self-contained log can tell that apart from a log that simply stopped.

```sh
python -m trustdocs.cli ledger head --ledger ledger.jsonl --json
# publish that value somewhere the writer cannot reach, then later:
python -m trustdocs.cli ledger verify --ledger ledger.jsonl --expect-head "<value>"
```

```text
! ledger verify: INVALID
  ✗ head mismatch -- entries were removed from the end
```

## 6. Attacks, and the auditor's own console

```sh
python -m trustdocs attack
```

Eight tampering attempts, **7 detected**, and the eighth reported as the known
limitation above rather than hidden.

```sh
python -m trustdocs.cli ledger console --ledger ledger.jsonl --evidence console.html
```

One self-contained HTML file: no server, no network, opens from a USB stick.
It does not show a verdict computed by this tool — it embeds the ledger and
recomputes every SHA-256 in the auditor's own browser.

### Same evidence, a different extractor

```sh
python -m trustdocs swap
```

Runs one document through the DWS adapter and through a local regex extractor
that shares nothing with it but the interface. Both produce valid evidence.

The local one is deliberately worse, and what it exposes is the interesting
part: a regex has no calibrated confidence, so it reports **none** — and the
existing policy then sends every such document to a human. The system degrades
into caution rather than into confident nonsense.

## 7. The real Nutrient run *(needs a key)*

```sh
python -m trustdocs.cli process sample/invoice.pdf --decision approve
python -m trustdocs.cli verify  sample/invoice.pdf.evidence.json

python -m trustdocs.cli process sample/research-paper.pdf --decision reject
python -m trustdocs.cli verify  sample/research-paper.pdf.evidence.json
```

The research paper is the "wrong document type" path. Each call consumes
Nutrient credits (the free tier includes 5,000/month).

Note the `verify` lines depend on the `process` line above them: they read the
evidence that call writes. `sample/invoice.pdf.evidence.json` ships with the
repository and can be verified without a key; the research-paper one does not,
so it only exists after you run the command above it.

```sh
python -m unittest tests.test_live_nutrient -v
```

CI runs the full suite **without** a key; the live test ships with the repo and
skips itself when the key is absent.

## The desktop app

```sh
python -m trustdocs.gui
```

Same pipeline behind a window: pick a document, choose the extractor
(`local` needs no key), process, verify, run the tamper demo, export.

---

## What this demonstrates

| Layer | Claim |
|---|---|
| 2 | A check no text pipeline can make, enabled by typed extraction |
| 3 | Low confidence stops rather than guesses |
| 4 | A decision is re-checkable offline, with no vendor and no key |
| 5 | The set of decisions is verifiable, not just each one — and where that stops |
| 6 | Tampering is detected, and the auditor need not trust this tool |
| 6 | The evidence layer survives replacing the extractor underneath |
| 7 | It works against the real service, end to end |

Everything except layer 7 runs with no credentials, so any of it can be
reproduced by someone who has just cloned the repository.
