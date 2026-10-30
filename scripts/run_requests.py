#!/usr/bin/env python3
"""run_requests.py — executes the order-placing controls on the cycle host (config/host.json = alwaysdata).

When the executor runs on its own server, the GitHub control and approve workflows do not place orders from GitHub's
US machines: they commit a request file state/requests/<time>-<action>-<agent>.json and the server's `requests` task
(every 5 minutes) runs it here, with only that agent's key, then moves the file to state/requests/done/ with the
result. Actions: flatten (close everything and halt) and approve (execute a pending proposal). Unknown or malformed
requests are refused and recorded, never guessed at.
"""
import json, os, re, subprocess, sys, time
import _path  # noqa: F401
from executor import common as C

REQ = C.ROOT / "state" / "requests"
DONE = REQ / "done"
HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.environ.get("EXECUTOR_PY") or sys.executable


def run(doc):
    agent, action = doc.get("agent", "core"), doc.get("action")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,23}", agent or ""):
        return 2, "invalid agent id"
    if agent != "core" and agent not in {a["id"] for a in C.agents()}:
        return 2, f"no agent {agent}"
    if action == "flatten":
        args = [os.path.join(HERE, "control.py"), "--flatten"]
    elif action == "approve":
        if any(a.get("id") == agent and a.get("shadow") for a in C.agents()):
            return 2, f"{agent} is a shadow experiment (paper only): approvals are refused"
        pid = str(doc.get("proposal_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", pid):
            return 2, "invalid proposal id"
        args = [os.path.join(HERE, "approve.py"), "--id", pid, "--confirm", "yes"]
    else:
        return 2, f"unknown action {action!r}"
    env = dict(os.environ, EXECUTOR_AGENT=agent)
    try:
        r = subprocess.run([PY, os.path.join(HERE, "with_agent_keys.py"), PY] + args, env=env, cwd=str(C.ROOT),
                           capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as e:   # recorded as failed and alerted, never left pending to re-run every tick
        # the lines already printed say which positions were closed before the kill; a timeout hands them back as bytes
        text = lambda b: b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")
        out = text(e.stdout) + text(e.stderr)
        return 124, (out + "\ntimed out after 10 min and stopped: check the positions and re-file if needed")[-1500:]
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def main():
    DONE.mkdir(parents=True, exist_ok=True)
    for f in sorted(REQ.glob("*.json")):
        try:
            doc = json.loads(f.read_text())
        except ValueError:
            doc = {}
        t0 = time.time()
        code, out = run(doc)
        doc.update({"done_at": C.iso(), "exit": code, "output": out, "secs": round(time.time() - t0, 1), "host": C.host()})
        C.write_json(DONE / f.name, doc)
        f.unlink()
        # the owner filed it and waits for it: done is a plain notice; a failed flatten or approval needs acting on now
        C.notify("Executor: request " + ("done" if code == 0 else "FAILED"), f"{doc.get('action')} {doc.get('agent')} (exit {code})",
                 "default" if code == 0 else "urgent")
        print(f"{f.name}: exit {code}")


if __name__ == "__main__":
    main()
