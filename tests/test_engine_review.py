"""The engine review's fixes (package E: engine safety + carry execution), one class per finding:

 1 a damaged .jsonl line is skipped, counted and alerted once, and never stops a cycle
 2 round_sz keeps exact sizes exact (0.29 stayed 0.28 for about 3% of sizes)
 3 a zero or negative close makes a momentum score undefined instead of raising
 4 a rotation holds every pick when one of its coins has no candles
 5 flatten writes HALT first and closes a carry pair (both legs) without the KeyError
 6 control.py refuses an agent id that is not on the roster
 7 go_live --back refuses while live positions are open
 8 go-live needs the lab's Ready, or the owner's exact override
 9 a live close that fills only part keeps the remainder open with a re-sized stop
10 a live resize that times out re-reads the exchange and re-places the stop at the true size
11 carry never commits more capital than the pot holds
12 the carry safety override never loops as a silent no-op; stale resting orders are re-sized or cancelled
13 carry legs stay equal in coins; on a trending path the hedge loses only its costs
14 alert priorities: paper trades are not pushed, live-money problems are urgent
15 a stop whose answer was lost is adopted by its client id instead of placed twice
16 control and go-live have their own concurrency groups
"""
import json, math, os, random, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
import _path  # noqa: F401
from executor import common as C, cycle as CY, ledger as L, paper as PA, hl_data as H, carry as CA, momentum as MO
from executor import families as F, target as TG, live as LV
import test_cycle as TC

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ["EXECUTOR_STATE"])
sys.path.insert(0, str(ROOT / "scripts"))
import control as CT  # noqa: E402

CFG = {"basket": ["HYPE"], "window_hours": 24, "enter_apr": 0.10, "exit_apr": 0.0, "per_asset_cap": 0.30, "perp_leverage": 2,
       "maker_offset_bps": 2, "requote_hours": 2, "delta_band": 0.02, "max_unhedged_hours": 1, "min_spot_vol_m": 0.5,
       "max_basis_pct": 1.0, "crisis_unwind": True, "resize_band": 0.25,
       "fees": {"spot_maker": 0.0004, "perp_maker": 0.00015, "spot_taker": 0.0007, "perp_taker": 0.00045}}
H_MS = 3600 * 1000
T0 = 1790000000


def fund_rows(now_ms, rate, hours=30):
    return [{"time": now_ms - k * H_MS, "fundingRate": str(rate)} for k in range(hours, 0, -1)]


def daily(closes, t0=0):
    return [{"t": t0 + i * 86400, "T": t0 + i * 86400 + 86399, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1} for i, c in enumerate(closes)]


def walk(n=300, seed=1, drift=0.001, vol=0.03):
    rnd, p, out = random.Random(seed), 100.0, []
    for _ in range(n):
        p *= math.exp(drift + vol * rnd.gauss(0, 1))
        out.append(p)
    return daily(out)


def carry_pos(coin="HYPE", state="open", spot=6.66, perp=6.66, px=30.0, pair="@107", **kw):
    p = {"coin": coin, "kind": "carry", "side": "carry", "mode": "paper", "state": state, "target_n": 200.0, "capital": 300.0,
         "book": "carry", "opened": C.iso(T0), "opened_ts": T0, "last_funding_ts": T0 * 1000,
         "legs": {"spot": {"pair": pair, "sz": spot, "entry": px, "mark": px}, "perp": {"sz": perp, "entry": px}}, "orders": {}}
    p.update(kw)
    return p


class Clean(TC.Base):
    """TC.Base plus: no alert-dedupe file, no HALT, no leftover patches of the market reads."""
    def setUp(self):
        super().setUp()
        for f in ("alerts_sent.json", "HALT", "HALT.since", "ledger/equity.jsonl"):
            (STATE / f).unlink(missing_ok=True)
        self.patches = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def patch(self, obj, name, value):
        p = mock.patch.object(obj, name, value)
        p.start()
        self.patches.append(p)

    def carry_cycle(self, positions, marks, cfg=CFG, now=T0, rates=None, pairs=None, mids=None, bars=None, szd_perp=3):
        cy = self.cycle("paper", positions, {}, marks)
        cy.s = dict(cy.s, strategy="carry", carry=dict(cfg))
        cy.now = now
        cy.ctxs = {c: {"szDecimals": szd_perp, "markPx": str(m)} for c, m in marks.items()}
        rates = rates or {c: 0.00002 for c in marks}
        pairs = pairs or {c: {"pair": f"@{100 + i}", "token": c, "szd": 2, "vol": 5e6} for i, c in enumerate(sorted(marks))}
        mids = mids or {pairs[c]["pair"]: m for c, m in marks.items()}
        self.patch(CY.H, "spot_pairs", lambda: pairs)
        self.patch(CY.H, "all_mids", lambda: mids)
        self.patch(CY.H, "funding_history", lambda coin, start: fund_rows(cy.now * 1000, rates.get(coin, 0.0)))
        self.patch(CY.H, "candles", lambda name, tf, days: (bars or {}).get(name, []))
        return cy


# 1 -----------------------------------------------------------------------------------------------------------------
class DamagedLines(Clean):
    def test_skipped_counted_and_alerted_once(self):
        f = STATE / "review_damaged.jsonl"
        f.write_text('{"a": 1}\n{"a": 2, "b": tr\n<<<<<<< HEAD\n{"a": 3}\n')
        sent = []
        with mock.patch.object(C, "alert", side_effect=lambda msg, priority="default", title=None: sent.append((msg, priority)) or True):
            self.assertEqual(C.read_jsonl(f), [{"a": 1}, {"a": 3}])
            self.assertEqual(C.read_jsonl(f), [{"a": 1}, {"a": 3}])          # the next cycle: no second alert
        self.assertEqual(len(sent), 1)
        self.assertIn("2 damaged line(s)", sent[0][0])
        self.assertEqual(sent[0][1], "high")
        f.unlink()

    def test_a_record_after_a_torn_tail_starts_on_its_own_line(self):
        f = STATE / "review_torn.jsonl"
        f.write_text('{"a": 1}\n{"a": 2, "b"')                               # a crash mid-write: no final newline
        C.append_jsonl(f, {"a": 3})
        with mock.patch.object(C, "alert", return_value=True):
            self.assertEqual(C.read_jsonl(f), [{"a": 1}, {"a": 3}])          # the new record survives
        f.unlink()

    def test_a_torn_equity_line_no_longer_stops_exits(self):
        L.EQUITY.parent.mkdir(parents=True, exist_ok=True)
        L.EQUITY.write_text('{"t": "x", "ts": 1, "equity": 1000.0, "mode": "paper"}\n{"t": "x", "ts": 2, "equ\n')
        TC.CTX["ETH"] = TC.ctx(daily=1)
        cy = self.cycle("paper", {"ETH": TC.paper_pos("ETH")}, {"ETH": []}, {"ETH": 104.0})
        with mock.patch.object(C, "alert", return_value=True):
            cy.load_account()                                                # raised JSONDecodeError every cycle before
            cy.manage_exits()
        self.assertEqual(L.trades()[-1]["reason"], "daily flip")
        L.EQUITY.unlink()


# 2 -----------------------------------------------------------------------------------------------------------------
class RoundSize(unittest.TestCase):
    def test_exact_sizes_stay_exact(self):
        wrong = []
        for d in range(0, 6):
            for k in range(0, 20000):
                sz = k / 10 ** d
                if H.round_sz(sz, d) != sz:
                    wrong.append((sz, d))
        self.assertEqual(wrong, [])
        self.assertEqual(H.round_sz(0.29, 2), 0.29)                           # was 0.28

    def test_never_rounds_up(self):
        rnd = random.Random(7)
        for _ in range(50000):
            d, x = rnd.randint(0, 6), rnd.uniform(0, 5000)
            r = H.round_sz(x, d)
            self.assertLessEqual(r, x * (1 + 1e-12))
            self.assertLess(x - r, 10 ** -d * (1 + 1e-9))
        self.assertEqual((H.round_sz(0.28999999, 2), H.round_sz(0.0056319, 5), H.round_sz(-0.29, 2)), (0.28, 0.00563, -0.29))


# 3 -----------------------------------------------------------------------------------------------------------------
class BadPrints(unittest.TestCase):
    def test_scores_are_undefined_not_raised(self):
        c = [100.0 + i for i in range(80)]
        t = [i * 86400 for i in range(80)]
        btc = {x: 50.0 + i for i, x in enumerate(t)}
        for bad in (0.0, -5.0):
            cc = list(c)
            cc[62] = bad
            for name in MO.SCORES:
                if name == "ensemble":
                    continue
                self.assertIsNone(MO.score(name, cc, 70, 20, btc, t), (name, bad))   # the bad bar is inside the window
                self.assertIsNotNone(MO.score(name, cc, 79, 10, btc, t) if name != "multi" else MO.score(name, cc, 79, 5, btc, t), name)

    def test_families_and_the_trend_rule_hold_instead_of_raising(self):
        panel = {c: walk(seed=s) for c, s in (("BTC", 1), ("ETH", 2), ("SOL", 3), ("AVAX", 4))}
        panel["SOL"][-5]["c"] = 0.0
        for fam, params in (("bull_momentum", {"rank": "sharpe", "gate": "none", "n": 20}), ("rs_rotation", {"n": 20}),
                            ("tsmom", {"n": 20}), ("sma_trend", {"n": 20})):
            F.latest(panel, fam, params)                                     # a ZeroDivisionError or ValueError before
        w, why = TG.weight(panel["SOL"], {"sma": 50, "vol_target": 0.3, "cap_x": 2.0, "vol_days": 30})
        self.assertIsNone(w)
        self.assertIn("bad print", why)


# 4 -----------------------------------------------------------------------------------------------------------------
class RotationDataGap(Clean):
    def plan(self, cfg, missing="SOL"):
        panel = {c: walk(seed=s, drift=0.002) for c, s in (("BTC", 11), ("ETH", 12), ("SOL", 13))}

        def get(_self, c):
            if c == missing:
                raise RuntimeError("api down")
            return panel[c], panel[c]
        cy = self.cycle("paper", {}, {}, {c: panel[c][-1]["c"] for c in panel})
        cy.bars = type("B", (), {"tf": "1d", "get": get})()
        return cy, cy.target_plan(cfg)

    def test_rotation_holds_every_pick(self):
        cfg = {"family": "rs_rotation", "params": {"n": 20, "k": 2, "rebalance_days": 1, "filter_n": 0}, "coins": ["BTC", "ETH", "SOL"],
               "band": 0.25, "stop_pct": 15}
        cy, plan = self.plan(cfg)
        self.assertEqual({c: plan[c][0] for c in plan}, {"BTC": None, "ETH": None, "SOL": None})
        self.assertIn("picks held", plan["BTC"][1])
        self.assertIn("SOL", plan["BTC"][1])
        self.assertIn("candles unavailable", plan["SOL"][1])
        _cy, ok = self.plan(cfg, missing=None)
        self.assertTrue(all(ok[c][0] is not None for c in ok))                # with every coin's data: readings again

    def test_a_per_coin_family_keeps_trading_the_coins_it_has(self):
        cfg = {"family": "tsmom", "params": {"n": 20}, "coins": ["BTC", "ETH", "SOL"], "band": 0.25, "stop_pct": 15}
        _cy, plan = self.plan(cfg)
        self.assertIsNone(plan["SOL"][0])
        self.assertIsNotNone(plan["BTC"][0])


# 5 -----------------------------------------------------------------------------------------------------------------
class FlattenCarry(Clean):
    def test_halt_is_written_before_anything_can_fail(self):
        class Boom(CY.Cycle):
            def load_market(self):
                raise RuntimeError("api down")
        with mock.patch.object(CT, "Cycle", Boom):
            with self.assertRaises(RuntimeError):
                CT.flatten()
        self.assertTrue(CY.HALT.read_text().startswith("manual flatten"))

    def test_both_legs_closed_and_recorded(self):
        cy = self.carry_cycle({"HYPE": carry_pos(funding_income=1.0, theo_funding=1.0, fees=0.2)}, {"HYPE": 30.0},
                              pairs={"HYPE": {"pair": "@107", "token": "HYPE", "szd": 2, "vol": 5e6}}, mids={"@107": 30.3})
        cy.load_market = cy.load_account = lambda: None
        with mock.patch.object(CT, "Cycle", lambda dry=False: cy):
            CT.flatten()                                                     # KeyError 'sz' before, and HALT never written
        self.assertTrue(CY.HALT.exists())
        self.assertEqual(L.positions("paper"), {})
        rec = L.trades()[-1]
        self.assertEqual((rec["coin"], rec["kind"], rec["reason"]), ("HYPE", "carry", "manual flatten"))
        self.assertAlmostEqual(rec["gross"], (30.3 * (1 - 0.0005) - 30.0) * 6.66 + (30.0 - 30.0 * 1.0005) * 6.66, places=6)

    def test_close_position_sends_carry_to_its_own_path(self):
        cy = self.carry_cycle({"HYPE": carry_pos()}, {"HYPE": 30.0}, pairs={"HYPE": {"pair": "@107", "token": "HYPE", "szd": 2, "vol": 5e6}},
                              mids={"@107": 30.0})
        rec = cy.close_position("HYPE", cy.positions["HYPE"], 29.9, "no stop possible", cy.now)
        self.assertEqual(rec["kind"], "carry")
        self.assertNotIn("HYPE", cy.positions)

    def test_paper_flatten_fills_each_side_worse_than_the_mark(self):
        # audit 2026-10-23: a short's buy-back was booked at mark*(1-slip), better than the mark, flattering paper P&L
        cy = self.cycle("paper", {}, {}, {"ETH": 100.0, "SOL": 100.0})
        sizing = {"notional": 100.0, "risk_amt": 1.0, "leverage": 1.0, "notional_pct_equity": 10.0}
        for coin, side, stop in (("ETH", "short", 200.0), ("SOL", "long", 50.0)):
            cand = {"coin": coin, "side": side, "kind": "book", "tier": "A", "stop": stop}
            cy.positions[coin] = PA.open_position(cand, sizing, 100.0, cy.s, cy.now)
        cy.load_market = cy.load_account = lambda: None
        with mock.patch.object(CT, "Cycle", lambda dry=False: cy):
            CT.flatten()
        slip = cy.s["paper_slippage_pct"] / 100
        exits = {t["coin"]: t["exit"] for t in L.trades() if t.get("reason") == "manual flatten"}
        self.assertAlmostEqual(exits["ETH"], 100.0 * (1 + slip), places=9)       # the short buys back above the mark
        self.assertAlmostEqual(exits["SOL"], 100.0 * (1 - slip), places=9)       # the long sells below it, as before
        self.assertEqual(L.positions("paper"), {})


# 6 -----------------------------------------------------------------------------------------------------------------
def sandbox():
    home = Path(tempfile.mkdtemp(prefix="exec-review-"))
    shutil.copytree(ROOT / "config", home / "config")
    shutil.copytree(ROOT / "agents", home / "agents")
    (home / "state").mkdir()
    return home


def run(home, *args, agent=None, state=None):
    env = dict(os.environ, EXECUTOR_HOME=str(home), EXECUTOR_STATE=str(state or home / "state"),
               EXECUTOR_FLEET_HALT=str(home / "state" / "FLEET_HALT"), PYTHONPATH=str(ROOT / "src"), ALERT_WEBHOOK="")
    env.pop("EXECUTOR_AGENT", None)
    if agent:
        env["EXECUTOR_AGENT"] = agent
    return subprocess.run([sys.executable] + list(args), env=env, capture_output=True, text=True, cwd=str(ROOT))


class ControlIds(unittest.TestCase):
    def test_unknown_agent_is_refused_and_nothing_is_written(self):
        home = sandbox()
        st = home / "state" / "agents" / "arena-1"
        r = run(home, "scripts/control.py", "--halt", "drill", agent="arena-1", state=st)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no agent 'arena-1'", r.stderr)
        self.assertFalse((st / "HALT").exists())
        st2 = home / "state" / "agents" / "arena-01"
        r = run(home, "scripts/control.py", "--halt", "drill", agent="arena-01", state=st2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((st2 / "HALT").read_text(), "drill")


# 7, 8 --------------------------------------------------------------------------------------------------------------
class GoLiveGates(unittest.TestCase):
    def home(self, ready=None, enable=("wide-4h", "arena-01", "arena-02"), disable=()):
        home = sandbox()
        idx = home / "agents" / "index.json"              # these tests are about Ready, not about which bots the
        d = json.loads(idx.read_text())                   # owner has retired in the real roster (2026-10-17: core,
        for a in d["agents"]:                             # wide-4h, fast-1h, arena-01)
            if a["id"] in enable:
                a["enabled"] = True
            if a["id"] in disable:
                a["enabled"] = False
        idx.write_text(json.dumps(d))
        (home / "factory").mkdir()
        rows = [{"agent": a, "ready": ok, "not_ready": [] if ok else ["16 of 42 days in the arena"]} for a, ok in (ready or {}).items()]
        (home / "factory" / "factory.json").write_text(json.dumps({"v": 1, "shortlist": rows}))
        return home

    def mode(self, home, aid):
        return json.loads((home / "agents" / aid / "settings.json").read_text())["mode"]

    def test_a_retired_bot_is_refused(self):
        home = self.home({"arena-02": True}, enable=(), disable=("wide-4h",))
        r = run(home, "scripts/go_live.py", "wide-4h", "--pot", "250", "--override", "LIVE WITHOUT READY wide-4h")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("disabled (retired)", r.stderr)
        self.assertEqual(self.mode(home, "wide-4h"), "paper")

    def test_ready_is_required_unless_the_owner_overrides(self):
        home = self.home({"arena-01": False, "arena-02": True})
        r = run(home, "scripts/go_live.py", "wide-4h", "--pot", "250")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not on the lab's shortlist", r.stderr)                 # a legacy agent is never Ready
        r = run(home, "scripts/go_live.py", "arena-01", "--pot", "250")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not Ready (16 of 42 days in the arena)", r.stderr)
        r = run(home, "scripts/go_live.py", "arena-01", "--pot", "250", "--override", "LIVE WITHOUT READY arena-02")
        self.assertNotEqual(r.returncode, 0)                                  # the override names this agent, exactly
        self.assertEqual(self.mode(home, "arena-01"), "paper")
        r = run(home, "scripts/go_live.py", "arena-01", "--pot", "250", "--override", "LIVE WITHOUT READY arena-01")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.mode(home, "arena-01"), "live")
        row = next(a for a in json.loads((home / "agents" / "index.json").read_text())["agents"] if a["id"] == "arena-01")
        self.assertTrue(row["live"]["without_ready"])
        r = run(home, "scripts/go_live.py", "arena-02", "--pot", "250")
        self.assertEqual(r.returncode, 0, r.stderr)                           # Ready: no override needed
        r = run(home, "scripts/go_live.py", "carry-1h", "--pot", "250", "--override", "LIVE WITHOUT READY carry-1h")
        self.assertIn("testnet", r.stderr)                                    # the existing refusals still come first

    def test_back_refuses_while_live_positions_are_open(self):
        home = self.home({"arena-02": True})
        self.assertEqual(run(home, "scripts/go_live.py", "arena-02", "--pot", "250").returncode, 0)
        live = home / "state" / "agents" / "arena-02" / "positions_live.json"
        live.parent.mkdir(parents=True)
        live.write_text(json.dumps({"mode": "live", "positions": {"ETH": {"coin": "ETH", "sz": 1.0}}}))
        r = run(home, "scripts/go_live.py", "arena-02", "--back")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("flatten first (control workflow: flatten arena-02), then BACK", r.stderr)
        self.assertEqual(self.mode(home, "arena-02"), "live")
        live.write_text(json.dumps({"mode": "live", "positions": {}}))
        r = run(home, "scripts/go_live.py", "arena-02", "--back")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.mode(home, "arena-02"), "paper")


class UnmanagedLiveBook(Clean):
    def test_a_paper_cycle_pages_about_a_live_book_it_cannot_manage(self):
        L.save_positions({"ETH": dict(TC.paper_pos("ETH"), mode="live")}, "live")   # e.g. back to paper from a stale ledger
        cy = self.cycle("paper", {}, {}, {"ETH": 100.0})
        got = []
        with mock.patch.object(C, "alert", side_effect=lambda msg, priority="default", title=None: got.append(priority) or True):
            cy.load_account()
            cy.load_account()                                                  # the next cycle: no second page
        self.assertEqual(got, ["urgent"])


# 9 -----------------------------------------------------------------------------------------------------------------
class PartialClose(Clean):
    def test_remainder_stays_open_with_a_resized_stop(self):
        ex = TC.FakeEx({"close": TC.FILL(99.0, 1.0)})
        pos = TC.paper_pos("ETH")
        pos.update({"mode": "live", "stop_cloid": "0xold", "sz": 2.5, "entry": 100.0, "notional": 250.0})
        cy = self.cycle("live", {"ETH": pos}, {"ETH": []}, {"ETH": 100.0}, ex=ex, exch_pos={"ETH": {"szi": 1.5, "entryPx": 100.0}})
        alerts = []
        with mock.patch.object(C, "notify", side_effect=lambda t, x, p="default": alerts.append((t, x, p))):
            self.assertIsNone(cy.close_position("ETH", pos, 100.0, "4h flip", 1000))
        self.assertEqual([c[0] for c in ex.calls], ["market_close", "stop", "cancel"])   # new stop first, the old one after
        self.assertEqual(ex.calls[1][2], 1.5)                                  # sized to the remainder
        on_disk = L.positions("live")["ETH"]
        self.assertEqual((on_disk["sz"], on_disk["stop_cloid"] != "0xold"), (1.5, True))
        self.assertAlmostEqual(on_disk["realized"], (99.0 - 100.0) * 1.0 - 99.0 * 1.0 * C.settings()["fee_taker_pct"] / 100)
        self.assertEqual(L.trades(), [])                                       # never recorded as a full close
        self.assertEqual(alerts[-1][2], "urgent")
        self.assertIn("only 1 of 2.5 filled", alerts[-1][1])

    def test_a_close_the_exchange_completed_is_a_full_close(self):
        ex = TC.FakeEx({"close": TC.FILL(99.0, 1.0)})
        pos = TC.paper_pos("ETH")
        pos.update({"mode": "live", "stop_cloid": "0xold", "sz": 2.5})
        cy = self.cycle("live", {"ETH": pos}, {"ETH": []}, {"ETH": 100.0}, ex=ex, exch_pos={})
        self.assertIsNotNone(cy.close_position("ETH", pos, 100.0, "4h flip", 1000))
        self.assertNotIn("ETH", L.positions("live"))


# 10 ----------------------------------------------------------------------------------------------------------------
class ResizeRecovery(Clean):
    def live_pos(self):
        pos = TC.paper_pos("BTC", stop=85.0)
        pos.update({"mode": "live", "sz": 1.0, "entry": 100.0, "notional": 100.0, "stop_cloid": "0xold"})
        return pos

    def test_timeout_reads_the_exchange_and_restops_at_the_true_size(self):
        ex = TC.FakeEx({"entry": TimeoutError("read timed out")})
        pos = self.live_pos()
        cy = self.cycle("live", {"BTC": pos}, {}, {"BTC": 100.0}, ex=ex, exch_pos={"BTC": {"szi": 1.6, "entryPx": 100.0}})
        with mock.patch.object(C, "notify"):
            cy.target_resize("BTC", pos, 160.0, 100.0, 0.15)
        self.assertAlmostEqual(cy.positions["BTC"]["sz"], 1.6)
        self.assertAlmostEqual(L.positions("live")["BTC"]["sz"], 1.6)
        stops = [c for c in ex.calls if c[0] == "stop"]
        self.assertEqual(stops[-1][2], 1.6)                                    # the stop covers what the exchange holds

    def test_unreadable_account_covers_the_largest_possible_size(self):
        ex = TC.FakeEx({"entry": TimeoutError("read timed out")})
        pos = self.live_pos()
        cy = self.cycle("live", {"BTC": pos}, {}, {"BTC": 100.0}, ex=ex)

        def down(addr):
            raise RuntimeError("info down")
        CY.LV.account = down
        alerts = []
        with mock.patch.object(C, "notify", side_effect=lambda t, x, p="default": alerts.append(p)):
            cy.target_resize("BTC", pos, 160.0, 100.0, 0.15)
        self.assertEqual(cy.positions["BTC"]["sz"], 1.0)                       # ledger unchanged; reconcile checks it
        self.assertEqual([c[2] for c in ex.calls if c[0] == "stop"], [1.6])
        self.assertIn("urgent", alerts)
        self.assertTrue(any("entry not filled" in x and "account unreadable" in x for x in cy.summary))


# 11 ----------------------------------------------------------------------------------------------------------------
class CarryCapital(Clean):
    def test_committed_capital_never_exceeds_equity(self):
        coins = ["HYPE", "PUMP", "XPL", "BTC", "ETH", "ZEC"]
        marks = {c: 30.0 for c in coins}
        cfg = dict(CFG, basket=coins, execution="taker")
        rates = {c: (0.00002 if c in ("HYPE", "PUMP", "XPL") else 0.0) for c in coins}
        cy = self.carry_cycle({}, marks, cfg, rates=rates)
        lev = cfg["perp_leverage"]
        for hour, more in enumerate((None, ("BTC", "ETH", "ZEC"), None)):
            if more:
                rates.update({c: 0.00003 for c in more})                      # three more qualify: n_active 6
            cy.now = T0 + hour * 3600
            cy.equity = PA.equity(cy.pot, cy.positions, cy.marks)[0]
            cy.manage_carry()
            committed = sum(p["capital"] for p in cy.positions.values())
            self.assertLessEqual(committed, cy.equity * (1 + 1e-9))
            for p in cy.positions.values():
                self.assertAlmostEqual(p["capital"], p["target_n"] * (1 + 1 / lev))
        self.assertEqual(len(cy.positions), 4)                                # 3 × 30% + one pair from the last 10%
        refused = [r for r in C.read_jsonl(L.REFUSED) if r.get("kind") == "carry"]
        self.assertTrue(refused and all(any(d["check"] == "gross exposure cap" for d in r["detail"]) for r in refused))
        self.assertAlmostEqual(CA.target_notional(1000, 6, cfg, free=100.0), 100.0 / 1.5)

    def test_a_pair_smaller_than_one_size_step_is_refused(self):
        # ZEC at 1300 with a 0.01 step: one step is 13 of pot currency; a 11-unit pair would round to zero coins
        cfg = dict(CFG, basket=["ZEC"], execution="taker")
        pos = {"HYPE": carry_pos(capital=1000 - 11 * 1.5 - 0.5)}                 # leaves room for an 11-unit pair only
        cy = self.carry_cycle(pos, {"ZEC": 1300.0, "HYPE": 30.0}, cfg, rates={"ZEC": 0.00003, "HYPE": 0.0},
                              pairs={"ZEC": {"pair": "@272", "token": "UZEC", "szd": 4, "vol": 5e6}}, mids={"@272": 1300.0}, szd_perp=2)
        cy.manage_carry()
        self.assertNotIn("ZEC", cy.positions)
        self.assertTrue(any("REFUSED" in x and "gross exposure cap" in x for x in cy.summary))


# 12 ----------------------------------------------------------------------------------------------------------------
class CarryOverride(Clean):
    def test_a_gap_below_one_size_step_triggers_nothing(self):
        # ZEC, perp size step 0.01 (about 7% of this leg): the old override "completed" it every hour, traded nothing
        # (the hedge rounded to zero), reset its timer and alerted the owner each time
        pos = carry_pos("ZEC", spot=0.1275, perp=0.1211, px=1300.0, pair="@272", target_n=166.67, stuck_since=T0 - 4 * 3600)
        cy = self.carry_cycle({"ZEC": pos}, {"ZEC": 1300.5}, dict(CFG, basket=["ZEC"]), pairs={"ZEC": {"pair": "@272", "token": "UZEC", "szd": 4, "vol": 5e6}},
                              mids={"@272": 1300.0}, szd_perp=2)
        with mock.patch.object(C, "notify") as nt, mock.patch.object(C, "alert") as al:
            cy.manage_carry()
        p = cy.positions["ZEC"]
        self.assertFalse(any("safety override" in x for x in cy.summary))
        self.assertFalse(nt.called or al.called)
        self.assertNotIn("stuck_since", p)
        self.assertEqual(p["legs"]["perp"]["sz"], 0.1211)
        self.assertEqual(p["orders"]["spot"]["side"], "sell")                 # the finer spot leg closes the gap itself
        self.assertAlmostEqual(p["orders"]["spot"]["sz"], 0.0064)

    def test_override_cancels_the_lagging_legs_resting_order(self):
        # the order that bought back 4,932 PUMP perp: left resting after the override completed the leg at market
        pos = carry_pos("HYPE", state="entering", spot=1.42, perp=0.0, px=93.2, target_n=132.4, stuck_since=T0,
                        orders={"perp": {"side": "sell", "px": 93.2566, "sz": 1.42, "t": T0 - 3600}})
        bars = {"@107": [], "HYPE": [{"t": T0 + 7200, "o": 92.5, "h": 93.5, "l": 92.3, "c": 93.4}]}
        cy = self.carry_cycle({"HYPE": pos}, {"HYPE": 92.0}, pairs={"HYPE": {"pair": "@107", "token": "HYPE", "szd": 2, "vol": 5e6}},
                              mids={"@107": 92.0}, now=T0 + 3600 + 60, bars={"@107": [], "HYPE": []}, szd_perp=2)
        cy.manage_carry()
        p = cy.positions["HYPE"]
        self.assertTrue(any("safety override" in x and "lagging leg completed" in x for x in cy.summary))
        self.assertEqual(p["legs"]["perp"]["sz"], 1.42)
        self.assertEqual(p["orders"], {})
        cy.now += 3 * 3600                                                    # later bars trade through the old price
        self.patch(CY.H, "candles", lambda name, tf, days: bars.get(name, []))
        cy.manage_carry()
        self.assertEqual(cy.positions["HYPE"]["legs"]["perp"]["sz"], 1.42)    # no second fill: 2.84 before

    def test_resting_orders_follow_what_is_still_needed(self):
        pos = carry_pos("HYPE", state="entering", spot=0.0, perp=0.0, target_sz=6.66,
                        orders={"spot": {"side": "buy", "px": 29.99, "sz": 9.0, "t": T0}, "perp": {"side": "buy", "px": 30.01, "sz": 2.0, "t": T0}})
        cy = self.carry_cycle({"HYPE": pos}, {"HYPE": 30.0}, pairs={"HYPE": {"pair": "@107", "token": "HYPE", "szd": 2, "vol": 5e6}},
                              mids={"@107": 30.0}, now=T0 + 3600)
        cy.manage_carry()
        o = cy.positions["HYPE"]["orders"]
        self.assertEqual((o["spot"]["side"], o["spot"]["sz"], o["spot"]["t"], o["spot"]["px"]), ("buy", 6.66, T0, 29.99))   # re-sized in place
        self.assertEqual((o["perp"]["side"], o["perp"]["sz"]), ("sell", 6.66))                                            # wrong side: re-placed


# 13 ----------------------------------------------------------------------------------------------------------------
class CarryTrend(Clean):
    def run_path(self, execution, hours=48, step=1.01):
        """Price trends +1%/hour for two days (spot = perp, no basis), funding stays high, then turns negative."""
        cfg = dict(CFG, execution=execution)
        px = [30.0 * step ** h for h in range(hours + 12)]
        bars = lambda now: [{"t": T0 + (h - 1) * 3600, "o": px[h - 1], "h": px[h] * 1.002, "l": px[h - 1] * 0.998, "c": px[h]}
                            for h in range(1, len(px)) if T0 + h * 3600 <= now][-3:]
        cy = self.carry_cycle({}, {"HYPE": px[0]}, cfg, pairs={"HYPE": {"pair": "@107", "token": "HYPE", "szd": 2, "vol": 5e6}},
                              mids={"@107": px[0]}, szd_perp=2)
        mids = {"@107": px[0]}
        self.patch(CY.H, "all_mids", lambda: mids)
        self.patch(CY.H, "candles", lambda name, tf, days: bars(cy.now))
        rate = {"HYPE": 0.00002}
        self.patch(CY.H, "funding_history", lambda coin, start: fund_rows(cy.now * 1000, rate["HYPE"]))
        fills, real = [], CA.apply_fill
        self.patch(CY.CA, "apply_fill", lambda pos, leg, side, p, sz, fee: (fills.append(p * sz), real(pos, leg, side, p, sz, fee))[1])
        gaps = []
        for h in range(hours + 10):                                          # the exit can take a few cycles with maker orders
            cy.now = T0 + h * 3600 + 300
            mids["@107"] = cy.marks["HYPE"] = px[h]
            if h == hours:
                rate["HYPE"] = -0.00001
            cy.equity = PA.equity(cy.pot, cy.positions, cy.marks)[0]
            cy.manage_carry()
            for p in cy.positions.values():
                gaps.append(abs(p["legs"]["spot"]["sz"] - p["legs"]["perp"]["sz"]))
            if h >= hours and not cy.positions:
                break
        self.assertEqual(cy.positions, {})
        rec = L.trades()[-1]
        return rec["gross"], sum(fills), max(gaps), rec

    def test_taker_hedge_loses_only_its_slippage(self):
        hedge, traded, gap, rec = self.run_path("taker")
        slip = C.settings()["paper_slippage_pct"] / 100
        self.assertLessEqual(gap, 1e-9)                                       # the legs never differ, every hour
        self.assertGreaterEqual(hedge, -slip * traded * 1.0001)               # a 60% trend costs the hedge nothing else
        self.assertLess(hedge, 0)
        self.assertLess(-hedge, 0.01 * 200)                                   # under 1% of the pair's notional

    def test_maker_hedge_is_bounded_by_the_unhedged_window(self):
        hedge, _traded, gap, rec = self.run_path("maker")
        # a resting leg that fills alone is completed at market after max_unhedged_hours (1h): the loss is bounded by
        # the move over that window (about 3% at +1%/hour), per one-legged fill, instead of growing with every 2% move
        self.assertGreater(hedge, -0.05 * 200 * 3)
        self.assertLessEqual(gap, 6.66)


# 14 ----------------------------------------------------------------------------------------------------------------
class AlertPriorities(Clean):
    def sent(self, fn, url="https://ntfy.example/topic"):
        with mock.patch.dict(os.environ, {"ALERT_WEBHOOK": url}), mock.patch.object(C.urllib.request, "urlopen") as uo:
            fn()
        return [c[0][0] for c in uo.call_args_list]

    def test_ntfy_priority_and_title_headers(self):
        for p, want in (("urgent", "5"), ("high", "4"), ("default", "3"), ("low", "2"), ("min", "1"), ("bogus", "3"), (5, "5")):
            req = self.sent(lambda: C.alert("stop missing", p, "Executor: test"))[0]
            self.assertEqual(req.get_header("Priority"), want)
            self.assertEqual(req.get_header("Title"), "Executor: test")
            self.assertEqual(req.data, b"stop missing")
        req = self.sent(lambda: C.notify("Executor: closed", "ETH on stop"))[0]          # the old two-part call still works
        self.assertEqual((req.get_header("Priority"), req.get_header("Title")), ("3", "Executor: closed"))
        req = self.sent(lambda: C.alert("x", "urgent"), url="https://hooks.slack.com/services/T/B/C")[0]
        self.assertTrue(json.loads(req.data)["text"].startswith("URGENT · Executor: x"))

    def test_paper_trades_are_not_pushed_live_ones_are_silent(self):
        TC.CTX["ETH"] = TC.ctx(daily=1)
        cy = self.cycle("paper", {"ETH": TC.paper_pos("ETH")}, {"ETH": []}, {"ETH": 104.0})
        self.assertEqual(self.sent(cy.manage_exits), [])                                   # closed in paper: logged only
        ex = TC.FakeEx()
        pos = TC.paper_pos("ETH")
        pos.update({"mode": "live", "stop_cloid": "0xold", "sz": 2.5})
        cy = self.cycle("live", {"ETH": pos}, {"ETH": []}, {"ETH": 100.0}, ex=ex)
        reqs = self.sent(lambda: cy.close_position("ETH", pos, 100.0, "4h flip", 1000))
        self.assertEqual([r.get_header("Priority") for r in reqs], ["2"])

    def test_live_money_problems_are_urgent(self):
        cy = self.cycle("live", {}, {}, {"ETH": 100.0}, ex=TC.FakeEx())
        CY.LV.reconcile = lambda local, addr: {"ok": False, "problems": ["ETH: on exchange, not in ledger"]}
        try:
            reqs = self.sent(cy.reconcile)
        finally:
            CY.LV.reconcile = LV.reconcile
        self.assertEqual(reqs[0].get_header("Priority"), "5")

    def test_alert_once_holds_across_cycles_but_not_without_a_channel(self):
        self.assertEqual(self.sent(lambda: C.alert_once("k", "m", "high"), url=""), [])   # no channel: not marked sent
        self.assertEqual(len(self.sent(lambda: C.alert_once("k", "m", "high"))), 1)
        self.assertEqual(self.sent(lambda: C.alert_once("k", "m", "high")), [])           # the next cycle: silent
        sent = C.load_json(C.SENT)
        sent["k"] -= 25 * 3600
        C.write_json(C.SENT, sent)
        self.assertEqual(len(self.sent(lambda: C.alert_once("k", "m", "high", every_hours=24))), 1)


# 15 ----------------------------------------------------------------------------------------------------------------
class LostStopReply(Clean):
    def test_a_stop_that_landed_is_adopted_not_placed_twice(self):
        ex = TC.FakeEx({"stop": TimeoutError("reply lost")})
        pos = TC.paper_pos("ETH")
        pos.update({"mode": "live", "stop_cloid": None})
        cy = self.cycle("live", {"ETH": pos}, {"ETH": []}, {"ETH": 100.0}, ex=ex)
        cid = "0x" + "ab" * 16                                                 # TC's fake client id
        cy.info = object()                                                     # a live client exists
        self.patch(CY.H, "frontend_open_orders", lambda addr: [{"coin": "ETH", "cloid": cid.upper().replace("X", "x")}, {"coin": "BTC"}])
        self.assertTrue(cy.protect("ETH", pos, 96.0))
        self.assertEqual([c[0] for c in ex.calls], ["stop"])                   # one request, no retry, no close
        self.assertEqual(L.positions("live")["ETH"]["stop_cloid"], cid)

    def test_without_the_order_a_retry_still_happens(self):
        ex = TC.FakeEx({"stop": TimeoutError("reply lost")})
        pos = TC.paper_pos("ETH")
        pos.update({"mode": "live", "stop_cloid": None})
        cy = self.cycle("live", {"ETH": pos}, {"ETH": []}, {"ETH": 100.0}, ex=ex)
        cy.info = object()
        self.patch(CY.H, "frontend_open_orders", lambda addr: [])
        ex.script["close"] = TC.FILL(100.0, pos["sz"])
        self.assertFalse(cy.protect("ETH", pos, 96.0))                         # two attempts, then closed rather than held
        self.assertEqual([c[0] for c in ex.calls], ["stop", "stop", "market_close"])
        self.patch(CY.H, "frontend_open_orders", lambda addr: (_ for _ in ()).throw(RuntimeError("down")))
        self.assertIsNone(LV.resting_cloids("0xaddr"))


# 16 ----------------------------------------------------------------------------------------------------------------
class Workflows(unittest.TestCase):
    def test_control_and_go_live_have_their_own_concurrency_groups(self):
        wf = ROOT / ".github" / "workflows"
        control, golive = (wf / "control.yml").read_text(), (wf / "go-live.yml").read_text()
        self.assertIn("group: executor-control-${{ inputs.agent }}", control)
        self.assertIn("group: executor-go-live", golive)
        self.assertNotIn("group: executor\n", control + golive)
        self.assertIn('--override "$OVERRIDE"', golive)


if __name__ == "__main__":
    unittest.main()
