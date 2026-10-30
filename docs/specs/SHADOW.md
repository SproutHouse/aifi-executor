# Shadow experiment: the long-short book (agent `shadow-01`)

_Built 2026-10-18 on the owner's decision: "paper-trade it as a shadow". Paper only. No real money, ever, for this bot._

## What and why

The AiFi Lab's best near miss of research wave 2 is recipe **ls-759fac45** (lab family `ls_xs`): residual momentum
against Bitcoin, market-neutral long-short, on the top 30 coins of each day, with book-level risk. Its lab verdict is
**failed**: it missed only the worst-regime floor (the crash years). The owner chose to paper-trade it anyway as an
unofficial experiment: paper is the real exam. The verdict stays failed.

So `shadow-01` ("S01 Shadow") is:

- **paper only, never live**, enforced three times: `cycle.resolve_mode` keeps any agent marked `shadow` (or any
  long-short book) in paper whatever its settings say (`cycle.paper_only`); `scripts/go_live.py` refuses it before
  anything else, and the override phrase `LIVE WITHOUT READY <agent>` does not apply (even a forged lab Ready is
  refused); `scripts/approve.py` and the server's request runner (`run_requests.py`) refuse it outright. There is no
  live short order path in the engine at all: `manage_book` trades nothing outside paper. `tests/test_longshort.py`.
- **never an arena bot, a survivor, a fleet member or Ready**: its row in `agents/index.json` has a `shadow` block and
  no `arena` block. The lab's arena roster skips it (even if an `arena` block were written into its row), the lab's fleet
  excludes it and leaves its equity out of the fleet totals, and the shortlist (Ready) is built from arena bots only.
- **labelled plainly on the dashboard**: its Command Center tile carries the chip "Shadow" and the line "Shadow
  experiment: failed the lab's crash check; paper only"; its Overview carries the pill "Shadow experiment · paper only"
  and the same line with the recipe id and the lab verdict. Its trades read "Opened"/"Closed" on the tile and
  "Bought"/"Shorted"/"Sold"/"Covered" per leg in its event log. Only % of pot and R, never money.

To stop it: `agents/index.json` → `"enabled": false` (it is then shown under Retired), after `control → flatten shadow-01`.

## The rule (src/executor/longshort.py, the lab's lab/lsbook.py `ls_targets` for these settings)

Settings: `agents/shadow-01/settings.json` → `target` (the recipe's own parameters, unchanged).

1. **Every 7 days** (epoch day number divisible by 7, as the lab), rank the day's eligible coins by **residual momentum
   against Bitcoin**: the sum of the last 21 daily residual returns (beta from the last 90 days) over the residuals'
   own noise.
2. With m ranked names and k = floor(0.3 × m): the **long leg** is the best-ranked names of the upper half the engine
   could buy today, at most k; the **short leg** the worst-ranked names of the lower half it could short today, at most
   k. "Could enter" is decided per name and side **before** the legs are formed (gates v7, review R1): the funding filter
   (a long is refused while funding is above +30%/yr, a short while it is below −30%/yr), the universe filters (24h
   volume and open interest at least $1M, max leverage at least 3x) and the price sanity band. A refused name is
   replaced by the next one on its side, so the book never becomes a naked one-sided bet.
3. **Equal dollars per side** (long leg +0.5, short leg −0.5 of equity, equal weights inside each leg), then the whole
   book is scaled to a **20%/yr portfolio volatility target** from the sample covariance of the last 90 daily returns,
   capped at a **gross 2x**. Fewer than 12 rankable names, or a leg left empty: no book that week (flat).
4. **Between rebalances nothing trades**: the weights drift. On a rebalance day a name moves only when it is more than
   25% off its target (the band); a name that leaves the book closes; a name that changes side closes, then opens.
5. **Book drawdown brake**: when the agent's equity falls 15% below its running peak, every position closes and the
   book stays flat for 28 days; it re-forms at the first rebalance after that, its peak reset to that day's equity
   (`book.json` in its state holds the peak and the brake).

Order of work in a daily run (`cycle.manage_book`): the catastrophic stops and funding (`manage_target_stops`), a held
coin Hyperliquid no longer lists closed at its last mark, the brake, then on a rebalance day the day's decision (the
universe, the per-side refusals, the book) and the trades: exits and trims first (they never wait), then opens and
growth, which pass the pre-trade checks.

### One decision per rebalance day

A daily agent runs up to three times after the close (00:05, 01:05 and 02:05 UTC), and the funding it reads moves
between those runs. Until 2026-10-30 each run re-formed the legs from its own reading, so a name crossing the funding
line closed one name and opened another: on 2026-10-30 a quarter of the week's book changed after 00:05 (lab audits
2026-10-23 E3 and 2026-10-30 N3). The lab models one reading, just after the close (about 00:08 UTC, `lab/pit.py`
`funding_reading`), so the book is now **decided once**:

- The **first fresh run** of a rebalance day decides: the universe, the per-name and per-side refusals, the legs and
  their target weights. It saves that decision in `book.json` (`last_rebalance`: `weights`, `decided`, and `pending`,
  the names not traded yet) **before** it trades, so a run that stops part-way leaves it to be finished.
- **Later runs that day re-decide nothing.** They keep the decided legs and weights and only finish the decision: an
  open or growth that was refused (a halt, a check) or a name that had no mark is retried at its decided weight of the
  current equity; a name held against the decision (a close that was missed) closes. Every other name keeps what the
  first run left, without a band check or a re-size. Delisting closes and the brake apply on every run, as before.
- A run whose data is **not fresh** never decides: positions are kept, and the first fresh run decides.
- The next rebalance day decides afresh from its own reading.

The lab's replay runs one run a day, so the deciding run is the one it measures; its trading is unchanged.

### Visible refusals and the second source

Every name refused at leg formation is said in the run summary ("refused at leg formation", with its reasons), counted
in the run's refusals, recorded in the refusal ledger (stage `leg formation`, the failed checks) and kept in
`book.json` (`refused_long`, `refused_short`). The price sanity band needs a second source: Binance's price counts
only while its USDT pair trades and its last trade is under an hour old (`binance_data.py`). LITUSDT and XMRUSDT are
halted on Binance (status BREAK) and kept serving prices frozen at 0.743 and 118.7, 3 to 4 times off Hyperliquid, so
until 2026-10-30 LIT and XMR were refused on both sides at every rebalance (audit E1). Names with no second source (a
halted or stale pair, no Binance pair at all, e.g. kPEPE and VVV) pass the band unchecked, as before (it fails open);
the run summary lists them with the reason, and `book.json` keeps them (`unchecked`, audit E10).

### Point-in-time universe, live

The lab ranks Binance spot pairs, dead coins included, by trailing 30-day median daily quote volume, known the day
before. The engine can trade only Hyperliquid perps, so it ranks **Hyperliquid's listed perps by their own trailing
30-day median daily notional volume** (base volume × close, from Hyperliquid's free daily candles), using the 30 days up
to the day before the decision, with at least 60 daily bars; the top 30 are the universe. A name is eligible on the
decision day when it is listed (not delisted) and traded at least $1M that day (the lab's floor for these books).
Shortable = listed on Hyperliquid and not delisted. Bitcoin is always read (the score needs it). To spare the API,
only the 90 perps busiest by 24h volume (and every held name) are read; the ranking is computed on rebalance days only.

The two rankings differ: on the last 240 days about 22 of the 30 names are the same each day (the lab's Phase 0 reports
the current overlap and replays the engine on its own universe end to end).

## Book risk and the catastrophic stop

The lab's book mode has **no per-name stop**: the volatility target and the brake control risk. The engine's safety
model never holds a position without a resident stop (live, it is what protects a position on the exchange while the
server is down), so each name still carries a **catastrophic stop 100% beyond its average entry**: a short closes if
its price doubles; a long's stop sits at zero and never fires. It is an engine rule, not part of the strategy. The lab
replayed the engine with it: since 2024-01 it fired once (a short); a 50% stop would have fired 22 times and cut the
book's return far below the lab's, so 100% was chosen. For this paper-only bot it protects no exchange position.

## Paper ledger (shorts)

A short keeps a positive size and `"side": "short"`: it is sold below the mark (slippage), gains as the price falls, has
its stop above its entry, and **receives funding while the rate is positive** (pays it when negative). With
`target.funding = "history"` the book's ledger accrues **Hyperliquid's actual hourly funding** of each name since its
last accrual (`funding_history`) on its value at the mark, instead of the rate read at the run times 24 hours (the
approximation every other agent uses), because over a weekly-held book of ~16 names that approximation drifted by more
than a point of return in replay. Every long position, of every agent, keeps exactly the code path and the numbers it
had (pinned by `tests/test_longshort.py`, and by the lab replaying its five parity recipes through the old and the new
engine with identical results).

## Differences from the lab, and where they are measured

| Difference | Where measured |
|---|---|
| Engine book weights vs `lsbook.ls_targets` | lab Phase 0: identical on every coin-day since 2017; `tests/test_shadow.py` (lab) |
| Engine trading (band, drift, brake, fills, funding) vs the harness, same universe | lab Phase 0 "mechanics" row, catastrophic stop out of reach: same bounds as the other parity checks |
| The catastrophic stop | lab Phase 0 "as shadow-01 trades it" row: fires and cost |
| The live universe (Hyperliquid volume ranking) | same row: daily overlap with the lab's universe, and the engine on its own universe end to end |
| Price sanity band and open-interest filter at leg formation | not in the lab; refusals are said, recorded in the refusal ledger (stage `leg formation`) and in `book.json` (`refused_long`, `refused_short`) every rebalance; names with no second source are listed (`unchecked`) |
| Three runs a day (00:05, 01:05, 02:05 UTC) | the book is decided once, by the first fresh run (the lab's one reading); later runs only retry refused opens |
| Portfolio-level checks per order (stale data, halt, gross cap 2.3x, $10 minimum) | not in the lab; recorded as refusals |
| Throttle | off (99%): the book's own brake is its drawdown control, as in the lab |
