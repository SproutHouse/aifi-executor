"""The long-short book's rebalance decision and its second price source (audit 2026-10-23 E1, E3, E10; 2026-10-30 N3).

  one decision   a rebalance day is decided once, by its first fresh run, and saved in book.json before any trade; the
                 later runs that day (00:05, 01:05, 02:05 UTC) keep that book however the funding they read moves, and
                 only finish it: an open refused (or never reached) is retried, nothing else is re-sized. A run whose
                 data is not fresh decides nothing. The next rebalance day decides afresh.
  visible        leg-formation refusals are said, counted and recorded (stage "leg formation"), with their reasons; the
                 names that had no second source for the price band are listed with why (it fails open for them).
  second source  Binance's price counts only while the pair trades: a halted pair's frozen ticker (LITUSDT, XMRUSDT,
                 status BREAK) and a stale one are "no second source", so they no longer refuse a name on both sides.
"""
import json, sys, time, unittest
from unittest import mock
import _path  # noqa: F401
from executor import common as C, cycle as CY, ledger as L, longshort as XS, binance_data as B
import test_cycle as TC
from test_longshort import SHADOW, P, make_panel
from test_fleet import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import dashboard_push as DP  # noqa: E402

DAY = 86400
REB = 20377 // 7 * 7                     # an epoch day divisible by 7: a rebalance day


class BookDay(TC.Base):
    def setUp(self):
        super().setUp()
        self._lp = CY.B.last_price
        CY.B.last_price = lambda coin: None
        CY.BOOK.unlink(missing_ok=True)
        B.forget()

    def tearDown(self):
        CY.B.last_price = self._lp
        CY.BOOK.unlink(missing_ok=True)
        B.forget()
        super().tearDown()

    def run_book(self, panel, funding=None, fresh=True, patch=None):
        """One daily run of the book on the positions and pot the previous run left on disk."""
        marks = {c: b[-1]["c"] for c, b in panel.items()}
        pot = C.load_json(CY.PA.POT)
        cy = self.cycle("paper", L.positions("paper"), {}, marks)
        cy.s = dict(SHADOW)
        cy.bars.get = lambda coin: (panel[coin], panel[coin])
        cy.ctxs = {c: {"szDecimals": 3, "markPx": str(m), "funding": str((funding or {}).get(c, 0.10) / 8760), "maxLeverage": 10,
                       "dayNtlVlm": str(panel[c][-1]["v"] * m), "openInterest": str(5e6 / m)} for c, m in marks.items()}
        cy.pot = pot if pot else {"cash": 1000.0, "start": 1000.0}
        cy.equity = CY.PA.equity(cy.pot, cy.positions, cy.marks)[0]
        cy.fresh = fresh
        if not fresh:
            cy.fresh_detail = "run started 200 min after the bar close, limit 180"
        for name, fn in (patch or {}).items():
            setattr(cy, name, fn.__get__(cy))
        cy.manage_book()
        return cy

    @staticmethod
    def held():
        return {c: (p["side"], round(p["sz"], 9)) for c, p in L.positions("paper").items()}

    @staticmethod
    def decision():
        return (C.load_json(CY.BOOK) or {}).get("last_rebalance") or {}


class OneDecisionPerRebalanceDay(BookDay):
    def test_the_same_book_across_three_runs_with_changing_funding(self):
        panel = make_panel()
        cy1 = self.run_book(panel)
        dec, book1, n = self.decision(), self.held(), len(L.trades())
        longs, shorts = dec["long"], dec["short"]
        self.assertTrue(longs and shorts)
        self.assertEqual(dec["day"], C.iso(REB * DAY)[:10])
        self.assertEqual(dec["decided"], C.iso(cy1.now))
        self.assertEqual(dec["pending"], {})                                  # everything traded by the deciding run
        self.assertEqual(sorted(c for c, x in dec["weights"].items() if x > 0), longs)
        # the funding the next runs read moves names across the refusal line, as on 2026-10-30 (ENA -66 → +56 %/yr)
        top_long, top_short = longs[0], shorts[0]
        moved2 = {top_long: 0.56}                                             # 01:05: a decided long too dear to buy now
        moved3 = {top_long: 0.56, top_short: -0.45}                           # 02:05: and a decided short too dear to short
        elig = sorted(panel)
        w2, _ = XS.latest(panel, P, elig, {top_long}, set())                  # what re-forming the legs would have done
        self.assertNotEqual(sorted(c for c, x in w2.items() if x > 0), longs)
        for moved in (moved2, moved3):
            cy = self.run_book(panel, funding=moved)
            self.assertEqual(self.held(), book1)                              # the same book: nothing opened, closed or re-sized
            self.assertEqual(len(L.trades()), n)
            self.assertEqual((self.decision()["long"], self.decision()["short"]), (longs, shorts))
            self.assertEqual(self.decision()["decided"], dec["decided"])
            self.assertTrue(any("the day's book stands" in x and "nothing pending" in x for x in cy.summary), cy.summary)
            self.assertFalse(any("names ranked of" in x for x in cy.summary))
            self.assertFalse(any("→" in x for x in cy.summary))
        self.assertEqual(len([r for r in C.read_jsonl(L.REFUSED) if r.get("stage") == "pre-trade"]), 0)

    def test_a_refused_open_is_retried_later_the_same_day(self):
        panel = make_panel()
        w0, _ = XS.latest(panel, P, sorted(panel))
        victim = min(w0, key=lambda c: w0[c])                                 # a decided short

        def refuse_victim(cy, coin, add, row, stop_pct, side="long"):
            if coin == victim:
                return False, [{"check": "not halted", "ok": False, "detail": "manual halt"}]
            return CY.Cycle.target_checks(cy, coin, add, row, stop_pct, side)
        cy1 = self.run_book(panel, patch={"target_checks": refuse_victim})
        self.assertNotIn(victim, L.positions("paper"))
        self.assertTrue(any(f"{victim}: signal book tier S REFUSED" in x for x in cy1.summary))
        self.assertIn("refused", self.decision()["pending"][victim])
        before, n = self.held(), len(L.trades())
        cy2 = self.run_book(panel, funding={victim: 0.20})                    # 01:05: the halt is gone, the funding moved
        pos = L.positions("paper")
        self.assertEqual(pos[victim]["side"], "short")                        # the decided short is opened now
        self.assertAlmostEqual(pos[victim]["sz"] * panel[victim][-1]["c"], -w0[victim] * cy2.equity, delta=0.01 * cy2.equity)
        self.assertEqual({c: v for c, v in self.held().items() if c != victim}, before)    # every other name as it was
        self.assertEqual(len(L.trades()), n)
        self.assertEqual(self.decision()["pending"], {})
        self.assertEqual(sum(1 for x in cy2.summary if "→ open" in x), 1)
        cy3 = self.run_book(panel)                                            # 02:05: nothing left to do
        self.assertFalse(any("→" in x for x in cy3.summary))
        self.assertEqual(self.held(), {**before, victim: self.held()[victim]})

    def test_a_run_that_stopped_part_way_is_finished_not_redecided(self):
        panel = make_panel()
        calls = []

        def open_then_fail(cy, *a, **k):
            calls.append(a[0])
            if len(calls) == 3:
                raise RuntimeError("simulated crash in the third open")
            return CY.Cycle._book_open(cy, *a, **k)
        with self.assertRaises(RuntimeError):
            self.run_book(panel, patch={"_book_open": open_then_fail})
        dec = self.decision()
        self.assertTrue(dec["weights"])                                       # the decision was saved before any trade
        self.assertEqual(len(L.positions("paper")), 2)
        dear = {c: (0.56 if p["side"] == "long" else -0.56) for c, p in L.positions("paper").items()}   # too dear on their side now
        cy2 = self.run_book(panel, funding=dear)
        held = L.positions("paper")
        self.assertEqual(sorted(c for c, p in held.items() if p["side"] == "long"), dec["long"])
        self.assertEqual(sorted(c for c, p in held.items() if p["side"] == "short"), dec["short"])
        self.assertEqual(self.decision()["pending"], {})
        self.assertFalse(any("names ranked of" in x for x in cy2.summary))

    def test_a_stale_run_decides_nothing_and_the_first_fresh_run_decides(self):
        panel = make_panel()
        cy = self.run_book(panel, fresh=False)
        self.assertEqual(L.positions("paper"), {})
        self.assertEqual(self.decision(), {})
        self.assertTrue(any("the first fresh run decides" in x for x in cy.summary))
        self.run_book(panel)
        self.assertTrue(self.decision()["weights"])
        self.assertTrue(L.positions("paper"))

    def test_the_next_rebalance_day_decides_afresh(self):
        self.run_book(make_panel())
        first = self.decision()
        cy = self.run_book(make_panel(last_day=REB + 1))                      # between rebalances: the decision is untouched
        self.assertTrue(any("between rebalances" in x for x in cy.summary))
        self.assertEqual(self.decision(), first)
        nxt = make_panel(last_day=REB + 7)                                    # the next rebalance day (same prices: no brake)
        top = first["long"][0]
        cy = self.run_book(nxt, funding={top: 0.56})                          # its own reading: the top long is too dear now
        dec = self.decision()
        self.assertEqual(dec["day"], C.iso((REB + 7) * DAY)[:10])
        self.assertTrue(any("names ranked of" in x for x in cy.summary))
        w, _ = XS.latest(nxt, P, sorted(nxt), {top}, set())
        self.assertEqual(dec["weights"], w)                                   # the new day's own book, from its own reading
        self.assertNotIn(top, dec["long"])
        self.assertIn(top, dec["refused_long"])
        self.assertNotIn(top, L.positions("paper"))
        self.assertTrue(any(x.startswith(f"{top}: target") and "→ close" in x for x in cy.summary))

    def test_pinned_the_deciding_run_trades_exactly_as_before(self):
        """The first run of a rebalance day forms and trades the book exactly as the engine did before (the lab's
        replay runs one run a day, so its parity rests on this)."""
        panel = make_panel()
        cy = self.run_book(panel, funding={"C19": 0.45, "C00": -0.45})
        w, info = XS.latest(panel, P, sorted(panel), {"C19"}, {"C00"})
        held = L.positions("paper")
        self.assertEqual(sorted(c for c, p in held.items() if p["side"] == "long"), info["long"])
        self.assertEqual(sorted(c for c, p in held.items() if p["side"] == "short"), info["short"])
        for c, p in held.items():
            self.assertAlmostEqual(p["notional"], abs(w[c]) * 1000.0, delta=0.002 * abs(w[c]) * 1000.0)
        self.assertEqual(sum(1 for x in cy.summary if "→ open" in x), len(w))


class LegFormationIsVisible(BookDay):
    def test_refusals_are_said_counted_recorded_and_decoded(self):
        panel = make_panel()
        cy = self.run_book(panel, funding={"C19": 0.45, "C00": -0.45})
        dec = self.decision()
        self.assertIn("funding", dec["refused_long"]["C19"])
        line = next(x for x in cy.summary if "refused at leg formation" in x)
        self.assertIn("long C19 (funding 45%/yr against longs above 30%)", line)
        self.assertIn("short C00 (funding -45%/yr against shorts beyond -30%)", line)
        self.assertNotIn("REFUSED", line)                                     # not an order refusal: no order was sent
        recs = [r for r in C.read_jsonl(L.REFUSED) if r.get("stage") == "leg formation"]
        self.assertEqual(sorted((r["coin"], r["tier"]) for r in recs), [("C00", "S"), ("C19", "L")])
        self.assertEqual(cy.counts["refused"], 2)
        self.assertTrue(all(r["t"] == C.iso(cy.now) for r in recs))          # joins the run doc on the dashboard
        rec = next(r for r in recs if r["coin"] == "C19")
        self.assertEqual(DP.refusal_codes(rec), [["fund", 45]])

    def test_names_without_a_second_source_are_listed_with_why(self):
        panel = make_panel()
        cy = self.run_book(panel)                                             # every last_price None here
        dec = self.decision()
        self.assertEqual(sorted(dec["unchecked"]), sorted(panel))
        self.assertTrue(all(v == B.NO_SOURCE for v in dec["unchecked"].values()))
        line = next(x for x in cy.summary if "no second source for the price band" in x)
        self.assertIn(f"{len(panel)} of {len(panel)} eligible names", line)
        self.assertIn("C07", line)


def fake_binance(table, calls=None):
    """http_json for the Binance mirror: table {pair: response dict or Exception}."""
    def http_json(url, **kw):
        pair = url.split("symbol=")[1]
        if calls is not None:
            calls.append(url)
        r = table[pair]
        if isinstance(r, Exception):
            raise r
        return r
    return http_json


class SecondSource(unittest.TestCase):
    def setUp(self):
        B.forget()

    def tearDown(self):
        B.forget()

    def test_trading_break_stale_missing_unreachable(self):
        now = time.time()
        ms = lambda t: int(t * 1000)                                          # noqa: E731
        table = {"SUIUSDT": {"symbol": "SUIUSDT", "lastPrice": "0.89370000", "closeTime": ms(now - 5)},
                 # LITUSDT and XMRUSDT as Binance served them on 2026-10-30: status BREAK, the ticker frozen ~24 days back
                 "LITUSDT": {"symbol": "LITUSDT", "lastPrice": "0.74300000", "closeTime": ms(now - 577.9 * 3600)},
                 "XMRUSDT": {"symbol": "XMRUSDT", "lastPrice": "118.70000000", "closeTime": ms(now - 577.8 * 3600)},
                 "THINUSDT": {"symbol": "THINUSDT", "lastPrice": "1.5", "closeTime": ms(now - 2 * 3600)},     # trading, but stale
                 "ZEROUSDT": {"symbol": "ZEROUSDT", "lastPrice": "0.00000000", "closeTime": ms(now - 5)},
                 "kPEPEUSDT": RuntimeError("https://data-api.binance.vision/api/v3/ticker/24hr: HTTP Error 400: Bad Request"),
                 "BTCUSDT": RuntimeError("https://data-api.binance.vision/api/v3/ticker/24hr: <urlopen error timed out>")}
        calls = []
        with mock.patch.object(B.C, "http_json", fake_binance(table, calls)):
            self.assertEqual(B.last_price("SUI"), 0.8937)
            self.assertIsNone(B.last_price("LIT"))
            self.assertIsNone(B.last_price("XMR"))
            self.assertIsNone(B.last_price("THIN"))
            self.assertIsNone(B.last_price("ZERO"))
            self.assertIsNone(B.last_price("kPEPE"))
            self.assertIsNone(B.last_price("BTC"))
            self.assertEqual(B.why_none("LIT"), "Binance LITUSDT not trading: last trade 578 h ago")
            self.assertEqual(B.why_none("THIN"), "Binance THINUSDT not trading: last trade 2 h ago")
            self.assertEqual(B.why_none("ZERO"), "Binance ZEROUSDT has no last price")
            self.assertEqual(B.why_none("kPEPE"), "no Binance kPEPEUSDT pair")
            self.assertTrue(B.why_none("BTC").startswith("Binance unreachable"))
            self.assertEqual(B.why_none("NEVER"), B.NO_SOURCE)
            self.assertTrue(all("/api/v3/ticker/24hr?symbol=" in u for u in calls))
            n = len(calls)
            self.assertEqual(B.last_price("SUI"), 0.8937)                     # one read per coin per run
            self.assertIsNone(B.last_price("LIT"))
            self.assertEqual(len(calls), n)
        self.assertEqual(CY.no_second("LIT"), "no second source (Binance LITUSDT not trading: last trade 578 h ago)")
        self.assertEqual(CY.no_second("NEVER"), "no second source")


class FrozenPrice(BookDay):
    def test_a_frozen_price_no_longer_refuses_a_name_on_both_sides(self):
        """E1 end to end: the book's best long has a BREAK pair on Binance, frozen at a fifth of the mark. Before, it was
        refused on both sides at every rebalance; now it is ranked like any name, listed as unchecked, and opened."""
        CY.B.last_price = self._lp                                            # the real reader (setUp saved it), on a fake mirror
        panel = make_panel()
        w0, _ = XS.latest(panel, P, sorted(panel))
        best = max(w0, key=lambda c: w0[c])
        now = time.time()
        table = {f"{c}USDT": {"lastPrice": str(b[-1]["c"]), "closeTime": int(now * 1000)} for c, b in panel.items()}
        table[f"{best}USDT"] = {"lastPrice": str(panel[best][-1]["c"] / 5), "closeTime": int((now - 578 * 3600) * 1000)}
        with mock.patch.object(B.C, "http_json", fake_binance(table)):
            cy = self.run_book(panel)
        dec = self.decision()
        self.assertIn(best, dec["long"])
        self.assertNotIn(best, dec["refused_long"])
        self.assertEqual(dec["unchecked"], {best: f"Binance {best}USDT not trading: last trade 578 h ago"})
        self.assertEqual(L.positions("paper")[best]["side"], "long")
        self.assertTrue(any("no second source for the price band" in x and best in x for x in cy.summary))
        self.assertFalse(any("REFUSED" in x for x in cy.summary))

    def test_a_live_price_outside_the_band_still_refuses(self):
        """The band itself is unchanged: a pair that trades, priced 5x off the mark, still refuses the name at leg formation."""
        CY.B.last_price = self._lp
        panel = make_panel()
        w0, _ = XS.latest(panel, P, sorted(panel))
        best = max(w0, key=lambda c: w0[c])
        now = time.time()
        table = {f"{c}USDT": {"lastPrice": str(b[-1]["c"] * (5 if c == best else 1)), "closeTime": int(now * 1000)} for c, b in panel.items()}
        with mock.patch.object(B.C, "http_json", fake_binance(table)):
            self.run_book(panel)
        dec = self.decision()
        self.assertNotIn(best, dec["long"])
        self.assertIn("mark vs Binance 80.00%", dec["refused_long"][best])
        self.assertEqual(dec["unchecked"], {})


class Docs(unittest.TestCase):
    def test_no_idempotence_claim_left(self):
        ra, ex = (ROOT / "scripts" / "run_agents.py").read_text(), (ROOT / "docs" / "EXECUTION.md").read_text()
        for text in (ra, ex):
            self.assertNotIn("is idempotent", text)
            self.assertNotIn("changes nothing", text)
        self.assertIn("decides once per rebalance day", ra)
        self.assertIn("decided once", (ROOT / "docs" / "specs" / "SHADOW.md").read_text())


if __name__ == "__main__":
    unittest.main()
