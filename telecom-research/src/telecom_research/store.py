"""Persistent authority for the workflow. No LLM loop, shell executor or device driver."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import time
import uuid


class WorkflowError(ValueError):
    pass


SCORES = ("novelty", "theory", "experiments", "engineering", "evidence", "presentation")


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise WorkflowError("JSON must contain only finite values") from exc


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{name} must be a nonempty string")
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def require_external(path):
    path = Path(path).resolve()
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists():
            raise WorkflowError("State and runtime directories must be outside every Git worktree")
    return path


def read_document(path):
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise WorkflowError("Submission inputs must be files smaller than 8 MiB")
    return text(path.read_text(encoding="utf-8"), path.name)


def hash_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


class Store:
    def __init__(self, state):
        self.state = require_external(state)
        source = Path(__file__).resolve().parents[2]
        if self.state == source or source in self.state.parents:
            raise WorkflowError("State must be outside the telecom-research source directory")
        self.db = self.state / "workflow.sqlite3"

    @contextmanager
    def _transaction(self):
        if not self.db.is_file():
            raise WorkflowError("Initialize the state directory first")
        connection = sqlite3.connect(self.db, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.state.mkdir(parents=True, exist_ok=True)
        token_file = self.state / "manager.token"
        if self.db.exists() or token_file.exists():
            raise WorkflowError("State is already initialized; existing authority is never replaced")
        token = secrets.token_urlsafe(40)
        token_file.write_text(token, encoding="utf-8")
        token_file.chmod(0o600)
        connection = sqlite3.connect(self.db)
        try:
            connection.executescript("""
                CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,
                  PRIMARY KEY(kind,id));
                CREATE TABLE audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,at TEXT NOT NULL,
                  actor TEXT NOT NULL,event TEXT NOT NULL,details TEXT NOT NULL);
            """)
            self._put(connection, "identity", "manager", {"id": "manager", "role": "manager", "token_hash": digest(token)})
            self._audit(connection, "manager", "initialize", {})
            connection.commit()
        finally:
            connection.close()
        return {"state": str(self.state), "manager_token_file": str(token_file)}

    def _get(self, connection, kind, identity):
        row = connection.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, identity)).fetchone()
        if row is None:
            raise WorkflowError(f"Unknown {kind}: {identity}")
        return json.loads(row[0])

    def _all(self, connection, kind):
        return [json.loads(row[0]) for row in connection.execute("SELECT data FROM records WHERE kind=? ORDER BY id", (kind,))]

    def _put(self, connection, kind, identity, value):
        connection.execute("INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, identity, canonical(value)))

    def _audit(self, connection, actor, event, details):
        connection.execute("INSERT INTO audit(at,actor,event,details) VALUES(?,?,?,?)", (now(), actor, event, canonical(details)))

    def _auth(self, connection, token, role=None):
        hashed = digest(text(token, "credential"))
        for identity in self._all(connection, "identity"):
            if secrets.compare_digest(identity["token_hash"], hashed):
                if role is not None and identity["role"] not in role:
                    raise WorkflowError("Credential is not authorized for this action")
                return identity
        raise WorkflowError("Invalid credential")

    @staticmethod
    def _public(identity):
        return {key: value for key, value in identity.items() if key != "token_hash"}

    def _runtime(self, connection, token, roles):
        identity = self._auth(connection, token, roles)
        project = self._get(connection, "project", identity["project"])
        return identity, project

    def create_project(self, token, name, final_quorum=2, synthetic=False):
        if isinstance(final_quorum, bool) or not isinstance(final_quorum, int) or not 2 <= final_quorum <= 10:
            raise WorkflowError("final_quorum must be an integer between 2 and 10")
        with self._transaction() as c:
            self._auth(c, token, ["manager"])
            project = {"id": uuid.uuid4().hex, "name": text(name, "name"), "draft": None, "final": None,
                       "status": "research", "final_quorum": final_quorum, "synthetic": bool(synthetic), "created_at": now()}
            self._put(c, "project", project["id"], project)
            self._audit(c, "manager", "project.create", {"project": project["id"]})
            return project

    def create_runtime(self, token, project_id, role, submission=None):
        if role not in ("research", "review", "execution"):
            raise WorkflowError("Runtime role must be research, review or execution")
        with self._transaction() as c:
            self._auth(c, token, ["manager"])
            project = self._get(c, "project", project_id)
            bound_draft = None
            if role == "execution":
                self._approved(c, project)
                bound_draft = project["draft"]
            if role == "review":
                if not submission:
                    raise WorkflowError("Review runtime requires an immutable submission assignment")
                submitted = self._get(c, "submission", submission)
                if submitted["project"] != project_id or project[submitted["kind"]] != submission:
                    raise WorkflowError("Review assignment must refer to the current project submission")
            elif submission is not None:
                raise WorkflowError("Only review runtimes take a submission assignment")
            runtime_id = uuid.uuid4().hex
            credential = secrets.token_urlsafe(40)
            identity = {"id": runtime_id, "role": role, "project": project_id, "submission": submission,
                        "bound_draft": bound_draft, "session_id": uuid.uuid4().hex, "created_at": now(), "token_hash": digest(credential)}
            credential_dir = self.state / "credentials"
            credential_dir.mkdir(exist_ok=True)
            credential_file = credential_dir / (runtime_id + ".token")
            credential_file.write_text(credential, encoding="utf-8")
            credential_file.chmod(0o600)
            self._put(c, "identity", runtime_id, identity)
            if role == "review":
                project["status"] = submitted["kind"] + "_review"
                self._put(c, "project", project_id, project)
            self._audit(c, "manager", "runtime.create", {"runtime": runtime_id, "role": role, "project": project_id, "submission": submission})
            return dict(self._public(identity), token_file=str(credential_file))

    def runtime_info(self, token, runtime_id):
        with self._transaction() as c:
            self._auth(c, token, ["manager"])
            identity = self._get(c, "identity", runtime_id)
            if identity["role"] == "manager":
                raise WorkflowError("Manager is not a harness runtime")
            return self._public(identity)

    def _approved(self, connection, project):
        if not project["draft"]:
            raise WorkflowError("Execution requires an approved draft")
        reviews = [r for r in self._all(connection, "review") if r["submission"] == project["draft"]]
        assignments = [r for r in self._all(connection, "identity") if r.get("submission") == project["draft"]]
        if not reviews or len(reviews) != len(assignments) or any(r["report"]["decision"] != "pass" for r in reviews):
            raise WorkflowError("Current draft has not passed independent review")
        return project["draft"]

    def _execution(self, connection, identity, project):
        self._approved(connection, project)
        if identity["bound_draft"] != project["draft"]:
            raise WorkflowError("Execution runtime grant is stale; create a new runtime after review")

    def status(self, token, project_id=None):
        with self._transaction() as c:
            identity = self._auth(c, token)
            if identity["role"] == "manager":
                if project_id is None:
                    return {"projects": self._all(c, "project")}
            else:
                if project_id is not None and project_id != identity["project"]:
                    raise WorkflowError("Cross-project access denied")
                project_id = identity["project"]
            project = self._get(c, "project", project_id)
            reviews = [r for r in self._all(c, "review") if self._get(c, "submission", r["submission"])["project"] == project_id]
            if identity["role"] == "review":
                reviews = [r for r in reviews if r["reviewer"] == identity["id"]]
            return {"project": project, "reviews": reviews}

    def submit(self, token, kind, manuscript, evidence, plan):
        if kind not in ("draft", "final"):
            raise WorkflowError("Submission kind must be draft or final")
        documents = {"manuscript": text(manuscript, "manuscript"), "evidence": text(evidence, "evidence"), "plan": text(plan, "plan")}
        if any(len(value.encode("utf-8")) > 8 * 1024 * 1024 for value in documents.values()):
            raise WorkflowError("Each submission document must be smaller than 8 MiB")
        with self._transaction() as c:
            identity, project = self._runtime(c, token, ["research"] if kind == "draft" else ["execution"])
            experiment_ids = []
            if kind == "final":
                self._execution(c, identity, project)
                runs = [run for run in self._all(c, "experiment") if run["project"] == project["id"] and run["draft"] == project["draft"] and run["status"] == "completed"]
                if not runs:
                    raise WorkflowError("Final manuscript requires imported results with checked provenance")
                for run in runs:
                    self._check_snapshots(run)
                experiment_ids = [run["id"] for run in runs]
            submission = {"id": uuid.uuid4().hex, "project": project["id"], "kind": kind, "author": identity["id"],
                          "documents": documents, "content_hash": digest(documents), "draft": project["draft"] if kind == "final" else None,
                          "experiments": experiment_ids, "created_at": now()}
            self._put(c, "submission", submission["id"], submission)
            project[kind] = submission["id"]
            project["status"] = kind + "_review"
            if kind == "draft":
                project["final"] = None
            self._put(c, "project", project["id"], project)
            self._audit(c, identity["id"], "submission.create", {"submission": submission["id"], "content_hash": submission["content_hash"]})
            return {key: value for key, value in submission.items() if key != "documents"}

    def review_context(self, token):
        with self._transaction() as c:
            identity, project = self._runtime(c, token, ["review"])
            submission = self._get(c, "submission", identity["submission"])
            if project[submission["kind"]] != submission["id"]:
                raise WorkflowError("Review assignment is stale")
            # Author identity and other reviewers' reports are intentionally not disclosed.
            context = {key: value for key, value in submission.items() if key != "author"}
            context["experiment_results"] = [self._get(c, "experiment", run_id) for run_id in submission["experiments"]]
            for run in context["experiment_results"]:
                self._check_snapshots(run)
            return context

    @staticmethod
    def _check_snapshots(run):
        for artifact in run["result"]["artifacts"]:
            snapshot = Path(artifact["snapshot"])
            if not snapshot.is_file() or hash_file(snapshot) != artifact["sha256"]:
                raise WorkflowError("Imported artifact snapshot is missing or has changed")

    def research_context(self, token):
        with self._transaction() as c:
            identity, project = self._runtime(c, token, ["research"])
            draft = self._get(c, "submission", project["draft"]) if project["draft"] else None
            feedback = [r for r in self._all(c, "review") if draft and r["submission"] == draft["id"]]
            return {"current_draft": draft, "feedback": feedback}

    def execution_context(self, token):
        with self._transaction() as c:
            identity, project = self._runtime(c, token, ["execution"])
            self._execution(c, identity, project)
            draft = self._get(c, "submission", project["draft"])
            runs = [run for run in self._all(c, "experiment") if run["project"] == project["id"] and run["draft"] == project["draft"]]
            for run in runs:
                if run["status"] == "completed":
                    self._check_snapshots(run)
            final = self._get(c, "submission", project["final"]) if project["final"] else None
            feedback = [r for r in self._all(c, "review") if final and r["submission"] == final["id"]]
            return {"approved_draft": draft, "experiments": runs, "current_final": final, "feedback": feedback}

    @staticmethod
    def _validate_report(report):
        canonical(report)
        if not isinstance(report, dict) or report.get("decision") not in ("pass", "revise", "reject", "insufficient"):
            raise WorkflowError("Invalid review decision")
        scores = report.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(SCORES):
            raise WorkflowError("Provide all six rubric scores")
        for value in scores.values():
            if value is None and report["decision"] == "insufficient":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 10:
                raise WorkflowError("Scores must be finite numbers in 0..10")
        confidence = report.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise WorkflowError("Confidence must be a number in 0..1")
        text(report.get("rationale"), "rationale")
        blockers = report.get("blockers")
        if not isinstance(blockers, list) or any(not isinstance(item, str) or not item.strip() for item in blockers):
            raise WorkflowError("blockers must be an array of nonempty strings")
        if report["decision"] == "pass" and blockers:
            raise WorkflowError("A pass cannot contain unresolved blockers")
        evidence = report.get("search_evidence")
        if not isinstance(evidence, list) or (not evidence and report["decision"] != "insufficient"):
            raise WorkflowError("Review must include an independent search trace")
        for item in evidence:
            if not isinstance(item, dict):
                raise WorkflowError("Search evidence must be structured")
            for key in ("query", "source", "url", "accessed_at", "finding"):
                text(item.get(key), "search_evidence." + key)
            if not item["url"].startswith(("https://", "http://")):
                raise WorkflowError("Search evidence URL must be HTTP(S)")

    def review(self, token, report):
        self._validate_report(report)
        with self._transaction() as c:
            identity, project = self._runtime(c, token, ["review"])
            submission = self._get(c, "submission", identity["submission"])
            if submission["author"] == identity["id"]:
                raise WorkflowError("Authors cannot review their own submission")
            if project[submission["kind"]] != submission["id"]:
                raise WorkflowError("Review assignment is stale")
            review_id = submission["id"] + ":" + identity["id"]
            if c.execute("SELECT 1 FROM records WHERE kind='review' AND id=?", (review_id,)).fetchone():
                raise WorkflowError("A submitted review is immutable; resubmit a new manuscript for another round")
            review = {"id": review_id, "submission": submission["id"], "content_hash": submission["content_hash"],
                      "reviewer": identity["id"], "report": report, "created_at": now()}
            self._put(c, "review", review_id, review)
            reviews = [r for r in self._all(c, "review") if r["submission"] == submission["id"]]
            assignments = [r for r in self._all(c, "identity") if r.get("submission") == submission["id"]]
            required = 1 if submission["kind"] == "draft" else project["final_quorum"]
            if any(r["report"]["decision"] != "pass" for r in reviews):
                project["status"] = submission["kind"] + "_revision_required"
            elif len(reviews) >= required and len(reviews) == len(assignments):
                project["status"] = "approved" if submission["kind"] == "draft" else "complete"
            self._put(c, "project", project["id"], project)
            self._audit(c, identity["id"], "review.submit", {"submission": submission["id"], "decision": report["decision"]})
            return {"review": review, "project_status": project["status"]}

    def tools(self, token):
        with self._transaction() as c:
            identity = self._auth(c, token, ["research", "review", "execution"])
            available = ["project_status"]
            if identity["role"] == "research":
                available += ["research_context", "submission_submit"]
            elif identity["role"] == "review":
                submitted = self._get(c, "submission", identity["submission"])
                project = self._get(c, "project", identity["project"])
                if project[submitted["kind"]] == submitted["id"]:
                    available += ["review_context", "review_submit"]
            else:
                try:
                    self._execution(c, identity, self._get(c, "project", identity["project"]))
                except WorkflowError:
                    return available
                available += ["execution_context", "experiment_submit", "experiment_status", "paper_submit"]
            return available

    def call(self, token, name, arguments):
        if name not in self.tools(token):
            raise WorkflowError("Tool is unavailable in the current runtime phase")
        if not isinstance(arguments, dict):
            raise WorkflowError("Tool arguments must be an object")
        handlers = {"project_status": lambda: self.status(token),
                    "research_context": lambda: self.research_context(token),
                    "submission_submit": lambda: self.submit(token, "draft", **arguments),
                    "review_context": lambda: self.review_context(token),
                    "review_submit": lambda: self.review(token, **arguments),
                    "execution_context": lambda: self.execution_context(token),
                    "experiment_submit": lambda: self.experiment_submit(token, **arguments),
                    "experiment_status": lambda: self.experiment_status(token, **arguments),
                    "paper_submit": lambda: self.submit(token, "final", **arguments)}
        try:
            return handlers[name]()
        except TypeError as exc:
            raise WorkflowError("Unexpected or missing tool arguments") from exc

    def register_device(self, token, device_id, config):
        canonical(config)
        if not isinstance(config, dict) or config.get("operator_approved") is not True:
            raise WorkflowError("Device configuration requires explicit operator_approved=true")
        text(device_id, "device_id")
        with self._transaction() as c:
            self._auth(c, token, ["manager"])
            device = {"id": device_id, "config": config, "config_hash": digest(config)}
            self._put(c, "device", device_id, device)
            self._audit(c, "manager", "device.register", {"device": device_id, "config_hash": device["config_hash"]})
            return device

    def lease_device(self, token, device_id, runtime_id, seconds=3600):
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 86400:
            raise WorkflowError("Lease seconds must be 1..86400")
        with self._transaction() as c:
            self._auth(c, token, ["manager"])
            device = self._get(c, "device", device_id)
            runtime = self._get(c, "identity", runtime_id)
            if runtime["role"] != "execution":
                raise WorkflowError("Only an execution runtime can reserve hardware")
            self._execution(c, runtime, self._get(c, "project", runtime["project"]))
            active = [x for x in self._all(c, "lease") if x["device"] == device_id and x["expires_at"] > time.time()]
            if active:
                raise WorkflowError("Device already has an active lease")
            lease = {"id": uuid.uuid4().hex, "device": device_id, "runtime": runtime_id,
                     "config_hash": device["config_hash"], "expires_at": time.time() + seconds}
            self._put(c, "lease", lease["id"], lease)
            self._audit(c, "manager", "device.lease", lease)
            return lease

    def experiment_submit(self, token, spec):
        canonical(spec)
        if not isinstance(spec, dict) or spec.get("kind") not in ("simulation", "hardware"):
            raise WorkflowError("Experiment kind must be simulation or hardware")
        text(spec.get("name"), "name")
        text(spec.get("code_revision"), "code_revision")
        if not isinstance(spec.get("config"), dict) or not spec["config"]:
            raise WorkflowError("Experiment requires a nonempty config")
        with self._transaction() as c:
            identity, project = self._runtime(c, token, ["execution"])
            self._execution(c, identity, project)
            if spec["kind"] == "hardware":
                device = self._get(c, "device", spec.get("device_id"))
                leases = [lease for lease in self._all(c, "lease") if lease["device"] == device["id"] and lease["runtime"] == identity["id"]
                          and lease["expires_at"] > time.time() and lease["config_hash"] == device["config_hash"]]
                if not leases:
                    raise WorkflowError("Hardware requires a current operator-approved device lease")
                if spec.get("device_config_hash") != device["config_hash"]:
                    raise WorkflowError("Hardware request must bind the exact approved device configuration")
                if spec.get("hardware_config") != device["config"]:
                    raise WorkflowError("hardware_config must equal the operator-approved device configuration; config is algorithm-only")
            run = {"id": uuid.uuid4().hex, "project": project["id"], "draft": project["draft"], "runtime": identity["id"],
                   "spec": spec, "config_hash": digest(spec["config"]), "status": "pending_unconfigured", "created_at": now(), "result": None}
            self._put(c, "experiment", run["id"], run)
            self._audit(c, identity["id"], "experiment.submit", {"experiment": run["id"]})
            return run

    def experiment_status(self, token, experiment_id):
        with self._transaction() as c:
            identity, project = self._runtime(c, token, ["execution"])
            self._execution(c, identity, project)
            run = self._get(c, "experiment", experiment_id)
            if run["project"] != project["id"] or run["draft"] != project["draft"]:
                raise WorkflowError("Experiment belongs to another project or obsolete draft")
            return run

    def import_result(self, token, experiment_id, result):
        canonical(result)
        if not isinstance(result, dict) or result.get("origin") not in ("simulated", "measured", "synthetic"):
            raise WorkflowError("Result origin must be simulated, measured or synthetic")
        for key in ("source", "code_revision", "config_hash"):
            text(result.get(key), key)
        if not isinstance(result.get("metrics"), dict) or not result["metrics"]:
            raise WorkflowError("Result requires nonempty metrics")
        if not isinstance(result.get("artifacts"), list) or not result["artifacts"]:
            raise WorkflowError("Result requires file artifacts and their SHA-256 hashes")
        for item in result["artifacts"]:
            if not isinstance(item, dict):
                raise WorkflowError("Invalid artifact")
            path = Path(text(item.get("path"), "artifact.path"))
            if not path.is_absolute() or not path.is_file():
                raise WorkflowError("Artifact must be an existing absolute file path")
            sha = hash_file(path)
            if item.get("sha256") != sha:
                raise WorkflowError("Artifact hash mismatch")
        with self._transaction() as c:
            self._auth(c, token, ["manager"])
            run = self._get(c, "experiment", experiment_id)
            project = self._get(c, "project", run["project"])
            if run["draft"] != project["draft"]:
                raise WorkflowError("Cannot import results for an obsolete draft")
            self._approved(c, project)
            if run["status"] == "completed":
                raise WorkflowError("Imported results are immutable")
            if result["origin"] == "synthetic" and not project["synthetic"]:
                raise WorkflowError("Synthetic results are allowed only in explicitly synthetic projects")
            if result["code_revision"] != run["spec"]["code_revision"] or result["config_hash"] != run["config_hash"]:
                raise WorkflowError("Result provenance does not match the registered experiment")
            if (run["spec"]["kind"] == "simulation" and result["origin"] == "measured") or (run["spec"]["kind"] == "hardware" and result["origin"] == "simulated"):
                raise WorkflowError("Result origin conflicts with the experiment kind")
            snapshots = []
            for item in result["artifacts"]:
                source = Path(item["path"])
                directory = self.state / "artifacts" / run["id"]
                directory.mkdir(parents=True, exist_ok=True)
                destination = directory / (item["sha256"] + source.suffix)
                temporary = directory / (uuid.uuid4().hex + ".tmp")
                try:
                    with source.open("rb") as incoming, temporary.open("wb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
                    if hash_file(temporary) != item["sha256"]:
                        raise WorkflowError("Artifact changed during import")
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
                snapshots.append(dict(item, snapshot=str(destination)))
            result = dict(result, artifacts=snapshots)
            run.update(status="completed", result=result, completed_at=now())
            self._put(c, "experiment", run["id"], run)
            self._audit(c, "manager", "experiment.result.import", {"experiment": run["id"], "origin": result["origin"], "result_hash": digest(result)})
            return run

    def audit(self, token):
        with self._transaction() as c:
            self._auth(c, token, ["manager"])
            return [{"seq": row[0], "at": row[1], "actor": row[2], "event": row[3], "details": json.loads(row[4])}
                    for row in c.execute("SELECT seq,at,actor,event,details FROM audit ORDER BY seq")]
