"""binance_data.py — second price source for the sanity band. Public mirror, no key.
Used only to refuse an entry when Hyperliquid's mark and Binance's last price disagree.

A pair is a second source only while it trades. Binance keeps serving the last ticker of a pair it has halted (status
BREAK): LITUSDT and XMRUSDT froze at 0.743 and 118.7 while Hyperliquid traded them near 2.96 and 592, so every check
of LIT and XMR failed the 2% band on both sides (audit 2026-10-23 E1). The 24-hour ticker says when the pair last
traded (closeTime, which freezes when trading stops) for the same request weight as the plain price, so a price counts
only when that is within MAX_AGE_S of now. Anything else (a halted or delisted pair, a pair that has not traded for an
hour, no USDT pair at all, the mirror unreachable) is "no second source": last_price returns None, which the callers
treat as before (the band is not checked; it fails open), and why_none(coin) says which for the run record (E10).

Each coin is read at most once per TTL_S in a process (a cycle is one short process), so the leg formation and the
order checks that follow it a few seconds later share one request."""
import time
from . import common as C

MIRROR = "https://data-api.binance.vision/api/v3/ticker/24hr?symbol={pair}"
MAX_AGE_S = 3600          # the pair's last trade at most this old, or it is no second source
TTL_S = 120               # one read per coin per this many seconds in a process
NO_SOURCE = "no second source"
_SEEN = {}                # coin -> (read at, price or None, why none)


def read(coin, now=None):
    """(Binance's last price for coin/USDT, "") while the pair trades and its last trade is fresh, else (None, why)."""
    now = time.time() if now is None else now
    hit = _SEEN.get(coin)
    if hit and 0 <= now - hit[0] < TTL_S:
        return hit[1], hit[2]
    px, why = None, ""
    try:
        r = C.http_json(MIRROR.format(pair=f"{coin}USDT"), tries=2, timeout=15)
        last, age = float(r["lastPrice"]), now - float(r["closeTime"]) / 1000
        if age > MAX_AGE_S:
            why = f"Binance {coin}USDT not trading: last trade {age / 3600:.0f} h ago"
        elif not last > 0:
            why = f"Binance {coin}USDT has no last price"
        else:
            px = last
    except Exception as e:  # noqa: BLE001 — a missing second source is a data gap, not a crash
        why = (f"no Binance {coin}USDT pair" if "HTTP Error 400" in str(e)
               else f"Binance unreachable ({type(e).__name__}: {str(e)[:80]})")
    _SEEN[coin] = (now, px, why)
    return px, why


def last_price(coin):
    """Binance's last price for coin/USDT, or None when it is no second source (why_none says why)."""
    return read(coin)[0]


def why_none(coin):
    """Why the last read of coin gave no second source; NO_SOURCE when this process never read it (a caller that
    replaced last_price, as the tests and the lab's replay do)."""
    hit = _SEEN.get(coin)
    return (hit[2] or NO_SOURCE) if hit else NO_SOURCE


def forget():
    """Drop every cached read (tests)."""
    _SEEN.clear()
