import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from telecom_research import Store, WorkflowError
from telecom_research.runtime import Supervisor, materialize
from telecom_research.store import SCORES, digest


def report(decision="pass"):
    return {"decision": decision, "scores": {key: 8 for key in SCORES}, "confidence": 0.8,
            "rationale": "Synthetic test fixture, not an actual scientific review.", "blockers": [],
            "search_evidence": [{"query": "synthetic fixture", "source": "synthetic fixture",
                "url": "https://example.invalid/synthetic-test", "accessed_at": "2026-11-03T00:00:00Z",
                "finding": "Synthetic fixture only; no Internet search performed."}]}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
        self.store.initialize()
        self.manager = (self.store.state / "manager.token").read_text()
        self.project = self.store.create_project(self.manager, "Synthetic OFDM workflow", synthetic=True)
        self.author = self.runtime("research")

    def tearDown(self):
        self.temp.cleanup()

    def runtime(self, role, submission=None):
        runtime = self.store.create_runtime(self.manager, self.project["id"], role, submission)
        runtime["token"] = Path(runtime["token_file"]).read_text()
        return runtime

    def draft(self, suffix=""):
        return self.store.submit(self.author["token"], "draft", "Synthetic manuscript " + suffix,
                                 "Synthetic bibliography and nearest-work comparison.", "Synthetic experiment plan.")

    def approved(self):
        draft = self.draft()
        reviewer = self.runtime("review", draft["id"])
        self.store.review(reviewer["token"], report())
        return draft, self.runtime("execution")

    def results(self, execution):
        run = self.store.experiment_submit(execution["token"], {"kind": "simulation", "name": "Synthetic simulation request",
            "code_revision": "synthetic-revision", "config": {"snr_db": [0, 5, 10], "seed": 42}})
        artifact = self.root / "synthetic-metrics.json"
        artifact.write_text('{"synthetic":true,"ber":0.125}')
        result = {"origin": "synthetic", "source": "Synthetic fixture; no experiment executed", "code_revision": "synthetic-revision",
            "config_hash": run["config_hash"], "metrics": {"ber": 0.125},
            "artifacts": [{"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}]}
        return self.store.import_result(self.manager, run["id"], result)

    def test_full_cycle_and_final_revision(self):
        draft, execution = self.approved()
        self.assertIn("experiment_submit", self.store.tools(execution["token"]))
        self.assertEqual(self.store.execution_context(execution["token"])["approved_draft"]["id"], draft["id"])
        run = self.results(execution)
        final = self.store.submit(execution["token"], "final", "Synthetic complete paper", "Evidence", "Plan")
        reviewer1 = self.runtime("review", final["id"])
        reviewer2 = self.runtime("review", final["id"])
        context = self.store.review_context(reviewer1["token"])
        self.assertEqual(context["experiment_results"][0]["id"], run["id"])
        self.store.review(reviewer1["token"], report())
        self.assertEqual(self.store.status(self.manager, self.project["id"])["project"]["status"], "final_review")
        revision = report("revise")
        revision["blockers"] = ["Synthetic baseline issue"]
        self.store.review(reviewer2["token"], revision)
        self.assertEqual(self.store.status(self.manager, self.project["id"])["project"]["status"], "final_revision_required")
        next_final = self.store.submit(execution["token"], "final", "Synthetic revised paper", "Evidence", "Plan")
        self.assertNotEqual(next_final["id"], final["id"])
        with self.assertRaises(WorkflowError):
            self.store.review_context(reviewer1["token"])
        for _ in range(2):
            reviewer = self.runtime("review", next_final["id"])
            self.store.review(reviewer["token"], report())
        self.assertEqual(self.store.status(self.manager, self.project["id"])["project"]["status"], "complete")

    def test_author_cannot_approve_or_create_execution(self):
        draft = self.draft()
        for action in (lambda: self.store.review(self.author["token"], report()),
                       lambda: self.store.create_runtime(self.author["token"], self.project["id"], "execution"),
                       lambda: self.store.create_runtime(self.manager, self.project["id"], "execution"),
                       lambda: self.store.call(self.author["token"], "experiment_submit", {"spec": {}})):
            with self.assertRaises(WorkflowError):
                action()
        self.assertEqual(self.store.tools(self.author["token"]), ["project_status", "research_context", "submission_submit"])

    def test_all_assigned_draft_reviews_required_and_late_assignment_revokes(self):
        draft = self.draft()
        one = self.runtime("review", draft["id"])
        two = self.runtime("review", draft["id"])
        self.store.review(one["token"], report())
        with self.assertRaises(WorkflowError):
            self.runtime("execution")
        self.store.review(two["token"], report())
        execution = self.runtime("execution")
        late = self.runtime("review", draft["id"])
        self.assertEqual(self.store.status(self.manager, self.project["id"])["project"]["status"], "draft_review")
        self.assertNotIn("experiment_submit", self.store.tools(execution["token"]))
        self.store.review(late["token"], report())
        self.assertIn("experiment_submit", self.store.tools(execution["token"]))

    def test_review_independence_and_immutability(self):
        draft = self.draft()
        one = self.runtime("review", draft["id"])
        two = self.runtime("review", draft["id"])
        self.store.review(one["token"], report())
        self.assertEqual(self.store.status(two["token"])["reviews"], [])
        self.assertNotIn("author", self.store.review_context(two["token"]))
        with self.assertRaises(WorkflowError):
            self.store.review(one["token"], report("revise"))

    def test_new_draft_revokes_existing_execution_calls(self):
        draft, execution = self.approved()
        first = self.store.execution_context(execution["token"])["approved_draft"]
        self.draft("second")
        self.assertEqual(self.store.tools(execution["token"]), ["project_status"])
        with self.assertRaises(WorkflowError):
            self.store.execution_context(execution["token"])
        with self.assertRaises(WorkflowError):
            self.store.call(execution["token"], "paper_submit", {"manuscript": "x", "evidence": "x", "plan": "x"})
        self.assertEqual(first["id"], draft["id"])

    def test_report_validation_and_insufficient_without_search(self):
        draft = self.draft()
        reviewer = self.runtime("review", draft["id"])
        bad_reports = []
        bad = report(); bad["scores"]["theory"] = float("nan"); bad_reports.append(bad)
        bad = report(); bad["scores"]["theory"] = True; bad_reports.append(bad)
        bad = report(); bad["decision"] = "approved"; bad_reports.append(bad)
        bad = report(); bad["search_evidence"] = []; bad_reports.append(bad)
        bad = report(); bad["blockers"] = ["unresolved"]; bad_reports.append(bad)
        for bad in bad_reports:
            with self.assertRaises(WorkflowError):
                self.store.review(reviewer["token"], bad)
        insufficient = report("insufficient")
        insufficient["scores"] = {key: None for key in SCORES}
        insufficient["search_evidence"] = []
        insufficient["rationale"] = "Literature service unavailable; cannot verify novelty."
        self.store.review(reviewer["token"], insufficient)
        resumed = self.runtime("research")
        resumed_context = self.store.research_context(resumed["token"])
        self.assertEqual(resumed_context["current_draft"]["id"], draft["id"])
        self.assertEqual(resumed_context["feedback"][0]["report"]["decision"], "insufficient")
        with self.assertRaises(WorkflowError):
            self.runtime("execution")

    def test_cross_project_and_role_spoof(self):
        other = self.store.create_project(self.manager, "Other project")
        with self.assertRaises(WorkflowError):
            self.store.status(self.author["token"], other["id"])
        with self.assertRaises(WorkflowError):
            self.store.call(self.author["token"], "submission_submit", {"role": "manager", "manuscript": "x", "evidence": "x", "plan": "x"})
        with self.assertRaises(WorkflowError):
            self.store.tools(self.manager)

    def test_hardware_requires_exact_configuration_and_lease(self):
        _, execution = self.approved()
        approved = {"operator_approved": True, "frequency_hz": 1000000000, "gain_db": 0, "sample_rate": 1000000}
        device = self.store.register_device(self.manager, "synthetic-usrp", approved)
        spec = {"kind": "hardware", "name": "Synthetic hardware request", "code_revision": "fixture",
                "config": {"algorithm": "fixture"}, "device_id": device["id"], "device_config_hash": device["config_hash"], "hardware_config": approved}
        with self.assertRaises(WorkflowError):
            self.store.experiment_submit(execution["token"], spec)
        self.store.lease_device(self.manager, device["id"], execution["id"])
        with self.assertRaises(WorkflowError):
            self.store.lease_device(self.manager, device["id"], execution["id"])
        bad = copy.deepcopy(spec); bad["hardware_config"]["gain_db"] = 70
        with self.assertRaises(WorkflowError):
            self.store.experiment_submit(execution["token"], bad)
        run = self.store.experiment_submit(execution["token"], spec)
        self.assertEqual(run["status"], "pending_unconfigured")

    def test_result_snapshots_detect_tamper(self):
        _, execution = self.approved()
        run = self.results(execution)
        Path(run["result"]["artifacts"][0]["snapshot"]).write_text("tampered")
        with self.assertRaises(WorkflowError):
            self.store.submit(execution["token"], "final", "x", "x", "x")

    def test_no_final_without_results_and_no_synthetic_in_real_project(self):
        _, execution = self.approved()
        with self.assertRaises(WorkflowError):
            self.store.submit(execution["token"], "final", "x", "x", "x")
        real = self.store.create_project(self.manager, "Real project")
        author = self.store.create_runtime(self.manager, real["id"], "research")
        author_token = Path(author["token_file"]).read_text()
        submitted = self.store.submit(author_token, "draft", "x", "x", "x")
        reviewer = self.store.create_runtime(self.manager, real["id"], "review", submitted["id"])
        self.store.review(Path(reviewer["token_file"]).read_text(), report())
        runner = self.store.create_runtime(self.manager, real["id"], "execution")
        with self.assertRaises(WorkflowError):
            self.results(dict(runner, token=Path(runner["token_file"]).read_text()))

    def test_materialization_and_fake_supervisor(self):
        profiles = Path(__file__).resolve().parents[1] / "profiles"
        research_dir = self.root / "research-runtime"
        plan = materialize(self.store, self.manager, self.author["id"], "claude", research_dir, profiles)
        self.assertTrue((research_dir / ".claude" / "skills" / "telecom-research" / "SKILL.md").is_file())
        self.assertFalse((research_dir / ".claude" / "skills" / "telecom-paper").exists())
        self.assertFalse((research_dir / ".claude" / "skills" / "telecom-review").exists())
        self.assertNotIn("--safe-mode", plan["argv"])
        draft = self.draft()
        reviewer = self.runtime("review", draft["id"])
        review_dir = self.root / "review-runtime"
        materialize(self.store, self.manager, reviewer["id"], "codex", review_dir, profiles)
        self.assertTrue((review_dir / ".agents" / "skills" / "telecom-review" / "SKILL.md").is_file())
        self.assertFalse((review_dir / ".agents" / "skills" / "telecom-paper").exists())
        self.assertNotEqual(reviewer["session_id"], self.author["session_id"])
        self.assertFalse((review_dir / "manuscript.md").exists())
        supervisor = Supervisor(self.store, self.manager)
        result = supervisor.start(self.author["id"], [sys.executable, "-c", "print('fake-harness-fixture')"], wait=True)
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("fake-harness-fixture", Path(result["log"]).read_text())
        started = supervisor.start(self.author["id"], [sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertEqual(started["status"], "running")
        with self.assertRaises(WorkflowError):
            supervisor.start(self.author["id"], [sys.executable, "-c", "pass"])
        stopped = supervisor.stop(self.author["id"])
        self.assertTrue(stopped["stop_requested"])
        for _ in range(100):
            if supervisor.status(self.author["id"])["status"] == "exited":
                break
            time.sleep(0.01)
        self.assertEqual(supervisor.status(self.author["id"])["status"], "exited")

    def test_supervisor_stops_descendant_process(self):
        profiles = Path(__file__).resolve().parents[1] / "profiles"
        materialize(self.store, self.manager, self.author["id"], "claude", self.root / "tree-runtime", profiles)
        heartbeat = self.root / "heartbeat.txt"
        child_code = "import pathlib,time; p=pathlib.Path(" + repr(str(heartbeat)) + "); " + "\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(0.02)"
        parent_code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]); time.sleep(30)"
        supervisor = Supervisor(self.store, self.manager)
        try:
            supervisor.start(self.author["id"], [sys.executable, "-c", parent_code])
            for _ in range(100):
                if heartbeat.exists():
                    break
                time.sleep(0.02)
            self.assertTrue(heartbeat.exists(), "Fake descendant did not start")
            supervisor.stop(self.author["id"])
            time.sleep(0.1)
            content = heartbeat.read_text()
            time.sleep(0.1)
            self.assertEqual(heartbeat.read_text(), content, "Descendant survived managed runtime stop")
            for _ in range(100):
                if supervisor.status(self.author["id"])["status"] == "exited":
                    break
                time.sleep(0.01)
        finally:
            supervisor.close()

    def test_state_restart_and_cli(self):
        draft = self.draft()
        reopened = Store(self.store.state)
        self.assertEqual(reopened.status(self.manager, self.project["id"])["project"]["draft"], draft["id"])
        with self.assertRaises(WorkflowError):
            reopened.initialize()
        result = subprocess.run([sys.executable, "-m", "telecom_research", "--state", str(self.store.state), "status", "--project", self.project["id"]],
                                capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertGreater(len(reopened.audit(self.manager)), 2)

    def test_state_and_runtime_reject_entire_git_worktree(self):
        repo = self.root / "fake-worktree"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: elsewhere")
        with self.assertRaises(WorkflowError):
            Store(repo / "private-state")
        with self.assertRaises(WorkflowError):
            materialize(self.store, self.manager, self.author["id"], "claude", repo / "private-runtime", Path(__file__).resolve().parents[1] / "profiles")


if __name__ == "__main__":
    unittest.main()
