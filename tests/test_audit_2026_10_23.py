"""Fixes from the 2026-10-23 audit (docs/audits/2026-10-23-audit.md) on the server's request and fleet loops:
one bot's unusable settings no longer stop the other bots' cycles, and a flatten or approval that times out is
recorded as failed and alerted instead of crashing the request loop and re-running every tick."""
import subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
import _path  # noqa: F401
from executor import common as C

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_agents as RA  # noqa: E402
import run_requests as RR  # noqa: E402


class OneBadBotDoesNotStopTheFleet(unittest.TestCase):
    def test_unusable_settings_skip_only_that_bot(self):
        def due(aid, now):
            if aid == "bad":
                raise RuntimeError("trigger_tf '2h' not supported")
            return False
        seen = []
        agents = [{"id": "bad", "enabled": True}, {"id": "good", "enabled": True}]
        failed = []
        with mock.patch.object(RA.C, "agents", lambda: agents), mock.patch.object(RA, "due", due), \
             mock.patch.object(RA, "agent_settings", lambda aid: seen.append(aid) or {}), \
             mock.patch.object(RA.C, "trigger_tf", lambda s: "1h"):
            RA.agents_loop({}, 0, False, True, False, None, failed, tempfile.mkdtemp())
        self.assertEqual(failed, ["bad"])          # counted as failed, so the job still exits non-zero and alerts
        self.assertEqual(seen, ["good"])           # the next bot was still evaluated


class TimedOutRequestIsRecorded(unittest.TestCase):
    def test_timeout_returns_a_failure_instead_of_raising(self):
        def hang(*a, **k):      # a real timeout hands back the captured output as bytes, even with text=True
            raise subprocess.TimeoutExpired(cmd="control.py", timeout=600, output=b"  ETH: closed on manual flatten\n",
                                            stderr=None)
        with mock.patch.object(RR.subprocess, "run", hang):
            code, out = RR.run({"agent": "core", "action": "flatten"})
        self.assertEqual(code, 124)
        self.assertIn("ETH: closed on manual flatten", out)     # what was already closed is kept for the owner
        self.assertIn("timed out after 10 min", out)

    def test_a_real_timeout_keeps_the_childs_output(self):
        # end to end with a real child process and a real 1 s timeout (no mock of the timeout itself)
        real = subprocess.run
        def short(cmd, **k):
            k["timeout"] = 1
            return real([sys.executable, "-c", "import time; print('  SOL: closed on manual flatten', flush=True); time.sleep(5)"], **k)
        with mock.patch.object(RR.subprocess, "run", short):
            code, out = RR.run({"agent": "core", "action": "flatten"})
        self.assertEqual(code, 124)
        self.assertIn("SOL: closed on manual flatten", out)

    def test_the_request_moves_to_done_and_alerts_urgently(self):
        home = Path(tempfile.mkdtemp())
        req, done = home / "requests", home / "requests" / "done"
        req.mkdir(parents=True)
        (req / "20261023T000000Z-flatten-core.json").write_text('{"agent": "core", "action": "flatten"}')
        sent = []
        with mock.patch.object(RR, "REQ", req), mock.patch.object(RR, "DONE", done), \
             mock.patch.object(RR, "run", lambda doc: (124, "timed out")), \
             mock.patch.object(RR.C, "notify", lambda title, text, priority="default": sent.append((title, priority))):
            RR.main()
        self.assertEqual(list(req.glob("*.json")), [])
        self.assertEqual(len(list(done.glob("*.json"))), 1)
        self.assertEqual(sent, [("Executor: request FAILED", "urgent")])


if __name__ == "__main__":
    unittest.main()
