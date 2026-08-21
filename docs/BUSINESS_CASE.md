# Business case

Every figure below is labelled with where it comes from:

| Tag | Meaning |
|---|---|
| **[measured]** | Taken from this repository. Reproducible by running it. |
| **[assumption]** | A number chosen to make the model concrete. Change it and the model changes; the arithmetic is shown so you can. |
| **[unverified]** | Something believed to be true that has not been checked to a standard this project would accept from anyone else. |

A business case written the way most business cases are written — plausible
figures with no provenance — would contradict the product. The product exists
because "trust me, it was fine" is not an acceptable answer.

---

## 1. What is being sold, and to whom

Not document processing. Nutrient does that, and does it better than a
hackathon project will.

What is sold is **a defensible record of automated decisions**: the ability to
answer, months later, *what did the system see and why did it decide that*.

The distinction that matters commercially is that **the user and the buyer are
different people**.

| | Operator (accounts payable) | Buyer (compliance / risk / internal audit) |
|---|---|---|
| Cares about | throughput | defensibility |
| Feels the pain | never — evidence slows them down | during an audit, an incident, a dispute |
| Competing option | automate without stopping | have nothing to show |

Selling this as a productivity tool loses. The honest comparison is against
*fully automatic approval*, which is strictly faster because it stops for
nothing. This is not a productivity product. **It is an insurance product**, and
insurance is bought by the person who carries the risk, not the person who does
the work.

## 2. The purchase trigger

Nobody buys this because processing invoices is annoying. They buy it after one
of:

- an auditor asks for the basis of a decision and the answer is a log line;
- a payment goes out that should not have, and nobody can reconstruct who saw
  what;
- a regulator asks how an automated decision was reached;
- an insurer or customer asks for evidence of controls before signing.

That makes the sales motion event-driven and the sales cycle long. It also
makes churn low: nobody removes the audit trail once it exists.

## 3. Unit economics

The unit is **one document decision**.

**[assumption]** A mid-size finance operation processes 20,000 supplier
invoices a year.
**[assumption]** 15% require human review under a confidence-and-validation
policy like the one in this repo.
**[measured]** Storage per decision is one evidence record plus one ledger
line. Averaged over the three evidence fixtures in this repo: **1,868 bytes**
of evidence and **478 bytes** of ledger entry, so **2,346 bytes** per decision,
uncompressed.

At that volume:

```
20,000 decisions/year  ×  2,346 bytes    =  ~47 MB/year of evidence
20,000 decisions/year  ×  15%            =  3,000 human reviews/year
```

Storage is not the cost. **The reviews are.** The pipeline's economic job is
therefore not to eliminate review but to make sure the 15% that stop are the
*right* 15% — and to make the 85% that do not stop defensible without a human
ever having looked.

The `line-items-reconcile` rule is the sharpest example: it catches documents
where every field extracted cleanly at high confidence and the document is
still wrong. Confidence alone would have auto-approved it.

## 4. Pricing

**[assumption]** Per-decision pricing, because it aligns with the buyer's own
volume and requires no seat negotiation:

| Tier | Decisions/year | Price/decision |
|---|---|---|
| Team | up to 25,000 | $0.02 |
| Business | up to 250,000 | $0.012 |
| Enterprise | above that | negotiated, with on-premise deployment |

At the assumed 20,000 documents that is **$400/year** — deliberately below the
threshold where anyone convenes a committee. The strategy is to be cheaper than
the meeting required to reject it, and to grow with the customer's automation
rather than with their headcount.

Revenue scales with **how much they automate**, which is the direction every
finance operation is already moving. That is the whole reason this is a
business and not a feature: the more the buyer trusts their AI, the more they
need to prove it was trustworthy.

## 5. Why now

**[unverified]** Two forces, both believed true and neither verified to this
project's own standard:

- Organisations are inserting language models into document workflows quickly,
  and the tooling for *explaining* those decisions is lagging the tooling for
  *making* them.
- Regulation is moving toward requiring traceability of automated decisions —
  the EU AI Act's record-keeping and human-oversight obligations for
  higher-risk systems being the most cited example.

Both claims are the kind that belong in a pitch deck and get repeated without
checking. Before either is used with a customer it needs a real source, and the
regulatory one needs a lawyer rather than a developer. They are listed here as
beliefs, not as evidence.

## 6. What makes it defensible

Not the code. It is roughly a thousand lines and any competent team could
rewrite it in a fortnight.

What is defensible:

- **Vendor independence, demonstrated.** The repo ships two extractors — the
  DWS adapter and a local heuristic one — writing into the same evidence chain.
  A customer who switches extraction providers keeps their history and their
  verifier. Switching *away* from the evidence layer means abandoning the
  record. **[measured]** — `tests/test_local_adapter.py`.
- **The format, if it spreads.** An evidence record that a third party can
  verify without the vendor is worth more when auditors start expecting it.
  That is a standards play, and standards plays are won by being open and
  first, not by being clever.
- **Nothing to exfiltrate.** The evidence contains hashes and outcomes, never
  extracted field values, so the record can be handed to an auditor, an
  insurer or a court without disclosing the documents themselves. **[measured]**
  — asserted in `tests/test_console.py`.

## 7. What would kill it

Stated plainly, because a business case that lists no failure modes is
marketing:

- **Nutrient, AWS or Azure ship this as a free feature.** The most likely
  outcome. The counter is vendor independence: a customer using two extractors
  cannot use either vendor's built-in audit trail.
- **Nobody is actually audited.** If the regulatory pressure in §5 does not
  materialise, the trigger in §2 never fires and this is a solution to a
  problem people are willing to keep having.
- **Tamper-evident is not enough.** The record proves it was not altered after
  the fact. It does not prevent someone recording a decision they should not
  have made. A buyer who wants the second thing will be disappointed, and the
  honest move is to tell them before they buy.

## 8. What is not known

- **Whether anyone pays for this.** Zero customer interviews. Everything above
  is a hypothesis about a buyer nobody has spoken to.
- **Where the real price sits.** §4 is arithmetic, not research. It has never
  been quoted to anyone.
- **Whether the 15% review rate is realistic.** It is an assumption chosen to
  make the model concrete, not a measurement from a production workload.
- **Whether the regulatory framing survives a lawyer.**

The first of these is the one that matters, and no amount of engineering
substitutes for it.
