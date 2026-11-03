"""Package an exact clean Git snapshot, without executing models or dependencies.

Git objects, rather than working-tree files or export rules, are authoritative.
The generated manifest and SHA-256 sidecar provide integrity, not publisher identity.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import tomllib
from urllib.parse import urlsplit
import zipfile


MANIFEST = "PACKAGE-METADATA.json"
ENTRYPOINT = "START_HERE_FOR_CODEX.md"
CHUNK = 1024 * 1024


class PackageError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            value.update(chunk)
    return value.hexdigest()


def git(repo, *args, check=True):
    environment = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                            capture_output=True, env=environment)
    if check and result.returncode:
        raise PackageError("Git command failed: " + " ".join(args[:2]) + "; " + result.stderr.decode("utf-8", "replace").strip())
    return result


def repo_root(repo):
    return Path(git(repo, "rev-parse", "--show-toplevel").stdout.decode("utf-8").strip()).resolve()


def clean_snapshot(repo, commit=None):
    head = git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    if commit is not None and head != commit:
        raise PackageError("HEAD changed while packaging; retry from a clean pinned commit")
    status = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    if status:
        # Report paths, never file contents. Do not stash or reset the user's work.
        paths = [part.decode("utf-8", "replace") for part in status.split(b"\0") if part]
        raise PackageError("Source worktree is dirty; commit or otherwise handle the listed work before packaging: " + "; ".join(paths[:20]))
    return head


def safe_path(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\0" in name:
        raise PackageError("Unsafe archive path: " + repr(name))
    parts = name.split("/")
    if any(part in ("", ".", "..") or part.rstrip(" .") != part or any(ord(char) < 32 for char in part) for part in parts):
        raise PackageError("Unsafe archive path: " + repr(name))
    if PurePosixPath(name).is_absolute() or any(part.lower() == ".git" for part in parts):
        raise PackageError("Git metadata or absolute path is not allowed: " + name)
    windows_reserved = {"con", "prn", "aux", "nul", *("com" + str(n) for n in range(1, 10)), *("lpt" + str(n) for n in range(1, 10))}
    if any(part.split(".")[0].lower() in windows_reserved for part in parts):
        raise PackageError("Archive path is not portable to Windows: " + name)
    return name


def unsafe_source(path):
    parts = path.lower().split("/")
    name = parts[-1]
    documented_env = name.endswith((".example", ".sample", ".template"))
    if (name == ".env" or name.startswith(".env.")) and not documented_env:
        return True
    if name.endswith((".token", ".sqlite", ".sqlite3", ".sqlite-wal", ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm")):
        return True
    if name in ("auth.json", "credentials.json", "manager.token", ".ds_store"):
        return True
    if name.endswith(".db") and (len(parts) == 1 or any(part in ("state", "data", "runtime", "runtime-data", "sessions", ".codex", ".claude") for part in parts[:-1])):
        return True
    if name.endswith(".log") and (name.startswith(("runtime-", "session-", "auth", "credential")) or any(part in ("logs", "sessions", "credentials") for part in parts[:-1])):
        return True
    return any(part in (".venv", "__pycache__", "node_modules") for part in parts[:-1])


def source_tree(repo, commit, scope):
    if scope not in ("repository", "telecom"):
        raise PackageError("scope must be repository or telecom")
    raw = git(repo, "ls-tree", "-r", "-z", "--full-tree", commit).stdout
    files = []
    seen = set()
    for row in raw.split(b"\0"):
        if not row:
            continue
        header, path_bytes = row.split(b"\t", 1)
        mode, kind, blob = header.decode("ascii").split()
        try:
            path = path_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PackageError("Git contains a non-UTF-8 filename; normalize it explicitly before packaging") from exc
        if scope == "telecom" and not path.startswith("telecom-research/"):
            continue
        safe_path(path)
        relative = path[len("telecom-research/"):] if scope == "telecom" else path
        safe_path(relative)
        if relative in (MANIFEST, ENTRYPOINT):
            raise PackageError("Tracked file conflicts with reserved generated manifest: " + path)
        if relative.casefold() in seen:
            raise PackageError("Case-colliding archive paths are not portable: " + path)
        seen.add(relative.casefold())
        if mode == "160000" or kind == "commit":
            raise PackageError("Submodule source is not bundled automatically: " + path)
        if mode == "120000":
            raise PackageError("Symbolic link requires an explicit portable packaging decision: " + path)
        if mode not in ("100644", "100755") or kind != "blob":
            raise PackageError("Unsupported tracked file mode at: " + path)
        if unsafe_source(path):
            raise PackageError("Refusing unsafe tracked credential/runtime/environment file: " + path)
        files.append({"path": relative, "source_path": path, "git_mode": mode, "git_blob": blob})
    if not files:
        raise PackageError("Selected source scope contains no tracked files")
    return sorted(files, key=lambda item: item["path"])


@contextmanager
def blobs(repo):
    environment = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    with tempfile.TemporaryFile() as error_log:
        process = subprocess.Popen(["git", "--no-replace-objects", "-C", str(repo), "cat-file", "--batch"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_log, env=environment)
        try:
            yield process
            process.stdin.close()
            if process.wait(timeout=30):
                raise PackageError("Could not read all Git blobs; hydrate the local checkout before packaging")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()
            if not process.stdin.closed:
                process.stdin.close()


def read_blob_header(process, blob):
    process.stdin.write((blob + "\n").encode("ascii"))
    process.stdin.flush()
    header = process.stdout.readline().decode("ascii").strip().split()
    if len(header) != 3 or header[0] != blob or header[1] != "blob":
        raise PackageError("Source blob unavailable locally; hydrate the checkout first: " + blob)
    return int(header[2])


def file_info(name, timestamp, mode="100644"):
    info = zipfile.ZipInfo(name, date_time=timestamp)
    info.create_system = 3
    info.external_attr = int(mode, 8) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def inventory_digest(files):
    return hashlib.sha256(canonical([{key: item[key] for key in ("path", "source_path", "git_mode", "git_blob")} for item in files])).hexdigest()


def metadata(repo, commit, scope, files, version=None):
    origin_result = git(repo, "remote", "get-url", "origin", check=False)
    origin = origin_result.stdout.decode("utf-8").strip() if origin_result.returncode == 0 else None
    if origin and re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", origin):
        parsed = urlsplit(origin)
        standard_ssh_user = parsed.scheme == "ssh" and parsed.username == "git" and parsed.password is None
        if (parsed.username is not None and not standard_ssh_user) or parsed.password is not None or parsed.query or parsed.fragment:
            raise PackageError("Origin URL contains embedded credentials or query/fragment data; use a credential-free origin URL")
    if version is None:
        result = git(repo, "show", commit + ":telecom-research/pyproject.toml", check=False)
        version = tomllib.loads(result.stdout.decode("utf-8")).get("project", {}).get("version", "snapshot") if result.returncode == 0 else "snapshot"
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise PackageError("Version must be a short portable label")
    branch = git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False).stdout.decode("utf-8").strip() or "detached"
    stamp = int(git(repo, "show", "-s", "--format=%ct", commit).stdout.decode("ascii").strip())
    snapshot_time = datetime.fromtimestamp(stamp, timezone.utc)
    archive_root = ("knowledge-work-plugins" if scope == "repository" else "telecom-research") + "-v" + version + "-" + commit[:12]
    guide = "telecom-research/docs/CODEX_HANDOFF.md" if scope == "repository" else "docs/CODEX_HANDOFF.md"
    paths = {item["path"] for item in files}
    return {"format_version": 1, "repository_url": origin, "commit": commit, "branch": branch, "version": version,
            "scope": scope, "archive_root": archive_root, "snapshot_time": snapshot_time.isoformat(),
            "handoff_entrypoint": guide if guide in paths else None,
            "source": {"git_tree": git(repo, "rev-parse", commit + "^{tree}").stdout.decode("ascii").strip(),
                       "object_format": git(repo, "rev-parse", "--show-object-format").stdout.decode("ascii").strip(),
                       "source_file_count": len(files), "source_inventory_sha256": inventory_digest(files), "complete_repository": scope == "repository"},
            "validation": {"tracked_worktree_clean": True, "untracked_source_clean": True,
                           "source_inventory_matches_git_tree": True, "safety_check": "passed", "tests": "not_run_by_packager"},
            "files": files}


def entrypoint(manifest):
    prefix = "telecom-research/" if manifest["scope"] == "repository" else ""
    guide = manifest["handoff_entrypoint"]
    lines = ["# 通信科研源码交接：请从这里开始", "",
             "这是固定 Git 提交的源码包，未包含模型凭据、运行状态或离线依赖。", "",
             "请将本目录交给同事的 Codex，并先让它阅读以下项目说明，再按需配置和使用。", ""]
    paths = {item["path"] for item in manifest["files"]}
    if prefix + "AGENTS.md" in paths:
        lines.append("1. 阅读 [项目约定](" + prefix + "AGENTS.md)，遵循通信研究的阶段边界。")
    if guide:
        lines.append("2. 阅读 [Codex 配置、使用与扩展指南](" + guide + ")，按指南安装依赖和配置连接器。")
    else:
        lines.append("本快照未包含同事使用指南；这是通用源码快照，不能声称已提供完整配置说明。")
    lines.extend(["", "源提交：`" + manifest["commit"] + "`。打包范围：`" + manifest["scope"] + "`。", "",
                  "先核验 ZIP 的 SHA-256 与 PACKAGE-METADATA.json。源码包没有 .git；需要继续提交或重新从 Git 打包时，应克隆来源仓库并检出该提交。", "",
                  "打包脚本只验证源码完整性，不代表已安装依赖、通过科研评审、调用真实模型或连接实验设备。", ""])
    return "\n".join(lines).encode("utf-8")


def package_source(repo, output_dir, scope="repository", ref="HEAD", version=None):
    repo = repo_root(repo)
    commit = clean_snapshot(repo)
    selected = git(repo, "rev-parse", "--verify", ref + "^{commit}").stdout.decode("ascii").strip()
    if selected != commit:
        raise PackageError("--ref must resolve to the clean checkout's current HEAD")
    output = Path(output_dir)
    if not output.is_absolute():
        raise PackageError("--output-dir must be an absolute external release directory")
    output = output.resolve()
    if output == repo or repo in output.parents:
        raise PackageError("Release output must be outside the source worktree")
    for ancestor in (output, *output.parents):
        if (ancestor / "manager.token").exists() or (ancestor / "workflow.sqlite3").exists():
            raise PackageError("Release output must be outside runtime state directories")
    files = source_tree(repo, commit, scope)
    manifest = metadata(repo, commit, scope, files, version)
    wrapper = entrypoint(manifest)
    manifest["generated_files"] = [{"path": ENTRYPOINT, "size": len(wrapper), "sha256": hashlib.sha256(wrapper).hexdigest()}]
    stamp = datetime.fromisoformat(manifest["snapshot_time"])
    year = min(2107, max(1980, stamp.year))
    timestamp = (year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second // 2 * 2)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (manifest["archive_root"] + ".zip")
    with tempfile.TemporaryDirectory(prefix=".package-source-", dir=output) as directory:
        pending = Path(directory) / "source.zip"
        with zipfile.ZipFile(pending, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as bundle, blobs(repo) as process:
            for item in files:
                size = read_blob_header(process, item["git_blob"])
                sha = hashlib.sha256()
                remaining = size
                with bundle.open(file_info(manifest["archive_root"] + "/" + item["path"], timestamp, item["git_mode"]), "w", force_zip64=True) as destination:
                    while remaining:
                        payload = process.stdout.read(min(CHUNK, remaining))
                        if not payload:
                            raise PackageError("Unexpected end of Git blob: " + item["source_path"])
                        destination.write(payload)
                        sha.update(payload)
                        remaining -= len(payload)
                if process.stdout.read(1) != b"\n":
                    raise PackageError("Malformed Git blob stream")
                item.update(size=size, sha256=sha.hexdigest())
            bundle.writestr(file_info(manifest["archive_root"] + "/" + ENTRYPOINT, timestamp), wrapper)
            bundle.writestr(file_info(manifest["archive_root"] + "/" + MANIFEST, timestamp), canonical(manifest) + b"\n")
        clean_snapshot(repo, commit)
        verified = verify_archive(pending, repo)
        checksum = verified["sha256"]
        sidecar = Path(str(archive) + ".sha256")
        sidecar_text = checksum + "  " + archive.name + "\n"
        if archive.exists() and sha_file(archive) != checksum:
            raise PackageError("Existing archive differs; choose a new output directory: " + str(archive))
        if sidecar.exists() and sidecar.read_text(encoding="ascii") != sidecar_text:
            raise PackageError("Existing checksum sidecar differs: " + str(sidecar))
        if not archive.exists():
            with archive.open("xb") as destination, pending.open("rb") as source:
                shutil.copyfileobj(source, destination, CHUNK)
        if not sidecar.exists():
            with sidecar.open("x", encoding="ascii", newline="\n") as stream:
                stream.write(sidecar_text)
    result = verify_archive(archive, repo)
    result["checksum_file"] = str(sidecar)
    result["handoff_entrypoint"] = manifest["handoff_entrypoint"]
    return result


def verify_archive(archive, repo=None):
    archive = Path(archive).resolve()
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if not names or len(names) != len(set(names)) or len(names) != len({name.casefold() for name in names}):
                raise PackageError("Archive is empty or has duplicate/case-colliding paths")
            for info in bundle.infolist():
                safe_path(info.filename)
                if info.is_dir() or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG):
                    raise PackageError("Archive may contain only regular files: " + info.filename)
            roots = {name.split("/")[0] for name in names}
            if len(roots) != 1:
                raise PackageError("Archive must have one top-level directory")
            root = next(iter(roots))
            manifest_name = root + "/" + MANIFEST
            if manifest_name not in names or bundle.getinfo(manifest_name).file_size > 16 * 1024 * 1024:
                raise PackageError("Missing or oversized package manifest")
            manifest = json.loads(bundle.read(manifest_name), parse_constant=lambda _: (_ for _ in ()).throw(PackageError("Non-finite manifest value")))
            if not isinstance(manifest, dict) or type(manifest.get("format_version")) is not int or manifest.get("format_version") != 1 or manifest.get("archive_root") != root or manifest.get("scope") not in ("repository", "telecom"):
                raise PackageError("Unsupported or inconsistent manifest")
            if not isinstance(manifest.get("source"), dict) or not isinstance(manifest.get("commit"), str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", manifest["commit"]):
                raise PackageError("Invalid source metadata or full commit")
            files = manifest.get("files")
            if not isinstance(files, list) or not files:
                raise PackageError("Missing source inventory")
            wanted = {manifest_name}
            source_paths = set()
            for item in files:
                if not isinstance(item, dict):
                    raise PackageError("Invalid inventory entry")
                path = safe_path(item.get("path"))
                source_path = safe_path(item.get("source_path"))
                expected_source = "telecom-research/" + path if manifest["scope"] == "telecom" else path
                if source_path != expected_source or source_path in source_paths or unsafe_source(source_path):
                    raise PackageError("Invalid or unsafe source mapping: " + source_path)
                source_paths.add(source_path)
                name = root + "/" + path
                if name in wanted or item.get("git_mode") not in ("100644", "100755"):
                    raise PackageError("Duplicate path or invalid mode in manifest: " + path)
                wanted.add(name)
                size = item.get("size")
                if isinstance(size, bool) or not isinstance(size, int) or size < 0 or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
                    raise PackageError("Invalid file size or SHA-256: " + path)
                info = bundle.getinfo(name)
                if info.file_size != size or (info.external_attr >> 16) != int(item["git_mode"], 8):
                    raise PackageError("File size or executable mode mismatch: " + path)
                sha = hashlib.sha256()
                object_format = manifest["source"].get("object_format")
                if object_format not in ("sha1", "sha256"):
                    raise PackageError("Unsupported Git object format")
                blob_hash = hashlib.new(object_format)
                blob_hash.update(b"blob " + str(size).encode("ascii") + b"\0")
                with bundle.open(name) as stream:
                    for chunk in iter(lambda: stream.read(CHUNK), b""):
                        sha.update(chunk)
                        blob_hash.update(chunk)
                if sha.hexdigest() != item["sha256"] or blob_hash.hexdigest() != item.get("git_blob"):
                    raise PackageError("Content checksum mismatch: " + path)
            generated = manifest.get("generated_files")
            if not isinstance(generated, list) or len(generated) != 1:
                raise PackageError("Missing generated handoff entry inventory")
            for item in generated:
                if not isinstance(item, dict):
                    raise PackageError("Invalid generated entry inventory")
                path = safe_path(item.get("path"))
                if path != ENTRYPOINT or root + "/" + path in wanted:
                    raise PackageError("Invalid generated entrypoint mapping")
                name = root + "/" + path
                wanted.add(name)
                generated_size = bundle.getinfo(name).file_size
                if generated_size > 65536 or type(item.get("size")) is not int or item["size"] != generated_size:
                    raise PackageError("Generated entrypoint size is invalid or exceeds 64 KiB")
                payload = bundle.read(name)
                if item.get("size") != len(payload) or item.get("sha256") != hashlib.sha256(payload).hexdigest():
                    raise PackageError("Generated entrypoint checksum mismatch")
                if payload != entrypoint(manifest):
                    raise PackageError("Generated entrypoint does not match the source handoff metadata")
            if wanted != set(names):
                raise PackageError("Archive file set differs from its complete inventory")
            if manifest["source"].get("source_file_count") != len(files) or manifest["source"].get("source_inventory_sha256") != inventory_digest(files):
                raise PackageError("Source inventory summary mismatch")
            if manifest["source"].get("complete_repository") != (manifest["scope"] == "repository"):
                raise PackageError("Source scope completeness flag mismatch")
            guide = manifest.get("handoff_entrypoint")
            if guide is not None and root + "/" + safe_path(guide) not in wanted:
                raise PackageError("Handoff entrypoint is missing")
            source_verified = False
            bio_count = 0
            if repo is not None:
                repo = repo_root(repo)
                commit = manifest.get("commit")
                if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
                    raise PackageError("Invalid full source commit")
                expected = source_tree(repo, commit, manifest["scope"])
                actual = [{key: item[key] for key in ("path", "source_path", "git_mode", "git_blob")} for item in files]
                if expected != actual or manifest["source"].get("git_tree") != git(repo, "rev-parse", commit + "^{tree}").stdout.decode("ascii").strip():
                    raise PackageError("Archive source inventory does not match the independently read Git snapshot")
                expected_format = git(repo, "rev-parse", "--show-object-format").stdout.decode("ascii").strip()
                if manifest["source"]["object_format"] != expected_format:
                    raise PackageError("Git object format mismatch")
                source_verified = True
                bio_count = sum(item["source_path"].startswith("bio-research/") for item in files)
    except (OSError, RuntimeError, zipfile.BadZipFile, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageError("Invalid package: " + str(exc)) from exc
    checksum = sha_file(archive)
    sidecar = Path(str(archive) + ".sha256")
    sidecar_verified = False
    if sidecar.exists():
        try:
            expected = checksum + "  " + archive.name + "\n"
            if sidecar.read_text(encoding="ascii") != expected:
                raise PackageError("Archive SHA-256 sidecar mismatch")
        except (OSError, UnicodeError) as exc:
            raise PackageError("Cannot read checksum sidecar") from exc
        sidecar_verified = True
    return {"ok": True, "archive": str(archive), "commit": manifest["commit"], "scope": manifest["scope"],
            "file_count": len(files), "source_verified": source_verified, "bio_research_files_verified": bio_count,
            "sha256": checksum, "sidecar_verified": sidecar_verified}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="Source Git checkout; defaults to current directory when packaging")
    parser.add_argument("--output-dir", help="Absolute external release directory")
    parser.add_argument("--scope", choices=["repository", "telecom"], default="repository")
    parser.add_argument("--ref", default="HEAD", help="Pinned current HEAD commit, optionally its full SHA")
    parser.add_argument("--version", help="Optional portable release label; otherwise project.version from Git")
    parser.add_argument("--verify", metavar="ZIP", help="Verify archive; --repo additionally proves snapshot completeness")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            if args.output_dir:
                raise PackageError("--verify does not create output; omit --output-dir")
            result = verify_archive(args.verify, args.repo)
        else:
            if not args.output_dir:
                raise PackageError("Packaging requires an absolute --output-dir")
            result = package_source(args.repo or Path.cwd(), args.output_dir, args.scope, args.ref, args.version)
        print(canonical(result).decode("utf-8"))
        return 0
    except (PackageError, OSError, ValueError) as exc:
        print(canonical({"ok": False, "error": str(exc)}).decode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
