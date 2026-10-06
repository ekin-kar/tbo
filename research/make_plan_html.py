"""Builds fundingpips_plan.html (self-contained, same look as the statistics pages) from research/results/fundingpips_plan_data.json.
Usage:  python research/make_plan_html.py   (run research/fundingpips_report.py first)"""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
data = json.load(open(ROOT / "research" / "results" / "fundingpips_plan_data.json"))
import pandas as pd
EV = pd.read_csv(ROOT / "research" / "results" / "fundingpips_results.csv")
FU = pd.read_csv(ROOT / "research" / "results" / "fundingpips_funded_results.csv")
EV = EV[EV.guard == 1.5]; FU = FU[FU.keep == 0.01]
EV_TAGS = {(0.4, 0.5, 1.0, 0.0): "slowest", (0.5, 0.6, 1.0, 0.0): "slow", (0.6, 0.8, 1.0, 0.0): "v6 setting", (0.7, 0.9, 1.0, 0.0): "no scaling",
           (0.8, 1.0, 1.0, 0.0): "fast, risky", (1.0, 1.2, 1.0, 0.0): "very risky", (0.6, 0.8, 0.5, 0.0): "safest, slow",
           (0.7, 0.9, 0.6, 0.0): "first v7 rule", (0.7, 0.9, 0.5, 0.03): "", (0.7, 0.9, 0.4, 0.04): "", (0.7, 0.9, 0.3, 0.04): "current (4 Oct 2026)",
           (0.7, 0.9, 0.3, 0.05): "", (0.8, 1.0, 0.3, 0.04): "faster", (0.6, 0.8, 0.3, 0.04): "safer"}
CUR = (0.7, 0.9, 0.3, 0.04)
FU_TAGS = {(0.5, 0.6, 1.0): "until 5 Oct 2026", (0.3, 0.4, 0.3): "safest, slow", (0.4, 0.5, 0.3): "safer", (0.5, 0.6, 0.3): "current",
           (0.6, 0.8, 0.3): "faster, riskier", (0.7, 0.9, 0.3): "risky", (0.8, 1.0, 0.3): "risky", (1.0, 1.2, 0.3): "very risky"}
FU_CUR = (0.5, 0.6, 0.3)
pct = lambda v: f"{v:.0f}"
MED, LOST = "_med", "_lost%"
def ev_table():
    h = ("<thead><tr><th>Gold / USDJPY risk</th><th>Below the start</th><th>Pass chance<br>2y / 3y / 10y / real</th><th>Failed<br>2y / 3y / 10y / real</th>"
         "<th>Median months to pass<br>2y / 3y / 10y / real</th><th>Passed within 6 months<br>3y / 10y</th><th></th></tr></thead>")
    rows = []
    for _, r in EV.iterrows():
        k = (r.gold, r.jpy, r.minm, round(r.dz, 2)); W = ("2y", "3y", "10y", "roll")
        sc = "fixed" if r.minm >= 1 else (f"shrink from the start, min {r.minm:g}&times;" if r.dz == 0 else f"full to -{r.dz * 100:g}%, then shrink, min {r.minm:g}&times;")
        rows.append(f'<tr{" class=hl" if k == CUR else ""}><td>{r.gold:.1f}% / {r.jpy:.1f}%</td><td>{sc}</td>'
                    f'<td>{" / ".join(pct(r[w + "_passp"]) for w in W)}%</td><td>{" / ".join(pct(r[w + "_fail"]) for w in W)}%</td>'
                    f'<td>{" / ".join(f"{r[w + MED]:.1f}" for w in W)}</td>'
                    f'<td>{pct(r["3y_in6"])} / {pct(r["10y_in6"])}%</td><td>{EV_TAGS.get(k, "")}</td></tr>')
    return h + "<tbody>" + "".join(rows) + "</tbody>"
def fu_table():
    h = ("<thead><tr><th>Gold / USDJPY risk</th><th>Below the start</th><th>Account lost in year 1<br>2y / 3y / 10y</th><th>Paid to you in year 1, median<br>2y / 3y / 10y</th>"
         "<th>Bad year (25th pct)<br>2y / 3y / 10y</th><th>Good year (75th pct)<br>2y / 3y / 10y</th><th>First payout, days<br>3y / 10y</th><th></th></tr></thead>")
    usd = lambda v: "$" + f"{v:,.0f}"
    rows = []
    for _, r in FU.sort_values(["gold", "minm"]).iterrows():
        k = (r.gold, r.jpy, r.minm); W = ("2y", "3y", "10y")
        shr = "fixed" if r.minm >= 1 else f"full to -{r.dz * 100:.0f}%, then shrink, min {r.minm:.1f}&times;"
        rows.append(f'<tr{" class=hl" if k == FU_CUR else ""}><td>{r.gold:.1f}% / {r.jpy:.1f}%</td><td>{shr}</td>'
                    f'<td>{" / ".join(f"{r[w + LOST]:.1f}" for w in W)}%</td>'
                    f'<td>{" / ".join(usd(r[w + "_paid_med"]) for w in W)}</td><td>{" / ".join(usd(r[w + "_paid_p25"]) for w in W)}</td>'
                    f'<td>{" / ".join(usd(r[w + "_paid_p75"]) for w in W)}</td>'
                    f'<td>{int(r["3y_first_pay_days"])} / {int(r["10y_first_pay_days"])}</td><td>{FU_TAGS.get(k, "")}</td></tr>')
    return h + "<tbody>" + "".join(rows) + "</tbody>"

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Funding Pips 10k plan</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f3f4f1; --surface:#ffffff; --ink:#18212b; --muted:#5d6874; --rule:#d9ddd6; --soft:#eceee9;
  --gold:#a47718; --jpy:#2f5d8c; --comb:#1d6b5b; --neg:#b3432f; --pos:#1d6b5b; --band1:rgba(29,107,91,.12); --band2:rgba(29,107,91,.22);
  --sample:rgba(24,33,43,.16);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#12171d; --surface:#19212a; --ink:#e7eaec; --muted:#9aa5b0; --rule:#2c3640; --soft:#1f2832;
  --gold:#d8aa4b; --jpy:#79a7da; --comb:#4fb39a; --neg:#e07a64; --pos:#4fb39a; --band1:rgba(79,179,154,.13); --band2:rgba(79,179,154,.25);
  --sample:rgba(231,234,236,.16); } }
:root[data-theme="dark"]{
  --bg:#12171d; --surface:#19212a; --ink:#e7eaec; --muted:#9aa5b0; --rule:#2c3640; --soft:#1f2832;
  --gold:#d8aa4b; --jpy:#79a7da; --comb:#4fb39a; --neg:#e07a64; --pos:#4fb39a; --band1:rgba(79,179,154,.13); --band2:rgba(79,179,154,.25);
  --sample:rgba(231,234,236,.16); }
*,*::before,*::after{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-variant-numeric:tabular-nums;}
.wrap{max-width:1120px;margin:0 auto;padding:28px 16px 56px}
h1{font-size:clamp(26px,4vw,38px);line-height:1.1;margin:0 0 6px;font-weight:700;letter-spacing:-.01em}
.lede{color:var(--muted);margin:0 0 22px;max-width:75ch}
.lede b{color:var(--ink);font-weight:600}
h2{font-size:20px;margin:40px 0 4px;font-weight:600}
.hint{color:var(--muted);margin:0 0 14px;font-size:14px;max-width:78ch}
.controls{display:flex;flex-wrap:wrap;gap:14px 26px;align-items:end;margin-bottom:18px}
.ctl-title{font-size:13px;color:var(--muted);margin-bottom:4px}
.sel{font:inherit;font-size:14px;color:var(--ink);background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:7px 10px;cursor:pointer}
.sel:focus-visible{outline:2px solid var(--comb);outline-offset:2px}
.btn{font:inherit;font-size:14px;border:1px solid var(--rule);background:var(--ink);color:var(--bg);border-radius:8px;padding:7px 13px;cursor:pointer}
.btn:focus-visible{outline:2px solid var(--comb);outline-offset:2px}
.seg{display:inline-flex;flex-wrap:wrap;max-width:100%;border:1px solid var(--rule);border-radius:8px;overflow:hidden;background:var(--surface)}
.seg button{font:inherit;font-size:14px;border:0;background:none;color:var(--ink);padding:8px 13px;cursor:pointer;border-right:1px solid var(--rule)}
.seg button:last-child{border-right:0}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.seg button:focus-visible{outline:2px solid var(--comb);outline-offset:2px}
.panel{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:16px 16px 10px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:18px}
.tile{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:14px 16px}
.tile .k{font-size:13px;color:var(--muted)}
.tile .v{font-size:28px;font-weight:700;line-height:1.15;margin:4px 0 2px}
.tile .s{font-size:13px;color:var(--muted)}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;margin:0 0 6px}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{width:16px;height:4px;border-radius:2px;display:inline-block}
.legend i.box{height:12px;border-radius:3px}
.chart-cap{font-size:13px;color:var(--muted);margin:4px 0 6px}
svg text{fill:var(--muted);font-size:12px;font-family:inherit}
svg .grid{stroke:var(--rule);stroke-width:1}
svg .axis{stroke:var(--muted);stroke-width:1}
.timeline{position:relative;height:96px;margin:8px 4px 4px}
.tl-track{position:absolute;left:0;right:0;top:40px;height:6px;background:var(--soft);border-radius:3px}
.tl-band{position:absolute;top:34px;height:18px;border-radius:9px;opacity:.85}
.tl-mark{position:absolute;top:28px;width:3px;height:30px;border-radius:2px;background:var(--ink)}
.tl-lab{position:absolute;font-size:12.5px;color:var(--muted);white-space:nowrap;transform:translateX(-50%)}
.tl-lab b{color:var(--ink);font-weight:600}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--rule);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{color:var(--muted);font-weight:500;font-size:13px}
tr.hl td{font-weight:600}
tr:hover>td{background:var(--soft);background:color-mix(in srgb,var(--ink) 8%,var(--surface))}
.specs{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.spec{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:16px}
.spec h3{margin:0 0 8px;font-size:16px}
.spec dl{display:grid;grid-template-columns:max-content 1fr;gap:5px 14px;margin:0;font-size:14px}
.spec dt{color:var(--muted)}
.spec dd{margin:0}
.notes{color:var(--muted);font-size:14px;max-width:85ch}
.notes li{margin:4px 0}
.pos{color:var(--pos)} .neg{color:var(--neg)}
@media (max-width:600px){ .tile .v{font-size:24px} th,td{padding:6px 7px} }
</style>
</head>
<body>
<div class="wrap">
  <h1>Funding Pips $10k: when you pass, when you get paid</h1>
  <p class="lede">Simulated journeys for account <b>***REMOVED***</b> (1-Step Flex, 2% daily) with the live bots: gold <b>PDAYT</b> and USDJPY <b>VOLC</b>.
  Challenge at <b>0.7% / 0.9%</b> risk, full risk down to $9,600 (-4%), below that <b>risk scaling</b> with the room left to the $8,800 floor
  (0.75&times; at $9,400, 0.5&times; at $9,200, never below 0.3&times; = 0.21% / 0.27% from $9,040), funded at <b>0.5% / 0.6%</b> with the same risk scaling (full down to $9,600, then min 0.3&times;) and $100 kept in the account, bot daily stop 1.5%, reset 21:00 UTC.
  Start: <b id="startlbl"></b>. Each journey is built from random 4-week blocks of the bots' real trades with every firm rule applied minute by minute.</p>

  <div class="controls">
    <div><div class="ctl-title">Based on market data from</div><div class="seg" id="win"></div></div>
    <div><div class="ctl-title">Funded: buffer kept in account</div><select class="sel" id="keep"></select></div>
    <div><div class="ctl-title">Pay out when above the buffer by</div><select class="sel" id="trig"></select></div>
    <div><div class="ctl-title">Profit split</div><select class="sel" id="split"></select></div>
  </div>

  <div class="tiles" id="tiles"></div>
  <p class="note" id="shortnote" style="display:none;border-left:3px solid var(--neg);padding:6px 10px;background:var(--surface);border-radius:6px"></p>

  <div class="panel">
    <div class="legend"><span><i class="box" style="background:var(--comb)"></i>Pass: middle 50% of journeys</span>
      <span><i class="box" style="background:var(--gold)"></i>First payout: middle 50%</span><span><i style="background:var(--ink)"></i>Median</span></div>
    <div class="timeline" id="tl"></div>
    <div class="chart-cap">From start to passing the challenge and to the first payout. Bars cover the middle half of all simulated journeys
      (25th to 75th percentile); the dark marks are the medians.</div>
  </div>

  <h2>When will I pass?</h2>
  <p class="hint">Share of journeys that have passed (green) or failed (red) by each date. The account has no time limit, so a slow start is not a failure.</p>
  <div class="panel">
    <div class="legend"><span><i style="background:var(--comb)"></i>Passed by this date</span><span><i style="background:var(--neg)"></i>Failed by this date</span></div>
    <svg id="cum" viewBox="0 0 1000 330" width="100%" role="img" aria-label="Probability of having passed by date"></svg>
  </div>

  <h2>Challenge balance</h2>
  <p class="hint">Balance from $10,000 towards the $11,200 target across all 3,000 journeys: the median and the middle 50% and 80%.
    A journey stops at $11,200 (passed) or $8,800 (failed).</p>
  <div class="panel">
    <div class="legend"><span><i style="background:var(--comb)"></i>Median</span><span><i class="box" style="background:var(--band2)"></i>Middle 50%</span>
      <span><i class="box" style="background:var(--band1)"></i>Middle 80%</span></div>
    <svg id="fan" viewBox="0 0 1000 360" width="100%" role="img" aria-label="Challenge balance paths"></svg>
  </div>

  <h2>Example journeys</h2>
  <p class="hint">12 single journeys, each built from a different random draw of the bots' real 4-week trade blocks. Green ended at the target (dot = pass day),
    red at the floor (dot = fail day), grey were still going after 8 months. Press the button for 12 other journeys (picked from 200 simulated ones per data period).</p>
  <div class="panel">
    <div class="legend" style="align-items:center"><button class="btn" id="reseed">New random journeys</button><span id="seedlbl"></span></div>
    <svg id="ex" viewBox="0 0 1000 360" width="100%" role="img" aria-label="Example journeys"></svg>
  </div>

  <h2>After passing: money paid to you</h2>
  <p class="hint" id="payhint"></p>
  <div class="panel">
    <div class="legend"><span><i style="background:var(--gold)"></i>Median</span><span><i class="box" style="background:rgba(164,119,24,.25)"></i>Middle 50%</span>
      <span><i class="box" style="background:rgba(164,119,24,.12)"></i>Middle 80%</span></div>
    <svg id="pay" viewBox="0 0 1000 330" width="100%" role="img" aria-label="Cumulative payouts"></svg>
  </div>

  <h2>All data periods side by side</h2>
  <p class="hint">6 months and 1 year reuse only the most recent months, so their funded-year figures (especially "lost") are exaggerated; 3, 5 and
    10 years are the ones to decide on, and the 10-year column, with the harder years, is the cautious view.</p>
  <div class="scroll panel"><table id="cmp"></table></div>

  <h2>Risk options: challenge</h2>
  <p class="hint">Other gold / USDJPY risk levels for the challenge, bot daily stop 1.5% in every row. Bold row = current setting.
    "Full to -y%, then shrink, min x" = the bots' risk scaling (v1.5 / v5.5): full risk down to $10,000 &times; (1 - y), below that risk &times; (balance - $8,800) / (that level - $8,800), never below x. "Shrink from the start": y = 0.
    2y / 3y / 10y: 4,000 simulated challenges each, built from random 4-week blocks of the real trades of that period.
    Real: a fresh challenge started every week 2016-2024 on the real trade order. Use 10y and real as the cautious view.</p>
  <div class="scroll panel"><table>__EVT__</table></div>

  <h2>Risk options: funded account</h2>
  <p class="hint">First 12 funded months, $10,000 account, payouts every 14 days with the plan's payout settings
    (1% buffer, payout at +2%, 80% split; the selectors at the top do not change this table). Bold row = current setting. "Lost" = hit the $8,800 floor or the daily limit; payouts made before that are kept.
    "Full to -4%, then shrink" = the bots' risk scaling as in the challenge (StartBalance 10000 for the funded account): full risk down to $9,600, below that risk &times; (balance - $8,800) / $800, never below 0.3&times;.
    It removes most lost accounts for a few dollars of payout; nearly half the losses without it come before the first payout, while the account has no buffer yet.
    4,000 simulated years per cell (built separately from the charts above, so the current row can differ from them by a little).</p>
  <div class="scroll panel"><table>__FUT__</table></div>

  <h2>Settings</h2>
  <div class="specs">
    <div class="spec"><h3>Challenge (now)</h3><dl>
      <dt>Gold risk</dt><dd>0.7% per trade</dd><dt>USDJPY risk</dt><dd>0.9% per trade</dd>
      <dt>Risk scaling</dt><dd>full risk down to $9,600; below: &times; (balance - 8,800) / 800, min 0.3&times; (cbotset: StartBalance 10000, FloorPercent 88, ShrinkFromPercent 4, MinScale 0.3); no step-up above the start</dd>
      <dt>Bot daily stop</dt><dd>1.5% (firm limit 2%)</dd><dt>Daily reset</dt><dd>21 UTC (00:00 platform time)</dd>
      <dt>Target / floor</dt><dd>$11,200 / $8,800 (static)</dd><dt>Time limit</dt><dd>none</dd></dl></div>
    <div class="spec"><h3>Funded (from the first funded day)</h3><dl>
      <dt>Gold risk</dt><dd>0.5% per trade</dd><dt>USDJPY risk</dt><dd>0.6% per trade</dd>
      <dt>Risk scaling</dt><dd>as in the challenge: full risk down to $9,600; below: &times; (balance - 8,800) / 800, min 0.3&times; (cbotset: StartBalance 10000, FloorPercent 88, ShrinkFromPercent 4, MinScale 0.3)</dd>
      <dt>Bot daily stop</dt><dd>1.5%</dd><dt>Payouts</dt><dd>every 14 days, 80% split</dd>
      <dt>Keep in account</dt><dd id="keepspec"></dd><dt>Swing add-on</dt><dd>yes (USDJPY holds overnight)</dd></dl></div>
    <div class="spec"><h3>Bots</h3><dl>
      <dt>Gold PDAYT</dt><dd>01:15 UTC stop at yesterday's high/low, EMA40 side, SL 2&times;ATR(m15), TP 2R, flat 20:00</dd>
      <dt>USDJPY VOLC</dt><dd>quiet market (ATR14 &lt; 0.8&times;ATR100), 10-candle range breakout, SL 1.5&times;ATR, TP 2.5R, closed after 20 hours, Friday close (v5.5)</dd>
      <dt>Versions</dt><dd>GoldPDay v1.5 (reloads its history after a reconnect), JpyVolContraction v5.5; risk scaling; trading rules unchanged from v6</dd></dl></div>
  </div>

  <h2>How to read this</h2>
  <ul class="notes">
    <li>These are simulations from backtested trades, not promises. Real results have run about 12-14% below the engine in tick tests.</li>
    <li>The funded account is assumed to start trading 3 days after passing. A payout can be requested every 14 days, when no trade is open, once the balance is at least start + buffer + trigger; everything above start + buffer is withdrawn. Change buffer, trigger and split with the selectors at the top.</li>
    <li>"Funded account lost" counts journeys whose funded account hit the $8,800 floor or the 2% daily limit within 12 months; payouts made before that are kept.</li>
    <li>Leave the settings alone for at least 3 months or 60 trades. A slow month is normal: about 4 in 10 trades win, the winners are about twice the size of the losers.</li>
  </ul>
</div>
<script>
const DATA = __DATA__;
const START = new Date(Date.UTC(2026, 9, 2));            // first trading day: Fri 2 Oct 2026
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const day = d => new Date(START.getTime() + d * 864e5);
const fmtD = d => day(d).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
const fmtM = d => day(d).toLocaleDateString('en-GB', {month: 'short', year: '2-digit', timeZone: 'UTC'});
const usd = v => '$' + Math.round(v).toLocaleString('en-US');
const NS = 'http://www.w3.org/2000/svg';
let W = '3y', KEEP = 1, TRIG = 1, SPLIT = 80;
const FU = s => s.funded[KEEP + '/' + TRIG];
const pay = v => usd(10000 * v / 100 * SPLIT / 100);
document.getElementById('startlbl').textContent = fmtD(0);

function el(tag, attrs, parent) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
function frame(svg, x0, x1, y0, y1, h, yfmt, yticks, xticks, xlab) {
  svg.innerHTML = ''; const L = 58, R = 990, T = 12, B = h - 28;
  const X = v => L + (v - x0) / (x1 - x0) * (R - L), Y = v => B - (v - y0) / (y1 - y0) * (B - T);
  for (const t of yticks) { el('line', {x1: L, x2: R, y1: Y(t), y2: Y(t), class: 'grid'}, svg); const tx = el('text', {x: L - 8, y: Y(t) + 4, 'text-anchor': 'end'}, svg); tx.textContent = yfmt(t); }
  for (const t of xticks) { const near = X(t) > R - 24; const tx = el('text', {x: near ? R : X(t), y: h - 8, 'text-anchor': near ? 'end' : 'middle'}, svg); tx.textContent = xlab(t); el('line', {x1: X(t), x2: X(t), y1: B, y2: B + 4, class: 'axis'}, svg); }
  el('line', {x1: L, x2: R, y1: B, y2: B, class: 'axis'}, svg);
  return {X, Y, L, R, T, B};
}
const pathOf = (xs, ys, f) => xs.map((x, i) => (i ? 'L' : 'M') + f.X(x).toFixed(1) + ' ' + f.Y(ys[i]).toFixed(1)).join('');
function band(svg, f, xs, lo, hi, fill) { const d = pathOf(xs, hi, f) + xs.slice().reverse().map((x, i) => 'L' + f.X(x).toFixed(1) + ' ' + f.Y(lo[xs.length - 1 - i]).toFixed(1)).join('') + 'Z'; el('path', {d, fill, stroke: 'none'}, svg); }
function line(svg, f, xs, ys, stroke, w, dash) { el('path', {d: pathOf(xs, ys, f), fill: 'none', stroke, 'stroke-width': w || 2, 'stroke-dasharray': dash || '', 'stroke-linejoin': 'round'}, svg); }
function monthTicks(n) { const t = []; for (let m = 0; m <= n; m += (n > 12 ? 3 : 1)) { const d = new Date(Date.UTC(2026, 9 + m, 1)); t.push((d - START) / 864e5); } return t.filter(x => x >= 0); }

function tiles(s) {
  const f = FU(s), pd = s.pass_days, fp = f.first_payout_total_days;
  const T = [
    ['Pass chance', s.pass_pct + '%', 'fail ' + s.fail_pct + '%, rest still running after 2 years'],
    ['Median pass date', fmtD(pd['50']), 'middle 50%: ' + fmtD(pd['25']) + ' to ' + fmtD(pd['75'])],
    ['First payout (median)', fmtD(fp['50']), 'middle 50%: ' + fmtD(fp['25']) + ' to ' + fmtD(fp['75'])],
    ['Paid in first funded year', pay(f.paid12['50']), 'middle 50%: ' + pay(f.paid12['25']) + ' to ' + pay(f.paid12['75'])],
    ['Funded account lost in year 1', f.lost_pct + '%', 'payouts before that are yours'],
  ];
  document.getElementById('tiles').innerHTML = T.map(t => `<div class="tile"><div class="k">${t[0]}</div><div class="v">${t[1]}</div><div class="s">${t[2]}</div></div>`).join('');
}

function timeline(s) {
  const tl = document.getElementById('tl'), pd = s.pass_days, fp = FU(s).first_payout_total_days, max = Math.max(fp['75'], 200) * 1.05;
  const P = d => (d / max * 100).toFixed(2) + '%';
  tl.innerHTML = `<div class="tl-track"></div>
    <div class="tl-band" style="left:${P(pd['25'])};width:calc(${P(pd['75'])} - ${P(pd['25'])});background:var(--comb)"></div>
    <div class="tl-band" style="left:${P(fp['25'])};width:calc(${P(fp['75'])} - ${P(fp['25'])});background:var(--gold);top:58px;height:12px"></div>
    <div class="tl-mark" style="left:0"></div><div class="tl-lab" style="left:0;top:78px;transform:none"><b>Start</b> ${fmtD(0)}</div>
    <div class="tl-mark" style="left:${P(pd['50'])}"></div><div class="tl-lab" style="left:${P(pd['50'])};top:4px"><b>Pass</b> ~${fmtD(pd['50'])}</div>
    <div class="tl-mark" style="left:${P(fp['50'])};top:52px;height:24px;background:var(--gold)"></div><div class="tl-lab" style="left:${P(fp['50'])};top:78px"><b>First payout</b> ~${fmtD(fp['50'])}</div>`;
}

function cumChart(s) {
  const svg = document.getElementById('cum'), n = 548, xs = [...Array(n).keys()];
  const f = frame(svg, 0, n - 1, 0, 100, 330, v => v + '%', [0, 25, 50, 75, 100], monthTicks(18), fmtM);
  line(svg, f, xs, s.pass_cum.slice(0, n), css('--comb'), 2.5);
  line(svg, f, xs, s.fail_cum.slice(0, n), css('--neg'), 2);
  for (const q of ['25', '50', '75']) {
    const d = s.pass_days[q]; if (d > n) continue;
    el('line', {x1: f.X(d), x2: f.X(d), y1: f.Y(0), y2: f.Y(+q), stroke: css('--comb'), 'stroke-dasharray': '3 4', 'stroke-width': 1}, svg);
    const t = el('text', {x: f.X(d) + 5, y: f.Y(+q) - 6}, svg); t.textContent = q + '% by ' + fmtD(d);
  }
}

function fanChart(s) {
  const svg = document.getElementById('fan'), F = s.fan, n = F['50'].length, xs = [...Array(n).keys()];
  const f = frame(svg, 0, n - 1, 8600, 11500, 360, v => '$' + (v / 1000).toFixed(1) + 'k', [8800, 9400, 10000, 10600, 11200], monthTicks(8), fmtM);
  band(svg, f, xs, F['10'], F['90'], css('--band1')); band(svg, f, xs, F['25'], F['75'], css('--band2'));
  line(svg, f, xs, F['50'], css('--comb'), 2.6);
  for (const [v, lab, c] of [[11200, 'Target $11,200: pass', '--pos'], [8800, 'Floor $8,800: fail', '--neg'], [10000, 'Start', '--muted']]) {
    el('line', {x1: f.L, x2: f.R, y1: f.Y(v), y2: f.Y(v), stroke: css(c), 'stroke-dasharray': '6 5', 'stroke-width': 1.3}, svg);
    const t = el('text', {x: f.R - 4, y: f.Y(v) - 5, 'text-anchor': 'end'}, svg); t.textContent = lab;
  }
}

function payChart(s) {
  const svg = document.getElementById('pay'), xs = DATA.settings.weeks, n = xs.length, k = 10000 / 100 * SPLIT / 100, P = {};
  for (const q in FU(s).paid) P[q] = FU(s).paid[q].map(v => v * k);
  const top = Math.max(1000, Math.ceil(P['90'][n - 1] / 1000) * 1000);
  const ticks = []; for (let v = 0; v <= top; v += top > 4000 ? 1000 : 500) ticks.push(v);
  const f = frame(svg, 0, xs[n - 1], 0, top, 330, v => '$' + v.toLocaleString('en-US'), ticks, [0, 61, 122, 183, 244, 305, 364], d => 'month ' + Math.round(d / 30.4));
  band(svg, f, xs, P['10'], P['90'], 'rgba(164,119,24,.12)'); band(svg, f, xs, P['25'], P['75'], 'rgba(164,119,24,.25)');
  line(svg, f, xs, P['50'], css('--gold'), 2.6);
  const t = el('text', {x: f.R - 4, y: f.Y(P['50'][n - 1]) - 8, 'text-anchor': 'end'}, svg); t.textContent = 'median ' + usd(P['50'][n - 1]);
}

function compare() {
  const ws = ['6m', '1y', '2y', '3y', '5y', '10y'], S = ws.map(w => DATA.windows[w]);
  const head = '<thead><tr><th></th><th>6 months</th><th>1 year</th><th>2 years</th><th>3 years</th><th>5 years</th><th>10 years</th></tr></thead>';
  const row = (lab, fn, hl) => `<tr${hl ? ' class="hl"' : ''}><td>${lab}</td>` + S.map(s => `<td>${fn(s)}</td>`).join('') + '</tr>';
  const rows = [
    row('Pass chance', s => s.pass_pct + '%', true),
    ...['1', '2', '3', '4', '6', '12'].map(m => row('&nbsp;&nbsp;passed within ' + m + (m === '1' ? ' month' : ' months'), s => s.pass_within[m] + '%')),
    row('Median pass date', s => fmtD(s.pass_days['50']), true),
    row('&nbsp;&nbsp;fast quarter by', s => fmtD(s.pass_days['25'])),
    row('&nbsp;&nbsp;slow quarter after', s => fmtD(s.pass_days['75'])),
    row('First payout, median date', s => fmtD(FU(s).first_payout_total_days['50']), true),
    row('&nbsp;&nbsp;days after funded start (median)', s => Math.round(FU(s).first_payout_days['50'])),
    row('&nbsp;&nbsp;paid within 6 weeks of funded start', s => FU(s).first_payout_within['42'] + '%'),
    row('&nbsp;&nbsp;no payout at all in year 1', s => FU(s).never_paid_pct + '%'),
    row('Paid in first funded year (median)', s => pay(FU(s).paid12['50']), true),
    row('&nbsp;&nbsp;bad year (10th percentile)', s => pay(FU(s).paid12['10'])),
    row('&nbsp;&nbsp;good year (90th percentile)', s => pay(FU(s).paid12['90'])),
    row('Funded account lost in year 1', s => FU(s).lost_pct + '%', true),
  ];
  document.getElementById('cmp').innerHTML = head + '<tbody>' + rows.join('') + '</tbody>';
}

function texts() {
  const b = 10000 * (1 + KEEP / 100), t = 10000 * (1 + (KEEP + TRIG) / 100);
  document.getElementById('payhint').textContent = `Cumulative payouts in your pocket (after the ${SPLIT}% split) during the first 12 months of the funded account, counted from its first trading day. A payout every 14 days once the balance is at least ${usd(t)}; everything above ${usd(b)} is withdrawn (buffer ${KEEP}%, trigger ${TRIG}%).`;
  document.getElementById('keepspec').textContent = `${usd(10000 * KEEP / 100)} (${KEEP}%), pay out at ${usd(t)}+, ${SPLIT}% split`;
}

let SEED = 1;
function rng(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function pick(pool, k) {
  const r = rng(SEED * 7919 + 17), idx = [...pool.keys()];
  for (let i = idx.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
  return idx.slice(0, k).map(i => pool[i]);
}
function exChart(s, f0, val, lines) {
  const svg = document.getElementById('ex'), f = f0(svg), cnt = {1: 0, '-1': 0, 0: 0};
  for (const [v, lab, c] of lines) {
    el('line', {x1: f.L, x2: f.R, y1: f.Y(v), y2: f.Y(v), stroke: css(c), 'stroke-dasharray': '6 5', 'stroke-width': 1.3}, svg);
    const t = el('text', {x: f.R - 4, y: f.Y(v) - 5, 'text-anchor': 'end'}, svg); t.textContent = lab;
  }
  for (const p of pick(s.samples, 12)) {
    const ys = p.slice(1).map(val), st = ys.length >= 240 ? 0 : p[0], xs = [...ys.keys()], c = st === 1 ? css('--comb') : st === -1 ? css('--neg') : css('--muted');
    cnt[st]++;
    el('path', {d: pathOf(xs, ys, f), fill: 'none', stroke: c, 'stroke-width': 1.6, 'stroke-opacity': 0.75, 'stroke-linejoin': 'round'}, svg);
    if (st !== 0) el('circle', {cx: f.X(xs[xs.length - 1]), cy: f.Y(ys[ys.length - 1]), r: 4, fill: c}, svg);
  }
  document.getElementById('seedlbl').textContent = `Seed ${SEED}: ${cnt[1]} passed, ${cnt['-1']} failed, ${cnt[0]} still going after 8 months (out of 12).`;
}
document.getElementById('reseed').onclick = () => { SEED = 1 + Math.floor(Math.random() * 9999); render(); };
function render() {
  const s = DATA.windows[W]; texts();
  const sn = document.getElementById('shortnote');
  sn.style.display = (W === '6m' || W === '1y') ? '' : 'none';
  sn.textContent = 'Short period: a 12-month funded year is built from only ' + (W === '6m' ? '6 months' : '1 year') + ' of trades, so the same few months (including the worst one) repeat many times in random order. This exaggerates losses, especially "funded account lost". On the real trade order, no funded account started in the last year was lost. Use 3, 5 or 10 years for decisions.'; compare(); tiles(s); timeline(s); cumChart(s); fanChart(s); payChart(s);
  exChart(s, svg => frame(svg, 0, 239, 8600, 11500, 360, v => '$' + (v / 1000).toFixed(1) + 'k', [8800, 9400, 10000, 10600, 11200], monthTicks(8), fmtM),
          v => v, [[11200, 'Target $11,200: pass', '--pos'], [8800, 'Floor $8,800: fail', '--neg'], [10000, 'Start', '--muted']]);
}
function select(id, vals, fmt, get, set) {
  const e = document.getElementById(id);
  e.innerHTML = vals.map(v => `<option value="${v}"${v === get() ? ' selected' : ''}>${fmt(v)}</option>`).join('');
  e.onchange = () => { set(+e.value); render(); };
}
select('keep', DATA.settings.keeps, v => v + '% (' + usd(100 * v) + ')' + (v === 1 ? ' (plan)' : ''), () => KEEP, v => KEEP = v);
select('trig', DATA.settings.trigs, v => '+' + v + '% (' + usd(100 * v) + ')' + (v === 1 ? ' (plan)' : ''), () => TRIG, v => TRIG = v);
select('split', [70, 80, 90, 100], v => v + '%' + (v === 80 ? ' (Funding Pips)' : ''), () => SPLIT, v => SPLIT = v);
const seg = document.getElementById('win');
for (const [k, lab] of [['6m', 'Last 6 months'], ['1y', 'Last year'], ['2y', 'Last 2 years'], ['3y', 'Last 3 years'], ['5y', 'Last 5 years'], ['10y', '10 years (cautious)']]) {
  const b = document.createElement('button'); b.textContent = lab; b.setAttribute('aria-pressed', k === W);
  b.onclick = () => { W = k; [...seg.children].forEach(c => c.setAttribute('aria-pressed', c === b)); render(); }; seg.appendChild(b);
}
render();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
</script>
</body>
</html>
"""
out = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__EVT__", ev_table()).replace("__FUT__", fu_table())
(ROOT / "plans" / "fundingpips_plan.html").write_text(out, encoding="utf-8")
print("written", len(out), "bytes")
