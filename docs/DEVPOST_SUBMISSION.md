# Devpost submission — copy-paste source

Every figure below is recomputable from this repository. Nothing here was
typed from memory.

---

## Project name

**Trustworthy Document Pipeline**

## Tagline (one line)

> When an AI approves an invoice, prove what it actually saw.

## Nutrient DWS's role (one line, required by the track)

> The DWS Data Extraction API turns a PDF into typed, confidence-scored fields
> with a source citation per value — which is what makes an automated decision
> checkable instead of a guess about pixels.

## Where DWS does the heavy lifting (one line, required by the track)

> Extraction is the operation this product cannot hand-wave: DWS returns *typed*
> fields (line items as arrays of numbers, totals as numbers) with per-field
> confidence and citations, and that is what lets a rule compute
> `Σ(quantity × unit_price)` and catch a document whose fields are all right and
> whose totals do not add up.

---

## The brand

> The product doesn't ask auditors to trust its AI. It doesn't ask judges to
> trust its business claims either. Measured facts are reproducible. Assumptions
> are labeled. Unknowns remain unknown. That is the mark of Trustworthy.

---

## Inspiration

Companies are pointing AI at their invoices right now. A model reads the PDF, a
person clicks approve, the number lands in the accounting system.

Six months later something is wrong — a duplicate payment, a vendor nobody
recognises, an auditor asking questions. Somebody pulls the log and finds this:

```
2026-03-14 14:32:07  user:accounts-payable-3  action:approve  invoice_id:4471
```

That line records that a human approved something. It does not record **what
they were looking at**. Not which fields the model extracted, not how confident
it was, not whether the totals even added up. The document may have been edited
since. The model has been upgraded twice.

The approval survives. The basis for it is gone.

That gap is the whole project. Not better extraction — Nutrient does that, and
does it well — but making the basis for a decision part of the record.

## What it does

The track asks for pipelines with **deterministic output** and **human-in-the-loop
workflows**, applied to real regulated document problems. This is e-invoicing —
one of the scenarios Nutrient names — and both properties are the product here,
not features bolted onto it.

A document goes in. DWS returns typed, confidence-scored fields. Validation
rules run. Anything that fails a rule, or a required field whose confidence is
unknown or below threshold, stops for a human. And every run emits an evidence
record: the SHA-256 of the document, of the extraction, and of the decision.

Months later, `verify` recomputes that chain **offline** — no API key, no
network, no vendor call — and says whether the record still matches what was
decided. Change one byte of the document and the chain breaks. Edit the stored
evidence and the chain breaks.

Five things make it more than a hashing script:

**The confidence gate is honest about what it does not know.** Nutrient returns
per-field confidence, not one document score — and this pipeline refuses to
invent an aggregate one, because a single average would hide exactly the field a
reviewer needed to see. The `FieldConfidencePolicy` checks each required field
individually: known confidence, above threshold, or a human sees it. The
vendor-independent local extractor makes the property visible — it has no
calibrated confidence, so it reports none, and the policy honestly routes every
such document to a person. The system degrades into caution, not into confident
nonsense.

**A check no text pipeline can make.** One rule computes `Σ(quantity ×
unit_price)` and compares it to the stated total. Free-form OCR alone does not
provide the typed line-item structure needed for a deterministic arithmetic
check. You need typed fields — line items as numbers, not as a sentence — which
is exactly what the DWS extraction schema provides. It catches invoices where
every individual field is correct and the document as a whole is internally
inconsistent.

**The record says what the human actually saw.** A decision that stops for
review is not a boolean. The pipeline writes a `ReviewRecord` — review id,
timestamp, reviewer role, decision, reason code, and the exact extraction hash
the reviewer was looking at — and hashes it into the evidence chain. Months
later the system can prove *which exact state* a human reviewed, offline and
with no vendor call.

**A ledger, not a pile of files.** A single evidence record proves its own
integrity and nothing about its neighbours: delete one file and every remaining
one still verifies. So decisions are chained, each entry carrying the hash of
the one before it. `python -m trustdocs attack` runs eight tampering attempts
and reports **7/7 detectable attacks caught**, plus one honest limitation —
truncating the tail of a chain is invisible to any self-contained log, and needs
an anchor published where the writer cannot reach it. The demo shows the anchor
catching it.

**An auditor console that does not ask to be trusted.** One self-contained HTML
file, no server, no network — it opens from a USB stick in a room with no
internet. It does not display a verdict computed by this tool: it embeds the
ledger and recomputes every SHA-256 in the auditor's own browser. Being handed a
clean report by the system under audit is not evidence; it is a claim.

## How we built it

Python, standard library, one dependency (`requests`). The DWS adapter is
roughly a hundred lines: the interesting work is the policy around it.

The design choice everything else follows from: **the evidence layer never
holds document content.** It records hashes and outcomes, never extracted field
values. That is what lets a record be handed to an auditor, an insurer or a
court without disclosing the documents themselves — and it is asserted by a
test, not by a promise.

The second design choice was proving vendor independence rather than claiming
it. The repo ships a **second extractor** that shares nothing with the DWS path
except the interface: a handful of regexes, no key, no network, deliberately
worse. `python -m trustdocs swap` runs the same document through both and shows
the evidence verifying either way.

What that second extractor exposed was the best surprise of the build. A regex
has no calibrated probability behind it, so it reports **no confidence at all** —
and the existing policy then routes every such document to a human. An extractor
that admits it cannot say how sure it is degrades into caution instead of into
confident nonsense. That property was already in the pipeline; the weak adapter
just made it visible.

That is human-in-the-loop arriving as a consequence of the design rather than as
a checkbox: the policy never needs to know which extractor is underneath, only
whether it can vouch for what it read.

## Challenges we ran into

**A test that passed in CI and failed on the developer's machine.** The Nutrient
adapter falls back to an environment variable when handed an empty key, so a
test asserting "no key means an error" passed on a clean CI runner and failed
wherever the key was exported. A test whose result depends on who runs it proves
nothing. Fixed by isolating the environment — and the fallback, which is
deliberate behaviour, now has a test of its own.

**Python and JavaScript disagreed about a hash, silently.** The auditor console
recomputes SHA-256 in the browser, over bytes canonicalised the way Python
canonicalises them. Python's `json.dumps` defaults to `ensure_ascii=True` and
writes `"año"`; JavaScript's `JSON.stringify` writes `"año"`. Different
bytes, different hash. The console would have reported "chain broken" for the
first invoice containing an accent — in a product meant for international
invoicing, a certainty. It was caught by a test that runs the page's own
JavaScript under Node and checks it agrees with Python, including on non-ASCII.

Worth noting how that one was found: the module docstring already warned that
the canonicalisation contract was fragile — and pointed at the wrong risk,
floats. **Documenting a risk is not the same as testing it.**

**The confidence gate almost sent everything to a human.** Nutrient returns
per-field confidence and no document score; the adapter correctly returned
`document_confidence=None`. But the pipeline read `None` as "unknown" and
routed *every* real document to a human, even when every required field had
high confidence. The fix was not an average — that would have invented a number
and hid the field that mattered. It was a `FieldConfidencePolicy` that checks
each required field individually. A document auto-approves only when every
required field has known, above-threshold confidence *and* validation passes.
The gap would have been invisible in the offline demos, which all set a
document score; only the real path exercised it.

## Accomplishments that we're proud of

- **156 tests**, and the README's own test count is now verified by one of them,
  because a number written by hand is exactly what this project argues against.
- **7/7 detectable tampering attacks caught**, with the eighth documented as a known
  limitation rather than hidden.
- **The console verifies independently.** Nobody has to trust the generator.
- **Vendor independence demonstrated in code**, with two extractors writing into
  one valid chain.
- **The record says what the human saw.** A `ReviewRecord` — review id,
  timestamp, reviewer, and the exact extraction hash reviewed — is hashed into
  the evidence chain, so the basis of a human decision is provable offline.

## What we learned

That the honest version of a security claim is more persuasive than the strong
one. The ledger cannot detect a truncated tail — no self-contained log can — and
saying so, with a test named after the weakness, makes the rest of the claims
credible. Showing the gap and then closing it with an external anchor lands
harder than pretending the gap was never there.

And that a document pipeline's hardest problem is not extraction. It is that
**the person who benefits and the person who pays are different people**: the
operator wants throughput, and the buyer is whoever has to explain the decision
later.

## What's next

Anchoring the ledger head from CI on every run, so truncation stops being
invisible in production rather than only in the demo. Signed evidence with a key
the pipeline does not hold. And the thing no amount of engineering substitutes
for: talking to someone who has actually been through the audit this is designed
for.

## Built with

`python` · `nutrient-dws` · `sha256` · `pyside6` · `pypdf` · `github-actions`

## Try it yourself

```sh
git clone https://github.com/DannyBaanks/trustworthy-document-pipeline
cd trustworthy-document-pipeline
python -m pip install -e .

python -m trustdocs.cli --demo-inconsistent   # the check OCR cannot make
python -m trustdocs attack                    # 7/7 detectable attacks caught
python -m trustdocs swap                      # same evidence, two extractors
```

No API key needed for any of those. CI runs the full suite without one; the live
Nutrient test ships with the repo and skips itself when the key is absent.
