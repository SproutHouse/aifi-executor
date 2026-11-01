# Dashboard v2 — build spec

_Synthesized 2026-09-25 from five audits, three proposals and a three-judge panel (winner: Mission control, with grafts from The Story). Source of truth for the dashboard rebuild._

# AiFi Executor dashboard v2: Mission control (final build spec)

## 0. Scope, sources and ground truth

**What this is.** The final spec, built on the judges' unanimous winner: Proposal 1, Mission control (verdict, cycle clock, Gate Run replay, On deck).

**Grafts from Proposal 3:**
- the moment row
- "Since you last looked"
- one shared cycle cursor
- board-change events
- event levels
- the Health sheet with a punctuality strip
- check lights that never invent passes
- lightweight-charts loaded lazily
- the template parser test

**Grafts from Proposal 2:**
- the flat pot dot-line
- the drawdown gauge with rule ticks
- slot pips
- "Too early · leading by 1.3 R" verdict pills
- the "Sold since you last looked" row
- stamp polling only inside the due window, with backoff
- a separate lazily fetched ledger payload

**Also covered.** Every judge must-fix and every HIGH audit finding (see §17).

**In this pass.** One focused implementation pass:
- `cloud/client.js`: rewritten, one file, vanilla, no build.
- `cloud/mission.js`: new; exports `MISSION_CSS`, appended after design.js CSS.
- `cloud/worker.js`: routes, HEAD, NAV, `md()` fix.
- `scripts/dashboard_push.py`: bundle v2 through an allowlist serializer.
- `scripts/control.py`: a 3-line `HALT.since` sidecar.
- `scripts/dashboard_demo.py`: new.
- Two test files and `docs/DASHBOARD.md`.

**Not in this pass.**
- Engine additions E1–E6 (data contract §10). The push reads those fields when they appear, so the page upgrades itself.
- Candle charts (`chart:<COIN>`).
- History archives.

**Deploys.** The pass ships in two deploys, so a half-migrated page can never look healthy while it is not:
- **Deploy 1, trust:** shell, status engine, capsule, banners, bundle v2, all five tabs in their basic form.
- **Deploy 2, replay:** Gate Run, dial, heartbeat, tape, cursor, arrival moment.

**Ground truth used in examples.** All figures were verified on disk. Times are in the phone's zone, America/Toronto (EDT).

- **Runs.** Wed 6:49 pm (169 min late) and Wed 10:12 pm (132 min late) skipped buys. The on-time runs are Thu 12:24 am, 4:21 am, 8:24 am, 12:20 pm, 4:20 pm, 8:27 pm and Fri 12:20 am. Their lags are 25, 21, 24, 21, 21, 27 and 20 min (median 21, range 20–27).
- **Per-name readings** exist from the Thu 12:20 pm run (16:20:54Z) onward. The UI never hard-codes this date; counts-only mode is chosen per run from `rd == null`.
- **Signals since start:** 8.
  - Blocked by a check: 3, all on volume. JUP 0.26× (Thu 12:24 am), LINK 0.73× (Thu 4:20 pm, the only auto grade), CRV 0.36× (Thu 8:27 pm).
  - Recorded, watch-only: 3. UNI and SOL (Thu 8:24 am), UNI (Thu 8:27 pm).
  - Proposed under the old model, then expired: 2. ETH and HYPE.
  - Name checks: 124.
- **Now (Fri 12:20 am readings):**
  - Could signal next: BTC +3.3%, ETH +4.4%, HYPE +8.1%.
  - Armed, too thin: AAVE +4.2% (volume 0.43×), BNB +3.4% (0.25×).
  - Already running: UNI (cushion 1.6%), SOL 3.8%, LINK 8.7%, CRV 5.7% (volume 0.38×, funding 68%/yr), CAKE 7.7% (0.06×), JUP 11.2% (0.37×).
  - Not set up: PENGU (weekly), JTO (daily), PUMP (daily).

---

## 1. Principles (apply to every component)

1. **Honest motion.** Something moves only for one of these reasons:
   - the real clock moved (countdown digits, the dial hand and arc, the due-phase pulse);
   - a recorded check arrived;
   - the owner asked (Replay, Step, Play, scrubbing).

   The only idle loops are the `.bg` drift (paused when hidden or while replaying) and the countdown digits. Every replay shows its recorded time on screen.
2. **Words first.** Every state is a word. Colour and glyph support the word and never replace it. Legends and `aria-label`s carry the words for dense cells.
3. **Only R and % of pot.** The bundle carries no pot-currency number, so the page cannot leak one. Coin prices appear only in sheets, captioned "market price, not your money".
4. **The phone's local time,** relative first ("4:21 am · in 2 h 13 m"). UTC appears only as a muted secondary where the bar schedule matters ("the 08:00 UTC close").
5. **One state vocabulary.** A single `STAGE` map (§12) gives each stage code its word, colour role, gate, tape cell and On deck group. It is used by the Gate Run chips, On deck, the tape, the heartbeat, All readings and the sheets.
6. **Magenta rule.** The magenta accent #f04ec2 appears in three tiers:
   - **Solid** (fill, ring, arc, hand): only "the bot acted" (bought, sold, stop raised) and the clock (progress arc, now hand, next bead, due countdown).
   - **Tint** (`--accent-soft`): "could act next" (armed names, the funnel bar at Bought).
   - **Text or 1px outline:** identity (active nav, `.tk` coin chips, "Auto grade" pill, LIVE pill).

   Green, amber and red mean health or risk only, and always travel with a word. Violet means PAPER only. Watch-only items are neutral ink-2, never violet.
7. **Glow rule (AiFi).** Only the big verdict status pill glows. Nothing else has a standing glow. On arrival, the existing `@keyframes pulse` plays once.
8. **Missing never becomes zero or normal.** A missing field renders "—" with a muted "not in this data". A missing throttle reads "unknown", not "normal".
9. **Never infer by absence without saying so.** Stopgap guesses are labelled as such, for example "signal · outcome not logged" and "held · no exit action logged".

---

## 2. Information architecture and shell

| key | Tab (hash) | Answers | Sections, in order |
|---|---|---|---|
| 1 | **Now** `#now` | Is it OK? Does it need me? How is it doing? What did it just do? What could it do next? | Alert rail · Mission card · Holding (only if held) · Pot (moves here once trades or positions exist) · Gate Run · On deck · Shakedown (while flat) · Latest |
| 2 | **Activity** `#activity` | What has it done, is it running, why didn't signals trade? | Heartbeat + punctuality line · Timeline · Signals · The board over time (tape) · All readings (disclosure) |
| 3 | **Positions** `#positions` | How is each position doing, and what could I lose? | Position cards · Risk budget · Books · Waiting for approval (legacy, only if any) |
| 4 | **Results** `#results` | Is it making money, is it beating holding, can it go live? | Verdict & go-live · Curve · Record strip · R per trade · Trades · Weekly review · Sweeps (if any) |
| 5 | **Rules** `#rules/<doc>` | What are the rules, and what does this word mean? | `.seg.quiet` nav: In force (default) · Glossary · the 9 docs · Log out (phone only) |

**Redirects.** `#overview`→`#now`, `#book`→`#positions`, `#trades`→`#results`, `#refused`→`#activity` (scrolls to Signals), `#logic/<doc>`→`#rules/<doc>`.

**NAV icons.** Defined in worker.js `NAV`, 24px, stroke 1.7, in the existing style.
- Now: pulse `M3 12h4l2-6 4 12 2-6h6`
- Activity: rail with dots `M6 5v14 M6 6h.01 M6 12h.01 M6 18h.01 M10 6h10 M10 12h10 M10 18h7`
- Positions: layers `M12 3l9 5-9 5-9-5z M3 13l9 5 9-5`
- Results: the existing trend icon
- Rules: the existing book icon

The tabbar shows a 6px accent-tint dot on Activity while events exist that are newer than `localStorage ex.seenEv`.

**Routing.** Port these from `~/SproutHouse/trading/aifi-desk/cloud/client.js`:

| Function | Line |
|---|---|
| `reduced` | 21 |
| `setSeg` | 311 |
| `initSegs` | 318 |
| `countUp` | 368 |
| `stagger` | 376 |
| `movePill` | 379 |
| `route` | 391 |
| digit `keydown` | 401 |

`route()` does the following:
1. Sets or removes `aria-current="page"` on `.rail nav a, .tabbar a`.
2. Calls `movePill()`: `transform: translateY(<offsetTop>px)`, sets the height, adds `.on`.
3. Calls `closeSheet()` and `hideTip()`.
4. Renders the tab.
5. Calls `scrollTo({top:0, behavior:'instant'})`.

Keys 1–5 switch tabs unless focus is in a field or a modifier is held. Escape closes the sheet or tip. `movePill` and `initSegs` rerun on resize.

**Topbar** (sticky glass, 52px):
- **Phone ≤640px:** `[Ex mark 28px → #now] [health capsule, flex:1] [mode pill] [theme ◐]`. The h1 tab title stays in the DOM with `.vh` (visually hidden). The "How it works" button is removed (that content lives in Rules).
- **Desktop:** `[h1 tab title] [capsule, long form] ··· [mode pill] [theme]`.
- "pushed X ago" is removed. It appears in the Health sheet only, and in the capsule only when the push trails the check by more than 10 min.
- The rail's status block mirrors the capsule (same dot class, word and age). The rail brand becomes a `div`, so the page has one h1. At 641–900px the rail labels use `.vh` instead of `display:none`.

**Mode pill.**
- PAPER: `.pill.pt` (violet), "Paper" on phone, "Paper · simulated" on desktop.
- LIVE: 1px accent-outline pill, "Live", with a static 6px accent dot.
- Red never means live.

---

## 3. Status engine, clock and refresh (one truth for the capsule, rail, verdict, alert rail and dial centre)

### 3.1 Clock model (client-side; never trusts a precomputed "next" time)

- `lastT = clock.last_t`
- `C = clock.last_slot + 14400`: the next 4-hour close the engine owes a check for.
- `lag = clock.lag_med_min` (21 today; 20 if fewer than 3 samples)
- `lim = cfg.late_min` (45)

| Phase | Window | Capsule | Level |
|---|---|---|---|
| countdown | now < C + lag | **On schedule · 27m** (age of the last check) | ok |
| due | C + lag ≤ now < C + lim | **Due now** | info |
| late | C + lim ≤ now < C + 4 h | **Late · 52m** | warn |
| late, positions held | C + 2 h ≤ now < C + 4 h and `risk.n_open > 0` | **Exits unchecked · 2h 10m** | bad |
| stale | now ≥ C + 4 h | **Stale · 9 h** | bad |

Every time is recomputed from `Date.now()`, never from a paused state.

### 3.2 Status precedence

`status(b, now)` returns `{lvl: ok|info|warn|bad, word, age, sentence, items[]}`. The first match sets the headline. Every match becomes an item in the alert rail and in the Health sheet.

| Level | Condition | Capsule word | Verdict sentence (template) |
|---|---|---|---|
| bad | `state.last.failed` | Failed | "**Needs you** · the 12:20 am check stopped early (ConnectionError). Exits may not have been checked." |
| bad | `state.halt.set` | Halted | "**Halted** since 3:12 pm: manual halt. No new buys; exits still run." (or "since unknown") |
| bad | `state.thr.state=='halted'` | Buying stopped | "**Buying stopped** · drawdown 20.4% reached the 20% limit." |
| bad | phase stale | Stale · 9 h | "**Stale** · no check for 9 h. The runner may be down." |
| bad | phase late with positions (≥ C + 2 h) | Exits unchecked | "**Needs you** · exits not checked since 8:20 pm." |
| bad | alert `recon`, `no_stop`, `close_failed`, `exit_failed` | Needs you | the alert's template sentence |
| warn | phase late | Late · 52m | "**Late** · no check yet for the 4:00 am close. After 4:45 am it skips buys." |
| warn | `mode.req != mode.eff` | Paper fallback | "**Live requested, running paper**: exchange key missing." (always also a banner) |
| warn | `state.last.fresh===false` | Ran late | "**Ran late** · the last check started 132 min after the close, so buys were skipped for that bar." |
| warn | `state.thr.state=='halved'` | Risk halved | "**Risk halved** · drawdown 11.2% (halves at 10%, stops at 20%)." |
| warn | other warn alerts (gap, entry_failed) | Check | the alert's sentence |
| info | phase due | Due now | "**Due now** · checks usually land 20–27 min after the close." |
| ok | none | On schedule · 27m | "**All clear** · nothing needs you." |

**Transport states override the capsule:**
- "Offline · last seen 1:02 am" (muted)
- "Signed out" (warn; a tap goes to /login)
- "Checking…" (only while a request is actually in flight)

### 3.3 Refresh loop and timers

**Boot.** `GET /api/latest` with a 10 s AbortController timeout. Failures branch:

| Failure | Card |
|---|---|
| 401 | "Signed out" + Sign in button |
| Network or timeout | "Can't reach the dashboard" + Retry |
| 404 | "No data yet. The first check after deployment pushes it." |
| 5xx or parse error | "The latest data couldn't be read (pushed <time>)" |

`b.v !== 2` shows a quiet info note: "Dashboard is newer than its data; some panels fill after the next check."

**Stamp polling** (`GET /api/stamp`, about 80 B):
- every 60 s while the page is visible and `C + 10 min ≤ now < C + 4 h`;
- every 10 min while visible otherwise (this catches control pushes such as halt or resume);
- immediately on `visibilitychange→visible`, on `pageshow` and on a capsule tap;
- after 3 consecutive errors, back off to 5 min.

**When `stamp.gen !== b.gen`:**
1. Fetch `/api/latest`.
2. If `latest.gen !== stamp.gen` (KV propagation), retry after 20 s, up to 3 times.
3. Re-render in place, keeping the scroll position and any open sheet.
4. Play the arrival moment (§13).
5. Refetch `/api/ledger` only if Results or Signals is open or next opened.

**Timers.**
- A **1 s tick** writes only the countdown text node, and only while the dial is on screen (IntersectionObserver).
- A **30 s tick** recomputes `status()`, the capsule, every `[data-ago]` node, the dial hand and arc, and On deck ages.
- **On `visibilitychange→hidden`,** all timers are cleared: countdown, 30 s tick, polling, Gate Run replay, tape Play. `html.hid` is set, which pauses `.bg`.
- **On visible,** everything is re-rendered from the real clock.

**Resilience.** Every section renders through `safe(fn, 'Section name')`. A throw draws a small `.empty` card, "This panel couldn't be drawn from this data", instead of blanking the tab.

---

## 4. Now tab (mission control)

### 4.1 Alert rail
- **Form:** a `.stack` (gap 8px) of `.banner.bad` / `.banner.warn` items. Each has a stroke icon, one sentence with a local time, and a right-aligned action link: "See check" (cycle sheet), "See position", "Runbook" (`#rules/operations`), "Signals".
- **Where it appears:** bad items and the paper-fallback warning appear at the top of **every** tab. Other warn items appear only on Now.
- **Empty:** nothing renders.

### 4.2 Mission card (`section.card.mission`, `container-type:inline-size`)

Children, in order:

**(a) Verdict**
- A `.pill.big` status word (the only glowing element) plus the sentence from §3.2, set at 17px/1.45.
- Meta line, 12.5px muted: "Last check 12:20 am · 20 min after the close".

**(b) Moment** (from P3; hidden if nothing reaches level 1 in 24 h)
- The highest-level event of the last 24 h (ties go to the most recent), plus a "since then" line built from the current `names[c]`.
- Clamped to 2 lines at 13.5px.
- Real example: "**Thu 4:20 pm · LINK** would have bought (auto grade), blocked: volume 0.73× the minimum. **Since then:** 4-hour still bullish, cushion 8.7%; volume now 1.12× the minimum."
- A tap sets the cursor to that run and scrolls to the Gate Run.

**(c) Since you last looked** (from P3, plus the P2 sold row)
- Keyed on `localStorage ex.seen = {t, at}`.
- Example: "Since Thu 5:05 pm: 3 new checks · 2 signals recorded (UNI, CRV) · nothing bought ›". The ›  opens the timeline at the "new" marker.
- When a position closed since then, the line "Sold since you last looked: LINK +2.10 R (4-hour turn)" is added.
- Hidden when nothing is new.
- First visit: "First look: 9 checks since Wed 6:49 pm."
- `ex.seen` updates once the newest cycle's Gate Run or Latest row has been in view for 3 s, or on tab hide.

**(d) Cycle clock dial** (inline SVG, `role="img"`)
- **Size:** viewBox `0 0 240 240`. `min(168px, 46vw)` on phones, 220px on desktop.
- **Face:**
  - track r=100, stroke `--glass-3`, width 12;
  - 24 hour ticks at r 86→90 in `--line-2`;
  - labels "12a 6a 12p 6p" in Plex Mono 10px muted;
  - local midnight at the top: `angle = localMinutes/1440·360 − 90`.
- **Beads** (r=9, no glyphs inside): each run of the last 24 h at its actual run time, plus one "next" bead at `C + lag`. Several runs in one slot merge into one bead with a count in its label.

  | Outcome | Fill | Ring |
  |---|---|---|
  | on time | `--good` | none |
  | ran late | `--warn` | none |
  | failed | `--bad` | none |
  | missed (slot with no run) | hollow, dashed `--muted` | none |
  | bought, sold or stop raised | its health fill | 2px solid accent |
  | next | hollow | 2px accent stroke; the pulse repeats every 2 s during the due phase only, never under reduced motion |

- **Arcs and hand:**
  - A solid accent arc (width 4, round caps) runs from the last run's bead to now; a dashed `--line-2` arc runs from now to the next bead.
  - The now hand is a 2px accent line from the centre to r=62, with a 5px dot. It is rotated by CSS transform (origin 120 120, `--dur-2`) on the 30 s tick.
- **Centre** (HTML overlay, `pointer-events:none`, content box ≤ 92px wide on phones):

  | Phase | Eyebrow | Main | Sub |
  |---|---|---|---|
  | countdown | NEXT CHECK | `2:13:07` (Plex Mono 22px on phone, 30px desktop, tabular) | "≈ 4:21 am" |
  | due | DUE NOW | `+04:12` in accent | "usually by 4:27" |
  | late | LATE | `52m` in warn | "buys skipped after 4:45" |
  | stale | NO CHECK | `9 h` in bad | — |

  The centre has no `aria-live`.
- **Legend:** one line under the dial, 11px, with coloured dots and words: "● on time ● ran late ● failed ◌ missed ◎ bought or sold · hand = now".
- **Bead hit areas:** each bead has a 44px circular transparent button, clipped to a circle so it cannot cover the centre text.
  - A past bead opens a tip in words, e.g. "Thu 8:27 pm · on time (27 min after the close) · 2 signals, nothing bought". The tip has a "Replay this check ›" button that sets the cursor.
  - The next bead's tip reads: "Scheduled 4:05 am (5 min after the 4:00 am close). Recent checks started 20–27 min after the close; buys need it within 45."
- **Empty (no run yet):** 6 hollow beads at the schedule; the centre reads "FIRST CHECK" with a countdown.

**(e) Machine brief**
- Port AiFi `.brief` from `~/SproutHouse/trading/aifi-desk/cloud/design.js:240-249` verbatim. Four items, 2×2 below a 620px container width. Each links to its detail.

| Item | Value (dot + word) | Sub |
|---|---|---|
| **Result** → #results | "Paper +0.00%" (neutral at 0), or once trades exist "+4.20 R" | "0 trades · 0.00 R", or "+1.30% of pot · 7 trades (n 7 of 30)" |
| **Buying** → #positions | Allowed / No auto buys / Risk halved / Halted / Stopped | "Bitcoin weekly bullish · drawdown 0.0%" |
| **Exposure** → #positions | Flat / "2 open · +1.3 R" | "0% of 4% at risk · 6 slots free" |
| **Last 24 h** → #activity | "5 signals · 0 bought" | "6 of 6 checks on time" |

**Layout**
- **Container ≥640px:** grid `240px minmax(0,1fr)`. The dial and legend sit on the left; verdict, moment, since and brief stack on the right.
- **Below 640px:** verdict → moment → since → dial and legend → brief.
- **Phone budget (flat, 390×844):** topbar 52 · verdict 64 · moment 44 · since 36 · dial 168 + legend 18 · brief 128 · padding 48. The brief's Result cell ends at about 620px, which is inside the 760px visible area, and the Gate Run head is at the fold.

### 4.3 Holding (only when `pos.length > 0`)
- **Form:** a card, "Holding · marks at 12:20 am", with at most 6 `.hold` rows of about 56px, in `pos` order (closest to its stop first).
- **Row:** `[.tk coin] [mini R-ladder, 8px track, flex] [open R, Plex Mono 16px, signed]`, with the sub-line "stop 3.2% below · locks +0.4 R · 2 d".
- **Tap:** opens the position sheet.
- **Flat:** not rendered. The brief says Flat.

### 4.4 Pot card (moves between positions)
**Flat, `rec.n == 0` and no positions: "Paper shakedown"**
- Placed after On deck.
- Sub: "since Wed 23 Sep, 6:49 pm · 9 checks".
- A line with printed numbers and no log bars: "124 name checks · 8 signals · 1 auto grade (blocked) · 0 trades".
- An SVG dot-line (full width × 24px): one dot per recorded check on a dashed zero line, time-scaled from `origin.t` to now, with gaps at missed slots and warn dots for late runs.
- The line "The R line starts with the first trade."
- A `.meter`: "0 of 30 closed trades before any verdict".
- The link "What going live needs ›" to #results.

**Once trades or positions exist: "Paper pot", or "Pot · live since <date>"**
- Placed directly after Holding.
- Total R with countUp, "+4.20 R" (closed +2.90 · open +1.30).
- The line "+1.30% of pot · this week +0.31%".
- vs holding: "+0.30 R per trade (n 4 of 30)".
- A 90px SVG sparkline of `pot.spark`: time-scaled, `preserveAspectRatio="none"`, label in HTML, a neutral stroke at exactly 0.
- A faint "Paper" pill in the corner.
- **Live mode with `pot.net == false`:** R only, with the note "Pot % appears once deposits are recorded."

### 4.5 Centerpiece: the Gate Run (Deploy 2)

**Purpose.** Replay one recorded check as its names moving down the engine's real gates (cycle.py order) and stopping where the record says they stopped. It gives real content today with 0 trades.

**Component.** `gateRun(runIndex, host, {autoplay})`. The same component renders on Now and inside the cycle sheet.

**Head** (`.head`)
- h2 "Last check", or "Check at Thu 8:27 pm" when the cursor is on an older run.
- `.sub`: "Fri 12:20 am · on time, 20 min after the 4-hour close · replayed from the record".
- Actions: `.btn.small` "▶ Replay" ("Step ›" under reduced motion). When the cursor is not on the latest run, a "Back to latest" chip is shown.

**Cycle bar** (`.cycbar`)
- The last 12 runs as 32px round buttons labelled with the local hour ("12a", "8p"), 12px gaps, `::before` inset −6px so each hit area is 44px.
- `overflow-x:auto` with scroll-snap. The newest button is scrolled into view on the right.
- Outline colour = health (good / warn late / bad failed / dashed missed). A 6px ink-2 inner dot = the run had a signal. A solid accent fill = the bot acted.
- The selected run gets a 2px `--ink` outer ring and `aria-pressed=true`.

**Gate rows** (`ol.gates > li.gate`, grid `34px 14px minmax(0,1fr)`, column gap 10)

| # | Row | Shown when | Stopped here (codes) |
|---|---|---|---|
| 0 | Exits checked first | held names exist in that run | `h`, with an action word from `hx` |
| 1 | In the books | always | `x` (no market data), `!` (error reading, bad) |
| 2 | Weekly bullish | always | `w` |
| 3 | Daily bullish | always | `d` |
| 4 | 4-hour signal | always | `a` `t` `u` (no signal), `n` (not ready), `g` (close not above the line), `m` (outcome not logged) |
| 5 | Safety checks | always | `r` (the failing check in words) |
| 6 | Grade may trade | always | `p` (watch-only, recorded), `P` (proposed, old model) |
| 7 | Order filled | live mode only | `e` |
| 8 | Bought | always | `E` reaches it |

Each row has three columns:
- **Count** in Plex Mono 18/650, right-aligned: the survivors past this gate. N is the names not held; `survivors(g)` is the number whose code maps beyond g.
- **Spine:** a 2px vertical line with a 10px node.
- **Content**, top to bottom:
  - the label, 14/600;
  - a caption, 12.5 muted: "Stopped here · 2: JTO, PUMP (daily not bullish)";
  - a 6px funnel bar on a shared 0..N scale. The track is `--glass-3` and the fill `--ink-2` at .55 (accent tint on the Bought row), drawn with `transform:scaleX(survivors/N)`, so the funnel shape reads down the card;
  - a tray of chips for the names stopped at this gate.

Row 4's caption gives per-reason subcounts: "Stopped here · 9: no signal on the last bar (5 one flip away, 4 already running)", then "· not ready N", "· close not above the line N" and "· outcome not logged N" when any is non-zero.

**Chips** (`button.nm`)
- 32px tall visual, Plex Mono 12.5px, glass-2 solid fill (no backdrop-filter), 12px gaps, `::before` inset −6px so the hit area is 44px.
- A 3px inset left bar coloured by `STAGE[code].role`.
- Second words:
  - `r`: "volume 0.36×" (every failing code: "volume 0.38× · funding 68%/yr")
  - `p`: "watch-only"
  - `E`: an accent fill chip reading "bought · stop 3.1% below"
  - `h`: "stop raised", "sold +2.10 R", or "no exit action logged" (stopgap)
- `aria-label` example: "CRV, blocked at safety checks: volume 0.36 times the minimum".
- A tap opens the name sheet at that run (§9.1).

**Tray rules**
- Row 4's muted tray is always collapsed to one chip, "9 names · show", which expands in place.
- Other muted trays (rows 1–3) collapse only above 6 chips, to 6 plus "+N".
- Blocked, watch-only, bought, error and unknown trays are always expanded.
- Rows below the deepest gate any name reached are dimmed to .45 and show "—".

**Row 6 context line:** "Bitcoin weekly bullish: a 4-hour flip is auto grade" (or "…not bullish: every signal is watch-only").

**Foot caption:** "Replayed from the record of the Fri 12:20 am check. Every name, every gate, as the engine logged it."

**Real content**
- Thu 8:27 pm: 14 → 13 (PENGU weekly) → 11 (JTO, PUMP daily) → 2 signals (9 · show) → 1 (CRV blocked: volume 0.36×) → 0 (UNI: watch-only, recorded) → 0 bought.
- Thu 4:20 pm: 14 → 13 → 11 → 1 (LINK flip, auto grade) → 0 (LINK blocked: volume 0.73×) → rows below dimmed.
- Fri 12:20 am: 14 → 13 → 11 → 0. Because it is quiet, the card adds "Quiet check. Last check with a signal: Thu 8:27 pm ›", which sets the cursor.

**Special runs**
- **Counts-only run** (`rd == null`, the five runs before Thu 12:20 pm):
  - "In the books" comes from `c[0]`. Weekly and daily are hatched and read "not recorded". "4-hour signal" = `c[1]`.
  - Rows 5–6 take their chips from `tg`/`rx` (refusal join). Bought = `c[4]`.
  - Caption, formatted at runtime from the first run with `rd`: "Names were not recorded for this check; per-name readings start Thu 24 Sep, 12:20 pm."
- **Failed run:** all rows grey, counts "—", and an inline `.banner.bad`: "This check stopped early (ConnectionError). Exits may not have been checked."
- **Late run** (`ok==0`): row 5's caption reads "Buys skipped: the data was too late."
- **No runs:** "The first check will be replayed here."

**Motion** (transform and opacity only)
- STEP = 260 ms per gate; total ≤ 2.4 s.
- At t0 a **flow cluster** sits on gate 1. It is a solid glass-3 capsule with one 6px dot per survivor in 2 columns, or a number bubble above 20 names.
- Each step:
  1. The cluster translates to the next node (220 ms, `--ease`).
  2. The node pops once (scale 1→1.35→1, 350 ms).
  3. The count counts up.
  4. The bar scales from the previous ratio.
  5. The dots of the names stopped here fade, and their chips enter: translateX −24→0, scale .9→1, opacity 0→1, 180 ms, 25 ms stagger capped at 250 ms.
- At Bought, surviving chips take the accent fill and the pulse plays once. The cluster then fades out and is removed; it exists only while a replay plays.
- A tap anywhere on the card skips to the final state.
- **Reduced motion:** final state only. "Step ›" reveals one gate per tap; the rows below the step stay dimmed.

**When it autoplays.** It plays once, only when all of these hold:
- the run t is newer than `localStorage ex.gr`;
- the run's `rd`, `tg` or events differ from the previous run's (an identical run renders final instantly with "Same as the previous check");
- the card is at least 50% in view;
- the page is visible;
- reduced motion is off.

An explicit selection (cycle bar, dial "Replay", heartbeat, timeline, tape "Open") always plays, except under reduced motion.

**Scale.** At 40 names the rules are the same; trays collapse, and the cluster uses a number bubble.

### 4.6 On deck (what the next 4-hour close could do)
- **Head:** h2 "On deck", sub "What the next 4-hour close could trigger", and a tip: "While a 4-hour cloud is bearish its line can only step down, so each figure is the most the next close must rise. Not a prediction. A signal still has to pass the safety checks and find a free slot."
- **Groups** (from `names[].grp`, one `STAGE` vocabulary). Each group header shows its count.

| Group | Rule | Tile | Real today |
|---|---|---|---|
| **Could signal next** (accent 1px top edge) | weekly and daily bullish, 4-hour bearish, passes today's checks | `.tk` coin · `.wd3` · "needs +3.3%" · proximity bar (accent tint; fill = 1 − min(pct,10)/10) · book | BTC +3.3 · ETH +4.4 · HYPE +8.1 |
| **Armed, too thin** (warn edge) | same state, fails a check | as above plus every failing check in warn words | AAVE +4.2 (volume 0.43×) · BNB +3.4 (volume 0.25×) |
| **Already running** (muted, `details.disc` collapsed) | 4-hour bullish: only a pullback can fire, which is watch-only | chip "UNI · cushion 1.6%", plus warn words if ineligible | UNI, SOL, LINK, CRV (0.38× · 68%/yr), CAKE, JUP |
| **Not set up** (muted, collapsed) | weekly or daily not bullish | chip "PENGU · weekly" | PENGU, JTO, PUMP |
| **Held** (good edge) | in a position | "stop 2.1% below (4-hour line)" | — |
| **No data** (bad edge) | unlisted, no candles, error | "no market data" / "error reading" | — |

- **Bitcoin weekly not bullish:** group 1 is titled "Could flip next (watch-only while Bitcoin's weekly is not bullish)".
- **Wording rules:**
  - Line distances are always moves from the last close: "needs +x%" for bearish names, "cushion x%" for bullish ones, "stop x% below" for held names.
  - Coin prices are never shown here, and a buy is never promised.
- **Phone layout:** the first two groups are a 2-column tile grid (`repeat(2,minmax(0,1fr))`, about 160×96px each). The other groups are collapsed disclosures: "Already running · 6", "Not set up · 3".
- **`.wd3`:** three 20×16 cells with ▲/▼, good-soft or bad-soft, "W D 4h" micro-labels at 9px, and `aria-label="weekly bullish, daily bullish, 4-hour bearish"`.
- **As-at mode** (the shared cursor is on an older run): a `.seg.quiet` "Now | As at Thu 4:20 pm" appears, and the groups are recomputed from `runs[k].rd` and `dx`. Thin tiles read "too thin then". A caption says "recorded".
- **Tap** a tile or chip to open the name sheet.
- **Empty states:**
  - Nothing armed: "Nothing is one close away. 6 names are already running; 3 are not set up."
  - No readings: "Readings appear after the next check."

### 4.7 Latest
- **Content:** the last 5 events with `lv ≥ 1`, newest first. Runs of consecutive quiet checks fold into one muted line, "3 quiet checks · 8:21 am → 4:20 pm", with any board lines (`lv 0`) as muted sub-lines.
- **Row:** `.tl` grid `52px 22px minmax(0,1fr)`: time (Plex Mono 12 muted) · 22px icon chip · sentence (13.5) + sub (12.5 muted). Coins are `.tk` chips.
- **Foot:** "All activity ›".
- **Real content:**
  - 8:27 pm · CRV pullback (watch-only) blocked: volume 0.36× the minimum
  - 8:27 pm · UNI pullback recorded, watch-only grade
  - 4:20 pm · LINK would have bought (auto grade), blocked: volume 0.73× the minimum
  - 8:24 am · UNI, SOL pullbacks recorded
  - 4:21 am · ETH, HYPE proposals expired (old approval model)
- **New rows** rise in (`--dur-3`) with a 6px accent-tint "new" dot that clears once seen.
- **Empty:** "No events yet. The first check writes here."

### 4.8 Now layouts
- **Phone, flat:** alert rail → mission → Gate Run → On deck → Shakedown → Latest. About 2,050px, down from 2,957px, with no horizontal scroll.
- **Phone, holding or with trades:** alert rail → mission → Holding → Pot → Gate Run → On deck → Latest.
- **Desktop ≥1100:**
  - Row A: mission, full width.
  - Row B: `.grid2` (1.6fr / 1fr), Gate Run | stack(Holding, On deck).
  - Row C: `.grid2.even`, Latest | Pot or Shakedown.
- **641–1099:** single column.

---

## 5. Shared cycle cursor (graft from P3)

- **State:** `S.cursor = run t`, or `null` for the latest run.
- **Setters:** cycle bar, dial "Replay this check", moment row, heartbeat cells, timeline cycle headers, tape column or scrubber, "Last check with a signal ›".
- **Followers:**
  - the Gate Run on Now (replays)
  - On deck (as-at mode)
  - the tape cursor column (accent outline)
  - the heartbeat selected cell (ink outline)
  - the cycle sheet
- **"Back to latest"** clears the cursor.
- **Off the Now tab,** setting the cursor opens the cycle sheet, which holds the Gate Run.
- **Scope:** the cursor is per-session and not persisted.

---

## 6. Activity tab

### 6.1 Heartbeat (Deploy 2)
- **Grid:** the last 42 four-hour slots in rows of 6, newest row on top. Cells are keyed by **UTC slot** and only labelled in local time, which keeps them DST-safe.
  - Column order: pick the UTC hour among 00/04/08/12/16/20 whose local hour is smallest on the newest row's date. Each row is then 6 consecutive slots starting at that hour.
  - Row labels are the local date of the row's first slot ("Fri 25").
  - Column labels are the local times from the newest row ("12a 4a 8a 12p 4p 8p").
- **Cells:** `44px repeat(6,minmax(0,1fr))`, 36px tall. Each cell is a button with an `aria-label` in words.

| State | Look |
|---|---|
| on time, quiet | good-soft fill, "·" |
| signals, nothing bought | ink-2 outline, count "2" |
| bought / sold | solid accent, "+1" / "−1" |
| ran late (buys skipped) | warn outline, "late" |
| failed | bad fill, "!" |
| missed (no run) | dashed `--line-2`, "—" |
| halted | bad outline, "‖" |
| before start | blank |
| next | accent 2px ring |

- **Several runs in one slot:** a merged cell with a small count badge. The cycle sheet lists every run in the slot.
- **Punctuality line:** "Usually 21 min after the close (20–27) · limit 45 · 2 late runs in 7 days (169, 132 min)."
- **Caption:** "Every cell is a recorded check. Late = started more than 45 min after the close, so buys were skipped."
- **Tap** a cell to set the cursor and open the cycle sheet.

### 6.2 Timeline
- **Grouping:** by local day ("Thursday, 24 September"), then by check. Each check header reads "8:27 pm · on time (27 min after the close) · 14 names · 2 signals". Its events use the Latest row form. Quiet checks fold.
- **Filters** (`.fchips`): All · Bought & sold · Blocked · Recorded · Health. Tapping a coin chip in any row adds a removable "LINK ✕" filter pill.
- **"New since your last visit"** hairline marker, with an accent-tint pill.
- **Range:** the bundle's 7 days. The last 3 days show by default, with "Show earlier".
- **Tap** a check header to set the cursor and open the cycle sheet.
- **Empty:** "Nothing recorded yet."

### 6.3 Signals (replaces the Refused tab)
**(a) Funnel.** `.seg.quiet` "Since start | This week". Linear `.fbar` rows with the count printed; on phones the label sits above a full-width track.
- Main path: Name checks **124** → Signals **8** → Passed every check **5** → Auto grade among them **0** → Bought **0**.
- Side rows, indented with "└":
  - Blocked by a check **3** (volume 3; auto grade 1), warn fill
  - Recorded, watch-only **3**, ink-2 fill
  - Expired, old approval model **2**, muted fill
  - Order not filled **0**, bad fill

Counts are per signal, so the side rows add up to the signals total.

**(b) "Would have traded"** (pinned): blocked auto-grade signals. "Thu 4:20 pm · **LINK** · 4-hour flip · Auto grade · Blocked: volume 0.73× the minimum."

**(c) Outcome list.**
- Cards on phone, a `section.card > .head + .tbl` at ≥900px.
- Filter chips: All · Blocked · Recorded · Expired · Not filled · Bought.
- A card shows: time, `.tk` coin, a kind+grade pill ("Flip · Auto grade" outline accent, or "Pullback · Watch-only" mute), an outcome pill, and the failing checks in words.
- Foot: "Latest 200 of N" whenever the list is truncated.

**(d) Why signals did not trade.**
- `.bars` with an explicit fill per outcome group (`--fill` variable) and a word label on its own line on phones.
- Animated by `scaleX`.
- Labels: "Volume below the minimum", "Watch-only grade (by design)", "Proposal expired".

**Empty:** "No signals yet. Signals appear when a 4-hour cloud flips or pulls back while weekly and daily agree."

**Data:** the funnel and pinned rows come from `latest`; rows and daily totals come from `ledger` (lazy).

### 6.4 The board over time (tape with replay, Deploy 2)
- **Grid:** rows are names in `order`, grouped under book labels in 10px eyebrows. Columns are `runs[]`, newest on the right.
  - Cells: `max(5px, floor((inner−48)/runs))` wide × 14px tall, 1px gap. On phone that is 48 + 42×6 = 300px.
  - The fill comes from `STAGE[code].tape`. A legend row carries the words.
  - Counts-only runs are hatched, with the column header "not recorded".
- **Controls:**
  - "▶ Play" steps the cursor one column every 600 ms.
  - A scrubber (`input[type=range]`).
  - The cursor time in Plex Mono 18.
  - A mini Gate Run line under the tape, "14 → 13 → 11 → 1 → 0", which follows the cursor; its "Open" opens the cycle sheet.
  - Cells cross-fade over 180 ms. Play pauses on `pointerdown` or when the page is hidden.
- **Reduced motion:** no Play, the scrubber only.
- **Accessibility:** tapping a row label opens the name sheet. Rows have `aria-label`s, e.g. "LINK: armed but thin Thu 12:20 pm, blocked Thu 4:20 pm, running since".
- **Real content:** LINK `t → r → u → u`, UNI `u → u → p → u`, CRV `u → u → r → u`, with constant `w` for PENGU and `d` for JTO and PUMP.

### 6.5 All readings (`details.disc` "Every name, last check")
- One card per name on phone; a table at ≥900px.
- Fields:
  - W / D / 4h in words with dots
  - range, with the note "only matters for watch-only pullbacks"
  - line distance ("needs"/"cushion")
  - volume × minimum ✓/✕
  - funding %/yr ✓/✕ (limit 30)
  - history days ✓/✕ (needs 280)
  - open interest: "checked when a signal fires" until E2
  - the stage in words
- Held names are included (code `h`).

---

## 7. Positions tab

### 7.1 Position cards (R-ladder), sorted by `to_stop_pct` ascending (closest to trouble first)
- **Head:** `.tk` coin · book · pill "Flip · Auto grade" · "held 2 d 6 h (13 bars)" · "marks at 12:20 am".
- **Headline row:**
  - **Open R**, net of costs so far: 26px/650, signed and coloured, with the word "open".
  - **Result:** "+1.8% of pot".
  - **Stop:** "3.2% below · locks in +0.4 R" (or "risks −0.6 R" while the stop is below entry).
- **R-ladder:**
  - 8px track, domain `lo=min(−1.25, r_now−.25)`, `hi=max(2, r_now+.5, r_lock+.5)`.
  - Ticks: −1 R (bad, "first stop"), 0 (ink-2, "entry"), and the current stop (a 12px solid accent bar, "stop +0.4 R").
  - Mark bead: 14px, ink, labelled "now +1.8 R".
  - Bands: the locked band from 0 to `r_lock` is good-soft and hatched; the at-risk span is glass-3.
  - On the first view after a change, the bead slides from `localStorage ex.r.<id>` (`--dur-3`, transform).
- **Exits:** "Exits if a 4-hour close falls below the stop (3.2% below) or the daily or weekly turns." Daily and weekly distances show once E1 exists; until then "daily and weekly distances after the engine update". The line "No fixed target: it rides until the stop or a 4-hour, daily or weekly turn" appears on the first card only.
- **Stop trail:** a 36px step sparkline of `stops[]` in R. Until E4 it is two points, captioned "trail history starts with the engine update".
- **Secondary line** (with a tip): "Exposure 84% of pot · 3× isolated · only 1.00% of pot at risk at entry".
- **Tap:** opens the position sheet.
- **Empty:** "No open positions. An auto-grade flip that passes every check appears here with its stop and R-ladder. Closest now: BTC needs +3.3% ›" (links to On deck).

### 7.2 Risk budget
- **Open risk:** a 4% track with one segment per book (solid accent at stepped opacity 1/.8/.6/.45/.3, each with a word label), and a tick at each book's cap. "1.0% of 4% at risk · room for 3 more full-size trades."
- **If every stop hit now:** "−0.9% of pot" (bad word), or "+0.4% of pot locked in".
- **Slots:** 6 pips, "2 of 6".
- **Gross:** a meter, "0.9× of 3×".
- **Drawdown:**
  - A `.bmeter`-style gauge (port `.bmeter` from `~/SproutHouse/trading/aifi-desk/cloud/design.js`), domain 0–25%.
  - Ticks at 10% ("risk halves") and 20% ("stops buying"); the fill is good below 10, warn from 10 to 20, bad from 20.
  - The value always carries a word: "0.8% · normal", "11.2% · risk halved".
  - If `dd ≥ threshold` but `mult == 1`: "risk halves from the next check".
- **Empty:** gauges at 0 with the ticks visible. "Nothing at risk. The pot is 0.0% below its peak."

### 7.3 Books (shown once)
- **Row:** book · "vs BTC" · "gets 20% of the pot, may risk up to 1%" · a mini meter of used vs cap · "tradeable today 1 of 1" (or "0 of 2 · volume" in warn) · once trades exist, "n 4 of 30 · +0.3 R vs holding".
- **Real rows:**
  - bitcoin 1 of 1
  - eth-defi 3 of 5 (AAVE, CRV: volume)
  - solana 2 of 5 (JUP, JTO, PENGU: volume)
  - hype 1 of 1
  - bnb 0 of 2 (volume)
- **Footnote:** "Open interest and leverage are checked when a signal fires."
- Untested names carry the small word "untested".

### 7.4 Waiting for approval
Only rendered while `proposals` is non-empty. It lists each open proposal with its expiry in local time.

---

## 8. Results tab
Every card title carries "Paper" while `mode.eff=='paper'`.

**8.1 Verdict & go-live (first card)**
- **Header:** "Too early to judge: 0 of 30 closed trades", with an n/30 accent meter.
- **Go-live checklist:** four rows from `ledger.verdict.gates`, each with a meter and a word: *not yet* (muted, while n<30), *passing* (good) or *failing* (bad; only drawdown can fail before n≥30).
  - 30 closed trades
  - average above +0.2 R
  - worst drawdown under 20%
  - costs at most 0.12 R per trade
- **Per book:** 90px small multiples. Book cumulative R in accent against holding-equivalent R (Σ(R−rel_R), dashed muted), with a pill:
  - n<30: "Too early · leading by 1.3 R" or "Too early · trailing by 0.4 R"
  - n≥30: "Beating BTC" (good) or "Trailing BTC" (bad)
- **Empty:** meters at 0, which still show what live needs.

**8.2 Curve.** lightweight-charts 4.2.3, injected by `loadLWC()` on first need from `https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js`; there is no HEAD tag. The Now tab never loads it. A `.seg` switches "In R | Pot %".
- **R view:**
  - `addBaselineSeries` of cumulative closed R at each close (`baseValue 0`, good above, bad below).
  - A dashed muted line of cumulative holding-equivalent R.
  - A dotted "open, not banked" tail to closed + open R.
  - Exit markers (circles coloured by R, text "+2.1R" hidden under 640px). A crosshair fills the legend with that trade.
- **Pot % view:**
  - A baseline series of `eq.pct`.
  - A drawdown histogram on an overlay scale (`scaleMargins {top:.75, bottom:0}`), with price lines at −10 "risk halves" and −20 "stops buying".
- **Chart settings:**
  - Local-time `tickMarkFormatter` and `timeFormatter` via Intl.
  - `priceFormatter` renders "+1.2 R" or "+0.4%".
  - Watermark "PAPER" (violet at .12) in paper mode.
  - Height `clamp(220px, 40vw, 360px)`.
  - Redraw on theme toggle and OS scheme change. Destroy on tab change.
  - In live mode with `pot.net==false`, the Pot % view is disabled with the note "Pot % needs the deposits record."
- **Empty:** no chart. A `.nochart` reads "The first closed trade starts this line. Paper since Wed 23 Sep · 9 checks · 0 trades."

**8.3 Record strip.** `.strip .t > .k/.v/.s`, plus a `.meter` n/30 under Trades and vs holding.
- Tiles: Trades · Win rate · Average R · Total R · vs holding · Profit factor · Worst losing streak · Costs per trade.
- R values are sign-coloured.
- Profit factor with no losses reads "—" with the sub "no losing trade yet".
- While n<30, values are ink-2 with "n=7: too few to judge". Buckets under n=10 are greyed.
- **Empty:** hidden, replaced by one sentence.

**8.4 R per trade.** An SVG strip: one dot per trade in order on an R axis clamped to [−1.5, +6], with hairlines at −1 R ("a full stop") and 0. Above 60 trades a `.seg` switches to a histogram of 0.5 R bins. Caption: "Trend following: many small losses, a few large wins." Hidden when empty.

**8.5 Trades.**
- Phone cards: coin, R (large), reason in words, hours, local date, vs holding.
- ≥900px: `section.card > .head + .tbl` with sortable `th`.
- Filters: book · outcome · coin. "Latest 300 of N", then "Show 50 more" client-side. A tap opens the trade sheet.
- **Empty:** no table; one `.empty` line.

**8.6 Weekly review.** A dated card, "Sunday review · 27 Sep", with `review.html` clamped to 12 lines behind "Read all". Empty: "No Sunday review yet."

**8.7 Sweeps** (only if any): "Thu · eth-defi → ETH · 0.42% of pot · recorded, not executed".

---

## 9. Sheets (the existing `.sheet`; one delegated handler on `[data-name] [data-cycle] [data-pos] [data-trade]`)

**9.1 Name sheet**
- **Header:** coin in Plex Mono 28 · book pill · group pill · "as of 12:20 am" (or "as at Thu 4:20 pm, recorded" under the cursor).
- **States:** W/D/4h in words; "needs a 4-hour close up to 3.3% higher to flip" or "cushion 8.7%"; range ("above its band" / "in its band" / "below its band"; relevant only for watch-only pullbacks).
- **Filters:** ✓/✕ with ratios, e.g. "Volume 1.12× the minimum ✓ · Funding 11%/yr (limit 30) ✓ · History 1,500 days ✓ · Open interest: checked when a signal fires".
- **This name's tape row**, enlarged: 42 cells; tapping one sets the cursor.
- **Check lights:** for any `r`/`p`/`P`/`e` event of this coin. AiFi `.step` chips in `cfg.checks` order (`risk.pre_trade` order), each with an 11px word, then Policy (Auto grade buys on its own / Watch-only: recorded), then Fill (live only).
  - Lights come on at 40 ms each (all at once under reduced motion).
  - The failing check turns bad and expands: "Universe filters: volume 0.73× the minimum".
  - Checks not stored for that record (every refusal before E5) render dashed, "not recorded". They are never shown as passed.
- **Its events**, newest first.
- **Market prices**, captioned: "4-hour line 86,983 · last close 84,221 (market prices, not your money)".

**9.2 Cycle sheet**
- Title: "Check at Thu 4:20 pm · on time (21 min after the close)".
- The Gate Run for that run, with autoplay.
- That run's events.
- "‹ Previous check / Next check ›", which moves the cursor.
- For a slot with several runs, a `.seg` switches between them.
- It shows no raw engine log.

**9.3 Position sheet.** The position card, larger, plus:
- facts as market prices with 5 significant figures: entry, first stop, current stop, mark;
- time held, costs so far in R, grade, trigger, and Bitcoin weekly and daily at entry;
- the stop-trail steps.

**9.4 Trade sheet.** Final R, relative R, reason, hours, pnl % of pot, costs R; mfe/mae once E4 exists; prices in sheet-only facts.

**9.5 Health sheet** (from a capsule tap, which also refreshes)
- **Punctuality strip:** the last 42 slots as bars of late minutes on a 0–60 scale, with the 45-minute limit drawn as a line. Missed slots are dashed and failed slots red. "Median 21 min after the close · range 20–27 · 2 late runs (169, 132 min)."
- The current alerts, each with its action.
- "Data pushed 12:47 am".
- A Refresh button.

---

## 10. Rules tab
- **In force.** Sentences built from `cfg`:
  - "Checks 6 times a day, about 20 minutes after each 4-hour close."
  - "Buys on its own only an auto-grade signal: a 4-hour flip while the coin's weekly and daily and Bitcoin's weekly are bullish. Everything else is recorded, not traded. Nobody approves anything."
  - "Risks 1% of the pot per trade; at most 4% at once, 6 positions, 3× exposure."
  - "Sells on the stop (it follows the 4-hour line up, never down) or when the 4-hour, daily or weekly turns. No fixed target."
  - "Halves risk at 10% drawdown; stops buying at 20% until reviewed."
  - "Trades only coins with at least 30M a day of market volume and 10M open interest (market figures, not your money), funding under 30% a year, 280 days of history and 3× leverage available."
  - Then one row per book: "eth-defi · gets 35% of the pot · may risk up to 2.5%".
- **Glossary.** Every `GLOSS` entry as a `details` list. Every entry is used somewhere on the page (§14).
- **Docs.** A `.seg.quiet` sub-nav with a sliding `.ind` that scrolls inside itself and centres the active item (port `initSegs`/`setSeg`), replacing the 10 crumb buttons. `md()` in worker.js is fixed: when a list is open and a line matches `/^\s{2,}\S/`, it is appended to the last `<li>` instead of closing the list.
- **Log out** (`.btn.small.ghost`) is shown on phones only.

---

## 11. Visual language: `cloud/mission.js` (`MISSION_CSS`)
`design.js` stays a clean AiFi copy (only its header comment changes to "one magenta accent"). Every addition and override lives here.

**Tokens**
- Motion: `--dur-1:180ms; --dur-2:350ms; --dur-3:600ms`, all on the existing `--ease`.
- Light theme, in both the `prefers-color-scheme:light` block and `[data-theme=light]`: `--good:#15784a; --warn:#8a5a0f; --bad:#b53a35` (≥4.5:1 on glass).
- Dark theme: `--muted:#8d95a2`.

**Fixes**
- `.brand .mark{background:linear-gradient(135deg,var(--accent),var(--violet))}`
- `.bar .fill{width:100%;transform-origin:left;transform:scaleX(var(--k,0));background:var(--fill,var(--ink-2));transition:transform var(--dur-3) var(--ease)}`
- `.tbl td.empty{text-align:center;white-space:normal}` (and tables are never rendered empty)
- `.tbl th{backdrop-filter:none;background:color-mix(in srgb,var(--bg) 70%,var(--glass-2))}`
- `ul.list{padding:0;margin:0;list-style:none}`
- `.tip{position:relative}.tip::before{content:"";position:absolute;inset:-14px}` gives a 43px hit area.
- `.vh` (clip technique) for the tablet rail labels and the phone h1.
- `html.hid .bg,html.play .bg{animation-play-state:paused}`
- Tables use `section.card > .head + .tbl` nesting, never `card tbl`. Overflowing scrollers get a right-edge mask class set by JS.

**New components** (surfaces run ground → glass → glass-2 → glass-3; blur only on the topbar, tabbar, sheet and section cards)

| Class | Purpose / key CSS |
|---|---|
| `.capsule` | 32px pill, glass-2, 13px/600, `.dot` + word + Plex Mono 12 age; `.warn` / `.bad` soft fills; `aria-live="polite"` |
| `.mission` | `container-type:inline-size`; ≥640px grid `240px minmax(0,1fr)` |
| `.moment`, `.since` | 13.5px rows; 2-line clamp |
| `.dial` | relative box; `.ctr` HTML overlay; `.hit` 44px circular buttons |
| `.brief` | ported verbatim |
| `.cycbar` | flex, gap 12, x-scroll, snap; 32px buttons with 44px hit |
| `.gates .gate .spine .fl .tray .nm .cluster` | Gate Run (§4.5); chips have no backdrop-filter |
| `.deck .tile .wd3 .prox` | On deck |
| `.hold .ladder .tick .stopm .bead .lock` | positions; `.lock` = `repeating-linear-gradient(45deg,var(--good-soft) 0 4px,transparent 4px 8px)` |
| `.rbar .pips .gauge` | risk budget |
| `.hb` | heartbeat grid |
| `.tape` | board tape cells `.st-<code>` |
| `.tl` | timeline / Latest rows |
| `.fbar` | funnel rows; label above the track under 640px |
| `.facts` | `dl` grid `auto 1fr`, muted keys, Plex Mono right-aligned values (replaces the misused `.kv`; any remaining `.kv` uses `div > .k/.v`) |
| `.lights` | `.step` chips + words |
| `.toast` | glass, bottom-centred at `calc(84px + env(safe-area-inset-bottom))`, max 360px |
| `.st-h … .st-E` | one class per stage code, from `STAGE` |

**worker.js HEAD**
- Two theme-color metas: `#0a0b0f` (`media="(prefers-color-scheme: dark)"`) and `#eef1f6` (light). JS rewrites the content on a manual toggle.
- `<style>${CSS}${MISSION_CSS}</style>`.

---

## 12. One state vocabulary (`STAGE` in client.js, `.st-*` in mission.js)

| Code | Word | Gate | Colour role (chip edge / tile) | Tape cell | On deck group |
|---|---|---|---|---|---|
| `h` | Held | 0 | good outline | good outline | Held |
| `x` | Not listed / no market data | 1 | bad-soft | hatched | No data |
| `!` | Error reading | 1 | bad | bad | No data |
| `w` | Weekly not bullish | 2 | muted | dark glass-3 | Not set up |
| `d` | Daily not bullish | 3 | muted | dark glass-3 | Not set up |
| `n` | 4-hour not ready | 4 | muted | muted | No data |
| `a` | One flip away | 4 | accent tint | accent tint | Could signal next |
| `t` | One flip away, too thin | 4 | warn outline | warn tint | Armed, too thin |
| `u` | Already running | 4 | good-soft | good-soft | Already running |
| `g` | Signal, close not above the line | 4 | muted | muted | by 4-hour state |
| `m` | Signal, outcome not logged | 4 | dashed muted ("unknown until the engine update") | dashed | — |
| `r` | Blocked by a check | 5 | warn | warn | — |
| `p` | Watch-only, recorded | 6 | ink-2 ring | ink-2 ring | — |
| `P` | Proposed (old model) | 6 | ink-2 ring | ink-2 | — |
| `e` | Order not filled | 7 | bad | bad | — |
| `E` | Bought | 8 | solid accent | solid accent | (Held next check) |
| `-` | Not recorded | — | hatched | hatched | — |

---

## 13. Motion kit
- **Allowed properties:** transform and opacity only (plus stroke dash offsets for the dial arcs).
- **Ported from AiFi:** `reduced`, `countUp(el, to, {from})` (extended with `from`) and `stagger`.

| Moment | What moves | Timing | Reduced motion |
|---|---|---|---|
| Tab change | rail pill translateY, tab colour | `--dur-2` | instant |
| Card entrance | `.rise` 60 ms stagger (cap 600) | `--dur-3` | 200 ms fade |
| First view of new numbers | countUp, only on changed values | 800 ms | final value |
| **Arrival** (stamp changed) | toast "Check 4:21 am landed · 1 signal · nothing bought" (4 s; with "↑ See it" if scrolled more than a screen) · next dial bead fills (scale .6→1) and pulses once · Gate Run replays if different · new Latest and timeline rows rise with a "new" dot · heartbeat cell scales in · changed numbers count up | `--dur-2` / `--dur-3` | instant, no pulse |
| Gate Run | §4.5 | ≤2.4 s | Step |
| Tape Play | one column every 600 ms, 180 ms cross-fade | — | scrubber only |
| Ladder bead | translateX from the last seen R | `--dur-3` | static |
| Bars and meters | scaleX from 0 on first view, from the old value on arrival | `--dur-3` | static |
| Check lights | 40 ms stagger | `--dur-1` | all at once |
| Due phase | next bead pulse every 2 s | real clock | none |

---

## 14. Words and formats

**Dictionary**

| Engine term | Page word |
|---|---|
| tier A | **Auto grade** (small "A" + tip) |
| tier B | **Watch-only grade** |
| trigger | signal |
| flip / pullback | "4-hour flip" / "pullback into the band" |
| pre-trade | Blocked by a check: <check> |
| policy | Recorded, not traded |
| proposal | Expired (old approval model) |
| execution | Order not filled |
| universe filter | "volume 0.73× the minimum", "funding 68%/yr (limit 30)", "only 190 days of history (needs 280)" |
| Unrealised | Open R · % of pot |
| To stop | "stop 3.2% below" |
| Size % pot | "Exposure 84% of pot · only 1% at risk" |
| Share · cap | "Gets 20% of the pot, may risk up to 1%" |
| range | only in sheets: above / in / below its band |

**Numbers**
- R: 2 decimals, signed ("+1.84 R").
- % of pot: 2 decimals.
- Distances: 1 decimal.
- Multiples: 2 decimals ("0.73×").
- Funding: "%/yr", no decimals.
- Prices: 5 significant figures, sheets only.
- |v| below half of the last digit prints 0 with no colour, so there is never a red "−0.00%".
- Missing leverage prints "—" with no "x".

**Time** (via `Intl.DateTimeFormat` in the phone's zone and locale)
- Today: "4:20 am". Within 7 days: "Thu 8:27 pm". Older: "Sep 18".
- Relative: "just now" under 90 s, "27 min ago", "3 h ago"; absolute at 48 h and beyond.
- Counts use the last 24 h, never the UTC day.

**New GLOSS entries.** Auto grade, watch-only grade, signal, flip, pullback, one flip away, too thin, cushion, needs (upper bound), open R, locked R, first stop, exposure, risk in use, drawdown gauge, slot, gate run, heartbeat, late check, vs holding, profit factor, go-live gates, paper. Thresholds are filled from `cfg`, never hard-coded.

---

## 15. Accessibility and performance budgets
**Accessibility**
- One h1.
- The capsule is the only `aria-live` region (polite).
- The dial, tape and punctuality strip are `role="img"` with sentence labels.
- Gate rows are list items with text counts. Every chip and cell is a button with a words `aria-label`.
- Tips use `role="tooltip"` + `aria-describedby` and are labelled "What is <term>?". They open on click or focus and close on Escape or an outside tap; there is no hover on touch.
- Scrollers (`.tbl`, `.cycbar`) get `tabindex=0 role=region aria-label`.
- Every tap target is at least 44px.

**Performance**
- Blur only on the topbar, tabbar, sheet and section cards (about 12 layers). Chips, tiles, tape and heartbeat cells and `th` have no blur.
- `.bg` pauses when hidden and during replays.
- One lightweight-charts instance at most (Results), loaded lazily and destroyed on tab change.
- Size targets: client.js ≤ 95 KB, mission.js ≤ 25 KB, `exec:latest` ≤ 12 KB today and ≤ 50 KB raw / 12 KB gz at maturity.
- Now interactive within 1 s on an iPhone 12 over LTE.

---

## 16. What is removed

| Removed | Replaced by |
|---|---|
| 4 Overview stat cards | verdict, brief, dial |
| 5 book cards and the orphan 5th card | the Positions books list |
| 9-column readings table | On deck + Gate Run + the All readings disclosure |
| "What the last cycle did" (engine lines) | Latest |
| "Next" card and "Cycles today N of 6" | dial + "6 of 6 on time in 24 h" |
| Book tab and its 11-column table | position cards |
| Refused tab and its empty bars | Signals |
| "Caps in force" / "Universe filters" `.kv` blocks | Rules sentences |
| Hand-built SVG equity line | lightweight-charts |
| 10 crumb buttons | `.seg.quiet` |
| "pushed X ago" in the topbar | capsule and Health sheet |
| amber PAPER / red LIVE pills | violet / outline accent |
| the `FAIL` dot class | `.dot.bad` / `.dot.gap` |
| unhandled digit badges | wired |
| From the bundle: every currency field, the `last_run`/`pot`/`positions`/`trades` passthrough, `settings.timezone`, `hours_local`, `approval._doc`, the duplicate `review_md` | data contract |
| KV `exec:<date>` and `dates`; `/api/dates` and `/api/day`; the dead `if False` line | — |

---

## 17. Coverage of HIGH audit findings and judge must-fixes

| HIGH finding (lens) | Resolution |
|---|---|
| No single "does it need me" answer; a failed cycle reads green (L1, L5) | §3 status engine reads `failed`, the halt file, throttle, `fresh`, mode fallback, alerts and the clock phase. A failed check is **Failed**, with a bad banner on every tab. |
| Freshness hidden on phones; FAIL has no dot style (L1, L2, L5) | Capsule in the topbar at every width; the rail mirrors it; `.dot.ok/.gap/.bad` only. |
| Overview never names holdings (L1) | Holding section, brief Exposure, position cards; the flat state points to On deck. |
| "Unrealised" price change next to Size % (L1) | Open R (net) and % of pot lead; risk % of pot; exposure on a secondary line; "stop x% below". |
| Only the last cycle; no history (L1, L4) | `runs[]` (7 days) and `events[]`; Gate Run over any run; Latest; heartbeat, timeline, tape. |
| "Next" is a UTC cron time (L1) | Client clock with measured lag, countdown, phases; On deck distances. |
| 9-column readings table (L1, L2) | On deck groups + Gate Run trays; All readings disclosure with ✓/✕. |
| No active tab (L2, L5) | Ported `route()`/`movePill()` (client.js:379-398). |
| `.kv` misuse (L2) | `.facts`; correct `.kv` markup. |
| Refusal bars have no fill (L2, L4) | `.bar .fill` background via `--fill`, scaleX, per-signal counts, normalised words. |
| Empty rows right-aligned and off-screen (L2) | No empty tables; card-level empty sentences; `td.empty` fix. |
| Phone Overview 2,957px (L2) | Now ≈ 2,050px flat; no sideways scroll. |
| Bundle ships pot currency (L3, L5) | Allowlist serializer + forbidden-key/value test. |
| Positions and trades shipped raw (L3) | Push-side ratios; the client never sees amounts. |
| paper.json baseline in live (L3, L5) | Effective-mode baseline; engine drawdown; R primary; live test; `pot.net`. |
| Held readings missing (L3) | Stopgap `h` from run positions + "no exit action logged"; E1 fills it. |
| Only `last_run` in the bundle (L4) | `runs`, `events`, funnel. |
| Fetched once, frozen (L4, L5) | Stamp polling, visibility checks, 30 s tick, capsule tap. |
| Record strip classes (L4) | `.k/.v/.s` + meters; profit factor "—". |
| HALT stale for hours (L5) | Push reads `state/HALT` + `HALT.since`; banner on every tab; control.yml already pushes. |

**Judge must-fixes, applied**
- Pot on the first screen (brief Result; the Pot card moves up once trades or positions exist; Shakedown is no longer last).
- Readings cutoff derived per run, never hard-coded (really Thu 12:20 pm).
- Row-4 tray collapsed to a count chip.
- Autoplay only on a changed run.
- 44px hit areas everywhere; the dial centre is clear of bead hits.
- Late escalates to bad after 2 h while holding.
- Stopgap `m` and `h` labelled unknown or not logged; template and stage tests before shipping.
- % first; prices only in sheets.
- The 1 s tick touches one node and stops when hidden; the pulse only in the due phase.
- Trust-first deploy order.
- Correct AiFi line references.
- Dial beads without glyphs, with a legend and word tips; the dial capped at 168px.
- Redundant Gate Run encodings removed (count + chips, a 6px shared-scale bar, the cluster only during a replay).
- The glow rule and the magenta tiers.
- LWC loaded lazily.
- Polling only in the due window.
- One sign convention.
- One stage vocabulary; watch-only is not violet.
- `HALT.since` instead of mtime.
- Real 2026 fixtures.
- `x` split from `!` errors.
- Row-4 subcounts.
- `elig` carries every failing code.
- UTC-slot-keyed heartbeat with merged multi-run cells.
- Linear shakedown numbers.
- Timers cleared when hidden.
- On deck never promises a buy.
- Unknown instead of normal.
- Real-iPhone Low Power Mode test.

## Data contract

# Bundle v2, KV keys, routes and engine hooks

## 1. Principles

- **Privacy boundary.** `scripts/dashboard_push.py` is the privacy boundary. It builds every payload through an **allowlist serializer**: each field below is set explicitly, and nothing from `state/` is passed through. `last_run`, `pot`, `positions` and trade records are never copied wholesale.
- **Units.**
  - Results are in R or % of pot.
  - Liquidity is a multiple of the config minimum (`vx`, `ox`).
  - Coin prices go only into `px` sub-objects, which the client shows only in sheets.
  - No field anywhere carries equity, cash, unrealized, start, peak, notional, sz, risk_amt, entry_fee, funding_paid, fees, funding, gross, pnl or margin.
- **Where equity lives.** The push holds E, the effective mode's latest equity, in memory only, to compute ratios.
- **Rounding.** Prices to 5 significant figures. % and R to 2 decimals. Ratios to 2 decimals. Timestamps inside arrays are unix seconds (int). `gen` is ISO with milliseconds (`2026-09-25T04:47:26.060Z`). Output uses `json.dumps(separators=(',',':'))`.
- **Effective mode.** `eff = last_run.mode or settings.mode`, and `req = settings.mode`. Every mode-scoped read filters by `eff`: positions, equity, trades, and refusals once they carry a mode.
- **Version.** `v: 2`.
- **Name collision.** The top-level config object is named `cfg`, not `rules`, so the forbidden-key test can ban the per-trade `rules` field everywhere.

## 2. KV keys, routes and write budget

| Key | Written | Shape | Size today → mature | Writes/day |
|---|---|---|---|---|
| `exec:latest` | every push (cycle, control, approve, review), first in the bulk call | §3 | ~9 KB → ~46 KB raw / ~11 KB gz | 6 (+0–3) |
| `exec:ledger` | every push, same bulk call | §4 | ~2 KB → ~100 KB raw / ~25 KB gz | 6 (+0–3) |
| `exec:stamp` | every push, same bulk call | `{"v":2,"gen":"…","t":1790310000}` | ~70 B | 6 (+0–3) |
| `doc:index` | only when any doc hash changed | `{slug: sha256}` | ~0.8 KB | ≈0–1 |
| `doc:<slug>` | only when its sha256 differs from `doc:index` (1 read per push) | markdown | unchanged | ≈0 |
| ~~`exec:<date>`~~, ~~`dates`~~ | removed (never read by the client) | | | −12 |

**Writes.** About 20–28 a day in total, down from about 72 today (54 of those were unchanged docs). That leaves the account's 1,000/day free-tier budget, shared with the AiFi desk, almost untouched for the follow-up `chart:<COIN>` keys.

**Push reads.** One `doc:index` read per push. The `dates` read is dropped. Line 111 (`if False`) is deleted.

**Client reads.**
- `exec:stamp`: up to 1/min per visible device during due windows (about 35 min × 6 a day), plus every 10 min otherwise. Worst case is about 350 reads a day per device, well inside 100k.
- `exec:latest`: once per new check.
- `exec:ledger`: only when Results or Signals is opened and `gen` changed.

**KV consistency.** Reads can lag by up to 60 s. The client retries `latest` 3 times at 20 s intervals when `latest.gen !== stamp.gen`.

**Worker routes** (all behind the existing cookie auth; `cache-control: no-store`):

| Route | Behaviour |
|---|---|
| `GET /api/latest` | raw text passthrough of `exec:latest` (no parse); 404 JSON if missing |
| `GET /api/ledger` | parse `exec:ledger`, set `review.html = md(review.md)`, delete `review.md`, return |
| `GET /api/stamp` | `exec:stamp`, or `{}` |
| `GET /api/doc/<slug>` | unchanged |
| `/api/dates`, `/api/day/*` | removed |

HEAD changes: two theme-color metas, and `MISSION_CSS` appended after `CSS`. There is no lightweight-charts tag; the client injects it on first need.

## 3. `exec:latest`

```
{v, gen, mode, origin, cfg, order, books, clock, state, alerts, pot, rec, risk,
 pos, names, runs, events, funnel, pinned, last24, proposals, diag}
```

**`mode`**
- Shape: `{eff:"paper", req:"paper", note:""}`
- Size: 60 B
- Source: `note` is set only when `req != eff`. It comes from the summary line matching `running paper$`, reduced to a fixed template: "exchange key missing" or "account address missing".

**`origin`**
- Shape: `{t:1790203756, mode:"paper"}`
- Size: 40 B
- Source: the first run doc of the effective mode across `state/runs/*.jsonl`.

**`cfg`**
- Shape: `{ver:"1.3", risk_pct:1, open_cap_pct:4, gross_cap_x:3, lev_cap_x:3, max_pos:6, thr:[10,20], late_min:45, sched_min:5, min_stop_pct:0.2, fee_pct:0.045, approval:"never", auto:["A"], uni:{vol_m:30, oi_m:10, days:280, fund_pct:30, lev:3}, gates:{n:30, avg_R:0.2, dd_pct:20, cost_R:0.12}, checks:[…]}`
- Size: 0.6 KB
- Source: settings.json. `uni` floors are converted to millions; they are market thresholds, not pot money.
- `gates` uses the literals above until `settings.review_gates` exists (review.py:57 should read the same key later).
- `checks` is `PRE_TRADE_ORDER`, a constant in the push: `["not halted","throttle allows entries","data fresh and run on time","no reconciliation mismatch","sizing accepted","no open position in this coin","below max positions","equity positive","open-risk cap","gross exposure cap","book open-risk cap","price sanity band","universe filters"]`. A test asserts it equals the order `risk.pre_trade` returns.
- Not shipped: `pot_usd_paper`, `min_notional_usd`, `timezone`, `online_hours`, `approval._doc`.

**`order`**
- Shape: `["BTC","ETH","AAVE","UNI","LINK","CRV","SOL","JUP","JTO","PENGU","PUMP","HYPE","BNB","CAKE"]`
- Size: 110 B → 330 B
- Source: the flattened names of the enabled books. Every `rd` and `dx` is aligned to this order.

**`books`**
- Shape: `[{b, bench, share_pct, cap_pct, on, sweep, names:[[coin, tested]], tradeable, of, why:{vol:2}}]`
- Size: 0.9 KB
- Source: books.json.
  - `tradeable` = the number of this book's names with an empty `elig`.
  - `why` counts the failing codes.
  - Real values: bitcoin 1/1 · eth-defi 3/5 · solana 2/5 · hype 1/1 · bnb 0/2.

**`clock`**
- Shape: `{last_t:1790310000, last_slot:1790308800, late_min:20, lag_med_min:21, lag_rng:[20,27], lag_n:7, limit_min:45, sched_min:5}`
- Size: 150 B
- Source:
  - `late = round((t − t//14400·14400)/60)`.
  - Median, min and max are taken over the effective-mode runs with `fresh` true among the last 42 slots. Real samples: [25,21,24,21,21,27,20].
  - Fall back to 20 when `lag_n < 3`.

**`state`**
- Shape: `{halt:{set, reason, since}, thr:{state, mult, dd_pct}, btc:{w:1, d:1}, last:{t, fresh, failed, late_min, abort}}`
- Size: 300 B
- Source:
  - `halt`: read from the `state/HALT` file, **not** from `last_run`.
    - `set` = the file exists.
    - `reason` = its text, reduced to a template word: "manual halt", "manual flatten", "open without a stop", or the scrubbed text ≤80 chars.
    - `since` = the ISO in `state/HALT.since` (new sidecar, written by scripts/control.py), else an ISO timestamp embedded in the HALT text (cycle.py:314 and flatten both write one), else `null`. `null` renders "since unknown". File mtime is never used; on Actions it is the checkout time.
  - `thr`: from `last_run.throttle`. `state` is "halted" if `halt`, "halved" if `multiplier < 1`, else "normal". If the throttle is missing, `state` is "unknown". `peak` is dropped.
  - `btc`: Bullish → 1, Bearish → 0, else null.
  - `last.abort`: the exception class name from `CYCLE ABORTED: <Type>: …` (the type only).

**`alerts`**
- Shape: `[{lv:"bad"|"warn"|"info", k, t, c, text}]`
- Size: 0–1 KB
- Source: see §6.1. Fixed templates only; no exception text, sizes or response dumps.

**`pot`**
- Shape: `{since, n_pts, chg_pct, wk_chg_pct, net, spark:[[t,pct]]}`
- Size: 0.8 KB
- Source: `EQ = L.equity_points(eff)`.
  - Base = `EQ[0].equity`. **paper.json is never read.**
  - `chg_pct = (EQ[-1]/base − 1)·100`.
  - `wk_chg_pct` is measured against the last point with ts ≤ now − 7 d, falling back to base.
  - `net` is true in paper. In live it is true only once `state/ledger/transfers.jsonl` exists (a go-live blocker). Otherwise the client hides pot % in live.
  - `spark` holds the last 42 points.

**`rec`**
- Shape: `{n, tot_R, avg_R, rel_R_avg, n_rel, closed_R, open_R}`
- Size: 100 B
- Source: the effective mode's trades; `open_R = Σ pos.r_now`. Feeds the brief and the Pot card.

**`risk`**
- Shape: `{n_open, max, used_pct, cap_pct, gross_x, gross_cap_x, stops_hit_pct, by_book:{b:{used_pct, cap_pct, share_pct, n}}}`
- Size: 0.45 KB
- Source:
  - `used_pct = Σ risk_amt / E · 100`. This is exactly the sum `risk.pre_trade` checks (asserted by a test).
  - `gross_x = Σ notional / E`.
  - `stops_hit_pct = Σ((stop−entry)/entry·notional − entry_fee − notional·(stop/entry)·fee − funding_paid) / E · 100`, where `fee = fee_pct/100`.

**`pos`**
- Size: 0 → 6 × ~450 B
- Source: §3.1.

**`names`**
- Size: 14 × ~210 B = 2.9 KB → 8.4 KB at 40 names
- Source: §3.2.

**`runs`**
- Size: 9 × ~120 B today (4 of them with readings, about +90 B each) → 60 × ~300 B = 18 KB
- Source: §3.3.

**`events`**
- Size: ~1 KB → 200 × ~70 B = 14 KB
- Source: §6.

**`funnel`**
- Shape: `{all:{…}, week:{…}}`
- Size: 0.3 KB
- Source: §5.

**`pinned`**
- Shape: `[[t, c, kind, code, val]]`
- Size: 50 B
- Source: blocked auto-grade signals, newest first. Real value: `[[1790281235,"LINK","flip","vol",0.73]]`.

**`last24`**
- Shape: `{slots:6, on_time:6, late:0, missed:0, failed:0, signals:5, bought:0, sold:0}`
- Size: 80 B
- Source: slots whose close + 45 min ≤ now, within the last 24 h.

**`proposals`**
- Shape: `[{id, c, kind, tier, expires}]`
- Source: open proposal files only.

**`diag`**
- Shape: `{unparsed:0}`
- Size: 20 B
- Source: the count of non-boilerplate summary lines that no template matched. The lines themselves are logged only in the Action run.

### 3.1 `pos[]` (one per open position of mode `eff`, sorted by `to_stop_pct` ascending)

```json
{"id":"LINK-1790400000","c":"LINK","b":"eth-defi","kind":"flip","tier":"A","t_in":1790400000,"bars":13,"as_of":1790446800,
 "r_now":1.43,"r_lock":0.41,"pnl_pct":1.43,"risk_pct":1.0,"size_pct":84.2,"lev":3,"to_stop_pct":3.21,"cost_R":0.08,
 "stops":[[1790400000,-1000],[1790446800,412]],"exits":{"h4_pct":3.21,"d_pct":null,"w_pct":null},
 "px":{"entry":13.214,"stop0":12.843,"stop":13.366,"mark":13.894}}
```

Symbols: `fee = cfg.fee_pct/100`, `est_exit = notional·(mark/entry)·fee`.

| Field | Formula |
|---|---|
| `r_now` | `((mark−entry)/entry·notional − entry_fee − est_exit − funding_paid) / risk_amt` (net if closed now) |
| `r_lock` | the same with `stop` in place of `mark` |
| `pnl_pct` | `((mark−entry)/entry·notional − entry_fee − est_exit − funding_paid) / E · 100` |
| `risk_pct` | `pos.risk_pct` (E4) else `risk_amt / E · 100` |
| `size_pct` | `notional / E · 100` |
| `to_stop_pct` | `(mark − stop)/mark · 100`; when negative the card reads "at or through the stop; checked next cycle" |
| `bars` | `(as_of − t_in)//14400`, where `as_of = last run t` |
| `cost_R` | `(entry_fee + est_exit + funding_paid) / risk_amt` |
| `stops` | milli-R: `round((p − entry)/(entry − initial_stop)·1000)`. From `pos.stops` (E4); before that `[[t_in, −1000]] + ([[as_of, Rm(stop)]] if stop != initial_stop)` |
| `exits.h4_pct` | `to_stop_pct` (the stop follows the 4-hour line) |
| `exits.d_pct`, `exits.w_pct` | from the E1 held reading (`dline`, `wline` vs mark); null until then |

Not shipped: `notional`, `sz`, `risk_amt`, `entry_fee`, `funding_paid`, cloids, `last_bar_t`, `last_funding_ts`, `upnl_pct`.

### 3.2 `names[]` (one per `order` entry, from the last run of mode `eff`)

```json
{"c":"AAVE","b":"eth-defi","st":"t","grp":"thin","w":1,"d":1,"h4":0,"rg":"O","dist":4.19,
 "vx":0.43,"ox":null,"fund":10.9,"days":1500,"elig":[["vol",0.43]],"sig":null,"px":{"close":145.61,"line":151.71}}
```

- **Directions.** `w`, `d`, `h4`: 1 is Bullish, 0 is Bearish, null means no reading. `rg` is O, I, S or null.
- **`dist`** = `(line/close − 1)·100`, a move from the last close. Positive means "needs +dist" (bearish); negative means "cushion |dist|" (bullish).
- **`vx`** = `vol_m / cfg.uni.vol_m`. `ox` stays null until E2 adds `oi_m`.
- **`elig`** lists **every** failing code with its value. Codes: `vol` (ratio), `fund` (%/yr), `days` (days); then `oi` and `lev` from E2 `reading.elig`. Real example: CRV `[["vol",0.38],["fund",67.6]]`.
- **`grp`** precedence:
  1. `held` if `st=='h'`
  2. `error` if `!`
  3. `nodata` if `x`, `n` or any null direction
  4. `notset` if `w!=1` or `d!=1`
  5. `run` if `h4==1`
  6. `next` if `elig==[]`
  7. otherwise `thin`

  Real values:
  - next: BTC, ETH, HYPE
  - thin: AAVE, BNB
  - run: UNI, LINK, CRV, SOL, JUP, CAKE
  - notset: PENGU, JTO, PUMP
- **`sig`** is "flip A" or "pullback B" when the name triggered in that run.
- **`st`** is the stage code (§3.4).

### 3.3 `runs[]` (every run doc with t ≥ now − 7 d, oldest first, cap 60; all modes, `m` marks the mode)

```json
{"t":1790296047,"s":1790294400,"lm":27,"ok":1,"x":0,"h":0,"m":"p","btc":"BB","c":[14,2,2,0,0],"n_open":0,"lv":2,
 "rd":"aatpuruudwdatu","dx":[33,44,42,-16,-87,-57,-38,-112,48,-60,116,81,34,-77],
 "tg":{"UNI":"pB","CRV":"pB"},"rx":{"CRV":[["vol",0.36]]},"hx":{}}
```

| Field | Meaning |
|---|---|
| `s` | slot, `t//14400·14400` |
| `lm` | late minutes |
| `ok` | `fresh` |
| `x` | `failed` |
| `h` | `halt` |
| `btc` | weekly + daily initials: B = Bullish, b = Bearish, n = none |
| `c` | counts: [evaluated, triggers, refused, proposed, entered] |
| `n_open` | `len(positions)` |
| `lv` | the highest event level of the run |
| `rd` | one stage code per `order` name; `null` when the run has no readings. Names not in the books at that time are `-` |
| `dx` | `dist·10` rounded (tenths of a %), per name; null when absent |
| `tg` | kind initial + tier, for triggered names |
| `rx` | the failing codes and values for `r`/`e` names, from the refusal joined on exact `t` + coin |
| `hx` | per held name: `t+0.41` trailed (r_lock after the trail), `c+2.10` closed (R), `g` data gap, `!` exit error, `?` no exit action logged (stopgap; `k` kept only from E1) |

- **The dx example** is illustrative. The push computes the real values from the readings: BTC is +3.28 at 04:20Z, and so on.
- **Real `rd` strings,** computed from `state/runs` with the refusal join, in `order`:

  | Run | `rd` |
  |---|---|
  | 2026-09-24T16:20:54Z (1790266854) | `aatutuuudwdatu` |
  | 20:20:35Z (1790281235) | `aaturuuudwdatu` |
  | 2026-09-25T00:27:27Z (1790296047) | `aatpuruudwdatu` |
  | 04:20:00Z (1790310000) | `aatuuuuudwdatu` |

  The five earlier runs have `rd: null`. Their `tg`/`rx` still come from refusals and PROPOSED lines, e.g. 04:24:55Z: JUP `r` vol 0.26, ETH `P`, HYPE `P`.

### 3.4 Stage codes (source now → source after the engine update)

| Code | Meaning | Stopgap derivation (per run, per name) | After E1/E2 |
|---|---|---|---|
| `h` | held | coin in `run.positions` (list of coins or dicts) | `reading.st` |
| `x` | not listed / no market data | summary `^{coin} \[.*\]: not listed` | `st` |
| `!` | error reading | summary `^{coin}: (candles unavailable\|entry check failed)` | `st` |
| `w` | weekly not bullish | `why == "weekly Momentum Cloud not bullish"` | `st` |
| `d` | daily not bullish | `why == "daily Momentum Cloud not bullish"` | `st` |
| `n` | 4-hour not ready | `why == "4-hour reading not ready"` | `st` |
| `a` / `t` / `u` | no signal: one flip away & eligible / one flip away & fails a check / 4-hour already bullish | `why == "no trigger on the last 4-hour bar"`, split by `h4` and `elig` | `st` + `elig` |
| `g` | signal, close not above the line | `why == "close not above the 4-hour line"` | `st` |
| `r` | blocked by a pre-trade check | trigger + refusal (t, coin) stage `pre-trade` | `st` |
| `p` | watch-only recorded | refusal stage `policy` | `st` |
| `P` | proposed (legacy) | summary `^{coin}: PROPOSED` | `st` |
| `e` | order not filled | refusal stage `execution` | `st` |
| `E` | bought | summary `^{coin}: ENTERED` | `st` |
| `m` | signal, outcome not logged | trigger with none of the above; rendered "unknown until the engine update" | `st` (no mark price) |
| `-` | not recorded | run without readings, or name absent | — |

- The why strings are the fixed constants in `signals.py` (lines 13, 15, 18, 28, 30).
- The join works because `record_refusal` and the run doc share `C.iso(self.now)`; this is verified for 12:24:17Z, 20:20:35Z and 00:27:27Z.
- Refusals with stage `proposal` are expiries at a later run. They become `expired` events and are never stage codes.

## 4. `exec:ledger` (fetched lazily by Results and Signals)

```
{v, gen,
 trades:{total, cols:["id","c","b","kind","tier","t_in","t_out","hours","R","rel_R","cost_R","pnl_pct","rsn","entry","exit","stop0","mfe_R","mae_R"], rows:[…last 300]},
 rseries:[[t_out, R, rel_R|null, book_index]],
 stats:{all:S, book:{b:S}, tier:{}, kind:{}, reason:{}},
 eq:{pct:[[t,pct]], dd:[[t,dd_pct]]},
 signals:{total, rows:[[t, c, b, kind, tier, outcome, code, val]] /*last 200*/, daily:{keys:[…], rows:[[date, n…]]}},
 verdict:{gates:[{k:"n"|"avg_R"|"dd"|"cost_R", val, target, state:"not_yet"|"passing"|"failing"}], books:[{b, n, cum_R, hold_R}]},
 sweeps:[[t, b, bench, pct_of_pot, executed]],
 review:{date, md}}
```

**Trades** (effective mode only):
- `id = coin-opened_ts`.
- `rsn` codes: stop, h4, d, w, flatten, nostop, exch.
- `cost_R = (fees+funding)/risk_amt`.
- `pnl_pct = pnl / E_close · 100`, where `E_close` is the last equity point of the same mode with ts ≤ the close ts.
- `stop0`, `mfe_R` and `mae_R` are null until E4.
- About 120 B per row.

**Stats S:** `{n, win, avg_R, tot_R, pf|null, rel_R, n_rel, hrs, streak, cost_R}`.
- Computed in R: `pf = ΣR⁺/|ΣR⁻|`, or null when there is no loss.
- They replace `L.stats`' pnl-based fields in the push.

**eq:**
- `pct` comes from the effective mode's points against its first point. Every point is kept for 30 days, then the last point of each day.
- `dd = (running peak − eq)/peak · 100`.
- Size: about 22 KB after a year.

**Signal outcomes:**

| Refusal stage | outcome | code |
|---|---|---|
| pre-trade | `blocked` | from §7 |
| policy | `recorded` | `tier` |
| proposal | `expired` | `expired` |
| execution | `notfilled` | `fill` (the raw exchange text is dropped) |
| venue | `perp` | from §7: a spot agent's long went on the perp because its spot pair failed the spot checks (2026-11-01) |
| trades opened | `bought` | — |

- Rows are filtered to `mode == eff` once refusals carry `mode` (E5). Before that, all rows are treated as paper, and in live mode only rows after the first live equity point are shipped.

**verdict:**
- `state` is `not_yet` while `n < cfg.gates.n`, except for the drawdown gate.
- `hold_R = Σ(R − rel_R)` over trades that have `rel_R`.

**review:** the newest `state/review/*.md`. The Worker renders it to `html` and deletes `md`, so the review travels once.

## 5. Funnel

`all`: every run of mode `eff`. `week`: the last 7 days. Shape: `{checks, signals, passed, auto, auto_passed, bought, blocked, blocked_auto, recorded, expired, proposed, notfilled, by_check:{code:n}}`.

| Field | Derivation |
|---|---|
| `checks` | Σ `counts.evaluated` |
| `signals` | Σ `counts.triggers` |
| `blocked` | pre-trade refusals, one per signal |
| `passed` | `signals − blocked` |
| `auto` | tier-A signals (refusals with tier A + trades with tier A) |
| `auto_passed` | tier-A signals not blocked |
| `recorded` | policy refusals |
| `proposed` | PROPOSED lines |
| `expired` | proposal-stage refusals |
| `notfilled` | execution refusals |
| `bought` | Σ `counts.entered` |
| `by_check` | keyed by the first failing reason code |

**Real `all`:** checks 124, signals 8, passed 5, auto 1, auto_passed 0, bought 0, blocked 3 (`by_check {vol:3}`), blocked_auto 1, recorded 3, proposed 2, expired 2, notfilled 0.

## 6. Events

**Row:** `[t, type, c|null, kind|null, tier|null, lv, detail|null, R|null, rel_R|null]`.
- `detail` is a short template string built from parsed parts (e.g. "vol 0.73", "132", "ConnectionError"). The client composes every sentence from its own dictionary.
- The bundle keeps the last 7 days, newest first, cap 200.

**Levels:**

| lv | Types |
|---|---|
| 3 | failed, halt, thr_halt, recon, no_stop, close_failed, exit_failed, fallback |
| 2 | bought, sold, trail, blocked (tier A), regime (BTC weekly/daily change), gap, thr_half; late when positions were open |
| 1 | recorded, blocked (tier B), proposed, expired, notfilled, resume, sweep, review, late, entry_failed, not_on_exchange |
| 0 | board (a name's w/d/h4 changed, or it entered or left `a`), derived by diffing consecutive runs with readings; suppressed when the same coin has another event in that run |

**Stopgap parsing** (summary lines of the runs in the window; templates mirror cycle.py; after E3, `run_doc.events` is copied directly and this path switches off):

| cycle.py line | Pattern (anchored) | type |
|---|---|---|
| 142 | `^(\S+) \[(.+?)\]: closed on (.+?) at \S+ → ([+-][\d.]+) R(?:.*?([+-][\d.]+) R vs)?` | sold |
| 243 | `^(\S+): stop trailed to ([\d.e+-]+)$` | trail (converted to R with the position's entry and stop0) |
| 355 | `^(\S+): ENTERED ` (kind and tier parsed from `describe()` output; pinned by test) | bought |
| 425 | `^(\S+): signal (flip\|pullback) tier ([AB]) REFUSED: (.*)$` | blocked (reasons via §7) |
| 433 | `^(\S+): signal (\w+) tier ([AB]) recorded, not traded` | recorded |
| 450 | `^(\S+): PROPOSED ` | proposed |
| 468 | `^(\S+): proposal \S+ expired unapproved` | expired |
| 343 | `^(\S+): entry not filled` | notfilled |
| 113 | `data (\d+) min after the bar close` + `fresh==false` | late |
| 478 | `^CYCLE ABORTED: (\w+)` | failed (type only) |
| 460 | `^HALT set` (deduped across runs) | halt |
| 472 / 474 | `^THROTTLE HALT` / `^throttle: drawdown ([\d.]+)%` | thr_halt / thr_half |
| 226 | `^(\S+): no reading on one timeframe` | gap |
| 273 | `^RECONCILIATION MISMATCH` | recon (detail dropped) |
| 310 | `^(\S+): could not place the resident stop` | no_stop |
| 156 | `^(\S+): close NOT filled` | close_failed |
| 205 | `^(\S+): exit management failed \((\w+)` | exit_failed |
| 365 / 378 | `entry check failed \((\w+)` / `candles unavailable` | entry_failed |
| 195 | `not on the exchange and no sell fill` | not_on_exchange |
| 183 | `^(\S+): gain earmarked for (\S+) \(([\d.]+)% of pot\)` | sweep |
| mode | `running paper$` | fallback |

- **Boilerplate lines** (113's BTC line, 489's counts line, 396's per-name reading lines) are recognised and skipped.
- **`resume`:** the HALT file disappears between consecutive runs (`run.halt` true then false).
- **`regime`:** the BTC weekly or daily initial changes between runs.
- **`sold`** rows are cross-checked against trades.jsonl, which is the source for R and rel_R.

### 6.1 Alerts (built from the last run doc plus the HALT file; time-based late and stale states are computed by the client)

| k | lv | Source | text template |
|---|---|---|---|
| failed | bad | `last_run.failed` | "The {time} check stopped early ({Type}). Exits may not have been checked." |
| halt | bad | HALT file | "Halted{ since {time}}: {reason}. No new buys; exits still run." |
| thr_halt | bad | throttle halt | "Drawdown {dd}% reached {limit}%: buying stopped until reviewed." |
| thr_half | warn | multiplier < 1 | "Drawdown {dd}%: risk per trade halved." |
| fallback | warn | req ≠ eff | "Live requested, running paper: {note}." |
| late | warn | `fresh==false` | "The last check started {n} min after the close; buys skipped." |
| recon | bad | 273 | "Exchange and ledger disagree; entries paused." |
| no_stop / close_failed / exit_failed | bad | 310 / 156 / 205 | "{coin}: …" fixed sentences |
| gap / entry_failed | warn | 226 / 365 / 378 | fixed sentences |
| proposals | info | open proposals | "{n} legacy proposal(s) open." |

### 6.2 Scrubber
No free text is shipped. Every string comes from a template, and the only variable parts are: coin tickers, codes, numbers that are % / R / ratios / minutes, and exception class names. The push asserts every outgoing string against the forbidden-string pattern (§8) before writing.

## 7. Reason codes (normalised refusals)

**Universe filters** (sub-parsed from the detail):

| Pattern | Code | Value |
|---|---|---|
| `24h volume ([\d.]+)M below (\d+)M` | `vol` | the ratio a/b |
| `open interest ([\d.]+)M below (\d+)M` | `oi` | the ratio |
| `funding (\d+)` | `fund` | %/yr |
| `(\d+) daily bars` | `days` | days |
| `max leverage (\d+)` | `lev` | the leverage |
| not listed | `list` | — |

**Other pre-trade checks:** not halted → `halt` · throttle → `thr` · data fresh → `fresh` · reconciliation → `recon` · sizing → `sizing` · already held → `dup` · max positions → `maxpos` · equity positive → `equity` (detail dropped) · open-risk cap → `cap` · gross → `gross` · book cap → `bookcap` · price sanity → `sanity`.

**Other stages:** policy → `tier`; proposal → `expired`; execution → `fill`; approval → `drift` / `recheck`.

## 8. Tests and fixtures (part of this pass)

**`tests/test_dashboard_bundle.py`** builds all three payloads from a temp state dir. Fixture contents:
- paper pot **1234.56**, live pot **377.19**;
- 2 open positions with a stop history;
- 5 closed trades;
- refusals of every stage, including an execution failure with a resp dump;
- a HALT file + `HALT.since`;
- a failed run doc;
- a run with a reconciliation mismatch.

The copies of the real `state/runs/*.jsonl` and `refused.jsonl` sit in `tests/fixtures/real/`. The test asserts:

1. **Forbidden keys.** Walking every JSON tree, no key matches `^(equity|cash|unrealized|start|peak|notional|sz|risk_amt|entry_fee|funding_paid|fees|funding|gross|pnl|margin|min_notional_usd|pot_usd_paper|stop_cloid|entry_cloid|last_bar_t|last_funding_ts|rules|context_at_entry|review_md|timezone|hours_local|_doc)$`.
2. **Forbidden values.** No number equals the fixture pots or any fixture notional, risk_amt, pnl or fee.
3. **Forbidden strings.** No string matches `/\b(USDC|USD)\b|\$\s?\d|equity \d|\bsz\b/`.
4. **Open risk.** `risk.used_pct` equals the open-risk figure `risk.pre_trade` computes for the same positions.
5. **Live baseline.** With `mode=live`, `pot.chg_pct` uses the first **live** equity point, `paper.json` is never opened (it is deleted in the fixture), `state.thr.dd_pct == last_run.throttle.drawdown_pct`, and `pot.net == false`.
6. **Halt.** `state.halt.set` reflects the file even when `last_run.halt` is false, and `since` comes from `HALT.since`.
7. **Stage codes.** The real `rd` strings equal the four values in §3.3, and `funnel.all` equals the real values in §5.
8. **Check order.** `cfg.checks` equals the check order returned by `risk.pre_trade` on a fixture candidate.

**`tests/test_dashboard_events.py`:** one line per cycle.py format string in §6 is rendered with sample values and must parse into the exact event tuple. It also asserts `diag.unparsed == 0` for the real run docs. A reworded `say()` fails CI.

**`scripts/dashboard_demo.py`** plus a `--kv-json <file>` flag on the push write `cloud/dev/kv.json` from a seeded **mature** state:
- 40 names;
- 6 positions with stop histories;
- 300 trades, with one book past 30;
- 60 runs, including late, failed, halted, throttle-halved and missed slots and a two-run slot;
- 200 events.

`cloud/dev/preview.mjs` already documents both.

## 9. Size summary

| Payload | Today | Mature (40 names, 6 pos, 300 trades, 1 y) |
|---|---|---|
| `exec:latest` | ≈9 KB raw / ≈2.5 KB gz | ≈46 KB raw / ≈11 KB gz |
| `exec:ledger` | ≈2 KB | ≈100 KB raw / ≈25 KB gz |
| `exec:stamp` | 70 B | 70 B |

## 10. Follow-up engine pass (NOT in this build; the push reads each field when present)

- **E1, held readings.** In `manage_exit`, append `{coin, book, st:'h', weekly, daily, h4, line, dline, wline, close, mark, stop, action:'kept'|'trailed'|'closed'|'gap'}`. Unlisted and no-candle names get `st:'x'`/`'!'` rows with a reason. This fills `hx` with `k`, and `exits.d_pct` / `exits.w_pct`.
- **E2, per-name outcome and eligibility.** `find_entry` sets `st` at every return (including `m` for no mark), runs `U.check` for every name (no extra API call), and stores `elig` codes and values, `oi_m`, `maxlev`, `dline`, `wline`, `up`, `lo`.
- **E3, run doc.** Add `late_min`, `secs`, `halt_reason`, `mode_req`, `mode_note`, `open_R`, and `events` via `Cycle.ev()` next to each `say()`.
- **E4, positions and trades.** Store `risk_pct` and `stops` on the position (append on every trail). `build_close` adds `id`, `initial_stop`, `stops`, `risk_pct`, `mfe_R`, `mae_R`.
- **E5, refusals.** Add `mode`, `book`, `stop`, `signal_close`, `bar_t`, and the **full** checks list.
- **E6, source scrubbing.** Reconciliation and IOC messages give relative differences; the equity check detail drops its value.
- **Later, chart pass.** The cycle writes `state/.cache/chart_<COIN>.json` from its Bars cache. The push uploads `chart:<COIN>` only when `bar_t` changed, behind a `kv:writes:<date>` guard (skip charts above 600/day). The worker adds `/api/chart/<COIN>`.
- **Go-live blocker.** `state/ledger/transfers.jsonl` must exist (Hyperliquid non-funding ledger updates), so that `pot.net` becomes true.

## Acceptance criteria

- Bundle privacy: `python -m pytest tests/test_dashboard_bundle.py tests/test_dashboard_events.py` passes. It covers forbidden keys, values and strings; the live baseline; halt read from the file; `used_pct` equal to `pre_trade`; the real `rd` strings `aatutuuudwdatu` / `aaturuuudwdatu` / `aatpuruudwdatu` / `aatuuuuudwdatu`; the real funnel 124/8/5/1/0/0; the check order; and `diag.unparsed == 0` on the real run docs.
- In the preview, devtools Network → `/api/latest` and `/api/ledger` responses contain no key named equity, peak, start, notional, risk_amt, pnl, fees, rules, timezone, hours_local or review_md, and the string `1000.0` never appears.
- At 390×844, dark and light, with the real bundle, the first screen without scrolling shows: the capsule reading 'On schedule' plus an age; the verdict pill 'All clear' with 'nothing needs you'; the moment row naming LINK blocked at Thu 4:20 pm with a 'Since then' line (cushion 8.7%, volume 1.12× the minimum); the dial countdown; and the brief Result cell 'Paper +0.00%'. The Gate Run head is at or just below the fold.
- The phone topbar shows the Ex mark, the capsule, a violet 'Paper' pill and the theme button. No 'pushed X ago' appears. The tab title is visually hidden but present for screen readers. The page has exactly one h1.
- Tapping each tab in the phone tab bar highlights it in magenta (aria-current=page) and scrolls to the top. On desktop the rail pill slides to the active item. Keys 1–5 switch tabs. `#overview`, `#book`, `#trades`, `#refused` and `#logic/risk` redirect to their new tabs.
- Status engine, using a demo bundle with `last.failed=true`: the capsule reads 'Failed' with a red dot, and a red banner quoting 'stopped early (ConnectionError)' appears at the top of all five tabs. With a HALT file set, the capsule reads 'Halted' and the banner shows the reason and 'since' (or 'since unknown'). Removing HALT and re-pushing clears the banner within one stamp poll or a capsule tap.
- Clock phases, set by overriding Date.now in devtools against the real bundle: at C+10 min the dial centre counts down to ≈ C+21 min. At C+25 the capsule says 'Due now' and the next bead pulses (no pulse with reduced motion). At C+50 it says 'Late · …' in amber. At C+4h it says 'Stale' in red. With a demo bundle holding positions, it goes red as 'Exits unchecked' from C+2h.
- The countdown updates each second and changes only one text node (the DevTools Elements panel flashes only that node). After switching to another tab or app and back, all timers resume from the real clock, and a stamp check fires immediately (visible in Network).
- Stamp polling: while visible in the due window, `/api/stamp` is requested about every 60 s. Outside it, about every 10 min. After 3 simulated failures it backs off to 5 min. No `/api/stamp` requests happen while the page is hidden.
- Arrival: replacing `exec:stamp` and `exec:latest` in `cloud/dev/kv.json` with a newer gen makes a bottom toast 'Check … landed · …' appear within one poll. The next dial bead fills and pulses once, the Gate Run replays the new run (only if it differs from the previous one), new Latest rows show a 'new' dot, and scroll position is kept.
- Gate Run for Thu 8:27 pm (picked from the cycle bar): 14 → 13 (PENGU chip at Weekly) → 11 (JTO, PUMP at Daily) → 2 at 4-hour signal, with a collapsed '9 names · show' chip and the caption '5 one flip away, 4 already running' → 1 (CRV chip 'volume 0.36×', warn edge, at Safety checks) → 0 (UNI 'watch-only' at Grade) → Bought 0.
- Gate Run for Thu 4:20 pm shows LINK stopped at Safety checks with 'volume 0.73×', and the rows below are dimmed to 45% with '—'. For Fri 12:20 am it shows 14 → 13 → 11 → 0 and the link 'Quiet check. Last check with a signal: Thu 8:27 pm ›', which selects that check.
- Gate Run for any check before Thu 12:20 pm (e.g. Thu 12:24 am) shows counts-only mode. The weekly and daily rows are hatched 'not recorded'. The caption reads 'per-name readings start Thu 24 Sep, 12:20 pm' and is derived at runtime, not hard-coded. JUP appears at Safety checks with 'volume 0.26×', and ETH and HYPE at Grade as 'proposed (old model)'.
- The Gate Run replay plays once, only for a newly seen, different check, and only when the card is at least 50% in view. Tapping the card skips to the final state. The dot cluster exists only during the replay. With reduced motion there is no autoplay, and 'Step ›' reveals one gate per tap.
- Every chip, cycle-bar button, dial bead, heartbeat cell and '?' tip has a hit area of at least 44×44 px (check with devtools box model plus the ::before inset). Bead hit areas do not cover the dial's centre text.
- On deck (real bundle) shows 'Could signal next': BTC needs +3.3%, ETH +4.4%, HYPE +8.1%. 'Armed, too thin' shows AAVE +4.2% (volume 0.43×) and BNB +3.4% (volume 0.25×). 'Already running · 6' is collapsed, and CRV inside it shows both 'volume 0.38×' and 'funding 68%/yr'. 'Not set up · 3' lists PENGU (weekly), JTO and PUMP (daily). No tile says 'buys' and no coin price appears.
- Selecting Thu 4:20 pm on the cursor switches On deck to 'As at Thu 4:20 pm, recorded' with a 'Back to now' control. The tape column for that check is outlined, and LINK is shown in the blocked state.
- Activity › Heartbeat shows 7 rows × 6 columns labelled in local time. Two amber 'late' cells for Wed 6:49 pm and Wed 10:12 pm are the 169 and 132 min runs, the rest are on time, and cells before the first run are blank. The punctuality line reads 'Usually 21 min after the close (20–27) · limit 45'. Tapping a cell opens the cycle sheet with that Gate Run.
- Activity › Signals: the funnel reads 124 → 8 → 5 → 0 → 0, with side rows Blocked 3 (volume 3), Recorded watch-only 3, Expired 2 and Not filled 0. The side rows sum to 8. 'Would have traded' pins LINK. Every bar has a visible coloured fill with its word label, and bars animate with scaleX.
- The name sheet for LINK (tap any LINK chip) shows W/D/4h in words, the cushion, the filters with ✓/✕ ratios, its 42-cell tape row, and check lights for its Thu 4:20 pm refusal. 'Universe filters' is lit red and expanded, and the other checks are dashed 'not recorded', never green. Coin prices appear only here, captioned 'market prices, not your money'.
- Positions with the real bundle: the flat empty state names BTC as closest (+3.3%), with no empty table. The risk budget shows 0% of 4% with book cap ticks, 6 empty pips, and a drawdown gauge with ticks labelled 'risk halves' at 10 and 'stops buying' at 20. The books list reads bitcoin 1/1, eth-defi 3/5, solana 2/5, hype 1/1 and bnb 0/2 ('volume').
- Positions with the demo bundle: cards are sorted by stop distance ascending. Each leads with open R ('+1.43 R open') and '% of pot', with 'stop x% below · locks in +y R'. The R-ladder shows first-stop, entry and stop ticks and the mark bead. Exposure and leverage sit on a secondary line with a tip. The page has no 'Unrealised' or 'To stop' labels.
- Results with the real bundle: no chart library request appears in Network until Results opens. The verdict card reads 'Too early to judge: 0 of 30 closed trades' with four go-live gates marked 'not yet'. The curve area shows 'The first closed trade starts this line…'. Cards carry 'Paper'.
- Results with the demo bundle: the R curve (baseline around 0) has local-time axis labels and a dashed holding line. The record strip tiles show 26px values with n/30 meters. Profit factor shows '—' when there are no losses. Trades are cards on phone and a table at 900px or wider, with 'Latest 300 of N'.
- Rules shows plain-sentence rules taken from the bundle's `cfg`, a glossary that includes Auto grade, Watch-only grade, cushion and needs, and a single-row scrolling `.seg.quiet` doc nav. In 'How it works' the numbered lists run 1, 2, 3 with no orphaned wrapped lines. Log out is present on phone.
- No horizontal page scroll at 344, 375, 390, 412, 700, 884, 1024 and 1440 px in either theme, including a live resize from 884 to 344. Tables appear only inside disclosures or at 900px or wider, and have a right-edge fade when they overflow.
- Light theme: pill text in green, amber and red measures at least 4.5:1 against its surface. The iPhone status bar colour follows the theme (two theme-color metas). The Ex brand mark gradient runs magenta to violet with no cyan.
- Magenta audit: solid magenta appears only on bought or sold marks, stop-raised marks, the dial arc, hand and next bead, the due countdown and the Bought gate. Coin chips, the active nav and Auto grade pills use magenta as text or outline only. Watch-only items are neutral grey, not violet. Only the verdict pill glows.
- Missing-data robustness: loading a demo bundle with `state.thr`, `names` and `runs` deleted shows 'unknown' or '—, not in this data' in those panels, and every other panel still renders. `v:1` shows the quiet 'newer than its data' note. A 401 shows 'Signed out' with Sign in, and offline shows 'Can't reach the dashboard' with Retry.
- On a real iPhone in Low Power Mode, in both themes: the Gate Run replay, tape Play and a tab change run without visible jank, and `.bg` drift pauses while hidden or replaying. The Now tab is interactive within about 1 s on LTE.
- KV writes: one cycle push, observed in the Action log or with a dry-run counter, writes exactly `exec:latest`, `exec:ledger` and `exec:stamp`, and writes `doc:*` only when a doc's hash changed. It never writes `exec:<date>` or `dates`.
- The demo mature bundle (40 names, 6 positions, 300 trades, 60 runs) renders every tab. Gate Run trays collapse muted groups larger than 6. Tape rows group by book. Latest folds quiet checks. `exec:latest` stays at or under 50 KB raw.

## Build plan

1. 1. Fixtures and demo (tests/fixtures/real/ with copies of state/runs/*.jsonl, refused.jsonl and equity.jsonl; tests/fixtures/synthetic builder; scripts/dashboard_demo.py; the --kv-json flag in scripts/dashboard_push.py). This makes the empty present and the full future available to every later step.
2. 2. Bundle v2 (scripts/dashboard_push.py). Build an allowlist serializer for exec:latest, exec:ledger and exec:stamp: effective-mode baseline, cfg including PRE_TRADE_ORDER, clock lag stats, state with halt read from the HALT file and HALT.since, alerts, pot/rec/risk/pos/names computed as ratios, runs with rd/dx/tg/rx/hx via the why-constant mapping and the exact-t refusal join, the event template parser plus board and regime diffs, funnel/pinned/last24, the reason-code normaliser, the scrubber assert, and hash-gated doc writes. Remove exec:<date>, dates and the dead line 111.
3. 3. HALT sidecar (scripts/control.py, 3 lines): --halt and --flatten write state/HALT.since with C.iso(), and --resume deletes it. control.yml already pushes the dashboard after the change.
4. 4. Tests (tests/test_dashboard_bundle.py, tests/test_dashboard_events.py): forbidden keys, values and strings; live baseline; halt; used_pct equal to pre_trade; the real rd strings and funnel; the check-order assertion; one fixture per say() template; diag.unparsed == 0. These must pass before any client work ships.
5. 5. Worker (cloud/worker.js): /api/latest passthrough, /api/ledger with md rendered to html and md dropped, /api/stamp, /api/dates and /api/day removed; NAV with 5 tabs and new icons; rail brand demoted from h1; tablet labels use .vh; two theme-color metas; import MISSION_CSS; md() indented-continuation fix; remove the topbar 'pushed' element.
6. 6. CSS module (cloud/mission.js; one comment fix in cloud/design.js): motion tokens, contrast tokens, brand gradient, .bar .fill / td.empty / th / tip / ul.list / .vh / paused .bg fixes, the ported .brief and .bmeter, and every new component class plus the .st-<code> vocabulary classes.
7. 7. Client core (cloud/client.js, sections core/data/shell): fmt with Intl and the number rules, val()/safe(), STAGE and GLOSS maps, ports from ~/SproutHouse/trading/aifi-desk/cloud/client.js (reduced 21, setSeg 311, initSegs 318, countUp 368, stagger 376, movePill 379, route 391, keydown 401) with redirects, boot with error branches and version note, the status engine and clock model, capsule plus rail mirror, alert rail on every tab, stamp polling with backoff, 1 s and 30 s timers cleared when hidden, delegated sheet and tip wiring with 44px hit areas.
8. 8. Now tab, trust content (cloud/client.js): mission card with verdict, moment, since-you-last-looked (with the sold row) and brief (Result, Buying, Exposure, Last 24 h); Holding; the Pot/Shakedown card with the flat dot-line; On deck groups and tiles; Latest with folding and levels. Use a static dial placeholder (countdown text only) until step 13.
9. 9. Positions, Activity (timeline and Signals), Results and Rules tabs (cloud/client.js): position cards with R-ladder and trail sparkline; risk budget; books; proposals; timeline with filters and the new marker; Signals funnel, pinned list, outcome list and reason bars; Results verdict/gates, loadLWC() curve, record strip, R per trade, trades cards/table, review; Rules in-force sentences, glossary, .seg.quiet docs, Log out.
10. 10. DEPLOY 1, trust release (deploy-dashboard.yml plus the next cycle push). Verify acceptance items for privacy, the first screen, status, clock phases, tabs, robustness, contrast and no horizontal scroll against the real bundle and the demo bundle. Update docs/DASHBOARD.md (tabs, capsule states, KV keys, routes, what 'Late/Stale/Exits unchecked' mean).
11. 11. Gate Run and shared cursor (cloud/client.js, cloud/mission.js): the gateRun() component with the cycle bar, gate mapping, survivor maths, trays with collapse rules, row-4 subcounts, counts-only/failed/late variants, choreography with a skip on tap, autoplay rules (new, different, in view, visible, not reduced), Step mode; S.cursor setters and followers; the cycle sheet with previous/next; the name sheet with check lights (unrecorded checks dashed).
12. 12. Activity replay pieces: heartbeat keyed by UTC slot with local labels and merged multi-run cells, the punctuality line, the board tape with Play/scrubber/mini funnel, On deck as-at mode, the All readings disclosure, the Health sheet punctuality strip opened from the capsule.
13. 13. Cycle clock dial (cloud/client.js, cloud/mission.js): SVG face, beads at actual run times without glyphs, next bead at C+lag, solid progress arc and dashed remainder, hand on the 30 s tick, centre overlay phases, legend, 44px circular bead buttons opening word tips with 'Replay this check', due-phase pulse only.
14. 14. Arrival moment and motion polish: diff old vs new bundle, toast (with '↑ See it' when scrolled), bead fill and one pulse, conditional Gate Run replay, new-row rise and dots, countUp on changed numbers only, ladder bead slide from localStorage, the Activity tab dot; reduced-motion paths for everything.
15. 15. QA and DEPLOY 2: layout audit at 344/375/390/412/700/884/1024/1440 in both themes plus the live resize; a real iPhone home-screen install in Low Power Mode (timers, pageshow, jank); a DST test with Date overrides (heartbeat columns, dial); the demo mature bundle; the full acceptance list; then deploy. Open follow-up issues for the engine pass (E1–E6) and the chart pass.

## Considered and left out

- Proposal 2's money-first Cockpit with the Position Deck as the first screen. Today it would show a first screen of zeros (+0.00%, 0 of 4%, 0.0%, six empty slots) and move 'what is it doing' one tap away. Kept from it: the flat pot dot-line, the drawdown ticks, slot pips, 'Too early · leading by' pills, the sold-since row, due-window polling and the ledger split.
- Proposal 3's spine, sticky scrub ribbon and board drawer as the home tab. On a phone the stacked sticky chrome takes about 290px, ribbon ticks are about 6px wide, and the IntersectionObserver/programmatic-scroll feedback loops are fragile in iOS Safari. Kept from it: the shared cursor, the moment row, since-you-last-looked, event levels, board events, the Health sheet, check lights, lazy chart loading and the parser test.
- Engine additions E1–E6 (held readings, per-name st/elig, run_doc.events, stop history, richer refusals and trades) in this pass. They are outside a dashboard-only pass. The push reads each field when present, and until then the stopgaps are labelled ('no exit action logged', 'outcome not logged', 'not recorded').
- chart:<COIN> keys, name-sheet candle charts with cloudPrimitive, R-space position mini charts and %-from-close On deck charts. They need the cycle to write a chart cache from its own Bars (an engine change), would add 84–240 KV writes a day, and add iPhone rendering load. Deferred to a chart pass.
- The kv:writes:<date> guard. Without chart keys the pass drops writes from about 72 to about 25 a day, so a guard would cost more than it saves. It ships with the chart pass.
- The runs:<date> archive and 'Load earlier' beyond 7 days. The 7-day window in the bundle covers the heartbeat, tape and timeline, and the archive adds writes and routes for little present value.
- trade:<id> replay archives and the per-trade replay scrubber. They need pos.track and stop history from the engine (E4).
- What-if or hypothetical R for blocked and watch-only signals. It could be read as a real result even when hatched, and it needs stop and signal_close on refusal records. It deserves its own decision.
- A blue-chip price overlay on the pot % chart. It needs benchmark marks per run, and the holding-equivalent R line (Σ(R − rel_R)) already answers 'beating holding?' in the right unit.
- The raw engine log in the cycle sheet. Free-text summary lines can carry sizes or equity in live mode, and typed events plus the Gate Run replace it.
- Log-scaled shakedown bars. Log scale on small counts implies proportions that are not real, so the numbers are printed plainly.
- Glyphs inside dial beads (+ − ↑ !). At 13–18px they cannot be read. Words go in bead tips, the legend and aria-labels.
- A standing accent glow on bought chips and acted beads. It breaks AiFi's rule that only the big status pill glows; a single pulse on arrival replaces it.
- Violet for watch-only items. It collides with the violet PAPER pill, so watch-only uses neutral ink-2.
- Radar chart and ribbon Sankey (audit opportunities). They cannot be read at 300px, have empty polygons at n=0, and use colour-only encoding.
- HALT 'since' from the file mtime. On GitHub Actions that is the checkout time; it is replaced by the HALT.since sidecar and ISO timestamps already embedded in the HALT text.
- A hard-coded 'readings start' date in the UI copy. Counts-only mode is derived per run from rd == null, and the date is formatted at runtime (the proposal's '4:20 pm' was wrong; it is 12:20 pm).
- Proposal 2's compact rows for 7–12 positions and the sort control above 12. max_positions is 6.
- Shipping settings.timezone and hours_local. The phone's own timezone formats every time, and the location hint is kept out of the bundle.
- A lightweight-charts script tag in HEAD. The Now tab never uses it, so it is injected on first need.
- aria-live on the countdown and an unconditional 60-second poll. They are noisy for screen readers and waste battery; only the capsule is live, and polling is limited to the due window.
- The transfers ledger (deposits and withdrawals) in this pass. It is exchange and engine work. It is flagged as a go-live blocker through pot.net, and the page hides pot % in live mode until it exists.
