"""Builds fundedhive_plan.html (self-contained, same look as fundingpips_plan.html; the stylesheet is taken from make_plan_html.py)
from research/results/fundedhive_plan_data.json (fundedhive_report.py) and research/results/fundedhive_results.json (fundedhive_sim.py).
Usage:  python research/make_fundedhive_html.py"""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "research" / "results"
plan = json.load(open(RES / "fundedhive_plan_data.json"))
res = json.load(open(RES / "fundedhive_results.json"))
src = (ROOT / "research" / "make_plan_html.py").read_text()
STYLE = src[src.index("<style>"):src.index("</style>") + len("</style>")]
STYLE = STYLE.replace("</style>", ".note{font-size:13px;color:var(--muted);margin:8px 2px 4px}\n</style>")
assert ".sel{" in STYLE, "run after make_plan_html.py has the .sel style"

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>FundedHive plan</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
__STYLE__
</head>
<body>
<div class="wrap">
  <h1>FundedHive: when you pass, when you get paid</h1>
  <p class="lede">Simulated journeys for FundedHive 1-step <b>Low</b> accounts with the live bots: gold <b>PDAYT</b> and
  USDJPY <b>VOLC v5.5</b> (20-hour max hold). Evaluation at the recommended risk <b>with risk scaling below the starting balance</b>
  (risk shrinks with the room left to the floor, never below 0.3&times;; no step-up above the start), then the funded account with the risk ladder <b>plus the same risk scaling below the start</b> (no manual B-book cuts), the fee and
  B-book debt, every firm rule applied minute by minute on live equity. Start: <b id="startlbl"></b>. Each journey is built from random
  4-week blocks of the bots' real trades. Percentages are the same for every account size; the size switch only changes the dollar amounts.</p>

  <div class="controls">
    <div><div class="ctl-title">Account size</div><div class="seg" id="size"></div></div>
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
    <div class="chart-cap">From the start of the evaluation to passing and to the first payout (funded trading starts 3 days after passing).
      Bars cover the middle half of all simulated journeys (25th to 75th percentile); the dark marks are the medians.</div>
  </div>

  <h2>When will I pass?</h2>
  <p class="hint">Share of journeys that have passed (green) or failed (red) by each date. There is no time limit, so a slow start is not a failure.</p>
  <div class="panel">
    <div class="legend"><span><i style="background:var(--comb)"></i>Passed by this date</span><span><i style="background:var(--neg)"></i>Failed by this date</span></div>
    <svg id="cum" viewBox="0 0 1000 330" width="100%" role="img" aria-label="Probability of having passed by date"></svg>
  </div>

  <h2>Evaluation balance</h2>
  <p class="hint" id="fanhint"></p>
  <div class="panel">
    <div class="legend"><span><i style="background:var(--comb)"></i>Median</span><span><i class="box" style="background:var(--band2)"></i>Middle 50%</span>
      <span><i class="box" style="background:var(--band1)"></i>Middle 80%</span></div>
    <svg id="fan" viewBox="0 0 1000 360" width="100%" role="img" aria-label="Evaluation balance paths"></svg>
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

  <h2>Risk options: evaluation</h2>
  <p class="hint" id="evhint"></p>
  <div class="scroll panel"><table id="evt"></table></div>
  <p class="note">2y / 3y / 10y: 3,000 simulated evaluations each, built from random 4-week blocks of the real trades of that period.
    Real: a fresh account started every week 2016-2024 on the real trade order. Use 10y and real as the realistic expectation.
    Almost every failure is the static max loss, not the daily limit: the bots' daily stop keeps every day inside the firm's limit.</p>

  <h2>Funded account: risk ladder</h2>
  <p class="hint">Buffer = equity - starting balance - debt still owed (the fee and any B-book debt). Every account starts on the first row because
    the fee begins as debt. Check the buffer at the daily reset: move up when it reaches a level, move down the same day it falls below.
    In B book (below 99%) do nothing: the bots' risk scaling shrinks the size by itself.</p>
  <div class="scroll panel"><table>
    <thead><tr><th>Buffer</th><th>Gold / USDJPY (RiskPercent)</th></tr></thead>
    <tbody><tr><td>below +1% (start)</td><td>0.25% / 0.35%</td></tr>
    <tr><td>+1% to +2%</td><td>0.30% / 0.40%</td></tr>
    <tr><td>+2% to +4%</td><td>0.40% / 0.50%</td></tr>
    <tr class="hl"><td>above +4% (cap)</td><td>0.50% / 0.60%</td></tr></tbody></table></div>

  <h2>Funded ladder options</h2>
  <p class="hint" id="futhint"></p>
  <div class="scroll panel"><table id="fut"></table></div>
  <p class="note">This table compares ladders with no payouts taken: withdrawable = equity above the start after repaying the fee and B-book
    debt, after 12 months, for the selected account size, before the profit split (the buffer / trigger selectors do not change it). 2,500 simulated years per cell. The cap protects the worst cases: large size near the top of the ladder is what
    loses funded accounts. Flat sizing earns a similar median but loses more accounts.</p>

  <h2>Settings</h2>
  <div class="specs">
    <div class="spec"><h3>Evaluation</h3><dl>
      <dt>Risk: gold / USDJPY</dt><dd><b>0.4% / 0.5%</b></dd>
      <dt>Risk scaling</dt><dd>below the start: &times; (balance - floor) / (start - floor), min <b>0.3&times;</b> (cbotset: StartBalance = account size, FloorPercent 95, ShrinkFromPercent 0, MinScale 0.3); no step-up. A delayed start (full risk until -1/-2%) was tested and adds failures on a 5% floor. Funded account: on as well, see Funded</dd>
      <dt>Bot daily stop</dt><dd>1.5% (account-wide)</dd><dt>Daily reset hour</dt><dd>0 UTC</dd>
      <dt>Max actual risk</dt><dd>0.9% (gold skips a day if even the minimum lot is above it)</dd>
      <dt>USDJPY close before weekend</dt><dd>Yes</dd><dt>Everything else</dt><dd>defaults</dd></dl></div>
    <div class="spec"><h3>Funded</h3><dl>
      <dt>Risk</dt><dd>the ladder above (change RiskPercent at the daily reset when the buffer crosses a level)</dd>
      <dt>Risk scaling</dt><dd>on, as in the evaluation: StartBalance = funded account size, FloorPercent 95, ShrinkFromPercent 0, MinScale 0.3; no manual B-book cuts</dd>
      <dt>Bot daily stop</dt><dd>1.5%</dd><dt>Daily reset hour</dt><dd>0 UTC</dd>
      <dt>Max actual risk</dt><dd>0.9%</dd><dt>USDJPY close before weekend</dt><dd>Yes (no weekend holding once funded)</dd></dl></div>
    <div class="spec"><h3>Firm rules</h3><dl>
      <dt>Max risk per trade</dt><dd>1%</dd>
      <dt>Daily loss</dt><dd>2% (from the higher of balance / equity at 00:00 UTC)</dd>
      <dt>Max loss (static)</dt><dd>5%</dd><dt>Evaluation target</dt><dd>+10%</dd>
      <dt>Fee</dt><dd>1% of the account, repaid from the first funded profits</dd>
      <dt>B book</dt><dd>equity below 99% of the start: flat 1% debt</dd></dl></div>
    <div class="spec"><h3>Bots</h3><dl>
      <dt>Gold PDAYT</dt><dd>01:15 UTC stop at yesterday's high/low, EMA40 side, SL 2&times;ATR(m15), TP 2R, flat 20:00</dd>
      <dt>USDJPY VOLC v5.5</dt><dd>quiet market (ATR14 &lt; 0.8&times;ATR100), 10-candle range breakout, SL 1.5&times;ATR, TP 2.5R, closed after 20 hours, Friday close</dd></dl></div>
  </div>

  <h2>Rules that always apply</h2>
  <ul class="notes">
    <li>Change risk only at switch points: start of the evaluation, the first funded day, a ladder level crossed at the daily reset. Never raise risk to win back losses.</li>
    <li>Keep both bots running 24/5; never switch them off after a bad day. Review after about 3 months or 60+ trades.</li>
    <li>10k accounts: gold often trades the minimum lot (0.01), so on very wide-stop days a trade can risk more than planned. Max actual risk 0.9 makes the gold bot skip those days.</li>
  </ul>

  <h2>How to read this</h2>
  <ul class="notes">
    <li>These are simulations from backtested trades, not promises. Live results have come in about 12-14% below the engine, and every figure carries about &plusmn;5 points of uncertainty.</li>
    <li>"Funded account lost" counts journeys whose funded account hit the static max loss or the daily limit within 12 months; payouts made before that are kept.</li>
    <li>Payouts: FundedHive pays on demand with an 80% split. The simulation requests a payout as soon as equity minus any debt is at least start + buffer + trigger (checked once a day, when no trade is open). Everything above start + buffer is withdrawn and split. The fee and any B-book debt are repaid at once from any profit above the start, so the balance stays at the start (5% above the floor) until the debt is 0.</li>
    <li>After a payout the ladder continues from the buffer, so a bigger buffer keeps risk higher and lets the account grow; a small buffer pays more often but keeps the account on the lowest ladder rows.</li>
    <li>"Ever in B book" is the share of funded accounts that dipped below 99% at a daily reset at least once; it costs a 1% debt each time, not the account.</li>
    <li>The charts use 3,000 journeys per period; the option tables come from a separate run, so the recommended row can differ from the charts by a point or so.</li>
  </ul>
</div>
<script>
const PLAN = __PLAN__, RES = __RES__;
const START = new Date(Date.UTC(2026, 9, 2));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const day = d => new Date(START.getTime() + d * 864e5);
const fmtD = d => day(d).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
const fmtM = d => day(d).toLocaleDateString('en-GB', {month: 'short', year: '2-digit', timeZone: 'UTC'});
const NS = 'http://www.w3.org/2000/svg';
let RULE = 'low', SIZE = 200000, W = '3y', KEEP = 3, TRIG = 1, SPLIT = 80;
const FU = s => s.funded[KEEP + '/' + TRIG];
const pay = p => usd(p * SPLIT / 100);
const usd = p => '$' + Math.round(SIZE * p / 100).toLocaleString('en-US');
const kusd = v => { const a = Math.abs(v); const s = a >= 1000 ? String(parseFloat((a / 1000).toFixed(a >= 100000 ? 0 : 2))) + 'k' : Math.round(a); return (v < 0 ? '-$' : '$') + s; };
const RULES = {low: {floor: 5, target: 10, fee: 1, rec: [0.4, 0.5], recm: 0.3, recf: 'rec_shrink', guard: 1.5}};
document.getElementById('startlbl').textContent = fmtD(0);

function el(tag, attrs, parent) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
function frame(svg, x0, x1, y0, y1, h, yfmt, yticks, xticks, xlab) {
  svg.innerHTML = ''; const L = 62, R = 990, T = 12, B = h - 28;
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
  const f = FU(s), pd = s.pass_days, w = f.paid12, fp = f.first_payout_total_days;
  const T = [
    ['Pass chance', s.pass_pct + '%', 'fail ' + s.fail_pct + '%, rest still running after 2 years'],
    ['Median pass date', fmtD(pd['50']), 'middle 50%: ' + fmtD(pd['25']) + ' to ' + fmtD(pd['75'])],
    ['First payout (median)', fmtD(fp['50']), 'middle 50%: ' + fmtD(fp['25']) + ' to ' + fmtD(fp['75'])],
    ['Paid in first funded year', pay(w['50']), 'middle 50%: ' + pay(w['25']) + ' to ' + pay(w['75'])],
    ['Funded account lost in year 1', f.lost_pct + '%', 'payouts before that are yours'],
    ['Ever in B book (year 1)', f.bbook_pct + '%', 'each time costs a 1% debt, not the account'],
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
    if (s.pass_pct < +q) continue;
    el('line', {x1: f.X(d), x2: f.X(d), y1: f.Y(0), y2: f.Y(+q), stroke: css('--comb'), 'stroke-dasharray': '3 4', 'stroke-width': 1}, svg);
    const t = el('text', {x: f.X(d) + 5, y: f.Y(+q) - 6}, svg); t.textContent = q + '% by ' + fmtD(d);
  }
}

function fanChart(s) {
  const r = RULES[RULE], svg = document.getElementById('fan'), F = s.fan, n = F['50'].length, xs = [...Array(n).keys()];
  const yt = []; for (let v = -r.floor; v <= r.target; v += r.floor === 5 ? 2.5 : 2) yt.push(v); if (!yt.includes(r.target)) yt.push(r.target);
  const f = frame(svg, 0, n - 1, -r.floor - 0.6, r.target + 0.8, 360, v => kusd(SIZE * (1 + v / 100)), yt, monthTicks(8), fmtM);
  band(svg, f, xs, F['10'], F['90'], css('--band1')); band(svg, f, xs, F['25'], F['75'], css('--band2'));
  line(svg, f, xs, F['50'], css('--comb'), 2.6);
  for (const [v, lab, c] of [[r.target, 'Target +10%: pass', '--pos'], [-r.floor, 'Max loss -' + r.floor + '%: fail', '--neg'], [0, 'Start', '--muted']]) {
    el('line', {x1: f.L, x2: f.R, y1: f.Y(v), y2: f.Y(v), stroke: css(c), 'stroke-dasharray': '6 5', 'stroke-width': 1.3}, svg);
    const t = el('text', {x: f.R - 4, y: f.Y(v) - 5, 'text-anchor': 'end'}, svg); t.textContent = lab;
  }
  document.getElementById('fanhint').textContent = `Equity from ${kusd(SIZE)} towards the ${kusd(SIZE * 1.1)} target (+10%). Across all 3,000 journeys: the median and the middle 50% and 80%. A journey stops at the target (passed) or at ${kusd(SIZE * (1 - r.floor / 100))} (failed, the static max loss).`;
}

function payChart(s) {
  const svg = document.getElementById('pay'), xs = PLAN.weeks, n = xs.length, P = {};
  for (const q in FU(s).paid) P[q] = FU(s).paid[q].map(v => v * SPLIT / 100);
  const topP = Math.max(5, Math.ceil(P['90'][n - 1] / 5) * 5), step = topP > 40 ? 10 : 5;
  const ticks = []; for (let v = 0; v <= topP; v += step) ticks.push(v);
  const f = frame(svg, 0, xs[n - 1], 0, topP, 330, v => kusd(SIZE * v / 100), ticks, [0, 61, 122, 183, 244, 305, 364], d => 'month ' + Math.round(d / 30.4));
  band(svg, f, xs, P['10'], P['90'], 'rgba(164,119,24,.12)'); band(svg, f, xs, P['25'], P['75'], 'rgba(164,119,24,.25)');
  line(svg, f, xs, P['50'], css('--gold'), 2.6);
  const t = el('text', {x: f.R - 4, y: f.Y(P['50'][n - 1]) - 8, 'text-anchor': 'end'}, svg); t.textContent = 'median ' + usd(P['50'][n - 1]) + ' (+' + P['50'][n - 1].toFixed(1) + '%)';
}

function compare() {
  const ws = ['6m', '1y', '2y', '3y', '5y', '10y'], S = ws.map(w => PLAN.plans[RULE][w]);
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
    row('Ever in B book (year 1)', s => FU(s).bbook_pct + '%'),
  ];
  document.getElementById('cmp').innerHTML = head + '<tbody>' + rows.join('') + '</tbody>';
}

const join = (r, ws, k, d) => ws.map(w => r[w][k] == null ? '-' : r[w][k].toFixed(d)).join(' / ');
function evTable() {
  const r = RULES[RULE], keys = Object.keys(RES).filter(k => k.startsWith('eval/' + RULE + '/'));
  const tags = RULE === 'low' ? {'0.3/0.4/1': 'slow', '0.4/0.5/1': 'v6 setting', '0.5/0.6/1': 'faster, risky', '0.6/0.7/1': 'risky', '0.6/0.8/1': 'risky', '0.7/0.9/1': 'very risky',
                                 '0.3/0.4/0.3': 'slowest, safest', '0.4/0.5/0.6': '', '0.4/0.5/0.5': '', '0.4/0.5/0.3': 'recommended', '0.5/0.6/0.5': 'faster', '0.5/0.6/0.3': 'faster, still safe'}
                              : {'0.4/0.5/1': 'safer', '0.5/0.6/1': 'v6 setting', '0.6/0.75/1': 'risky', '0.7/0.9/1': 'risky', '0.8/1.0/1': 'very risky', '1.0/1.2/1': 'very risky',
                                 '0.4/0.5/0.3': 'safest', '0.5/0.6/0.6': '', '0.5/0.6/0.5': '', '0.5/0.6/0.3': 'recommended', '0.6/0.75/0.3': 'faster'};
  const W4 = ['2y', '3y', '10y', 'real'];
  const rows = keys.map(k => { const [, , g, j, mk] = k.split('/'), x = RES[k], m = mk ? +mk.slice(1) : 1, rec = +g === r.rec[0] && +j === r.rec[1] && m === r.recm;
    return `<tr${rec ? ' class="hl"' : ''}><td>${(+g).toFixed(1)}% / ${+j}%</td><td>${m < 1 ? 'shrink, min ' + m + '&times;' : 'fixed'}</td><td>${join(x, W4, 'passp', 0)}%</td><td>${join(x, W4, 'fail', 0)}%</td><td>${join(x, W4, 'med', 1)}</td><td>${tags[(+g).toFixed(1) + '/' + j + '/' + m] || ''}</td></tr>`; });
  document.getElementById('evt').innerHTML = '<thead><tr><th>Gold / USDJPY risk</th><th>Below the start</th><th>Pass chance<br>2y / 3y / 10y / real</th><th>Failed<br>2y / 3y / 10y / real</th><th>Median months to pass<br>2y / 3y / 10y / real</th><th></th></tr></thead><tbody>' + rows.join('') + '</tbody>';
  document.getElementById('evhint').textContent = `Low: other gold / USDJPY risk levels for the evaluation, bot daily stop ${r.guard.toFixed(1)}% in every row. Bold row = recommended. "Shrink, min x" = the bots' risk scaling below the starting balance (v1.5 / v5.5, shrink from 0% = from the start), never below x; it cuts failures by more than half for a few weeks more. One step faster saves about half a month and costs several points of pass chance.`;
}
function fuTable() {
  const r = RULES[RULE], W3 = ['2y', '3y', '10y'];
  const labs = [['rec_shrink', 'Recommended: ladder 0.25/0.35 to 0.50/0.60 + risk scaling, no manual B-book cuts'],
                ['rec_shrink_bb', 'Same + manual B-book cuts (0.25/0.35, 0.15/0.20)'],
                ['rec', 'Ladder + manual B-book cuts, no scaling (plan until 5 Oct 2026)'],
                ['flat_0.4_shrink', 'Flat 0.40/0.50 + risk scaling (= the evaluation settings)'], ['flat_0.4', 'Flat 0.40/0.50, manual B-book cuts'],
                ['rec_cap_0.6', 'Ladder to 0.60/0.70, manual B-book cuts'], ['old', 'Old plan: 0.15/0.20 up to 0.65/0.85']];
  const rows = labs.map(([k, lab]) => { const x = RES['funded/' + RULE + '/' + k];
    return `<tr${k === r.recf ? ' class="hl"' : ''}><td>${lab}</td><td>${join(x, W3, 'lost', 1)}%</td><td>${W3.map(w => usd(x[w].med)).join(' / ')}</td><td>${W3.map(w => usd(x[w].p25)).join(' / ')}</td><td>${x['3y'].bbook}%</td></tr>`; });
  document.getElementById('fut').innerHTML = '<thead><tr><th>Ladder</th><th>Account lost<br>2y / 3y / 10y</th><th>Median withdrawable<br>2y / 3y / 10y</th><th>Bad year (25th pct)<br>2y / 3y / 10y</th><th>B book<br>(3y)</th></tr></thead><tbody>' + rows.join('') + '</tbody>';
  document.getElementById('futhint').textContent = 'Low: first 12 funded months with different funded settings. Bold row = recommended.';
}

function texts() {
  document.getElementById('payhint').textContent = `Cumulative payouts in your pocket (after a ${SPLIT}% split) during the first 12 funded months, counted from the first funded trading day. A payout (on demand) as soon as equity minus any debt is at least ${kusd(SIZE * (1 + (KEEP + TRIG) / 100))}; everything above ${kusd(SIZE * (1 + KEEP / 100))} is withdrawn (buffer ${KEEP}%, trigger ${TRIG}%). The fee and any B-book debt are repaid first, from any profit above the start.`;
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
  const s = PLAN.plans[RULE][W], r = RULES[RULE]; texts();
  const sn = document.getElementById('shortnote');
  sn.style.display = (W === '6m' || W === '1y') ? '' : 'none';
  sn.textContent = 'Short period: a 12-month funded year is built from only ' + (W === '6m' ? '6 months' : '1 year') + ' of trades, so the same few months (including the worst one) repeat many times in random order. This exaggerates losses, especially "funded account lost". On the real trade order, no funded account started in the last year was lost. Use 3, 5 or 10 years for decisions.'; tiles(s);
  const yt = []; for (let v = -r.floor; v <= r.target; v += r.floor === 5 ? 2.5 : 2) yt.push(v); if (!yt.includes(r.target)) yt.push(r.target);
  exChart(s, svg => frame(svg, 0, 239, -r.floor - 0.6, r.target + 0.8, 360, v => kusd(SIZE * (1 + v / 100)), yt, monthTicks(8), fmtM),
          v => v / 100, [[r.target, 'Target +10%: pass', '--pos'], [-r.floor, 'Max loss -' + r.floor + '%: fail', '--neg'], [0, 'Start', '--muted']]); timeline(s); cumChart(s); fanChart(s); payChart(s);
  compare(); evTable(); fuTable();
}
function seg(id, opts, get, set) {
  const box = document.getElementById(id);
  for (const [k, lab] of opts) {
    const b = document.createElement('button'); b.textContent = lab; b.setAttribute('aria-pressed', k === get());
    b.onclick = () => { set(k); [...box.children].forEach(c => c.setAttribute('aria-pressed', c === b)); render(); }; box.appendChild(b);
  }
}
seg('size', [[10000, '$10k'], [100000, '$100k'], [200000, '$200k']], () => SIZE, v => SIZE = v);
seg('win', [['6m', 'Last 6 months'], ['1y', 'Last year'], ['2y', 'Last 2 years'], ['3y', 'Last 3 years'], ['5y', 'Last 5 years'], ['10y', '10 years (cautious)']], () => W, v => W = v);
function select(id, vals, fmt, get, set) {
  const e = document.getElementById(id);
  e.innerHTML = vals.map(v => `<option value="${v}"${v === get() ? ' selected' : ''}>${fmt(v)}</option>`).join('');
  e.onchange = () => { set(+e.value); render(); };
}
select('keep', PLAN.keeps, v => v + '%' + (v === 3 ? ' (plan)' : ''), () => KEEP, v => KEEP = v);
select('trig', PLAN.trigs, v => '+' + v + '%' + (v === 1 ? ' (plan)' : ''), () => TRIG, v => TRIG = v);
select('split', [70, 80, 90, 100], v => v + '%' + (v === 80 ? ' (FundedHive)' : ''), () => SPLIT, v => SPLIT = v);
render();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
</script>
</body>
</html>
"""
out = (HTML.replace("__STYLE__", STYLE).replace("__PLAN__", json.dumps(plan, separators=(",", ":")))
       .replace("__RES__", json.dumps(res, separators=(",", ":"))))
(ROOT / "plans" / "fundedhive_plan.html").write_text(out, encoding="utf-8")
print("written", len(out), "bytes")
