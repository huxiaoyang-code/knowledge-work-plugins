"""Manager CLI. Agent processes use scoped MCP credentials, never this authority."""
import argparse
import json
from pathlib import Path
import sys

from .runtime import materialize, supervise
from .store import Store, WorkflowError, canonical, read_document


def parser():
    p = argparse.ArgumentParser(description="Manage independent telecom research harness runtimes")
    p.add_argument("--state", required=True, help="External state directory")
    p.add_argument("--token-file", help="Manager credential file (default STATE/manager.token)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    s = sub.add_parser("project-create")
    s.add_argument("--name", required=True)
    s.add_argument("--final-quorum", type=int, default=2)
    s.add_argument("--synthetic", action="store_true", help="Explicit synthetic demonstration project")
    s = sub.add_parser("runtime-create")
    s.add_argument("--project", required=True)
    s.add_argument("--role", required=True, choices=["research", "review", "execution"])
    s.add_argument("--submission")
    for command in ("submit", "review", "experiment-submit"):
        s = sub.add_parser(command)
        s.add_argument("--runtime", required=True)
        if command == "submit":
            s.add_argument("--kind", required=True, choices=["draft", "final"])
            for field in ("manuscript", "evidence", "plan"):
                s.add_argument("--" + field, required=True)
        else:
            s.add_argument("--report" if command == "review" else "--spec", required=True)
    s = sub.add_parser("status")
    s.add_argument("--project")
    s = sub.add_parser("materialize")
    s.add_argument("--runtime", required=True)
    s.add_argument("--harness", required=True, choices=["claude", "codex"])
    s.add_argument("--destination", required=True)
    s.add_argument("--profiles-root")
    s.add_argument("--python-executable")
    s = sub.add_parser("experiment-result")
    s.add_argument("--experiment", required=True)
    s.add_argument("--result", required=True)
    s = sub.add_parser("device-register")
    s.add_argument("--device", required=True)
    s.add_argument("--config", required=True)
    s = sub.add_parser("device-lease")
    s.add_argument("--device", required=True)
    s.add_argument("--runtime", required=True)
    s.add_argument("--seconds", type=int, default=3600)
    sub.add_parser("audit")
    sub.add_parser("supervise", help="JSONL process manager: start/status/stop/quit; launches models only on start")
    return p


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(WorkflowError("Non-finite JSON value")))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        store = Store(args.state)
        if args.command == "init":
            result = store.initialize()
        else:
            manager = Path(args.token_file or store.state / "manager.token").read_text(encoding="utf-8").strip()
            # CLI runtime actions are manager-mediated convenience commands, not agent endpoints.
            def credential():
                store.runtime_info(manager, args.runtime)
                return (store.state / "credentials" / (args.runtime + ".token")).read_text(encoding="utf-8").strip()
            if args.command == "project-create":
                result = store.create_project(manager, args.name, args.final_quorum, args.synthetic)
            elif args.command == "runtime-create":
                result = store.create_runtime(manager, args.project, args.role, args.submission)
            elif args.command == "submit":
                result = store.submit(credential(), args.kind, read_document(args.manuscript), read_document(args.evidence), read_document(args.plan))
            elif args.command == "review":
                result = store.review(credential(), load_json(args.report))
            elif args.command == "status":
                result = store.status(manager, args.project)
            elif args.command == "materialize":
                result = materialize(store, manager, args.runtime, args.harness, args.destination, args.profiles_root, args.python_executable)
            elif args.command == "experiment-submit":
                result = store.experiment_submit(credential(), load_json(args.spec))
            elif args.command == "experiment-result":
                result = store.import_result(manager, args.experiment, load_json(args.result))
            elif args.command == "device-register":
                result = store.register_device(manager, args.device, load_json(args.config))
            elif args.command == "device-lease":
                result = store.lease_device(manager, args.device, args.runtime, args.seconds)
            elif args.command == "audit":
                result = store.audit(manager)
            elif args.command == "supervise":
                supervise(store, manager)
                return
        print(canonical({"ok": True, "result": result}))
    except (WorkflowError, OSError, json.JSONDecodeError, TypeError) as exc:
        print(canonical({"ok": False, "error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
