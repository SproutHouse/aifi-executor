"""paper.py — the paper engine. Same position records as live, filled at Hyperliquid's mark with the
configured slippage and taker fee, stopped on the 4-hour bars that closed since the last cycle.

Shorts (2026-10-18, the long-short book of agents/shadow-01 only; paper only): a position with "side": "short" keeps
a positive size, gains when the price falls, has its stop above the entry, and RECEIVES funding while the rate is
positive (funding_paid goes negative). Every long position takes exactly the code path it always took.

Spot longs (2026-11-01, target mode with settings.target.long_venue "spot"; paper only): a position with "venue": "spot"
holds the coin itself on its Hyperliquid spot pair ("pair", e.g. "@142" for UBTC). It is valued at that pair's mark
(marks[pair]), pays its own taker fee (the position's "fee_taker_pct") and never pays funding: a coin held outright has
no funding. A perp position carries no "venue" key and takes exactly the code path it always took."""
from . import common as C

POT = C.STATE / "paper.json"


def pot(s):
    p = C.load_json(POT)
    if not p:
        p = {"cash": float(s["pot_usd_paper"]), "start": float(s["pot_usd_paper"]), "created": C.iso()}
        C.write_json(POT, p)
    return p


def save_pot(p):
    C.write_json(POT, p)


def carry_value(pos, perp_mark):
    """A carry position's value to the pot: funding received − fees + realised leg P&L + open P&L on both legs."""
    L = pos["legs"]
    v = pos.get("funding_income", 0.0) - pos.get("fees", 0.0) + pos.get("spot_pnl", 0.0) + pos.get("perp_pnl", 0.0)
    sm = L["spot"].get("mark")
    if sm and L["spot"]["sz"]:
        v += (sm - L["spot"]["entry"]) * L["spot"]["sz"]
    if perp_mark and L["perp"]["sz"]:
        v += (L["perp"]["entry"] - perp_mark) * L["perp"]["sz"]
    return v


def is_spot(pos):
    return bool(pos) and pos.get("venue") == "spot"


def mark_of(pos, coin, marks):
    """The price a position is valued at: a spot long at its pair's mark (the perp's when the spot mark is missing: the
    two sit within the engine's basis limit of each other, and a missing price must not read as a loss), a perp at the
    coin's mark."""
    if is_spot(pos):
        return marks.get(pos.get("pair")) or marks.get(coin)
    return marks.get(coin)


def fee_pct(pos, s):
    """The taker fee, in %, that trades on this position pay: its own (spot) or the settings' perp fee."""
    f = (pos or {}).get("fee_taker_pct")
    return float(f) if isinstance(f, (int, float)) else float(s["fee_taker_pct"])


def equity(p, positions, marks):
    unreal = 0.0
    for coin, pos in positions.items():
        m = mark_of(pos, coin, marks)
        if pos.get("kind") == "carry":
            unreal += carry_value(pos, m)
        elif m and is_short(pos):
            unreal += (pos["entry"] - m) / pos["entry"] * pos["notional"] - pos.get("funding_paid", 0.0)
        elif m:
            # open P&L less the funding already owed: funding is charged to cash at close (cycle._record_close), so
            # counting it here keeps equity (and the throttle's drawdown) honest while the position is open
            unreal += (m - pos["entry"]) / pos["entry"] * pos["notional"] - pos.get("funding_paid", 0.0)
    return p["cash"] + unreal, unreal


def is_short(pos):
    return pos.get("side") == "short"


def open_position(cand, sizing, mark, s, ts, mode="paper", context=None, rules=None):
    slip = s["paper_slippage_pct"] / 100
    short = cand.get("side") == "short"
    entry = mark * (1 - slip) if short else mark * (1 + slip)       # a short sells: filled below the mark
    fpct = fee_pct(cand, s)                                         # a spot candidate carries its own fee
    fee = sizing["notional"] * fpct / 100
    pos = {"coin": cand["coin"], "side": "short" if short else "long", "kind": cand["kind"], "tier": cand["tier"], "mode": mode,
            "entry": entry, "stop": cand["stop"], "initial_stop": cand["stop"], "notional": sizing["notional"],
            "sz": sizing["notional"] / entry, "risk_amt": sizing["risk_amt"], "leverage": sizing["leverage"],
            "notional_pct_equity": sizing["notional_pct_equity"], "entry_fee": fee, "funding_paid": 0.0,
            "opened": C.iso(ts), "opened_ts": ts, "last_bar_t": cand.get("bar_t", ts), "last_funding_ts": ts,
            "context": context or {}, "rules": rules or [], "stop_cloid": None, "entry_cloid": None,
            "book": cand.get("book"), "benchmark": cand.get("benchmark"), "bench_entry": cand.get("bench_mark")}
    if cand.get("venue") == "spot" and not short:
        pos.update({"venue": "spot", "pair": cand["pair"], "token": cand.get("token"), "fee_taker_pct": fpct})
    return pos


def accrue_funding(pos, hourly_rate, ts):
    """Longs pay a positive rate; a short receives it (its funding_paid falls), and pays a negative one. A spot long
    pays none: only the cursor moves."""
    hours = max(0.0, (ts - pos.get("last_funding_ts", ts)) / 3600)
    if is_spot(pos):
        pos["last_funding_ts"] = ts
        return
    if is_short(pos):
        pos["funding_paid"] = pos.get("funding_paid", 0.0) - hourly_rate * hours * pos["notional"]
    else:
        pos["funding_paid"] = pos.get("funding_paid", 0.0) + hourly_rate * hours * pos["notional"]
    pos["last_funding_ts"] = ts


def accrue_funding_history(pos, rows, mark, ts):
    """Accrue Hyperliquid's ACTUAL funding (the long-short book's "funding": "history"): each hourly record of
    funding_history ({time in ms, fundingRate}) after the position's last accrual and up to ts, on the position's value
    at the mark; longs pay a positive rate, a short receives it. Returns the number of records used. The cursor moves to
    the newest record used, so an hour is never counted twice and never skipped."""
    last = pos.get("last_funding_ts", ts)
    if is_spot(pos):
        pos["last_funding_ts"] = ts
        return 0
    used = [(int(r["time"]), float(r["fundingRate"])) for r in rows if last * 1000 < int(r["time"]) <= ts * 1000]
    if not used:
        return 0
    paid = sum(x for _t, x in used) * pos["sz"] * mark
    pos["funding_paid"] = pos.get("funding_paid", 0.0) + (-paid if is_short(pos) else paid)
    pos["last_funding_ts"] = max(t for t, _x in used) // 1000
    return len(used)


def check_stop(pos, bars, s):
    """First completed 4-hour bar after the last checked one whose low breaches the stop fills the exit (a short: whose
    high reaches its stop, filled at max(open, stop) plus slippage)."""
    slip = s["paper_slippage_pct"] / 100
    for b in bars:
        if b["t"] <= pos.get("last_bar_t", 0):
            continue
        if is_short(pos):
            if b["h"] >= pos["stop"]:
                return max(b["o"], pos["stop"]) * (1 + slip), b["t"]
            pos["last_bar_t"] = b["t"]
            continue
        if b["l"] <= pos["stop"]:
            px = min(b["o"], pos["stop"]) * (1 - slip)
            return px, b["t"]
        pos["last_bar_t"] = b["t"]
    return None, None


def exit_fee(pos, px, s):
    return pos["sz"] * px * fee_pct(pos, s) / 100
