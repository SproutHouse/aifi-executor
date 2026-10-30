"""The 2026-10-16 dashboard review (package D: dashboard truth and loud failures), one class per finding.

D1 a failed push is recorded with its reason, fails the job after the fleet step and alerts once per failure streak; every
child has a time limit · D1b rows carry ran_t and push_fail ("Page behind") · D2 the fleet step replays agents whose page is
behind their state · D3 config names never block a payload, and a payload that fails the privacy check still writes an error
stamp · D5/D9 lifetime carry capture, the hedge result, closed pairs on the capital they used · D6 "1h flip but no mark
price" · D7 the fleet's paper pot from equity.jsonl · D8 a sale's % of pot · D10 the latest events go last in a row ·
D11 the usual start from the first check of each slot · D12 no "vs holding" for rebalancers · D13 stops from the last
prices · D14 invested at market · D15 drawdown from the latest point · D16 since start from the paper pot · D17 a
rotation's two actions · the lab's payload loses any money key on its way to KV. The client side of these is in
tests/client_join_check.mjs (facts.review) and tests/test_dashboard_client.py."""
import contextlib, io, json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock
import _path  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
import dashboard_push as DP  # noqa: E402
import cc_fixtures as F  # noqa: E402
import run_agents as RA  # noqa: E402

H, DAY, T0 = F.H, F.DAY, F.T0


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def run_t(t, **kw):
    return F.run_doc(t, **kw)


def tree(root, settings=None, runs=None, positions=None, trades=(), equity=None, books=None):
    s = settings or F.settings(trigger_tf="1h", data={"late_run_minutes": 35})
    runs = runs or [run_t(T0 + 6 * 60)]
    return F.write_tree(root, s, runs, positions, trades, equity if equity is not None else [(T0, 1000.0), (T0 + 600, 1000.0)], books)


class D1RunAgents(unittest.TestCase):
    """run_agents.py: a failed push is recorded with its reason, the job exits non-zero after the fleet step, and the
    streak's first failure (reported by the fleet step) sends ONE alert."""

    def go(self, argv, fail=(), fleet_result=None, fleet_code=0, why=None):
        captured, order, alerts = [], [], []

        def fake_run(cmd, env, label):
            captured.append((label, cmd, dict(env)))
            order.append(label)
            if label in fail:
                if why and label.endswith(" push") and label != "fleet push":
                    Path(env["EXECUTOR_ROWS_DIR"], label.split()[0] + ".fail.json").write_text(json.dumps({"v": 1, "why": why}))
                return RA.TIMED_OUT if why == "timeout" else 1
            if label == "fleet push":
                if fleet_result is not None:
                    Path(cmd[cmd.index("--fleet") + 1], "_fleet.json").write_text(json.dumps(fleet_result))
                return fleet_code
            return 0
        roster = [{"id": "core", "name": "Core", "enabled": True}, {"id": "fast-1h", "name": "Fast", "enabled": True}]
        os.environ["ALL_SECRETS"] = json.dumps({"CLOUDFLARE_API_TOKEN": "cf", "CLOUDFLARE_ACCOUNT_ID": "acct", "ALERT_WEBHOOK": "https://alert.invalid/x"})
        code = 0
        with mock.patch.object(RA, "run", fake_run), mock.patch.object(RA.C, "agents", lambda: roster), \
                mock.patch.object(RA, "agent_settings", lambda aid: {"trigger_tf": "1h"}), mock.patch.object(RA, "fleet_guard", lambda: None), \
                mock.patch.object(RA, "send_alert", lambda title, text, priority="high": alerts.append((title, text, priority))), quiet() as out:
            try:
                RA.main(argv)
            except SystemExit as e:
                code = e.code
        return order, code, alerts, out.getvalue()

    def test_push_failure_fails_the_job_after_the_fleet_step(self):
        order, code, alerts, out = self.go(["--push-only"], fail=("fast-1h push",), why="data check: forbidden key 'gross' at exec:latest.x",
                                           fleet_result={"ok": True, "new_fail": {"fast-1h": "data check: forbidden key 'gross' at exec:latest.x"}, "still_fail": {}})
        self.assertEqual(order, ["core push", "fast-1h push", "fleet push"])     # the fleet step still runs
        self.assertEqual(code, 1)                                                 # and the job fails after it (was 0)
        self.assertIn("dashboard push failed: fast-1h (data check: forbidden key 'gross' at exec:latest.x)", out)
        self.assertEqual(len(alerts), 1)                                          # one alert: the streak starts now
        self.assertEqual(alerts[0][0], "Executor: dashboard not updating")
        self.assertIn("Fast's page stopped updating (data check", alerts[0][1])
        self.assertEqual(alerts[0][2], "high")

    def test_a_continuing_streak_does_not_alert_again(self):
        _o, code, alerts, _ = self.go(["--push-only"], fail=("fast-1h push",), why="data check",
                                      fleet_result={"ok": True, "new_fail": {}, "still_fail": {"fast-1h": "data check"}})
        self.assertEqual((code, alerts), (1, []))

    def test_fleet_step_failure_alerts_for_the_job(self):
        _o, code, alerts, _ = self.go(["--push-only"], fail=("core push",), fleet_code=1,
                                      fleet_result={"ok": False, "why": "could not read the fleet index (exec:agents)"})
        self.assertEqual(code, 1)
        self.assertEqual([a[0] for a in alerts], ["Executor: dashboard update failed"])
        self.assertIn("could not read the fleet index (exec:agents); pages not updated: Core.", alerts[0][1])

    def test_all_good_is_silent_and_zero(self):
        order, code, alerts, _ = self.go(["--push-only"], fleet_result={"ok": True, "new_fail": {}, "still_fail": {}})
        self.assertEqual((order[-1], code, alerts), ("fleet push", 0, []))

    def test_timeout_is_a_failure_with_its_reason(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(RA.push_fail_why(d, "core", RA.TIMED_OUT), "timed out after 5 min")
            self.assertEqual(json.loads(Path(d, "core.fail.json").read_text())["why"], "timed out after 5 min")
            Path(d, "fast-1h.fail.json").write_text(json.dumps({"v": 1, "why": "Cloudflare: cloudflare 503"}))
            self.assertEqual(RA.push_fail_why(d, "fast-1h", 1), "Cloudflare: cloudflare 503")   # the child's own words win

    def test_a_hung_child_is_stopped(self):
        # a fresh copy of the module: tests/test_agents.py replaces run_agents.run for the rest of the process
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_agents_fresh", ROOT / "scripts" / "run_agents.py")
        RF = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(RF)
        self.assertEqual((RF.limit_of("core cycle"), RF.limit_of("fast-1h push"), RF.limit_of("fleet push")), (15 * 60, 5 * 60, 6 * 60))
        with mock.patch.object(RF, "limit_of", lambda label: 1), quiet() as out:
            t0 = time.time()
            code = RF.run([sys.executable, "-c", "import time; time.sleep(30)"], dict(os.environ), "slow push")
        self.assertEqual(code, RF.TIMED_OUT)
        self.assertLess(time.time() - t0, 15)
        self.assertIn("[slow push] timed out", out.getvalue())

    def test_alert_uses_the_engine_priority_when_it_takes_one(self):
        got = []
        RA.ALERT["url"] = "https://alert.invalid/x"
        try:
            with mock.patch.object(RA.C, "alert", lambda msg, priority="default", title=None: got.append((title, msg, priority, os.environ.get("ALERT_WEBHOOK"))), create=True):
                RA.send_alert("T", "text", "urgent")
            with mock.patch.object(RA.C, "alert", lambda msg, priority="default": got.append((None, msg, priority, None)), create=True):
                RA.send_alert("T", "no title", "high")                           # an alert() without a title
            with mock.patch.object(RA.C, "alert", lambda msg: got.append((None, msg, None, None)), create=True):
                RA.send_alert("T", "older", "high")                              # an alert() without priorities still works
        finally:
            RA.ALERT["url"] = None
        self.assertEqual(got, [("T", "text", "urgent", "https://alert.invalid/x"), (None, "T: no title", "high", None), (None, "T: older", None, None)])
        self.assertNotIn("ALERT_WEBHOOK", os.environ)                             # restored: never inherited by a child

    def test_the_fleet_step_knows_whether_this_job_can_alert(self):
        cmds = []
        with mock.patch.object(RA, "run", lambda cmd, env, label: cmds.append((cmd, env)) or 0), quiet():
            RA.fleet_push({"CLOUDFLARE_API_TOKEN": "cf", "CLOUDFLARE_ACCOUNT_ID": "a", "ALERT_WEBHOOK": "https://alert.invalid/x"}, "/tmp/rows")
            RA.fleet_push({"CLOUDFLARE_API_TOKEN": "cf", "CLOUDFLARE_ACCOUNT_ID": "a"}, "/tmp/rows")
        self.assertEqual([c[0][2:] for c in cmds], [["--fleet", "/tmp/rows", "--alerts"], ["--fleet", "/tmp/rows"]])
        self.assertNotIn("ALERT_WEBHOOK", cmds[0][1])                            # the flag only: the child never holds the webhook

    def test_workflow_wires_the_alert_channel(self):
        y = (ROOT / ".github" / "workflows" / "dashboard-sync.yml").read_text()
        self.assertIn("ALERT_WEBHOOK: ${{ secrets.ALERT_WEBHOOK }}", y)
        self.assertNotIn("timeout-minutes: 15", y)


class D1FleetStep(unittest.TestCase):
    """The fleet step marks push_fail on the row (since kept across jobs), reports new streaks, clears them on success."""

    ROSTER = [{"id": "core", "name": "Core", "enabled": True}, {"id": "fast-1h", "name": "Fast", "enabled": True}]

    def env(self, prev, rows, fails, now, can_alert=True):
        report = {}
        with mock.patch.object(DP.C, "agents", lambda: self.ROSTER), mock.patch.object(DP, "ran_t_of", lambda *a, **k: None), \
                mock.patch.object(DP, "fleet_paper", lambda roster: None):
            e = DP.envelope(json.dumps(prev) if prev is not None else None, rows, newest=True, fails=fails, report=report, now=now, can_alert=can_alert)
        return e, report

    def test_streak(self):
        old = {"id": "fast-1h", "name": "Fast", "gen": "2026-10-16T06:07:00.000Z", "last_t": 1792130745}
        e1, r1 = self.env({"v": 2, "agents": [old]}, [], {"fast-1h": "data check"}, 1792134000)
        row = e1["agents"][0]
        self.assertEqual(row["push_fail"], {"since": 1792134000, "why": "data check", "alerted": True})
        self.assertEqual((r1["new_fail"], r1["still_fail"]), ({"fast-1h": "data check"}, {}))
        self.assertEqual(row["last_t"], old["last_t"])                           # the old row stays: the page says it is behind
        e2, r2 = self.env(e1, [], {"fast-1h": "Cloudflare: x"}, 1792137600)
        self.assertEqual(e2["agents"][0]["push_fail"], {"since": 1792134000, "why": "Cloudflare: x", "alerted": True})   # since survives
        self.assertEqual((r2["new_fail"], r2["still_fail"]), ({}, {"fast-1h": "Cloudflare: x"}))
        fresh = dict(old, gen="2026-10-16T09:07:00.000Z")
        e3, r3 = self.env(e2, [fresh], {}, 1792141200)
        self.assertNotIn("push_fail", e3["agents"][0])
        self.assertEqual(r3["cleared"], {"fast-1h": "Cloudflare: x"})

    def test_a_streak_that_starts_without_the_alert_channel_is_told_later(self):
        # review.yml or deploy-dashboard push without ALERT_WEBHOOK: the next sync job (which has it) still alerts, once
        old = {"id": "fast-1h", "name": "Fast", "gen": "2026-10-16T06:07:00.000Z"}
        e1, r1 = self.env({"v": 2, "agents": [old]}, [], {"fast-1h": "data check"}, 1792134000, can_alert=False)
        self.assertEqual((e1["agents"][0]["push_fail"]["alerted"], list(r1["new_fail"])), (False, ["fast-1h"]))
        e2, r2 = self.env(e1, [], {"fast-1h": "data check"}, 1792137600)
        self.assertEqual((e2["agents"][0]["push_fail"], list(r2["new_fail"])), ({"since": 1792134000, "why": "data check", "alerted": True}, ["fast-1h"]))
        _e3, r3 = self.env(e2, [], {"fast-1h": "data check"}, 1792141200)
        self.assertEqual((r3["new_fail"], list(r3["still_fail"])), ({}, ["fast-1h"]))

    def test_a_bot_retired_after_its_last_push_shows_as_retired(self):
        # its row was stored while it still ran; a retired bot is never pushed again, so the roster decides (2026-10-30:
        # six retired bots sat in "Needs you" as halted or stale)
        self.ROSTER = [{"id": "core", "name": "Core", "enabled": False}, {"id": "fast-1h", "name": "Fast", "enabled": True}]
        stale = {"id": "core", "name": "Core", "gen": "2026-10-16T06:07:00.000Z", "enabled": True, "halt": True}
        e, _r = self.env({"v": 2, "agents": [stale]}, [{"id": "fast-1h", "name": "Fast", "gen": "x", "enabled": True}], {}, 1792134000)
        core = e["agents"][0]
        self.assertIs(core["enabled"], False)
        self.assertTrue(core["halt"])                                           # the rest of its record stays as it was
        self.assertEqual(e["order"], ["fast-1h"])
        self.ROSTER = [dict(self.ROSTER[0], enabled=True), self.ROSTER[1]]       # and a bot switched back on shows as on
        e2, _r = self.env(e, [], {}, 1792137600)
        self.assertIs(e2["agents"][0]["enabled"], True)

    def test_a_row_that_fails_the_privacy_check_never_freezes_the_index(self):
        bad = {"id": "core", "name": "Core", "gen": "x", "risk": {"notional": 12.5}}
        e, r = self.env({"v": 2, "agents": [bad]}, [], {}, 1792134000)
        self.assertEqual(e["agents"][0]["push_fail"]["why"], "data check: forbidden key 'notional' at exec:agents[core].risk")
        self.assertNotIn("risk", e["agents"][0])
        DP.scrub_assert(e, "exec:agents")
        self.assertEqual(list(r["new_fail"]), ["core"])

    def test_ran_t_from_the_state(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "runs").mkdir()
            (Path(d) / "runs" / "last_run.json").write_text(json.dumps({"t": "2026-10-16T09:05:40Z"}))
            self.assertEqual(DP.ran_t_of("x", d), 1792141540)
            (Path(d) / "runs" / "last_run.json").write_text(json.dumps({"t": "2026-10-16T09:05:40Z", "dry": True}))
            self.assertIsNone(DP.ran_t_of("x", d))


class D2Replay(unittest.TestCase):
    """The fleet step rebuilds every agent whose stored row was pushed before its state's newest check."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.st, self.cfg = tree(self.root / "rp", runs=[run_t(T0 + 6 * 60), run_t(T0 + H + 6 * 60)])
        self.roster = [{"id": "rp-1h", "name": "Replay", "enabled": True}, {"id": "off-1h", "name": "Off", "enabled": False}]

    def tearDown(self):
        self.tmp.cleanup()
        DP.BAR = 4 * 3600

    def replay(self, prev, rows=(), fails=None):
        with mock.patch.object(DP.C, "agents", lambda: self.roster), mock.patch.object(DP, "state_dir", lambda a: self.st), \
                mock.patch.object(DP, "config_dir", lambda a: self.cfg), quiet():
            return DP.replay_behind(json.dumps(prev) if prev else None, list(rows), fails or {}, T0 + H + 1800)

    def test_behind_is_rebuilt(self):
        ran = T0 + H + 6 * 60
        pairs, rows, fails, done = self.replay({"v": 2, "agents": [{"id": "rp-1h", "gen": DP.iso_ms(ran - 3600)}]})
        self.assertEqual(done, ["rp-1h"])
        self.assertEqual(sorted(pairs), ["exec:rp-1h:latest", "exec:rp-1h:ledger", "exec:rp-1h:stamp"])
        self.assertEqual((rows[0]["id"], rows[0]["ran_t"], rows[0]["last_t"]), ("rp-1h", ran, ran))
        self.assertEqual(fails, {})

    def test_up_to_date_pushed_or_failing_is_left_alone(self):
        ran = T0 + H + 6 * 60
        self.assertEqual(self.replay({"v": 2, "agents": [{"id": "rp-1h", "gen": DP.iso_ms(ran + 60)}]})[3], [])   # pushed after it ran
        self.assertEqual(self.replay(None, rows=[{"id": "rp-1h"}])[3], [])                                          # pushed this job
        self.assertEqual(self.replay(None, fails={"rp-1h": "x"})[3], [])                                            # failed this job

    def test_a_replay_that_cannot_be_built_is_a_push_failure(self):
        with mock.patch.object(DP, "build", side_effect=DP.ScrubError("forbidden string", "exec:latest.x")):
            pairs, rows, fails, done = self.replay(None)
        self.assertEqual((done, rows), ([], []))
        self.assertEqual(fails, {"rp-1h": "data check: forbidden string at exec:latest.x"})
        stamp = json.loads(pairs["exec:rp-1h:stamp"])
        self.assertEqual((stamp["t"], stamp["err"]), (T0 + H + 6 * 60, "data check"))

    def test_fleet_push_writes_replays_in_the_same_bulk_call(self):
        calls = []

        def fake_api(path, payload=None, method=None):
            calls.append((path, payload))
            return {"result": [{"title": DP.NAMESPACE_TITLE, "id": "ns1"}]} if path.startswith("/storage/kv/namespaces?") else {"success": True}
        stale = {"v": 2, "agents": [{"id": "rp-1h", "name": "Replay", "gen": DP.iso_ms(T0)}]}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(DP.C, "agents", lambda: self.roster), mock.patch.object(DP, "state_dir", lambda a: self.st), \
                mock.patch.object(DP, "config_dir", lambda a: self.cfg), mock.patch.object(DP, "api", fake_api), \
                mock.patch.object(DP, "kv_get_strict", lambda ns, k: json.dumps(stale)), mock.patch.object(DP, "kv_get", lambda ns, k: None), \
                mock.patch.object(DP, "factory_payload", lambda: None), quiet():
            DP.fleet_push(d)
            res = json.loads(Path(d, "_fleet.json").read_text())
        bulks = [p for path, p in calls if path.endswith("/bulk")]
        self.assertEqual(len(bulks), 1)
        self.assertEqual([x["key"] for x in bulks[0]], ["exec:agents", "exec:rp-1h:latest", "exec:rp-1h:ledger", "exec:rp-1h:stamp"])
        self.assertEqual(res["replayed"], ["rp-1h"])
        env = json.loads(bulks[0][0]["value"])
        self.assertEqual(env["agents"][0]["last_t"], T0 + H + 6 * 60)


class D3NamesAndErrorStamp(unittest.TestCase):
    def test_config_names_never_block_a_payload(self):
        for path, payload in (("exec:latest.risk.by_book", {"funding": {"used_pct": 1}, "fees": {"used_pct": 0}}),
                              ("exec:ledger.stats.book", {"gross": {"n": 1}, "margin": {"n": 2}}),
                              ("exec:ledger.stats.reason", {"funding": {"n": 1}}), ("exec:latest.books[0].why", {"fees": 2})):
            DP.scrub_assert(payload, path)                                     # names: allowed
        with self.assertRaises(AssertionError):                                # below them, money keys still fail
            DP.scrub_assert({"funding": {"notional": 5}}, "exec:latest.risk.by_book")
        with self.assertRaises(AssertionError):                                # and a name is still screened for currency
            DP.scrub_assert({"USD book": {"n": 1}}, "exec:ledger.stats.book")

    def test_a_book_named_funding_builds(self):
        books = {"books": [{"book": "funding", "benchmark": "BTC", "pot_share_pct": 50, "open_risk_cap_pct": 4, "names": ["BTC"]},
                           {"book": "gross", "benchmark": "ETH", "pot_share_pct": 50, "open_risk_cap_pct": 4, "names": ["ETH"]}]}
        pos = {"BTC": {"coin": "BTC", "side": "long", "kind": "flip", "tier": "A", "mode": "paper", "entry": 100.0, "stop": 95.0, "notional": 100.0,
                       "risk_amt": 5.0, "opened_ts": T0, "book": "funding", "mark": 101.0}}
        trade = {"coin": "ETH", "kind": "flip", "tier": "A", "mode": "paper", "opened": F.iso(T0 - 2 * H), "closed": F.iso(T0 - H), "R": 0.5,
                 "risk_amt": 5.0, "pnl": 2.5, "book": "gross", "reason": "stop", "hours": 1}
        with tempfile.TemporaryDirectory() as d:
            b = DP.build(*tree(Path(d), positions=pos, trades=[trade], books=books), T0 + 1200)
        self.assertIn("funding", b["latest"]["risk"]["by_book"])
        self.assertIn("gross", b["ledger"]["stats"]["book"])

    def test_a_refused_payload_writes_an_error_stamp_and_a_fail_file(self):
        books = {"books": [{"book": "USD majors", "benchmark": "BTC", "pot_share_pct": 100, "open_risk_cap_pct": 4, "names": ["BTC"]}]}
        with tempfile.TemporaryDirectory() as d:
            st, cfg = tree(Path(d) / "t", books=books)
            kv, rows = Path(d) / "kv.json", Path(d) / "rows"
            kv.write_text(json.dumps({"exec:latest": "{\"v\":2,\"old\":true}"}))
            with mock.patch.dict(os.environ, {"EXECUTOR_ROWS_DIR": str(rows)}), quiet() as out, self.assertRaises(SystemExit) as cm:
                DP.main(["--kv-json", str(kv), "--state", str(st), "--config", str(cfg), "--now", str(T0 + 1200)])
            self.assertEqual(cm.exception.code, 3)
            got = json.loads(kv.read_text())
            self.assertEqual(got["exec:latest"], "{\"v\":2,\"old\":true}")      # the old payload stays
            stamp = json.loads(got["exec:stamp"])
            self.assertEqual(sorted(stamp), ["err", "gen", "t", "v"])
            self.assertEqual((stamp["t"], stamp["err"]), (T0 + 6 * 60, "data check"))
            self.assertEqual(DP.read_fails(rows)["core"], "data check: forbidden key 'USD majors' at exec:latest.risk.by_book")
            self.assertNotIn("$", out.getvalue())
            self.assertIn("push failed: data check", out.getvalue())

    def test_messages_never_quote_the_offending_text(self):
        with self.assertRaises(DP.ScrubError) as cm:
            DP.scrub_assert({"a": ["the pot was $1,000"]}, "exec:latest")
        self.assertEqual(str(cm.exception), "forbidden string at exec:latest.a[0]")


class D5Carry(unittest.TestCase):
    """Lifetime capture over open AND closed pairs (old closed records: theo from their capture), the hedge result."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.b = DP.build(*F.carry_tree(Path(cls.tmp.name) / "c"), F.CARRY_NOW)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        DP.BAR = 4 * 3600

    def test_closed_record_shapes(self):
        old = {"pnl": -6.79, "fees": 0.30, "funding": -0.77, "gross": -7.26, "capture": 0.60, "risk_amt": 250.0}
        fi, fees, theo, legs, cap = DP.Bundle.closed_carry(old)
        self.assertAlmostEqual(theo, (0.77 - 0.30) / 0.60)
        self.assertEqual((fi, fees, legs, cap), (0.77, 0.30, -7.26, 250.0))
        self.assertEqual(DP.Bundle.closed_carry(dict(old, capture=None))[2], 0.0)          # capture None: theory was 0
        self.assertIsNone(DP.Bundle.closed_carry({k: v for k, v in old.items() if k != "capture"})[2])   # cannot be known
        new = {"pnl": 1.0, "fees": 0.1, "funding_income": 0.6, "theo_funding": 0.8, "spot_pnl": 0.3, "perp_pnl": 0.2, "capital": 100.0}
        self.assertEqual(DP.Bundle.closed_carry(new), (0.6, 0.1, 0.8, 0.5, 100.0))          # the engine's newer fields win

    def test_lifetime_and_hedge(self):
        cs, P, sol, E = self.b["latest"]["carry_sum"], F.CARRY_POS.values(), F.CARRY_TRADES[0], F.CARRY_EQ[-1]
        base = F.CARRY_EQ[0]
        fi = sum(p["funding_income"] for p in P) + (-sol["funding"])
        fees = sum(p["fees"] for p in P) + sol["fees"]
        self.assertEqual(cs["fund_all_pct"], round(fi / base * 100, 3))
        self.assertEqual(cs["cost_all_pct"], round(fees / base * 100, 3))
        realised = sum(p.get("spot_pnl", 0) + p.get("perp_pnl", 0) for p in P) + sol["gross"]
        self.assertIsNotNone(cs["leg_open_pct"])
        self.assertAlmostEqual(cs["leg_pct"], round(realised / base * 100 + cs["leg_open_pct"], 2), delta=0.011)
        self.assertEqual((cs["closed_n"], cs["closed_ret_pct"]), (1, round(sol["pnl"] / sol["risk_amt"] * 100, 2)))
        self.assertEqual(cs["capture_scope"], "all")
        for k in DP.ROW_CARRY_DROP:
            self.assertIn(k, cs)

    def test_open_pairs_only_when_a_closed_record_cannot_say(self):
        trades = [dict(F.CARRY_TRADES[0]), F.CARRY_TRADES[1]]
        del trades[0]["capture"]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "c"
            st, cfg = F.carry_tree(root)
            (st / "ledger" / "trades.jsonl").write_text("".join(json.dumps(x) + "\n" for x in trades))
            cs = DP.build(st, cfg, F.CARRY_NOW)["latest"]["carry_sum"]
        self.assertEqual((cs["capture_scope"], cs["capture_pct"]), ("open", cs["capture_open_pct"]))

    def test_closed_pairs_on_the_capital_they_used(self):
        # D9: Σ pnl / Σ capital, never a sum of returns on different capitals
        x = [{"pnl": -8.96, "risk_amt": 199.64}, {"pnl": 0.41, "risk_amt": 250.0}]
        self.assertAlmostEqual(sum(t["pnl"] for t in x) / sum(t["risk_amt"] for t in x) * 100, -1.9, delta=0.01)


class D6NoMark(unittest.TestCase):
    def test_hourly_flip_without_a_mark_alerts(self):
        for tf in ("1h", "1d", "4h", "daily", "weekly"):
            ev = DP.parse_line(f"LINK: {tf} flip but no mark price; position kept until the next cycle")
            self.assertEqual((ev[0], ev[1], ev[4]), ("exit_failed", "LINK", "nomark"), tf)
        self.assertEqual((DP.RSN["1h flip"], DP.RSN["4h flip"], DP.RSN["1d flip"]), ("h1", "h4", "d"))
        with tempfile.TemporaryDirectory() as d:
            L = DP.build(*tree(Path(d), runs=[run_t(T0 + 6 * 60, summary=["LINK: 1h flip but no mark price; position kept until the next cycle"],
                                                    positions=["LINK"])]), T0 + 1200)["latest"]
        a = [x for x in L["alerts"] if x["k"] == "exit_failed"]
        self.assertEqual([(x["lv"], x["c"]) for x in a], [("bad", "LINK")])
        self.assertIn("no mark price", a[0]["text"])


class D7FleetPaper(unittest.TestCase):
    def test_summed_series(self):
        # a peaks at t=200 and falls; b peaks later (t=300), after a fell: the fleet never stood at both peaks at once
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for aid, pts in (("a-1h", [(100, 1000.0), (200, 1100.0), (250, 900.0), (400, 900.0)]), ("b-1h", [(150, 999.0), (300, 1080.0), (400, 950.0)])):
                st = root / "state" / "agents" / aid
                (st / "ledger").mkdir(parents=True)
                (st / "ledger" / "equity.jsonl").write_text("".join(json.dumps({"ts": t, "equity": e, "mode": "paper"}) + "\n" for t, e in pts))
                (root / "agents" / aid).mkdir(parents=True)
                (root / "agents" / aid / "settings.json").write_text(json.dumps({"pot_usd_paper": 1000}))
            roster = [{"id": "a-1h", "enabled": True}, {"id": "b-1h", "enabled": True}, {"id": "c-1h", "enabled": False}]
            with mock.patch.object(DP.C, "ROOT", root):
                p = DP.fleet_paper(roster)
        # starts 1000 + 1000 (b's first point, 999, sits just below its 1,000 pot); the summed series: 2000, 1999, 2099,
        # 1899, 1980, 1850 → peak 2099
        self.assertEqual((p["n"], p["ret_pct"], p["since"], p["t"]), (2, round((1850 / 2000 - 1) * 100, 2), 100, 400))
        self.assertEqual((p["dd_pct"], p["dd_max_pct"]), (round((2099 - 1850) / 2099 * 100, 2), round((2099 - 1850) / 2099 * 100, 2)))
        self.assertGreater((1 - 1850 / (1100 + 1080)) * 100, p["dd_pct"] + 3)     # the lab's sum-of-peaks figure overstated it
        self.assertFalse({"peak", "start", "equity"} & set(json.dumps(p).replace('"', " ").split()))


class D8D17Act(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.b = DP.build(*F.target_tree(Path(cls.tmp.name) / "t"), F.TARGET_NOW)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        DP.BAR = 4 * 3600

    def test_a_sale_in_percent_of_pot(self):
        sold_at = T0 + 6 * 60
        trade = {"coin": "LINK", "kind": "flip", "tier": "A", "mode": "paper", "opened": F.iso(T0 - 5 * H), "closed": F.iso(T0 - 1200), "R": -1.02,
                 "risk_amt": 10.0, "pnl": -10.2, "book": "eth-defi", "reason": "1h flip", "hours": 5}
        runs = [run_t(T0 - 5 * H + 360, summary=["LINK: ENTERED LINK long [eth-defi] · flip tier A · stop 12.8 (2.81% away)"], positions=["LINK"]),
                run_t(sold_at, summary=["LINK [eth-defi]: closed on 1h flip at 13.1 → -1.02 R"])]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(DP.C, "agents", lambda: [{"id": "core", "name": "Core"}]):
            b = DP.build(*tree(Path(d), runs=runs, trades=[trade], equity=[(T0 - 6 * H, 1020.0), (T0 - 1300, 1010.0), (T0 + 600, 999.8)]), T0 + 1200)
            row = DP.agent_summary(b)
        pct = round(-10.2 / 1010.0 * 100, 2)                                     # over the pot at its close, like the ledger's pnl_pct
        sold = next(e for e in b["latest"]["events"] if e[1] == "sold")
        self.assertEqual((sold[6], sold[7], sold[9]), ("h1", -1.02, pct))           # D6 code, D8 10th column
        self.assertEqual((b["latest"]["act"]["R"], b["latest"]["act"]["pot_pct"]), (-1.02, pct))
        cols = b["ledger"]["trades"]["cols"]
        self.assertEqual(dict(zip(cols, b["ledger"]["trades"]["rows"][0]))["pnl_pct"], pct)
        self.assertEqual(row["recent"][0][9], pct)

    def test_a_rotation_shows_both_actions(self):
        runs = [run_t(F.TARGET_OPEN, summary=["LTC: ENTERED LTC long [trend] · target tier T · stop 65.1 (20.0% away)"], positions=["LTC"])]
        t = F.TARGET_OPEN + DAY
        trade = {"coin": "LTC", "kind": "target", "tier": "T", "mode": "paper", "opened": F.iso(F.TARGET_OPEN), "closed": F.iso(t), "R": -0.2,
                 "risk_amt": 24.0, "pnl": -4.8, "book": "trend", "reason": "target weight zero", "hours": 24, "rel_R": 0.3}
        runs.append(run_t(t, summary=["LTC [trend]: closed on target weight zero at 80.0 → -0.20 R · -0.50 R vs LTC",
                                      "NEAR: ENTERED NEAR long [trend] · target tier T · stop 2.33 (20.0% away)"], positions=["NEAR"]))
        pos = {"NEAR": dict(F.TARGET_POS["NEAR"], opened=F.iso(t), opened_ts=t)}
        with tempfile.TemporaryDirectory() as d:
            s = F.settings(strategy="target", trigger_tf="1d", btc_gate=False, data={"late_run_minutes": 180})
            b = DP.build(*F.write_tree(Path(d), s, runs, pos, [trade], [(F.TARGET_OPEN, 1000.0), (t + 600, 995.2)]), t + 1200)
        act = b["latest"]["act"]
        self.assertEqual(sorted([act["ty"]] + [a[0] for a in act.get("also", [])]), ["bought", "sold"])
        self.assertIn(["NEAR"] if act["ty"] == "sold" else ["LTC"], [a[1] for a in act["also"]])
        # D12: a rebalancer's trade never ships "vs holding" (its benchmark is the coin itself)
        ev = [e for e in b["latest"]["events"] if e[1] == "sold"]
        self.assertEqual([e[8] for e in ev], [None])
        cols = b["ledger"]["trades"]["cols"]
        self.assertEqual([dict(zip(cols, r))["rel_R"] for r in b["ledger"]["trades"]["rows"]], [None])
        self.assertIsNone(b["latest"]["rec"]["rel_R_avg"])
        self.assertTrue(all(r[2] is None for r in b["ledger"]["rseries"]))

    def test_market_value_stops_and_drawdown(self):
        L = self.b["latest"]
        pos = {p["c"]: p for p in L["pos"]}
        E = F.TARGET_POT * 1.005
        ltc = F.TARGET_POS["LTC"]
        self.assertEqual(pos["LTC"]["val_pct"], round(ltc["notional"] * ltc["mark"] / ltc["entry"] / E * 100, 1))   # D14
        self.assertEqual(pos["LTC"]["size_pct"], round(ltc["notional"] / E * 100, 1))
        drop = sum((p["stop"] - p["mark"]) / p["entry"] * p["notional"] - p["notional"] * (p["stop"] / p["entry"]) * 0.00045 for p in F.TARGET_POS.values())
        self.assertAlmostEqual(L["risk"]["stops_drop_pct"], drop / E * 100, delta=0.011)                            # D13
        self.assertLess(L["risk"]["stops_drop_pct"], 0)
        self.assertEqual((L["pot"]["dd_pct"], L["pot"]["dd_max_pct"]), (0, 0))                                      # D15: at its peak


class D10Rows(unittest.TestCase):
    def test_a_long_description_keeps_the_latest_events(self):
        with tempfile.TemporaryDirectory() as d:
            b = DP.build(*F.beat_tree(Path(d) / "b", F.BEAT_TOP + 40 * 60), F.BEAT_TOP + 40 * 60)
        loud = [e for e in b["latest"]["events"] if e[5] >= 2 and e[1] not in ("blocked", "board", "review")]
        with mock.patch.object(DP.C, "agents", lambda: [{"id": "beat-1h", "name": "B", "desc": "x" * 428}]), mock.patch.object(DP.C, "AGENT", "beat-1h"):
            row = DP.agent_summary(b)
        self.assertEqual(len(row["desc"]), 428)                                  # 3 KB fits it: nothing is cut
        self.assertEqual(row["recent"], loud[:DP.ROW_RECENT_N])
        self.assertEqual(row["recent_more"], max(0, len(loud) - DP.ROW_RECENT_N))
        self.assertLessEqual(len(DP.dumps(row)), DP.ROW_BUDGET)


class D11Clock(unittest.TestCase):
    def test_first_check_of_each_slot(self):
        runs = []
        for k in range(5):                                                       # a daily bot re-runs at :05 in its window
            for m in (7, 67, 127):
                runs.append(run_t(T0 + k * DAY + m * 60, late_min=m))
        s = F.settings(strategy="target", trigger_tf="1d", btc_gate=False, data={"late_run_minutes": 180})
        with tempfile.TemporaryDirectory() as d:
            ck = DP.build(*F.write_tree(Path(d), s, runs, equity=[(T0, 1000.0), (T0 + 4 * DAY + 600, 1000.0)]), T0 + 4 * DAY + 3 * H)["latest"]["clock"]
        self.assertEqual((ck["lag_med_min"], ck["lag_rng"], ck["lag_n"]), (7, [7, 7], 5))                         # was 67 (every re-run)
        self.assertEqual(ck["late_min"], 127)                                    # the last check's own lag is unchanged


class D16Base(unittest.TestCase):
    def test_since_start_from_the_paper_pot(self):
        self.assertEqual(DP.paper_base(999.36, 1000), 1000.0)                    # the first check's entry fees count
        self.assertEqual(DP.paper_base(1007.31, 1000), 1007.31)                  # above the setting: the first point
        self.assertEqual(DP.paper_base(900.0, 1000), 900.0)                      # far below (a reset): the first point
        self.assertEqual(DP.paper_base(377.19, None), 377.19)                    # live: the first point
        with tempfile.TemporaryDirectory() as d:
            s = F.settings(trigger_tf="1h", data={"late_run_minutes": 35})
            s["pot_usd_paper"] = 1000
            L = DP.build(*tree(Path(d), settings=s, equity=[(T0, 999.36), (T0 + 600, 961.68)]), T0 + 1200)["latest"]
        self.assertEqual(L["pot"]["chg_pct"], round((961.68 / 1000 - 1) * 100, 2))
        self.assertEqual(L["pot"]["dd_pct"], round((999.36 - 961.68) / 999.36 * 100, 2))


class LabPayload(unittest.TestCase):
    def test_money_keys_never_reach_kv(self):
        raw = {"v": 1, "shortlist": [{"agent": "a", "paper": {"ret_pct": 1.0, "equity": 1043.2, "pnl": 3.0}, "hypothesis": "turns $1,000 into more"}],
               "lab": {"rules": "v2", "runs": [{"start": "2026-10-16T00:00:00Z"}]}}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "factory").mkdir()
            (Path(d) / "factory" / "factory.json").write_text(json.dumps(raw))
            with mock.patch.object(DP.C, "ROOT", Path(d)), quiet() as out:
                got = json.loads(DP.factory_payload())
        self.assertEqual(got["shortlist"][0]["paper"], {"ret_pct": 1.0})
        self.assertEqual(got["shortlist"][0]["hypothesis"], "—")
        self.assertEqual(got["lab"], raw["lab"])                                 # the lab's own names (rules, start) stay
        self.assertIn("dropped 3 money field(s)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
