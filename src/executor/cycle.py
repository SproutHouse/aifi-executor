"""cycle.py — one pass of the loop, run five minutes after every 4-hour close.

Order of work, and why: absorb positions the exchange already closed (a resident stop fired), so nothing
below acts on a position that no longer exists; expire stale proposals; manage exits on open positions
(exits never wait for anyone, and each position is handled on its own so one failure cannot stop the
others); reconcile the ledger with the exchange in live mode; then, and only then, look for entries.

State is written through after every open, close and trail, so a crash between two steps can never make
the ledger and the positions file disagree. A reading of "no data" on any timeframe keeps a position and
its stop exactly as they are; only an explicit bearish reading closes. In live mode a close happens before
its stop is cancelled, and a fresh fill is recorded and protected before anything else can fail. Every
refusal is written down with its reasons. The model is nowhere in this file.
"""
import time
from . import common as C, hl_data as H, binance_data as B, regime as R, signals as S, universe as U
from . import risk as K, hours as HR, proposals as P, ledger as L, paper as PA, live as LV, target as TG, carry as CA
from . import families as F, market_regime as MR, longshort as XS

HALT = C.STATE / "HALT"
BOOK = C.STATE / "book.json"          # the long-short book's own state (peak, brake), shadow agents only


def agent_coins(s):
    t, c = s.get("target") or {}, s.get("carry") or {}
    return list(t.get("coins") or t.get("weights") or []) + list(c.get("basket") or [])


def paper_only(s):
    """Why this agent can never trade live, or "" when it can: a shadow experiment (a recipe the lab FAILED, paper-traded
    on the owner's decision as an unofficial experiment) or any agent whose target block holds shorts (the engine has
    no live short order path). go_live.py and approve.py refuse the same agents."""
    if s.get("shadow"):
        return "a shadow experiment (its lab verdict is failed): paper only, never live"
    if (s.get("target") or {}).get("shorts") or (s.get("target") or {}).get("family") == "ls_xs":
        return "a long-short book: the engine has no live short order path, paper only"
    return ""


def resolve_mode(s):
    mode = s.get("mode", "paper")
    why = paper_only(s)
    if why:
        return "paper", (f"live requested but this agent is {why}: running paper" if mode == "live" else "")
    if mode == "live" and any(H.is_builder(c) for c in agent_coins(s)) and not s.get("builder_live_validated"):
        return "paper", "live requested but builder-market (HIP-3) order handling is not validated yet (docs/specs/MARKETS.md): running paper"
    if mode == "live" and s.get("strategy") == "carry" and not s.get("carry_live_validated"):
        return "paper", "live requested but carry live order handling is not validated on testnet yet (Phase 4): running paper"
    if mode == "live":
        key, addr = LV.creds()
        if not key or not addr:
            return "paper", "live requested but HL_AGENT_KEY / HL_ACCOUNT_ADDRESS missing: running paper"
        if not LV.available():
            return "paper", "live requested but the exchange SDK is not installed: running paper"
    return mode, ""


def freshness(h4, now_ts, s):
    if not h4:
        return False, "no trigger bars"
    T = h4[-1].get("T") or (h4[-1]["t"] + C.bar_seconds(s))
    late = (now_ts - T) / 60
    if late < 0:
        return False, "last bar has not closed"
    if late > s["data"]["late_run_minutes"]:
        return False, f"run started {late:.0f} min after the bar close, limit {s['data']['late_run_minutes']}"
    return True, f"{late:.0f} min after the bar close"


def no_second(coin):
    """The sanity band's detail when Binance gives no second source for coin (the band fails open): why, when known."""
    why = B.why_none(coin)
    return why if why == B.NO_SOURCE else f"{B.NO_SOURCE} ({why})"


def bearish(d):
    return d == 1


def no_reading(d):
    return d is None


class Bars:
    """Candles per coin: daily, the trigger timeframe, and 4-hour gate bars when the trigger is 1-hour."""
    def __init__(self, s):
        self.s, self.cache, self.gates = s, {}, {}
        self.tf = C.trigger_tf(s)

    def get(self, coin):
        if coin not in self.cache:
            d = H.candles(coin, "1d", self.s["data"]["candle_days_daily"])
            if H.is_builder(coin):
                d = H.weekdays(d)
            days = self.s["data"].get("candle_days_trigger", self.s["data"]["candle_days_4h"]) if self.tf != "4h" else self.s["data"]["candle_days_4h"]
            h = d if self.tf == "1d" else H.candles(coin, self.tf, days)
            self.cache[coin] = (d, h)
        return self.cache[coin]

    def gate(self, coin):
        if self.tf == "4h":
            return None
        if coin not in self.gates:
            self.gates[coin] = H.candles(coin, "4h", self.s["data"]["candle_days_4h"])
        return self.gates[coin]

    def context(self, coin, now, ind):
        d, h = self.get(coin)
        return R.context(d, h, now, ind, self.gate(coin))


def describe(cand, sizing):
    return (f"{cand['coin']} {cand.get('side', 'long')} [{cand.get('book', '?')}] · {cand['kind']} tier {cand['tier']} · stop {cand['stop']:.5g} "
            f"({sizing.get('dist_pct', 0):.1f}% away) · size {sizing.get('notional_pct_equity', 0):.1f}% of pot at "
            f"{sizing.get('leverage', '?')}x · risk {sizing.get('risk_pct', 0):.2f}% of pot")


class Cycle:
    def __init__(self, dry=False, verbose=False):
        self.dry, self.verbose = dry, verbose
        self.counts = {"evaluated": 0, "triggers": 0, "refused": 0, "proposed": 0, "entered": 0}
        self.readings = []
        self.s = C.settings()
        self.now = C.now_ts()
        self.summary = []
        self.mode, self.mode_note = resolve_mode(self.s)
        self.hours_mode, self.local = HR.mode(self.s)
        self.halt = HALT.exists()
        self.halt_reason = HALT.read_text().strip() if self.halt else ""
        if not self.halt and C.FLEET_HALT.exists():
            self.halt, self.halt_reason = True, "fleet halt: " + (C.FLEET_HALT.read_text().strip() or "manual")
        self.fleet_mult = C.fleet_mult()
        self.bars = Bars(self.s)
        self.ex = self.info = self.addr = None
        self.pot = None
        self.positions, self.marks, self.ctxs, self.exch_pos, self.rec_flags = {}, {}, {}, {}, {}
        self.btc = {"weekly_dir": None, "daily_dir": None}
        self.fresh, self.fresh_detail, self.btc_bull = False, "not loaded", False
        self.equity = self.unreal = self.cash = None
        self.thr = K.throttle([], self.s["throttle"])
        self.failed = False
        self.run_doc = None

    def say(self, line):
        self.summary.append(line)
        C.log("  " + line)

    def trade_alert(self, title, text):
        """A trade done as planned is nothing to act on (the owner's rule: the phone sounds only when there is something
        to do). Paper trades are logged, never pushed; live ones arrive silently (low priority) so real money is visible."""
        if self.mode == "live":
            C.notify(title, text, "low")
        else:
            C.log(f"  (paper, not pushed) {title}: {text}")

    def step_alert(self, title, coin, e):
        """One coin's step failed. Live: high, every time (real money; its resident stop still holds). Paper: a bug to fix
        but nothing at risk, so silent and once a day per coin and kind of fault, not every cycle."""
        text = f"{coin}: {type(e).__name__}: {str(e)[:200]}"
        if self.mode == "live":
            C.notify(title, text, "high")
        else:
            C.alert_once(f"step:{title}:{coin}:{type(e).__name__}", text, "low", title, every_hours=24)

    def persist(self):
        """Write-through: the positions file and the paper pot after every change."""
        if self.dry:
            return
        if self.mode == "paper" and self.pot is not None:
            PA.save_pot(self.pot)
        L.save_positions(self.positions, self.mode)

    # ------------------------------------------------------------ market --
    def load_market(self):
        self.ctxs = H.meta_and_ctxs({c.split(":")[0] for c in agent_coins(self.s) if H.is_builder(c)})
        self.marks = {k: float(v["markPx"]) for k, v in self.ctxs.items() if v.get("markPx")}
        btc_d, btc_h = self.bars.get("BTC")
        self.btc = R.context(btc_d, btc_h, self.now, self.s["indicators"])
        self.fresh, self.fresh_detail = freshness(btc_h, self.now, self.s)
        self.btc_bull = self.btc["weekly_dir"] == -1
        self.say(f"BTC weekly {R.label(self.btc['weekly_dir'])} · daily {R.label(self.btc['daily_dir'])} · data {self.fresh_detail}")

    # ---------------------------------------------------------- accounts --
    def load_account(self):
        self.positions = L.positions(self.mode)
        if self.mode == "paper":
            self.pot = PA.pot(self.s) if not self.dry else (C.load_json(PA.POT) or {"cash": float(self.s["pot_usd_paper"]), "start": float(self.s["pot_usd_paper"])})
            self.equity, self.unreal = PA.equity(self.pot, self.positions, self.marks)
            self.cash = self.pot["cash"]
            left = L.positions("live")
            if left:
                # a live book this paper cycle never manages: set back to paper without a flatten, or live requested but a
                # key is missing. Its positions sit on the exchange with nothing but their resident stops.
                C.alert_once("live-left:" + ",".join(sorted(left)), f"{', '.join(sorted(left))} still open in the LIVE ledger while this agent "
                             "runs paper: only their resident stops protect them. Restore live mode (or its keys) and flatten, or close them "
                             "on the exchange.", "urgent", "Executor: live positions unmanaged", every_hours=4)
        else:
            self.ex, self.info, self.addr = LV.clients()
            self.equity, self.exch_pos, _ = LV.account(self.addr)
            self.cash, self.unreal = self.equity, 0.0
        pts = L.equity_points(self.mode) + [{"equity": self.equity}]
        self.thr = K.throttle(pts, self.s["throttle"])

    # ------------------------------------------------------------- exits --
    def _record_close(self, coin, pos, px, reason, ts, fee):
        """Remove the position and persist FIRST, then append the trade: a crash in between loses one ledger
        line (recoverable from the run log) instead of closing the same position twice."""
        bench_exit = self.marks.get(pos.get("benchmark") or "")
        rec = L.build_close(pos, px, reason, ts, fee, pos.get("funding_paid", 0.0), bench_exit)
        self.positions.pop(coin, None)
        if self.mode == "paper":
            self.pot["cash"] += rec["gross"] - fee - pos.get("funding_paid", 0.0)
        self.persist()
        if not self.dry:
            L.append_trade(rec)
        rel = f" · {rec['rel_R']:+.2f} R vs {pos.get('benchmark')}" if rec.get("rel_R") is not None else ""
        self.say(f"{coin} [{pos.get('book')}]: closed on {reason} at {px:.5g} → {rec['R']:+.2f} R{rel}")
        self.trade_alert("Executor: closed", f"{coin} ({pos.get('book')}) on {reason}: {rec['R']:+.2f} R{rel} after {rec['hours']:.0f}h")
        self.maybe_sweep(pos, rec, ts)
        return rec

    def close_position(self, coin, pos, px, reason, ts):
        if pos.get("kind") == "carry":                 # two legs, no single size: its own path (flatten reaches here)
            return self.close_carry(coin, pos, reason)
        if self.mode == "live":
            # close FIRST; the resident stop stays on the exchange until the close is confirmed
            try:
                resp = LV.close_market(self.ex, coin, None, LV.new_cloid())
                avg, second = LV.fill_from_response(resp)
            except Exception as e:  # noqa: BLE001
                avg, second = None, str(e)[:160]
            if avg is not None:
                rest = self.left_after_close(coin, pos, float(second))
                if rest > 0:                           # a reduce-only IOC can fill only part: never record that as a full close
                    second, avg = self.keep_remainder(coin, pos, avg, float(second), rest), None
            if avg is None:
                self.say(f"{coin}: close NOT filled ({second}); position and its resident stop kept, retry next cycle")
                C.notify("Executor: close failed", f"{coin} {reason}: {second}", "urgent")
                return None
            px = avg
            fee = pos["sz"] * px * self.s["fee_taker_pct"] / 100
            if pos.get("stop_cloid"):
                try:
                    LV.cancel(self.ex, coin, LV.cloid_from(pos["stop_cloid"]))
                except Exception as e:  # noqa: BLE001
                    self.say(f"{coin}: leftover stop cancel failed ({str(e)[:80]}); harmless once flat, reconcile will report it")
        else:
            fee = PA.exit_fee(pos, px, self.s)
        return self._record_close(coin, pos, px, reason, ts, fee)

    def exchange_long(self, coin):
        """What the exchange holds in this coin: ("long", entryPx, size) | ("flat", None, 0.0) | ("unknown", None, why)."""
        try:
            _value, exch, _ = LV.account(self.addr)
        except Exception as e:  # noqa: BLE001
            return "unknown", None, f"recovery read failed ({str(e)[:80]})"
        e = exch.get(coin)
        if e and e.get("szi", 0) > 0:
            return "long", e["entryPx"], abs(e["szi"])
        return "flat", None, 0.0

    def left_after_close(self, coin, pos, filled):
        """Size still open after a close that filled `filled`. The ledger says size − filled; when the account can be read,
        the smaller of that and what the exchange holds (it may have closed part already). Under one size step is none."""
        szd = int((self.ctxs.get(coin) or {}).get("szDecimals", 3))
        rest = max(0.0, pos["sz"] - filled)
        state, _px, held = self.exchange_long(coin)
        if state != "unknown":
            rest = min(rest, held)
        return rest if H.round_sz(rest, szd) > 0 else 0.0

    def keep_remainder(self, coin, pos, avg, filled, rest):
        """A close that filled only part (market_close is a reduce-only IOC at mid ∓ 5%): the filled part is realised into the
        position (counted when it finally closes, like a target trim), the rest stays open with a resident stop sized to
        it, and the close is retried next cycle. Returns the detail for the summary and the urgent alert."""
        pos["realized"] = pos.get("realized", 0.0) + (avg - pos["entry"]) * filled - avg * filled * self.s["fee_taker_pct"] / 100
        pos["sz"], pos["notional"] = rest, rest * pos["entry"]
        self.persist()                                    # the smaller size exists on the exchange: record it first
        try:
            self.replace_stop(coin, pos, pos["stop"])     # the new stop first, the old one cancelled only once it rests
            kept = "a resident stop re-sized to it"
        except Exception as e:  # noqa: BLE001
            kept = f"its old resident stop (re-sizing failed: {type(e).__name__}; reduce-only, so it still covers it)"
        return f"only {filled:.6g} of {filled + rest:.6g} filled; the remaining {rest:.6g} stays open with {kept}"

    def maybe_sweep(self, pos, rec, ts):
        """Book policy: a realised gain is earmarked for the book's benchmark while that benchmark's weekly is bullish."""
        _name, book = C.book_of(pos["coin"])
        if not book or not book["sweep"] or rec["pnl"] <= 0 or self.dry:
            return
        bench = book["benchmark"]
        try:
            ctx = self.bars.context(bench, self.now, self.s["indicators"])
        except Exception:  # noqa: BLE001
            return
        if ctx["weekly_dir"] == -1 and self.equity and self.equity > 0:
            L.record_sweep_intent(pos.get("book"), bench, rec["pnl"] / self.equity * 100, ts)
            self.say(f"{pos['coin']}: gain earmarked for {bench} ({rec['pnl'] / self.equity * 100:.2f}% of pot); execution is a later version")

    def absorb_exchange_closes(self):
        """Live only, before anything else: a ledger position the exchange no longer holds means the resident
        stop fired. Record it from the account's fills so no later step acts on a ghost position."""
        if self.mode != "live":
            return
        for coin, pos in list(self.positions.items()):
            if coin in self.exch_pos:
                continue
            px = self.exit_price_from_fills(coin, pos)
            if px is None:
                self.say(f"{coin}: not on the exchange and no sell fill found; left for reconcile to report")
                continue
            fee = pos["sz"] * px * self.s["fee_taker_pct"] / 100
            self._record_close(coin, pos, px, "stop (exchange)", self.now, fee)

    def manage_exits(self):
        for coin, pos in list(self.positions.items()):
            try:
                self.manage_exit(coin, pos)
            except Exception as e:  # noqa: BLE001 — one position's failure must not stop the others
                self.say(f"{coin}: exit management failed ({type(e).__name__}: {str(e)[:100]}); position kept"
                         + (", resident stop still on the exchange" if self.mode == "live" else ""))
                self.step_alert("Executor: exit check failed", coin, e)
        self.persist()   # funding accrual and paper stop-check cursors

    def manage_exit(self, coin, pos):
        d, h = self.bars.get(coin)
        ctx = self.bars.context(coin, self.now, self.s["indicators"])
        row = self.ctxs.get(coin, {})
        if self.mode == "paper":
            try:
                PA.accrue_funding(pos, float(row.get("funding", 0) or 0), self.now)
            except (TypeError, ValueError):
                pass
            px, bt = PA.check_stop(pos, h, self.s)
            if px is not None:
                if not self.dry:
                    self.close_position(coin, pos, px, "stop", bt or self.now)
                return
        h4 = ctx.get("h4") or {}
        if no_reading(ctx.get("weekly_dir")) or no_reading(ctx.get("daily_dir")) or no_reading(h4.get("dir")) or ("gate4h" in ctx and no_reading(ctx["gate4h"])):
            self.say(f"{coin}: no reading on one timeframe (data gap); position and stop kept as they are")
            return
        g4 = ctx.get("gate4h")
        if bearish(ctx["weekly_dir"]) or bearish(ctx["daily_dir"]) or bearish(g4) or bearish(h4["dir"]):
            reason = ("weekly flip" if bearish(ctx["weekly_dir"]) else "daily flip" if bearish(ctx["daily_dir"])
                      else "4h flip" if (bearish(g4) or self.bars.tf == "4h") else f"{self.bars.tf} flip")
            mark = self.marks.get(coin)
            if not mark:
                self.say(f"{coin}: {reason} but no mark price; position kept until the next cycle")
            elif not self.dry:
                self.close_position(coin, pos, mark * (1 - self.s["paper_slippage_pct"] / 100) if self.mode == "paper" else mark, reason, self.now)
            return
        if h4.get("line") and h4["line"] > pos["stop"]:
            new_stop = h4["line"]
            if self.mode == "live" and not self.dry:
                self.replace_stop(coin, pos, new_stop)       # raises on rejection: the old stop then stays
            else:
                pos["stop"] = new_stop
                self.persist()
            self.say(f"{coin}: stop trailed to {new_stop:.5g}")

    def replace_stop(self, coin, pos, new_stop, sz=None, cloid=None):
        """Place the new resident stop, confirm the exchange accepted it, persist, then cancel the old one.
        sz: the size the stop covers (default the position's); cloid: the client id to use (default a new one)."""
        row = self.ctxs.get(coin, {})
        szd = int(row.get("szDecimals", 3))
        cl = cloid or LV.new_cloid()
        stop_px = H.round_px(new_stop, szd)
        worst = H.round_px(new_stop * 0.97, szd)
        resp = LV.place_stop(self.ex, coin, H.round_sz(pos["sz"] if sz is None else sz, szd), stop_px, worst, cl)
        ok, detail = LV.order_ok(resp)
        if not ok:
            raise RuntimeError(f"stop order rejected: {detail}")
        self._adopt_stop(coin, pos, stop_px, cl)

    def _adopt_stop(self, coin, pos, stop_px, cl):
        old = pos.get("stop_cloid")
        pos["stop"], pos["stop_cloid"] = stop_px, LV.raw(cl)
        self.persist()
        if old and old != LV.raw(cl):
            try:
                LV.cancel(self.ex, coin, LV.cloid_from(old))
            except Exception as e:  # noqa: BLE001
                self.say(f"{coin}: old stop cancel failed ({str(e)[:80]}); two stops rest, the second is rejected as reduce-only when it triggers")

    def stop_landed(self, coin, pos, stop, cl):
        """After a stop request that raised (a timeout, a dropped connection): the order may rest on the exchange although
        its answer was lost. Look it up by its client id; if it rests, adopt it instead of placing a second one."""
        if self.info is None:                       # no live client (paper, tests): there is no book to look in
            return False
        held = LV.resting_cloids(self.addr)
        if not held or LV.raw(cl).lower() not in held:
            return False
        self._adopt_stop(coin, pos, H.round_px(stop, int((self.ctxs.get(coin) or {}).get("szDecimals", 3))), cl)
        return True

    # ----------------------------------------------------- reconciliation --
    def reconcile(self):
        self.rec_flags = {}
        if self.mode != "live":
            return
        r = LV.reconcile(self.positions, self.addr)
        if not r["ok"]:
            self.rec_flags = {"reconcile_mismatch": True, "reconcile_detail": "; ".join(r["problems"])}
            self.say("RECONCILIATION MISMATCH: " + "; ".join(r["problems"]))
            C.notify("Executor: reconciliation mismatch, entries halted", "; ".join(r["problems"])[:900], "urgent")

    def exit_price_from_fills(self, coin, pos):
        try:
            fills = [f for f in H.user_fills(self.addr) if f.get("coin") == coin and f.get("side") == "A"
                     and int(f.get("time", 0)) // 1000 >= pos["opened_ts"]]
            if not fills:
                return None
            tot = sum(float(f["sz"]) for f in fills)
            return sum(float(f["px"]) * float(f["sz"]) for f in fills) / tot if tot else None
        except Exception:  # noqa: BLE001
            return None

    # ----------------------------------------------------------- entries --
    def recover_entry(self, coin, err):
        """After an exception during an entry: the request may have reached the exchange. Look before
        assuming nothing happened. Returns (avg_px, size) when a long exists, else (None, detail)."""
        state, px, sz = self.exchange_long(coin)
        if state == "long":
            return px, sz
        return None, err if state == "flat" else f"{err}; {sz}"

    def resize_recover(self, coin, pos, err, mark, adding, cover):
        """After an exception during a live resize the order may have reached the exchange. Read the account, as the
        entry path does: when the size moved the way the order meant, return (price, size moved) so the caller records
        it and re-places the stop at the TRUE size (price estimated at the mark; the exchange's fills hold the exact
        one). (None, detail) otherwise. Unreadable account: the stop is re-placed to cover `cover`, the largest size the
        order could have produced (reduce-only, so a stop larger than the position never opens anything), the ledger is
        left as it is, and reconcile checks the size next cycle."""
        szd = int((self.ctxs.get(coin) or {}).get("szDecimals", 3))
        step = 10 ** -szd
        state, _px, held = self.exchange_long(coin)
        if state == "unknown":
            note = "account unreadable; ledger unchanged, reconcile checks the size next cycle"
            if adding and cover > pos["sz"] + step / 2:
                try:
                    self.replace_stop(coin, pos, pos["stop"], sz=cover)
                    note += f"; the stop now covers {cover:.6g}"
                except Exception as e:  # noqa: BLE001
                    note += f"; the stop could not be re-sized ({type(e).__name__})"
            C.notify("Executor: resize outcome unknown", f"{coin}: {err}; {note}", "urgent")
            return None, f"{err}; {note}"
        moved = held - pos["sz"]
        if abs(moved) < step / 2:
            return None, f"{err}; the exchange shows no change"
        if state == "flat" or (moved > 0) != adding:
            C.notify("Executor: resize outcome unclear", f"{coin}: {err}; the exchange holds {held:.6g}, the ledger {pos['sz']:.6g}; left for reconcile", "urgent")
            return None, f"{err}; the exchange holds {held:.6g}, left for reconcile"
        C.notify("Executor: resize recovered", f"{coin}: {err}; the exchange shows {abs(moved):.6g} {'added' if adding else 'cut'}; recorded, stop re-placed at the true size", "urgent")
        return mark, abs(moved)

    def protect(self, coin, pos, stop):
        """Place the resident stop for a fresh fill; one retry, then close rather than hold unprotected. A request that
        raised may still have reached the exchange: before retrying, look the first stop up by its client id and adopt it,
        so a retry never leaves two stops (each attempt has its own id; reusing one would make the exchange reject the
        retry of a stop that did land, and the position would then be closed for nothing)."""
        last = ""
        for _attempt in range(2):
            cl = LV.new_cloid()
            try:
                self.replace_stop(coin, pos, stop, cloid=cl)
                return True
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {str(e)[:100]}"
                if not str(e).startswith("stop order rejected") and self.stop_landed(coin, pos, stop, cl):
                    return True
                time.sleep(2)
        self.say(f"{coin}: could not place the resident stop ({last}); closing the position rather than holding it unprotected")
        C.notify("Executor: stop placement failed, closing", f"{coin}: {last}", "urgent")
        rec = self.close_position(coin, pos, self.marks.get(coin) or pos["entry"], "no stop possible", self.now)
        if rec is None and not self.dry:
            HALT.write_text(f"{coin} open without a resident stop and the close failed {C.iso()}")
            self.halt, self.halt_reason = True, "unprotected position"
            C.notify("Executor: HALT", f"{coin} is open without a stop and could not be closed; intervene now", "urgent")
        return False

    def execute_entry(self, cand, sizing, mark, ctx):
        coin = cand["coin"]
        context = {"btc_weekly": R.label(self.btc["weekly_dir"]), "pair_weekly": R.label(ctx["weekly_dir"]),
                   "pair_daily": R.label(ctx["daily_dir"]), "h4_range": cand.get("range"),
                   "funding_annual_pct": H.funding_annual_pct(self.ctxs.get(coin, {})), "hours_mode": self.hours_mode}
        rules = [f"LOGIC v{self.s.get('version', '?')}", f"agent:{C.AGENT}", f"trigger:{cand['kind']}", f"tier:{cand['tier']}", f"stop:{self.bars.tf}-line", "long-only", f"book:{cand.get('book')}"]
        if self.mode == "paper":
            pos = PA.open_position(cand, sizing, mark, self.s, self.now, "paper", context, rules)
            self.pot["cash"] -= pos["entry_fee"]
            self.positions[coin] = pos
            self.persist()
        else:
            row = self.ctxs[coin]
            szd = int(row.get("szDecimals", 3))
            sz = H.round_sz(sizing["notional"] / mark, szd)
            cap = H.round_px(mark * (1 + self.s["entry_slippage_cap_pct"] / 100), szd)
            ecl = LV.new_cloid()
            try:
                LV.set_isolated_leverage(self.ex, coin, sizing["leverage"])
                resp = LV.entry_ioc(self.ex, coin, sz, cap, ecl)
                avg, second = LV.fill_from_response(resp)
            except Exception as e:  # noqa: BLE001
                avg, second = self.recover_entry(coin, f"{type(e).__name__}: {str(e)[:100]}")
            if avg is None:
                self.say(f"{coin}: entry not filled ({second})")
                if not self.dry:
                    L.record_refusal(cand, f"IOC entry not filled: {second}", self.now, "execution")
                return None
            filled_sz = float(second) if isinstance(second, (int, float)) else sz
            pos = PA.open_position(cand, sizing, avg, self.s, self.now, "live", context, rules)
            pos.update({"entry": avg, "sz": filled_sz, "notional": avg * filled_sz, "entry_cloid": LV.raw(ecl),
                        "entry_fee": avg * filled_sz * self.s["fee_taker_pct"] / 100})
            self.positions[coin] = pos
            self.persist()                                     # the fill exists on the exchange: record it first
            if not self.protect(coin, pos, cand["stop"]):
                return None
        self.say(f"{coin}: ENTERED {describe(cand, sizing)}")
        self.trade_alert("Executor: entered", describe(cand, sizing))
        return pos

    def find_entries(self):
        for book_name, book in C.books().items():
            for coin in book["names"]:
                try:
                    self.find_entry(coin, book_name, book)
                except Exception as e:  # noqa: BLE001
                    self.say(f"{coin}: entry check failed ({type(e).__name__}: {str(e)[:100]}); skipped this cycle")

    def find_entry(self, coin, book_name, book):
        if coin in self.positions:
            return
        row = self.ctxs.get(coin)
        if row is None:
            if self.verbose:
                self.say(f"{coin} [{book_name}]: not listed on Hyperliquid perpetuals")
            return
        try:
            d, h = self.bars.get(coin)
        except Exception as e:  # noqa: BLE001
            self.say(f"{coin}: candles unavailable ({str(e)[:80]})")
            return
        ctx = self.bars.context(coin, self.now, self.s["indicators"])
        cand, why = S.evaluate(coin, ctx, self.btc_bull, self.s.get("btc_gate", True))
        self.counts["evaluated"] += 1
        if cand:
            cand.update({"book": book_name, "benchmark": book["benchmark"], "bench_mark": self.marks.get(book["benchmark"])})
        h4r = ctx.get("h4") or {}
        try:
            vol_m = float(row.get("dayNtlVlm", 0)) / 1e6
        except (TypeError, ValueError):
            vol_m = None
        self.readings.append({"coin": coin, "book": book_name, "weekly": R.label(ctx["weekly_dir"]), "daily": R.label(ctx["daily_dir"]),
                              "h4": R.label(h4r.get("dir")), "range": h4r.get("range"), "line": h4r.get("line"), "close": h4r.get("close"),
                              "trigger": (cand["kind"] + " tier " + cand["tier"]) if cand else None, "why": None if cand else why[0],
                              "vol_m": vol_m, "funding_pct": H.funding_annual_pct(row), "days": ctx["days"], "mark": self.marks.get(coin)})
        if self.verbose:
            fa = H.funding_annual_pct(row)
            self.say(f"{coin} [{book_name}]: W {R.label(ctx['weekly_dir'])} · D {R.label(ctx['daily_dir'])} · 4h {R.label(h4r.get('dir'))} "
                     f"{h4r.get('range') or ''} · {cand['kind'] + ' tier ' + cand['tier'] if cand else why[0]} · "
                     f"vol {vol_m if vol_m is None else round(vol_m)}M · funding {fa if fa is None else round(fa, 1)}%/yr · {ctx['days']}d history")
        if not cand:
            return
        self.counts["triggers"] += 1
        mark = self.marks.get(coin)
        if not mark:
            return
        u_ok, u_reasons = U.check(coin, row, self.s["universe"], ctx["days"])
        second = B.last_price(coin)
        if second:
            dev = abs(mark - second) / second * 100
            sanity_ok, sanity_detail = dev <= self.s["data"]["sanity_band_pct"], f"mark vs Binance {dev:.2f}%"
        else:
            sanity_ok, sanity_detail = True, no_second(coin)
        worst_entry = mark * (1 + self.s["entry_slippage_cap_pct"] / 100)
        sizing = K.size(self.equity or 0.0, worst_entry, cand["stop"], self.s, row.get("maxLeverage"), self.thr["multiplier"] * self.fleet_mult)
        flags = {"halt": self.halt, "halt_reason": self.halt_reason, "throttle_halt": self.thr["halt"],
                 "drawdown_pct": self.thr["drawdown_pct"], "fresh": self.fresh, "fresh_detail": self.fresh_detail,
                 "sanity_ok": sanity_ok, "sanity_detail": sanity_detail, "universe_ok": u_ok, "universe_reasons": u_reasons,
                 "book_cap_pct": book.get("open_risk_cap_pct")}
        flags.update(self.rec_flags)
        ok, checks = K.pre_trade(cand, sizing, self.positions, self.equity or 0.0, self.s, flags)
        if not ok:
            failed = [c for c in checks if not c["ok"]]
            self.counts["refused"] += 1
            if not self.dry:
                L.record_refusal(cand, failed, self.now, "pre-trade")
            self.say(f"{coin}: signal {cand['kind']} tier {cand['tier']} REFUSED: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed))
            return
        ap = self.s.get("approval", {"mode": "online_hours"})
        if ap.get("mode") == "never":
            if cand["tier"] not in ap.get("auto_tiers", ["A"]):
                self.counts["refused"] += 1
                if not self.dry:
                    L.record_refusal(cand, f"tier {cand['tier']} is not automated and approvals are disabled", self.now, "policy")
                self.say(f"{coin}: signal {cand['kind']} tier {cand['tier']} recorded, not traded (tier not automated)")
                return
            auto = True
        else:
            auto = self.hours_mode == "auto" and cand["tier"] in self.s["offline_auto_tiers"]
        if auto and not self.dry:
            if self.execute_entry(cand, sizing, mark, ctx):
                self.counts["entered"] += 1
        else:
            why_wait = ("dry run" if self.dry else "online hours: approval required" if self.hours_mode == "approval"
                        else f"tier {cand['tier']} always needs approval")
            exp = HR.next_bar_close(self.now, C.bar_seconds(self.s))
            if self.dry:
                self.say(f"{coin}: would PROPOSE {P.new_id(coin, cand['kind'], self.now)} ({why_wait}) · {describe(cand, sizing)}")
                return
            doc = P.create(cand, sizing, checks, exp, why_wait, mark, self.mode)
            self.counts["proposed"] += 1
            self.say(f"{coin}: PROPOSED {doc['id']} ({why_wait}), expires {doc['expires']}")
            C.notify("Executor: approval needed", f"{describe(cand, sizing)} · id {doc['id']} · expires {doc['expires'][11:16]} UTC", "high")

    # -------------------------------------------------------------- run ---
    def run(self):
        C.log(f"cycle {C.iso(self.now)} · mode {self.mode} · hours {self.hours_mode} ({self.local.strftime('%H:%M %Z')}) · dry {self.dry}")
        if self.mode_note:
            self.say(self.mode_note)
            # actionable (a key or the SDK is missing) but standing: once a day, not every cycle
            C.alert_once("fallback:" + self.mode_note, self.mode_note, "high", "Executor: running paper instead of live", every_hours=24)
        if self.halt:
            self.say(f"HALT set: {self.halt_reason} (exits still managed, no entries)")
        try:
            self.load_market()
            self.load_account()
            self.absorb_exchange_closes()
            expired = P.expire_stale(self.now) if not self.dry else []
            for d in expired:
                L.record_refusal(d["candidate"], "proposal expired unapproved", self.now, "proposal")
                self.say(f"{d['candidate']['coin']}: proposal {d['id']} expired unapproved")
            if self.s.get("strategy") == "carry":
                self.reconcile()
                self.manage_carry()
                return self._run_tail()
            if self.s.get("strategy") == "target":
                self.manage_target_stops()
                self.reconcile()
                if (self.s["target"] or {}).get("family") == "ls_xs":
                    self.manage_book()
                else:
                    self.manage_targets()
                return self._run_tail()
            self.manage_exits()
            self.reconcile()
            if self.thr["halt"]:
                self.say(f"THROTTLE HALT: drawdown {self.thr['drawdown_pct']:.1f}% ≥ {self.s['throttle']['halt_at_drawdown_pct']}%; no entries until reviewed")
            elif self.thr["multiplier"] < 1:
                self.say(f"throttle: drawdown {self.thr['drawdown_pct']:.1f}%, risk per trade halved")
            self.find_entries()
        except Exception as e:  # noqa: BLE001
            self.failed = True
            self.say(f"CYCLE ABORTED: {type(e).__name__}: {str(e)[:160]}")
            # live: exits were not managed this cycle (resident stops still hold), urgent but not every hour for the same
            # fault; paper: a bug to fix, high, once a day per kind of fault
            C.alert_once(f"aborted:{self.mode}:{type(e).__name__}", f"{type(e).__name__}: {str(e)[:200]}",
                         "urgent" if self.mode == "live" else "high", "Executor: cycle aborted", every_hours=4 if self.mode == "live" else 24)
        finally:
            if not getattr(self, "_finished", False):
                self.finish()
        if self.failed:
            raise SystemExit(1)
        return self.run_doc

    def _run_tail(self):
        self._finished = True
        self.finish()
        return self.run_doc

    # ------------------------------------------------------- carry mode --
    def manage_carry(self):
        cfg = self.s["carry"]
        now_ms = self.now * 1000
        pairs = H.spot_pairs()
        mids = H.all_mids()
        fund, dec = {}, {}
        for coin in cfg["basket"]:
            try:
                fund[coin] = H.funding_history(coin, now_ms - (cfg["window_hours"] + 30) * 3600 * 1000)
            except Exception as e:  # noqa: BLE001
                fund[coin] = None
                self.say(f"{coin}: candles unavailable ({str(e)[:80]})")
            apr = CA.mean_apr(fund[coin] or [], now_ms, cfg["window_hours"]) if fund[coin] is not None else None
            dec[coin] = (CA.decide(apr, coin in self.positions, cfg), apr)
        if self.btc and self.s.get("carry", {}).get("crisis_unwind") and self.regime_crisis():
            dec = {c: (("exit" if c in self.positions else "none"), a) for c, (d, a) in dec.items()}
        n_active = sum(1 for c, (d, a) in dec.items() if d in ("enter", "hold")) or 1
        # pairs already held first (an exit frees its capital before a new pair is sized), then new entries
        for coin in sorted(cfg["basket"], key=lambda c: dec[c][0] == "enter"):
            try:
                self.carry_step(coin, dec[coin][0], dec[coin][1], pairs.get(coin), mids, fund.get(coin) or [], n_active, cfg)
            except Exception as e:  # noqa: BLE001
                self.say(f"{coin}: entry check failed ({type(e).__name__}: {str(e)[:100]}); skipped this cycle")
        self.persist()

    def regime_crisis(self):
        """True when BTC's market regime (market_regime.py, the Doctrine's classifier) reads crisis on the last
        completed day. A missing reading never forces an unwind."""
        try:
            d, _h = self.bars.get("BTC")
            return MR.now(d) == "crisis"
        except Exception:  # noqa: BLE001 — no reading is not a crisis
            return False

    def carry_committed(self, cfg):
        """Pot capital the open carry pairs use: per pair, its notional per leg × (1 spot + 1/leverage perp margin)."""
        lev = cfg["perp_leverage"]
        return sum(p.get("capital") or p.get("target_n", 0.0) * (1 + 1 / lev) for p in self.positions.values() if p.get("kind") == "carry")

    def carry_capital(self, n, committed, cfg, step_n=0.0):
        """The pot can commit each dollar once: a new pair takes only FREE capital (equity minus what the open pairs use),
        and never a pair below the exchange minimum or below one size step of both legs (step_n, in pot currency: such a
        pair would round to zero coins and sit 'entering' forever, holding its capital). Kept out of carry_checks, whose
        list the dashboard mirrors."""
        eq, lo = self.equity or 0.0, max(float(self.s.get("min_notional_usd", 10)), step_n)
        after = (committed + max(n, lo) * (1 + 1 / cfg["perp_leverage"])) / eq if eq > 0 else 99.0
        return {"check": "gross exposure cap", "ok": n >= lo and after <= 1 + 1e-9, "detail": f"{after:.2f}x after entry, cap 1.00x"}

    def carry_checks(self, coin, pair, spot_mid, perp_mid, cfg):
        checks = []
        add = lambda name, ok, detail="": checks.append({"check": name, "ok": bool(ok), "detail": detail})
        add("not halted", not self.halt, self.halt_reason)
        add("throttle allows entries", not self.thr["halt"], f"drawdown {self.thr['drawdown_pct']:.1f}%")
        add("no reconciliation mismatch", not self.rec_flags.get("reconcile_mismatch"), self.rec_flags.get("reconcile_detail", ""))
        add("equity positive", (self.equity or 0) > 0, "")
        vol_m = (pair or {}).get("vol", 0) / 1e6
        add("universe filters", pair is not None and vol_m >= cfg["min_spot_vol_m"], f"spot 24h volume {vol_m:.1f}M below {cfg['min_spot_vol_m']}M" if pair else "no USDC spot pair")
        basis = abs(spot_mid / perp_mid - 1) * 100 if (spot_mid and perp_mid) else 99.0
        add("price sanity band", basis <= cfg["max_basis_pct"], f"spot vs perp {basis:.2f}%")
        return all(c["ok"] for c in checks), checks

    def carry_step(self, coin, decision, apr, pair, mids, fund_rows, n_active, cfg):
        perp_mid = self.marks.get(coin)
        pos = self.positions.get(coin)
        held = (pos or {}).get("legs", {}).get("spot", {}).get("pair")
        if pos and pair and held and held != pair["pair"]:
            # the most liquid spot pair changed since entry: keep pricing and trading the pair this position holds
            pair = dict(pair, pair=held, szd=pos["legs"]["spot"].get("szd", pair["szd"]))
        spot_mid = mids.get(pair["pair"]) if pair else None
        self.counts["evaluated"] += 1
        self.readings.append({"coin": coin, "book": "carry", "weekly": None, "daily": None, "h4": None, "range": None, "line": None,
                              "close": None, "trigger": None, "why": f"funding {apr * 100:.1f}%/yr (24h mean)" if apr is not None else "no funding reading",
                              "vol_m": (pair or {}).get("vol", 0) / 1e6, "funding_pct": apr * 100 if apr is not None else None, "days": None, "mark": perp_mid})
        if not (perp_mid and spot_mid):
            if pos:
                self.say(f"{coin}: no reading on one timeframe (data gap); position and stop kept as they are")
            return
        if self.mode != "paper":
            raise RuntimeError("live carry is not enabled")
        if pos:
            pos["legs"]["spot"]["mark"] = spot_mid
            self.carry_resolve(coin, pos, pair, cfg)
            CA.accrue(pos, fund_rows, perp_mid, rule_in=pos["state"] != "exiting")
        if decision == "enter" and not pos:
            committed = self.carry_committed(cfg)
            fees = cfg["fees"]
            cost = (fees["spot_taker"] + fees["perp_taker"] + 2 * self.s["paper_slippage_pct"] / 100 if cfg.get("execution") == "taker"
                    else fees["spot_maker"] + fees["perp_maker"])          # what entering both legs costs, per unit of notional
            n = CA.target_notional(self.equity or 0.0, n_active, cfg, (self.equity or 0.0) - committed, cost) * self.fleet_mult
            ok, checks = self.carry_checks(coin, pair, spot_mid, perp_mid, cfg)
            step_n = 10 ** -min(int(pair["szd"]), int((self.ctxs.get(coin) or {}).get("szDecimals", 3))) * perp_mid if pair else 0.0
            checks.append(self.carry_capital(n, committed, cfg, step_n))
            ok = ok and checks[-1]["ok"]
            cand = {"kind": "carry", "tier": "C"}
            if not ok:
                failed = [c for c in checks if not c["ok"]]
                self.counts["refused"] += 1
                if not self.dry:
                    L.record_refusal({"coin": coin, "kind": "carry", "tier": "C"}, failed, self.now, "pre-trade")
                self.say(f"{coin}: signal {cand['kind']} tier {cand['tier']} REFUSED: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed))
                return
            pos = {"coin": coin, "kind": "carry", "side": "carry", "mode": self.mode, "state": "entering", "target_n": n,
                   "capital": n * (1 + 1 / cfg["perp_leverage"]), "book": "carry", "opened": C.iso(self.now), "opened_ts": self.now,
                   "last_funding_ts": int(self.now * 1000), "legs": {"spot": {"pair": pair["pair"], "szd": pair["szd"], "sz": 0.0, "entry": 0.0,
                   "mark": spot_mid}, "perp": {"sz": 0.0, "entry": 0.0}}, "orders": {},
                   "rules": [f"LOGIC v{self.s.get('version', '?')}", f"agent:{C.AGENT}", "carry"]}
            self.positions[coin] = pos
            self.counts["entered"] += 1
            self.say(f"{coin}: carry ENTERING · funding {apr * 100:.1f}%/yr · {n / (self.equity or 1) * 100:.0f}% of pot per leg, "
                     f"{'both legs at market' if (self.s.get('carry') or {}).get('execution') == 'taker' else 'maker orders resting'}")
        if not pos:
            return
        if decision == "exit" and pos["state"] != "exiting":
            pos["state"], pos["orders"], pos["exit_reason"], pos["exit_ts"] = "exiting", {}, "funding below exit", self.now
            self.say(f"{coin}: carry EXITING · funding {apr * 100 if apr is not None else 0:.1f}%/yr below exit")
        self.carry_trade(coin, pos, spot_mid, perp_mid, pair, cfg)
        if pos["state"] == "exiting" and pos["legs"]["spot"]["sz"] <= 1e-12 and pos["legs"]["perp"]["sz"] <= 1e-12:
            self.carry_close_out(coin, pos)

    def carry_close_out(self, coin, pos):
        """Both legs flat: the pair's trade line, its result into the paper pot, the summary line. Returns the record."""
        pos["closed_ts"] = self.now
        rec = CA.closed_record(pos, C.iso(self.now))
        self.positions.pop(coin, None)
        if self.mode == "paper" and self.pot is not None:
            self.pot["cash"] += rec["pnl"]
        self.persist()
        if not self.dry:
            L.append_trade(rec)
        cap = f"{rec['capture'] * 100:.0f}%" if rec["capture"] is not None else "n/a"
        self.say(f"{coin}: carry CLOSED · {rec['pnl'] / (self.equity or 1) * 100:+.2f}% of pot · capture {cap}")
        return rec

    def carry_resolve(self, coin, pos, pair, cfg):
        """Paper: each resting maker order against the hourly bars that opened after it was placed; it fills only if price
        traded through it. Bars are read only for legs that have an order."""
        orders = pos.get("orders") or {}
        for leg in [x for x in ("spot", "perp") if x in orders]:
            o = orders[leg]
            px = CA.paper_fill(o, H.candles(pair["pair"] if leg == "spot" else coin, "1h", 3))
            if px is not None:
                CA.apply_fill(pos, leg, o["side"], px, o["sz"], cfg["fees"][leg + "_maker"])
                orders.pop(leg)

    def carry_goal(self, coin, pos, perp_mid, szd, cfg):
        """The pair's size in COINS, the same for both legs: a coin-equal short perp and long spot is delta-neutral (the
        perp tracks the spot), equal dollars is not. Fixed at entry, so a price move no longer re-trades both legs (the
        old constant-dollar goal did on every 2% move, and that churn was most of the paper losses). Re-set only when the
        pair's notional has drifted more than resize_band from its target, both legs together."""
        legs = pos["legs"]
        fresh = H.round_sz(pos["target_n"] / perp_mid, szd) if perp_mid > 0 else 0.0
        if pos.get("target_sz") is None:
            # a pair opened before coin-equal legs: an open one keeps its perp leg (the hedge) as its size, so nothing trades
            pos["target_sz"] = legs["perp"]["sz"] if (pos["state"] == "open" and legs["perp"]["sz"] > 0) else fresh
        goal = pos["target_sz"]
        if pos["state"] == "open" and goal > 0 and pos.get("target_n"):
            drift = goal * perp_mid / pos["target_n"] - 1
            if abs(drift) > cfg.get("resize_band", 0.25) and fresh > 0 and abs(fresh - goal) >= 10 ** -szd:
                C.log(f"  {coin}: carry pair re-sized {goal:.6g} → {fresh:.6g} coins per leg (notional {drift * 100:+.0f}% from target)")
                pos["resized"] = {"t": C.iso(self.now), "from": goal, "to": fresh}
                pos["target_sz"] = goal = fresh
        return goal

    def carry_trade(self, coin, pos, spot_mid, perp_mid, pair, cfg, at_market=False):
        """Move both legs toward the pair's goal (carry_goal; zero while exiting), keeping them equal in coins.

        execution "maker" (the spec's default): one resting post-only order per leg, both placed and re-quoted together;
        every cycle each order is re-sized to what is still needed, or cancelled when nothing is (a stale order once bought
        back 4,932 PUMP perp after the hedge was already done). When one leg has filled and the other not, the lagging
        leg keeps its order for max_unhedged_hours, then completes at market (the safety override; taker fee).
        execution "taker", or at_market (a flatten): both legs trade now with immediate-or-cancel orders, so the pair is
        never one-legged. Both legs sit on the coarser of the two size steps, and the out-of-balance band is at least one
        such step: a gap no order can close never triggers anything."""
        legs, orders = pos["legs"], pos.setdefault("orders", {})
        szds = {"spot": int(pair["szd"]), "perp": int((self.ctxs.get(coin) or {}).get("szDecimals", 3))}
        szd = min(szds.values())
        mids = {"spot": spot_mid, "perp": perp_mid}
        exiting = pos["state"] == "exiting"
        goal = 0.0 if exiting else self.carry_goal(coin, pos, perp_mid, szd, cfg)
        # out of balance: legs apart by more than the band, never less than one coarse step (a gap no order can close)
        band = max(cfg["delta_band"] * (max(legs["spot"]["sz"], legs["perp"]["sz"]) if exiting else goal), 10 ** -szd)
        # a leg trades when it is off the goal by more than the band, or than its own step (the finer leg can close a
        # gap the coarser one cannot)
        todo = {leg: goal - legs[leg]["sz"] for leg in ("spot", "perp")
                if (legs[leg]["sz"] > 0 if exiting else abs(goal - legs[leg]["sz"]) > max(cfg["delta_band"] * goal, 10 ** -szds[leg]))}
        if at_market or cfg.get("execution") == "taker":
            orders.clear()                                   # live carry would cancel them on the exchange here (Phase 4)
            for leg, n in todo.items():
                self.carry_fill(coin, pos, leg, n, mids[leg], szds[leg], cfg)
            pos.pop("stuck_since", None)
        else:
            self.carry_maker(coin, pos, todo, goal, band, mids, szds, cfg)
        for leg in ("spot", "perp"):
            have = legs[leg]["sz"]
            if exiting and have > 0 and H.round_sz(have, szds[leg]) <= 0:
                # dust no order can sell (below the size precision): written off at the mark so the close can finish
                CA.apply_fill(pos, leg, "sell" if leg == "spot" else "buy", mids[leg], have, 0.0)
                orders.pop(leg, None)
                self.say(f"{coin}: carry dust · {leg} remainder below the exchange's size step, written off at the mark")
        if pos["state"] == "entering" and goal > 0 and legs["spot"]["sz"] > 0 and all(abs(goal - legs[x]["sz"]) <= band for x in legs):
            pos["state"] = "open"

    carry_orders = carry_trade          # the name this step had before coin-equal legs (review scripts call it)

    def carry_maker(self, coin, pos, todo, goal, band, mids, szds, cfg):
        legs, orders = pos["legs"], pos["orders"]
        diff = legs["spot"]["sz"] - legs["perp"]["sz"]             # coins the spot leg holds beyond the perp short
        slack = 600                                                 # cycles start a few seconds early or late
        if abs(diff) > band:
            # one leg filled and the other not: the lagging leg is the one farther from the goal; the leading leg waits
            lag = "perp" if abs(goal - legs["perp"]["sz"]) > abs(goal - legs["spot"]["sz"]) else "spot"
            lead = "spot" if lag == "perp" else "perp"
            move = legs[lead]["sz"] - legs[lag]["sz"]               # coins the lagging leg must move to match
            orders.pop(lead, None)
            pos.setdefault("stuck_since", self.now)
            if self.now - pos["stuck_since"] < cfg["max_unhedged_hours"] * 3600 - slack:
                self.carry_quote(pos, lag, move, mids[lag], szds[lag], cfg)    # its own order keeps its last chance
                return
            if H.round_sz(abs(move), szds[lag]) <= 0:
                return                                              # nothing an order can do: no trade, no alert, timer kept
            orders.pop(lag, None)
            self.carry_fill(coin, pos, lag, move, mids[lag], szds[lag], cfg)
            pos.pop("stuck_since", None)
            what = "leading leg trimmed" if pos["state"] == "exiting" else "lagging leg completed"
            self.say(f"{coin}: carry safety override · legs out of balance for {cfg['max_unhedged_hours']}h, {what} at market")
            if self.mode == "live":
                C.notify("Executor: carry safety override", f"{coin}: legs were out of balance for {cfg['max_unhedged_hours']}h; {what} with a taker order", "high")
            return
        pos.pop("stuck_since", None)
        if not todo:
            orders.clear()
            return
        ts = [o["t"] for o in orders.values()]
        requote = bool(ts) and self.now - min(ts) >= cfg["requote_hours"] * 3600 - slack     # both legs together
        for leg in ("spot", "perp"):
            if leg in todo:
                self.carry_quote(pos, leg, todo[leg], mids[leg], szds[leg], cfg, requote)
            else:
                orders.pop(leg, None)

    def carry_quote(self, pos, leg, n, mid, szd, cfg, requote=False):
        """One resting maker order on `leg` for `n` coins (signed: + adds to the leg; the perp leg is short, so adding
        sells). An order already on the right side keeps its price and time, re-sized in place when the size changed by
        a step, so its paper fill stays honest; it is re-quoted at the mid only when `requote`. Nothing to do cancels."""
        orders = pos["orders"]
        side = ("buy" if n > 0 else "sell") if leg == "spot" else ("sell" if n > 0 else "buy")
        sz = H.round_sz(abs(n), szd)
        o = orders.get(leg)
        if sz <= 0:
            orders.pop(leg, None)
        elif o and o["side"] == side and not requote:
            if abs(o["sz"] - sz) >= 10 ** -szd / 2:
                o["sz"] = sz
        else:
            off = cfg["maker_offset_bps"] / 10000
            orders[leg] = {"side": side, "px": mid * (1 - off) if side == "buy" else mid * (1 + off), "sz": sz, "t": self.now}

    def carry_fill(self, coin, pos, leg, n, mid, szd, cfg):
        """Trade `n` coins on one leg NOW as a taker (signed: + adds to the leg). Paper: at the mid with the paper slippage
        and the taker fee. Live (only a flatten can reach it while live carry is refused): an immediate-or-cancel order
        capped at the entry slippage limit, or 5% when closing; what fills is recorded, the rest waits for the next
        cycle. Returns the size filled."""
        sz = H.round_sz(abs(n), szd)
        if sz <= 0:
            return 0.0
        side = ("buy" if n > 0 else "sell") if leg == "spot" else ("sell" if n > 0 else "buy")
        fee = cfg["fees"][leg + "_taker"]
        if self.mode != "live":
            slip = self.s["paper_slippage_pct"] / 100
            CA.apply_fill(pos, leg, side, mid * (1 + slip) if side == "buy" else mid * (1 - slip), sz, fee)
            return sz
        closing = (leg == "spot") == (side == "sell")
        cap = (5.0 if closing else self.s["entry_slippage_cap_pct"]) / 100
        px = mid * (1 + cap) if side == "buy" else mid * (1 - cap)
        px = H.round_px(px, szd) if leg == "perp" else H.round_spot_px(px, szd)
        name = coin if leg == "perp" else pos["legs"]["spot"]["pair"]
        try:
            avg, got = LV.fill_from_response(LV.taker(self.ex, name, side == "buy", sz, px, LV.new_cloid(), reduce_only=(leg == "perp" and closing)))
        except Exception as e:  # noqa: BLE001
            avg, got = None, f"{type(e).__name__}: {str(e)[:100]}"
        if avg is None:
            C.notify("Executor: carry order not filled", f"{coin} {leg} {side}: {got}", "urgent")
            return 0.0
        CA.apply_fill(pos, leg, side, avg, float(got), fee)
        return float(got)

    def close_carry(self, coin, pos, reason):
        """Close a carry pair NOW, both legs at market (the flatten path; close_position sends carry here). Funding is
        accrued up to now first. Returns the trade record once both legs are flat, else None: what did not fill stays,
        the pair is left exiting, and the next cycle carries on closing it."""
        cfg, legs = self.s.get("carry") or {}, pos["legs"]
        try:
            mids, best = H.all_mids(), H.spot_pairs().get(coin) or {}
        except Exception as e:  # noqa: BLE001
            C.log(f"  {coin}: carry close needs the spot price ({str(e)[:80]}); left for the next cycle")
            return None
        name = legs["spot"].get("pair")
        pair = {"pair": name, "szd": legs["spot"].get("szd", best.get("szd", 8) if best.get("pair") == name else 8)}
        spot_mid, perp_mid = mids.get(name), self.marks.get(coin)
        if not (spot_mid and perp_mid):
            C.log(f"  {coin}: carry close has no spot or perp price; left for the next cycle")
            return None
        legs["spot"]["mark"] = spot_mid
        try:
            CA.accrue(pos, H.funding_history(coin, int(pos.get("last_funding_ts") or self.now * 1000)), perp_mid, rule_in=pos["state"] != "exiting")
        except Exception:  # noqa: BLE001 — at most the last hour's funding is missing from the record
            pass
        if pos["state"] != "exiting":
            pos["state"], pos["exit_ts"] = "exiting", self.now
        pos["exit_reason"], pos["orders"] = reason, {}
        self.carry_trade(coin, pos, spot_mid, perp_mid, pair, cfg, at_market=True)
        if legs["spot"]["sz"] <= 1e-12 and legs["perp"]["sz"] <= 1e-12:
            return self.carry_close_out(coin, pos)
        self.persist()
        return None

    # ------------------------------------------------------ target mode --
    def manage_target_stops(self):
        """Paper only: the resident protective stop, checked on the daily bars since the last check.
        Live stops sit on the exchange; absorb_exchange_closes records them."""
        if self.mode != "paper":
            return
        for coin, pos in list(self.positions.items()):
            try:
                d, h = self.bars.get(coin)
                row = self.ctxs.get(coin, {})
                if not (pos.get("kind") == "book" and self.book_funding(coin, pos)):
                    try:
                        PA.accrue_funding(pos, float(row.get("funding", 0) or 0), self.now)
                    except (TypeError, ValueError):
                        pass
                px, bt = PA.check_stop(pos, h, self.s)
                if px is not None and not self.dry:
                    self.close_position(coin, pos, px, "catastrophic stop" if pos.get("kind") == "book" else "protective stop", bt or self.now)
            except Exception as e:  # noqa: BLE001
                self.say(f"{coin}: exit management failed ({type(e).__name__}: {str(e)[:100]}); position kept")
        self.persist()

    def target_checks(self, coin, add_notional, row, stop_pct, side="long"):
        """The pre-trade checks that apply to opening or increasing a target position (exits never wait). side "short"
        (the long-short book, paper only) mirrors the funding filter."""
        checks = []
        add = lambda name, ok, detail="": checks.append({"check": name, "ok": bool(ok), "detail": detail})
        eq = self.equity or 0.0
        add("not halted", not self.halt, self.halt_reason)
        add("throttle allows entries", not self.thr["halt"], f"drawdown {self.thr['drawdown_pct']:.1f}%")
        add("data fresh and run on time", self.fresh, self.fresh_detail)
        add("no reconciliation mismatch", not self.rec_flags.get("reconcile_mismatch"), self.rec_flags.get("reconcile_detail", ""))
        add("equity positive", eq > 0, "" if eq > 0 else f"equity {eq}")
        gross = sum(p["sz"] * (self.marks.get(c) or p["entry"]) for c, p in self.positions.items())
        add("gross exposure cap", eq > 0 and gross + add_notional <= self.s["gross_exposure_cap_x"] * eq + 1e-9,
            f"{(gross + add_notional) / eq:.2f}x after, cap {self.s['gross_exposure_cap_x']}x" if eq > 0 else "n/a")
        add("above the exchange minimum", add_notional >= self.s["min_notional_usd"], "")
        mark = self.marks.get(coin)
        second = B.last_price(coin)
        dev = abs(mark - second) / second * 100 if (mark and second) else 0.0
        add("price sanity band", dev <= self.s["data"]["sanity_band_pct"], f"mark vs Binance {dev:.2f}%" if second else no_second(coin))
        u_ok, u_reasons = U.check(coin, row, self.s["universe"], None) if side == "long" else U.check(coin, row, self.s["universe"], None, side)
        add("universe filters", u_ok, "; ".join(u_reasons))
        return all(c["ok"] for c in checks), checks

    def manage_targets(self):
        cfg = self.s["target"]
        band, stop_pct = float(cfg["band"]), float(cfg["stop_pct"]) / 100
        eq = self.equity or 0.0
        for coin, (frac, why, d) in self.target_plan(cfg).items():
            try:
                self.manage_target(coin, frac, why, d, eq, band, stop_pct, cfg)
            except Exception as e:  # noqa: BLE001
                self.say(f"{coin}: entry check failed ({type(e).__name__}: {str(e)[:100]}); skipped this cycle")
                self.step_alert("Executor: target step failed", coin, e)

    def target_plan(self, cfg):
        """{coin: (fraction of equity to hold or None, why, daily bars)}. The original Trend block (no "family") keeps
        target.weight × its allocation, unchanged. A recipe block ("family", "params", "coins") runs the shared
        family code in families.py, the same functions the lab backtested. The engine is long-or-flat: a negative
        weight is held at zero."""
        out, panel = {}, {}
        if not cfg.get("family"):
            for coin, alloc in cfg["weights"].items():
                try:
                    d, _h = self.bars.get(coin)
                    w, why = TG.weight(d, cfg)
                    out[coin] = (None if w is None else w * float(alloc), why, d)
                except Exception as e:  # noqa: BLE001
                    out[coin] = (None, f"candles unavailable ({str(e)[:60]})", [])
            return out
        fam, params, alloc, coins = F.from_target_cfg(cfg)
        failed = {}
        for coin in coins:
            try:
                panel[coin] = self.bars.get(coin)[0]
            except Exception as e:  # noqa: BLE001 — one coin's outage is a data gap for that coin only
                failed[coin] = f"candles unavailable ({str(e)[:60]})"
                out[coin] = (None, failed[coin], [])
        if failed and fam in F.ROTATIONS:
            # a rotation ranks the coins against each other: without one coin's bars the ranking of all the others would
            # change and the engine would trade picks the recipe never made. Hold every weight this cycle instead.
            why = f"picks held this cycle: {', '.join(sorted(failed))} has no candles, and ranking without it would change the picks"
            return {c: (None, failed.get(c) or why, panel.get(c, [])) for c in coins}
        regime = None
        if F.needs_regime(params):
            try:
                regime = MR.by_day(self.bars.get("BTC")[0])
            except Exception as e:  # noqa: BLE001 — no regime reading: hold everything as it is
                return {c: (None, f"market regime unavailable ({str(e)[:60]})", panel.get(c, [])) for c in coins}
        if panel:
            for coin, (w, why) in F.latest(panel, fam, params, regime, alloc).items():
                if w is not None and w < 0:
                    w, why = 0.0, why + " · short signal held flat (the engine is long-or-flat)"
                out[coin] = (w, why, panel[coin])
        return out

    def manage_target(self, coin, frac, why, d, eq, band, stop_pct, cfg):
        row = self.ctxs.get(coin) or {}
        mark = self.marks.get(coin)
        self.counts["evaluated"] += 1
        self.readings.append({"coin": coin, "book": cfg.get("book", "trend"), "weekly": None, "daily": None, "h4": None, "range": None,
                              "line": None, "close": d[-1]["c"] if d else None, "trigger": None, "why": why,
                              "vol_m": None, "funding_pct": H.funding_annual_pct(row), "days": len(d), "mark": mark})
        if frac is None or not mark:
            self.say(f"{coin}: no reading on one timeframe (data gap); position and stop kept as they are")
            return
        pos = self.positions.get(coin)
        cur = pos["sz"] * mark if pos else 0.0
        mult = (self.thr["multiplier"] if self.thr["multiplier"] > 0 else 1.0) * self.fleet_mult
        tgt = frac * eq * mult
        action = TG.decide(cur, tgt, band)
        self.say(f"{coin}: target {tgt / eq * 100 if eq else 0:.0f}% of pot, holding {cur / eq * 100 if eq else 0:.0f}% → {action}")
        if action in ("hold", "none") or self.dry:
            return
        if action == "close":
            self.close_position(coin, pos, mark * (1 - self.s["paper_slippage_pct"] / 100) if self.mode == "paper" else mark, "below its average" if not cfg.get("family") else "target weight zero", self.now)
            return
        if action == "decrease":
            self.target_resize(coin, pos, tgt, mark, stop_pct)
            return
        ok, checks = self.target_checks(coin, tgt - cur, row, stop_pct)
        if not ok:
            failed = [c for c in checks if not c["ok"]]
            self.counts["refused"] += 1
            L.record_refusal({"coin": coin, "kind": action, "tier": "T"}, failed, self.now, "pre-trade")
            cand = {"kind": action, "tier": "T"}
            self.say(f"{coin}: signal {cand['kind']} tier {cand['tier']} REFUSED: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed))
            return
        if action == "open":
            self.target_open(coin, tgt, mark, stop_pct, why)
        else:
            self.target_resize(coin, pos, tgt, mark, stop_pct)

    def target_open(self, coin, notional, mark, stop_pct, why):
        eq = self.equity or 0.0
        stop = mark * (1 - stop_pct)
        lev = int(self.s["leverage_cap_x"])
        cand = {"coin": coin, "kind": "target", "tier": "T", "stop": stop, "bar_t": self.bars.get(coin)[0][-1]["t"],
                "book": self.s["target"].get("book", "trend"), "benchmark": coin, "bench_mark": mark}
        sizing = {"notional": notional, "risk_amt": notional * stop_pct, "leverage": lev, "risk_pct": stop_pct * notional / eq * 100 if eq else 0,
                  "notional_pct_equity": notional / eq * 100 if eq else 0, "dist_pct": stop_pct * 100}
        pos = self.execute_entry(cand, sizing, mark, {"weekly_dir": None, "daily_dir": None})
        if pos:
            self.counts["entered"] += 1
            pos["rules"] = pos.get("rules", []) + ["target:" + why[:60]]
            if self.mode == "paper":
                pos["stop"] = pos["initial_stop"] = pos["entry"] * (1 - stop_pct)   # 15% below the fill, per the spec
            self.persist()

    def target_resize(self, coin, pos, tgt, mark, stop_pct):
        cur = pos["sz"] * mark
        if self.mode == "paper":
            cash = TG.paper_resize(pos, tgt, mark, self.s)
            self.pot["cash"] += cash
        else:
            row = self.ctxs.get(coin, {})
            szd = int(row.get("szDecimals", 3))
            if tgt > cur:
                add_sz = H.round_sz((tgt - cur) / mark, szd)
                try:
                    resp = LV.entry_ioc(self.ex, coin, add_sz, H.round_px(mark * (1 + self.s["entry_slippage_cap_pct"] / 100), szd), LV.new_cloid())
                    avg, second = LV.fill_from_response(resp)
                except Exception as e:  # noqa: BLE001 — a timeout is not "no fill": look at the exchange
                    avg, second = self.resize_recover(coin, pos, f"{type(e).__name__}: {str(e)[:100]}", mark, True, pos["sz"] + add_sz)
                if avg is None:
                    self.say(f"{coin}: entry not filled ({second})")
                    return
                filled = float(second)
                pos["entry"] = (pos["entry"] * pos["sz"] + avg * filled) / (pos["sz"] + filled)
                pos["sz"] += filled
                pos["entry_fee"] = pos.get("entry_fee", 0.0) + avg * filled * self.s["fee_taker_pct"] / 100
            else:
                cut_sz = H.round_sz(min(pos["sz"], (cur - tgt) / mark), szd)
                try:
                    resp = LV.reduce_ioc(self.ex, coin, cut_sz, H.round_px(mark * (1 - self.s["entry_slippage_cap_pct"] / 100), szd), LV.new_cloid())
                    avg, second = LV.fill_from_response(resp)
                except Exception as e:  # noqa: BLE001
                    avg, second = self.resize_recover(coin, pos, f"{type(e).__name__}: {str(e)[:100]}", mark, False, pos["sz"])
                if avg is None:
                    self.say(f"{coin}: close NOT filled ({second}); position and its resident stop kept, retry next cycle")
                    return
                filled = float(second)
                pos["realized"] = pos.get("realized", 0.0) + (avg - pos["entry"]) * filled - avg * filled * self.s["fee_taker_pct"] / 100
                pos["sz"] -= filled
            pos["notional"] = pos["sz"] * pos["entry"]
            self.persist()                                    # the new size exists on the exchange: record it first
        pos["notional"] = pos["sz"] * pos["entry"]
        pos["risk_amt"] = max(pos.get("risk_amt", 0.0), pos["notional"] * stop_pct)
        new_stop = pos["entry"] * (1 - stop_pct)
        if self.mode == "live":
            self.protect(coin, pos, new_stop)                 # the resident stop follows the new size; fail closed
        else:
            pos["stop"] = new_stop
        self.persist()
        self.say(f"{coin}: resized to {tgt / (self.equity or 1) * 100:.0f}% of pot, stop {new_stop:.5g}")

    # ------------------------------------------------ long-short book --
    # The lab's ls_xs family (src/executor/longshort.py), PAPER ONLY: the shadow experiment agents/shadow-01. Order of
    # work each daily run, as the lab's harness: the catastrophic stops (manage_target_stops, above), a held coin no
    # longer listed closed at its last mark, the book drawdown brake on the agent's equity, then, on a rebalance day
    # only, the day's decision (the universe, the legs, the target weights) and the trades toward it (exits and trims
    # first, then opens and growth, which pass the pre-trade checks). Between rebalances nothing is traded: the weights
    # drift, as in the lab.
    # One decision per rebalance day (audit 2026-10-23 E3, 2026-10-30 N3): a daily agent runs up to three times after
    # the close (00:05, 01:05, 02:05 UTC) and the funding it reads moves between runs, so re-forming the legs on every
    # run re-formed the book (2026-10-30: a quarter of the week's book changed after 00:05). The first fresh run decides,
    # as the lab's single funding reading at about 00:08 UTC (lab/pit.py funding_reading), and saves the decision in
    # book.json (last_rebalance) before any trade; later runs that day keep that book and only finish it (book_trade).
    # A run whose data is not fresh never decides.
    def manage_book(self):
        cfg = self.s["target"]
        if self.mode != "paper" or not cfg.get("shorts"):
            self.say("long-short book: runs in paper with target.shorts on only; nothing traded")
            return
        p = XS.params(cfg.get("params"))
        u = dict(XS.UNIVERSE, **(cfg.get("universe") or {}))
        band = float(cfg.get("band", p["band"]))
        cat = float(cfg.get("catastrophic_stop_pct", 100.0)) / 100
        slip = self.s["paper_slippage_pct"] / 100
        btc = self.bars.get("BTC")[0]
        if not btc:
            self.say("long-short book: no Bitcoin bars (data gap); positions kept as they are")
            return
        day = btc[-1]["t"] // XS.DAY * XS.DAY
        for coin, pos in list(self.positions.items()):        # a held coin Hyperliquid no longer lists: closed at its last mark
            if coin not in self.ctxs and not self.dry:
                px = self.marks.get(coin) or pos.get("mark") or pos["entry"]
                self.close_position(coin, pos, px, "delisted", self.now)
        self.equity, self.unreal = PA.equity(self.pot, self.positions, self.marks)
        eq = self.equity or 0.0
        book = C.load_json(BOOK) or {}
        rebalance = XS.is_rebalance(day, p)
        braked, event = XS.brake_step(book, eq, day, rebalance, bool(self.positions), p)
        book.update({"day": C.iso(day)[:10], "equity_seen": eq})
        until = C.iso(book["braked_until"])[:10] if book.get("braked_until") else None
        if event == "brake":
            self.say(f"BOOK BRAKE: equity {eq / book['peak'] * 100 - 100:+.1f}% from its peak, beyond -{p['brake_dd'] * 100:.0f}%: "
                     f"every position closes, flat until the first rebalance after {until}")
            self.trade_alert("Executor: book brake", f"down {100 - eq / book['peak'] * 100:.1f}% from its peak: the book closes and stays flat for {p['brake_days']} days")
        elif event == "lift":
            self.say(f"book brake lifted: the book re-forms today, its peak reset to today's equity")
        if braked:
            if event != "brake":
                self.say(f"book brake on: flat until the first rebalance after {until}")
            # every braked day, as the lab: whatever is still held closes (a name without a mark the day the brake
            # tripped closes on the first day it has one)
            for coin, pos in list(self.positions.items()):
                mark = self.marks.get(coin)
                if mark and not self.dry:
                    self.close_position(coin, pos, mark * (1 + slip) if PA.is_short(pos) else mark * (1 - slip), "book brake", self.now)
            self._book_save(book)
            return
        if not rebalance:
            nxt = C.iso(day + (p["rebalance_days"] - (day // XS.DAY) % p["rebalance_days"]) * XS.DAY)[:10]
            self.say(f"long-short book: between rebalances (next on {nxt}); {len(self.positions)} names held as they drift")
            for coin, pos in self.positions.items():
                self._book_reading(coin, f"{pos.get('side')} leg, held between rebalances", None)
            self._book_save(book)
            return
        day_s = C.iso(day)[:10]
        dec = book.get("last_rebalance") or {}
        later = dec.get("day") == day_s and isinstance(dec.get("weights"), dict)
        if later:
            pend = dec.get("pending") or {}
            self.say(f"long-short book {day_s}: the day's book stands (decided {str(dec.get('decided') or '?')[11:16]} UTC); "
                     + (f"long {', '.join(dec.get('long') or [])} · short {', '.join(dec.get('short') or [])}" if dec["weights"]
                        else (dec.get("why") or "no book"))
                     + (f"; still to do: {', '.join(f'{c} ({why})' for c, why in sorted(pend.items()))}" if pend else "; nothing pending"))
        elif not self.fresh:
            self.say(f"long-short book {day_s}: data not fresh ({self.fresh_detail}); the first fresh run decides the day's book, "
                     f"{len(self.positions)} names kept as they are")
            for coin, pos in self.positions.items():
                self._book_reading(coin, f"{pos.get('side')} leg, kept: the day's book is not decided yet", None)
            self._book_save(book)
            return
        else:
            dec = self.book_decide(day, u, p, book)
            if dec is None:
                self._book_save(book)
                return
        self.book_trade(dec, later, band, cat, slip, eq)
        self._book_save(book)

    def book_decide(self, day, u, p, book):
        """The day's decision, made by the first fresh run of a rebalance day: the universe, the per-name and per-side
        gates, the legs and their target weights, saved in book.json (last_rebalance) before any trade with every name
        pending until a run has traded it. Leg-formation refusals are said, counted and recorded (stage "leg formation"),
        and so are the names that had no second source for the price band (it fails open for them). None when there
        is no reading this run (positions kept; the next run decides)."""
        try:
            elig, excluded, top, bars = self.book_universe(day, u)
        except Exception as e:  # noqa: BLE001 — a missing coin would change the ranking: no rebalance this run
            self.say(f"long-short book: universe unavailable ({type(e).__name__}: {str(e)[:100]}); positions kept, retried next run")
            return None
        row = lambda c: self.ctxs.get(c) or {}                       # noqa: E731
        # gates v7 (review R1): each leg is formed only from names the engine could enter on that side today, so a
        # refusal never leaves a one-sided book. Per name and side: the universe filters (funding mirrored for a short,
        # volume, open interest, max leverage) and the price sanity band. Portfolio checks stay per order.
        why_not = {"long": {}, "short": {}}                          # {side: {coin: [failed checks]}}
        unchecked = {}                                               # no second source: the band is not checked (E10)
        for c in elig:
            mark, second = self.marks.get(c), B.last_price(c)
            if not second:
                unchecked[c] = B.why_none(c)
            dev = abs(mark - second) / second * 100 if (mark and second) else 0.0
            for side in ("long", "short"):
                ok, reasons = U.check(c, row(c), self.s["universe"], None, side)
                failed = [] if ok else [{"check": "universe filters", "ok": False, "detail": "; ".join(reasons)}]
                if dev > self.s["data"]["sanity_band_pct"]:
                    failed.append({"check": "price sanity band", "ok": False, "detail": f"mark vs Binance {dev:.2f}%"})
                if failed:
                    why_not[side][c] = failed
        no_long, no_short = set(why_not["long"]), set(why_not["short"])
        panel = {c: bars[c] for c in set(elig) | set(self.positions) | {"BTC"} if bars.get(c)}
        w, info = XS.latest(panel, p, elig, no_long, no_short)
        if w is None:
            self.say(f"long-short book: no reading today ({info.get('why')}); positions kept")
            return None
        text = lambda f: "; ".join(x["detail"] for x in f)           # noqa: E731
        refused = {side: {c: why_not[side][c] for c in sorted(info.get("skipped_" + side) or [])} for side in ("long", "short")}
        day_s = C.iso(day)[:10]
        dec = {"day": day_s, "ranked": info.get("ranked"), "k": info.get("k"),
               "long": info.get("long"), "short": info.get("short"), "why": info.get("why") or None,
               "refused_long": {c: text(f) for c, f in refused["long"].items()},
               "refused_short": {c: text(f) for c, f in refused["short"].items()},
               "universe": [c for c, _v in top], "excluded": excluded, "unchecked": dict(sorted(unchecked.items())),
               "decided": C.iso(self.now), "weights": w,
               "pending": {c: "not traded yet" for c in sorted(set(w) | set(self.positions))}}
        book["last_rebalance"] = dec
        self._book_save(book)                     # the decision before any trade: a run that stops part-way leaves it to finish
        self.say(f"long-short book {day_s}: {info.get('ranked')} names ranked of {len(elig)} eligible (top {u['n']} by Hyperliquid volume); "
                 + (f"long {', '.join(info['long'])} · short {', '.join(info['short'])}" if w else info.get("why", "no book")))
        if refused["long"] or refused["short"]:
            self.say("long-short book: refused at leg formation, so left out of that side's leg today: "
                     + " · ".join(f"{side} " + ", ".join(f"{c} ({text(f)})" for c, f in refused[side].items())
                                  for side in ("long", "short") if refused[side]))
            for side in ("long", "short"):
                for c, f in refused[side].items():
                    self.counts["refused"] += 1
                    if not self.dry:
                        L.record_refusal({"coin": c, "kind": "book", "tier": "S" if side == "short" else "L"}, f, self.now, "leg formation")
        if unchecked:
            by_why = {}
            for c, why in sorted(unchecked.items()):
                by_why.setdefault(why, []).append(c)
            self.say(f"long-short book: no second source for the price band, so it was not checked for {len(unchecked)} of {len(elig)} "
                     "eligible names: " + "; ".join(f"{', '.join(cs)} ({why})" for why, cs in by_why.items()))
        return dec

    def book_trade(self, dec, later, band, cat, slip, eq):
        """Trade toward the day's decided book (dec: book.json last_rebalance). The deciding run takes every name. A later
        run the same day re-decides nothing: it takes only the names still pending (an open or growth that was refused,
        a name that had no mark) and any name held against the decision (a close that was missed); every other name
        keeps what the earlier run left, without a band check or a re-size. A name leaves pending once traded or found
        inside the band."""
        w, pending = dec["weights"], dec.setdefault("pending", {})
        row = lambda c: self.ctxs.get(c) or {}                       # noqa: E731
        when = f" (decided {str(dec.get('decided') or '?')[11:16]} UTC)" if later else ""
        mult = (self.thr["multiplier"] if self.thr["multiplier"] > 0 else 1.0) * self.fleet_mult
        want = {c: w.get(c, 0.0) * eq * mult for c in sorted(set(w) | set(self.positions))}
        ups = []
        for coin, tgt in want.items():                                # 1. exits, flips and trims: never wait
            mark = self.marks.get(coin)
            pos = self.positions.get(coin)
            why = (f"{'long' if tgt > 0 else 'short'} leg, weight {w[coin] * 100:+.1f}% of equity" if coin in w
                   else "not in this week's book") + when
            self._book_reading(coin, why, mark)
            sg = -1.0 if (pos and PA.is_short(pos)) else 1.0
            against = bool(pos) and (tgt == 0 or (tgt > 0) != (sg > 0))
            if later and coin not in pending and not against:
                continue                                              # traded by an earlier run today: kept as decided
            if not mark:
                self.say(f"{coin}: no reading on one timeframe (data gap); position and stop kept as they are")
                pending[coin] = "no mark (data gap)"
                continue
            cur = sg * pos["sz"] * mark if pos else 0.0
            if against:
                self.say(f"{coin}: target {tgt / eq * 100 if eq else 0:+.0f}% of pot, holding {cur / eq * 100 if eq else 0:+.0f}% → close")
                if not self.dry:
                    self.close_position(coin, pos, mark * (1 + slip) if sg < 0 else mark * (1 - slip), "target weight zero" if tgt == 0 else "side flips", self.now)
                pos, cur = None, 0.0
            if tgt == 0:
                pending.pop(coin, None)
                continue
            action = TG.decide(abs(cur), abs(tgt), band)
            if action == "decrease":
                self.say(f"{coin}: target {tgt / eq * 100 if eq else 0:+.0f}% of pot, holding {cur / eq * 100 if eq else 0:+.0f}% → decrease")
                if not self.dry:
                    self._book_resize(coin, pos, abs(tgt), mark, cat)
                pending.pop(coin, None)
            elif action in ("open", "increase"):
                ups.append((coin, tgt, action))
            else:
                self.say(f"{coin}: target {tgt / eq * 100 if eq else 0:+.0f}% of pot, holding {cur / eq * 100 if eq else 0:+.0f}% → {action}")
                pending.pop(coin, None)
        for coin, tgt, action in ups:                                # 2. opens and growth: the pre-trade checks
            mark, pos = self.marks[coin], self.positions.get(coin)
            side = "long" if tgt > 0 else "short"
            cur = ((pos["sz"] * mark) if pos else 0.0) * (1 if tgt > 0 else -1)
            self.say(f"{coin}: target {tgt / eq * 100 if eq else 0:+.0f}% of pot, holding {cur / eq * 100 if eq else 0:+.0f}% → {action}")
            if self.dry:
                continue
            ok, checks = self.target_checks(coin, abs(tgt) - abs(cur), row(coin), cat, side)
            if not ok:
                failed = [c for c in checks if not c["ok"]]
                self.counts["refused"] += 1
                cand = {"coin": coin, "kind": "book", "tier": "S" if side == "short" else "L", "side": side, "action": action}
                L.record_refusal(cand, failed, self.now, "pre-trade")
                self.say(f"{coin}: signal {cand['kind']} tier {cand['tier']} REFUSED: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed))
                pending[coin] = f"{action} refused: " + "; ".join(c["check"] for c in failed)
                continue
            if pos:
                self._book_resize(coin, pos, abs(tgt), mark, cat)
            else:
                self._book_open(coin, side, abs(tgt), mark, cat, dec)
            pending.pop(coin, None)

    def book_funding(self, coin, pos):
        """The long-short book with target "funding": "history" (shadow-01): accrue Hyperliquid's actual hourly funding
        since the last accrual (PA.accrue_funding_history) instead of the rate read now times the hours. True when done;
        False (the caller falls back to the rate) when the history cannot be read or the setting is off."""
        if (self.s.get("target") or {}).get("funding") != "history":
            return False
        mark = self.marks.get(coin) or pos.get("mark") or pos["entry"]
        try:
            rows = H.funding_history(coin, int(pos.get("last_funding_ts", self.now)) * 1000)
        except Exception as e:  # noqa: BLE001 — no history this run: the read rate, as every other agent
            self.say(f"long-short book: {coin} funding history unavailable ({type(e).__name__}); the rate read now is used")
            return False
        PA.accrue_funding_history(pos, rows or [], mark, self.now)
        return True

    def book_universe(self, day, u):
        """(eligible coins, {coin: why not eligible}, ranked top [(coin, median volume)], {coin: daily bars}) for the
        decision day: Hyperliquid's listed perps, the u["prefilter"] busiest by 24h volume (and every held coin) read
        once, ranked by trailing median notional volume up to the day before (longshort.rank_by_volume), the top
        u["n"] kept, those listed with at least u["min_usd_vol"] traded on the day eligible. Raises when a coin's candles
        cannot be read: a ranking without it could differ, so the book waits for the next run."""
        listed = {c for c in self.ctxs if not H.is_builder(c)}

        def vol24(c):
            try:
                return float(self.ctxs[c].get("dayNtlVlm") or 0)
            except (TypeError, ValueError):
                return 0.0
        cand = sorted(listed, key=lambda c: (-vol24(c), c))[:int(u["prefilter"])]
        cand = sorted(set(cand) | set(self.positions) | {"BTC"})
        bars = {c: self.bars.get(c)[0] for c in cand}
        top = XS.rank_by_volume(bars, day - XS.DAY, int(u["n"]), int(u["window"]), int(u["min_history"]))
        elig, excluded = XS.eligible_today(bars, day, top, listed, float(u["min_usd_vol"]))
        return elig, excluded, top, bars

    def _book_open(self, coin, side, notional, mark, cat, last):
        """Paper only: a new name of the book, at the mark with slippage and the taker fee, its catastrophic stop set."""
        eq = self.equity or 0.0
        short = side == "short"
        cand = {"coin": coin, "kind": "book", "tier": "S" if short else "L", "side": side, "stop": mark * (1 + cat) if short else mark * (1 - cat),
                "bar_t": self.bars.get(coin)[0][-1]["t"], "book": self.s["target"].get("book", "longshort"), "benchmark": None, "bench_mark": None}
        sizing = {"notional": notional, "risk_amt": notional * cat, "leverage": int(self.s["leverage_cap_x"]),
                  "risk_pct": cat * notional / eq * 100 if eq else 0, "notional_pct_equity": notional / eq * 100 if eq else 0, "dist_pct": cat * 100}
        rules = [f"LOGIC v{self.s.get('version', '?')}", f"agent:{C.AGENT}", "book:ls_xs", f"side:{side}", "paper-only",
                 f"rebalance:{last.get('day')}"]
        pos = PA.open_position(cand, sizing, mark, self.s, self.now, "paper", {"funding_annual_pct": H.funding_annual_pct(self.ctxs.get(coin, {}))}, rules)
        pos["stop"] = pos["initial_stop"] = pos["entry"] * (1 + cat) if short else pos["entry"] * (1 - cat)
        self.pot["cash"] -= pos["entry_fee"]
        self.positions[coin] = pos
        self.persist()
        self.counts["entered"] += 1
        cand["stop"] = pos["stop"]
        self.say(f"{coin}: ENTERED {describe(cand, sizing)}")
        self.trade_alert("Executor: entered", f"{coin} {side} (long-short book, paper)")
        return pos

    def _book_resize(self, coin, pos, tgt, mark, cat):
        """Paper only: grow or trim a name of the book to the notional tgt; its catastrophic stop follows the entry."""
        self.pot["cash"] += TG.paper_resize(pos, tgt, mark, self.s)
        pos["risk_amt"] = max(pos.get("risk_amt", 0.0), pos["notional"] * cat)
        new_stop = pos["entry"] * (1 + cat) if PA.is_short(pos) else pos["entry"] * (1 - cat)
        pos["stop"] = new_stop
        self.persist()
        self.say(f"{coin}: resized to {tgt / (self.equity or 1) * 100:.0f}% of pot, stop {new_stop:.5g}")

    def _book_reading(self, coin, why, mark):
        self.counts["evaluated"] += 1
        row = self.ctxs.get(coin) or {}
        try:
            d = self.bars.get(coin)[0]
        except Exception:  # noqa: BLE001
            d = []
        self.readings.append({"coin": coin, "book": self.s["target"].get("book", "longshort"), "weekly": None, "daily": None, "h4": None,
                              "range": None, "line": None, "close": d[-1]["c"] if d else None, "trigger": None, "why": why,
                              "vol_m": None, "funding_pct": H.funding_annual_pct(row), "days": len(d), "mark": mark or self.marks.get(coin)})

    def _book_save(self, book):
        if not self.dry:
            C.write_json(BOOK, book)

    def finish(self):
        """Always runs: marks, write-through, the run record, the ledger page, the daily line."""
        c = self.counts
        self.say(f"evaluated {c['evaluated']} names · {c['triggers']} triggers · {c['refused']} refused · {c['proposed']} proposed · {c['entered']} entered · {len(self.positions)} open")
        if self.mode == "paper" and self.pot is not None:
            self.equity, self.unreal = PA.equity(self.pot, self.positions, self.marks)
        for coin, pos in self.positions.items():
            m = self.marks.get(coin)
            if m and pos.get("entry"):
                pos["mark"], pos["upnl_pct"] = m, ((pos["entry"] / m - 1) if PA.is_short(pos) else (m / pos["entry"] - 1)) * 100
        if not self.dry and (self.pot is not None or self.mode == "live"):
            self.persist()
            if self.equity is not None:
                L.equity_point(self.now, self.equity, self.cash if self.mode == "live" else self.pot["cash"], self.unreal or 0.0, self.mode)
        self.run_doc = {"t": C.iso(self.now), "agent": C.AGENT, "tf": self.bars.tf, "mode": self.mode, "hours": self.hours_mode, "dry": self.dry, "fresh": self.fresh,
                        "failed": self.failed, "btc_weekly": R.label(self.btc.get("weekly_dir")), "btc_daily": R.label(self.btc.get("daily_dir")),
                        "positions": sorted(self.positions), "open_proposals": [p["id"] for p in P.open_proposals()],
                        "throttle": self.thr, "halt": self.halt, "fleet_mult": self.fleet_mult, "counts": self.counts, "summary": self.summary,
                        "readings": self.readings, "equity": self.equity, "hours_local": self.local.strftime("%H:%M %Z")}
        if not self.dry:
            C.write_json(C.STATE / "runs" / "last_run.json", self.run_doc)
            C.append_jsonl(C.STATE / "runs" / f"{C.iso(self.now)[:10]}.jsonl", self.run_doc)
            L.render_markdown(self.positions, self.summary, self.mode)
            if not self.failed and self.local.hour == self.s.get("daily_summary_local_hour", 8):
                pts = L.equity_points(self.mode)
                day_ago = [p for p in pts if p["ts"] <= self.now - 86400]
                chg = f"{(self.equity / day_ago[-1]['equity'] - 1) * 100:+.2f}% on the day" if self.equity and day_ago and day_ago[-1]["equity"] else "no prior day"
                C.notify("Executor: daily", f"{self.mode} · BTC weekly {R.label(self.btc.get('weekly_dir'))} · {len(self.positions)} open · "
                                            f"{len(P.open_proposals())} awaiting approval · pot {chg} · drawdown {self.thr['drawdown_pct']:.1f}%", "low")
