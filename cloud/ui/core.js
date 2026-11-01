// cloud/ui/core.js — the client core (spec §2, §3, §4.1, §5, §9, §12, §14, §15; COMMAND_CENTER_SPEC §2, §6.7, §9 B).
// Joined FIRST into the page's one IIFE (see ui/README.md) and the only module that declares top-level names. Nothing
// here runs at load except building constants; boot.js starts everything last.
/* ================================================ CORE API ================================================
 Module builders: everything below is in scope for every ui/*.js block. Times in the bundle are unix SECONDS and
 every fmt time function takes seconds. Helpers that return HTML escape their own input.

 DOM + misc      esc(s) · $(sel, root?) → Element · $$(sel, root?) → Element[] · HTML (documentElement)
                 BAR: this bot's bar in seconds (3600 | 14400 | 86400), set from barOf(S.b) in start(); 14400 on the master
                 TF = {'1h': 3600, '4h': 14400, '1d': 86400} · barOf(b?) → seconds: b.clock.bar_s → TF[b.cfg.tf] →
                 TF[rowOf(AGENT).tf] → 14400
                 nowMs() → ms, nowS() → s (tests: window.__exNow = ms number or function, or override Date.now)
                 reduced (live boolean, prefers-reduced-motion) · lsGet(key, fallback) / lsSet(key, value) (JSON, never
                 throw) · call(fn, ...args) (try/catch) · report(err, where) · isoS(iso|num) → s|null
                 tok('--good') → CSS token value · isDark() · jump(y) (instant scroll, no smooth) · into(el, smooth?)
                 num(v) → finite number or null ('' / boolean / NaN → null) · isObj(v) (plain object, not an array)
                 cap1(s) → first letter upper-cased · getJSON(url, ms?) → Promise<json>; rejects {kind: 'net' | 'auth'
                 | 'missing' | 'server' | 'parse'} (same-origin, no-store, AbortController timeout)
 Formats (§14)   fmt.R(v, nd=2) "+1.84 R" · fmt.Rn(v, nd=2) "+1.84" · fmt.pct(v, nd=2) "+1.30%" (signed)
                 fmt.pctu(v, nd=1) "3.2%" (|v|) · fmt.num(v, nd=2, signed?) · fmt.int(v) "1,500" · fmt.x(v, nd=2) "0.73×"
                 fmt.lev(v) "3×" or "—" · fmt.fund(v) "68%/yr" · fmt.px(v) 5 significant figures (sheets only)
                 fmt.cls(v, nd=2) → 'pos'|'neg'|''. Below half the last digit prints 0 with no sign and no colour.
                 fmt.time(t) "4:20 am" · fmt.when(t) today "4:20 am" / within 6 days "Thu 8:27 pm" / older "Sep 18"
                 fmt.day(t) "Thu Sep 24" · fmt.stamp(t) "Thu Sep 24, 12:20 pm" · fmt.dayLong(t) "Thursday, September 24"
                 fmt.md(t) "Sep 18" · fmt.wd(t) "Thu" · fmt.hr(t) "12a"/"8p" · fmt.utc(t) "08:00 UTC"
                 fmt.ago(t) "just now" / "27 min ago" / "3 h ago" / fmt.when(t) from 48 h · fmt.rel(t) "in 2 h 13 m"
                 fmt.age(sec) "27m" "2h 10m" "9 h" "3 d" · fmt.dur(sec) "27 min" "2 h 13 m" "2 d 6 h"
                 fmt.cd(sec) "2:13:07" / "13:07" · fmt.over(sec) "+04:12". Output is plain text, safe inside HTML.
                 Any element with data-ago="<unix s>" gets fresh fmt.ago() text on every 30 s tick.
 Missing (§1.8)  val(v, f?, short?) → f(v), or "— not in this data" (short: a muted "—") · na(short?) · MISSING
                 safe(fn, name, host?) → fn(), or a small .empty card "This panel couldn't be drawn…" (also into host)
 Vocabulary      STAGE[code] = {code, w, short, gate, role, tape, grp, cls:'st-<code>', note?} (§12) · stage(code)
                 GATES[i] = {g, label, codes, live?} (Gate Run rows 0–8) · GRP[grp] → On deck group title
                 CHECK_OF[reasonCode] → the cfg.checks name it belongs to (check lights)
                 GLOSS[key] = {t, d: text | d(cfg)} · gloss(key) → {t, d} · tip(key) → the "?" button (44px hit area)
                   keys: auto watch signal flip pullback oneflip thin cushion needs openR lockedR firstStop exposure
                   riskInUse drawdown slot gateRun heartbeat late vsHolding pf goLive paper R stop book checks line
                   due stale
                 word.kind(k, long?) · word.tier(t) · word.dir(1|0|null) · word.range(rg) · word.dist(d, held?)
                 word.reason(code, v, long?) · word.reasons([[code, v]…], long?) · word.codes("vol 0.73,fund 68")
                 word.exit(rsn, tradeRow?) · word.outcome(o) · word.stage(code) · word.run(run) → {k, w, s} · word.lag(min, ok)
                 word.event(eventsRow) → {html, ic, lv, t, type, c} (a 10th column on sold / trail: % of pot, shown first,
                   R in brackets) · word.alert(alert) → html
                 word.punct(b) the punctuality sentence · word.list([…]) · word.plural(n, one, many?)
                 word.bar(b?) 'hourly' | '4-hour' | 'daily' · word.every(b?) 'every hour' | 'every 4 hours' | 'every day'
                 word.kindName(kind, bar_s?) "Signal trader · hourly" ("—" for an unknown kind)
                 TIP[key] = [title, text] | fn(arg, el) → [title, text] | null: the plain words of every hover tip
                   (§3.11) · hint(key, arg?, focus?) → ' data-tk="key:arg"' (+ tabindex=0) · tipText(spec, el) → html
                   FAM[family id] = [plain name, what it does] · famName(id) (an unknown id prettified)
                 chip(coin, runT?) → a .tk button that opens the name sheet · ICON[name] / icon(name) → inline SVG
                   ICON names: x warn bad info ok left right up down raise block rec clock pause play flag eye doc
                   swap refresh
 Registries      VIEWS[tab] = {title, render(root, why) → html | nothing, after?(root) → cleanup fn?, leave?()}
                   bot-page tabs: overview results activity rules; the master renders VIEWS.fleet · why: 'route' |
                   'arrival' | 'redraw'. A missing VIEWS entry renders a quiet placeholder. A cleanup returned by after()
                   runs before the next render.
                 COMP[name] = fn: shared components. Always guard: COMP.x ? COMP.x(…) : … . Core itself reads
                   COMP.punctuality(b) → html, for the Health sheet, when a module provides it.
                 SHEETS[kind] = (arg, el) → html | {html, after?(sheetEl) → cleanup fn?, cls?}. Opened by ONE
                   delegated click on the nearest [data-cursor] [data-health] [data-cycle] [data-name] [data-pos]
                   [data-trade] [data-sheet="kind:arg"]. data-at on a [data-name] is the run t. Core ships a default
                   SHEETS.health (replaceable). A click whose default is already prevented is left alone, so a
                   module claims a click with e.preventDefault().
                 HOOKS: hook(name, fn) registers; runHooks(name, ...args). arrival(prev, next) (bot page) · tick1s() ·
                   tick30s() · route(tab, sub) · theme(theme) · hide() · show() · status(st) (after every
                   refreshShell(): the 30 s tick, a landed bundle, or a module that saw the phase flip) ·
                   agents(rows, envelope) after every /api/agents (re)load (boot, each bot arrival, each master poll)
 Pages           PAGE 'fleet' (the Command Center, "/") | 'bot' ("/?a=<id>") | 'lab' ("/lab": VIEWS.lab, no polling) · AGENT
                 the bot id, null on the master and the lab page
                 AGENTS rows of exec:agents (null until loaded) · S.E the exec:agents envelope · rowOf(id) → row | null
                 rowBundle(row, env?) → a status pseudo-bundle (§6.7, plus ran/pf/host/egen) or null for a v1 row · kindOf(b?) → 'flip' |
                 'target' | 'carry' (cfg.kind → row.kind → inference) · kindInfo(b?) → {kind, inferred}
                 loadAgents() → Promise<rows> (never rejects) · loadFactory(force?) → Promise<factory | null> (5 min cache)
                 botHref(id, hash?) "/?a=<id>#<hash>" · goFleet() back to the master (history.back() when we came from it)
                 botStep(±1) → the previous / next bot in exec:agents.order, replacing the history entry
                 switchAgent(id) → botHref(id), a replace on a bot page (a shim; ex.agent is never written) · ready() → the page has
                 its data · navHash('#tab/sub') (bot page: replaceState + route) · legacyHash() (boot.js, before boot)
                 ssGet(k) / ssSet(k, v | null) sessionStorage, never throw
 State           S = {b, ledger, ledgerGen, ledgerErr, cursor, tab, sub, prev, st, net, seenAt, seenEv, sheet, E, stamp}
                   S.stamp the last /api/stamp (bot page; {err} when a push failed: status() then says "Page behind")
                   S.b exec:latest · S.prev the bundle before the last arrival · S.st = status(S.b), refreshed on the
                   30 s tick · S.net 'ok'|'checking'|'offline'|'signedout' · S.seenEv = ex.seenEv as it was when
                   Activity opened (the "new since your last visit" marker) · S.sheet {kind, arg} of the open sheet
                 setCursor(t|null, opts?) null = latest; opts {scroll, sheet:false, explicit} · onCursor(fn(t, prev, opts))
                 runsOf(b?) · lastRun(b?) · runAt(t, b?) · cursorRun() · nameOf(coin) · modeOf(b) · stateOf(b) · clockOf(b)
                 loadLedger(force?) → Promise<ledger|null>, never rejects; S.ledgerErr says why when null
                 loadLWC() → Promise<LightweightCharts> (lightweight-charts 4.2.3 from jsdelivr, injected once)
 Status (§3)     clock(b?, nowS?) → {phase:'countdown'|'due'|'late'|'stale'|'none', C, lag, lim, next, lateAt, staleAt,
                   exitsAt, sched, lastT, lastSlot, age, over, toNext, rng, lagN, nOpen, exits, now}
                 status(b?, nowS?) → {lvl:'ok'|'info'|'warn'|'bad', dot, word, age, wide, sentence(html), k, items[], K, pb, shown}
                   pb = {ran, pf} when the page is behind its bot (behindOf: row ran_t / push_fail, or a stamp's err), then
                   k 'behind' "Page behind" leads (bad while the update fails) and K runs from ran; shown = the page's check
                   items[i] = {lvl, k, word, sentence(html), act:{label, href | cycle}, age, wide, head}
                 DOT[lvl] → dot class (ok due gap bad) · LVCLS[lvl] → '' | 'warn' | 'bad'
 Shell           openSheet(html | {html, after, cls}, key?) · showSheet(kind, arg, el?) · closeSheet() · refreshSheet()
                 showTip(el, html?, by?) · hideTip() · retip() · toast(html, {ms}) · setPlay(key, on) (html.play pauses .bg)
                 every1s(el, fn): fn runs every second while el is on screen and the page is visible
                 countUp(el, to, {from, decimals, prefix, suffix, ms, fmt}) · stagger(root) · setSeg(seg, v)
                 initSegs(root?) · movePill() · masks(root?) (edge fades .mask-l/.mask-r + region semantics) ·
                 mdTables(html) → md() html with each table in a details.disc.mdt (closed under 900px) ·
                 banner(lvl, html, act?) · go(tab, sub?) · route() · poll(user?) · land(bundle)
                 redraw() → re-render the open tab in place (why 'redraw'), keeping the scroll and an open sheet
                 refreshShell() → recompute S.st and repaint the capsule, rail mirror, mode pill, alert rail and the
                   Activity dot, then run the 'status' hooks. Call it when a module sees the clock phase flip.
 Anchors         route() scrolls to id="<tab>-<sub>" when present (#activity/signals → id="activity-signals";
                 #refused redirects there). setCursor(t, {scroll:true}) on Overview scrolls to id="overview-gaterun".
                 On a bot page every same-page hash link is history.replaceState + route(): tabs add no history entry.
 Clicks          [data-cursor="<t>" | ""] sets the cursor ([data-scroll] also scrolls to the Gate Run) ·
                 [data-refresh] checks for new data · [data-retry] reboots · [data-top] scrolls to the top ·
                 .tip / [data-tip="text"] / [data-g="glossKey"] / [data-tk="key[:arg]"] open a tip (or set el._tip =
                 html | fn(el)) on click, keyboard focus, a 250 ms mouse hover or a 450 ms long press; a tipped label
                 inside a link or control leaves its click to the control. [data-tip-cursor="<t>"] adds a "Replay this
                 check ›" button to that tip.
 ========================================================================================================== */

// ============================================================================================ basics ==
let BAR = 14400;
const TF = { '1h': 3600, '4h': 14400, '1d': 86400 };
const HTML = document.documentElement;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function nowMs() {
  const o = window.__exNow;
  if (typeof o === 'function') { const v = Number(o()); if (isFinite(v)) return v; }
  if (typeof o === 'number' && isFinite(o)) return o;
  return Date.now();
}
function nowS() { return Math.floor(nowMs() / 1000); }
const MQ_RM = matchMedia('(prefers-reduced-motion: reduce)');
let reduced = MQ_RM.matches;
// A change of the OS setting redraws the open tab and sheet, so Replay/Step, Play and the pings follow it at once.
function onMotion(e) { reduced = e.matches; if (ready() && document.getElementById('app')) { redraw(); refreshSheet(); } }
if (MQ_RM.addEventListener) MQ_RM.addEventListener('change', onMotion);
else if (MQ_RM.addListener) MQ_RM.addListener(onMotion);
function report(e, where) { try { console.error('[executor] ' + (where || 'error'), e); } catch (_) {} }
function call(fn, ...a) { if (typeof fn !== 'function') return; try { return fn(...a); } catch (e) { report(e, fn.name || 'hook'); } }
// "seen" markers are per agent: ex.seen for core, ex.seen@<agent> for the others. ex.agent itself is global.
var AGENT_NS = '';
function lsKey(k) { return (k === 'ex.agent' || !AGENT_NS) ? k : k + '@' + AGENT_NS; }
function lsGet(k, d) { try { const v = localStorage.getItem(lsKey(k)); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
function lsSet(k, v) { try { localStorage.setItem(lsKey(k), JSON.stringify(v)); } catch (e) {} }
function isoS(v) { if (v == null || v === '') return null; if (typeof v === 'number') return isFinite(v) ? Math.floor(v) : null; const ms = Date.parse(v); return isFinite(ms) ? Math.floor(ms / 1000) : null; }
function tok(n) { return getComputedStyle(HTML).getPropertyValue(n).trim(); }
function isDark() { const t = HTML.dataset.theme; return t === 'dark' || (t !== 'light' && !matchMedia('(prefers-color-scheme: light)').matches); }
function jump(y) { try { scrollTo({ top: y, behavior: 'instant' }); } catch (e) { scrollTo(0, y); } }
function into(el, smooth) { if (!el) return; el.style.scrollMarginTop = '72px'; try { el.scrollIntoView({ block: 'start', behavior: smooth && !reduced ? 'smooth' : 'instant' }); } catch (e) { el.scrollIntoView(); } }

// ===================================================================================== formats (§14) ==
const MINUS = '−', NB = ' ';
const NF = {}, DF = {};
function nf(nd, sig) { const k = (sig ? 's' : 'f') + nd; return NF[k] || (NF[k] = new Intl.NumberFormat(undefined, sig ? { maximumSignificantDigits: nd } : { minimumFractionDigits: nd, maximumFractionDigits: nd })); }
function df(k, o) { return DF[k] || (DF[k] = new Intl.DateTimeFormat(undefined, o)); }
function numv(v) { if (v == null || v === '' || typeof v === 'boolean') return null; const x = Number(v); return isFinite(x) ? x : null; }
const num = numv;                                                                        // shared: a finite number or null
const isObj = v => !!v && typeof v === 'object' && !Array.isArray(v);
const cap1 = s => { s = s == null ? '' : String(s); return s.charAt(0).toUpperCase() + s.slice(1); };
function rz(x, nd) { return Math.abs(x) < 0.5 * Math.pow(10, -nd) ? 0 : x; }
function signed(x, nd) { const r = rz(x, nd); return (r > 0 ? '+' : r < 0 ? MINUS : '') + nf(nd).format(Math.abs(r)); }
function ymd(ms) { const d = new Date(ms); return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / 864e5; }     // local calendar day
function clockText(ms) {
  return df('t', { hour: 'numeric', minute: '2-digit' }).formatToParts(new Date(ms)).map(p =>
    p.type === 'dayPeriod' ? p.value.toLowerCase().replace(/\./g, '') : p.type === 'literal' ? p.value.replace(/[\s ]+/g, NB) : p.value).join('');
}
const fmt = {
  num: (v, nd = 2, sg) => { const x = numv(v); if (x == null) return '—'; if (sg) return signed(x, nd); const r = rz(x, nd); return (r < 0 ? MINUS : '') + nf(nd).format(Math.abs(r)); },
  R: (v, nd = 2) => { const x = numv(v); return x == null ? '—' : signed(x, nd) + NB + 'R'; },
  Rn: (v, nd = 2) => { const x = numv(v); return x == null ? '—' : signed(x, nd); },
  pct: (v, nd = 2) => { const x = numv(v); return x == null ? '—' : signed(x, nd) + '%'; },
  pctu: (v, nd = 1) => { const x = numv(v); return x == null ? '—' : nf(nd).format(Math.abs(rz(x, nd))) + '%'; },
  int: v => { const x = numv(v); return x == null ? '—' : (Math.round(x) < 0 ? MINUS : '') + nf(0).format(Math.abs(Math.round(x))); },
  x: (v, nd = 2) => { const x = numv(v); return x == null ? '—' : nf(nd).format(Math.abs(rz(x, nd))) + '×'; },
  lev: v => { const x = numv(v); return x == null ? '—' : nf(x % 1 ? 1 : 0).format(x) + '×'; },
  fund: v => { const x = numv(v); return x == null ? '—' : (Math.round(x) < 0 ? MINUS : '') + nf(0).format(Math.abs(Math.round(x))) + '%/yr'; },
  px: v => { const x = numv(v); return x == null ? '—' : (x < 0 ? MINUS : '') + nf(5, true).format(Math.abs(x)); },
  cls: (v, nd = 2) => { const x = numv(v); if (x == null) return ''; const r = rz(x, nd); return r > 0 ? 'pos' : r < 0 ? 'neg' : ''; },
  time: t => t == null ? '—' : clockText(t * 1000),
  wd: t => t == null ? '—' : df('wd', { weekday: 'short' }).format(new Date(t * 1000)).replace(/\.$/, ''),
  md: t => t == null ? '—' : df('md', { month: 'short', day: 'numeric' }).format(new Date(t * 1000)),
  day: t => t == null ? '—' : fmt.wd(t) + ' ' + fmt.md(t),
  stamp: t => t == null ? '—' : fmt.day(t) + ', ' + fmt.time(t),
  dayLong: t => t == null ? '—' : df('dl', { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date(t * 1000)),
  when: t => {
    if (t == null) return '—';
    const dd = ymd(nowMs()) - ymd(t * 1000);
    return dd === 0 ? fmt.time(t) : Math.abs(dd) <= 6 ? fmt.wd(t) + ' ' + fmt.time(t) : fmt.md(t);
  },
  hr: t => {
    if (t == null) return '—';
    const ps = df('h', { hour: 'numeric' }).formatToParts(new Date(t * 1000));
    const h = (ps.find(p => p.type === 'hour') || {}).value || '', dp = (ps.find(p => p.type === 'dayPeriod') || {}).value;
    return dp ? String(Number(h)) + dp.replace(/\./g, '').charAt(0).toLowerCase() : h.padStart(2, '0');
  },
  utc: t => { if (t == null) return '—'; const d = new Date(t * 1000); return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0') + ' UTC'; },
  ago: t => {
    if (t == null) return '—';
    const s = nowS() - t;
    if (s < -60) return fmt.rel(t);
    if (s < 90) return 'just now';
    if (s < 3600) return Math.round(s / 60) + ' min ago';
    if (s < 48 * 3600) return Math.floor(s / 3600) + ' h ago';
    return fmt.when(t);
  },
  rel: t => { if (t == null) return '—'; const s = t - nowS(); return s >= 60 ? 'in ' + fmt.dur(s) : s > -90 ? 'now' : fmt.ago(t); },
  age: sec => {
    const s = Math.max(0, Math.floor(numv(sec) || 0));
    if (s < 60) return '<1m';
    if (s < 3600) return Math.floor(s / 60) + 'm';
    if (s < 4 * 3600) { const m = Math.floor(s / 60) % 60; return Math.floor(s / 3600) + 'h' + (m ? ' ' + m + 'm' : ''); }
    if (s < 48 * 3600) return Math.floor(s / 3600) + NB + 'h';
    return Math.floor(s / 86400) + NB + 'd';
  },
  dur: sec => {
    const s = Math.max(0, Math.round(numv(sec) || 0));
    if (s < 60) return s + NB + 's';
    if (s < 3600) return Math.round(s / 60) + NB + 'min';
    if (s < 48 * 3600) { const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60; return h + NB + 'h' + (m ? ' ' + m + NB + 'm' : ''); }
    const d = Math.floor(s / 86400), h = Math.floor(s / 3600) % 24; return d + NB + 'd' + (h ? ' ' + h + NB + 'h' : '');
  },
  cd: sec => {
    const s = Math.max(0, Math.floor(numv(sec) || 0)), h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : String(m)) + ':' + String(x).padStart(2, '0');
  },
  over: sec => { const s = Math.max(0, Math.floor(numv(sec) || 0)); return '+' + String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); },
};

// ==================================================================================== missing data ==
const MISSING = 'not in this data';
function na(short) { return short ? '<span class="na" data-tk="na">—</span>' : '— <span class="na">' + MISSING + '</span>'; }
function val(v, f, short) { return v == null || (typeof v === 'number' && !isFinite(v)) ? na(short) : f ? f(v) : esc(v); }
function broken(name) { return '<div class="card"><div class="empty">' + (name ? '<b>' + esc(name) + '</b> · ' : '') + 'This panel couldn’t be drawn from this data.</div></div>'; }
function safe(fn, name, host) {
  try { const out = fn(); return out == null ? '' : out; }
  catch (e) { report(e, name); const h = broken(name); if (host) host.innerHTML = h; return h; }
}

// ================================================================================== vocabulary (§12) ==
const STAGE = {
  h: { w: 'Held', short: 'held', gate: 0, role: 'good outline', tape: 'good outline', grp: 'held' },
  x: { w: 'Not listed / no market data', short: 'no market data', gate: 1, role: 'bad-soft', tape: 'hatched', grp: 'nodata' },
  '!': { w: 'Error reading', short: 'error reading', gate: 1, role: 'bad', tape: 'bad', grp: 'nodata' },
  w: { w: 'Weekly not bullish', short: 'weekly', gate: 2, role: 'muted', tape: 'dark glass-3', grp: 'notset' },
  d: { w: 'Daily not bullish', short: 'daily', gate: 3, role: 'muted', tape: 'dark glass-3', grp: 'notset' },
  n: { w: '4-hour not ready', short: 'not ready', gate: 4, role: 'muted', tape: 'muted', grp: 'nodata' },
  a: { w: 'One flip away', short: 'one flip away', gate: 4, role: 'accent tint', tape: 'accent tint', grp: 'next' },
  t: { w: 'One flip away, too thin', short: 'too thin', gate: 4, role: 'warn outline', tape: 'warn tint', grp: 'thin' },
  u: { w: 'Already running', short: 'running', gate: 4, role: 'good-soft', tape: 'good-soft', grp: 'run' },
  g: { w: 'Signal, close not above the line', short: 'close not above the line', gate: 4, role: 'muted', tape: 'muted', grp: null },
  m: { w: 'Signal, outcome not logged', short: 'outcome not logged', gate: 4, role: 'dashed muted', tape: 'dashed', grp: null, note: 'unknown until the engine update' },
  r: { w: 'Blocked by a check', short: 'blocked', gate: 5, role: 'warn', tape: 'warn', grp: null },
  p: { w: 'Watch-only, recorded', short: 'watch-only', gate: 6, role: 'ink-2 ring', tape: 'ink-2 ring', grp: null },
  P: { w: 'Proposed (old model)', short: 'proposed (old model)', gate: 6, role: 'ink-2 ring', tape: 'ink-2', grp: null },
  e: { w: 'Order not filled', short: 'not filled', gate: 7, role: 'bad', tape: 'bad', grp: null },
  E: { w: 'Bought', short: 'bought', gate: 8, role: 'solid accent', tape: 'solid accent', grp: 'held' },
  '-': { w: 'Not recorded', short: 'not recorded', gate: null, role: 'hatched', tape: 'hatched', grp: null },
};
for (const k in STAGE) { STAGE[k].code = k; STAGE[k].cls = 'st-' + k; }
function stage(c) { return STAGE[c] || STAGE['-']; }
const GATES = [
  { g: 0, label: 'Exits checked first', codes: 'h' },
  { g: 1, label: 'In the books', codes: 'x!' },
  { g: 2, label: 'Weekly bullish', codes: 'w' },
  { g: 3, label: 'Daily bullish', codes: 'd' },
  { g: 4, label: '4-hour signal', codes: 'atungm' },
  { g: 5, label: 'Safety checks', codes: 'r' },
  { g: 6, label: 'Grade may trade', codes: 'pP' },
  { g: 7, label: 'Order filled', codes: 'e', live: true },
  { g: 8, label: 'Bought', codes: 'E' },
];
const GRP = { next: 'Could signal next', thin: 'Armed, too thin', run: 'Already running', notset: 'Not set up', held: 'Held', nodata: 'No data', error: 'No data' };
const CHECK_OF = {
  halt: 'not halted', thr: 'throttle allows entries', fresh: 'data fresh and run on time', recon: 'no reconciliation mismatch',
  sizing: 'sizing accepted', dup: 'no open position in this coin', maxpos: 'below max positions', equity: 'equity positive',
  cap: 'open-risk cap', gross: 'gross exposure cap', bookcap: 'book open-risk cap', sanity: 'price sanity band',
  vol: 'universe filters', oi: 'universe filters', fund: 'universe filters', days: 'universe filters', lev: 'universe filters',
  list: 'universe filters', uni: 'universe filters',
};

// ================================================================================ icons and chips ==
const I = d => '<svg viewBox="0 0 24 24" aria-hidden="true">' + (d.charAt(0) === '<' ? d : '<path d="' + d + '"/>') + '</svg>';
const ICON = {
  x: I('M6 6l12 12M18 6L6 18'),
  warn: I('<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>'),
  bad: I('<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5h.01"/>'),
  info: I('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'),
  ok: I('<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>'),
  left: I('M15 6l-6 6 6 6'), right: I('M9 6l6 6-6 6'),
  up: I('M7 17L17 7M9 7h8v8'), down: I('M7 7l10 10M17 9v8H9'),
  raise: I('<path d="M5 20h14"/><path d="M12 16V5M8 9l4-4 4 4"/>'),
  block: I('<circle cx="12" cy="12" r="9"/><path d="M5.7 5.7l12.6 12.6"/>'),
  rec: I('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>'),
  clock: I('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
  pause: I('M9 5v14M15 5v14'), play: I('M7 5l12 7-12 7z'),
  flag: I('M5 21V4M5 4h11l-2 4 2 4H5'),
  eye: I('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  doc: I('<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>'),
  swap: I('M4 8h14l-3-3M20 16H6l3 3'),
  refresh: I('M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6'),
};
function icon(n) { return ICON[n] || ICON.info; }
function chip(c, at) { return '<button type="button" class="tk" data-name="' + esc(c) + '"' + (at != null ? ' data-at="' + esc(at) + '"' : '') + '>' + esc(c) + '</button>'; }

// ====================================================================================== glossary ==
// One or two plain sentences each. Thresholds come from the bundle's cfg at render time, never from this file.
function cfgOf(b) { return ((b || S.b || {}).cfg) || {}; }
function q(v, unit, alt) { return v == null ? alt : v + (unit || ''); }
const bw = () => word.bar();                                        // this bot's bar in words, read at render time
const aBw = (a = 'a') => a + (bw() === 'hourly' ? 'n ' : ' ') + bw();   // with its article: "an hourly", "a daily"
const GLOSS = {
  auto: { t: 'Auto grade', d: () => aBw('A') + ' flip while the coin’s weekly and daily and Bitcoin’s weekly are all bullish. It is the only signal the bot buys on its own, and only after every safety check passes.' },
  watch: { t: 'Watch-only grade', d: 'Every other signal: a pullback into the band, or a flip while Bitcoin’s weekly is not bullish. It is recorded, never traded.' },
  signal: { t: 'Signal', d: () => 'A coin’s ' + bw() + ' Momentum Cloud flips bullish, or its price pulls back into the band, while its weekly and daily are bullish. A signal is not a buy: it still needs the auto grade and every safety check.' },
  flip: { t: () => cap1(bw()) + ' flip', d: () => aBw('A') + ' close above the Momentum Cloud line, which turns the ' + bw() + ' trend bullish.' },
  pullback: { t: 'Pullback into the band', d: () => 'The price dips back into its band while the ' + bw() + ' trend is already bullish. Always watch-only.' },
  oneflip: { t: 'One flip away', d: () => 'Weekly and daily are bullish and the ' + bw() + ' is bearish, so one ' + bw() + ' close above the line would be a flip.' },
  thin: { t: 'Too thin', d: c => { const u = c.uni || {}; return 'One flip away, but the coin fails a market check today (volume under ' + q(u.vol_m, 'M a day', 'the minimum') + ', funding above ' + q(u.fund_pct, '%/yr', 'the limit') + ' or less than ' + q(u.days, ' days', 'the minimum') + ' of history), so a signal would be blocked. Market figures, not your money.'; } },
  cushion: { t: 'Cushion', d: () => 'How far the last ' + bw() + ' close sits above the Momentum Cloud line. The ' + bw() + ' stays bullish until a close falls below the line.' },
  needs: { t: 'Needs (an upper bound)', d: () => 'How far the next ' + bw() + ' close must rise to cross the line. While ' + aBw('a') + ' cloud is bearish its line can only step down, so this is the most it must rise. Not a prediction.' },
  openR: { t: 'Open R', d: 'What the position would bring if it were closed at the last mark, after costs, in units of its first risk.' },
  lockedR: { t: 'Locked R', d: 'What the position would still bring if its current stop were hit now, after costs. Positive once the stop is above entry.' },
  firstStop: { t: 'First stop', d: 'The stop set at entry. Hitting it loses 1 R, the planned risk of the trade.' },
  exposure: { t: 'Exposure', d: c => 'The position’s size as a share of the pot. With leverage it can pass 100% while only ' + q(c.risk_pct, '%', 'the per-trade risk') + ' of the pot was at risk at entry.' },
  riskInUse: { t: 'Risk in use', d: c => 'What every open position would lose at its current stop, as % of the pot. At most ' + q(c.open_cap_pct, '%', 'the open-risk cap') + ' at once and ' + q(c.risk_pct, '%', 'the per-trade risk') + ' per trade.' },
  drawdown: { t: 'Drawdown gauge', d: c => { const t = c.thr || []; return 'How far the pot is below its peak. At ' + q(t[0], '%', 'the first limit') + ' risk per trade halves; at ' + q(t[1], '%', 'the second') + ' the bot stops buying until reviewed.'; } },
  slot: { t: 'Slot', d: c => 'One of the ' + q(c.max_pos, '', 'few') + ' positions the bot may hold at once.' },
  gateRun: { t: 'Gate Run', d: 'A replay of one recorded check: every name moves down the engine’s gates in order and stops where the record says it stopped.' },
  heartbeat: { t: 'Heartbeat', d: () => 'One cell per ' + bw() + ' close' + (BAR === 14400 ? ' for the last 7 days' : '') + '. Each cell is a recorded check: on time, late, failed or missed.' },
  late: { t: 'Late check', d: c => 'A check that started more than ' + q(c.late_min, ' minutes', 'the late limit') + ' after the ' + bw() + ' close. Its data is too old to buy on, so buys are skipped for that bar; exits still run.' },
  vsHolding: { t: 'vs holding', d: 'A trade’s R minus what simply holding the book’s benchmark over the same hours would have made, in the same R. Positive means the trade beat holding. Signal traders only: a rebalancer’s benchmark is the coin it holds, so it would be compared with itself.' },
  pf: { t: 'Profit factor', d: 'Total R won divided by total R lost. Above 1 the wins outweigh the losses; with no losing trade yet it has no value.' },
  goLive: { t: 'Go-live gates', d: c => { const g = c.gates || {}; return 'What the paper record must show before real money: ' + q(g.n, ' closed trades', 'enough closed trades') + ', ' + (g.avg_R != null ? 'an average above +' + g.avg_R + ' R' : 'a positive average R') + ', a worst drawdown under ' + q(g.dd_pct, '%', 'the limit') + ', and costs of at most ' + q(g.cost_R, ' R', 'the cost limit') + ' per trade.'; } },
  paper: { t: 'Paper', d: 'The bot runs every rule on real market data, but no order reaches the exchange. Fills and costs are simulated.' },
  R: { t: 'R', d: c => 'One unit of planned risk: what a trade loses if its first stop is hit, ' + q(c.risk_pct, '% of the pot', 'a fixed share of the pot') + '. Results are counted in R so they compare across coins.' },
  stop: { t: 'Stop', d: () => 'The price that closes the position. It follows the ' + bw() + ' line up, never down.' },
  book: { t: 'Book', d: 'A group of coins judged against one benchmark, with its own share of the pot and its own risk cap.' },
  checks: { t: 'Safety checks', d: c => 'The checks every signal must pass before a buy' + (Array.isArray(c.checks) && c.checks.length ? ', in order: ' + c.checks.join(', ') + '.' : '.') },
  line: { t: 'Momentum Cloud line', d: () => 'The ' + bw() + ' trend line. A close above it turns the ' + bw() + ' bullish; a close below it turns it bearish.' },
  due: { t: 'Due', d: () => 'The check for the last ' + bw() + ' close should land about now. It is not late until the limit passes.' },
  stale: { t: 'Stale', d: c => 'No check within ' + fmt.dur(staleGap(BAR, num(c.late_min) || 45)) + ' of ' + aBw('a') + ' close. The status line says whether the server is still running.' },
};
function gloss(k) {
  const g = GLOSS[k]; if (!g) return null;
  let d = ''; try { d = typeof g.d === 'function' ? g.d(cfgOf()) : g.d; } catch (e) { report(e, 'gloss ' + k); }
  return { t: typeof g.t === 'function' ? g.t() : g.t, d };
}
function tip(k) { const g = gloss(k); return '<button class="tip" type="button" data-g="' + esc(k) + '" aria-label="What is ' + esc(g ? g.t : k) + '?">?</button>'; }

// ========================================================================================== words ==
const KIND = { flip: ['flip', '4-hour flip'], pullback: ['pullback', 'pullback into the band'] };
const EXIT = { stop: 'stop hit', h1: 'hourly turn', h4: '4-hour turn', d: 'daily turn', w: 'weekly turn', flatten: 'manual flatten', nostop: 'no stop possible', exch: 'exchange stop', fund: 'funding fell below its exit rate', other: 'exit',
  brake: 'book brake', cat: 'catastrophic stop', side: 'switched sides', delist: 'delisted', venue: 'moved between perp and spot', basket: 'left the basket' };
const OUTCOME = { blocked: 'Blocked by a check', recorded: 'Recorded, not traded', expired: 'Expired (old approval model)', notfilled: 'Order not filled', bought: 'Bought', perp: 'Spot not usable: traded on the perp' };
const EV_IC = { bought: 'up', sold: 'down', trail: 'raise', blocked: 'block', recorded: 'rec', proposed: 'rec', expired: 'clock', notfilled: 'x',
  late: 'clock', failed: 'bad', halt: 'pause', resume: 'play', thr_halt: 'pause', thr_half: 'warn', recon: 'bad', no_stop: 'bad', close_failed: 'bad',
  exit_failed: 'bad', fallback: 'warn', regime: 'flag', gap: 'warn', entry_failed: 'warn', not_on_exchange: 'warn', sweep: 'swap', review: 'doc', board: 'eye',
  resized: 'swap', carry_in: 'up', carry_out: 'down', carry_closed: 'ok', carry_fix: 'swap' };
// A bar in words: [adjective, cadence, the tile's short form]
const BARW = { 3600: ['hourly', 'every hour', 'hourly'], 14400: ['4-hour', 'every 4 hours', 'every 4 h'], 86400: ['daily', 'every day', 'daily'] };
function barw(s, i) { const w = BARW[s]; if (w) return w[i]; const h = Math.round(s / 3600); return [h + '-hour', 'every ' + h + ' hours', 'every ' + h + ' h'][i]; }
const KINDW = { flip: 'Signal trader', target: 'Rebalancer', carry: 'Funding collector' };
const DIRW = { B: 'bullish', b: 'bearish', n: 'no reading', 1: 'bullish', 0: 'bearish' };
const word = {
  bar: b => barw(barOf(b === undefined ? S.b : b), 0),
  every: b => barw(barOf(b === undefined ? S.b : b), 1),
  kindName: (k, bar) => KINDW[k] ? KINDW[k] + (num(bar) ? ' · ' + barw(num(bar), 2) : '') : '—',
  kind: (k, long) => KIND[k] ? KIND[k][long ? 1 : 0] : (k ? String(k) : 'signal'),
  tier: t => t === 'A' ? 'Auto grade' : t === 'B' ? 'Watch-only grade' : 'grade not recorded',
  dir: v => v === 1 || v === true ? 'bullish' : v === 0 || v === false ? 'bearish' : 'no reading',
  range: rg => ({ O: 'above its band', I: 'in its band', S: 'below its band' })[rg] || 'no reading',
  dist: (d, held) => {
    const x = numv(d); if (x == null) return '—';
    if (held) return 'stop ' + (x >= 0 && x < 0.05 ? 'less than 0.1%' : fmt.pctu(x, 1)) + ' below';     // never a false "0.0%"
    return rz(x, 1) > 0 ? 'needs +' + fmt.pctu(x, 1) : rz(x, 1) < 0 ? 'cushion ' + fmt.pctu(x, 1) : 'at the line';
  },
  reason: (code, v, long) => {
    const u = cfgOf().uni || {}, x = numv(v), has = x != null;
    switch (code) {
      case 'vol': return has ? 'volume ' + fmt.x(x) + (long ? ' the minimum' : '') : 'no volume reading';
      case 'oi': return has ? 'open interest ' + fmt.x(x) + (long ? ' the minimum' : '') : 'no open-interest reading';
      case 'fund': return has ? 'funding ' + fmt.fund(x) + (long && u.fund_pct != null ? ' (limit ' + u.fund_pct + ')' : '') : 'funding unreadable';
      case 'days': return has ? (long ? 'only ' : '') + fmt.int(x) + ' days of history' + (long && u.days != null ? ' (needs ' + u.days + ')' : '') : 'history unknown';
      case 'lev': return has ? 'max leverage ' + fmt.lev(x) + (long && u.lev != null ? ' (needs ' + u.lev + '×)' : '') : 'max leverage unreadable';
      case 'list': return 'not listed';
      case 'uni': return 'universe filters';
      case 'halt': return 'halted';
      case 'thr': return 'throttle' + (has ? ' (drawdown ' + fmt.pctu(x, 1) + ')' : '');
      case 'fresh': return 'data too late' + (has ? ' (' + fmt.int(x) + ' min after the close)' : '');
      case 'recon': return 'reconciliation mismatch';
      case 'sizing': return 'sizing not accepted';
      case 'dup': return 'already held';
      case 'maxpos': return 'max positions' + (has ? ' (' + fmt.int(x) + ' open)' : '');
      case 'equity': return 'equity check';
      case 'cap': return 'open-risk cap' + (has ? ' (' + fmt.pctu(x, 2) + ' after entry)' : '');
      case 'bookcap': return 'book risk cap' + (has ? ' (' + fmt.pctu(x, 2) + ' after entry)' : '');
      case 'gross': return 'gross exposure cap' + (has ? ' (' + fmt.x(x) + ' after entry)' : '');
      case 'sanity': return 'price sanity band' + (has ? ' (' + fmt.pctu(x, 1) + ' off)' : '');
      case 'tier': return 'watch-only grade';
      case 'expired': return 'proposal expired';
      case 'fill': return 'order not filled';
      case 'recheck': return 're-check failed';
      case 'drift': return 'price ran' + (has ? ' ' + fmt.pctu(x, 1) : '') + ' above the signal';
      default: return 'a safety check';
    }
  },
  reasons: (list, long) => (Array.isArray(list) ? list : []).map(p => Array.isArray(p) ? word.reason(p[0], p[1], long) : word.reason(p, null, long)).join(' · '),
  codes: det => String(det || '').split(',').map(s => s.trim()).filter(Boolean).map(s => { const m = s.match(/^(\S+)(?:\s+(\S+))?$/); return m ? [m[1], m[2] != null ? numv(m[2]) : null] : [s, null]; }),
  // a stop exit above the entry price locked in a gain (owner-13); with no prices, the plain reason
  exit: (r, row) => r === 'stop' && row && num(row.exit) != null && num(row.entry) != null && num(row.exit) > num(row.entry) ? 'trailing stop, locked in gain' : EXIT[r] || 'exit',
  outcome: o => OUTCOME[o] || (o ? String(o) : '—'),
  stage: c => stage(c).w,
  lag: (min, ok) => (ok === false || ok === 0 ? 'ran late' : 'on time') + (min != null ? ' (' + min + ' min after the close)' : ''),
  run: r => {
    if (!r) return { k: 'none', w: 'no check', s: 'no check' };
    if (r.x) return { k: 'failed', w: 'failed', s: 'stopped early' };
    if (!r.ok) return { k: 'late', w: 'ran late', s: 'ran late (' + r.lm + ' min after the close), buys skipped' };
    const s = 'on time (' + r.lm + ' min after the close)';
    return r.h ? { k: 'halted', w: 'halted', s: 'halted · ' + s } : { k: 'ok', w: 'on time', s };
  },
  list: a => (a || []).join(', '),
  plural: (n, one, many) => fmt.int(n) + ' ' + (Number(n) === 1 ? one : (many || one + 's')),
  punct: b => {
    const k = clockOf(b); if (!k) return '';
    const lim = limOf(b), m = modeOf(b).eff === 'live' ? 'l' : 'p';
    const known = !!b && Array.isArray(b.runs);
    const late = runsOf(b).filter(r => !r.x && r.ok === 0 && (!r.m || r.m === m) && r.lm != null).map(r => r.lm);
    let s = k.lag_n >= 3 && Array.isArray(k.lag_rng) ? 'Usually ' + Math.round(k.lag_med_min) + ' min after the close (' + k.lag_rng[0] + '–' + k.lag_rng[1] + ')' : 'Too few on-time checks yet to measure the usual start';
    s += ' · limit ' + lim + ' · ' + (!known ? 'late runs not in this data' : late.length ? word.plural(late.length, 'late run') + ' in 7 days (' + late.join(', ') + ' min)' : 'no late runs in 7 days');
    return s + '.';
  },
  alert: a => {
    if (!a) return '';
    let h = esc(a.text || '').replace('{time}', esc(fmt.when(a.t)));
    if (a.c && String(a.text || '').indexOf(a.c + ':') === 0) h = chip(a.c, a.t) + h.slice(esc(a.c).length);
    return h;
  },
  event: e => {
    if (!Array.isArray(e)) return { html: '', ic: 'info', lv: 0 };
    const [t, ty, c, kind, tier, lv, det, R, rel, pp] = e;
    const C = c ? chip(c, t) : '', k = word.kind(kind), D = det == null ? '' : esc(det);
    const Rs = v => '<span class="' + fmt.cls(v) + '">' + fmt.R(v) + '</span>';
    // a sale or a raised stop: % of pot first (1 R is a different share of pot per bot), R in brackets
    const RP = (v, x) => num(pp) != null ? '<span class="' + fmt.cls(pp) + '">' + fmt.pct(pp) + '</span> of pot (' + Rs(v) + (x ? ', ' + x : '') + ')' : Rs(v) + (x ? ' (' + x + ')' : '');
    const dirs = s => String(s || '').split(',').map(x => x.trim()).filter(Boolean).map(x => {
      if (x === 'a in') return 'now one flip away';
      if (x === 'a out') return 'no longer one flip away';
      const m = x.match(/^(w|d|h4) (\S+)>(\S+)$/); if (!m) return esc(x);
      return ({ w: 'weekly', d: 'daily', h4: bw() })[m[1]] + (m[3] === 'n' ? ' lost its reading' : ' turned ' + (DIRW[m[3]] || esc(m[3])));
    }).join(', ');
    let s;
    switch (ty) {
      case 'bought': { if (kind === 'book') { s = (tier === 'S' ? 'Shorted ' : 'Bought ') + C + ' (' + (tier === 'S' ? 'short' : 'long') + ' leg of the book)'; break; }
        const sp = (String(det || '').match(/stop ([\d.]+)/) || [])[1]; s = 'Bought ' + C + (KIND[kind] ? ' on a ' + word.kind(kind, true) : kind === 'carry' ? ' (a carry pair)' : '') + (tier === 'A' || tier === 'B' ? ' (' + word.tier(tier).toLowerCase() + ')' : '') + (sp ? ', stop ' + fmt.pctu(sp, 1) + ' below' : ''); break; }
      case 'sold': s = (kind === 'book' && tier === 'S' ? 'Covered ' : 'Sold ') + C + ' ' + RP(R, word.exit(det)) + (rel != null ? ' · ' + Rs(rel) + ' vs holding' : ''); break;
      case 'trail': s = C + ' stop raised' + (R != null ? (rz(R, 2) < 0 ? ', still risks ' : ', locks ') + RP(R) : ''); break;
      case 'blocked': {
        const rs = esc(word.reasons(word.codes(det), true)) || 'a safety check';
        s = kind === 'book' ? C + ' ' + (tier === 'S' ? 'short' : 'long') + ' leg blocked: ' + rs : tier === 'A' ? C + ' would have bought (auto grade), blocked: ' + rs : C + ' ' + k + (tier === 'B' ? ' (watch-only)' : '') + ' blocked: ' + rs; break;
      }
      case 'recorded': s = C + ' ' + k + ' recorded, ' + (tier === 'A' ? 'auto grade' : 'watch-only grade'); break;
      case 'proposed': s = C + ' ' + k + ' proposed (old approval model)'; break;
      case 'expired': s = C + ' ' + k + ' proposal expired (old approval model)'; break;
      case 'notfilled': s = C + ' order not filled'; break;
      case 'late': s = 'The check started ' + (D || 'too long') + ' min after the close; buys skipped'; break;
      case 'failed': s = 'The check stopped early' + (D ? ' (' + D + ')' : '') + '. Exits may not have been checked'; break;
      case 'halt': s = 'Halted' + (D ? ': ' + D : '') + '. No new buys; exits still run'; break;
      case 'resume': s = 'Resumed: buying is allowed again'; break;
      case 'thr_halt': s = 'Drawdown ' + (D ? D + '% ' : '') + 'reached the limit: buying stopped until reviewed'; break;
      case 'thr_half': s = 'Drawdown ' + (D ? D + '%' : '') + ': risk per trade halved'; break;
      case 'recon': s = 'Exchange and ledger disagree; entries paused'; break;
      case 'no_stop': s = C + ': the resident stop could not be placed'; break;
      case 'close_failed': s = C + ': the close was not filled; kept for the next check'; break;
      case 'exit_failed': s = det === 'nomark' ? C + ': an exit signal came without a mark price; kept for the next check' : C + ': the exit check failed' + (D ? ' (' + D + ')' : '') + '; kept'; break;
      case 'fallback': s = 'Live requested, running paper: ' + (det === 'sdk' ? 'exchange SDK not installed' : det === 'key' ? 'exchange key or account address missing' : 'live requirements missing'); break;
      case 'regime': {
        const [a, z] = String(det || '').split('>'), parts = [];
        if (a && z) { if (a[0] !== z[0]) parts.push('weekly turned ' + (DIRW[z[0]] || '?')); if (a[1] !== z[1]) parts.push('daily turned ' + (DIRW[z[1]] || '?')); }
        s = 'Bitcoin’s ' + (parts.join(' and ') || 'regime changed'); break;
      }
      case 'gap': s = C + ': no reading on one timeframe; position and stop kept'; break;
      case 'entry_failed': s = det === 'candles' ? C + ': candles unavailable; skipped this check' : C + ': the entry check failed' + (D ? ' (' + D + ')' : '') + '; skipped this check'; break;
      case 'not_on_exchange': s = C + ': not on the exchange and no sell fill'; break;
      case 'sweep': { const m = String(det || '').match(/^(\S+) ([\d.]+)$/); s = C + ' gain earmarked for ' + (m ? esc(m[1]) + ' (' + fmt.pctu(m[2], 2) + ' of pot)' : 'its benchmark') + ' · recorded, not executed'; break; }
      case 'review': s = 'Sunday review written'; break;
      case 'board': s = C + ': ' + (dirs(det) || 'reading changed'); break;
      case 'resized': s = 'Resized ' + C + (D ? ' to ' + D + '% of pot' : ''); break;
      case 'carry_in': s = 'Started collecting on ' + C + (numv(det) != null ? ' · funding ' + fmt.num(det, 1) + '%/yr' : ''); break;
      case 'carry_out': s = 'Started closing ' + C + ' carry' + (numv(det) != null ? ' · funding ' + fmt.num(det, 1) + '%/yr' : ''); break;
      case 'carry_closed': { const [r, cp] = String(det || '').split(','); s = 'Closed ' + C + ' carry' + (numv(r) != null ? ' · <span class="' + fmt.cls(r) + '">' + fmt.pct(r) + '</span> of pot' : '') + (cp ? ' · kept ' + esc(cp) + ' of its funding' : ''); break; }
      case 'carry_fix': s = C + ': evened its legs at market'; break;
      default: s = (C ? C + ' ' : '') + esc(ty || 'event');
    }
    return { html: s, ic: EV_IC[ty] || 'info', lv: numv(lv) || 0, t, type: ty, c };
  },
};

// ======================================================================================== registries ==
const VIEWS = {};
const COMP = {};
const SHEETS = {};
const HOOKS = { arrival: [], tick1s: [], tick30s: [], route: [], theme: [], hide: [], show: [], status: [], agents: [] };
function hooksOf(name) { const h = HOOKS[name]; return h == null ? [] : Array.isArray(h) ? h : [h]; }
function hook(name, fn) { HOOKS[name] = hooksOf(name); HOOKS[name].push(fn); }
function runHooks(name, ...a) { hooksOf(name).forEach(fn => call(fn, ...a)); }

// ============================================================================================ state ==
// The bot page's tabs (COMMAND_CENTER_SPEC §2.2), in key order 1–4. The master has one view, 'fleet'.
const TABS = ['overview', 'results', 'activity', 'rules'];
const TITLE = { overview: 'Overview', results: 'Trades', activity: 'Activity', rules: 'Rules', fleet: 'Command center', lab: 'AiFi Lab' };
const S = { b: null, ledger: null, ledgerGen: null, ledgerErr: null, cursor: null, tab: 'overview', sub: null, prev: null,
            st: null, net: 'checking', seenAt: 0, seenEv: 0, sheet: null, bootErr: null, booting: false, E: null, prevE: null, agentsErr: null, stamp: null };
// Whether the page has its data: the bundle on a bot page, the exec:agents envelope on the master.
function ready() { return PAGE === 'lab' || (PAGE === 'fleet' ? !!S.E : !!S.b); }
function runsOf(b) { b = b || S.b; return b && Array.isArray(b.runs) ? b.runs : []; }
function modeOf(b) {
  const m = b && b.mode;
  if (m && typeof m === 'object') return { eff: m.eff || null, req: m.req || m.eff || null, note: m.note || '' };
  return { eff: m || null, req: (b && b.settings && b.settings.mode) || m || null, note: '' };    // v1: a plain string
}
function lastRun(b) {
  const rs = runsOf(b), m = modeOf(b || S.b).eff === 'live' ? 'l' : 'p';
  for (let i = rs.length - 1; i >= 0; i--) if (!rs[i].m || rs[i].m === m) return rs[i];
  return rs[rs.length - 1] || null;
}
function runAt(t, b) { const n = Number(t); return t == null || t === '' || !isFinite(n) ? null : runsOf(b).find(r => r.t === n) || null; }
function cursorRun() { return (S.cursor != null && runAt(S.cursor)) || lastRun(); }
function nameOf(c) { return ((S.b && S.b.names) || []).find(n => n.c === c) || null; }
const CURSOR = [];
function onCursor(fn) { CURSOR.push(fn); }
// Shared cycle cursor (§5), null = the latest run. With the cycle sheet open, moving the cursor redraws that sheet;
// off Overview it opens it; on Overview the followers replay, and {scroll:true} opens and shows the Gate Run.
function setCursor(t, opts) {
  opts = opts || {};
  let v = t == null || t === '' ? null : Number(t);
  if (v != null && !isFinite(v)) v = null;
  const last = lastRun();
  if (v != null && last && v === last.t) v = null;
  const prev = S.cursor; S.cursor = v;
  CURSOR.forEach(fn => call(fn, v, prev, opts));
  if (opts.sheet === false) return;
  const tt = v != null ? v : last && last.t;
  if (S.sheet && S.sheet.kind === 'cycle' && tt != null) return openSheet(sheetContent('cycle', tt), { kind: 'cycle', arg: tt, replace: true });
  if (S.tab !== 'overview') { if (tt != null) showSheet('cycle', tt); return; }
  const gr = document.getElementById('overview-gaterun');
  if (opts.scroll && gr) { if (gr.tagName === 'DETAILS') gr.open = true; into(gr, true); }
}

// ======================================================================== the status engine (§3) ==
// A v2 bundle carries clock and state. A v1 bundle is read into the same shape, so the capsule stays truthful.
function clockOf(b) {
  if (!b) return null;
  if (b.clock && b.clock.last_t != null) return b.clock;
  const t = b.last_run && isoS(b.last_run.t);
  if (t == null) return b.clock || null;
  const bar = barOf(b);
  return { last_t: t, last_slot: Math.floor(t / bar) * bar, late_min: null, lag_med_min: 20, lag_rng: null, lag_n: 0, limit_min: null, sched_min: 5 };
}
function stateOf(b) {
  if (b && b.state) return b.state;
  const lr = (b && b.last_run) || {}, th = lr.throttle;
  return { halt: { set: !!lr.halt, reason: null, since: null },
           thr: th ? { state: th.halt ? 'halted' : th.multiplier < 1 ? 'halved' : 'normal', mult: th.multiplier, dd_pct: th.drawdown_pct } : { state: 'unknown', mult: null, dd_pct: null },
           btc: {}, last: { t: isoS(lr.t), fresh: lr.fresh, failed: lr.failed, late_min: null, abort: null } };
}
function limOf(b) { return (b && b.cfg && b.cfg.late_min) || (b && b.clock && b.clock.limit_min) || (b && b.settings && b.settings.data && b.settings.data.late_run_minutes) || 45; }
function thrOf(b) { const t = b && b.cfg && b.cfg.thr; if (Array.isArray(t)) return t; const s = b && b.settings && b.settings.throttle; return s ? [s.halve_at_drawdown_pct, s.halt_at_drawdown_pct] : [null, null]; }
function nOpen(b) {
  if (b && b.risk && b.risk.n_open != null) return b.risk.n_open;
  if (b && Array.isArray(b.pos)) return b.pos.length;
  if (b && b.positions && typeof b.positions === 'object') return Object.keys(b.positions).length;
  return 0;
}
// barOf(b): the bot's bar in seconds (COMMAND_CENTER_SPEC §9 B0). The bundle says it (clock.bar_s); an older bundle
// is read from cfg.tf, then from its exec:agents row's tf (a v1 field), and only then assumed to be 4 hours.
function barOf(b) {
  const x = b && b.clock && num(b.clock.bar_s);
  if (x > 0) return x;
  const tf = b && b.cfg && b.cfg.tf;
  if (TF[tf]) return TF[tf];
  const r = rowOf(AGENT);
  return (r && (num(r.bar_s) || TF[r.tf])) || 14400;
}
// How long after its close a check counts as missed for good: a whole bar but at least 2 h, and never under 4 h nor
// under the late limit plus an hour (an hourly bot is stale after two missed checks, not one late hour; a daily one 4 h
// after its close). Exits count as unchecked 2 h after the close; for an hourly bot that is when it turns stale.
function staleGap(bar, lim) { return Math.min(Math.max(bar, 7200), Math.max(14400, lim * 60 + 3600)); }
// clock(b, now): §3.1 with the per-bar rule (COMMAND_CENTER_SPEC §6.7). C is the next close the engine owes a check
// for; every time is recomputed from now. A 4-hour bot gives exactly the same output as before the rule.
function clock(b, now) {
  b = b === undefined ? S.b : b; now = now == null ? nowS() : now;
  const k = clockOf(b), lim = limOf(b), bar = barOf(b);
  if (!k || k.last_slot == null || k.last_t == null) return { phase: 'none', now, lim, lag: 20, C: null, next: null, nOpen: nOpen(b), exits: false };
  const lag = (k.lag_n != null && k.lag_n < 3) ? 20 : (numv(k.lag_med_min) ?? 20);
  const C = k.last_slot + bar, next = Math.round(C + lag * 60), lateAt = C + lim * 60, staleAt = C + staleGap(bar, lim), exitsAt = C + 7200;
  const phase = now < next ? 'countdown' : now < lateAt ? 'due' : now < staleAt ? 'late' : 'stale';
  const n = nOpen(b);
  return { phase, now, C, lag, lim, next, lateAt, staleAt, exitsAt, sched: C + (numv(k.sched_min) ?? 5) * 60, lastT: k.last_t, lastSlot: k.last_slot,
           age: now - k.last_t, over: now - C, toNext: next - now, rng: Array.isArray(k.lag_rng) ? k.lag_rng : null, lagN: k.lag_n ?? null,
           nOpen: n, exits: phase === 'late' && now >= exitsAt && n > 0 };
}
const DOT = { ok: 'ok', info: 'due', warn: 'gap', bad: 'bad' };
const LVCLS = { ok: '', info: '', warn: 'warn', bad: 'bad' };
const COVERED = new Set(['failed', 'halt', 'thr_halt', 'thr_half', 'fallback', 'late']);     // alerts the state already speaks for
const AWORD = { unhedged: 'Legs uneven', exit_slow: 'Closing slow' };                                                    // a warn alert's own word ("Check" otherwise)
const HOLD = '#overview/holding';
// The page is behind its bot (2026-10-16): the committed state records a newer check than this page shows, because the
// dashboard update failed or has not landed. From the row's ran_t and push_fail (rowBundle; a bot page reads its own row)
// and a failed push's error stamp (S.stamp.err). → {ran, pf} or null.
function behindOf(b, K) {
  let ran = num(b && b.ran), pf = b && isObj(b.pf) ? b.pf : null;
  if (PAGE === 'bot' && b && b === S.b) {
    const A = rowOf(AGENT), s = S.stamp;
    if (A) { ran = num(A.ran_t); pf = isObj(A.push_fail) ? A.push_fail : null; }
    if (isObj(s) && s.err) { const t = isoS(s.t); if (t != null && (ran == null || t > ran)) ran = t; pf = pf || { why: String(s.err) }; }
  }
  return ran != null && K.lastT != null && ran > K.lastT + 60 ? { ran, pf } : null;
}
// Why the page is behind, in plain words (the raw reason stays in the Health sheet).
function pfWords(pf) {
  const w = String((pf && pf.why) || '');
  return /^data check/.test(w) ? 'a privacy check refused the new numbers' : /^Cloudflare/.test(w) ? 'the dashboard store refused them'
    : /timed out/.test(w) ? 'the update timed out' : /^build/.test(w) ? 'the new numbers could not be put together' : 'the update failed';
}
// Who to suspect when a bot is stale: the server's own heartbeat (exec:agents host.t, refreshed by every dashboard sync)
// and the index's age tell "the server is down" from "this bot's checks are not landing". Never blame the runner while
// its heartbeat is fresh.
function staleWhy(b, now) {
  const E = S.E || {}, h = (b && isObj(b.host) && b.host) || (isObj(E.host) && E.host) || null, ht = h ? isoS(h.t) : null, eg = isoS((b && b.egen) || E.gen);
  if (ht != null && now - ht < 7200) return [', though the server is running: this bot’s checks are not landing.', '· its checks are not landing'];
  if (eg != null && now - eg < 7200) return ['. The server may be down: its last tick was ' + esc(ht != null ? fmt.when(ht) : 'not recorded') + '.', '· the server may be down'];
  return ['. The server, or the dashboard update, may be down.', '· the server may be down'];
}
// status(b, now): one truth for the capsule, rail mirror, verdict, alert rail and the master's tiles. The first item marked
// head sets the headline (§3.2 precedence); every item goes to the alert rail and the Health sheet. When the page is behind
// (behindOf), the clock runs from the newest check the state records, and "Page behind" leads.
function status(b, now) {
  b = b === undefined ? S.b : b;
  let K = clock(b, now);
  if (!b) return { lvl: 'info', dot: 'mute', word: 'Checking…', age: '', wide: '', sentence: 'Checking…', k: 'none', items: [], K };
  const pb = behindOf(b, K), shown = K.lastT;
  if (pb) { const bar = barOf(b); K = clock(Object.assign({}, b, { clock: Object.assign({}, clockOf(b), { last_t: pb.ran, last_slot: Math.floor(pb.ran / bar) * bar }) }), K.now); }
  const st = stateOf(b), last = st.last || {}, halt = st.halt || {}, thr = st.thr || {}, m = modeOf(b), T = t => esc(fmt.when(t));
  const ageLast = K.lastT != null ? fmt.age(K.age) : '', items = [];
  const RUNBOOK = { label: 'Runbook', href: '#rules/operations' };
  const add = (lvl, k, wd, sentence, o) => items.push(Object.assign({ lvl, k, word: wd, sentence, act: null, age: ageLast, wide: '', head: true }, o));
  const dd = thr.dd_pct != null ? fmt.pctu(thr.dd_pct, 1) : null, lims = thrOf(b);
  const behind = () => add(pb.pf ? 'bad' : 'warn', 'behind', 'Page behind', '<b>Page behind</b> · it checked at ' + T(pb.ran) + ', but this page still shows ' + T(shown)
    + (pb.pf ? ': ' + pfWords(pb.pf) + (num(pb.pf.since) != null ? ' (failing since ' + T(pb.pf.since) + ')' : '') : ' (the update has not landed yet)') + '. The bot itself is running.',
    { act: RUNBOOK, age: fmt.age(pb.ran - shown), wide: '· checked ' + fmt.when(pb.ran) + ', page shows ' + fmt.when(shown) });   // age: how far behind
  if (pb && pb.pf) behind();
  if (last.failed) add('bad', 'failed', 'Failed', '<b>Needs you</b> · the ' + T(last.t) + ' check stopped early' + (last.abort ? ' (' + esc(last.abort) + ')' : '') + '. Exits may not have been checked.',
    { act: { label: 'See check', cycle: last.t }, wide: '· the ' + fmt.when(last.t) + ' check stopped early' });
  if (halt.set) add('bad', 'halt', 'Halted', '<b>Halted</b> since ' + (halt.since ? T(halt.since) : 'unknown') + ': ' + esc(halt.reason || 'manual halt') + '. No new buys; exits still run.',
    { act: RUNBOOK, wide: '· no new buys' });
  if (thr.state === 'halted') add('bad', 'thr_halt', 'Buying stopped', '<b>Buying stopped</b> · drawdown ' + (dd || '—') + ' reached the ' + (lims[1] != null ? esc(lims[1]) + '% ' : '') + 'limit.',
    { act: { label: 'Positions', href: HOLD }, wide: dd ? '· drawdown ' + dd : '' });
  if (K.phase === 'stale') { const w = staleWhy(b, K.now); add('bad', 'stale', 'Stale', '<b>Stale</b> · no check for ' + esc(fmt.age(K.age)) + w[0], { act: RUNBOOK, wide: w[1] }); }
  if (K.exits) add('bad', 'exits', 'Exits unchecked', '<b>Needs you</b> · exits not checked since ' + T(K.lastT) + '.',
    { act: { label: 'See positions', href: HOLD }, age: fmt.age(K.over), wide: '· since ' + fmt.when(K.lastT) });
  const alerts = Array.isArray(b.alerts) ? b.alerts.filter(a => a && typeof a === 'object') : [];
  const actOf = a => a.c && /^(gap|close_failed|exit_failed|unhedged|exit_slow)$/.test(a.k) ? { label: 'See position', href: HOLD } : a.k === 'entry_failed' ? { label: 'See check', cycle: a.t != null ? a.t : last.t } : RUNBOOK;
  for (const a of alerts) if (a.lv === 'bad' && !COVERED.has(a.k)) add('bad', a.k, 'Needs you', word.alert(a), { act: actOf(a), wide: '· see the alert' });
  if (pb && !pb.pf) behind();
  if (K.phase === 'late' && !K.exits) add('warn', 'late_now', 'Late', '<b>Late</b> · no check yet for the ' + T(K.C) + ' close. After ' + T(K.lateAt) + ' it skips buys.',
    { act: RUNBOOK, age: fmt.age(K.over), wide: '· no check for the ' + fmt.time(K.C) + ' close' });
  if (m.req && m.eff && m.req !== m.eff) add('warn', 'fallback', 'Paper fallback', '<b>Live requested, running paper</b>: ' + esc(m.note || 'live requirements missing') + '.', { act: RUNBOOK, wide: '· live requested' });
  if (last.fresh === false && !last.failed) {
    const lm = last.late_min != null ? last.late_min : (lastRun(b) || {}).lm;
    add('warn', 'late', 'Ran late', '<b>Ran late</b> · the last check started ' + (lm != null ? esc(lm) + ' min' : 'too long') + ' after the close, so buys were skipped for that bar.',
      { act: { label: 'See check', cycle: last.t }, wide: lm != null ? '· ' + lm + ' min after the close' : '' });
  }
  if (thr.state === 'halved') add('warn', 'thr_half', 'Risk halved', '<b>Risk halved</b> · drawdown ' + (dd || '—') + ' (halves at ' + esc(lims[0] ?? '—') + '%, stops at ' + esc(lims[1] ?? '—') + '%).',
    { act: { label: 'Positions', href: HOLD }, wide: dd ? '· drawdown ' + dd : '' });
  for (const a of alerts) if (a.lv === 'warn' && !COVERED.has(a.k)) add('warn', a.k, AWORD[a.k] || 'Check', word.alert(a), { act: actOf(a) });
  if (K.phase === 'due') add('info', 'due', 'Due now', '<b>Due now</b> · checks usually land ' + (K.rng ? esc(K.rng[0]) + '–' + esc(K.rng[1]) : 'about ' + Math.round(K.lag)) + ' min after the close.',
    { age: '', wide: '· usually by ' + fmt.time(K.C + (K.rng ? K.rng[1] : K.lag) * 60) });
  for (const a of alerts) if (a.lv === 'info' && !COVERED.has(a.k))
    add('info', a.k, 'Note', word.alert(a), { head: false, act: a.k === 'proposals' ? { label: 'See them', href: HOLD } : /^(unhedged|exit_slow)$/.test(a.k) ? actOf(a) : null });
  let head = items.find(i => i.head);
  if (!head) head = K.phase === 'none'
    ? { lvl: 'info', k: 'none', word: 'No checks yet', age: '', wide: '', sentence: '<b>No checks yet</b> · the first check after deployment writes here.' }
    : { lvl: 'ok', k: 'ok', word: 'On schedule', age: ageLast, wide: K.next ? '· next check ≈ ' + fmt.when(K.next) : '', sentence: '<b>All clear</b> · nothing needs you.' };
  const gen = isoS(b.gen || b.generated);
  const trail = !pb && gen != null && K.lastT != null && gen - K.lastT > 600 ? ' · pushed ' + fmt.when(gen) : '';
  return { lvl: head.lvl, dot: DOT[head.lvl], word: head.word, age: head.age, wide: (head.wide || '') + trail, sentence: head.sentence, k: head.k, items, K, head, pb, shown };
}

// ================================================================================= fetch + ledger ==
// ---- pages and agents (COMMAND_CENTER_SPEC §2). "/" is the Command Center (PAGE 'fleet', AGENT null); "/?a=<id>" is
// one bot's page (PAGE 'bot'). Every bot page is a full page load, so nothing from one bot's numbers can carry into
// another's. ex.agent is read once, by the legacy-hash redirect, and never written.
const AGENT_RE = /^[a-z][a-z0-9-]{1,23}$/;
const AGENT = (function () {
  let a = null;
  try { a = new URLSearchParams(location.search).get('a'); } catch (e) {}
  return AGENT_RE.test(a || '') ? a : null;
})();
// "/lab" is the AiFi Lab page (COMMAND_CENTER_SPEC §11): its own bundle (core + lab + boot); lab.js loads its data, core only routes.
const PAGE = AGENT ? 'bot' : location.pathname === '/lab' ? 'lab' : 'fleet';
AGENT_NS = AGENT && AGENT !== 'core' ? AGENT : '';
function api(path) { return !AGENT || AGENT === 'core' ? path : path + (path.indexOf('?') < 0 ? '?' : '&') + 'a=' + encodeURIComponent(AGENT); }
function botHref(id, hash) { const h = hash == null ? '' : String(hash).replace(/^#/, ''); return '/?a=' + encodeURIComponent(id) + (h ? '#' + h : ''); }
function ssGet(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
function ssSet(k, v) { try { if (v == null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, String(v)); } catch (e) {} }
// Back to the master: when the master opened this page (ex.fl.from), history.back() lets the bfcache restore it at its
// scroll position; tabs and ‹ › never add history entries, so that entry is always the fleet. Otherwise load "/".
function goFleet() {
  if (ssGet('ex.fl.from') === '1') { ssSet('ex.fl.from', null); history.back(); return; }
  location.href = '/';
}
function switchAgent(id) { if (PAGE === 'bot') location.replace(botHref(id)); else location.href = botHref(id); }   // factory.js "Open"; bot → bot replaces (§2.4)
// The pre-boot redirect of an old "/#tab" bookmark or alert link to that tab on a bot page (§2.5).
const LEGACY = { now: 'overview', overview: 'overview', positions: 'overview/holding', book: 'overview/holding', results: 'results',
                 trades: 'results', refused: 'activity/signals', activity: 'activity', logic: 'rules', rules: 'rules' };
function legacyHash() {
  if (PAGE !== 'fleet') return false;
  const raw = (location.hash || '').slice(1); if (!raw) return false;
  let h; try { h = decodeURIComponent(raw); } catch (e) { h = raw; }
  const parts = h.split('/'), to = LEGACY[parts[0]]; if (!to) return false;
  const sub = parts.slice(1).join('/'), stored = lsGet('ex.agent', null), id = AGENT_RE.test(stored || '') ? stored : 'core';
  location.replace(botHref(id, to + (sub && to.indexOf('/') < 0 ? '/' + sub : '')));
  return true;
}
let AGENTS = null;
function rowOf(id) { return (id && Array.isArray(AGENTS) && AGENTS.find(r => r && r.id === id)) || null; }
function orderOf(E) { E = E || S.E || {}; const o = Array.isArray(E.order) && E.order.length ? E.order : (AGENTS || []).map(r => r && r.id); return o.filter(Boolean); }
// ‹ › on a bot page: the neighbour in exec:agents.order, replacing this history entry so Back still means "All bots".
function botStep(d) {
  const o = orderOf(), i = o.indexOf(AGENT); if (i < 0 || o.length < 2) return;
  location.replace(botHref(o[(i + d + o.length) % o.length], location.hash));
}
let agentsP = null;
function loadAgents() {
  if (agentsP) return agentsP;
  agentsP = getJSON('/api/agents', 8000).then(r => {
    const E = r && typeof r === 'object' && !Array.isArray(r) ? r : {};
    S.E = E; AGENTS = Array.isArray(E.agents) ? E.agents.filter(isObj) : [];
  }, e => { if (!AGENTS) AGENTS = []; S.agentsErr = (e && e.kind) || 'net'; })
    .then(() => { agentsP = null; runHooks('agents', AGENTS, S.E); return AGENTS; });
  return agentsP;
}
// A status pseudo-bundle from one exec:agents row (§6.7): status(rowBundle(row)) on the master gives the same word the
// bot page computes from status(S.b). A fleet halt forces state.halt. A v1 row (no sb) has none: null.
function rowBundle(A, E) {
  if (!A || !isObj(A.sb)) return null;
  E = E || S.E || {};
  const sb = A.sb, ck = isObj(sb.clock) ? sb.clock : {}, st = isObj(sb.state) ? sb.state : {}, fl = isObj(E.fleet) ? E.fleet : {};
  const halt = fl.halt && !(st.halt && st.halt.set)
    ? Object.assign({}, st, { halt: { set: true, reason: 'fleet halt: ' + (fl.reason || 'no reason given'), since: fl.since } }) : st;
  return { v: 2, gen: A.gen, clock: Object.assign({}, ck, { bar_s: ck.bar_s || A.bar_s || TF[A.tf] }), state: halt, cfg: isObj(sb.cfg) ? sb.cfg : {},
           mode: sb.mode, alerts: Array.isArray(sb.alerts) ? sb.alerts : [], risk: sb.risk, runs: [],
           ran: num(A.ran_t), pf: isObj(A.push_fail) ? A.push_fail : null, host: isObj(E.host) ? E.host : null, egen: E.gen };
}
// The bot's kind: its bundle's cfg.kind, its row's kind, or inferred from what it holds and logs (said as inferred).
const KINDS = { flip: 1, target: 1, carry: 1 };
function kindInfo(b) {
  b = b === undefined ? S.b : b;
  const k = b && b.cfg && b.cfg.kind; if (KINDS[k]) return { kind: k, inferred: false };
  const r = b && KINDS[b.kind] ? b : rowOf(AGENT);
  if (r && KINDS[r.kind]) return { kind: r.kind, inferred: false };
  const ev = b && Array.isArray(b.events) ? b.events : [];
  if ((b && Array.isArray(b.pos) && b.pos.some(p => p && p.kind === 'target')) || ev.some(e => Array.isArray(e) && e[3] === 'target')) return { kind: 'target', inferred: true };
  if (ev.some(e => Array.isArray(e) && e[3] === 'carry')) return { kind: 'carry', inferred: true };
  return { kind: 'flip', inferred: true };
}
function kindOf(b) { return kindInfo(b).kind; }
// /api/factory (exec:factory, the AiFi Lab), cached for 5 minutes; never rejects (null when unavailable).
let fxCache = null, fxAt = 0, fxP = null;
function loadFactory(force) {
  if (!force && fxCache && Date.now() - fxAt < 300e3) return Promise.resolve(fxCache);
  if (fxP) return fxP;
  fxP = getJSON('/api/factory', 10000).then(d => { fxCache = isObj(d) && d.v === 1 ? d : null; fxAt = Date.now(); return fxCache; }, () => fxCache)
    .finally(() => { fxP = null; });
  return fxP;
}
async function getJSON(url, ms) {
  const ctl = typeof AbortController === 'function' ? new AbortController() : null;
  const tm = ctl ? setTimeout(() => ctl.abort(), ms || 10000) : 0;
  let r;
  try { r = await fetch(url, { signal: ctl ? ctl.signal : undefined, cache: 'no-store', credentials: 'same-origin', headers: { accept: 'application/json' } }); }
  catch (e) { clearTimeout(tm); throw { kind: 'net', err: e }; }
  if (r.status === 401 || (r.redirected && /\/login\b/.test(r.url))) { clearTimeout(tm); throw { kind: 'auth', status: r.status }; }
  if (r.status === 404) { clearTimeout(tm); throw { kind: 'missing', status: 404 }; }
  if (!r.ok) { clearTimeout(tm); throw { kind: 'server', status: r.status }; }
  let txt;
  try { txt = await r.text(); } catch (e) { throw { kind: 'net', err: e }; } finally { clearTimeout(tm); }
  try { return JSON.parse(txt); } catch (e) { throw { kind: 'parse' }; }
}
let ledgerP = null;
function loadLedger(force) {
  const gen = S.b && S.b.gen;
  if (!force && S.ledgerGen != null && S.ledgerGen === gen) return Promise.resolve(S.ledger);
  if (ledgerP && ledgerP.gen === gen && !force) return ledgerP;
  // A v1 bundle predates exec:ledger: say so without a request that can only 404.
  if (S.b && S.b.v == null) { S.ledger = null; S.ledgerGen = gen; S.ledgerErr = 'missing'; return Promise.resolve(null); }
  const p = getJSON(api('/api/ledger'), 15000).then(L => {
    if (!L || typeof L !== 'object') throw { kind: 'parse' };
    S.ledger = L; S.ledgerGen = gen; S.ledgerErr = null; return L;
  }).catch(e => {
    S.ledgerErr = (e && e.kind) || 'net';
    if (S.ledgerErr === 'missing') { S.ledger = null; S.ledgerGen = gen; }
    if (S.ledgerErr === 'auth') { S.net = 'signedout'; paintCapsule(); }
    return S.ledgerGen === gen ? S.ledger : null;
  }).finally(() => { if (ledgerP === p) ledgerP = null; });
  p.gen = gen; ledgerP = p;
  return p;
}
const LWC_URL = 'https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js';
let lwcP = null;
function loadLWC() {
  if (window.LightweightCharts) return Promise.resolve(window.LightweightCharts);
  if (lwcP) return lwcP;
  lwcP = new Promise((res, rej) => {
    const s = document.createElement('script');
    let tm = 0;
    const fail = why => { clearTimeout(tm); lwcP = null; s.remove(); rej(new Error(why)); };
    tm = setTimeout(() => fail('the chart library timed out'), 15000);
    s.src = LWC_URL; s.async = true; s.crossOrigin = 'anonymous'; s.referrerPolicy = 'no-referrer';
    s.onload = () => { clearTimeout(tm); if (window.LightweightCharts) res(window.LightweightCharts); else fail('the chart library did not load'); };
    s.onerror = () => fail('the chart library did not load');
    document.head.appendChild(s);
  });
  return lwcP;
}

// ================================================================================ motion + controls ==
// Ported from ~/aifi/cloud/client.js: setSeg 311, initSegs 318, countUp 368 (with a `from`), stagger 376, movePill 379.
function countUp(el, to, opts) {
  if (!el) return;
  const o = Object.assign({ from: 0, decimals: 0, prefix: '', suffix: '', ms: 800, fmt: null }, opts || {});
  const out = v => { el.textContent = o.fmt ? o.fmt(v) : o.prefix + Number(v).toFixed(o.decimals) + o.suffix; };
  const tk = el._cu = (el._cu || 0) + 1;
  if (reduced || o.from === to || !isFinite(to) || !isFinite(o.from)) return out(to);
  const t0 = performance.now();
  const step = now => { if (el._cu !== tk) return; const k = Math.min(1, Math.max(0, (now - t0) / o.ms)), e = 1 - Math.pow(1 - k, 3); out(k < 1 ? o.from + (to - o.from) * e : to); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
function stagger(root) { $$('.rise', root || document).forEach((el, i) => { el.style.animationDelay = Math.min(i * 60, 600) + 'ms'; }); }
function setSeg(seg, value) {
  if (!seg) return;
  const btns = $$('button', seg); let on = null;
  btns.forEach(b => { const hit = (b.dataset.tf ?? b.dataset.v) === value; b.setAttribute('aria-pressed', hit ? 'true' : 'false'); if (hit) on = b; });
  const ind = $('.ind', seg); if (!ind || !on) return;
  ind.style.width = on.offsetWidth + 'px'; ind.style.transform = 'translateX(' + on.offsetLeft + 'px)';
  if (seg.scrollWidth > seg.clientWidth) { const left = Math.max(0, on.offsetLeft - (seg.clientWidth - on.offsetWidth) / 2); try { seg.scrollTo({ left, behavior: 'instant' }); } catch (e) { seg.scrollLeft = left; } }
}
function initSegs(root) { $$('.seg', root || document).forEach(seg => { const on = $('button[aria-pressed=true]', seg); if (on) setSeg(seg, on.dataset.tf ?? on.dataset.v); }); }
function movePill() {
  const pill = $('.rail nav .pill'), on = $('.rail nav a[aria-current=page]'); if (!pill || !on) return;
  pill.style.transform = 'translateY(' + on.offsetTop + 'px)'; pill.style.height = on.offsetHeight + 'px'; pill.classList.add('on');
}
// Overflowing scrollers get an edge fade on each side that hides more (mask-r / mask-l), plus region semantics (§15).
const SCROLLERS = '.tbl,.cycbar,[data-mask]';
function maskOne(el) {
  const over = el.scrollWidth > el.clientWidth + 1;
  el.classList.toggle('mask-r', over && el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  el.classList.toggle('mask-l', over && el.scrollLeft > 2);
  if (!el.hasAttribute('tabindex')) el.tabIndex = 0;
  if (!el.getAttribute('role')) el.setAttribute('role', 'region');
  if (!el.getAttribute('aria-label')) { const c = el.closest('.card,section,.sheet'), h = c && $('h2,h3', c); el.setAttribute('aria-label', h ? h.textContent.trim() : 'Scrollable list'); }
}
function masks(root) { $$(SCROLLERS, root || document).forEach(maskOne); }
// Markdown tables (the Rules docs, the Sunday review; md() in worker.js writes '<div class="tbl"><table>…') go
// inside a disclosure: closed under 900px, open from 900px (acceptance: tables only inside disclosures or at 900px
// or wider). The summary names the first columns and counts the rows. Input is md() output, already escaped.
function mdTables(html) {
  const wide = !!(window.matchMedia && matchMedia('(min-width: 900px)').matches);
  return String(html == null ? '' : html).replace(/<div class="tbl"><table>([\s\S]*?)<\/table><\/div>/g, (m, inner) => {
    const th = [];
    inner.replace(/<th\b[^>]*>([\s\S]*?)<\/th>/g, (x, c) => { const t = c.replace(/<[^>]*>/g, '').trim(); if (t) th.push(t); return x; });
    const n = ((inner.split('<tbody>')[1] || '').match(/<tr\b/g) || []).length;
    const cols = th.slice(0, 3).join(' · ') + (th.length > 3 ? ' …' : '');
    return '<details class="disc mdt"' + (wide ? ' open' : '') + '><summary><span class="mdt-s">Table' + (cols ? ': ' + cols : '') + '</span>'
      + '<span class="sub">' + n + (n === 1 ? ' row' : ' rows') + '</span></summary><div class="body">' + m + '</div></details>';
  });
}
const PLAYING = new Set();
function setPlay(key, on) { if (on) PLAYING.add(key); else PLAYING.delete(key); HTML.classList.toggle('play', PLAYING.size > 0); }
let toastT = 0;
function toast(html, opts) {
  const el = $('#toast'); if (!el) return;
  el.innerHTML = html; el.classList.add('on');
  clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('on'), (opts && opts.ms) || 4000);
}

// ============================================================================================ tips ==
// One bubble for every tip (COMMAND_CENTER_SPEC §3.11). A tap, a click or keyboard focus opens it; a mouse resting
// 250 ms on a tipped label opens it; on touch a long press (450 ms) opens it. A label inside a link or another control
// never takes that control's click: only hover or a long press shows its tip, and the tap that ends a long press (or
// the next tap, which just closes the bubble) is swallowed. Escape, a scroll, an outside tap or the mouse leaving
// closes it. role=tooltip plus aria-describedby on the trigger; the "?" buttons read "What is <term>?" and have a 44px
// hit area (mission.js). tipBy: 'hover' | 'click' | 'focus' | 'press'.
let tipbox = null, tipEl = null, tipAt = 0, tipQuiet = null, tipBy = '', tipSig = '';
let hovEl = null, hovT = 0, prT = 0, pr = null, prUp = false, prDown = 0;
function tipFocus(el) { if (!el || !el.isConnected) return; tipQuiet = el; try { el.focus({ preventScroll: true }); } catch (e) {} if (document.activeElement !== el) tipQuiet = null; }
const TIPSEL = '.tip,[data-tip],[data-g],[data-tip-cursor],[data-tk]';
// A label inside one of these (or a control carrying a tip itself) leaves the click to the control.
const TIPACT = 'a[href],button,summary,label,input,select,textarea,[data-health],[data-sheet],[data-cursor],[data-cycle],[data-name],[data-pos],[data-trade]';
const tipOwn = el => el.matches('.tip,[data-g],[data-tip-cursor],button[data-tip]') || !el.closest(TIPACT);
const focusVis = el => { try { return el.matches(':focus-visible'); } catch (e) { return true; } };
const sigOf = el => ((el.closest('[id]') || {}).id || '') + '|' + (el.dataset.tk || el.dataset.tip || el.dataset.g || '');
function tipHtml(el) {
  if (typeof el._tip === 'function') return el._tip(el);
  if (typeof el._tip === 'string') return el._tip;
  let h = '';
  if (el.dataset.tip) h = esc(el.dataset.tip);
  else if (el.dataset.tk) h = tipText(el.dataset.tk, el);
  else if (el.dataset.g) { const g = gloss(el.dataset.g); if (g) h = '<b class="tipt">' + esc(g.t) + '</b>' + esc(g.d); }
  if (el.dataset.tipCursor != null) h += '<div><button type="button" class="btn small" data-cursor="' + esc(el.dataset.tipCursor) + '">Replay this check ›</button></div>';
  return h;
}
function showTip(el, html, by) {
  if (!el) return;
  const h = html != null ? html : tipHtml(el); if (!h) return;
  if (!tipbox) { tipbox = document.createElement('div'); tipbox.className = 'tipbox glass'; tipbox.id = 'tipbox'; tipbox.setAttribute('role', 'tooltip'); document.body.appendChild(tipbox); }
  if (tipEl && tipEl !== el) tipEl.removeAttribute('aria-describedby');
  tipbox.innerHTML = h; tipEl = el; tipAt = performance.now(); tipBy = by || 'click'; tipSig = sigOf(el);
  el.setAttribute('aria-describedby', 'tipbox');
  const r = el.getBoundingClientRect(), vw = HTML.clientWidth || innerWidth;
  tipbox.style.left = '0px'; tipbox.style.top = '0px'; tipbox.classList.add('on');
  const w = tipbox.offsetWidth, ht = tipbox.offsetHeight;
  const x = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, vw - w - 8));
  let y = r.bottom + 8; if (y + ht > innerHeight - 8) y = Math.max(8, r.top - ht - 8);
  tipbox.style.left = x + 'px'; tipbox.style.top = y + 'px';
}
function hideTip() {
  if (tipbox) tipbox.classList.remove('on');
  if (tipEl) tipEl.removeAttribute('aria-describedby');
  tipEl = null; tipBy = ''; tipSig = '';
}
// A redraw replaced the trigger (a tile's 30 s repaint): follow it to its replacement, with fresh words, or close.
function retip() {
  if (!tipEl || tipEl.isConnected) return;
  const s = tipSig, n = s ? $$(TIPSEL).find(x => sigOf(x) === s) : null;
  if (n) showTip(n, null, tipBy); else hideTip();
}
function pressOpen() { if (!pr || !pr.el.isConnected) return; pr.on = true; prDown = 0; showTip(pr.el, null, 'press'); }
function initTips() {
  document.addEventListener('click', e => {
    const t = e.target; if (!(t instanceof Element)) return;
    if (tipbox && tipbox.contains(t)) return;                    // a button inside the tip acts; the shell then closes it
    const el = t.closest(TIPSEL), act = t.closest(TIPACT);
    if (el && tipOwn(el) && !(act && act !== el && el.contains(act))) { e.preventDefault(); if (tipEl === el && tipBy !== 'hover' && performance.now() - tipAt > 350) hideTip(); else showTip(el, null, 'click'); return; }
    if (tipEl) hideTip();
  });
  // Touch: a long press shows the tip. The tap that ends it, and the next tap outside the bubble, only close or keep it.
  addEventListener('pointerdown', e => {
    prUp = false; clearTimeout(prT); pr = null;
    const t = e.target instanceof Element ? e.target : null, inBox = !!(t && tipbox && tipbox.contains(t));
    prDown = tipEl && tipBy === 'press' && !inBox ? performance.now() : 0;
    const el = e.pointerType !== 'mouse' && t && !inBox ? t.closest(TIPSEL) : null;
    if (el) { pr = { el, x: e.clientX, y: e.clientY, on: false }; prT = setTimeout(pressOpen, 450); }
  }, true);
  addEventListener('pointermove', e => { if (pr && !pr.on && Math.abs(e.clientX - pr.x) + Math.abs(e.clientY - pr.y) > 12) { clearTimeout(prT); pr = null; } }, { capture: true, passive: true });
  addEventListener('pointerup', () => { clearTimeout(prT); if (pr && pr.on) prUp = true; pr = null; }, true);
  addEventListener('pointercancel', () => { clearTimeout(prT); if (pr && pr.on) prUp = true; pr = null; prDown = 0; }, true);
  addEventListener('contextmenu', e => { if (pr) { e.preventDefault(); if (!pr.on) { clearTimeout(prT); pressOpen(); } } else if (tipEl && tipBy === 'press') e.preventDefault(); }, true);
  addEventListener('click', e => {
    if (prUp) { prUp = false; e.preventDefault(); e.stopPropagation(); return; }
    if (prDown && performance.now() - prDown < 1500) { e.preventDefault(); e.stopPropagation(); hideTip(); }
    prDown = 0;
  }, true);
  // Mouse: rest 250 ms on a label (at once when moving from one tip to the next); leaving it closes a hover tip.
  document.addEventListener('pointerover', e => {
    if (e.pointerType !== 'mouse') return;
    const t = e.target instanceof Element ? e.target : null;
    if (t && tipbox && tipbox.contains(t)) { clearTimeout(hovT); return; }
    const el = t && t.closest(TIPSEL);
    if (el === hovEl) return;
    hovEl = el; clearTimeout(hovT);
    if (el) hovT = setTimeout(() => { if (hovEl === el && el.isConnected) showTip(el, null, 'hover'); }, tipEl && tipBy === 'hover' ? 60 : 250);
    else if (tipBy === 'hover') hovT = setTimeout(hideTip, 150);
  });
  document.addEventListener('pointerout', e => { if (e.pointerType === 'mouse' && !e.relatedTarget) { hovEl = null; clearTimeout(hovT); if (tipBy === 'hover') hideTip(); } });
  document.addEventListener('focusin', e => { const el = e.target instanceof Element && e.target.closest(TIPSEL); if (el && el === tipQuiet) { tipQuiet = null; return; } if (el && !(tipbox && tipbox.contains(el)) && focusVis(el)) showTip(el, null, 'focus'); });
  document.addEventListener('focusout', () => { if (tipEl && (tipBy === 'focus' || tipBy === 'click')) setTimeout(() => { const a = document.activeElement; if (tipEl && (tipBy === 'focus' || tipBy === 'click') && a !== tipEl && !(tipbox && tipbox.contains(a))) hideTip(); }, 0); });
  document.addEventListener('keydown', e => {
    if (!tipEl) return;
    const a = document.activeElement, inBox = !!(tipbox && a && tipbox.contains(a));
    // Keyboard reach into a tip that holds buttons ("Replay this check ›"): Tab from its trigger moves into the tip;
    // Escape, or Tab out of either end, returns to the trigger without reopening it.
    const fs = tipbox ? $$('button,a[href]', tipbox) : [];
    if (e.key === 'Escape') { e.preventDefault(); const el = tipEl; hideTip(); if (inBox) tipFocus(el); return; }
    if (e.key !== 'Tab' || !fs.length || tipEl.closest('.dl')) return;
    if (a === tipEl && !e.shiftKey) { e.preventDefault(); fs[0].focus(); return; }
    if (inBox && ((!e.shiftKey && a === fs[fs.length - 1]) || (e.shiftKey && a === fs[0]))) { e.preventDefault(); const el = tipEl; hideTip(); tipFocus(el); }
  });
  addEventListener('scroll', () => { if (tipEl) hideTip(); }, { passive: true, capture: true });
  addEventListener('resize', () => { if (tipEl) hideTip(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden && tipEl) hideTip(); });
}

// ================================================================================== the tip words ==
// One plain-language dictionary for every title and label the owner may wonder about (COMMAND_CENTER_SPEC §3.11), so
// a word always gets the same explanation. An element carries data-tk="key" or "key:arg" (hint() writes it); the words
// are built when the bubble opens, so a time in them is never stale. An entry is [title, text] or fn(arg, el) →
// [title, text] | null. Words first; R and % of pot only, never money. The bot a tip is about: its arg, else the
// nearest [data-id] (a master tile), else this page's bot.
function hint(k, arg, focus) { return ' data-tk="' + esc(k + (arg == null || arg === '' ? '' : ':' + arg)) + '"' + (focus ? ' tabindex="0"' : ''); }
function tipText(spec, el) {
  const s = String(spec), i = s.indexOf(':'), k = i < 0 ? s : s.slice(0, i);
  let v = TIP[k];
  try { if (typeof v === 'function') v = v(i < 0 ? '' : s.slice(i + 1), el); } catch (e) { report(e, 'tip ' + k); v = null; }
  return !v ? '' : '<b class="tipt">' + esc(v[0]) + '</b>' + esc(v[1]);
}
function tipRow(arg, el) { const h = el && el.closest ? el.closest('[data-id]') : null; return rowOf(arg || (h && h.dataset.id) || AGENT); }
const onPage = A => PAGE === 'bot' && !!S.b && (!A || A.id === AGENT);
const tipBar = A => onPage(A) ? barOf(S.b) : (A && (num(A.bar_s) || TF[A.tf])) || null;
const R1 = 'R is the amount this bot planned to risk on one trade: +1 R means it won what it risked.';
// A status word for one bot, with its own times.
function stTip(st, b, A) {
  if (!st) return null;
  const K = st.K || {}, T = fmt.when, ev = barw(b ? barOf(b) : tipBar(A) || BAR, 1);
  const d = {
    ok: 'It checks the market ' + ev + '. Its last check' + (K.lastT != null ? ' (' + fmt.ago(K.lastT) + ')' : '') + ' ran on time.' + (K.next != null ? ' Next check about ' + T(K.next) + '.' : ''),
    due: 'Its ' + T(K.C) + ' check should land any minute' + (K.rng ? ' (usually ' + K.rng[0] + '–' + K.rng[1] + ' min after)' : '') + '. Nothing is wrong unless it is still missing at ' + T(K.lateAt) + '.',
    late_now: 'Its ' + T(K.C) + ' check is past its ' + (K.lim || limOf(b)) + '-min limit, so this round’s buys are skipped. Sells are checked once it runs.',
    stale: 'No check for ' + fmt.age(K.age) + ', though it checks ' + ev + ', so these numbers may be out of date. The line beside it says whether the server is still running.',
    behind: st.pb ? 'It checked at ' + T(st.pb.ran) + ', but the dashboard did not get the new numbers' + (st.pb.pf ? ' (its update is failing)' : '') + ', so this page shows ' + T(st.shown) + '. The bot keeps running and trading.' : null,
    exits: 'It holds coins, but no check since ' + T(K.lastT) + ' has looked at selling them.',
    failed: 'Its last check stopped partway, so its sells may not have been checked.',
    halt: 'Buying is off, set by you or the fleet kill switch. It still sells when its rules say so.',
    thr_halt: 'The pot fell to its safety limit below its best point, so buying stopped until reviewed. Sells still run.',
    thr_half: 'The pot is far enough below its best point that new trades risk half as much until it recovers.',
    late: 'Its last check started too late, on old prices, so it skipped buying that round. Sells still ran.',
    fallback: 'Live trading was asked for, but something it needs is missing, so it still trades on paper.',
    unhedged: 'In one pair the coin and its short bet differ in size, so price moves no longer cancel. It evens them within a few hours.',
    exit_slow: 'A pair it is closing is taking longer than usual.',
    none: 'It hasn’t run its first check yet.',
    v1: 'It hasn’t sent its schedule yet; its on-time status shows after its next check.',
  }[st.k];
  return [st.word, d || (st.lvl === 'bad' ? 'It raised a problem. Open the bot to see it.' : 'It raised a note worth a look. Open the bot for details.')];
}
const VTIP = {
  ok: ['All clear', 'Every bot checked in on time and nothing needs you.'],
  mute: ['Waiting', 'No bot has sent its schedule yet; this fills in after their next checks.'],
  info: ['Due', 'A check is due any minute. Nothing is wrong yet.'],
  warn: ['Watch', 'Something is worth a look but not urgent, like a late check. The line beside it names the bot.'],
  bad: ['Needs you', 'A bot has a problem that won’t fix itself, like a failed check or a halt. Open it to see what to do.'],
};
function capTip() {
  const c = capState(), net = { signedout: 'Your session ended. Tap to sign in again.', offline: 'Can’t reach the dashboard; the numbers are from the last time it could.', checking: 'Fetching the latest data.' }[S.net];
  if (net) return [c.word, net];
  let v = null;
  if (PAGE === 'fleet') { const f = S.E && typeof COMP.fleetSummary === 'function' ? safe(() => COMP.fleetSummary(), 'Fleet') : null; if (isObj(f) && VTIP[f.lvl]) v = [c.word, VTIP[f.lvl][1]]; }
  else if (S.b) v = stTip(S.st || status(S.b), S.b, rowOf(AGENT));
  return v ? [v[0], v[1] + ' Tap for the health details.'] : [c.word, 'No readable data yet; the next check sends it.'];
}
const KTIP = {
  flip: 'It buys a coin when its trend signal fires and every safety check passes, and sells when the trend turns or its stop is hit.',
  target: 'It keeps a set mix of coins and adjusts it at each check, instead of trading single signals.',
  carry: 'It holds a coin plus an equal short bet on it, so price moves mostly cancel, and earns the funding fees traders pay.',
};
// An arena bot's day in its trial, counted live from its enrolment date (the lab's snapshot only as a fallback), and the
// trial's length from the lab's not_ready sentence.
function arenaDays(id) {
  const s = fxCache && Array.isArray(fxCache.shortlist) ? fxCache.shortlist.find(x => x && x.agent === id) : null, A = rowOf(id);
  const m = s && /(\d+)\s+of\s+(\d+)\s+days/.exec(String(s.not_ready || '')), e = A && isObj(A.arena) && /^(\d{4})-(\d\d)-(\d\d)/.exec(String(A.arena.enrolled || ''));
  const d = e ? (nowS() - Date.UTC(+e[1], e[2] - 1, +e[3]) / 1000) / 86400 : s && num(s.days);
  return { day: d != null ? Math.max(0, Math.floor(d)) : null, of: m ? m[2] : null };
}
const FXT = {
  '': ['Bot factory', 'The AiFi Lab, a separate program, designs and tests new bot recipes every night. This shows how many it tried and how few got through.'],
  tested: ['Tested', 'Every recipe tried so far: rules for when to buy and sell, replayed on about 8 years of past prices.'],
  cheap: ['Passed the quick check', 'A fast first screen: did it make money on past prices, with sensible risk?'],
  audit: ['Passed the full audit', 'A strict review: realistic costs, many market periods, and a test that the result isn’t luck.'],
  holdout: ['Passed the unseen final year', 'The lab hides the latest year of prices while it designs. A recipe gets one try to work on that year.'],
  arena: ['Trading in the arena', 'A recipe that passed everything trades on paper, no real money, for a trial of several weeks, and must keep matching its backtest.'],
  ready: ['Ready for you', 'Its paper trading was checked against its backtest (execution verified) and the evidence of an edge is strong. Going live is always your call; nothing switches by itself.'],
  last: ['Nightly batch', 'The lab’s latest nightly batch: new recipes tested, and how many passed every check.'],
  fam: ['By strategy type', 'The kinds of idea the lab tests: recipes tried and passed for each.'],
  study: ['Research', 'A bigger experiment to learn which ideas are worth testing. A study, not a bot.'],
};
// Strategy families the lab tests: [plain name, what it does]. An id not listed reads as its own words.
const FAM = {
  rs_rotation: ['Strongest-coins rotation', 'Holds the few coins that rose most in recent weeks, swapping as the ranking changes.'],
  tsmom: ['Trend: price vs N days ago', 'Holds a coin while its price is above where it was a set number of days ago.'],
  sma_trend: ['Trend: price vs its average', 'Holds a coin while its price is above its recent average.'],
  dual_ma: ['Two-average crossover', 'Buys when a short average price crosses above a longer one; sells when it crosses back.'],
  donchian: ['Breakout to new highs', 'Buys when a coin breaks above its recent high; sells on a break below its recent low.'],
  cloud_trend: ['Momentum Cloud trend', 'Follows the Momentum Cloud trend line your signal traders use.'],
  meanrev: ['Buy the dip in an uptrend', 'Buys a short drop in a coin that is in a longer uptrend.'],
  carry: ['Funding collector', 'Holds a coin plus an equal short bet on it and collects funding fees.'],
  bull_momentum: ['Bull-market momentum', 'Buys the strongest coins, only while the whole market is rising.'],
};
function famName(id) { const f = FAM[id]; return f ? f[0] : cap1(String(id || '—').replace(/[_-]+/g, ' ')); }
const TIP = {
  st: (a, el) => {
    const A = tipRow(a, el);
    if (onPage(A)) return stTip(S.st || status(S.b), S.b, A);
    if (!A) return null;
    if (A.enabled === false) return TIP.retired;
    const b = rowBundle(A), t = num(A.last_t);
    return stTip(b ? status(b) : A.failed === true ? { k: 'failed', word: 'Failed', lvl: 'bad' } : A.halt === true || (S.E && S.E.fleet && S.E.fleet.halt) ? { k: 'halt', word: 'Halted', lvl: 'bad' }
      : { k: 'v1', word: t != null ? 'Checked ' + fmt.ago(t) : 'Waiting for its first check' }, b, A);
  },
  cap: capTip,
  verdict: l => VTIP[l],
  retired: ['Retired', 'Switched off; it no longer trades. Its record stays here.'],
  shadow: ['Shadow experiment', 'A recipe the lab failed (it missed the crash check), paper-traded anyway on your decision as an unofficial test. Paper only: it can never go live, and it is not in the arena, the shortlist or the fleet.'],
  wait: ['Waiting for its first check', 'On the roster but not reported yet. Its tile fills in after its first check.'],
  name: (a, el) => { const A = tipRow(a, el); return A && [A.name || A.id, A.desc || 'No description yet.']; },
  kind: (a, el) => {
    const A = tipRow(a, el), ki = onPage(A) ? kindInfo(S.b) : { kind: A && A.kind }, bar = tipBar(A), r = A && A.arena ? arenaDays(A.id) : null;
    return KTIP[ki.kind] && [KINDW[ki.kind], KTIP[ki.kind] + (bar ? ' It checks ' + barw(bar, 1) + '.' : '')
      + (r ? ' Arena: a new AiFi Lab bot on a ' + (r.of ? r.of + '-day ' : '') + 'paper trial' + (r.day != null ? ', on day ' + r.day : '') + '. It stays only while it matches its backtest.' : '')
      + (ki.inferred ? ' Type inferred from what it holds; confirmed after its next check.' : '')];
  },
  mode: a => ({ paper: ['Paper', 'It follows every rule on real prices but places no real orders: no real money, simulated results.'],
    live: ['Live', 'It places real orders with real money.'], ask: ['Paper (live requested)', 'Live trading was asked for, but something it needs is missing, so it is still on paper.'] })[a],
  modes: ['Paper and live', 'How many bots trade real money (live) and how many only simulate (paper).'],
  ret: ['Return', 'How much its pot grew or shrank since it started, in % of the pot. A paper pot is pretend.'],
  since: ['Since', 'The day it started on its current rules; the return counts from then.'],
  trades: ['Trades', 'Finished trades: bought, then sold. An open one counts once it closes.'],
  won: ['Won', 'Finished trades that made money after costs, out of all finished trades.'],
  holding: ['Holding', 'The coins it owns right now.'],
  ropen: ['Open R', 'Where the trades it still holds stand now. ' + R1],
  invested: ['Invested', 'The share of its pot in coins right now; the rest waits in cash.'],
  closed: ['Closed trades', 'Trades it has fully exited. A rebalancer trades rarely, so it is judged over a year (an arena bot over its trial), not by trade count.'],
  pairs: ['Pairs', 'Each pair is a coin plus an equal short bet on it, so price moves mostly cancel while it collects funding.'],
  kept: (a, el) => { const A = tipRow('', el), c = (onPage(A) ? S.b.carry_sum : A && A.carry) || {}; return ['Funding kept', 'The share of the funding it could earn that it kept after costs and timing, over every pair it ever held, closed ones included' + (c.capture_scope === 'open' ? ' (here only the open pairs: older closed pairs did not record it)' : '') + '. It needs ' + (num(c.gate_pct) ?? 80) + '% to go live; its first 2 weeks are too early to judge.']; },
  capuse: ['Capital in use', 'How much of the pot its pairs tie up. It can pass 100%: each pair counts the coin and the short.'],
  legs: ['Hedge result', 'What the coin and its short bet did not cancel out, over every pair: booked when legs were trimmed or a pair closed, plus the open legs at the last prices. With funding minus costs, it makes up the pot’s change.'],
  beads: (a, el) => {
    const bar = tipBar(tipRow('', el)), m = /^(\d+)\/(\d+)$/.exec(a);
    return ['Heartbeat', 'One dot per check' + (bar ? ' (' + barw(bar, 1) + ')' : '') + ', oldest left. Green on time, amber late, red failed; a magenta ring means it traded. A dashed empty dot was missed; the empty magenta dot is the next check.'
      + (m ? ' ' + m[1] + ' of the last ' + m[2] + ' ran on time.' : '')];
  },
  last: ['Last trade', 'The latest thing it bought or sold, and when. A magenta dot: within 24 hours.'],
  na: ['Not in this data', 'Not in the latest data; it fills in after the next check.'],
  bots: ['Bots', 'Bots running normally. Below: how many are late, failed or halted (stopped by a safety rule or by you).'],
  day: ['Last 24 h', 'Checks in the past day that ran on time, all bots together. Below: signals seen, and the buys and sells that followed.'],
  open: ['Open', 'Coins held now by the traders and rebalancers, then the funding pairs, counted apart (a pair is two positions).'],
  fleet: ['Fleet (paper)', 'All paper bots as one pretend pot: its change since each started, how far it is below its best point now (drawdown), and its worst drop. Worked out from every bot’s own pot at its latest check.'],
  kill: a => a === 'halt' ? ['Fleet halted', 'The fleet kill switch is on: no bot buys; sells still run.'] : a ? ['Fleet running', 'The fleet kill switch is off. If it trips, every bot stops buying but keeps selling.'] : ['Kill switch', 'Not in this data yet.'],
  market: ['Market', 'The AiFi Lab’s read of the crypto market: bull (rising), bear (falling) or crisis. Some bots buy only in a bull market.'],
  server: a => [a || 'Server', 'The always-on computer that runs the bots’ checks. A tick is it waking to run them, about hourly.'],
  next: ['Next check', 'Which bot checks the market next, with a live countdown.'],
  sort: a => ({ roster: ['Roster', 'Your bots in a fixed order; tiles never move on their own.'], attention: ['Needs attention', 'Bots with a problem first, then live before paper.'],
    return: ['Return', 'Best return since the start first.'], active: ['Most active', 'Most buys and sells in the last 24 hours first.'] })[a],
  log: ['What just happened', 'The latest trades and events of every bot, newest first. Tap one to open that bot’s log.'],
  fx: a => FXT[a],
  fam: a => [famName(a), (FAM[a] || [])[1] || 'A kind of recipe the lab added recently.'],
  sec: a => ({ record: ['Wins and losses', 'How its finished trades went, and whether its record is long enough to judge.'],
    traded: ['What it traded', 'Every buy, sell and adjustment, newest first.'],
    pace: ['How often', 'How regularly it checks and how often it trades; for a signal trader, how many signals passed its checks.'],
    holding: ['Holding now', 'What it owns now and, for a trader, where each safety exit (stop) sits.'],
    equity: ['Equity', 'Its pot over time; shaded is how far it fell below its best point (drawdown).'],
    health: ['Health and schedule', 'Whether its checks run on time, whether it may buy, and any warnings.'],
    strategy: ['Strategy and evidence', 'Its rules in brief and, for an arena bot, paper results against the backtest.'] })[a],
  wl: ['Won / lost', 'Finished trades that made money against those that lost, after costs.'],
  avg: ['Average trade', 'The average finished trade, in R and in % of the pot. ' + R1],
  best: ['Best / worst', 'Its best and worst finished trades, in R.'],
  nclosed: () => ['Closed trades', 'Finished trades. It needs ' + (num((cfgOf().gates || {}).n) || 'enough') + ' before its record can be judged for going live.'],
  openres: ['Open result', 'Where its holdings stand now, in % of the pot and in R.'],
  dd: ['Drawdown', 'How far the pot is below its best point. At the limits shown, risk halves, then buying stops.'],
  got: ['Collected', 'Funding earned so far in % of the pot, and what trading cost.'],
  result: ['Result', 'The pot’s change since it started, everything included.'],
  early: ['Too early', 'A fair verdict needs more trades or days. Until then the numbers are a first look, not proof.'],
  yearly: ['Judged yearly', 'A slow rebalancer can only be judged fairly over a full year.'],
  buying: ['Buying', 'Whether it may open new trades now. After a big drop its safety rules halve the risk, then stop buying.'],
  bt: ['Backtest vs paper', 'Backtest: the recipe replayed on past prices. Paper: how it does now on live prices, no real money. Close numbers mean it behaves as tested.'],
};

// =========================================================================================== theme ==
function setTheme(t) {
  HTML.dataset.theme = t;
  try { localStorage.setItem('aifi.theme', t); } catch (e) {}
  $$('meta[name=theme-color]').forEach(m => m.setAttribute('content', t === 'light' ? '#eef1f6' : '#0a0b0f'));
  runHooks('theme', t);
}
function initTheme() {
  document.addEventListener('click', e => { const b = e.target instanceof Element && e.target.closest('[data-theme-toggle]'); if (b) { e.preventDefault(); setTheme(isDark() ? 'light' : 'dark'); } });
  const mq = matchMedia('(prefers-color-scheme: light)'), f = () => { if (!HTML.dataset.theme) runHooks('theme', isDark() ? 'dark' : 'light'); };
  if (mq.addEventListener) mq.addEventListener('change', f); else if (mq.addListener) mq.addListener(f);
}

// ========================================================================================== sheets ==
let sheetStack = [], sheetFocus = null, sheetClean = null;
function sheetContent(kind, arg, el) {
  const f = SHEETS[kind];
  if (typeof f !== 'function') return { html: '<h2>Details</h2><div class="empty">This detail isn’t built yet.</div>' };
  let out; try { out = f(arg, el); } catch (e) { report(e, kind + ' sheet'); out = '<h2>Details</h2>' + broken(); }
  return typeof out === 'string' ? { html: out } : (out && typeof out === 'object' ? out : { html: '' });
}
// key = {kind, arg} makes the sheet refreshable on arrival. Opening over an open sheet keeps a "‹ Back" step;
// key.replace swaps it in place (cycle sheet previous/next), key.same redraws it keeping its scroll.
function openSheet(c, key) {
  const s = $('#sheet'), bg = $('#sheetbg'); if (!s) return;
  c = typeof c === 'string' ? { html: c } : (c || {});
  key = key || {};
  const open = s.classList.contains('on');
  const keep = key.same ? s.scrollTop : 0;
  if (open && S.sheet && key.kind && !key.back && !key.same && !key.replace) sheetStack.push(S.sheet);
  if (!open) { sheetStack = []; sheetFocus = document.activeElement; }
  if (typeof sheetClean === 'function') call(sheetClean);
  sheetClean = null;
  S.sheet = key.kind ? { kind: key.kind, arg: key.arg, at: key.at } : null;
  s.className = 'sheet glass' + (c.cls ? ' ' + c.cls : '') + (open ? ' on' : '');
  s.innerHTML = '<button class="btn icon x" id="sheetx" type="button" aria-label="Close">' + ICON.x + '</button>'
    + (sheetStack.length ? '<button class="btn small ghost" type="button" data-sheet-back>‹ Back</button>' : '') + (c.html || '');
  const h = $('h2', s); s.setAttribute('aria-label', h ? h.textContent.trim() : 'Details');
  s.setAttribute('tabindex', '-1');
  s.scrollTop = keep;
  const token = s._token = (s._token || 0) + 1;                   // a close in the same frame must win
  if (!open) requestAnimationFrame(() => { if (s._token === token) { s.classList.add('on'); if (bg) bg.classList.add('on'); try { s.focus({ preventScroll: true }); } catch (e) {} } });
  HTML.classList.add('noscroll');
  initSegs(s); stagger(s); masks(s);
  if (typeof c.after === 'function') { try { const r = c.after(s); if (typeof r === 'function') sheetClean = r; } catch (e) { report(e, (key.kind || 'sheet') + ' (after)'); } }
}
// A sheet remembers its trigger's data-at (the name sheet's "as at" run), so ‹ Back and an arrival redraw it the same.
const atOf = el => (el && el.dataset && el.dataset.at != null && el.dataset.at !== '' ? el.dataset.at : undefined);
const elOf = k => (k && k.at != null ? { dataset: { at: k.at } } : undefined);
function showSheet(kind, arg, el) { openSheet(sheetContent(kind, arg, el), { kind, arg, at: atOf(el) }); }
function sheetBack() { const p = sheetStack.pop(); if (p) openSheet(sheetContent(p.kind, p.arg, elOf(p)), { kind: p.kind, arg: p.arg, at: p.at, back: true }); }
function refreshSheet() {
  const s = $('#sheet'); if (!s || !S.sheet || !s.classList.contains('on')) return;
  openSheet(sheetContent(S.sheet.kind, S.sheet.arg, elOf(S.sheet)), { kind: S.sheet.kind, arg: S.sheet.arg, at: S.sheet.at, same: true });
}
function closeSheet() {
  const s = $('#sheet'), bg = $('#sheetbg'); if (!s) return;
  s._token = (s._token || 0) + 1;
  const was = s.classList.contains('on');
  if (typeof sheetClean === 'function') call(sheetClean);
  sheetClean = null; S.sheet = null; sheetStack = [];
  s.classList.remove('on'); if (bg) bg.classList.remove('on');
  HTML.classList.remove('noscroll');
  if (!was) return;
  setTimeout(() => { if (!s.classList.contains('on')) s.innerHTML = ''; }, 350);
  const f = sheetFocus; sheetFocus = null;
  if (f && f.isConnected && f !== document.body) try { f.focus({ preventScroll: true }); } catch (e) {}
}
// The default Health sheet (§9.5): status, punctuality, every alert with its action, the data's age, Refresh.
// A module may replace SHEETS.health; COMP.punctuality(b), when present, adds the punctuality strip.
SHEETS.health = function () {
  const b = S.b, x = ['<h2>Health</h2>'];
  if (!b) {
    x.push('<p class="note">' + (S.net === 'offline' ? 'Can’t reach the dashboard right now.' : S.net === 'signedout' ? 'Signed out.' : 'No data yet. The first check after deployment pushes it.') + '</p>');
    x.push('<div class="pn"><span></span><button class="btn small" type="button" data-refresh>Refresh</button></div>');
    return x.join('');
  }
  const st = S.st || status(b), K = st.K, s = stateOf(b), thr = s.thr || {}, m = modeOf(b), last = s.last || {};
  x.push('<p><span class="pill ' + ({ ok: 'ok', info: 'info', warn: 'warn', bad: 'bad' })[st.lvl] + '">' + esc(st.word) + '</span></p><p class="ink2">' + st.sentence + '</p>');
  x.push('<div class="sec"><h3>Punctuality</h3>' + (typeof COMP.punctuality === 'function' ? safe(() => COMP.punctuality(b), 'Punctuality') : '') + '<p class="note">' + esc(word.punct(b) || MISSING) + '</p></div>');
  x.push('<div class="sec"><h3>Alerts</h3>' + (st.items.length ? '<div class="alerts">' + st.items.map(i => banner(i.lvl, i.sentence, i.act)).join('') + '</div>' : '<p class="note">Nothing needs you.</p>') + '</div>');
  const thrW = { normal: 'Allowed', halved: 'Risk halved', halted: 'Stopped', unknown: 'unknown' }[thr.state] || 'unknown';
  const f = [];
  const lm = last.late_min != null ? last.late_min : (lastRun(b) || {}).lm;
  f.push(['Last check', st.pb ? esc(fmt.when(st.pb.ran)) + ' <span class="sub">(this page shows ' + esc(fmt.when(st.shown)) + ')</span>'
    : K.lastT != null ? esc(fmt.when(K.lastT)) + ' · ' + (last.failed ? '<span class="neg">stopped early</span>' + (lm != null ? ' (started ' + esc(lm) + ' min after the close)' : '') : esc(word.lag(lm, last.fresh))) : na()]);
  const PH = { countdown: ['On schedule', ''], due: ['Due now', 'due'], late: [K.exits ? 'Late, exits unchecked' : 'Late', 'late'], stale: ['Stale', 'stale'] }[K.phase];
  if (PH) f.push(['Clock', esc(PH[0]) + (PH[1] ? ' ' + tip(PH[1]) : '')]);
  if (K.C != null) {
    f.push(['Next ' + word.bar(b) + ' close', esc(fmt.when(K.C)) + ' <span class="sub">' + esc(fmt.utc(K.C)) + '</span>']);
    f.push(['Check expected', '≈ ' + esc(fmt.when(K.next)) + ' <span class="sub">' + esc(fmt.rel(K.next)) + '</span>']);
    f.push(['Buys skipped after', esc(fmt.when(K.lateAt))]);
  }
  f.push(['Mode', m.eff === 'live' ? 'Live' : m.eff === 'paper' ? 'Paper' : na()]);
  if (m.req && m.eff && m.req !== m.eff) f.push(['Requested', esc(m.req) + ' · ' + esc(m.note || 'live requirements missing')]);
  f.push(['Buying', esc(thrW) + (s.halt && s.halt.set ? ' · <span class="neg">halted</span>' : '')]);
  f.push(['Drawdown', thr.dd_pct != null ? esc(fmt.pctu(thr.dd_pct, 1)) : na()]);
  const gen = isoS(b.gen || b.generated);
  f.push(['Data pushed', gen != null ? esc(fmt.when(gen)) + ' <span class="sub" data-ago="' + gen + '">' + esc(fmt.ago(gen)) + '</span>' : na()]);
  if (st.pb) f.push(['Dashboard update', 'behind: checked ' + esc(fmt.when(st.pb.ran)) + ', shown ' + esc(fmt.when(st.shown))
    + (st.pb.pf ? ' · <span class="neg">failing</span>' + (num(st.pb.pf.since) != null ? ' since ' + esc(fmt.when(st.pb.pf.since)) : '') + (st.pb.pf.why ? ' <span class="sub">(' + esc(st.pb.pf.why) + ')</span>' : '') : '')]);
  if (b.diag && b.diag.unparsed) f.push(['Unread engine lines', esc(fmt.int(b.diag.unparsed))]);
  const tr = b.diag && isObj(b.diag.trim) ? b.diag.trim : null;   // the push kept exec:latest within 50 KB
  if (tr && (num(tr.dx) || num(tr.board))) f.push(['Trimmed to fit', esc([num(tr.dx) ? 'distances of the ' + word.plural(tr.dx, 'oldest check') : '', num(tr.board) ? word.plural(tr.board, 'older reading change') : ''].filter(Boolean).join(' · '))]);
  x.push('<dl class="facts">' + f.map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + v + '</dd>').join('') + '</dl>');
  x.push('<div class="pn"><span class="sub">A tap on the status also checks for new data.</span><button class="btn small" type="button" data-refresh>Refresh</button></div>');
  return x.join('');
};

// ================================================================== shell: capsule, mode, alerts ==
function banner(lvl, sentence, act) {
  const cls = lvl === 'bad' ? 'bad' : lvl === 'warn' ? 'warn' : 'info';
  let a = '';
  if (act && act.cycle != null) a = '<button type="button" class="act" data-cycle="' + esc(act.cycle) + '">' + esc(act.label) + '</button>';
  else if (act && act.href) a = '<a class="act" href="' + esc(act.href) + '">' + esc(act.label) + '</a>';
  return '<div class="banner ' + cls + '"><span class="ic">' + (cls === 'bad' ? ICON.bad : cls === 'warn' ? ICON.warn : ICON.info) + '</span><span class="bt">' + sentence + '</span>' + a + '</div>';
}
let capMemo = null, railMemo = null, alertMemo = null, modeMemo = null;
function capState() {
  if (S.net === 'signedout') return { dot: 'gap', cls: 'warn', word: 'Signed out', age: '', wide: '· tap to sign in' };
  if (S.net === 'checking') return { dot: 'mute', cls: 'mute', word: 'Checking…', age: '', wide: '' };
  if (S.net === 'offline') return { dot: 'mute', cls: 'mute', word: 'Offline', age: S.seenAt ? 'last seen ' + fmt.when(S.seenAt) : '', wide: '' };
  if (PAGE === 'fleet') {                                           // the master: the worst fleet level, from fleet.js
    if (!S.E) return S.bootErr ? { dot: 'gap', cls: 'warn', word: 'Data unreadable', age: '', wide: '' } : { dot: 'mute', cls: 'mute', word: 'Checking…', age: '', wide: '' };
    const f = typeof COMP.fleetSummary === 'function' ? safe(() => COMP.fleetSummary(), 'Fleet status') : null;
    return isObj(f) && f.cap ? f.cap : { dot: 'mute', cls: 'mute', word: word.plural((AGENTS || []).length, 'bot'), age: '', wide: '' };
  }
  if (!S.b) return S.bootErr === 'missing' ? { dot: 'mute', cls: 'mute', word: 'No data yet', age: '', wide: '' }
    : S.bootErr ? { dot: 'gap', cls: 'warn', word: 'Data unreadable', age: '', wide: '' } : { dot: 'mute', cls: 'mute', word: 'Checking…', age: '', wide: '' };
  const st = S.st || (S.st = status(S.b));
  return { dot: DOT[st.lvl], cls: LVCLS[st.lvl], word: st.word, age: st.age || '', wide: st.wide || '' };
}
function paintCapsule() {
  const c = capState(), cap = $('#capsule');
  if (cap) {
    // The capsule is the page's only live region. Its age is aria-hidden, so a ticking minute is never announced;
    // a change of word (a state change) is.
    const h = '<span class="dot ' + c.dot + '"></span><span class="cw">' + esc(c.word) + '</span>'
      + (c.age ? '<span class="ca" aria-hidden="true">' + esc(c.age) + '</span>' : '')
      + (c.wide ? '<span class="wide-only sub">' + esc(c.wide) + '</span>' : '');
    const cls = 'capsule' + (c.cls ? ' ' + c.cls : '');
    if (h !== capMemo) { cap.innerHTML = h; capMemo = h; }
    if (cap.className !== cls) cap.className = cls;
    if (!cap.dataset.tk) cap.dataset.tk = 'cap';
  }
  const rs = $('#railstat');
  if (rs) {
    const h = '<span class="dot ' + c.dot + '"></span><span class="txt"><b>' + esc(c.word) + '</b><span class="age">' + esc(c.age || '') + '</span></span>';
    const cls = 'status' + (c.cls === 'warn' || c.cls === 'bad' ? ' ' + c.cls : '');
    if (h !== railMemo) { rs.innerHTML = h; railMemo = h; }
    if (rs.className !== cls) rs.className = cls;
    if (!rs.dataset.tk) rs.dataset.tk = 'cap';
  }
}
function paintMode() {
  const el = $('#modepill'); if (!el) return;
  let cls, h;
  if (PAGE === 'fleet') {                                           // "6 paper" or "2 live · 4 paper" (§3.0), retired bots left out
    const on = (AGENTS || []).filter(r => r.enabled !== false), live = on.filter(r => r.mode === 'live').length, paper = on.filter(r => r.mode === 'paper').length;
    cls = live ? 'pill live' : paper ? 'pill pt' : 'pill mute';
    h = live || paper ? [live ? live + ' live' : '', paper ? paper + ' paper' : ''].filter(Boolean).join(' · ') : '—';
  } else {
    const e = modeOf(S.b).eff;
    cls = e === 'live' ? 'pill live' : e === 'paper' ? 'pill pt' : 'pill mute';
    h = e === 'live' ? 'Live' : e === 'paper' ? 'Paper<span class="wide-only"> · simulated</span>' : '—';
  }
  if (el.className !== cls) el.className = cls;
  if (h !== modeMemo || !el.firstChild) { el.innerHTML = h; modeMemo = h; }
  const tk = PAGE === 'fleet' ? 'modes' : 'mode:' + (modeOf(S.b).eff || '');
  if (el.dataset.tk !== tk) el.dataset.tk = tk;
}
// Alert rail (§4.1): bad items and the paper fallback on every tab, other warn items on Overview only; empty renders
// nothing. The master's rail (COMMAND_CENTER_SPEC §3.1) comes from fleet.js: a fleet halt, a runner that seems down.
function paintAlerts() {
  const el = $('#alerts'); if (!el) return;
  let h = '';
  if (PAGE === 'fleet') {
    const f = S.E && typeof COMP.fleetSummary === 'function' ? safe(() => COMP.fleetSummary(), 'Fleet alerts') : null;
    if (isObj(f) && Array.isArray(f.alerts)) for (const a of f.alerts) h += banner(a.lvl, a.html, a.act);
    if (S.net === 'offline' && S.E && S.seenAt) h += banner('info', 'Offline · showing ' + esc(fmt.when(S.seenAt)));
  }
  if (S.b && S.b.v !== 2) h += banner('info', 'Dashboard is newer than its data; some panels fill after the next check.');
  if (S.b && S.st) for (const i of S.st.items) if (i.lvl === 'bad' || i.k === 'fallback' || (i.lvl === 'warn' && S.tab === 'overview')) h += banner(i.lvl, i.sentence, i.act);
  if (h !== alertMemo) { el.innerHTML = h; alertMemo = h; }
}
function newestEv(b) { let n = 0; for (const e of (b && Array.isArray(b.events) ? b.events : [])) if (Array.isArray(e) && e[5] >= 1 && e[0] > n) n = e[0]; return n; }
function paintNewDot() {
  const on = !!S.b && S.tab !== 'activity' && newestEv(S.b) > (Number(lsGet('ex.seenEv', 0)) || 0);
  $$('a[data-tab=activity]').forEach(a => a.classList.toggle('new', on));
}
function markEvSeen() { const n = newestEv(S.b); if (n) lsSet('ex.seenEv', Math.max(n, Number(lsGet('ex.seenEv', 0)) || 0)); paintNewDot(); }
// One repaint of everything that shows the status engine; modules that show it too (the Overview verdict, the master's
// tiles) follow via hook('status'). On the master S.st stays null: fleet.js reads every row's status itself.
function refreshShell() { S.st = S.b ? status(S.b) : null; paintMode(); paintCapsule(); paintAlerts(); paintNewDot(); paintRoster(); runHooks('status', S.st); }
// The rail's mini roster (§3.0, §2.4): COMP.roster from fleet.js, on both pages once exec:agents has loaded.
let rosterMemo = null;
function paintRoster() {
  const el = $('#roster'); if (!el) return;
  const h = AGENTS && AGENTS.length && typeof COMP.roster === 'function' ? safe(() => COMP.roster(), 'Roster') : '';
  if (h !== rosterMemo) { el.innerHTML = h; rosterMemo = h; }
}

// ========================================================================================= routing ==
// Ported from ~/aifi/cloud/client.js route() 391 and the digit keydown 401, plus the redirects of the old tabs
// (COMMAND_CENTER_SPEC §2.3): Now → Overview, Positions → Overview › Holding now, #trades → Trades (#results).
const REDIRECT = { now: ['overview'], positions: ['overview', 'holding'], book: ['overview', 'holding'], trades: ['results'],
                   refused: ['activity', 'signals'], logic: ['rules'] };
function parseHash() {
  if (PAGE !== 'bot') return { tab: PAGE, sub: null };
  const raw = (location.hash || '').slice(1);
  let h; try { h = decodeURIComponent(raw); } catch (e) { h = raw; }
  const parts = h.split('/');
  let tab = parts[0] || 'overview', sub = parts.slice(1).join('/') || null, moved = false;
  if (REDIRECT[tab]) { const r = REDIRECT[tab]; tab = r[0]; sub = r[1] || sub; moved = true; }
  if (!TABS.includes(tab)) { tab = 'overview'; sub = null; moved = !!raw; }
  if (moved) try { history.replaceState(null, '', '#' + tab + (sub ? '/' + sub : '')); } catch (e) {}
  return { tab, sub };
}
// Tab changes never add a history entry (§2.4), so Back always means "All bots".
function go(tab, sub) { navHash('#' + tab + (sub ? '/' + sub : '')); }
function navHash(h) {
  if (PAGE !== 'bot') return;
  try { history.replaceState(null, '', h); } catch (e) { location.hash = h; return; }
  route();
}
let viewTab = null, viewClean = null;
function placeholder(tab) { return '<div class="card rise"><div class="empty"><b>' + esc(TITLE[tab] || tab) + '</b> is not built yet. The status and alerts above are live.</div></div>'; }
function renderView(why) {
  const root = $('#view'); if (!root || !ready()) return;
  if (typeof viewClean === 'function') call(viewClean);
  viewClean = null;
  if (viewTab && viewTab !== S.tab && VIEWS[viewTab] && typeof VIEWS[viewTab].leave === 'function') call(VIEWS[viewTab].leave);
  viewTab = S.tab;
  const V = VIEWS[S.tab], name = TITLE[S.tab];
  if (!V || typeof V.render !== 'function') { root.innerHTML = placeholder(S.tab); stagger(root); return; }
  let out;
  try { out = V.render(root, why || 'route'); } catch (e) { report(e, name); out = broken(name); }
  if (typeof out === 'string') root.innerHTML = out;
  stagger(root); initSegs(root); masks(root);
  if (typeof V.after === 'function') { try { const r = V.after(root); if (typeof r === 'function') viewClean = r; } catch (e) { report(e, name + ' (after)'); } }
  retip();
}
// Re-render the open tab in place (a layout breakpoint crossed, a module's own state changed): keeps the scroll
// position and any open sheet; not an arrival, so nothing counts up and no card rises.
function redraw() { if (!ready()) return; const y = scrollY; renderView('redraw'); jump(y); }
function botName() { const r = rowOf(AGENT); return (r && r.name) || AGENT || ''; }
function paintTitle() {
  const h1 = $('#ttl');
  if (PAGE !== 'bot') { document.title = TITLE[PAGE] + ' · AiFi Executor'; return; }
  const n = botName(), tt = TITLE[S.tab] || (VIEWS[S.tab] && VIEWS[S.tab].title) || '';
  if (h1 && h1.textContent !== n) h1.textContent = n;                // §5.0: the h1 is the bot's name
  document.title = n + ' · ' + tt + ' · AiFi Executor';
}
function route() {
  const { tab, sub } = parseHash();
  S.tab = tab; S.sub = sub;
  $$('.rail nav a[data-tab], .tabbar a[data-tab]').forEach(a => { if (a.dataset.tab === tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  movePill();
  paintTitle();
  closeSheet(); hideTip();
  if (tab === 'activity') S.seenEv = Number(lsGet('ex.seenEv', 0)) || 0;
  paintAlerts();
  renderView('route');
  if (tab === 'activity' && S.b) markEvSeen(); else paintNewDot();
  runHooks('route', tab, sub);
  if (PAGE !== 'bot') return;                                       // fleet.js and lab.js place their own scroll
  const a = sub && document.getElementById(tab + '-' + sub);
  if (a) { if (a.tagName === 'DETAILS') a.open = true; into(a, false); holdAnchor(a); } else jump(0);
}
// A deep link lands while cards still rise and lazy panels (the ledger, a chart) fill in above it, which moves the
// section after the first scroll. Keep it 72px below the top for two seconds, measured from layout (offsetTop, which
// ignores the rise transform), and let go the moment the reader touches, scrolls, clicks or types.
let anchorT = 0;
function holdAnchor(el) {
  clearTimeout(anchorT);
  const EV = ['wheel', 'touchstart', 'pointerdown', 'keydown'], t0 = Date.now();
  const off = () => { clearTimeout(anchorT); anchorT = 0; EV.forEach(n => removeEventListener(n, off, true)); };
  EV.forEach(n => addEventListener(n, off, { capture: true, passive: true }));
  const top = () => { let y = 0; for (let e = el; e; e = e.offsetParent) y += e.offsetTop; return y - 72; };
  const tick = () => {
    if (!el.isConnected || Date.now() - t0 > 2000) return off();
    const y = Math.max(0, top()); if (Math.abs(scrollY - y) > 2) jump(y);
    anchorT = setTimeout(tick, 250);
  };
  anchorT = setTimeout(tick, 250);
}

// ======================================================================= polling and timers (§3.3) ==
const P = { t: 0, err: 0, busy: false, at: 0, due: 0, pull: 0, tok: 0, gaveUp: null };
// Bot page: every 60 s from 5 min before the expected check until it is stale, else every 10 min. Master (§3.10): every
// 60 s while any bot's clock is in [next − 5 min, lateAt + 10 min], else every 5 min. Both back off to 5 min after 3 errors.
function pollEvery() {
  if (P.err >= 3) return 300e3;
  const n = nowS();
  if (PAGE === 'fleet') {
    if (!S.E) return 60e3;
    const hot = (AGENTS || []).some(r => { if (r.enabled === false) return false; const b = rowBundle(r); if (!b) return false;
      const K = clock(b, n); return K.next != null && n >= K.next - 300 && n < K.lateAt + 600; });
    return hot ? 60e3 : 300e3;
  }
  if (!S.b) return 60e3;
  const K = clock(S.b, n); if (K.C == null) return 600e3;
  return n >= K.next - 300 && n < K.staleAt ? 60e3 : 600e3;
}
function schedulePoll(ms) {
  clearTimeout(P.t); P.t = 0;
  if (document.hidden) return;
  const d = Math.max(0, ms != null ? ms : pollEvery());
  P.due = Date.now() + d; P.t = setTimeout(() => poll(), d);
}
function nudgePoll() {                                             // the due window may have opened since the timer was set
  if (document.hidden || P.busy) return;
  const next = (P.at || Date.now()) + pollEvery();
  if (!P.t || P.due > next + 1000) schedulePoll(next - Date.now());
}
async function poll(user) {
  if (P.busy || S.booting || PAGE === 'lab') return;
  P.busy = true; clearTimeout(P.t); P.t = 0;
  if (user) { S.net = 'checking'; paintCapsule(); }
  try {
    if (PAGE === 'fleet') {                                         // the master reads one KV key: exec:agents
      const E = await getJSON('/api/agents', 10000);
      P.err = 0; S.net = 'ok'; S.seenAt = nowS();
      if (isObj(E) && (!S.E || E.gen !== S.E.gen || user)) landFleet(E);
      loadFactory();
    } else {
      const st = await getJSON(api('/api/stamp'), 10000);
      P.err = 0; S.net = 'ok'; S.seenAt = nowS(); S.stamp = isObj(st) ? st : null;     // a failed push's stamp says why (status)
      if (st && st.gen && !st.err && (!S.b || st.gen !== S.b.gen) && P.gaveUp !== st.gen) await pull(st.gen, 0);
    }
  } catch (e) {
    if (e && e.kind === 'auth') S.net = 'signedout';
    else { P.err++; S.net = e && e.kind === 'net' ? 'offline' : (S.net === 'checking' ? 'ok' : S.net); }
  }
  P.at = Date.now(); P.busy = false;
  if (S.b) S.st = status(S.b);
  paintCapsule(); paintAlerts();
  if (S.sheet && (S.sheet.kind === 'health' || S.sheet.kind === 'fleethealth')) refreshSheet();
  schedulePoll();
}
function newer(nb) { return !S.b || (!!nb.gen && nb.gen !== S.b.gen && (!S.b.gen || nb.gen > S.b.gen)); }
async function pull(gen, tries) {
  const tk = ++P.tok; clearTimeout(P.pull); P.pull = 0;
  let nb;
  try { nb = await getJSON(api('/api/latest'), 10000); }
  catch (e) { if (e && e.kind === 'auth') S.net = 'signedout'; else if (e && e.kind === 'net') S.net = 'offline'; return; }
  if (tk !== P.tok || !nb || typeof nb !== 'object' || Array.isArray(nb)) return;
  if (newer(nb)) land(nb);
  if (nb.gen === gen) return;
  if (tries >= 3) { P.gaveUp = gen; return; }                       // KV propagation: up to 3 retries, 20 s apart
  if (!document.hidden) P.pull = setTimeout(() => pull(gen, tries + 1), 20e3);
}
// A new bundle landed: re-render in place (scroll position and any open sheet kept), then the arrival hook plays.
// The bot's exec:agents row is reloaded after it (the roster, the prev/next order, the row's extras).
function land(nb) {
  if (!S.b) { S.bootErr = null; return start(nb); }
  const prev = S.b; S.prev = prev; S.b = nb; BAR = barOf(nb);
  refreshShell();
  const y = scrollY;
  renderView('arrival');
  jump(y);
  refreshSheet();
  if (S.tab === 'activity') markEvSeen();
  runHooks('arrival', prev, nb);
  loadAgents();
}
// A new exec:agents envelope landed on the master: fleet.js updates its tiles in place (they never reorder here).
function setFleet(E) { S.E = E; AGENTS = Array.isArray(E.agents) ? E.agents.filter(isObj) : []; }
function landFleet(E) {
  if (!S.E) { S.bootErr = null; setFleet(E); runHooks('agents', AGENTS, S.E); return start(null); }
  S.prevE = S.E; setFleet(E);
  refreshShell();
  const y = scrollY;
  renderView('arrival');
  jump(y);
  refreshSheet();
  runHooks('agents', AGENTS, S.E);
}
// The 1 s tick runs only while a registered element is on screen and the page is visible (the Next-check ticker).
const ONE = []; let io1 = null, T1 = 0;
function every1s(el, fn) {
  if (!el || typeof fn !== 'function') return;
  const ent = { el, fn, on: !('IntersectionObserver' in window) };
  ONE.push(ent);
  if ('IntersectionObserver' in window) {
    io1 = io1 || new IntersectionObserver(es => { for (const e of es) for (const x of ONE) if (x.el === e.target) x.on = e.isIntersecting; sync1s(); });
    io1.observe(el);
  }
  sync1s();
}
function sync1s() {
  for (let i = ONE.length - 1; i >= 0; i--) if (!ONE[i].el.isConnected) { if (io1) io1.unobserve(ONE[i].el); ONE.splice(i, 1); }
  const want = !document.hidden && ready() && (ONE.some(x => x.on) || hooksOf('tick1s').length > 0);
  if (want && !T1) T1 = setTimeout(() => { tick1(); if (T1) T1 = setInterval(tick1, 1000); }, 1000 - (Date.now() % 1000) + 5);
  else if (!want && T1) { clearInterval(T1); T1 = 0; }
}
function tick1() { sync1s(); if (!T1) return; for (const x of ONE) if (x.on) call(x.fn); runHooks('tick1s'); }
let T30 = 0;
function tick30() {
  if (!ready()) return;
  refreshShell();
  $$('[data-ago]').forEach(el => { const t = Number(el.dataset.ago); if (!isFinite(t)) return; const a = fmt.ago(t); if (el.textContent !== a) el.textContent = a; });
  runHooks('tick30s');
  retip(); nudgePoll(); sync1s();
}
function startTimers() {
  stopTimers();
  if (document.hidden || !ready()) return;
  T30 = setTimeout(() => { tick30(); if (T30) T30 = setInterval(tick30, 30000); }, 30000 - (Date.now() % 30000) + 50);
  sync1s();
}
function stopTimers() { clearInterval(T30); T30 = 0; if (T1) { clearInterval(T1); T1 = 0; } }
function onVis() {
  if (document.hidden) {
    HTML.classList.add('hid');
    stopTimers(); clearTimeout(P.t); P.t = 0; clearTimeout(P.pull); P.pull = 0;
    runHooks('hide');
  } else {
    HTML.classList.remove('hid');
    if (ready()) { tick30(); startTimers(); }
    runHooks('show');
    poll();
  }
}

// ==================================================================================== boot + shell ==
function bootCard(title, text, btn) {
  return '<div class="card rise"><div class="empty"><h2 style="color:var(--ink);font-size:var(--fs-lg);margin-bottom:6px">' + esc(title) + '</h2>'
    + '<p style="margin:0 0 12px">' + esc(text) + '</p>' + (btn || '') + '</div></div>';
}
// The words that name this bot's bar in the shared vocabulary (gate labels, the flip). Exit codes name their own
// timeframe (h1 hourly, h4 4-hour, d daily): on an hourly bot "h4" is its 4-hour gate turning, so it is never renamed.
function barWords() {
  const w = word.bar();
  STAGE.n.w = cap1(w) + ' not ready';
  GATES[4].label = cap1(w) + ' signal';
  KIND.flip[1] = w + ' flip';
}
async function boot() {
  if (S.booting) return;
  S.booting = true; S.net = 'checking'; paintCapsule();
  if (PAGE === 'fleet') return bootFleet();
  if (PAGE === 'lab') { S.booting = false; S.net = 'ok'; return start(null); }
  // The bot page reads its exec:agents row in parallel: barOf() falls back to the row's tf for an older bundle.
  const ag = loadAgents();
  let b = null, err = null;
  try { b = await getJSON(api('/api/latest'), 10000); if (!b || typeof b !== 'object' || Array.isArray(b)) err = { kind: 'parse' }; }
  catch (e) { err = e && e.kind ? e : { kind: 'net' }; }
  await ag;
  S.booting = false;
  if (err) return bootFail(err);
  S.net = 'ok'; S.seenAt = nowS(); S.bootErr = null; P.err = 0; P.at = Date.now();
  start(b);
}
async function bootFleet() {
  loadFactory();
  const v = $('#view');
  if (v && typeof COMP.fleetLoading === 'function') v.innerHTML = safe(() => COMP.fleetLoading(), 'Loading');
  let E = null, err = null;
  try { E = await getJSON('/api/agents', 10000); if (!isObj(E)) err = { kind: 'parse' }; }
  catch (e) { err = e && e.kind ? e : { kind: 'net' }; }
  S.booting = false;
  if (err && err.kind === 'missing') { E = { v: 1, agents: [] }; err = null; }   // no bot has reported: the empty state
  if (err) return bootFail(err);
  S.net = 'ok'; S.seenAt = nowS(); S.bootErr = null; P.err = 0; P.at = Date.now();
  setFleet(E);
  runHooks('agents', AGENTS, S.E);
  start(null);
}
function start(b) {
  if (PAGE === 'bot') { S.b = b; S.prev = null; BAR = barOf(b); barWords(); }
  refreshShell();
  route();
  startTimers(); schedulePoll();
}
async function bootFail(e) {
  const v = $('#view'), retry = '<button class="btn" type="button" data-retry>Retry</button>';
  let h;
  S.bootErr = e.kind;
  if (e.kind === 'auth') { S.net = 'signedout'; h = bootCard('Signed out', 'Your session ended. Sign in again to see the executor.', '<a class="btn primary" href="/login">Sign in</a>'); }
  else if (e.kind === 'net') { S.net = 'offline'; h = bootCard('Can’t reach the dashboard', 'Check the connection, then try again.', retry); }
  else if (PAGE === 'fleet') { S.net = 'ok'; h = bootCard('The fleet data couldn’t be read', 'The next check pushes a fresh copy.', retry); }
  else if (e.kind === 'missing') { S.net = 'ok'; h = bootCard('No data yet', 'This bot appears after its first check.', '<a class="btn" href="/" data-back>All bots</a>'); }
  else {
    S.net = 'ok';
    let when = '';
    try { const st = await getJSON(api('/api/stamp'), 5000); const g = isoS(st && st.gen); if (g != null) when = ' (pushed ' + fmt.when(g) + ')'; } catch (_) {}
    h = bootCard('The latest data couldn’t be read' + when, 'The next check pushes a fresh copy.', retry);
  }
  if (v) { v.innerHTML = h; stagger(v); }
  paintCapsule(); paintAlerts();
  P.err++; P.at = Date.now(); schedulePoll();
}
const TRIGGERS = '[data-cursor],[data-health],[data-cycle],[data-name],[data-pos],[data-trade],[data-sheet]';
const mods = e => e.metaKey || e.ctrlKey || e.shiftKey || e.altKey;
function sheetOpen() { const s = $('#sheet'); return !!s && s.classList.contains('on'); }
function onClick(e) {
  if (e.defaultPrevented || e.button > 0) return;
  const t = e.target; if (!(t instanceof Element)) return;
  let el;
  if (t.closest('#sheetx')) return closeSheet();
  if (t.closest('[data-sheet-back]')) return sheetBack();
  if (t.closest('[data-retry]')) { e.preventDefault(); return boot(); }
  if (t.closest('[data-refresh]')) { e.preventDefault(); return poll(true); }
  if (t.closest('[data-top]')) { e.preventDefault(); return scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' }); }
  if ((el = t.closest('[data-back]')) && !mods(e)) { e.preventDefault(); return goFleet(); }
  // Bot → bot (the rail roster, a sheet's "Open") replaces this history entry, so Back still means "All bots" (§2.4).
  if (PAGE === 'bot' && (el = t.closest('a[href^="/?a="]')) && !el.target && !mods(e)) { e.preventDefault(); location.replace(el.href); return; }
  if ((el = t.closest(TRIGGERS))) {
    e.preventDefault(); hideTip();
    const d = el.dataset;
    if (d.cursor != null) return setCursor(d.cursor, { explicit: true, scroll: d.scroll != null });
    if (d.health != null) {
      if (S.net === 'signedout') { location.href = '/login'; return; }
      showSheet(PAGE === 'fleet' && typeof SHEETS.fleethealth === 'function' ? 'fleethealth' : 'health'); return poll(true);
    }
    if (d.cycle != null) { const n = Number(d.cycle); setCursor(n, { explicit: true, sheet: false }); return showSheet('cycle', n, el); }
    if (d.name != null) return showSheet('name', d.name, el);
    if (d.pos != null) return showSheet('pos', d.pos, el);
    if (d.trade != null) return showSheet('trade', d.trade, el);
    const i = d.sheet.indexOf(':');
    return i < 0 ? showSheet(d.sheet, undefined, el) : showSheet(d.sheet.slice(0, i), d.sheet.slice(i + 1), el);
  }
  if ((el = t.closest('.rail nav a[data-tab], .tabbar a[data-tab]')) && el.dataset.tab === S.tab && !S.sub) {
    e.preventDefault(); scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });       // tapping the open tab: back to the top
    return;
  }
  // Every same-page hash link on a bot page (tabs, status-item acts, in-page anchors) replaces the history entry (§2.4).
  if (PAGE === 'bot' && (el = t.closest('a[href^="#"]')) && !el.target && !mods(e)) { e.preventDefault(); navHash(el.getAttribute('href')); }
}
function onKey(e) {
  if (e.defaultPrevented) return;
  const field = e.target instanceof Element && e.target.closest('input,select,textarea,[contenteditable]');
  if (e.key === 'Escape') {
    if (tipEl) hideTip(); else if (sheetOpen()) closeSheet();
    else if (PAGE === 'bot' && !field && !mods(e)) { e.preventDefault(); goFleet(); }          // Esc returns to the fleet
    return;
  }
  if (mods(e) || e.isComposing || field || PAGE !== 'bot') return;
  const i = '1234'.indexOf(e.key);
  if (e.key.length === 1 && i >= 0) { e.preventDefault(); go(TABS[i]); return; }
  if (e.key === '[' || e.key === ']') { e.preventDefault(); botStep(e.key === ']' ? 1 : -1); }
}
function initShell() {
  addEventListener('hashchange', () => { if (PAGE === 'fleet') legacyHash(); else if (PAGE === 'bot') route(); });
  document.addEventListener('keydown', onKey);
  document.addEventListener('click', onClick);
  const bg = $('#sheetbg'); if (bg) bg.addEventListener('click', closeSheet);
  let rf = 0;
  addEventListener('resize', () => { cancelAnimationFrame(rf); rf = requestAnimationFrame(() => { initSegs(); movePill(); masks(); }); });
  document.addEventListener('scroll', e => { const el = e.target; if (el instanceof Element && el.matches(SCROLLERS)) maskOne(el); }, { capture: true, passive: true });
  document.addEventListener('toggle', e => { const d = e.target; if (d instanceof Element && d.matches('details') && d.open) masks(d); }, true);   // a table shown by a disclosure gets its edge fade
  document.addEventListener('visibilitychange', onVis);
  addEventListener('pageshow', e => { if (e.persisted) onVis(); });
  addEventListener('online', () => { if (!document.hidden) poll(); });
  addEventListener('offline', () => { S.net = 'offline'; paintCapsule(); paintAlerts(); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(movePill, () => {});
  if (document.hidden) HTML.classList.add('hid');
  hook('agents', () => { paintTitle(); paintRoster(); if (PAGE === 'fleet') paintMode(); });
  paintCapsule();
  route();
}
