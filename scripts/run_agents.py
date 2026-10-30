#!/usr/bin/env python3
"""run_agents.py — run every due agent, each in its own process with only its own keys, then push its dashboard.

Called hourly (cycle.yml cron "5 * * * *"). An agent is due when its trigger bar closed less than
DUE_WINDOW_MIN minutes ago: 4-hour agents at 00/04/08/12/16/20 UTC, 1-hour agents every hour.

Isolation: the workflow passes each secret by name (never toJSON(secrets), which GitHub flags); this script removes
them all from its own environment, and each child process receives only what it needs:
  cycle child  → EXECUTOR_AGENT, its own HL_AGENT_KEY / HL_ACCOUNT_ADDRESS, ALERT_WEBHOOK
  push child   → EXECUTOR_AGENT, EXECUTOR_ROWS_DIR, CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID
  fleet step   → CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID only
Key names: agent "core" uses HL_AGENT_KEY and HL_ACCOUNT_ADDRESS; agent "wide-4h" uses HL_AGENT_KEY_WIDE_4H and
HL_ACCOUNT_ADDRESS_WIDE_4H. No agent can see another agent's key. Only this process itself sends alerts with the webhook
(the fleet kill switch, a dashboard that stopped updating); the push and fleet children never see it.

Every child has a time limit (a cycle 15 min, a push 5 min, the fleet step 6 min), so one hung bot cannot hold up the
others; a child that runs over is stopped and counted as failed.

The fleet index (docs/COMMAND_CENTER_SPEC.md §6.5): each push child writes only its own keys and saves its exec:agents row
into a per-job rows dir; after the loop (in a `finally`, so it runs even after a failed agent) the fleet guard runs, then
ONE `dashboard_push.py --fleet <dir>` merges every row into exec:agents and rebuilds any bot whose page is behind its
state. A failed push leaves that bot's previous row, marked push_fail {since, why} (its <id>.fail.json in the rows dir),
which the page shows as "Page behind"; the fleet step reports the failure streaks that start now and this script sends
ONE alert for them (the marker lives in the KV row, since GitHub's runners keep nothing between jobs). A failed push or
fleet step makes the job exit non-zero after the fleet step. `--fleet-only` skips the loop (a FLEET_HALT-only commit).

Usage: run_agents.py [--force] [--only a,b] [--push-only] [--fleet-only] [--dry]
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import _path  # noqa: F401
from executor import common as C

DUE_WINDOW_MIN = 50
CYCLE_TIMEOUT_S, PUSH_TIMEOUT_S, FLEET_TIMEOUT_S = 15 * 60, 5 * 60, 6 * 60
TIMED_OUT = 124                                  # the exit code a child that ran over its limit is reported with
PY_BIN = os.environ.get("EXECUTOR_PY") or sys.executable
HERE = Path(__file__).resolve().parent
ALERT = {"url": None}                            # this process's own webhook, set by main() from the secrets


def secrets():
    raw = os.environ.pop("ALL_SECRETS", "") or ""
    try:
        s = json.loads(raw) if raw else {}
    except ValueError:
        s = {}
    for k in list(os.environ):            # legacy individual secrets, if a workflow still passes them
        if k.startswith(("HL_AGENT_KEY", "HL_ACCOUNT_ADDRESS", "CLOUDFLARE_", "ALERT_WEBHOOK")):
            s.setdefault(k, os.environ.pop(k))
    return s


def suffix(agent_id):
    return "" if agent_id == "core" else "_" + agent_id.upper().replace("-", "_")


def agent_settings(agent_id):
    d = C.ROOT / "config" if agent_id == "core" else C.ROOT / "agents" / agent_id
    return C.load_json(d / "settings.json") or {}


def due(agent_id, now):
    """Due inside the window after the agent's bar closes. Daily agents use their own late limit (GitHub's cron can
    slip for hours), and their cycle is idempotent, so running twice inside the window changes nothing."""
    s = agent_settings(agent_id)
    window = DUE_WINDOW_MIN
    if C.trigger_tf(s) == "1d":
        window = max(DUE_WINDOW_MIN, int((s.get("data") or {}).get("late_run_minutes", 180)))
    return (now % C.bar_seconds(s)) < window * 60


def base_env():
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "PYTHONPATH", "EXECUTOR_HOME", "SSL_CERT_FILE", "GITHUB_ACTIONS", "RUNNER_TEMP", "TMPDIR")
    return {k: v for k, v in os.environ.items() if k in keep}


def limit_of(label):
    """A child's time limit from its label: "<id> cycle", "<id> push" or "fleet push"."""
    return CYCLE_TIMEOUT_S if label.endswith(" cycle") else FLEET_TIMEOUT_S if label == "fleet push" else PUSH_TIMEOUT_S if label.endswith(" push") else None


def run(cmd, env, label):
    """One child process; a child still running after its limit (limit_of) is killed and reported as TIMED_OUT."""
    t0, timeout = time.time(), limit_of(label)
    try:
        r = subprocess.run(cmd, env=env, cwd=str(C.ROOT), timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[{label}] timed out after {timeout // 60} min: stopped, counted as failed", flush=True)
        return TIMED_OUT
    print(f"[{label}] exit {r.returncode} in {time.time() - t0:.0f}s", flush=True)
    return r.returncode


def send_alert(title, text, priority="high"):
    """One alert through the engine's alert() (with a priority when it takes one), else notify(). The webhook is put in
    this process's environment only for the call: no child is running by then, and none ever inherits it."""
    url, old = ALERT["url"], os.environ.get("ALERT_WEBHOOK")
    if url:
        os.environ["ALERT_WEBHOOK"] = url
    try:
        f = getattr(C, "alert", None)
        if not callable(f):
            return C.notify(title, text)
        for kw in ({"priority": priority, "title": title}, {"priority": priority}, {}):   # whatever this engine's alert() takes
            try:
                return f(text if "title" in kw else f"{title}: {text}", **kw)
            except TypeError:
                continue
        return False
    finally:
        if old is None:
            os.environ.pop("ALERT_WEBHOOK", None)
        else:
            os.environ["ALERT_WEBHOOK"] = old


def main(argv):
    force, dry, push_only, fleet_only = "--force" in argv, "--dry" in argv, "--push-only" in argv, "--fleet-only" in argv
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    S = secrets()
    ALERT["url"] = S.get("ALERT_WEBHOOK")
    now = int(time.time())
    failed, push_failed, fleet = [], {}, {"code": None, "res": None}
    rows_dir = tempfile.mkdtemp(prefix="exec-rows-", dir=os.environ.get("RUNNER_TEMP") or None)
    try:
        if not fleet_only:
            agents_loop(S, now, force, dry, push_only, only, failed, rows_dir, push_failed)
    finally:
        try:
            if not dry:
                try:
                    fleet_guard()              # before the fleet write, so a fresh halt is in it
                finally:
                    fleet["code"] = fleet_push(S, rows_dir)
                    fleet["res"] = C.load_json(Path(rows_dir) / "_fleet.json")
        finally:
            shutil.rmtree(rows_dir, ignore_errors=True)
    push_alerts(push_failed, fleet["code"], fleet["res"])
    if failed:
        print("failed agents: " + ", ".join(failed), flush=True)
    if push_failed:
        print("dashboard push failed: " + "; ".join(f"{a} ({w})" for a, w in sorted(push_failed.items())), flush=True)
    if failed or push_failed or fleet["code"] not in (None, 0):
        sys.exit(1)


def cf_env(S):
    env = base_env()
    env.update({"CLOUDFLARE_API_TOKEN": S["CLOUDFLARE_API_TOKEN"], "CLOUDFLARE_ACCOUNT_ID": S["CLOUDFLARE_ACCOUNT_ID"]})
    return env


def fleet_push(S, rows_dir):
    """One exec:agents write per job: the rows the push children saved, the push failures, the bots whose page is behind,
    plus the fleet kill switch and the host beat. None when skipped (no Cloudflare secrets), else the exit code."""
    if not (S.get("CLOUDFLARE_API_TOKEN") and S.get("CLOUDFLARE_ACCOUNT_ID")):
        print("no Cloudflare secrets: fleet not pushed", flush=True)
        return None
    alerts = ["--alerts"] if S.get("ALERT_WEBHOOK") else []           # this job can tell the owner: a new failure counts as told
    code = run([PY_BIN, str(HERE / "dashboard_push.py"), "--fleet", rows_dir] + alerts, cf_env(S), "fleet push")
    if code:
        print("fleet push failed (the cycles and the agents' own pages are unaffected)", flush=True)
    return code


def bot_name(aid):
    return next((a.get("name") or aid for a in C.agents() if a.get("id") == aid), aid)


def push_alerts(push_failed, code, res):
    """D1: one alert per failure streak. The fleet step marks each failing bot's row (push_fail.since) and reports only
    the streaks that start in this job. When the fleet step itself failed, nothing could be marked, so this job sends
    one alert of its own (an outage repeats it at most once per sync job)."""
    if code is None:                                   # nothing was pushed (no Cloudflare secrets, or --dry)
        return
    tail = " The bots keep running and trading; only the dashboard is behind."
    if code == 0 and isinstance(res, dict) and res.get("ok"):
        new = res.get("new_fail") or {}
        if new:
            send_alert("Executor: dashboard not updating", "; ".join(f"{bot_name(a)}'s page stopped updating ({w})" for a, w in sorted(new.items()))
                       + "." + tail + " Sent once; the page says when it recovers.")
        return
    if code == 0 and not push_failed:                  # the fleet step ran but left no report: nothing is known to be wrong
        return
    why = (res or {}).get("why") if isinstance(res, dict) else None
    behind = ", ".join(bot_name(a) for a in sorted(push_failed))
    send_alert("Executor: dashboard update failed", (why or ("the fleet step timed out" if code == TIMED_OUT else f"the fleet step exited {code}"))
               + (f"; pages not updated: {behind}" if behind else "") + "." + tail)


def push_fail_why(rows_dir, aid, code):
    """The push child's own words (<id>.fail.json) when it left them, else what this process saw; written back so the
    fleet step always finds one."""
    f = Path(rows_dir) / f"{aid}.fail.json"
    d = C.load_json(f)
    if isinstance(d, dict) and isinstance(d.get("why"), str) and d["why"]:
        return d["why"]
    why = f"timed out after {PUSH_TIMEOUT_S // 60} min" if code == TIMED_OUT else f"push exited {code}"
    try:
        f.write_text(json.dumps({"v": 1, "why": why}))
    except OSError:
        pass
    return why


def agents_loop(S, now, force, dry, push_only, only, failed, rows_dir, push_failed=None):
    push_failed = push_failed if push_failed is not None else {}
    for a in C.agents():
        aid = a["id"]
        if not a.get("enabled", True) or (only and aid not in only):
            continue
        try:
            is_due = force or push_only or due(aid, now)
        except Exception as e:  # noqa: BLE001 — one bot's unusable settings must not stop the others (audit 2026-10-23)
            print(f"[{aid}] settings unusable, skipped: {type(e).__name__}: {str(e)[:200]}", flush=True)
            failed.append(aid)
            continue
        if not is_due:
            print(f"[{aid}] not due ({C.trigger_tf(agent_settings(aid))} bars)", flush=True)
            continue
        if not push_only:
            env = base_env()
            env["EXECUTOR_AGENT"] = aid
            for name in ("HL_AGENT_KEY", "HL_ACCOUNT_ADDRESS"):
                v = S.get(name + suffix(aid))
                if v:
                    env[name] = v
            if S.get("ALERT_WEBHOOK"):
                env["ALERT_WEBHOOK"] = S["ALERT_WEBHOOK"]
            code = run([PY_BIN, str(HERE / "run_cycle.py")] + (["--dry"] if dry else []), env, aid + " cycle")
            if code:
                failed.append(aid)
        if dry:
            continue
        if S.get("CLOUDFLARE_API_TOKEN") and S.get("CLOUDFLARE_ACCOUNT_ID"):
            env = cf_env(S)
            env.update({"EXECUTOR_AGENT": aid, "EXECUTOR_ROWS_DIR": rows_dir})
            code = run([PY_BIN, str(HERE / "dashboard_push.py")], env, aid + " push")
            if code:
                push_failed[aid] = push_fail_why(rows_dir, aid, code)
                print(f"[{aid}] dashboard push failed: {push_failed[aid]} (the cycle itself is unaffected)", flush=True)
        else:
            print(f"[{aid}] no Cloudflare secrets: dashboard not pushed", flush=True)


def fleet_guard():
    """The fleet kill switch's automatic trigger: when the LIVE agents together are down more than
    agents/fleet.json max_live_dd_pct from their peaks, set state/FLEET_HALT (no agent enters; exits still run).
    Fleet drawdown = 1 - sum(current equity) / sum(each agent's own peak), which never understates the real one."""
    f = C.fleet()
    lim = f.get("max_live_dd_pct")
    if not lim or C.FLEET_HALT.exists():
        return None
    cur = peak = 0.0
    for a in C.agents():
        if not a.get("enabled", True):
            continue
        st = C.ROOT / "state" if a["id"] == "core" else C.ROOT / "state" / "agents" / a["id"]
        pts = [p for p in C.read_jsonl(st / "ledger" / "equity.jsonl") if p.get("mode") == "live" and p.get("equity")]
        if pts:
            cur += pts[-1]["equity"]
            peak += max(p["equity"] for p in pts)
    if peak <= 0:
        return None
    dd = (1 - cur / peak) * 100
    print(f"fleet (live): drawdown {dd:.1f}% (limit {lim}%)", flush=True)
    if dd > float(lim):
        C.FLEET_HALT.parent.mkdir(parents=True, exist_ok=True)
        C.FLEET_HALT.write_text(f"fleet drawdown {dd:.1f}% beyond {lim}%")
        C.FLEET_HALT.with_name("FLEET_HALT.since").write_text(C.iso())
        # secrets() took ALERT_WEBHOOK out of this process's environment, so a bare notify() here never reached the phone
        send_alert("Executor: FLEET HALTED", f"live agents together are down {dd:.1f}% (limit {lim}%); no agent enters, exits still run. "
                                             "Resume with the control workflow (fleet-resume) once reviewed.", "urgent")
    return dd


if __name__ == "__main__":
    main(sys.argv[1:])
