# Execution — schedule, orders, reconciliation, paper engine

## Schedule

Since 2026-09-30 the cycles run on the alwaysdata server in Paris (`config/host.json` = `alwaysdata`): `tick.sh cycle`
at :05 every hour runs `scripts/run_agents.py`, which runs each agent whose trigger bar just closed: 1-hour agents
every hour, 4-hour agents after the 00/04/08/12/16/20 UTC closes, daily agents in the runs after 00:00 UTC that fall
inside their late-run window. GitHub's `cycle` workflow stands by (`host.json` = `github` makes it the runner again;
its scheduler has been dropping many runs, so it is a weak failover).

| UTC 4-hour close | Toronto, summer (EDT) | Toronto, winter (EST) |
|---|---|---|
| 00:00 | 20:00 | 19:00 |
| 04:00 | 00:00 | 23:00 |
| 08:00 | 04:00 | 03:00 |
| 12:00 | 08:00 | 07:00 |
| 16:00 | 12:00 | 11:00 |
| 20:00 | 16:00 | 15:00 |

Tier A executes at every hour (no human approval since 2026-09-24); tier B is recorded, not traded. If a run begins
later than the agent's late-run window (`data.late_run_minutes`: 35 for the 1-hour agent, 45 for 4-hour agents, 50
for carry, 180 for daily agents), entries for that bar are skipped and recorded; exits and trailing still run. Live
stops are unaffected because they sit on the exchange.

## Order of work in a cycle, `src/executor/cycle.py`

1. Resolve mode. Live needs `HL_AGENT_KEY`, `HL_ACCOUNT_ADDRESS` and the SDK; otherwise the cycle runs paper
   and says so.
2. Load market context and Bitcoin's regime; judge data freshness.
3. Load positions and equity; compute the throttle.
4. Live: absorb positions the exchange already closed (a resident stop fired), recording each from the
   account's fills, so nothing below acts on a ghost position.
5. Expire proposals past the last bar close.
6. Manage exits, one position at a time inside its own error boundary: stop check (paper), then any
   missing reading keeps the position untouched, then regime and 4-hour flips, then trailing.
7. Live: reconcile the ledger against the exchange (below); a mismatch halts entries.
8. Look for entries book by book, name by name; run the pre-trade checklist including the book's own risk
   cap; execute by tier. Every candidate carries its book and the benchmark's mark at entry.
9. Always, even after an error: write state, the equity point, the run record with every name's reading,
   `LEDGER.md`; send the daily line at 08:00 local. An aborted cycle still records itself and exits non-zero.

State is written through after every open, close and trail. A close removes the position and persists
before the trade line is appended, so a crash between the two loses one ledger line rather than closing
the same position twice.

## Orders in live mode, `src/executor/live.py`

| Action | Order | Notes |
|---|---|---|
| Set leverage | isolated, the value the sizing chose | before the first order in a coin |
| Entry | limit, IOC, price mark × 1.003, unique client id | fills up to the cap or not at all; never rests |
| Stop | reduce-only trigger, `tpsl: sl`, market on trigger, trigger on **mark price**, worst price stop × 0.97 | placed immediately after the fill; the exchange enforces it |
| Trail | place the new stop, then cancel the old by client id | never lowered |
| Close | `market_close` for the whole exchange size, reduce-only by construction, sent BEFORE the stop is cancelled | a failed close keeps the position and its stop and alerts; retried next cycle |
| Fresh fill | recorded to the positions file first, then the stop is placed with one retry; if the stop cannot be placed the position is closed; if that fails too, HALT and a page | never a filled position the ledger does not know |
| Entry exception | followed by a read of the account: a long that exists is recorded and protected | a timeout is not assumed to mean "no fill" |
| Rounding | size to `szDecimals`; price to 5 significant figures and at most 6 − szDecimals decimals | Hyperliquid's rules |

Every order carries a client order id (a random 128-bit hex). A retry gets a fresh id, so the id alone does not
prevent a duplicate; instead, after a request that raised, `protect()` looks the stop up by its client id and adopts
it if it rests, and entries re-read the account. A close whose fill is smaller than the position keeps the remainder
open with a stop sized to it (placed before the old stop is cancelled) and pages; a target resize that times out
re-reads the account and re-places the stop at the true size. Sizes round down to the exchange step exactly (no
float error). Nothing here has been run against a funded account yet; stage one of going live proves it with a
minimum-size order (see OPERATIONS.md).

## Reconciliation, live only

The exchange is the truth; the ledger is derived. Each cycle:

- A ledger position the exchange no longer holds means the resident stop fired: the exit price is taken from
  the account's fills and the trade is recorded as `stop (exchange)`.
- Then any of these halts new entries and alerts: a position on the exchange the ledger does not know; a
  size that differs by more than 2%; a position without a resting reduce-only stop.
- Exits are never blocked by a mismatch.

## Data checks before any entry

- Freshness: the agent's last completed trigger bar closed within its late-run window (`data.late_run_minutes`).
- Sanity band: Hyperliquid mark within 2% of Binance's last price when Binance gives a second source: a USDT pair that
  trades, its last trade under an hour old (`binance_data.py`, the 24-hour ticker's close time). A halted pair keeps
  serving a frozen price (LITUSDT and XMRUSDT, status BREAK, were 3 to 4 times off Hyperliquid in October 2026), so it
  counts as no second source; with none the band is not checked (it fails open) and the check's detail says why.
- Universe filters on live volume, open interest, funding and max leverage.

## Paper engine, `src/executor/paper.py`

Same position records as live. Entry at mark × 1.0005 with a 0.045% fee. Funding: the coin's current hourly rate at
each cycle times the hours since the last cycle (an approximation; the actual hourly rates can differ, by −27% on one
trend-1d position). Stop checked on every completed bar of the agent's trigger timeframe since the last check (daily
agents: daily bars): the first bar whose low touches the stop fills at min(open, stop) × 0.9995, so a gap through the
stop is charged in full. On wide-range days a live stop (triggered on the mark price, worst price 0.97 × stop) may
fill partly or not at all; paper books the full fill. Regime exits fill at mark × 0.9995. The pot starts at `pot_usd_paper` and lives in `state/paper.json`.

## Target-weight mode (`"strategy": "target"`, the Trend agent)

Instead of entering on a signal and trailing a stop, a target-weight agent holds a size and moves toward it once per
bar (docs/specs/TREND.md). Each cycle, per coin: compute the target from the rule; if the current size is outside the
band (±25% of target), open, grow, trim or close toward it. Exits and trims never wait on checks; opening or growing
passes halt, throttle, freshness, reconciliation, equity, gross-exposure, exchange-minimum, price-sanity and universe
checks. Live: growth is an immediate-or-cancel buy; a trim is a **reduce-only** immediate-or-cancel sell that can never
open a short; after any change the resident stop (15% below the average entry) is replaced at the new size through the
same fail-closed path as a fresh entry. Partial trims are realised into the position and counted when it finally closes.
Daily agents are due for up to their late limit after 00:00 UTC, so they run up to three times after a close (00:05,
01:05, 02:05). A later run derives the same target from the closed daily bar and trades only outside the band, so it
mostly holds or retries an open the checks refused; it is not idempotent by itself (marks, funding and volume are read
live each run). The long-short book is decided once per rebalance day, by its first fresh run (docs/specs/SHADOW.md).

**Recipe agents (strategy families).** A `target` block with `"family"`, `"params"` and `"coins"` (written by the AiFi
Lab for arena agents) computes each coin's target with `src/executor/families.py` instead of the Trend rule: the same
functions the lab backtested, run over the agent's recent daily history, last value traded. Families: `sma_trend`,
`tsmom`, `dual_ma`, `donchian`, `cloud_trend`, `rs_rotation`, `meanrev`. Every family is causal (tests prove the value on
a day never changes when later data is removed) and can be gated by the market regime (`long_regimes`). The engine is
long-or-flat: a family's short signal is held at zero. The one exception is the **long-short book** of the shadow
experiment `shadow-01` (`"family": "ls_xs"`, `"shorts": true`; docs/specs/SHADOW.md): paper only by construction
(`cycle.paper_only`; go-live and approve refuse it), it holds signed weights, its shorts carry `"side": "short"` in the
paper ledger (they receive positive funding), and it accrues Hyperliquid's actual hourly funding. A Trend block without `"family"` keeps `target.weight` exactly
as before (`tests/test_families.py` proves the two agree to 9 decimals on every day).

## Carry mode (`"strategy": "carry"`, the Carry agent)

Short perp plus long spot of the same number of coins, collecting hourly funding (docs/specs/CARRY.md). Each hourly cycle:
read the last 24 hours of funding per coin; enter at ≥ 10%/yr, exit below 0%; accrue funding on the short leg. Since
2026-10-16 carry-1h trades both legs together with taker orders in the same cycle (`execution: "taker"`), so the legs
never sit apart; the older maker mode (one resting order per leg, a lagging leg completed after `max_unhedged_hours`)
remains available. A pair is re-sized, both legs together, only when its notional drifts more than 25% from target
(`resize_band`). New pairs are sized from free capital: total committed capital (1.5 × notional) never exceeds equity;
a coin that qualifies when the pot is full is refused as "gross exposure cap". Entries pass halt, throttle,
reconciliation, equity, spot-liquidity and spot-perp basis checks. `control → flatten` writes HALT first, then closes
both legs of every pair. The dashboard's position cards skip
carry positions until the Phase 6 carry view; their value is in the pot figure and their closes are in the ledger.
