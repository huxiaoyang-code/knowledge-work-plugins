"""Materialize phase-specific workspaces and supervise explicitly started harnesses."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

from .store import Store, WorkflowError, canonical, now, require_external


class WindowsJob:
    """Owned job handle; terminating/closing it cancels associated descendants."""
    def __init__(self, child):
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
                        ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                        ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(key, ctypes.c_ulonglong) for key in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", Counters), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        self.lock = threading.Lock()
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        if not self.api.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(child._handle))):
            self.close()
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def terminate(self):
        with self.lock:
            if self.handle and not self.api.TerminateJobObject(self.handle, 1):
                raise WorkflowError("Could not terminate the owned Windows job")

    def close(self):
        with self.lock:
            if self.handle:
                self.api.CloseHandle(self.handle)
                self.handle = None


def materialize(store: Store, token, runtime_id, harness, destination, profiles_root=None, python_executable=None):
    if harness not in ("claude", "codex"):
        raise WorkflowError("Harness must be claude or codex")
    info = store.runtime_info(token, runtime_id)
    runtime_token = (store.state / "credentials" / (runtime_id + ".token")).read_text(encoding="utf-8")
    if info["role"] == "execution" and "experiment_submit" not in store.tools(runtime_token):
        raise WorkflowError("Execution runtime grant is no longer valid")
    if info["role"] == "review" and "review_context" not in store.tools(runtime_token):
        raise WorkflowError("Review assignment is no longer current")
    profiles = Path(profiles_root).resolve() if profiles_root else Path(__file__).resolve().parents[2] / "profiles"
    profile = profiles / info["role"]
    if not (profile / "skills").is_dir():
        raise WorkflowError("Profiles are not installed with the Python wheel; provide --profiles-root from the source checkout")
    target = require_external(destination)
    source_root = Path(__file__).resolve().parents[2]
    if target.exists() or target == source_root or source_root in target.parents or target == store.state or store.state in target.parents:
        raise WorkflowError("Destination must be a new external directory, outside source and state")
    if any(path.is_symlink() for path in profile.rglob("*")):
        raise WorkflowError("Profile symlinks are not accepted")
    target.mkdir(parents=True)
    skill_root = target / (".claude" if harness == "claude" else ".agents") / "skills"
    shutil.copytree(profile / "skills", skill_root)
    credential = target / ".runtime.token"
    credential.write_text(runtime_token, encoding="utf-8")
    credential.chmod(0o600)
    executable = str(python_executable or sys.executable)
    mcp = {"mcpServers": {"telecom": {"command": executable,
        "args": ["-m", "telecom_research.mcp_server", "--state", str(store.state), "--token-file", str(credential)]}}}
    mcp_file = target / "mcp.json"
    mcp_file.write_text(json.dumps(mcp, indent=2), encoding="utf-8")
    # Copy no manuscript history; the reviewer receives immutable content via its scoped MCP.
    prompt = "Use the telecom " + info["role"] + " skill in this workspace. First call project_status. Runtime identity: " + runtime_id + "."
    if harness == "claude":
        argv = ["claude", "-p", prompt, "--strict-mcp-config", "--mcp-config", str(mcp_file),
                "--no-session-persistence", "--output-format", "stream-json", "--verbose"]
    else:
        # Use only runtime-scoped MCP configuration; no unknown global user config.
        args = canonical(mcp["mcpServers"]["telecom"]["args"])
        argv = ["codex", "exec", "--ephemeral", "--json", "--ignore-user-config", "--skip-git-repo-check", "--sandbox", "workspace-write",
                "-C", str(target), "-c", "mcp_servers.telecom.command=" + json.dumps(executable),
                "-c", "mcp_servers.telecom.args=" + args, prompt]
    plan = {"runtime": runtime_id, "session_id": info["session_id"], "harness": harness, "profile": info["role"],
            "cwd": str(target), "argv": argv, "mcp_config": str(mcp_file), "created_at": now(),
            "notice": "Fresh session; host sandbox and filesystem isolation are operator responsibilities. No model was invoked."}
    (target / "launch-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    with store._transaction() as c:
        store._auth(c, token, ["manager"])
        store._put(c, "launch", runtime_id, plan)
        store._audit(c, "manager", "runtime.materialize", {"runtime": runtime_id, "profile": info["role"], "cwd": str(target)})
    return plan


class Supervisor:
    """Foreground owner of subprocesses. A separate CLI manager process remains alive."""
    def __init__(self, store, manager_token):
        self.store = store
        self.token = manager_token
        self.processes = {}
        self.jobs = {}
        self.lock = threading.Lock()

    def start(self, runtime_id, command=None, wait=False):
        info = self.store.runtime_info(self.token, runtime_id)
        runtime_token = (self.store.state / "credentials" / (runtime_id + ".token")).read_text(encoding="utf-8")
        available = self.store.tools(runtime_token)
        if info["role"] == "execution" and "experiment_submit" not in available:
            raise WorkflowError("Execution grant is stale")
        if info["role"] == "review" and "review_context" not in available:
            raise WorkflowError("Review assignment is stale")
        with self.store._transaction() as c:
            self.store._auth(c, self.token, ["manager"])
            plan = self.store._get(c, "launch", runtime_id)
            if any(r.get("runtime") == runtime_id and r.get("status") == "running" for r in self.store._all(c, "process")):
                raise WorkflowError("Runtime already has a running process; reconcile a crashed supervisor before restarting")
            argv = command or plan["argv"]
            if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
                raise WorkflowError("Command must be a nonempty argv array")
            log_path = self.store.state / ("runtime-" + runtime_id + ".log")
            log = log_path.open("ab")
            try:
                options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
                child = subprocess.Popen(argv, cwd=plan["cwd"], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, shell=False, **options)
                job = WindowsJob(child) if os.name == "nt" else None
            except Exception:
                if "child" in locals() and child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
                log.close()
                raise
            record = {"id": runtime_id, "runtime": runtime_id, "pid": child.pid, "status": "running", "argv": argv,
                      "cwd": plan["cwd"], "log": str(log_path), "started_at": now(), "exit_code": None}
            self.store._put(c, "process", runtime_id, record)
            self.store._audit(c, "manager", "runtime.start", {"runtime": runtime_id, "pid": child.pid})
            with self.lock:
                self.processes[runtime_id] = child
                self.jobs[runtime_id] = job

        def finish():
            code = child.wait()
            if job is not None:
                job.close()
            log.close()
            with self.store._transaction() as c:
                current = self.store._get(c, "process", runtime_id)
                current.update(status="exited", exit_code=code, ended_at=now())
                self.store._put(c, "process", runtime_id, current)
                self.store._audit(c, "manager", "runtime.exit", {"runtime": runtime_id, "exit_code": code})
            with self.lock:
                if self.processes.get(runtime_id) is child:
                    self.processes.pop(runtime_id, None)
                    self.jobs.pop(runtime_id, None)

        if wait:
            finish()
            return self.status(runtime_id)
        threading.Thread(target=finish, daemon=False).start()
        return record

    def status(self, runtime_id):
        with self.store._transaction() as c:
            self.store._auth(c, self.token, ["manager"])
            return self.store._get(c, "process", runtime_id)

    def stop(self, runtime_id):
        self.store.runtime_info(self.token, runtime_id)
        with self.lock:
            child = self.processes.get(runtime_id)
            job = self.jobs.get(runtime_id)
        if child is None:
            raise WorkflowError("This supervisor does not own that live process; refusing to kill an unverified PID")
        if child.poll() is not None:
            return {"runtime": runtime_id, "stop_requested": False, "exit_code": child.returncode}
        if os.name == "nt":
            job.terminate()
        else:
            os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                child.kill()
            else:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        return {"runtime": runtime_id, "stop_requested": True, "exit_code": child.returncode}

    def close(self):
        with self.lock:
            ids = list(self.processes)
        for runtime_id in ids:
            self.stop(runtime_id)


def supervise(store, token):
    """JSON-lines manager interface: start/status/stop/quit. Credentials stay local."""
    supervisor = Supervisor(store, token)
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                operation = request.get("op")
                if operation == "quit":
                    print(canonical({"ok": True, "result": "closing"}), flush=True)
                    break
                runtime_id = request.get("runtime")
                if operation == "start":
                    result = supervisor.start(runtime_id)
                elif operation == "status":
                    result = supervisor.status(runtime_id)
                elif operation == "stop":
                    result = supervisor.stop(runtime_id)
                else:
                    raise WorkflowError("Supervisor op must be start, status, stop or quit")
                print(canonical({"ok": True, "result": result}), flush=True)
            except (ValueError, OSError, KeyError) as exc:
                print(canonical({"ok": False, "error": str(exc)}), flush=True)
    finally:
        supervisor.close()
