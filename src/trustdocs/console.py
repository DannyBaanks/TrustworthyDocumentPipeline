"""Generate a self-contained auditor console from a ledger.

One HTML file, no server, no network, no build step. Open it from a USB stick
in a room with no internet and it works.

The page does not display a verification result computed by this module. It
embeds the ledger and **recomputes every hash in the browser**, which is the
only version of this worth shipping: an auditor asked to trust a report
produced by the system under audit has not been given evidence, they have been
given a claim.

`crypto.subtle` is unavailable over `file://`, which is precisely how this will
be opened, so the page carries a small SHA-256 implementation instead of
reaching for the browser API.

## The canonicalisation contract

Python hashes `json.dumps(body, sort_keys=True, separators=(",", ":"))`. The
browser must produce byte-identical input, so `canonical_json` here mirrors that
exactly and is tested against `evidence._digest`.

This holds because every value in a ledger entry body is a string, an integer or
null. **Adding a float to the entry body would break it**, because Python writes
`0.0` where JavaScript writes `0`. If that day comes, the fix is to serialise
floats explicitly on both sides, not to hope.
"""
from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ledger import Ledger


def canonical_json(value: Any) -> str:
    """Serialise the way `evidence._digest` does, so hashes agree."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# A compact SHA-256. Written out rather than pulled from a CDN because the page
# must work offline, and rather than crypto.subtle because file:// is not a
# secure context.
_SHA256_JS = r"""
function sha256(ascii) {
  function rr(v, a) { return (v >>> a) | (v << (32 - a)); }
  var maxWord = Math.pow(2, 32), i, j, result = '';
  var words = [], asciiBitLength = ascii.length * 8;
  var hash = sha256.h = sha256.h || [], k = sha256.k = sha256.k || [];
  var primeCounter = k.length, isComposite = {};
  for (var candidate = 2; primeCounter < 64; candidate++) {
    if (!isComposite[candidate]) {
      for (i = 0; i < 313; i += candidate) isComposite[i] = candidate;
      hash[primeCounter] = (Math.pow(candidate, 0.5) * maxWord) | 0;
      k[primeCounter++] = (Math.pow(candidate, 1 / 3) * maxWord) | 0;
    }
  }
  ascii += '\x80';
  while (ascii.length % 64 - 56) ascii += '\x00';
  for (i = 0; i < ascii.length; i++) {
    j = ascii.charCodeAt(i);
    if (j >> 8) return;
    words[i >> 2] |= j << ((3 - i) % 4) * 8;
  }
  words[words.length] = (asciiBitLength / maxWord) | 0;
  words[words.length] = asciiBitLength;
  for (j = 0; j < words.length;) {
    var w = words.slice(j, j += 16), oldHash = hash;
    hash = hash.slice(0, 8);
    for (i = 0; i < 64; i++) {
      var w15 = w[i - 15], w2 = w[i - 2];
      var a = hash[0], e = hash[4];
      var temp1 = hash[7] + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25))
        + ((e & hash[5]) ^ ((~e) & hash[6])) + k[i]
        + (w[i] = (i < 16) ? w[i] : (
            w[i - 16] + (rr(w15, 7) ^ rr(w15, 18) ^ (w15 >>> 3))
            + w[i - 7] + (rr(w2, 17) ^ rr(w2, 19) ^ (w2 >>> 10))
          ) | 0);
      var temp2 = (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22))
        + ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));
      hash = [(temp1 + temp2) | 0].concat(hash);
      hash[4] = (hash[4] + temp1) | 0;
    }
    for (i = 0; i < 8; i++) hash[i] = (hash[i] + oldHash[i]) | 0;
  }
  for (i = 0; i < 8; i++) {
    for (j = 3; j + 1; j--) {
      var b = (hash[i] >> (j * 8)) & 255;
      result += ((b < 16) ? 0 : '') + b.toString(16);
    }
  }
  return result;
}

function utf8(str) {
  return unescape(encodeURIComponent(str));
}

// Python's json.dumps defaults to ensure_ascii=True and writes "año"
// where JSON.stringify writes "año". Without this the two languages hash
// different bytes for any non-ASCII value, and the console would report a
// broken chain for the first invoice containing an accent.
function jsonStr(s) {
  return JSON.stringify(s).replace(/[\u007f-\uffff]/g, function (c) {
    return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
  });
}

function canonical(value) {
  if (value === null) return 'null';
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (typeof value === 'object') {
    return '{' + Object.keys(value).sort()
      .map(function (k) { return jsonStr(k) + ':' + canonical(value[k]); })
      .join(',') + '}';
  }
  if (typeof value === 'string') return jsonStr(value);
  return JSON.stringify(value);
}
"""

_VERIFY_JS = r"""
// Recompute the chain here, in the reader's browser. Nothing below trusts the
// generator: every entry hash and every link is derived from the embedded data.
function verifyChain(rows) {
  var problems = [], prev = null;
  rows.forEach(function (row, index) {
    var body = {
      sequence: row.sequence,
      prev_entry_sha256: row.prev_entry_sha256,
      recorded_at: row.recorded_at,
      execution_id: row.execution_id,
      record_sha256: row.record_sha256,
      document_sha256: row.document_sha256,
      decision: row.decision
    };
    var recomputed = sha256(utf8(canonical(body)));
    row._recomputed = recomputed;
    row._contentOk = recomputed === row.entry_sha256;
    row._linkOk = row.prev_entry_sha256 === prev;
    row._sequenceOk = row.sequence === index;

    if (!row._contentOk) problems.push('entry ' + row.sequence + ': content altered after recording');
    if (!row._linkOk) problems.push('entry ' + row.sequence + ': broken link to the previous entry');
    if (!row._sequenceOk) problems.push('entry ' + row.sequence + ': sequence gap at position ' + index);
    prev = row.entry_sha256;
  });
  return { ok: problems.length === 0, problems: problems, head: prev };
}
"""


def render_console(ledger_path: Path | str, *, expected_head: str | None = None) -> str:
    ledger = Ledger(ledger_path)
    rows = [entry.to_dict() for entry in ledger.entries()]
    summary = ledger.summary()

    data = json.dumps(rows, indent=None, separators=(",", ":"))
    # Embedded inside a <script>; the sequence "</script>" in any string value
    # would end the block early. Ledger values are hashes and enum-ish strings,
    # but they arrive from whatever ran the pipeline, so treat them as data.
    data = data.replace("</", "<\\/")

    anchor = html.escape(expected_head or "", quote=True)
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    counts = "".join(
        f'<div class="stat"><span class="stat-n">{count}</span>'
        f'<span class="stat-l">{html.escape(name)}</span></div>'
        for name, count in sorted(summary["by_decision"].items()))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Decision ledger &mdash; auditor console</title>
<style>
  :root {{
    --ground:#f6f7f9; --surface:#fff; --ink:#151b23; --soft:#5b6673; --rule:#dfe4ea;
    --ok:#1a7f47; --ok-bg:#e5f4ec; --bad:#b3341c; --bad-bg:#fbe9e5; --accent:#20558a;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --ground:#0f151b; --surface:#161d25; --ink:#e6ecf2; --soft:#9aa7b4; --rule:#28323d;
      --ok:#4cc38a; --ok-bg:#12291f; --bad:#f0836a; --bad-bg:#2c1712; --accent:#63a8e0;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--ground); color:var(--ink);
    font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }}
  .wrap {{ max-width:60rem; margin:0 auto; padding:2.5rem 1.5rem 5rem;
    display:flex; flex-direction:column; gap:2rem; }}
  h1 {{ font-size:1.6rem; margin:0; letter-spacing:-.02em; }}
  .sub {{ color:var(--soft); margin:.3rem 0 0; }}
  .mono {{ font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace; }}
  .banner {{ padding:1.1rem 1.3rem; border:1px solid var(--rule); border-left-width:4px;
    background:var(--surface); display:flex; flex-direction:column; gap:.4rem; }}
  .banner.ok {{ border-left-color:var(--ok); background:var(--ok-bg); }}
  .banner.bad {{ border-left-color:var(--bad); background:var(--bad-bg); }}
  .banner h2 {{ margin:0; font-size:1.05rem; }}
  .banner .why {{ color:var(--soft); font-size:.9rem; }}
  .stats {{ display:flex; flex-wrap:wrap; gap:1.75rem; padding:1rem 1.3rem;
    background:var(--surface); border:1px solid var(--rule); }}
  .stat {{ display:flex; flex-direction:column; }}
  .stat-n {{ font-size:1.5rem; font-weight:600; font-variant-numeric:tabular-nums; }}
  .stat-l {{ font-size:.72rem; letter-spacing:.09em; text-transform:uppercase; color:var(--soft); }}
  .controls {{ display:flex; gap:.6rem; flex-wrap:wrap; }}
  input, select {{ font:inherit; padding:.45rem .6rem; border:1px solid var(--rule);
    background:var(--surface); color:var(--ink); }}
  input {{ flex:1; min-width:14rem; }}
  .tbl {{ overflow-x:auto; border:1px solid var(--rule); background:var(--surface); }}
  table {{ border-collapse:collapse; width:100%; font-size:.86rem; }}
  th,td {{ padding:.55rem .8rem; text-align:left; border-bottom:1px solid var(--rule);
    white-space:nowrap; }}
  th {{ font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; color:var(--soft); }}
  tbody tr:last-child td {{ border-bottom:none; }}
  td.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .pill {{ font-size:.68rem; font-weight:600; padding:.12rem .45rem; letter-spacing:.05em; }}
  .pill.ok {{ background:var(--ok-bg); color:var(--ok); }}
  .pill.bad {{ background:var(--bad-bg); color:var(--bad); }}
  .anchor {{ padding:1rem 1.3rem; background:var(--surface); border:1px solid var(--rule);
    font-size:.86rem; color:var(--soft); display:flex; flex-direction:column; gap:.35rem; }}
  .anchor code {{ color:var(--ink); word-break:break-all; }}
  footer {{ color:var(--soft); font-size:.8rem; border-top:1px solid var(--rule);
    padding-top:1.2rem; }}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <h1>Decision ledger</h1>
    <p class="sub">Every hash on this page was recomputed by your browser from the
      embedded records. Nothing here is taken on the word of the tool that wrote it.</p>
  </header>

  <div id="banner" class="banner"><h2>Verifying&hellip;</h2></div>

  <div class="stats">
    <div class="stat"><span class="stat-n">{summary['total']}</span>
      <span class="stat-l">decisions</span></div>
    {counts}
  </div>

  <div class="controls">
    <input id="q" type="search" placeholder="Search by document hash, execution id or decision"
           aria-label="Search the ledger">
    <select id="filter" aria-label="Filter by decision">
      <option value="">All decisions</option>
    </select>
  </div>

  <div class="tbl">
    <table>
      <thead><tr>
        <th class="n">#</th><th>Recorded</th><th>Decision</th>
        <th>Document</th><th>Link</th>
      </tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>

  <div class="anchor">
    <div><strong>Chain head</strong> &mdash; publish this value somewhere the system
      cannot reach, and a truncated tail stops being invisible.</div>
    <code id="head" class="mono"></code>
  </div>

  <footer>
    Generated {generated} from a ledger of {summary['total']} decisions.
    This page contains hashes and outcomes only &mdash; never extracted document values.
  </footer>
</div>

<script>
{_SHA256_JS}
{_VERIFY_JS}

const LEDGER = {data};
const EXPECTED_HEAD = "{anchor}";

const result = verifyChain(LEDGER);

(function renderBanner() {{
  const el = document.getElementById('banner');
  const truncated = EXPECTED_HEAD && result.head !== EXPECTED_HEAD;
  const ok = result.ok && !truncated;
  el.className = 'banner ' + (ok ? 'ok' : 'bad');

  let title, why;
  if (ok) {{
    title = '\\u2713 Chain intact \\u2014 ' + LEDGER.length + ' entries verified in this browser';
    why = EXPECTED_HEAD
      ? 'Every link recomputed, and the head matches the published anchor.'
      : 'Every link recomputed. No anchor was supplied, so a truncated tail would still look valid.';
  }} else if (truncated) {{
    title = '\\u2717 Entries removed from the end';
    why = 'The chain itself is consistent, but it ends at ' + result.head
        + ' while the published anchor says ' + EXPECTED_HEAD + '.';
  }} else {{
    title = '\\u2717 Chain broken \\u2014 ' + result.problems.length + ' problem(s)';
    why = result.problems.join(' \\u00b7 ');
  }}
  el.innerHTML = '';
  const h = document.createElement('h2'); h.textContent = title;
  const p = document.createElement('p'); p.className = 'why'; p.textContent = why;
  el.appendChild(h); el.appendChild(p);
}})();

document.getElementById('head').textContent = result.head || '(empty ledger)';

(function fillFilter() {{
  const seen = {{}};
  LEDGER.forEach(function (r) {{ seen[r.decision] = true; }});
  const sel = document.getElementById('filter');
  Object.keys(seen).sort().forEach(function (d) {{
    const o = document.createElement('option'); o.value = d; o.textContent = d;
    sel.appendChild(o);
  }});
}})();

function draw() {{
  const q = document.getElementById('q').value.trim().toLowerCase();
  const only = document.getElementById('filter').value;
  const body = document.getElementById('rows');
  body.innerHTML = '';

  LEDGER.filter(function (r) {{
    if (only && r.decision !== only) return false;
    if (!q) return true;
    return (r.document_sha256 + ' ' + r.execution_id + ' ' + r.decision)
      .toLowerCase().indexOf(q) !== -1;
  }}).forEach(function (r) {{
    const tr = document.createElement('tr');
    const intact = r._contentOk && r._linkOk && r._sequenceOk;

    function cell(text, cls) {{
      const td = document.createElement('td');
      if (cls) td.className = cls;
      td.textContent = text;
      return td;
    }}

    tr.appendChild(cell(r.sequence, 'n'));
    tr.appendChild(cell(r.recorded_at.replace('T', ' ').slice(0, 19)));
    tr.appendChild(cell(r.decision));
    tr.appendChild(cell(r.document_sha256.slice(0, 16) + '\\u2026', 'mono'));

    const status = document.createElement('td');
    const pill = document.createElement('span');
    pill.className = 'pill ' + (intact ? 'ok' : 'bad');
    pill.textContent = intact ? 'verified' : 'broken';
    status.appendChild(pill);
    tr.appendChild(status);

    body.appendChild(tr);
  }});
}}

document.getElementById('q').addEventListener('input', draw);
document.getElementById('filter').addEventListener('change', draw);
draw();
</script>
</body>
</html>
"""


def write_console(ledger_path: Path | str, out_path: Path | str,
                  *, expected_head: str | None = None) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_console(ledger_path, expected_head=expected_head),
                   encoding="utf-8")
    return out
