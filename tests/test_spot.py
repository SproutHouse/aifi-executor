"""Spot longs for target mode (settings.target.long_venue "spot", agents/trend-1d since 2026-11-01; paper only) and the
carry-1h settings of 2026-11-01.

Spot: a long is the coin itself on its Hyperliquid spot pair, valued at the spot mark, charged the spot taker fee, and
never charged funding; the perp funding filter does not apply to it (it stays for perp longs); a spot pair that is
missing or fails the spot checks sends the long to the perp with the reason recorded; a perp long held when the setting
says spot is moved at once (closed and re-opened on spot, both fees paid); stops are checked on the spot pair's bars;
spot never uses borrowed money; live refuses spot. A full paper cycle runs on fixture data in the test state dir, and
the dashboard bundle built from it marks the positions as spot.

Carry: the settings file holds the recipe's values, and the engine reads them (window, thresholds, basket)."""
import json, sys, unittest
from pathlib import Path
from unittest import mock
import _path  # noqa: F401
from executor import common as C, cycle as CY, ledger as L, paper as PA, target as TG, universe as U, carry as CA
import test_cycle as TC

ROOT = Path(__file__).resolve().parents[1]
STATE = TC.STATE
REAL_CHECK = U.check            # test_target patches U.check without restoring it; these tests need the real filters
TREND = json.loads((ROOT / "agents" / "trend-1d" / "settings.json").read_text())
CARRY = json.loads((ROOT / "agents" / "carry-1h" / "settings.json").read_text())
CFG = dict(TREND["target"], weights={"BTC": 0.5, "ETH": 0.5})
H_FUND = "0.0001"               # per hour: 87.6%/yr, far above the 30% the perp funding filter allows


def bars(closes, t0=0):
    return [{"t": t0 + i * 86400, "T": t0 + i * 86400 + 86399, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1} for i, c in enumerate(closes)]


def trending(n=120, vol=0.03, p=100.0):
    out = []
    for i in range(n):
        p *= 1 + (vol if i % 2 == 0 else -vol * 0.5)
        out.append(p)
    return out


UP = bars(trending())
PX = UP[-1]["c"]
SPOT_PX = PX * 0.999            # the spot pair trades a little below the perp


def pairs(vol=12e6, px=SPOT_PX):
    return {"BTC": {"pair": "@142", "token": "UBTC", "szd": 5, "vol": vol, "mid": px, "mark": px},
            "ETH": {"pair": "@151", "token": "UETH", "szd": 4, "vol": vol, "mid": px, "mark": px}}


class Clean(TC.Base):
    def setUp(self):
        super().setUp()
        for f in ("alerts_sent.json", "ledger/equity.jsonl"):
            (STATE / f).unlink(missing_ok=True)
        self.patches = []
        self.patch(CY.U, "check", REAL_CHECK)
        self.patch(CY.B, "last_price", lambda coin: PX)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        super().tearDown()

    def patch(self, obj, name, value):
        p = mock.patch.object(obj, name, value)
        p.start()
        self.patches.append(p)

    def tcycle(self, positions, venue="spot", spot=None, coins=("BTC",), spot_bars=None, perp_bars=None, funding=H_FUND):
        marks = {c: PX for c in coins}
        cy = self.cycle("paper", positions, {}, marks)
        cfg = dict(CFG, weights={c: 0.5 for c in coins}, long_venue=venue)
        cy.s = dict(cy.s, strategy="target", trigger_tf="1d", target=cfg, gross_exposure_cap_x=2.2)
        cy.bars.get = lambda coin: (perp_bars or UP, perp_bars or UP)
        cy.bars.tf = "1d"
        cy.ctxs = {c: {"szDecimals": 5, "markPx": str(PX), "funding": funding, "maxLeverage": 40, "dayNtlVlm": "5e8",
                       "openInterest": "1e5"} for c in coins}
        if isinstance(spot, Exception):
            def boom():
                raise spot
            self.patch(CY.H, "spot_pairs", boom)
        else:
            self.patch(CY.H, "spot_pairs", lambda: pairs() if spot is None else spot)
        self.patch(CY.H, "all_mids", lambda: {})
        self.patch(CY.H, "candles", lambda name, tf, days: (spot_bars if name.startswith("@") else perp_bars) or [])
        return cy


class PaperSpot(unittest.TestCase):
    CAND = {"coin": "BTC", "kind": "target", "tier": "T", "stop": 85.0, "book": "trend", "benchmark": "BTC", "bench_mark": 100.0,
            "venue": "spot", "pair": "@142", "token": "UBTC", "fee_taker_pct": 0.07}
    SIZING = {"notional": 300.0, "risk_amt": 45.0, "leverage": 1, "notional_pct_equity": 30.0}

    def test_spot_open_pays_the_spot_fee_and_no_funding(self):
        s = C.settings()
        pos = PA.open_position(self.CAND, self.SIZING, 100.0, s, 0)
        self.assertEqual((pos["venue"], pos["pair"], pos["fee_taker_pct"]), ("spot", "@142", 0.07))
        self.assertAlmostEqual(pos["entry_fee"], 300.0 * 0.07 / 100)
        self.assertAlmostEqual(pos["entry"], 100.0 * (1 + s["paper_slippage_pct"] / 100))
        PA.accrue_funding(pos, 0.0001, 86400 * 3)
        self.assertEqual(pos["funding_paid"], 0.0)
        self.assertEqual(pos["last_funding_ts"], 86400 * 3)
        self.assertEqual(PA.accrue_funding_history(pos, [{"time": 86400 * 4000, "fundingRate": "0.01"}], 100.0, 86400 * 5), 0)
        self.assertEqual(pos["funding_paid"], 0.0)
        self.assertAlmostEqual(PA.exit_fee(pos, 110.0, s), pos["sz"] * 110.0 * 0.07 / 100)

    def test_perp_open_is_unchanged(self):
        s = C.settings()
        cand = {k: v for k, v in self.CAND.items() if k not in ("venue", "pair", "token", "fee_taker_pct")}
        pos = PA.open_position(cand, self.SIZING, 100.0, s, 0)
        self.assertNotIn("venue", pos)
        self.assertAlmostEqual(pos["entry_fee"], 300.0 * s["fee_taker_pct"] / 100)
        PA.accrue_funding(pos, 0.0001, 3600)
        self.assertGreater(pos["funding_paid"], 0)

    def test_equity_values_spot_at_its_pair_mark(self):
        pos = PA.open_position(self.CAND, self.SIZING, 100.0, C.settings(), 0)
        pot = {"cash": 1000.0}
        eq_spot, _ = PA.equity(pot, {"BTC": pos}, {"BTC": 200.0, "@142": 110.0})
        self.assertAlmostEqual(eq_spot, 1000.0 + (110.0 - pos["entry"]) / pos["entry"] * pos["notional"])
        eq_nospot, _ = PA.equity(pot, {"BTC": pos}, {"BTC": 110.0})            # no spot mark: the perp's stands in
        self.assertAlmostEqual(eq_nospot, eq_spot)

    def test_resize_charges_the_spot_fee(self):
        s = C.settings()
        pos = PA.open_position(self.CAND, self.SIZING, 100.0, s, 0)
        fee0, cur = pos["entry_fee"], pos["sz"] * 100.0
        cash = TG.paper_resize(pos, 600.0, 100.0, s)
        self.assertAlmostEqual(-cash, (600.0 - cur) * 0.07 / 100)              # the added notional at the spot fee
        self.assertAlmostEqual(pos["entry_fee"] - fee0, -cash)


class SpotCycle(Clean):
    def test_spot_long_opens_at_the_spot_mark_with_the_spot_fee(self):
        cy = self.tcycle({})
        cy.manage_targets()
        p = L.positions("paper")["BTC"]
        slip = cy.s["paper_slippage_pct"] / 100
        self.assertEqual((p["venue"], p["pair"], p["token"], p["leverage"]), ("spot", "@142", "UBTC", 1))
        self.assertAlmostEqual(p["entry"], SPOT_PX * (1 + slip))
        self.assertAlmostEqual(p["entry_fee"], p["notional"] * 0.07 / 100)
        self.assertAlmostEqual(p["stop"], p["entry"] * (1 - CFG["stop_pct"] / 100))
        self.assertIn("venue:spot", p["rules"])
        self.assertAlmostEqual(cy.pot["cash"], 1000.0 - p["entry_fee"])

    def test_funding_filter_skipped_for_spot_kept_for_perp(self):
        cy = self.tcycle({})                                   # funding 87.6%/yr against longs
        cy.manage_targets()
        self.assertIn("BTC", cy.positions)
        cy2 = self.tcycle({}, venue="perp")
        cy2.manage_targets()
        self.assertNotIn("BTC", cy2.positions)
        self.assertTrue(any("REFUSED" in x and "against longs above" in x for x in cy2.summary))

    def test_spot_long_pays_no_funding_and_stops_on_spot_bars(self):
        cy = self.tcycle({})
        cy.manage_targets()
        pos = cy.positions["BTC"]
        stop = pos["stop"]
        later = UP[-1]["t"] + 86400
        spot_bars = [{"t": later, "T": later + 86399, "o": SPOT_PX, "h": SPOT_PX, "l": stop * 0.98, "c": stop * 0.99, "v": 1}]
        perp_bars = UP + [{"t": later, "T": later + 86399, "o": PX, "h": PX, "l": PX * 0.99, "c": PX, "v": 1}]   # never near the stop
        cy2 = self.tcycle(dict(cy.positions), spot_bars=spot_bars, perp_bars=perp_bars)
        cy2.now = cy.now + 3 * 86400
        cy2.manage_target_stops()
        self.assertNotIn("BTC", cy2.positions)
        rec = L.trades()[-1]
        slip = cy.s["paper_slippage_pct"] / 100
        self.assertEqual(rec["reason"], "protective stop")
        self.assertEqual(rec["funding"], 0.0)                  # three days at 87.6%/yr, none of it owed by a spot coin
        self.assertAlmostEqual(rec["exit"], stop * (1 - slip))
        self.assertAlmostEqual(rec["fees"], pos["entry_fee"] + pos["sz"] * rec["exit"] * 0.07 / 100)

    def test_thin_spot_falls_back_to_the_perp_and_says_why(self):
        cy = self.tcycle({}, spot=pairs(vol=2e5), funding="0.0000125")
        cy.manage_targets()
        p = cy.positions["BTC"]
        self.assertNotIn("venue", p)                           # an ordinary perp long
        self.assertAlmostEqual(p["entry_fee"], p["notional"] * cy.s["fee_taker_pct"] / 100)
        ref = [r for r in C.read_jsonl(L.REFUSED) if r.get("stage") == "venue"]
        self.assertEqual(len(ref), 1)
        self.assertIn("spot 24h volume 0.2M below 0.5M", ref[0]["detail"][0]["detail"])
        self.assertTrue(any("venue · spot not used" in x for x in cy.summary))

    def test_spot_data_down_falls_back_and_the_perp_keeps_its_funding_filter(self):
        cy = self.tcycle({}, spot=RuntimeError("info down"))      # and funding is 87.6%/yr: the perp long is refused
        cy.manage_targets()
        self.assertNotIn("BTC", cy.positions)
        self.assertTrue(any("REFUSED" in x and "against longs above" in x for x in cy.summary))

    def test_wide_basis_falls_back(self):
        cy = self.tcycle({}, spot=pairs(px=PX * 0.97), funding="0.0000125")
        cy.manage_targets()
        self.assertNotIn("venue", cy.positions["BTC"])
        self.assertIn("spot vs perp 3.00%", C.read_jsonl(L.REFUSED)[-1]["detail"][0]["detail"])

    def test_held_perp_moves_to_spot_at_once_paying_both_fees(self):
        perp = self.tcycle({}, venue="perp", funding="0.0000125")
        perp.manage_targets()
        old = dict(perp.positions["BTC"])
        self.assertNotIn("venue", old)
        cy = self.tcycle(dict(perp.positions))
        cy.now = perp.now + 86400
        cy.manage_target_stops()                                # as run(): the perp's day of funding accrues first
        cy.manage_targets()
        new = cy.positions["BTC"]
        self.assertEqual(new["venue"], "spot")
        rec = L.trades()[-1]
        self.assertEqual(rec["reason"], "venue switch")
        self.assertGreater(rec["funding"], 0)                  # the perp's funding is settled at the close
        self.assertAlmostEqual(rec["fees"], old["entry_fee"] + old["sz"] * rec["exit"] * cy.s["fee_taker_pct"] / 100)
        self.assertAlmostEqual(new["entry_fee"], new["notional"] * 0.07 / 100)
        self.assertTrue(any("moving the long from perp to spot" in x for x in cy.summary))
        cy2 = self.tcycle(dict(cy.positions))                  # next run: nothing more to move
        cy2.manage_targets()
        self.assertEqual(len(L.trades()), 1)

    def test_move_waits_while_halted(self):
        perp = self.tcycle({}, venue="perp", funding="0.0000125")
        perp.manage_targets()
        cy = self.tcycle(dict(perp.positions))
        cy.halt, cy.halt_reason = True, "manual"
        cy.manage_targets()
        self.assertNotIn("venue", cy.positions["BTC"])          # never closed into a position it cannot re-open
        self.assertEqual(L.trades(), [])
        self.assertTrue(any("signal switch tier T REFUSED: not halted" in x for x in cy.summary))

    def test_perp_stays_while_spot_unusable(self):
        perp = self.tcycle({}, venue="perp", funding="0.0000125")
        perp.manage_targets()
        cy = self.tcycle(dict(perp.positions), spot=pairs(vol=1e5), funding="0.0000125")
        cy.manage_targets()
        self.assertNotIn("venue", cy.positions["BTC"])
        self.assertEqual(L.trades(), [])
        self.assertTrue(any("stays on the perp" in x for x in cy.summary))

    def test_spot_increase_refused_while_its_pair_is_unusable(self):
        cy = self.tcycle({})
        cy.manage_targets()
        pos = cy.positions["BTC"]
        pos["sz"] /= 3                                          # far below target: an increase
        cy2 = self.tcycle(dict(cy.positions), spot=pairs(vol=1e5))
        cy2.manage_targets()
        self.assertAlmostEqual(cy2.positions["BTC"]["sz"], pos["sz"])
        self.assertTrue(any("signal increase tier T REFUSED: universe filters (spot: UBTC spot 24h volume" in x for x in cy2.summary))

    def test_spot_is_never_bought_with_borrowed_money(self):
        calm = bars([100 + i * 0.01 for i in range(120)])     # tiny volatility: weight at its 2x cap, 1x of pot per coin
        cy = self.tcycle({}, coins=("BTC", "ETH"), perp_bars=calm)
        for c in ("BTC", "ETH"):
            cy.marks[c] = calm[-1]["c"]
            cy.ctxs[c]["markPx"] = str(calm[-1]["c"])
        sp = pairs(px=calm[-1]["c"])
        self.patch(CY.H, "spot_pairs", lambda: sp)
        self.patch(CY.B, "last_price", lambda coin: calm[-1]["c"])
        cy.manage_targets()
        held = sum(p["notional"] for p in cy.positions.values())
        self.assertLessEqual(held, 1000.0)
        self.assertTrue(all(p["venue"] == "spot" for p in cy.positions.values()))
        self.assertTrue(any("capped at" in x and "never borrowed" in x for x in cy.summary))

    def test_live_refuses_spot(self):
        s = dict(TREND, mode="live")
        with mock.patch.object(CY.LV, "creds", return_value=("k", "a")), mock.patch.object(CY.LV, "available", return_value=True):
            mode, note = CY.resolve_mode(s)
            self.assertEqual(mode, "paper")
            self.assertTrue(note.endswith("running paper"))
            self.assertEqual(CY.resolve_mode(dict(s, target=dict(s["target"], long_venue="perp")))[0], "live")
        cy = self.tcycle({})
        cy.mode = "live"
        with self.assertRaises(RuntimeError):
            cy.execute_entry({"coin": "BTC", "kind": "target", "tier": "T", "stop": 1.0, "venue": "spot", "pair": "@142"},
                             {"notional": 100.0, "leverage": 1}, PX, {"weekly_dir": None, "daily_dir": None})

    def test_other_agents_never_read_spot(self):
        def no_network():
            raise AssertionError("a perp agent read the spot market")
        cy = self.tcycle({}, venue="perp", funding="0.0000125")
        self.patch(CY.H, "spot_pairs", no_network)
        cy.manage_targets()
        cy.manage_target_stops()
        self.assertNotIn("venue", cy.positions["BTC"])


class FullCycle(Clean):
    """Cycle.run() end to end with trend-1d's own settings, every market read served from fixtures, in the test state
    dir; then the dashboard bundle built from that state."""
    def test_paper_cycle_holds_spot_coins_and_the_dashboard_says_so(self):
        now = C.now_ts()
        T = now - 1800                                          # the last daily bar closed half an hour ago
        closes = trending(n=400, vol=0.03)
        daily = [{"t": T - (400 - i) * 86400 + 1, "T": T - (399 - i) * 86400, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1}
                 for i, c in enumerate(closes)]
        px = closes[-1]
        ctx = {"szDecimals": 5, "markPx": str(px), "funding": H_FUND, "maxLeverage": 40, "dayNtlVlm": "5e8", "openInterest": "1e5"}
        s = dict(TREND)
        C.settings = lambda: s
        CY.R.context = self._context                            # the real readings (TC.Base fakes them)
        self.patch(CY.H, "meta_and_ctxs", lambda dexes=(): {"BTC": dict(ctx), "ETH": dict(ctx)})
        self.patch(CY.H, "candles", lambda name, tf, days, completed_only=True: daily)
        self.patch(CY.H, "spot_pairs", lambda: pairs(px=px * 0.999))
        self.patch(CY.H, "all_mids", lambda: {})
        self.patch(CY.B, "last_price", lambda coin: px)
        self.patch(C, "notify", lambda *a, **k: None)
        doc = CY.Cycle(dry=False).run()
        self.assertFalse(doc["failed"], doc["summary"])
        pos = L.positions("paper")
        self.assertEqual(set(pos), {"BTC", "ETH"})
        for c, p in pos.items():
            self.assertEqual((p["venue"], p["funding_paid"], p["leverage"]), ("spot", 0.0, 1))
            self.assertAlmostEqual(p["mark"], px * 0.999)       # marked at the spot pair every run
        sys.path.insert(0, str(ROOT / "scripts"))
        import dashboard_push as DP
        b = DP.build(state=STATE, config=ROOT / "agents" / "trend-1d")
        rows = b["latest"]["pos"]
        self.assertEqual({r["c"] for r in rows}, {"BTC", "ETH"})
        self.assertTrue(all(r.get("venue") == "spot" for r in rows))


class CarrySettings(Clean):
    def test_carry_1h_holds_the_recipe_values(self):
        c = CARRY["carry"]
        self.assertEqual((CARRY["mode"], CARRY["strategy"], CARRY["carry_live_validated"]), ("paper", "carry", False))
        self.assertEqual(c["basket"], ["BTC", "ETH"])
        self.assertEqual((c["window_hours"], c["enter_apr"], c["exit_apr"], c["per_asset_cap"], c["perp_leverage"]), (281, 0.062, -0.076, 0.977, 2))
        self.assertEqual((c["execution"], c["resize_band"], c["max_basis_pct"], c["min_spot_vol_m"], c["crisis_unwind"]), ("taker", 0.25, 1.0, 0.5, True))
        f = c["fees"]
        self.assertEqual((f["spot_taker"], f["perp_taker"]), (0.0007, 0.00045))

    def carry_cycle(self, positions, rows):
        cfg = CARRY["carry"]
        cy = self.cycle("paper", positions, {}, {"BTC": 100.0, "ETH": 100.0, "ZEC": 100.0})
        cy.s = dict(cy.s, strategy="carry", carry=cfg)
        cy.now = 1790000000
        asked = []
        self.patch(CY.H, "spot_pairs", lambda: {c: {"pair": f"@{i}", "token": "U" + c, "szd": 4, "vol": 5e6} for i, c in enumerate(("BTC", "ETH", "ZEC"))})
        self.patch(CY.H, "all_mids", lambda: {"@0": 100.0, "@1": 100.0, "@2": 100.0})
        self.patch(CY.H, "funding_history", lambda coin, start: (asked.append((coin, start)), rows(coin))[1])
        self.patch(CY.H, "candles", lambda name, tf, days: [])
        self.patch(cy, "regime_crisis", lambda: False)
        return cy, asked

    def test_the_engine_reads_the_slow_window(self):
        now_ms = 1790000000 * 1000
        # high funding for the last day only (24h mean 17.5%/yr), low before (281h mean about 3%/yr): the old 24-hour
        # rule would enter, the recipe's slow window does not
        rows = lambda coin: [{"time": now_ms - k * 3600 * 1000, "fundingRate": str(0.00002 if k <= 24 else 0.0000015)} for k in range(311, 0, -1)]
        cy, asked = self.carry_cycle({}, rows)
        cy.manage_carry()
        self.assertEqual(cy.positions, {})
        self.assertEqual(sorted(c for c, _ in asked), ["BTC", "ETH"])                       # the basket, nothing else
        self.assertTrue(all(start == now_ms - (281 + 30) * 3600 * 1000 for _, start in asked))
        self.assertTrue(any(r["why"].endswith("(281h mean)") for r in cy.readings))
        self.assertIsNotNone(CA.mean_apr(rows("BTC"), now_ms, 24))
        self.assertGreater(CA.mean_apr(rows("BTC"), now_ms, 24), 0.10)
        self.assertLess(CA.mean_apr(rows("BTC"), now_ms, 281), CARRY["carry"]["enter_apr"])

    def test_thresholds_hold_through_negative_funding(self):
        cfg = CARRY["carry"]
        self.assertEqual(CA.decide(0.07, False, cfg), "enter")
        self.assertEqual(CA.decide(0.05, False, cfg), "none")
        self.assertEqual(CA.decide(-0.05, True, cfg), "hold")                               # negative, above the exit
        self.assertEqual(CA.decide(-0.08, True, cfg), "exit")
        self.assertAlmostEqual(CA.target_notional(1000, 1, cfg), 1000 * 0.977 / 1.5)          # alone: almost the whole pot
        self.assertAlmostEqual(CA.target_notional(1000, 2, cfg), 1000 * 0.5 / 1.5)

    def test_a_pair_outside_the_basket_is_unwound(self):
        now_ms = 1790000000 * 1000
        rows = lambda coin: [{"time": now_ms - k * 3600 * 1000, "fundingRate": "0.00002"} for k in range(311, 0, -1)]
        zec = {"coin": "ZEC", "kind": "carry", "side": "carry", "mode": "paper", "state": "open", "target_n": 100.0, "capital": 150.0,
               "target_sz": 1.0, "book": "carry", "opened": C.iso(1789000000), "opened_ts": 1789000000, "last_funding_ts": now_ms - 3600 * 1000,
               "legs": {"spot": {"pair": "@2", "szd": 4, "sz": 1.0, "entry": 100.0, "mark": 100.0}, "perp": {"sz": 1.0, "entry": 100.0}}, "orders": {}}
        cy, _asked = self.carry_cycle({"ZEC": zec}, rows)
        cy.manage_carry()
        self.assertNotIn("ZEC", cy.positions)
        rec = [x for x in L.trades() if x["coin"] == "ZEC"][-1]
        self.assertEqual(rec["reason"], "left the basket")
        self.assertTrue(any("ZEC: carry EXITING" in x and "left the basket" in x for x in cy.summary))


if __name__ == "__main__":
    unittest.main()
