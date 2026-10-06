"""Builds the bot statistics pages, one per firm: fundedhive_statistics.html and fundingpips_statistics.html.

Same trade list as every other report (gold PDAYT 01:15 UTC / EMA40 + USDJPY VOLC with Friday close, current costs, live-gap
deduction). Every trade also carries its floating result hour by hour (worst point of each hour and the value at the end of
each hour, in R, from the 1-minute bars), so the page can run the account the way the firm sees it: live equity including
floating P&L, the daily loss measured from max(balance, equity) at the firm's daily reset, the bots' own account-wide daily
stop, and the firm's static floor and target. Equity is checked at the minute of every open trade's worst point in each hour,
with all open trades valued at that same minute; this reproduces the minute-level simulators (fundingpips_sim.py,
fundedhive_sim.py) to within about half a point of pass chance.
Usage:  TRADING_DATA=<folder with data> python research/make_stats_html.py
"""
import sys, pathlib, json; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd
import R, ideas as X, fundingpips_sim as F

ROOT = pathlib.Path(__file__).resolve().parent.parent


def trades():
    G = F.clean("XAUUSD", R.run("XAUUSD", X.pday_trend(R.get("XAUUSD")), "main"), 0.02)
    V = F.clean("USDJPY", R.run("USDJPY", X.volc_f(R.get("USDJPY")), "main", max_bars=20 * 60), 0.002)   # v5.3: 20 h max hold
    tl = []                                        # (sym, dir, R, entry minute, exit minute, fc, fw) per trade
    for s, sym, tr in ((0, "XAUUSD", G), (1, "USDJPY", V)):
        e0, e1, fc, fw, off = F.floats(sym, tr)
        for k in range(len(tr)):
            a, b = int(e0[k]), int(e1[k])
            tl.append((s, int(tr.dir.values[k]), round(float(tr.R.values[k]), 3), a, b,
                       fc[off[k]: off[k] + b - a + 1], fw[off[k]: off[k] + b - a + 1]))
    tl.sort(key=lambda t: (t[3], t[0]))
    # candidate minutes per hour: the minute of every open trade's worst point in that hour
    cand = {}
    for s, d, r, a, b, c, w in tl:
        for H in range(a // 60, b // 60 + 1):
            lo, hi = max(a, H * 60) - a, min(b, H * 60 + 59) - a
            cand.setdefault(H, set()).add((a + lo + int(np.argmin(w[lo: hi + 1]))) % 60)
    cand = {H: sorted(m) for H, m in cand.items()}
    rows = []
    for s, d, r, a, b, c, w in tl:
        V, cs = [], []
        for H in range(a // 60, b // 60 + 1):        # worst-side value at each candidate minute (None outside the trade's life)
            V.append([int(np.floor(w[H * 60 + mu - a] * 100)) if a <= H * 60 + mu <= b else None for mu in cand[H]])
            if H < b // 60: cs.append(int(round(c[H * 60 + 59 - a] * 100)))
        rows.append([round(b / 1440, 4), round(a / 1440, 4), s, d, r, a // 60, a % 60, b % 60, V, cs])
    hours = sorted(cand)
    return rows, dict(h=hours, m=[cand[H] for H in hours])


FIRMS = {
    "fundedhive": dict(
        file="stats/fundedhive_statistics.html", title="FundedHive bot statistics", firm="FundedHive", reset=0, rg=0.4, rj=0.5,
        accounts=[dict(id="low", label="1-step Low", daily=2, floor=5, target=10, guard=1.5, minm=0.3, dz=0,
                       rules="1% max per trade, 2% daily loss, 5% static max loss, +10% target")],
        match="Trades come from a 1-minute backtest engine that matched a cTrader tick backtest trade for trade "
              "(226 of 226 trades, same day and direction)."),
    "fundingpips": dict(
        file="stats/fundingpips_statistics.html", title="Funding Pips bot statistics", firm="Funding Pips", reset=21, rg=0.7, rj=0.9,
        accounts=[dict(id="flex", label="1-Step Flex, 2% daily", daily=2, floor=12, target=12, guard=1.5, minm=0.3, dz=4,
                       rules="2% daily loss (from max of balance and equity at 00:00 platform time = 21:00 UTC), "
                             "12% static max loss, +12% target, no per-trade limit")],
        match="Trades come from a 1-minute backtest engine. Against a cTrader tick backtest on Funding Pips data, 375 of 377 trades "
              "were on the same day and direction and 95% had the same outcome; the cTrader result was about 14% below the engine, "
              "so treat the R totals as a ceiling."),
}

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f3f4f1; --surface:#ffffff; --ink:#18212b; --muted:#5d6874; --rule:#d9ddd6; --soft:#eceee9;
  --gold:#a47718; --jpy:#2f5d8c; --comb:#1d6b5b; --neg:#b3432f; --pos:#1d6b5b;
  box-sizing:border-box; padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#12171d; --surface:#19212a; --ink:#e7eaec; --muted:#9aa5b0; --rule:#2c3640; --soft:#1f2832;
  --gold:#d8aa4b; --jpy:#79a7da; --comb:#4fb39a; --neg:#e07a64; --pos:#4fb39a; } }
:root[data-theme="dark"]{
  --bg:#12171d; --surface:#19212a; --ink:#e7eaec; --muted:#9aa5b0; --rule:#2c3640; --soft:#1f2832;
  --gold:#d8aa4b; --jpy:#79a7da; --comb:#4fb39a; --neg:#e07a64; --pos:#4fb39a; }
*,*::before,*::after{box-sizing:inherit}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-variant-numeric:tabular-nums;}
.wrap{max-width:1120px;margin:0 auto;padding:28px 16px 56px}
h1{font-size:clamp(26px,4vw,38px);line-height:1.1;margin:0 0 6px;font-weight:700;letter-spacing:-.01em}
.lede{color:var(--muted);margin:0 0 22px;max-width:72ch}
.lede b{color:var(--ink);font-weight:600}
h2{font-size:20px;margin:40px 0 4px;font-weight:600}
.hint{color:var(--muted);margin:0 0 14px;font-size:14px;max-width:78ch}
.controls{display:flex;flex-wrap:wrap;gap:14px 26px;align-items:end;margin-bottom:16px}
.seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--rule);border-radius:8px;overflow:hidden;background:var(--surface)}
.seg button{font:inherit;font-size:14px;border:0;background:none;color:var(--ink);padding:8px 13px;cursor:pointer;border-right:1px solid var(--rule)}
.seg button:last-child{border-right:0}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.seg button:focus-visible,input:focus-visible{outline:2px solid var(--comb);outline-offset:2px}
label.risk{font-size:13px;color:var(--muted);display:flex;flex-direction:column;gap:4px}
label.risk input{font:inherit;width:84px;padding:7px 9px;border:1px solid var(--rule);border-radius:8px;background:var(--surface);color:var(--ink)}
.ctl-title{font-size:13px;color:var(--muted);margin-bottom:4px}
.panel{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:16px 16px 10px}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;margin:0 0 6px}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{width:18px;height:3px;border-radius:2px;display:inline-block}
svg text{fill:var(--muted);font-size:12px;font-family:inherit}
.chart-cap{font-size:13px;color:var(--muted);margin:6px 2px 4px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--rule);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{font-weight:600;color:var(--muted);font-size:13px;border-bottom:1.5px solid var(--ink)}
tr:hover>td{background:var(--soft);background:color-mix(in srgb,var(--ink) 8%,var(--surface))}
.g{color:var(--gold)} .j{color:var(--jpy)} .c{color:var(--comb)}
.neg{color:var(--neg)} .pos{color:var(--pos)}
th.g,th.j,th.c{font-size:14px}
.big{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:10px;overflow:hidden;margin-bottom:18px}
.big div{background:var(--surface);padding:12px 14px}
.big b{display:block;font-size:24px;font-weight:600;line-height:1.2}
.big small{color:var(--muted);font-size:13px}
.rules{font-size:14px;color:var(--muted);margin:0 0 14px}
.rules b{color:var(--ink);font-weight:600}
.specs{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:18px}
.spec{border-top:3px solid var(--gold);background:var(--surface);border-radius:0 0 10px 10px;padding:14px 16px}
.spec.jp{border-top-color:var(--jpy)}
.spec h3{margin:0 0 2px;font-size:17px}
.spec p{margin:0 0 10px;color:var(--muted);font-size:14px}
.spec dl{display:grid;grid-template-columns:max-content 1fr;gap:5px 14px;margin:0;font-size:14px}
.spec dt{color:var(--muted)} .spec dd{margin:0}
.notes{font-size:13px;color:var(--muted);max-width:80ch;padding-left:18px}
.notes li{margin-bottom:5px}
@media (max-width:640px){ th,td{padding:7px 7px} .seg button{padding:7px 9px} .big b{font-size:20px} }
</style>
</head>
<body>
<div class="wrap">
  <h1>__TITLE__</h1>
  <p class="lede">Every trade of <b>PDAYT</b> (gold, bot v1.5) and <b>VOLC</b> (USDJPY, bot v5.5 with the 20-hour max hold) from January 2016 to __ENDTXT__, at current costs.
  Percent figures run the account the way <b>__FIRM__</b> measures it: live equity with floating losses, the daily loss from the
  __RESETTXT__ reset, the bots' own daily stop, and the bots' <b>risk scaling below the starting balance</b> (full risk until the balance is the "shrink from" % below the start,
  then risk &times; the share of the room left to the firm's floor, never below the "min risk &times;" box; min 1 = off). Pick a period and your risk; everything recalculates.</p>

  <div class="controls">
    <div><div class="ctl-title">Period</div><div class="seg" id="periods"></div></div>
    <div id="acctbox"><div class="ctl-title">Account rules</div><div class="seg" id="accts"></div></div>
    <label class="risk">Gold risk per trade (%)<input id="rg" type="number" step="0.05" min="0.05" max="3" value="__RG__"></label>
    <label class="risk">USDJPY risk per trade (%)<input id="rj" type="number" step="0.05" min="0.05" max="3" value="__RJ__"></label>
    <label class="risk" title="Bots v1.5 / v5.5: full risk until the balance is this far below the start, then the risk shrinks with the room left to the firm's floor. 0 = shrink from the start.">Shrink from (% below start)<input id="dz" type="number" step="0.5" min="0" max="20" value="__DZ__"></label>
    <label class="risk" title="Bots v1.5 / v5.5: the shrink never goes below this factor. 1 = scaling off.">Shrink: min risk &times;<input id="mm" type="number" step="0.05" min="0.05" max="1" value="__MM__"></label>
  </div>

  <div class="big" id="headline"></div>

  <div class="panel">
    <div class="controls" style="margin-bottom:8px"><div class="seg" id="chartmode"></div>
    <div class="legend" style="margin:0"><span><i style="background:var(--comb)"></i>Combined</span><span><i style="background:var(--gold)"></i>Gold (PDAYT)</span><span><i style="background:var(--jpy)"></i>USDJPY (VOLC)</span></div></div>
    <svg id="eq" viewBox="0 0 1000 360" width="100%" role="img" aria-label="Account growth"></svg>
    <div class="chart-cap"><span id="eqcap"></span> Below: drawdown of the combined account from its peak, on live equity (floating losses included), at your risk settings. The firm's max loss is measured from the starting balance, not from a peak: see the prop account check below.</div>
    <svg id="dd" viewBox="0 0 1000 150" width="100%" role="img" aria-label="Live-equity drawdown in percent"></svg>
  </div>

  <h2>Prop account check</h2>
  <p class="rules" id="rulesnote"></p>
  <p class="hint">A fresh evaluation started every week of the selected period, each on the real trades that followed (at most 2 years).
  Starts near the end of the data have not finished yet. This is the hard test: real order, no reshuffling.</p>
  <div class="big" id="evalbox"></div>
  <div class="scroll panel"><table id="evaltab"></table></div>

  <h2>Statistics for the selected period</h2>
  <p class="hint" id="periodnote"></p>
  <div class="scroll panel"><table id="stats"></table></div>

  <h2>The same numbers across periods</h2>
  <p class="hint">For answering "what was the win rate over 10 years, 5 years, last year". Choose which bot to show.</p>
  <div class="controls"><div class="seg" id="which"></div></div>
  <div class="scroll panel"><table id="across"></table></div>

  <h2>Year by year</h2>
  <p class="hint">Result in R and win rate per calendar year; the last column is the combined account at your risk on live equity. 2016 and __ENDYEAR__ are partial years.</p>
  <div class="scroll panel"><table id="years"></table></div>

  <h2>How the bots trade</h2>
  <div class="specs">
    <div class="spec">
      <h3 class="g">PDAYT, gold (XAUUSD)</h3>
      <p>Breakout of the previous day's high or low, only in the direction of the daily trend. Orders go in during the Asian session.</p>
      <dl>
        <dt>Entry</dt><dd>01:15 UTC stop order at the previous day's high (buy) or low (sell), valid until 20:00</dd>
        <dt>Trend filter</dt><dd>Only buys if yesterday's close is above the daily EMA40, only sells if below</dd>
        <dt>Stop-loss</dt><dd>2.0 × ATR14 on 15-minute bars</dd>
        <dt>Take-profit</dt><dd>2R (reward : risk 1 : 2)</dd>
        <dt>Exit</dt><dd>Stop, target, or flat at 20:00 UTC</dd>
        <dt>Frequency</dt><dd>At most 1 trade per day, never overnight</dd>
      </dl>
    </div>
    <div class="spec jp">
      <h3 class="j">VOLC, USDJPY</h3>
      <p>Breakout after a quiet period: when volatility contracts, it trades the range break.</p>
      <dl>
        <dt>Condition</dt><dd>ATR14 on 1-hour bars below 0.8 × ATR100</dd>
        <dt>Entry</dt><dd>Stop orders at the 10-bar high and low, valid 24 hours</dd>
        <dt>Stop-loss</dt><dd>1.5 × ATR14 (1-hour)</dd>
        <dt>Take-profit</dt><dd>2.5R (reward : risk 1 : 2.5)</dd>
        <dt>Exit</dt><dd>Stop, target, closed after 20 hours (v5.3), or flat on Friday 20:00 UTC</dd>
        <dt>Frequency</dt><dd>Several trades a day possible; no new orders 20:30–23:00 UTC</dd>
      </dl>
    </div>
  </div>

  <h2>How these numbers were made</h2>
  <ul class="notes">
    <li>__MATCH__</li>
    <li>Costs: current broker spreads (gold 0.003%, USDJPY 0.001% of price, with the real minute-by-minute pattern) plus $30 per $1M commission. Every trade is also reduced by the measured gap between backtest and live cTrader execution (gold 0.02R, USDJPY 0.002R).</li>
    <li>Data: Dukascopy prices 2016–2024, broker prices from 2025. Trades that crossed whole missing days in the old data are left out.</li>
    <li>R figures (win rate, profit factor, net R, drawdown in R) are pure trade statistics and do not depend on risk or firm.</li>
    <li>Percent figures run one account through the period hour by hour: position size = risk % of balance at entry (as the bots size it), equity includes every open trade's floating result, below the shrink level (start &times; (1 - shrink from %)) the size is multiplied by max(min risk &times;, (balance - floor) / (shrink level - floor)) as the bots v1.5 / v5.5 do, the bots' daily stop (__GUARDTXT__) closes everything and stops trading until the next reset, and the daily loss is measured from the higher of balance and equity at __RESETTXT__. Equity is checked at the minute of every open trade's worst point in each hour; this matches the minute-by-minute simulators behind the plans to within about half a point of pass chance.</li>
    <li>Settings were chosen after testing many alternatives on this history, so long-run figures are somewhat optimistic. A backtest is not a promise: past behaviour does not guarantee future results.</li>
  </ul>
</div>

<script>
const DATA = __DATA__;
const CFG = __CFG__;
const T = DATA.trades.map(r=>({x:r[0],e:r[1],s:r[2],d:r[3],R:r[4],eh:r[5],em:r[6],xm:r[7],V:r[8],c:r[9].map(v=>v/100)}));
for(const t of T) t.xh=t.eh+t.V.length-1;
const CAND=new Map(DATA.cand.h.map((h,i)=>[h,DATA.cand.m[i]]));   // hour -> minutes at which equity is checked
const END = DATA.endDay;                     // day after the last trading day in the data
const ENDH = END*24;
const dayOf = s => Date.UTC(+s.slice(0,4),+s.slice(5,7)-1,+s.slice(8,10))/864e5;
const PERIODS = DATA.periods.map(p=>({id:p[0],label:p[1],from:dayOf(p[2])}));
const STRATS=[{k:'c',name:'Combined'},{k:'g',name:'Gold (PDAYT)'},{k:'j',name:'USDJPY (VOLC)'}];
const SLIP=0.0005, RESET=CFG.reset;
let cur='all', which='c', acct=CFG.accounts[0].id;

const pick=(from,k)=>T.filter(t=>t.e>=from&&t.e<END&&(k==='c'||(k==='g'?t.s===0:t.s===1)));
const risk=()=>({g:Math.max(0,+document.getElementById('rg').value||0)/100, j:Math.max(0,+document.getElementById('rj').value||0)/100,
                  m:Math.min(1,Math.max(0.05,+document.getElementById('mm').value||1)),
                  dz:Math.min(50,Math.max(0,+document.getElementById('dz').value||0))/100});
const A=()=>{const a=CFG.accounts.find(x=>x.id===acct);return {...a,dailyF:a.daily/100,floorF:1-a.floor/100,targetF:1+a.target/100,guardF:a.guard/100}};
const rmod=h=>((h-RESET)%24+24)%24;

/* One account through `list` (trades in time order), hour by hour, on live equity.
   firm=true: stop at pass (balance >= target) or fail (floor or firm daily limit). Returns a summary. */
function sim(list,r,a,firm,maxH){
  const n=list.length; const out={status:0,hours:0,why:'',bal:1,mdd:0,worstDay:0,guardDays:0,breachDays:0,pts:[],floorLow:1};
  if(!n) return out;
  const h0=list[0].eh-rmod(list[0].eh); const stopH=Math.min(ENDH,maxH?h0+maxH:Infinity);
  let h=h0,bal=1,base=1,halted=false,open=[],j=0,peak=1,dayLow=0,dayBreach=false;
  out.pts.push([h0,1,0]);
  const closeDay=()=>{out.worstDay=Math.min(out.worstDay,dayLow); if(dayBreach) out.breachDays++; dayLow=0; dayBreach=false};
  while(true){
    if(!open.length){
      if(j>=n) break;
      const nr=rmod(h)===0?h:h+24-rmod(h); h=Math.min(list[j].eh,nr);
    }
    if(h>=stopH) break;
    if(rmod(h)===0){
      let eq=bal; for(const o of open) if(h>o.t.eh) eq+=o.sz*o.t.c[h-1-o.t.eh];
      if(h>h0) closeDay(); base=Math.max(bal,eq); halted=false;
    }
    // bots v1.5 / v5.5: full risk until the balance is r.dz below the start, then it shrinks with the room left to the floor, never below r.m
    const sc=(r.m<1&&bal<1-r.dz)?Math.max(r.m,Math.max(0,(bal-a.floorF)/((1-r.dz)-a.floorF))):1;
    while(j<n&&list[j].eh===h){ if(!halted) open.push({t:list[j],sz:(list[j].s===0?r.g:r.j)*bal*sc}); j++; }
    // equity at the minute of every open trade's worst point this hour (all trades valued at that same minute;
    // trades already closed count at their final result, trades not yet entered are left out)
    let ew=bal;
    if(open.length){
      ew=Infinity; const mins=CAND.get(h);
      for(let i=0;i<mins.length;i++){
        const mu=mins[i]; let e=bal, any=false;
        for(const o of open){const t=o.t; if(t.eh===h&&t.em>mu) continue; any=true;
          e+=o.sz*((t.xh===h&&t.xm<mu)?t.R:t.V[h-t.eh][i]/100)}
        if(any) ew=Math.min(ew,e); if(ew<=base*(1-a.guardF)) break;
      }
      if(ew===Infinity) ew=bal;
    }
    let low=ew;
    if(open.length&&ew<=base*(1-a.guardF)){
      const lvl=base*(1-a.guardF)-SLIP*base; low=lvl;
      if(lvl<=base*(1-a.dailyF)) dayBreach=true;
      bal=lvl; open=[]; halted=true; out.guardDays++;
    } else if(ew<=base*(1-a.dailyF)) dayBreach=true;
    dayLow=Math.min(dayLow,low/base-1); out.mdd=Math.max(out.mdd,1-low/peak); out.floorLow=Math.min(out.floorLow,low);
    if(firm&&(dayBreach||low<=a.floorF)){out.status=-1; out.why=low<=a.floorF?'floor':'daily'; out.hours=h-h0; break}
    let k=0; while(k<open.length){const o=open[k]; if(o.t.xh===h){bal+=o.sz*o.t.R; open.splice(k,1)} else k++}
    let eqEnd=bal; for(const o of open) eqEnd+=o.sz*o.t.c[h-o.t.eh];
    peak=Math.max(peak,eqEnd,bal);
    out.pts.push([h,bal,1-low/peak]);
    if(firm&&bal>=a.targetF){out.status=1; out.hours=h-h0; break}
    h++;
  }
  if(!out.status){closeDay(); out.hours=h-h0}
  out.bal=bal; return out;
}

function evals(from,r,a){
  const res={pass:[],fail:0,floor:0,daily:0,open:0,n:0};
  const first=Math.ceil((from-2)/7)*7+2;                 // first Saturday (day number % 7 == 2) on or after `from`
  const all=T;
  for(let d=first; d<END; d+=7){
    const sH=d*24; let k=all.findIndex(t=>t.eh>=sH); if(k<0) break;
    const s=sim(all.slice(k),r,a,true,24*730);
    res.n++;
    if(s.status===1) res.pass.push(s.hours/24/30.4);
    else if(s.status===-1){res.fail++; res[s.why]++}
    else res.open++;
  }
  res.pass.sort((x,y)=>x-y); return res;
}

function stats(list,from){
  const n=list.length; const yrs=(END-from)/365.25;
  let pos=0,neg=0,wins=0,cum=0,peak=0,mdd=0,streak=0,maxStreak=0,L=0,S=0,sw=0,sl=0,nl=0;
  const months={};
  for(const t of [...list].sort((a,b)=>a.x-b.x)){
    if(t.R>0){pos+=t.R;wins++;sw+=t.R;streak=0}else{neg-=t.R;sl+=t.R;nl++;streak++;maxStreak=Math.max(maxStreak,streak)}
    cum+=t.R; peak=Math.max(peak,cum); mdd=Math.max(mdd,peak-cum);
    if(t.d===1)L+=t.R; else S+=t.R;
    const dt=new Date(t.x*864e5); const mk=dt.getUTCFullYear()*12+dt.getUTCMonth(); months[mk]=(months[mk]||0)+t.R;
  }
  const mv=Object.values(months);
  const s=sim(list,risk(),A(),false);
  return {n, perYr:n/yrs, wr:n?wins/n:0, pf:neg?pos/neg:Infinity, net:cum, avg:n?cum/n:0,
    avgW:wins?sw/wins:0, avgL:nl?sl/nl:0, mdd, ret:s.bal-1, cagr:yrs>0?Math.pow(Math.max(s.bal,1e-9),1/yrs)-1:0, mddp:s.mdd,
    worstDay:s.worstDay, guardDays:s.guardDays, breachDays:s.breachDays,
    rdd:mdd?cum/mdd:0, pm:mv.length?mv.filter(v=>v>0).length/mv.length:0, nm:mv.length,
    best:mv.length?Math.max(...mv):0, worst:mv.length?Math.min(...mv):0, streak:maxStreak, L, S, sim:s};
}
const f1=v=>(v>=0?'+':'')+v.toFixed(1), f2=v=>v.toFixed(2), pct=v=>(v*100).toFixed(1)+'%', spct=v=>(v>=0?'+':'')+(v*100).toFixed(1)+'%';
const sign=v=>v>=0?'pos':'neg';
const rtxt=r=>`${+(r.g*100).toFixed(2)}% / ${+(r.j*100).toFixed(2)}%`;

function seg(id,items,curv,set){
  const el=document.getElementById(id); el.innerHTML='';
  for(const it of items){const b=document.createElement('button');b.textContent=it.label;b.setAttribute('aria-pressed',it.id===curv);
    b.onclick=()=>{set(it.id);render()}; el.appendChild(b)}
}
function renderControls(){
  seg('periods',PERIODS,cur,v=>cur=v);
  seg('accts',CFG.accounts,acct,v=>{acct=v; const ac=CFG.accounts.find(x=>x.id===v); document.getElementById('mm').value=ac.minm; document.getElementById('dz').value=ac.dz});
  document.getElementById('acctbox').style.display=CFG.accounts.length>1?'':'none';
  seg('which',STRATS.map(s=>({id:s.k,label:s.name})),which,v=>which=v);
  seg('chartmode',MODES,chartMode,v=>chartMode=v);
}

function renderHeadline(P,c){
  const r=risk(), a=A();
  document.getElementById('headline').innerHTML=
   `<div><b>${c.n.toLocaleString()}</b><small>trades, ${c.perYr.toFixed(0)} per year</small></div>`+
   `<div><b>${pct(c.wr)}</b><small>win rate</small></div>`+
   `<div><b>${f2(c.pf)}</b><small>profit factor</small></div>`+
   `<div><b class="${sign(c.net)}">${f1(c.net)}R</b><small>net result</small></div>`+
   `<div><b class="${sign(c.ret)}">${spct(c.ret)}</b><small>return at ${rtxt(r)} risk</small></div>`+
   `<div><b>${pct(c.mddp)}</b><small>max drawdown from peak, live equity</small></div>`;
}

function renderEval(P){
  const r=risk(), a=A(), e=evals(P.from,r,a);
  const fin=e.pass.length+e.fail, med=e.pass.length?e.pass[Math.floor(e.pass.length/2)]:NaN;
  const q=p=>e.pass.length?e.pass[Math.min(e.pass.length-1,Math.floor(e.pass.length*p))]:NaN;
  document.getElementById('rulesnote').innerHTML=`<b>${CFG.firm} ${a.label}:</b> ${a.rules}. Bots: daily stop ${a.guard}%, reset ${String(RESET).padStart(2,'0')}:00 UTC, risk scaling ${r.m<1?'from '+(r.dz*100)+'% below the start, min '+r.m+'&times;':'off'}.`;
  document.getElementById('evalbox').innerHTML=
   `<div><b>${fin?pct(e.pass.length/fin):'–'}</b><small>passed, of ${fin} finished evaluations</small></div>`+
   `<div><b>${isNaN(med)?'–':med.toFixed(1)+' mo'}</b><small>median time to pass</small></div>`+
   `<div><b class="${e.fail?'neg':''}">${fin?pct(e.fail/fin):'–'}</b><small>failed: ${e.floor} max loss, ${e.daily} daily limit</small></div>`+
   `<div><b>${e.open}</b><small>still running at the end of the data</small></div>`;
  document.getElementById('evaltab').innerHTML='<thead><tr><th>Evaluations started</th><th>Passed</th><th>Failed</th><th>Not finished</th><th>Fastest quarter</th><th>Median</th><th>Slowest quarter</th></tr></thead><tbody>'+
   `<tr><td>${e.n} (one per week)</td><td>${e.pass.length}</td><td>${e.fail}</td><td>${e.open}</td><td>${isNaN(q(.25))?'–':q(.25).toFixed(1)+' mo'}</td><td>${isNaN(med)?'–':med.toFixed(1)+' mo'}</td><td>${isNaN(q(.75))?'–':q(.75).toFixed(1)+' mo'}</td></tr></tbody>`;
}

function renderStats(P,s){
  const a=A();
  const rows=[
    ['Trades',x=>x.n.toLocaleString()],['Trades per year',x=>x.perYr.toFixed(0)],['Win rate',x=>pct(x.wr)],
    ['Profit factor',x=>f2(x.pf)],['Net result',x=>`<span class="${sign(x.net)}">${f1(x.net)}R</span>`],
    ['Average per trade',x=>`${(x.avg>=0?'+':'')+x.avg.toFixed(3)}R`],['Average win / average loss',x=>`+${x.avgW.toFixed(2)}R / ${x.avgL.toFixed(2)}R`],
    ['Max drawdown (R, closed trades)',x=>x.mdd.toFixed(1)+'R'],['Net result ÷ max drawdown',x=>f2(x.rdd)],
    ['Return at your risk',x=>`<span class="${sign(x.ret)}">${spct(x.ret)}</span>`],['Annualised return',x=>spct(x.cagr)],
    ['Max drawdown at your risk (live equity)',x=>pct(x.mddp)],
    [`Worst day vs the reset (firm limit ${a.daily}%)`,x=>`<span class="${x.worstDay<0?'neg':''}">${(x.worstDay*100).toFixed(2)}%</span>`],
    [`Days the bots' ${a.guard}% daily stop fired`,x=>x.guardDays],
    [`Days over the firm's ${a.daily}% limit`,x=>`<span class="${x.breachDays?'neg':''}">${x.breachDays}</span>`],
    ['Profitable months',x=>`${pct(x.pm)} of ${x.nm}`],
    ['Best / worst month',x=>`${f1(x.best)}R / ${f1(x.worst)}R`],['Longest losing streak',x=>`${x.streak} trades`],
    ['Longs / shorts',x=>`${f1(x.L)}R / ${f1(x.S)}R`],
  ];
  let h='<thead><tr><th>Measure</th><th class="g">Gold (PDAYT)</th><th class="j">USDJPY (VOLC)</th><th class="c">Combined</th></tr></thead><tbody>';
  for(const [lab,fn] of rows) h+=`<tr><td>${lab}</td><td>${fn(s.g)}</td><td>${fn(s.j)}</td><td>${fn(s.c)}</td></tr>`;
  document.getElementById('stats').innerHTML=h+'</tbody>';
  const from=new Date(P.from*864e5).toISOString().slice(0,10);
  document.getElementById('periodnote').textContent=`${P.label}: trades opened from ${from} to ${DATA.end}. Percent rows: gold ${rtxt(risk()).split(' / ')[0]}, USDJPY ${rtxt(risk()).split(' / ')[1]} risk, ${CFG.firm} ${A().label} rules, risk scaling ${risk().m<1?'from '+(risk().dz*100)+'% below the start, min '+risk().m+'x':'off'}; a single bot's column runs that bot alone.`;
}

function renderAcross(){
  let h='<thead><tr><th>Period</th><th>Trades</th><th>Per year</th><th>Win rate</th><th>Profit factor</th><th>Net R</th><th>Avg R</th><th>Max DD (R)</th><th>Return</th><th>Annualised</th><th>Max DD (live)</th></tr></thead><tbody>';
  for(const P of PERIODS){const x=stats(pick(P.from,which),P.from);
    h+=`<tr><td>${P.label}</td><td>${x.n}</td><td>${x.perYr.toFixed(0)}</td><td>${pct(x.wr)}</td><td>${f2(x.pf)}</td><td class="${sign(x.net)}">${f1(x.net)}</td><td>${x.avg.toFixed(3)}</td><td>${x.mdd.toFixed(1)}</td><td class="${sign(x.ret)}">${spct(x.ret)}</td><td>${spct(x.cagr)}</td><td>${pct(x.mddp)}</td></tr>`}
  document.getElementById('across').innerHTML=h+'</tbody>';
}

function renderYears(){
  const y0=+DATA.start.slice(0,4), y1=+DATA.end.slice(0,4);
  const all=sim(T.filter(t=>t.e<END),risk(),A(),false).pts;
  const balAt=hh=>{let b=1; for(const p of all){ if(p[0]>=hh) break; b=p[1]} return b};
  let h='<thead><tr><th>Year</th><th class="g">Gold R</th><th class="g">Gold win rate</th><th class="j">USDJPY R</th><th class="j">USDJPY win rate</th><th class="c">Combined R</th><th class="c">Combined at your risk</th></tr></thead><tbody>';
  for(let y=y0;y<=y1;y++){
    const a=Date.UTC(y,0,1)/864e5,b=Date.UTC(y+1,0,1)/864e5;
    const sub=k=>T.filter(t=>t.e>=a&&t.e<b&&(k==='c'||(k==='g'?t.s===0:t.s===1)));
    const cell=l=>{const n=l.length,R=l.reduce((s,t)=>s+t.R,0),w=l.filter(t=>t.R>0).length;return {R,wr:n?w/n:0}};
    const g=cell(sub('g')),j=cell(sub('j')),cr=sub('c').reduce((s,t)=>s+t.R,0);
    const ret=balAt(Math.min(b,END)*24)/balAt(a*24)-1;
    h+=`<tr><td>${y}${y===y1?' (to '+DATA.endMonth+')':''}</td><td class="${sign(g.R)}">${f1(g.R)}</td><td>${pct(g.wr)}</td><td class="${sign(j.R)}">${f1(j.R)}</td><td>${pct(j.wr)}</td><td class="${sign(cr)}">${f1(cr)}</td><td class="${sign(ret)}">${spct(ret)}</td></tr>`}
  document.getElementById('years').innerHTML=h+'</tbody>';
}

let chartMode='acct';
const MODES=[{id:'acct',label:'Account % at your risk'},{id:'R',label:'Result in R'}];
function renderCharts(P,c,all){
  const acct=chartMode==='acct', unit=acct?'%':'R', W=1000,H=360,ml=acct?62:48,mr=12,mt=10,mb=26;
  const x0=P.from,x1=END, sx=x=>ml+(x-x0)/(x1-x0)*(W-ml-mr);
  const series={};
  if(acct){
    // account balance at your risk (each bot alone, and combined), from the same hour-by-hour run as the tables
    for(const k of ['c','g','j']){const pts=[[x0,0]], src=all[k].sim.pts, step=Math.max(1,Math.floor(src.length/1500));
      for(let i=0;i<src.length;i+=step) pts.push([src[i][0]/24,(src[i][1]-1)*100]);
      pts.push([x1,(all[k].sim.bal-1)*100]); series[k]=pts}
  } else {
    for(const k of ['c','g','j']){let s=0; const pts=[[x0,0]]; for(const t of pick(P.from,k).sort((a,b)=>a.x-b.x)){s+=t.R;pts.push([t.x,s])} pts.push([x1,s]); series[k]=pts}
  }
  const r=risk();
  document.getElementById('eqcap').textContent=acct
    ? `Account growth in % at your risk (gold ${+(r.g*100).toFixed(2)}%, USDJPY ${+(r.j*100).toFixed(2)}%), compounding, after every rule above; each bot's line runs that bot alone.`
    : 'Cumulative result in R (1R = the amount risked on one trade); does not depend on the risk setting.';
  let lo=0,hi=0; for(const k in series) for(const p of series[k]){lo=Math.min(lo,p[1]);hi=Math.max(hi,p[1])}
  const pad=(hi-lo)*0.06||1; lo-=pad; hi+=pad; const sy=y=>mt+(hi-y)/(hi-lo)*(H-mt-mb);
  const step=niceStep((hi-lo)/5); let g='';
  for(let v=Math.ceil(lo/step)*step; v<=hi; v+=step){g+=`<line x1="${ml}" x2="${W-mr}" y1="${sy(v)}" y2="${sy(v)}" style="stroke:var(--rule)" stroke-width="${v===0?1.4:0.7}"/><text x="${ml-6}" y="${sy(v)+4}" text-anchor="end">${v>0?'+':''}${+v.toFixed(0)}${unit}</text>`}
  g+=xTicks(x0,x1,sx,H-mb+17,mt,H-mb);
  const col={c:'--comb',g:'--gold',j:'--jpy'}, sw={c:2.4,g:1.5,j:1.5};
  for(const k of ['g','j','c']){const d=series[k].map((p,i)=>(i?'L':'M')+sx(p[0]).toFixed(1)+' '+sy(p[1]).toFixed(1)).join('');
    g+=`<path d="${d}" fill="none" style="stroke:var(${col[k]})" stroke-width="${sw[k]}" stroke-linejoin="round"/>`}
  document.getElementById('eq').innerHTML=g;
  // live-equity drawdown of the combined account at the chosen risk
  const a=A(), H2=150, mb2=20, pts=[[x0,0]];
  for(const p of c.sim.pts) pts.push([p[0]/24,-p[2]]);
  pts.push([x1,pts[pts.length-1][1]]);
  const worst=Math.min(...pts.map(p=>p[1]));
  const lo2=Math.min(worst,-0.02)*1.12, sy2=y=>6+(0-y)/(0-lo2)*(H2-6-mb2);
  let g2=`<line x1="${ml}" x2="${W-mr}" y1="${sy2(0)}" y2="${sy2(0)}" style="stroke:var(--rule)"/>`;
  const st2=niceStep(-lo2/3*100)/100;
  for(let v=-st2; v>=lo2; v-=st2) g2+=`<line x1="${ml}" x2="${W-mr}" y1="${sy2(v)}" y2="${sy2(v)}" style="stroke:var(--rule)" stroke-width=".6"/><text x="${ml-6}" y="${sy2(v)+4}" text-anchor="end">${(v*100).toFixed(0)}%</text>`;
  const step2=Math.max(1,Math.floor(pts.length/1500)), thin=pts.filter((p,i)=>i%step2===0||p[1]<-0.02);
  const area='M'+sx(x0)+' '+sy2(0)+thin.map(p=>'L'+sx(p[0]).toFixed(1)+' '+sy2(p[1]).toFixed(1)).join('')+'L'+sx(x1)+' '+sy2(0)+'Z';
  g2+=`<path d="${area}" style="fill:var(--neg);stroke:var(--neg)" fill-opacity=".22" stroke-width="1"/>`;
  g2+=xTicks(x0,x1,sx,H2-4,6,H2-mb2,true);
  document.getElementById('dd').innerHTML=g2;
}
function niceStep(raw){const p=Math.pow(10,Math.floor(Math.log10(raw||1)));const m=raw/p;return (m<1.5?1:m<3?2:m<7?5:10)*p}
function xTicks(x0,x1,sx,ty,top,bot,noText){
  let g=''; const span=x1-x0; const d0=new Date(x0*864e5), d1=new Date(x1*864e5);
  if(span>900){for(let y=d0.getUTCFullYear()+1;y<=d1.getUTCFullYear();y++){const x=Date.UTC(y,0,1)/864e5;
    g+=`<line x1="${sx(x)}" x2="${sx(x)}" y1="${top}" y2="${bot}" style="stroke:var(--rule)" stroke-width=".5"/>`+(noText?'':`<text x="${sx(x)}" y="${ty}" text-anchor="middle">${y}</text>`)}}
  else {const mo=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']; const every=span>400?3:span>200?2:1;
    let y=d0.getUTCFullYear(),m=d0.getUTCMonth()+1; while(true){if(m>11){m=0;y++} const x=Date.UTC(y,m,1)/864e5; if(x>=x1)break;
      if(m%every===0) g+=`<line x1="${sx(x)}" x2="${sx(x)}" y1="${top}" y2="${bot}" style="stroke:var(--rule)" stroke-width=".5"/>`+(noText?'':`<text x="${sx(x)}" y="${ty}" text-anchor="middle">${mo[m]}${m===0?' '+y:''}</text>`); m++}}
  return g;
}
function render(){
  const P=PERIODS.find(p=>p.id===cur); renderControls();
  const s={}; for(const k of ['g','j','c']) s[k]=stats(pick(P.from,k),P.from);
  renderHeadline(P,s.c); renderCharts(P,s.c,s); renderEval(P); renderStats(P,s); renderAcross(); renderYears();
}
// update while typing or clicking the arrows (short pause so typing stays smooth), and on leaving the box
let _rt=null; const soon=()=>{clearTimeout(_rt); _rt=setTimeout(render,250)};
for(const id of ['rg','rj','mm','dz']){const el=document.getElementById(id); el.addEventListener('input',soon); el.addEventListener('change',render)}
render();
</script>
</body>
</html>
"""


def build(rows, cand):
    end = pd.Timestamp(max(r[0] for r in rows) * 1440 * 60, unit="s").normalize()      # last exit day
    endday = int(end.value // 86_400_000_000_000) + 1
    endtxt = f"{end.day} {end.strftime('%B %Y')}"
    e = end + pd.Timedelta(days=1)
    per = [("all", f"Full ({(endday - 16804) / 365.25:.1f} yrs)", "2016-01-04")]
    for pid, lab, off in [("5y", "5 years", pd.DateOffset(years=5)), ("3y", "3 years", pd.DateOffset(years=3)),
                          ("2y", "2 years", pd.DateOffset(years=2)), ("1y", "1 year", pd.DateOffset(years=1)),
                          ("6m", "6 months", pd.DateOffset(months=6))]:
        per.append((pid, lab, (e - off).strftime("%Y-%m-%d")))
    data = dict(trades=rows, cand=cand, start="2016-01-04", end=end.strftime("%Y-%m-%d"), endDay=endday, endMonth=end.strftime("%b"), periods=per)
    for key, c in FIRMS.items():
        cfg = dict(firm=c["firm"], reset=c["reset"], accounts=c["accounts"])
        guards = sorted({a["guard"] for a in c["accounts"]})
        html = (PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__CFG__", json.dumps(cfg))
                .replace("__TITLE__", c["title"]).replace("__FIRM__", c["firm"]).replace("__ENDTXT__", endtxt)
                .replace("__ENDYEAR__", str(end.year)).replace("__RG__", str(c["rg"])).replace("__RJ__", str(c["rj"])).replace("__MM__", str(c["accounts"][0]["minm"])).replace("__DZ__", str(c["accounts"][0]["dz"]))
                .replace("__RESETTXT__", f"{c['reset']:02d}:00 UTC").replace("__MATCH__", c["match"])
                .replace("__GUARDTXT__", " / ".join(f"{g}%" for g in guards)))
        (ROOT / c["file"]).write_text(html, encoding="utf-8"); print("written", c["file"], len(html) // 1024, "KB")


if __name__ == "__main__":
    build(*trades())
