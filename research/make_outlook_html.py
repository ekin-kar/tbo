"""Builds plans/accounts_outlook.html: pass, fail, first payout and monthly payout for the user's accounts started fresh, from
research/results/income_plan.json (research/scans/income_plan.py). Same look as the plan pages (stylesheet from make_plan_html.py).
Usage:  python research/make_outlook_html.py"""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
J = json.load(open(ROOT / "research" / "results" / "income_plan.json"))
src = (ROOT / "research" / "make_plan_html.py").read_text()
STYLE = src[src.index("<style>"):src.index("</style>") + len("</style>")]
STYLE = STYLE.replace("</style>", """:root{--c1:#1d6b5b;--c2:#a47718;--c3:#2f5d8c;--c4:#7a4fa3}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--c1:#4fb39a;--c2:#d8aa4b;--c3:#79a7da;--c4:#b18ad8}}
:root[data-theme="dark"]{--c1:#4fb39a;--c2:#d8aa4b;--c3:#79a7da;--c4:#b18ad8}
.note{font-size:13px;color:var(--muted);margin:8px 2px 4px}
.acc{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(400px,100%),1fr));gap:14px;margin:14px 0 6px}
.card{border:1px solid var(--rule);border-radius:12px;background:var(--surface);padding:16px 18px;border-top:4px solid var(--cc)}
.card h3{margin:0 0 12px;font-size:17px}
.card dl{display:grid;grid-template-columns:1fr auto;gap:7px 12px;margin:0;font-size:14px}
.card dt{color:var(--muted)}.card dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
.big2{font-size:21px;font-weight:700}.small{font-size:12px;color:var(--muted)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:7px;vertical-align:baseline}
.legend2{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:14px;margin:4px 2px 8px}
#chart{width:100%;height:auto;display:block}
#chart text{fill:var(--muted);font-size:12px;font-family:inherit;pointer-events:none}
.chartbox{position:relative;padding:10px 6px}
#tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:10px 12px;
  font-size:13px;box-shadow:0 6px 18px rgba(0,0,0,.18);min-width:190px;display:none;z-index:5}
#tip .t{font-weight:700;margin-bottom:6px}#tip .r{display:flex;justify-content:space-between;gap:16px;font-variant-numeric:tabular-nums}
#tip .tot{border-top:1px solid var(--rule);margin-top:6px;padding-top:6px;font-weight:700}
</style>""")

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Accounts outlook</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
__STYLE__
</head>
<body>
<div class="wrap">
  <h1>My accounts: what to expect</h1>
  <p class="lede">Four accounts started on <b>5 Oct 2026</b>: <b>FundedHive 200k</b> and <b>10k</b> (1-step Low) and <b>Funding Pips 10k</b>
    and <b>50k</b> (1-Step Flex). All run on the <b>same</b> simulated market, because the bots trade the same signals everywhere, each with
    its plan: evaluation / challenge, then the funded account 3 days after passing. Payouts are what reaches you after the 80% split.
    A failed account pays nothing (no re-buy assumed).</p>
  <div class="controls">
    <div><div class="ctl-title">Based on market data from</div><div class="seg" id="win"></div></div>
  </div>
  <p class="note" id="shortnote" style="display:none"></p>

  <h2>At a glance</h2>
  <div class="scroll panel"><table id="sum"></table></div>
  <p class="note">"Per month once funded" = paid in the first 12 funded months divided by 12: the typical case (median) and the average.
    Payouts come in lumps, not evenly.</p>

  <h2>Paid to you each month</h2>
  <p class="hint">Average amount paid in each month, all accounts stacked. The average includes the paths that pay nothing that month,
    so it shows what a month is worth on average, not a fixed salary.</p>
  <div class="legend2" id="legend"></div>
  <div class="panel chartbox" id="chartbox"><svg id="chart" viewBox="0 0 960 360" role="img" aria-label="Average payout per month by account"></svg><div id="tip"></div></div>

  <div class="acc" id="cards"></div>

  <h2>Total paid so far, month by month</h2>
  <p class="hint">Cumulative amount paid to you by the end of each month, all accounts together, and the median per account.</p>
  <div class="scroll panel"><table id="cum"></table></div>

  <h2>Plans behind these numbers</h2>
  <div class="specs">
    <div class="spec"><h3>FundedHive Low (200k, 10k)</h3><dl>
      <dt>Evaluation</dt><dd>0.4% / 0.5%, risk scaling from the start (min 0.3&times;), +10% to pass, 5% max loss</dd>
      <dt>Funded</dt><dd>ladder 0.25/0.35 &rarr; 0.50/0.60 by buffer + risk scaling, no manual B-book cuts</dd>
      <dt>Fee</dt><dd>1%, repaid at once from profit above the start; B book below 99% adds 1% debt</dd>
      <dt>Payouts</dt><dd>on demand at +4% (start + 3% kept + 1%), 80% split</dd></dl></div>
    <div class="spec"><h3>Funding Pips 1-Step Flex (10k, 50k)</h3><dl>
      <dt>Challenge</dt><dd>0.7% / 0.9%, full risk down to -4%, then shrink (min 0.3&times;), +12% to pass, 12% max loss, 2% daily</dd>
      <dt>Funded</dt><dd>0.5% / 0.6% with the same risk scaling</dd>
      <dt>Payouts</dt><dd>every 14 days at +2% (1% kept), 80% split</dd></dl></div>
  </div>

  <h2>How to read this</h2>
  <ul class="notes">
    <li>Simulations from the bots' backtested trades with every firm rule applied minute by minute on live equity, 3,000 paths per period. Not promises: live results have run about 12-14% below the engine.</li>
    <li>The rules are the same in percent for both sizes of a firm, so 200k and 10k (and 10k and 50k) pass and fail together; only the dollars differ. On 10k accounts gold trades about 12% smaller than planned (lot rounding), so the 10k figures are slightly optimistic.</li>
    <li>"Last 6 months" and "Last year" reuse only a few months of trades, which exaggerates both good and bad runs; use 3, 5 or 10 years for decisions. "10 years" includes 2016-2018, a weak period for gold.</li>
    <li>FundedHive's first payout comes months after passing: the 1% fee is repaid first, then the account has to reach +4% at the ladder's small starting risk, and a dip below 99% adds another 1% debt.</li>
    <li>Funding Pips 50k is assumed to have the same rules as the 10k (1-Step Flex, 2% daily). Built from research/scans/income_plan.py.</li>
  </ul>
</div>
<script>
const J = __DATA__;
const TODAY = new Date(J.today + 'T00:00:00Z');
const COLS = ['--c1', '--c2', '--c3', '--c4'];
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const day = d => new Date(TODAY.getTime() + d * 864e5);
const fmtD = d => d == null ? '-' : day(d).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
const fmtM = d => d == null ? '-' : day(d).toLocaleDateString('en-GB', {month: 'short', year: 'numeric', timeZone: 'UTC'});
const mo = d => d == null ? '' : (d / 30.44).toFixed(1) + ' months';
const usd = v => v == null ? '-' : '$' + Math.round(v).toLocaleString('en-US');
const kusd = v => v >= 1000 ? '$' + (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k' : '$' + Math.round(v);
const NS = 'http://www.w3.org/2000/svg';
const el = (t, a, p) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; };
let W = '3y';
function chart(T) {
  const svg = document.getElementById('chart'); svg.innerHTML = '';
  const L = 58, R = 948, top = 14, B = 318, n = J.months.length, M = T.monthly_mean;
  const tot = J.months.map((_, k) => M.reduce((s, r) => s + r[k], 0));
  const raw = Math.max(...tot, 1), step = [100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000].find(s => raw / s <= 6) || 20000;
  const ymax = Math.ceil(raw / step) * step, Y = v => B - (B - top) * v / ymax, bw = (R - L) / n;
  for (let v = 0; v <= ymax + 1e-9; v += step) {
    el('line', {x1: L, x2: R, y1: Y(v), y2: Y(v), stroke: css('--rule'), 'stroke-width': 1}, svg);
    const t = el('text', {x: L - 8, y: Y(v) + 4, 'text-anchor': 'end'}, svg); t.textContent = kusd(v);
  }
  J.months.forEach((m, k) => {
    let y0 = 0;
    M.forEach((r, a) => {
      if (r[k] <= 0) return;
      const h = Y(y0) - Y(y0 + r[k]);
      el('rect', {x: L + k * bw + bw * 0.16, width: bw * 0.68, y: Y(y0 + r[k]), height: Math.max(h, 0.5), fill: css(COLS[a]), rx: 2, 'pointer-events': 'none'}, svg);
      y0 += r[k];
    });
    if (tot[k] >= ymax * 0.06) { const t = el('text', {x: L + k * bw + bw / 2, y: Y(tot[k]) - 5, 'text-anchor': 'middle'}, svg); t.textContent = kusd(tot[k]); }
    if (k % 2 === 0 || n <= 12) { const t = el('text', {x: L + k * bw + bw / 2, y: B + 18, 'text-anchor': 'middle'}, svg); t.textContent = m.replace(' 20', " '"); }
  });
  el('line', {x1: L, x2: R, y1: B, y2: B, stroke: css('--muted'), 'stroke-width': 1}, svg);
  // hover / tap: one invisible column per month shows that month's amounts
  const tip = document.getElementById('tip'), box = document.getElementById('chartbox');
  const hl = el('rect', {y: top, height: B - top, width: bw, fill: css('--soft'), opacity: 0, 'pointer-events': 'none'}, svg);
  svg.insertBefore(hl, svg.firstChild);
  const show = (k, ev) => {
    hl.setAttribute('x', L + k * bw); hl.setAttribute('opacity', 1);
    tip.innerHTML = `<div class="t">${J.months[k]} (average)</div>` + M.map((r, a) => `<div class="r"><span><span class="dot" style="background:var(${COLS[a]})"></span>${J.accounts[a]}</span><span>${usd(r[k])}</span></div>`).join('') +
      `<div class="r tot"><span>Total</span><span>${usd(tot[k])}</span></div>`;
    tip.style.display = 'block';
    const bx = box.getBoundingClientRect(), x = ev.clientX - bx.left, y = ev.clientY - bx.top, tw = tip.offsetWidth;
    tip.style.left = Math.max(6, Math.min(x + 14, bx.width - tw - 6)) + 'px'; tip.style.top = Math.max(6, y - 20) + 'px';
  };
  const hide = () => { tip.style.display = 'none'; hl.setAttribute('opacity', 0); };
  window._hideTip = hide;
  if (!window._tipOutside) { window._tipOutside = true; document.addEventListener('pointerdown', ev => { if (!box.contains(ev.target)) window._hideTip(); }); }
  J.months.forEach((m, k) => {
    const hit = el('rect', {x: L + k * bw, y: top, width: bw, height: B - top + 24, fill: 'transparent', style: 'cursor:pointer'}, svg);
    hit.addEventListener('pointermove', ev => show(k, ev)); hit.addEventListener('pointerdown', ev => show(k, ev));
    hit.addEventListener('pointerleave', ev => { if (ev.pointerType !== 'touch') hide(); });   // a tap keeps it open
  });
}
function render() {
  const T = J.windows[W], A = T.accounts;
  const sn = document.getElementById('shortnote'); sn.style.display = (W === '6m' || W === '1y') ? '' : 'none';
  sn.textContent = 'Short period: only ' + (W === '6m' ? '6 months' : '1 year') + ' of trades are reused many times, which exaggerates both good and bad runs. Use 3, 5 or 10 years for decisions.';
  document.getElementById('legend').innerHTML = J.accounts.map((n, a) => `<span><span class="dot" style="background:var(${COLS[a]})"></span>${n}</span>`).join('');
  document.getElementById('sum').innerHTML = '<thead><tr><th>Account</th><th class="num">Pass chance</th><th class="num">Expected pass<br>(median)</th><th class="num">First payout<br>(median)</th><th class="num">Per month once funded<br>typical (average)</th><th class="num">Funded account<br>lost in year 1</th></tr></thead><tbody>' +
    A.map((a, i) => `<tr><td><span class="dot" style="background:var(${COLS[i]})"></span><b>${a.name}</b></td>
    <td class="num">${a.pass_pct.toFixed(0)}%<div class="small">fail ${a.fail_pct.toFixed(0)}%</div></td>
    <td class="num">${fmtM(a.pass_days['50'])}<div class="small">${mo(a.pass_days['50'])}</div></td>
    <td class="num">${fmtM(a.first_pay_days['50'])}<div class="small">${mo(a.first_pay_days['50'])}</div></td>
    <td class="num"><b>${usd(a.paid12['50'] / 12)}</b><div class="small">average ${usd(a.paid12_mean / 12)}</div></td>
    <td class="num">${a.funded_lost_pct.toFixed(1)}%</td></tr>`).join('') + '</tbody>';
  chart(T);
  document.getElementById('cards').innerHTML = A.map((a, i) => `<div class="card" style="--cc:var(${COLS[i]})"><h3>${a.name}</h3><dl>
    <dt>Passes</dt><dd>${a.pass_pct.toFixed(1)}% <span class="small">(fails ${a.fail_pct.toFixed(1)}%)</span></dd>
    <dt>Pass date, median</dt><dd><b>${fmtD(a.pass_days['50'])}</b></dd>
    <dt>&nbsp;&nbsp;middle half</dt><dd>${fmtM(a.pass_days['25'])} - ${fmtM(a.pass_days['75'])}</dd>
    <dt>First payout, median</dt><dd><b>${fmtD(a.first_pay_days['50'])}</b></dd>
    <dt>&nbsp;&nbsp;middle half</dt><dd>${fmtM(a.first_pay_days['25'])} - ${fmtM(a.first_pay_days['75'])}</dd>
    <dt>Paid within 12 months</dt><dd>${a.paid_within_12m.toFixed(0)}% of paths</dd>
    <dt>First funded year</dt><dd><span class="big2">${usd(a.paid12['50'])}</span></dd>
    <dt>&nbsp;&nbsp;middle half</dt><dd>${usd(a.paid12['25'])} - ${usd(a.paid12['75'])}</dd>
    <dt>&nbsp;&nbsp;per month, typical / average</dt><dd>${usd(a.paid12['50'] / 12)} / ${usd(a.paid12_mean / 12)}</dd>
    <dt>Funded account lost in year 1</dt><dd>${a.funded_lost_pct.toFixed(1)}%</dd></dl></div>`).join('');
  document.getElementById('cum').innerHTML = `<thead><tr><th>End of</th><th class="num">All accounts<br>median</th><th class="num">Bad case<br>(25%)</th><th class="num">Good case<br>(75%)</th><th class="num">Average</th>${J.accounts.map(n => `<th class="num">${n}<br>(median)</th>`).join('')}</tr></thead><tbody>` +
    J.months.map((m, k) => `<tr><td>${m}</td><td class="num"><b>${usd(T.total['50'][k])}</b></td><td class="num">${usd(T.total['25'][k])}</td><td class="num">${usd(T.total['75'][k])}</td><td class="num">${usd(T.total_mean[k])}</td>${T.by_acc_median.map(r => `<td class="num">${usd(r[k])}</td>`).join('')}</tr>`).join('') + '</tbody>';
}
const box = document.getElementById('win');
for (const [k, lab] of [['6m', 'Last 6 months'], ['1y', 'Last year'], ['2y', 'Last 2 years'], ['3y', 'Last 3 years'], ['5y', 'Last 5 years'], ['10y', '10 years (cautious)']]) {
  const b = document.createElement('button'); b.textContent = lab; b.setAttribute('aria-pressed', k === W);
  b.onclick = () => { W = k; [...box.children].forEach(c => c.setAttribute('aria-pressed', c === b)); render(); }; box.appendChild(b);
}
render();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
</script>
</body>
</html>
"""
out = HTML.replace("__STYLE__", STYLE).replace("__DATA__", json.dumps(J, separators=(",", ":")))
(ROOT / "plans" / "accounts_outlook.html").write_text(out, encoding="utf-8")
print("written", len(out), "bytes")
