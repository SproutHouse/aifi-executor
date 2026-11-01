# Trend bot — specification (Phase 1, frozen 2026-09-26)

_Evidence: `research/phase1/trend_wf.py`, results in `research/phase1/trend_results.json`. Binance daily candles
2017–2026 for BTC and ETH. Parameters below are FROZEN: changing any of them is a new bot, re-tested from zero._

## The rule

| Item | Value |
|---|---|
| Markets | BTC and ETH perpetuals on Hyperliquid, 50/50 |
| Signal | once a day, at the 00:00 UTC daily close: **long if the close is above its 50-day simple moving average, otherwise flat** |
| Direction | **long or flat only.** No shorts (see "Departures from the Doctrine") |
| Size | each coin targets 30% annualised volatility, from its 30-day realised volatility: weight = 0.30 ÷ vol, capped at 2x |
| Rebalance | daily, toward the target weight; Phase 2 adds a no-trade band (target ±25%) and must re-test it before launch |
| Protective stop | an exchange-resident, reduce-only stop 15% below each entry, as outage and gap insurance only (the rule exits at the close long before). Phase 2 must confirm it never fires in the backtest's normal operation |
| Costs assumed | 0.045% taker + 0.05% slippage per unit turned over; longs pay 10%/yr funding, shorts get no credit |

## Evidence

| Measure | Value |
|---|---|
| Variants tried (all counted) | 28: SMA 50/100/150/200, time-series momentum 30/60/90/120/180, Donchian 20/40/55/100, daily Momentum Cloud; each long/short and long/flat |
| This rule, full sample 2017–2026 | Sharpe 1.32, t = 3.94, 30.6%/yr, max drawdown 34% |
| Deflated Sharpe probability (28 trials) | 0.992 (bar: 0.95) — passes |
| Walk-forward 2020–2026 (rule re-picked every January from prior data only) | Sharpe 0.83, t = 2.15, 18.2%/yr, max drawdown 40%; years +44, +39, −27, +19, +33, +13, +18% |
| Walk-forward picks | 2020 SMA100 L/S · 2021–22 Donchian20 long/flat · 2023 Cloud long/flat · **2024–26 SMA50 long/flat** |
| Plateau (long/flat SMA, full sample) | 50: 1.32 · 100: 1.06 · 150: 0.98 — a broad plateau, not a spike |

## Verdict against the Doctrine's gate

- In-sample process gate: **passed** (t ≥ 3 and deflated Sharpe ≥ 0.95).
- Out-of-sample: **positive but not proven** (t = 2.15 < 3). By the Doctrine's own arithmetic a true Sharpe near 0.8
  needs about six years of live data to confirm. It therefore goes live only **sized as tuition**, reviewed yearly
  against this distribution, never monthly against hope.

## Departures from the Doctrine

- **No short side.** Across every rule family, long/flat beat long/short (e.g. SMA-50: Sharpe 1.32 vs 1.15; the short
  leg added drawdown without return). This matches the executor's earlier backtests. The Doctrine's "full short in
  trending bear" is not supported by this data.
- **Daily close, not a moving-average crossover of two averages**: one average, one comparison, the fewest knobs.

## What Phase 2 must build for it

Daily trigger timeframe; a target-weight execution mode (the engine currently sizes by stop distance); the no-trade
band; the resident 15% stop on a target-weight position; reconciliation of target versus actual weight.

## Phase 2 status (2026-09-26)

- Band and stop re-tested (`research/phase1/trend_band.py`): the 25% band keeps Sharpe at 1.31 and cuts trading from
  about 400 to 49 trades a year; the 15% stop fired 5 times in nine years and costs about 0.4%/yr. Both kept as frozen.
- Built: daily timeframe, target-weight mode, paper resizing with realised partial P&L, reduce-only live trims, the
  resident stop following the size. Tests in `tests/test_target.py`.
- Agent `trend-1d` runs in paper from the next 00:00 UTC close. Its drawdown throttle is set at 25% (halve) and 45% (halt),
  above the rule's historical 40% drawdown, so normal drawdowns do not stop it.

## Spot holdings (2026-11-01, the owner's decision; paper only)

The rule is unchanged (same signal, size, band and stop, still read from the perps' daily bars). What changed is
where a long is held: `settings.target.long_venue: "spot"` makes `trend-1d` hold the coins themselves on Hyperliquid's
spot pairs, **UBTC/USDC (`@142`) and UETH/USDC (`@151`)**, instead of perpetuals. A perp long pays funding every hour;
a coin held outright pays none. Every other agent keeps the default `"perp"` and its exact old behaviour.

- **Prices and costs.** A spot long is bought and sold at its spot pair's mark price with the engine's paper slippage,
  and pays Hyperliquid's spot taker fee (`target.spot.fee_taker_pct`, 0.07%) instead of the perp's. Its funding is
  always zero. It is valued at the spot mark (the perp's mark stands in for a run whose spot prices cannot be read).
- **Checks.** The perp funding filter (`universe.max_funding_annual_pct`) exists because a perp long pays funding; it
  does not apply to a spot long and still applies to every perp long. Every other pre-trade check, the throttle, the
  halt and the 15% stop work as before; the stop is checked on the spot pair's own daily bars.
- **No borrowed money.** Spot is bought with cash, so the spot longs together hold at most `target.spot.max_x` (1x) of
  the pot. A target above that is capped and the run says so. At the rule's usual volatility this rarely binds.
- **Fallback to the perp.** A coin whose spot pair is missing, has no price, trades less than `target.spot.min_spot_vol_m`
  (0.5M) a day, or sits more than `target.spot.max_basis_pct` (1%) from the perp's price is opened or increased on the
  perp instead. The run says why ("venue · spot not used (…)") and a record with stage `venue` goes into
  `refused.jsonl`; the dashboard shows it as "Spot not usable: traded on the perp". A held spot long whose pair turns
  thin is kept (exits and trims still happen there) but is not increased.
- **Switching venue.** A long held on the other venue than the setting is moved **at once**, on the first run after
  the change: closed and re-opened at that day's target on the new venue, both fees paid, so it stops paying funding
  the day the setting changes instead of whenever the band next trades. The close is a normal trade line with reason
  "venue switch". The move waits (the position stays as it is) while the pre-trade checks would refuse the new
  position, for example under a halt; a perp long also stays a perp while spot is unusable.
- **Live.** There is no live spot order path yet: an agent with `long_venue: "spot"` runs paper even if `mode` says live
  (`spot_live_validated` would be the switch, as `carry_live_validated` is for carry).
