# Demo video — shot list

Target: **3:00**, hard ceiling 4:00 (track requirement is 2–4 minutes).

The rule that governs every choice below: the track requires the video to
*"demonstrate actual working functionality, not just slides or concepts."*
So every second of screen time is either a real terminal running real commands,
or a title card between two of them. Nothing is mocked, nothing is sped up
without saying so on screen.

Record at **1920×1080**, terminal font at 18–20pt. Anything smaller is
unreadable once the platform re-encodes it.

---

## Shot 1 — The log line that says nothing · 0:00–0:22

**On screen:** black, then one line of monospace text appearing as if tailed
from a real log:

```
2026-03-14 14:32:07  user:accounts-payable-3  action:approve  invoice_id:4471
```

Hold. Then, underneath, three questions fade in one at a time:

```
Which fields did the model extract?
How confident was it?
Did the totals even add up?
```

**Narration:**

> Your AI reads an invoice. A person clicks approve. Six months later an
> auditor asks what they were looking at. This log line records the approval.
> It does not record the basis for it.

**Production:** this is the one place a generated visual belongs — the three
questions can resolve out of a FLOW field render. Keep it under four seconds of
abstraction; the terminal starts at 0:22.

---

## Shot 2 — The clean case · 0:22–0:52

**On screen:** real terminal. Type and run:

```sh
python -m trustdocs.cli --demo
```

Let the output land. Cursor rests.

**Narration:**

> Same pipeline, three documents. This is the clean one. The extraction returns
> typed fields with confidence scores, validation passes, confidence clears the
> gate, and it auto-approves. Note the two hashes: the document, and the
> evidence record for the decision.

**Production:** highlight the `Document:` and `Evidence:` lines as they are
mentioned — a soft box, not an animation.

---

## Shot 3 — The one that matters · 0:52–1:45

**On screen:**

```sh
python -m trustdocs.cli --demo-inconsistent
```

When the `✗ line-items-reconcile` line appears, **stop talking for one second**
and let it sit. Then zoom that single line to fill the frame.

**Narration:**

> This invoice looks perfect. Every field extracted cleanly, high confidence on
> all of them. And it is wrong.
>
> The line items do not add up to the stated total. The pipeline computes
> quantity times unit price across every row and compares it to the total.
> They disagree, so it refuses to auto-approve and routes it to a human.
>
> Free-form OCR cannot make that check. Text has no arithmetic. You need typed
> fields — line items as numbers, not as a sentence — and that is what the DWS
> extraction schema gives you. Every extracted field can be correct and the
> document can still be internally inconsistent.

**This is the peak of the video.** Everything before it sets it up; everything
after it is consequence. If a shot has to be cut for time, it is never this one.

---

## Shot 4 — Verify, months later · 1:45–2:20

**On screen:** clear the terminal. Then:

```sh
unset NUTRIENT_EXTRACTION_API_KEY      # on screen, deliberately
python -m trustdocs.cli verify docs/evidence/rejected.json
```

Output:

```
✓ VALID
  Recorded decision: REJECTED
```

Then break it on camera — copy the evidence, edit one character of a hash in an
editor, save, and re-run `verify` on the copy. Show it fail.

**Narration:**

> This is a decision from an earlier run. No API key — I just removed it. No
> network call. Verify recomputes the hash chain offline and confirms the
> recorded outcome.
>
> Now I change one character in the stored evidence. Same command. It fails.
> The record is tamper-evident: you cannot quietly rewrite what was decided.

**Production:** the failing case is the single most persuasive thing in the
video. Do not skip it for time — cut narration elsewhere instead.

---

## Shot 5 — The real service · 2:20–2:45

**On screen:**

```sh
python -m trustdocs.cli process sample/invoice.pdf --decision approve
python -m trustdocs.cli verify sample/invoice.pdf.evidence.json
```

**Narration:**

> Everything so far ran offline against fixtures. This is the real Nutrient
> endpoint, on a real PDF, producing evidence that verifies the same way.
> Continuous integration runs the whole unit suite with no API key, so anyone
> can reproduce the build; the live test ships with the repo and skips itself
> when there is no key.

---

## Shot 6 — Who pays for this · 2:45–3:00

**On screen:** the pipeline line from the README, then three lines of text.

```text
document -> DWS extraction -> validation -> confidence gate
         -> human review when needed -> verifiable evidence
```

```
Accounts payable, automating invoice intake
Regulated industries, where "the model decided" is not an answer
Anyone deploying document AI under the EU AI Act
```

**Narration:**

> Nutrient does the extraction, and does it well. What this adds is the evidence
> layer on top — vendor-agnostic, and still valid after the model underneath
> gets replaced. The extraction is the feature. Being able to prove what was
> approved is the business.

**Last frame:** repository URL, held for three full seconds. People pause here.

---

## Production notes

**Audio.** Record narration separately from the screen capture and lay it under.
Live narration while typing produces keyboard noise and hesitation.

**BEAT** boots in QEMU and drives the PC speaker, so its audio is captured from
the emulator, not exported as a file. Use it for the intro sting and the card
under Shot 6 — under narration it fights the voice. Budget an hour for the
capture and keep a silent fallback: no music is better than a late submission.

**FLOW** renders deterministically from a trace (`flow run` → `trace.json`,
`flow render` → image/gif). Generate the Shot 1 visual and **commit the trace
next to it**, so the visual can be regenerated and verified exactly like the
project's own evidence. That parallel is worth one sentence in the submission
text and zero seconds of video time.

**LangBuster** consumes video as a program rather than producing it, so it has
no role in production. If there is spare time at the end, the finished video can
be fed to it as a LangBuster program — a closing curiosity for the write-up, not
part of the deliverable.

**Cut order if running long:** Shot 5 first (the README covers it), then
narration in Shot 2, then the Shot 1 abstraction. Shots 3 and 4 are the
submission.
