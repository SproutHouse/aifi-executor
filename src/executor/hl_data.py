"""hl_data.py — read-only Hyperliquid info API, standard library only.

Everything here is public data and needs no key. Candles come from Hyperliquid
itself so the executor prices what it trades; weekly bars are aggregated from
daily bars Monday-anchored to match the TradingView charts the desk uses (Hyperliquid's
native 1w candle is Thursday-anchored).
"""
import time
from . import common as C

API = "https://api.hyperliquid.xyz/info"
INTERVAL_SECONDS = {"4h": 4 * 3600, "1d": 86400}


_last_call = [0.0]
MIN_GAP = 0.35          # seconds between info calls: ~170/min keeps far under Hyperliquid's weight limit


def info(body):
    import time as _t
    gap = _t.time() - _last_call[0]
    if gap < MIN_GAP:
        _t.sleep(MIN_GAP - gap)
    _last_call[0] = _t.time()
    return C.http_json(API, body)


def meta_and_ctxs(dexes=()):
    """{coin: {szDecimals, maxLeverage, dayNtlVlm, openInterest, funding, markPx, oraclePx, midPx, ...}}.
    dexes: builder-deployed perp exchanges (HIP-3, e.g. "xyz") to include; their coins are named "xyz:SP500"."""
    out = {}
    for dex in [None] + sorted(set(dexes or ())):
        meta, ctxs = info({"type": "metaAndAssetCtxs", "dex": dex} if dex else {"type": "metaAndAssetCtxs"})
        for i, u in enumerate(meta["universe"]):
            if u.get("isDelisted"):
                continue
            row = dict(u)
            row.update(ctxs[i] if i < len(ctxs) else {})
            out[u["name"]] = row
    return out


def is_builder(coin):
    """A builder-market (HIP-3) coin: "dex:NAME". These are stock indices, commodities and stocks."""
    return ":" in coin


def weekdays(bars):
    """Builder-market perps trade all week but their underlying does not: the lab backtests on the underlying's
    weekday history, so the engine reads weekday bars only for these coins (same calendar on both sides)."""
    import datetime as _dt
    return [b for b in bars if _dt.datetime.fromtimestamp(b["t"], tz=_dt.timezone.utc).weekday() < 5]


def candles(coin, interval, days, completed_only=True):
    """Bars as {t, o, h, l, c, v} with t in seconds, ascending. The forming bar is dropped
    when completed_only, judged by the bar's close time against the clock."""
    now_ms = int(time.time() * 1000)
    raw = info({"type": "candleSnapshot", "req": {"coin": coin, "interval": interval,
                                                  "startTime": now_ms - days * 86400000, "endTime": now_ms}})
    bars = []
    for r in raw:
        if completed_only and int(r["T"]) >= now_ms:
            continue
        bars.append({"t": int(r["t"]) // 1000, "T": int(r["T"]) // 1000, "o": float(r["o"]), "h": float(r["h"]),
                     "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    bars.sort(key=lambda b: b["t"])
    return bars


def all_mids():
    return {k: float(v) for k, v in info({"type": "allMids"}).items()}


def l2(coin):
    return info({"type": "l2Book", "coin": coin})


def user_state(address):
    return info({"type": "clearinghouseState", "user": address})


def frontend_open_orders(address):
    return info({"type": "frontendOpenOrders", "user": address})


def user_fills(address):
    return info({"type": "userFills", "user": address})


def funding_annual_pct(ctx):
    """Hyperliquid quotes funding per hour; longs pay when positive."""
    try:
        return float(ctx.get("funding", 0.0)) * 24 * 365 * 100
    except (TypeError, ValueError):
        return None


def notional_oi_usd(ctx):
    try:
        return float(ctx["openInterest"]) * float(ctx["markPx"])
    except (KeyError, TypeError, ValueError):
        return None


def round_sz(sz, sz_decimals):
    """Floor a size to the exchange's step (toward zero: never more than asked). In floating point 0.29 × 100 is
    28.999999999999996, so a bare floor turned an exact 0.29 into 0.28 (about 3% of exact sizes lost a step). A
    tolerance of a billionth of a step (plus 1e-12 relative, for big sizes) absorbs that error; it can never round a
    real shortfall up, since nothing tradable is that close below a step."""
    import math
    q = 10 ** int(sz_decimals)
    n = abs(sz) * q
    k = math.floor(n + 1e-9 + n * 1e-12)
    return math.copysign(k / q, sz) if k else 0.0


def round_px(px, sz_decimals, max_decimals=6):
    """Hyperliquid perps: at most 5 significant figures and at most (6 - szDecimals) decimals."""
    if px <= 0:
        return px
    import math
    sig = 5
    mag = math.floor(math.log10(px))
    dec_sig = max(0, sig - 1 - mag)
    dec = min(dec_sig, max_decimals - int(sz_decimals))
    return round(px, dec)


def spot_pairs():
    """Perp coin → its USDC spot pair: {"BTC": {"pair": "@142", "token": "UBTC", "szd": 5, "vol": 24h notional,
    "mid": mid price, "mark": the spot mark price}} (the most liquid USDC pair when a coin has several).
    Unit-bridged tokens carry a U prefix (UBTC); native tokens do not (HYPE)."""
    sm, ctxs = info({"type": "spotMetaAndAssetCtxs"})
    tok = {t["index"]: t for t in sm["tokens"]}
    byname = {c.get("coin"): c for c in ctxs}
    out = {}
    for u in sm["universe"]:
        base, quote = tok[u["tokens"][0]], tok[u["tokens"][1]]
        if quote["name"] != "USDC":
            continue
        name = base["name"]
        coin = name[1:] if name.startswith("U") and len(name) > 2 else name
        c = byname.get(u["name"], {})
        row = {"pair": u["name"], "token": name, "szd": int(base.get("szDecimals", 2)),
               "vol": float(c.get("dayNtlVlm") or 0), "mid": float(c["midPx"]) if c.get("midPx") else None,
               "mark": float(c["markPx"]) if c.get("markPx") else None}
        if coin not in out or row["vol"] > out[coin]["vol"]:
            out[coin] = row
    return out


def funding_history(coin, start_ms):
    return info({"type": "fundingHistory", "coin": coin, "startTime": int(start_ms)})


def round_spot_px(px, sz_decimals):
    return round_px(px, sz_decimals, max_decimals=8)
