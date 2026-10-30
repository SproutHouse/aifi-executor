"""The stopgap event parser (scripts/dashboard_push.py) against cycle.py's own say() formats.

Every self.say(...) call in src/executor/cycle.py is found in the source tree, rendered with sample values by evaluating
its own expression (and the f-string assignments it depends on), and must parse into the exact event tuple below. A
reworded say(), a new say() without a template here, or a template here whose say() is gone all fail this test. The
engine's detail formats the parser reads (freshness, universe.check, risk.pre_trade, describe, proposal ids) are
rendered by the engine's own functions for the same reason. Also: diag.unparsed == 0 on the real run docs."""
import ast, json, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import _path  # noqa: F401
from executor import cycle as CY, regime as R, proposals as P, universe as U, risk as K, live as LV

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dashboard_push as DP  # noqa: E402

REAL = Path(__file__).resolve().parent / "fixtures" / "real"
SETTINGS = json.loads((REAL / "config" / "settings.json").read_text())
SKIP = DP.SKIP


def mode_note(creds, sdk=True):
    s = dict(SETTINGS, mode="live")
    with mock.patch.object(LV, "creds", return_value=creds), mock.patch.object(LV, "available", return_value=sdk):
        return CY.resolve_mode(s)[1]


def fresh_detail(minutes):
    T = 1790208000
    return CY.freshness([{"t": T - 14400, "T": T}], T + minutes * 60 + 17, SETTINGS)


def base_self(**kw):
    d = dict(btc={"weekly_dir": -1, "daily_dir": -1}, fresh_detail="21 min after the bar close", s=SETTINGS, mode="paper",
             mode_note="", halt_reason="manual halt", thr={"multiplier": 1.0, "drawdown_pct": 0.0, "halt": False, "peak": None},
             counts={"evaluated": 14, "triggers": 2, "refused": 1, "proposed": 0, "entered": 1}, positions={"LINK": {}}, equity=1000.0,
             dry=False, hours_mode="auto", now=1790310000)
    d.update(kw)
    return SimpleNamespace(**d)


CAND = {"coin": "LINK", "side": "long", "kind": "flip", "tier": "A", "stop": 12.843, "book": "eth-defi"}
SIZING = {"dist_pct": 2.81, "notional_pct_equity": 84.2, "leverage": 3, "risk_pct": 1.0}
PID = P.new_id("ETH", "pullback", 1790223895)
FAILED = [{"check": "universe filters", "ok": False, "detail": "24h volume 22.0M below 30M; funding 68%/yr against longs above 30%"},
          {"check": "below max positions", "ok": False, "detail": "6 open of 6"}]
E_CONN = ConnectionError("HTTPSConnectionPool(host='api.hyperliquid.xyz', port=443): Read timed out.")

# fragment of the say() source → [(namespace overrides, fresh, expected tuple or SKIP, expected aux subset)]
CASES = {
    "BTC weekly": [({"self": base_self(fresh_detail=fresh_detail(132)[1])}, False, ("late", None, None, None, "132", None, None), {"min": 132}),
                   ({"self": base_self(fresh_detail=fresh_detail(21)[1])}, True, SKIP, None)],
    "closed on": [({"coin": "LINK", "pos": {"book": "eth-defi", "benchmark": "ETH"}, "reason": "4h flip", "px": 13.894,
                    "rec": {"R": 2.1, "rel_R": 0.35}}, True, ("sold", "LINK", None, None, "h4", 2.1, 0.35), {"book": "eth-defi"}),
                  ({"coin": "SOL", "pos": {"book": "solana", "benchmark": "SOL"}, "reason": "stop (exchange)", "px": 0.000012345,
                    "rec": {"R": -1.04, "rel_R": None}}, True, ("sold", "SOL", None, None, "exch", -1.04, None), None)],
    "could not place the resident stop": [({"coin": "SOL", "e": RuntimeError("stop order rejected: Order has invalid price.")}, True,
                                           ("no_stop", "SOL", None, None, None, None, None), None)],
    "ENTERED": [({"coin": "LINK", "cand": CAND, "sizing": SIZING}, True, ("bought", "LINK", "flip", "A", "stop 2.8", None, None),
                 {"book": "eth-defi", "stop": 12.843})],
    "names · ": [({"c": {"evaluated": 14, "triggers": 2, "refused": 1, "proposed": 0, "entered": 1}}, True, SKIP, None)],
    "gain earmarked": [({"pos": {"coin": "UNI"}, "bench": "ETH", "rec": {"pnl": 4.2}}, True, ("sweep", "UNI", None, None, "ETH 0.42", None, None), None)],
    "no reading on one timeframe": [({"coin": "XRP"}, True, ("gap", "XRP", None, None, None, None, None), None)],
    "stop trailed to": [({"coin": "LINK", "new_stop": 13.366}, True, ("trail", "LINK", None, None, None, None, None), {"stop": 13.366})],
    "RECONCILIATION MISMATCH": [({"r": {"problems": ["LINK size 63.8 on the exchange vs 63.7558 in the ledger", "equity 377.19 vs 380.00"]}}, True,
                                 ("recon", None, None, None, None, None, None), None)],
    "]: W ": [({"coin": "BTC", "book_name": "bitcoin", "ctx": {"weekly_dir": -1, "daily_dir": -1, "days": 1500},
                "h4r": {"dir": 1, "range": "Overextended"}, "cand": None, "why": ["no trigger on the last 4-hour bar"], "vol_m": 3938.4,
                "fa": 10.95}, True, SKIP, None)],
    "REFUSED": [({"coin": "LINK", "cand": CAND, "failed": FAILED}, True, ("blocked", "LINK", "flip", "A", "vol 0.73,fund 68,maxpos 6", None, None),
                 {"codes": [["vol", 0.73], ["fund", 68], ["maxpos", 6]]})],
    "PROPOSED {doc": [({"coin": "ETH", "cand": dict(CAND, coin="ETH", kind="pullback", tier="B"), "doc": {"id": PID, "expires": "2026-09-24T08:00:00Z"}},
                       True, ("proposed", "ETH", "pullback", "B", None, None, None), {"id": PID}),
                      ({"coin": "ETH", "cand": dict(CAND, coin="ETH", kind="pullback", tier="B"), "doc": {"id": PID, "expires": "2026-09-24T08:00:00Z"},
                        "self": base_self(hours_mode="approval")}, True, ("proposed", "ETH", "pullback", None, None, None, None), None)],
    "self.mode_note": [({"self": base_self(mode_note=mode_note((None, None)))}, True, ("fallback", None, None, None, "key", None, None), None),
                       ({"self": base_self(mode_note=mode_note(("k", "a"), sdk=False))}, True, ("fallback", None, None, None, "sdk", None, None), None)],
    "HALT set": [({"self": base_self(halt_reason="manual halt")}, True, ("halt", None, None, None, "manual halt", None, None), None),
                 ({"self": base_self(halt_reason="manual flatten 2026-09-25T03:12:00.123456Z")}, True,
                  ("halt", None, None, None, "manual flatten", None, None), None),
                 ({"self": base_self(halt_reason="LINK open without a resident stop and the close failed 2026-09-25T03:12:00.1Z")}, True,
                  ("halt", None, None, None, "LINK open without a stop", None, None), None),
                 ({"self": base_self(halt_reason="pot $1,234 is too small")}, True, ("halt", None, None, None, "pot … is too small", None, None), None),
                 ({"self": base_self(halt_reason="equity was 1000.0, pausing for the weekend")}, True,
                  ("halt", None, None, None, "equity was …, pausing for the weekend", None, None), None)],
    "close NOT filled": [({"coin": "LINK", "second": "Insufficient margin $843.12"}, True, ("close_failed", "LINK", None, None, None, None, None), None)],
    "not on the exchange": [({"coin": "LINK"}, True, ("not_on_exchange", "LINK", None, None, None, None, None), None)],
    "but no mark price": [({"coin": "LINK", "reason": "daily flip"}, True, ("exit_failed", "LINK", None, None, "nomark", None, None), None)],
    "entry not filled": [({"coin": "BNB", "second": "{'status': 'err', 'response': 'notional $843.12'}"}, True,
                          ("notfilled", "BNB", None, None, None, None, None), None)],
    "not listed on Hyperliquid": [({"coin": "PUMP", "book_name": "solana"}, True, ("_x", "PUMP", None, None, None, None, None), None)],
    "candles unavailable": [({"coin": "JTO", "e": RuntimeError("https://api.hyperliquid.xyz/info: timed out")}, True,
                             ("entry_failed", "JTO", None, None, "candles", None, None), None)],
    "recorded, not traded": [({"coin": "UNI", "cand": dict(CAND, coin="UNI", kind="pullback", tier="B")}, True,
                              ("recorded", "UNI", "pullback", "B", None, None, None), None)],
    "would PROPOSE": [({"coin": "ETH", "cand": dict(CAND, coin="ETH"), "sizing": SIZING, "self": base_self(dry=True)}, True, SKIP, None)],
    "expired unapproved": [({"d": {"candidate": {"coin": "ETH"}, "id": PID}}, True, ("expired", "ETH", "pullback", None, None, None, None), {"id": PID})],
    "THROTTLE HALT": [({"self": base_self(thr={"multiplier": 0.0, "drawdown_pct": 20.43, "halt": True, "peak": 1})}, True,
                       ("thr_halt", None, None, None, "20.4", None, None), None)],
    "CYCLE ABORTED": [({"e": E_CONN}, True, ("failed", None, None, None, "ConnectionError", None, None), None)],
    "exit management failed": [({"coin": "LINK", "e": KeyError("h4"), "self": base_self(mode="live")}, True,
                                ("exit_failed", "LINK", None, None, "KeyError", None, None), None)],
    "old stop cancel failed": [({"coin": "LINK", "e": E_CONN}, True, SKIP, None)],
    "throttle: drawdown": [({"self": base_self(thr={"multiplier": 0.5, "drawdown_pct": 11.24, "halt": False, "peak": 1})}, True,
                            ("thr_half", None, None, None, "11.2", None, None), None)],
    "leftover stop cancel failed": [({"coin": "LINK", "e": E_CONN}, True, SKIP, None)],
    "% of pot, holding": [({"coin": "BTC", "tgt": 330.0, "cur": 0.0, "eq": 1000.0, "action": "open"}, True, SKIP, None)],
    # Command Center §6.1: the five acting lines are typed events now (the `target` weights line stays SKIP)
    "carry ENTERING": [({"coin": "HYPE", "apr": 0.349, "n": 200.0, "self": base_self()}, True, ("carry_in", "HYPE", "carry", None, "34.9", None, None), None)],
    "carry EXITING": [({"coin": "HYPE", "apr": -0.002}, True, ("carry_out", "HYPE", "carry", None, "-0.2", None, None), None),
                      ({"coin": "HYPE", "apr": None}, True, ("carry_out", "HYPE", "carry", None, "0.0", None, None), None)],
    "carry CLOSED": [({"coin": "HYPE", "rec": {"pnl": 1.2, "capture": 0.85}, "cap": "85%", "self": base_self()}, True,
                      ("carry_closed", "HYPE", "carry", None, "+0.12,85%", None, None), None),
                     ({"coin": "HYPE", "rec": {"pnl": -0.5, "capture": None}, "cap": "n/a", "self": base_self()}, True,
                      ("carry_closed", "HYPE", "carry", None, "-0.05,n/a", None, None), None)],
    "carry safety override": [({"coin": "HYPE", "cfg": {"max_unhedged_hours": 3}, "what": "lagging leg completed"}, True, ("carry_fix", "HYPE", "carry", None, None, None, None), None),
                              ({"coin": "HYPE", "cfg": {"max_unhedged_hours": 3}, "what": "leading leg trimmed"}, True, ("carry_fix", "HYPE", "carry", None, None, None, None), None)],
    "carry dust": [({"coin": "HYPE", "leg": "spot"}, True, SKIP, None)],
    "resized to": [({"coin": "BTC", "tgt": 480.0, "new_stop": 71642.35, "self": base_self()}, True, ("resized", "BTC", "target", None, "48", None, None), None)],
    "entry check failed": [({"coin": "HYPE", "e": ValueError("could not convert string to float: ''")}, True,
                            ("entry_failed", "HYPE", None, None, "ValueError", None, None), None)],
    # the long-short book (2026-10-18, shadow agents, paper only): its own lines are SKIP; its trades are the usual
    # ENTERED / closed on / resized to / REFUSED / target lines (a short's ENTERED carries "short" and tier S)
    "runs in paper with target.shorts": [({}, True, SKIP, None)],
    "no Bitcoin bars": [({}, True, SKIP, None)],
    "funding history unavailable": [({"coin": "PUMP", "e": E_CONN}, True, SKIP, None)],
    "BOOK BRAKE": [({"eq": 850.0, "book": {"peak": 1000.0}, "until": "2026-11-12", "p": {"brake_dd": 0.15, "brake_days": 28}}, True, SKIP, None)],
    "book brake lifted": [({}, True, SKIP, None)],
    "book brake on": [({"until": "2026-11-12"}, True, SKIP, None)],
    "between rebalances (next on": [({"nxt": "2026-10-22", "self": base_self()}, True, SKIP, None)],
    "universe unavailable": [({"e": E_CONN}, True, SKIP, None)],
    "no reading today": [({"info": {"why": "no bars"}}, True, SKIP, None)],
    "names ranked of": [({"day_s": "2026-10-15", "info": {"ranked": 25, "long": ["AAVE", "SOL"], "short": ["PUMP", "XPL"], "why": ""},
                          "elig": ["AAVE"] * 28, "u": {"n": 30}, "w": {"AAVE": 0.1}}, True, SKIP, None),
                         ({"day_s": "2026-10-15", "info": {"ranked": 9, "why": "only 9 names could be ranked, fewer than 12: no book this week"},
                           "elig": ["AAVE"] * 9, "u": {"n": 30}, "w": {}}, True, SKIP, None)],
    # one decision per rebalance day (audit E3/N3) and the leg-formation refusals and unchecked names (E1/E10): SKIP too
    "the day's book stands": [({"day_s": "2026-10-29", "dec": {"decided": "2026-10-30T00:05:54Z", "long": ["ARB"], "short": ["SOL"],
                                                              "weights": {"ARB": 0.04, "SOL": -0.04}},
                                "pend": {"AAVE": "open refused: price sanity band"}}, True, SKIP, None),
                               ({"day_s": "2026-10-29", "dec": {"decided": "2026-10-30T00:05:54Z", "weights": {}, "why": "a leg is empty"},
                                 "pend": {}}, True, SKIP, None)],
    "the first fresh run decides": [({"day_s": "2026-10-29", "self": base_self(fresh_detail="run started 200 min after the bar close, limit 180")},
                                     True, SKIP, None)],
    "refused at leg formation": [({"refused": {"long": {"ENA": [{"check": "universe filters", "ok": False, "detail": "funding 51%/yr against longs above 30%"}]},
                                               "short": {"LIT": [{"check": "price sanity band", "ok": False, "detail": "mark vs Binance 268.37%"}]}},
                                   "text": lambda f: "; ".join(x["detail"] for x in f)}, True, SKIP, None)],
    "no second source for the price band": [({"unchecked": {"kPEPE": "no Binance kPEPEUSDT pair", "VVV": "no Binance VVVUSDT pair"},
                                              "by_why": {"no Binance kPEPEUSDT pair": ["kPEPE"], "no Binance VVVUSDT pair": ["VVV"]},
                                              "elig": ["AAVE"] * 30}, True, SKIP, None)],
}


def say_sites():
    """[(enclosing FunctionDef, the say() Call node, the argument's source)] for every self.say(...) in cycle.py."""
    tree = ast.parse((ROOT / "src" / "executor" / "cycle.py").read_text())
    out = []
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "say"
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"):
                    out.append((fn, node, ast.unparse(node.args[0])))
    return out


def render(fn, call, overrides):
    """Evaluate the say() argument with sample values, after the f-string assignments of its function that it uses."""
    ns = {"R": R, "P": P, "describe": CY.describe, "self": base_self(), "coin": "LINK", "cand": CAND, "sizing": SIZING}
    ns.update(overrides)
    used = {n.id for n in ast.walk(call.args[0]) if isinstance(n, ast.Name)}
    for node in sorted((n for n in ast.walk(fn) if isinstance(n, ast.Assign)), key=lambda n: n.lineno):
        if (node.lineno < call.lineno and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in used and node.targets[0].id not in overrides and any(isinstance(x, ast.JoinedStr) for x in ast.walk(node.value))):
            ns[node.targets[0].id] = eval(compile(ast.fix_missing_locations(ast.Expression(node.value)), "cycle.py", "eval"), ns)  # noqa: S307
    return eval(compile(ast.fix_missing_locations(ast.Expression(call.args[0])), "cycle.py", "eval"), ns)  # noqa: S307


class SayTemplates(unittest.TestCase):
    def test_every_say_parses_into_its_event(self):
        sites = say_sites()
        self.assertEqual(len(sites), 69, "cycle.py gained or lost a say(): add or remove its template case here")
        used = set()
        for fn, call, src in sites:
            keys = [k for k in CASES if k in src]
            self.assertEqual(len(keys), 1, f"line {call.lineno}: {src[:90]} matches {keys}")
            used.add(keys[0])
            for overrides, fresh, want, aux in CASES[keys[0]]:
                line = render(fn, call, overrides)
                got = DP.parse_line(line, fresh)
                with self.subTest(line=line):
                    self.assertIsNotNone(got, f"unparsed: {line}")
                    if want is SKIP:
                        self.assertIs(got, SKIP)
                    else:
                        self.assertEqual(tuple(got), want)
                        for k, v in (aux or {}).items():
                            self.assertEqual(got.aux.get(k), v)
        self.assertEqual(used, set(CASES), "a template case whose say() no longer exists")

    def test_rendered_lines_carry_no_money_into_events(self):
        for fn, call, src in say_sites():
            key = next(k for k in CASES if k in src)
            for overrides, fresh, want, _aux in CASES[key]:
                got = DP.parse_line(render(fn, call, overrides), fresh)
                if got is not SKIP:
                    for part in got:
                        if isinstance(part, str):
                            self.assertIsNone(DP.FORBIDDEN_STR.search(part), part)
                            self.assertNotIn("843", part)


class BookLines(unittest.TestCase):
    """The long-short book's trade lines parse into the usual events, its short side marked by tier S."""
    def test_short_entry_and_signed_target_lines(self):
        cand = {"coin": "PUMP", "side": "short", "kind": "book", "tier": "S", "stop": 0.0061, "book": "longshort"}
        sizing = {"dist_pct": 50.0, "notional_pct_equity": 6.4, "leverage": 3, "risk_pct": 3.2}
        got = DP.parse_line("PUMP: ENTERED " + CY.describe(cand, sizing))
        self.assertEqual(tuple(got), ("bought", "PUMP", "book", "S", "stop 50", None, None))
        self.assertIs(DP.parse_line("PUMP: target -6% of pot, holding -7% → hold"), SKIP)
        self.assertIs(DP.parse_line("PUMP: target -6% of pot, holding +0% → open"), SKIP)
        got = DP.parse_line("PUMP [longshort]: closed on book brake at 0.0049 → +0.31 R")
        self.assertEqual((got[0], got[4], got[5]), ("sold", "brake", 0.31))
        self.assertEqual(DP.TW_RX.match("PUMP: target -6% of pot, holding -7% → hold").group(2), "-6")


class EngineDetails(unittest.TestCase):
    """The detail strings the reason-code normaliser reads, produced by the engine's own functions."""

    def test_universe_reasons(self):
        row = {"dayNtlVlm": 7.8e6, "openInterest": 100, "markPx": 50, "maxLeverage": 2, "funding": 0.0000775}
        ok, reasons = U.check("JUP", row, SETTINGS["universe"], 190)
        self.assertFalse(ok)
        self.assertEqual(DP.universe_codes("; ".join(reasons)), [["vol", 0.26], ["oi", 0], ["lev", 2], ["fund", 68], ["days", 190]])
        self.assertEqual(DP.universe_codes("; ".join(U.check("X", None, SETTINGS["universe"])[1])), [["list", None]])

    def test_pre_trade_details(self):
        s = SETTINGS
        pos = {c: {"risk_amt": 12.0, "notional": 900.0, "book": "eth-defi"} for c in ("A", "B", "C", "D", "E", "LINK")}
        flags = {"halt": True, "halt_reason": "manual halt", "throttle_halt": True, "drawdown_pct": 20.43, "fresh": False,
                 "fresh_detail": fresh_detail(143)[1], "reconcile_mismatch": True, "reconcile_detail": "equity 377.19 vs 380",
                 "sanity_ok": False, "sanity_detail": "mark vs Binance 2.31%", "universe_ok": False,
                 "universe_reasons": ["24h volume 10.7M below 30M"], "book_cap_pct": 2.5}
        sizing = {"refused": "notional below the exchange minimum of 10", "risk_amt": 12.0, "notional": 900.0}
        _ok, checks = K.pre_trade({"coin": "LINK", "book": "eth-defi"}, sizing, pos, 400.0, s, flags)
        codes = []
        for c in checks:
            if not c["ok"]:
                codes += DP.check_codes(c["check"], c["detail"])
        self.assertEqual(codes, [["halt", None], ["thr", 20.4], ["fresh", 143], ["recon", None], ["sizing", None], ["dup", None],
                                 ["maxpos", 6], ["cap", 21], ["gross", 15.75], ["bookcap", 21], ["sanity", 2.31], ["vol", 0.36]])
        _ok, checks = K.pre_trade({"coin": "LINK"}, {}, {}, 0.0, s, {"fresh": True})
        eq = next(c for c in checks if c["check"] == "equity positive")
        self.assertEqual(DP.check_codes(eq["check"], eq["detail"]), [["equity", None]])       # its money detail is dropped

    def test_refusal_records(self):
        self.assertEqual(DP.refusal_codes({"stage": "policy", "detail": "tier B is not automated and approvals are disabled"}), [["tier", None]])
        self.assertEqual(DP.refusal_codes({"stage": "proposal", "detail": "proposal expired unapproved"}), [["expired", None]])
        self.assertEqual(DP.refusal_codes({"stage": "execution", "detail": "IOC entry not filled: $843.12"}), [["fill", None]])
        self.assertEqual(DP.refusal_codes({"stage": "approval", "detail": "price ran 1.23% above the signal mark"}), [["drift", 1.23]])
        self.assertEqual(DP.refusal_codes({"stage": "approval", "detail": [{"check": "open-risk cap", "ok": False}]}), [["recheck", None]])


def run_doc(t, summary, readings=None, **kw):
    d = {"t": DP.iso_ms(t)[:19] + "Z", "mode": "paper", "fresh": True, "failed": False, "halt": False, "btc_weekly": "Bullish",
         "btc_daily": "Bullish", "positions": [], "counts": {"evaluated": 3, "triggers": 0, "refused": 0, "proposed": 0, "entered": 0},
         "summary": summary, "readings": readings or []}
    d.update(kw)
    return d


def reading(coin, w="Bullish", d="Bullish", h4="Bearish", vol=100.0):
    return {"coin": coin, "weekly": w, "daily": d, "h4": h4, "line": 10.5, "close": 10.0, "trigger": None,
            "why": "no trigger on the last 4-hour bar" if (w, d) == ("Bullish", "Bullish") else
            ("weekly Momentum Cloud not bullish" if w != "Bullish" else "daily Momentum Cloud not bullish"),
            "vol_m": vol, "funding_pct": 10.95, "days": 1500}


class Diffs(unittest.TestCase):
    """Events that come from comparing runs: board, regime, resume; and the halt dedupe."""

    def build(self, docs, now):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            st, cfg = Path(d) / "state", Path(d) / "config"
            (st / "runs").mkdir(parents=True)
            cfg.mkdir()
            (cfg / "settings.json").write_text(json.dumps(SETTINGS))
            (cfg / "books.json").write_text(json.dumps({"books": [{"book": "b", "benchmark": "BTC", "names": ["BTC", "ETH", "AAVE"]}]}))
            (st / "runs" / "x.jsonl").write_text("".join(json.dumps(x) + "\n" for x in docs))
            return DP.build(st, cfg, now)["latest"]

    def test_board_regime_resume_and_halt_dedupe(self):
        t = 1790266854
        btc = "BTC weekly Bullish · daily Bullish · data 21 min after the bar close"
        docs = [run_doc(t, [btc], [reading("BTC"), reading("ETH"), reading("AAVE", vol=12)]),
                run_doc(t + 14400, ["HALT set: manual halt (exits still managed, no entries)", btc],
                        [reading("BTC", h4="Bullish"), reading("ETH", d="Bearish"), reading("AAVE", vol=40)], halt=True, btc_daily="Bearish"),
                run_doc(t + 28800, ["HALT set: manual halt (exits still managed, no entries)", btc],
                        [reading("BTC", h4="Bullish"), reading("ETH", d="Bearish"), reading("AAVE", vol=40)], halt=True, btc_daily="Bearish"),
                run_doc(t + 43200, [btc], [reading("BTC", h4="Bullish"), reading("ETH", d="Bearish"), reading("AAVE", vol=40)])]
        L = self.build(docs, t + 43200 + 1800)
        ev = [(e[0] - t, e[1], e[2], e[6]) for e in L["events"]]
        self.assertIn((14400, "board", "BTC", "h4 0>1,a out"), ev)
        self.assertIn((14400, "board", "ETH", "d 1>0,a out"), ev)
        self.assertIn((14400, "board", "AAVE", "a in"), ev)
        self.assertIn((14400, "regime", None, "BB>Bb"), ev)
        self.assertIn((43200, "regime", None, "Bb>BB"), ev)
        self.assertEqual([x for x in ev if x[1] == "halt"], [(14400, "halt", None, "manual halt")])       # once, on the transition
        self.assertIn((43200, "resume", None, None), ev)
        self.assertEqual(L["diag"]["unparsed"], 0)
        self.assertEqual([r["rd"] for r in L["runs"]], ["aat", "uda", "uda", "uda"])

    def test_unparsed_lines_are_counted_not_shipped(self):
        t = 1790266854
        L = self.build([run_doc(t, ["LINK: something the engine never said before, equity 1234.56"])], t + 600)
        self.assertEqual(L["diag"]["unparsed"], 1)
        self.assertNotIn("1234.56", DP.dumps(L))


class RealRuns(unittest.TestCase):
    def test_real_run_docs_fully_parsed(self):
        b = DP.build(REAL / "state", REAL / "config", 1790311646.06)
        self.assertEqual(b["latest"]["diag"], {"unparsed": 0})
        self.assertEqual(b["unparsed"], [])
        n = 0
        for f in sorted((REAL / "state" / "runs").glob("*.jsonl")):
            for line in f.read_text().splitlines():
                doc = json.loads(line)
                for s in doc["summary"]:
                    self.assertIsNotNone(DP.parse_line(s, doc["fresh"]), s)
                    n += 1
        self.assertEqual(n, 28)


if __name__ == "__main__":
    unittest.main()
