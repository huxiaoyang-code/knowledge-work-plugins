"""Exercise release integrity using tiny temporary Git repositories only."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import warnings
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_source.py"
SPEC = importlib.util.spec_from_file_location("telecom_package_source", SCRIPT)
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "source repo 通信"
        self.repo.mkdir()
        self.git("init", "-b", "test-release")
        self.git("config", "user.name", "Synthetic Packaging Test")
        self.git("config", "user.email", "packaging@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("remote", "add", "origin", "https://example.invalid/source-fixture.git")
        self.write("README.md", "Synthetic complete repository source.\n")
        self.write("LICENSE", "Synthetic fixture license bytes\r\n")
        self.write(".gitignore", "ignored-state/\n.env\n*.token\n")
        self.write(".gitattributes", "other/hidden.md export-ignore\nother/template.txt export-subst\n")
        self.write("bio-research/README.md", "Original bio source must remain byte-identical.\r\n")
        self.write("other/hidden.md", "Tracked file despite export-ignore.\n")
        self.write("other/template.txt", "$Format:%H$\n")
        self.write("other/图片 asset.bin", bytes(range(256)))
        self.write("telecom-research/pyproject.toml", '[project]\nname="fixture"\nversion="0.1.0"\n')
        self.write("telecom-research/docs/CODEX_HANDOFF.md", "Synthetic coworker entrypoint.\n")
        self.write("telecom-research/.env.example", "API_KEY=example-not-a-key\n")
        self.write("telecom-research/.agents/skills/package-test/SKILL.md", "Synthetic packaging skill.\n")
        self.commit()
        self.output = self.root / "releases 同事"

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args, input=None):
        result = subprocess.run(["git", "-C", str(self.repo), *args], input=input, capture_output=True, check=True)
        return result.stdout

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-m", "Synthetic fixture snapshot")
        return self.git("rev-parse", "HEAD").decode().strip()

    def package(self, scope="repository", output=None):
        return packaging.package_source(self.repo, output or self.output, scope)

    def contents(self, archive):
        with zipfile.ZipFile(archive) as bundle:
            root = bundle.namelist()[0].split("/")[0]
            manifest = json.loads(bundle.read(root + "/" + packaging.MANIFEST))
            contents = {name[len(root) + 1:]: bundle.read(name) for name in bundle.namelist()}
            return root, manifest, contents

    def rewrite(self, source, name, change):
        target = self.root / name
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as altered:
            for info in original.infolist():
                payload = original.read(info.filename)
                replacement = change(info.filename, payload)
                if replacement is not None:
                    altered.writestr(info, replacement)
        return target

    def test_full_snapshot_preserves_all_source_bytes_and_is_reproducible(self):
        self.write("ignored-state/manager.token", "ignored-secret")
        self.write(".env", "ignored-secret")
        self.git("sparse-checkout", "init", "--cone")
        self.git("sparse-checkout", "set", "telecom-research")
        self.assertFalse((self.repo / "bio-research/README.md").exists())
        result = self.package()
        self.assertTrue(result["source_verified"])
        self.assertTrue(result["sidecar_verified"])
        self.assertEqual(result["bio_research_files_verified"], 1)
        root, manifest, contents = self.contents(result["archive"])
        self.assertTrue(root.startswith("knowledge-work-plugins-v0.1.0-"))
        self.assertEqual(contents["bio-research/README.md"], b"Original bio source must remain byte-identical.\r\n")
        self.assertEqual(contents["other/图片 asset.bin"], bytes(range(256)))
        self.assertIn("other/hidden.md", contents)
        self.assertEqual(contents["other/template.txt"], b"$Format:%H$\n")
        self.assertNotIn(".env", contents)
        self.assertFalse(any("manager.token" in name or name.startswith(".git/") for name in contents))
        self.assertEqual(manifest["handoff_entrypoint"], "telecom-research/docs/CODEX_HANDOFF.md")
        self.assertEqual(manifest["validation"]["tests"], "not_run_by_packager")
        self.assertEqual(manifest["source"]["source_file_count"], len(contents) - 2)
        self.assertIn(packaging.ENTRYPOINT, contents)
        self.assertIn(b"telecom-research/docs/CODEX_HANDOFF.md", contents[packaging.ENTRYPOINT])
        again = self.package(output=self.root / "second-release")
        self.assertEqual(Path(again["archive"]).read_bytes(), Path(result["archive"]).read_bytes())
        self.assertEqual(self.package()["sha256"], result["sha256"])

    def test_telecom_scope_keeps_full_feature_and_portable_handoff(self):
        result = self.package("telecom")
        root, manifest, contents = self.contents(result["archive"])
        self.assertTrue(root.startswith("telecom-research-v0.1.0-"))
        self.assertEqual(manifest["handoff_entrypoint"], "docs/CODEX_HANDOFF.md")
        self.assertIn(".agents/skills/package-test/SKILL.md", contents)
        self.assertIn(".env.example", contents)
        self.assertNotIn("bio-research/README.md", contents)
        self.assertFalse(manifest["source"]["complete_repository"])

    def test_refuses_dirty_tracked_and_nonignored_untracked_files(self):
        self.write("README.md", "Uncommitted edit")
        with self.assertRaisesRegex(packaging.PackageError, "dirty"):
            self.package()
        self.commit()
        self.write("telecom-research/new-source.py", "print('untracked source')")
        with self.assertRaisesRegex(packaging.PackageError, "new-source.py"):
            self.package()
        self.assertTrue((self.repo / "telecom-research/new-source.py").exists())

    def test_refuses_tracked_secret_without_printing_contents(self):
        self.write("telecom-research/auth.json", '{"api_key":"fixture-secret-not-to-display"}')
        self.commit()
        with self.assertRaises(packaging.PackageError) as raised:
            self.package()
        self.assertIn("auth.json", str(raised.exception))
        self.assertNotIn("fixture-secret", str(raised.exception))

    def test_refuses_old_commit_output_in_source_and_runtime_state(self):
        old = self.git("rev-parse", "HEAD").decode().strip()
        self.write("new.md", "new source")
        self.commit()
        with self.assertRaisesRegex(packaging.PackageError, "current HEAD"):
            packaging.package_source(self.repo, self.output, ref=old)
        with self.assertRaisesRegex(packaging.PackageError, "outside the source"):
            self.package(output=self.repo / "releases")
        state = self.root / "state"
        state.mkdir()
        (state / "manager.token").write_text("fixture-only")
        with self.assertRaisesRegex(packaging.PackageError, "runtime state"):
            self.package(output=state / "releases")

    def test_detects_content_tampering_and_checksum_sidecar_tampering(self):
        result = self.package()
        altered = self.rewrite(result["archive"], "tampered.zip", lambda name, payload: b"changed source bytes" if name.endswith("/README.md") else payload)
        with self.assertRaises(packaging.PackageError):
            packaging.verify_archive(altered)
        Path(result["checksum_file"]).write_text("0" * 64 + "  wrong.zip\n", encoding="ascii")
        with self.assertRaisesRegex(packaging.PackageError, "sidecar mismatch"):
            packaging.verify_archive(result["archive"])

    def test_independent_git_check_detects_self_consistent_source_omission(self):
        result = self.package()
        _, manifest, _ = self.contents(result["archive"])
        omitted = "other/hidden.md"
        forged = copy.deepcopy(manifest)
        forged["files"] = [item for item in forged["files"] if item["path"] != omitted]
        forged["source"]["source_file_count"] = len(forged["files"])
        forged["source"]["source_inventory_sha256"] = packaging.inventory_digest(forged["files"])
        def change(name, payload):
            if name.endswith("/" + omitted):
                return None
            if name.endswith("/" + packaging.MANIFEST):
                return packaging.canonical(forged)
            return payload
        altered = self.rewrite(result["archive"], "omitted.zip", change)
        self.assertFalse(packaging.verify_archive(altered)["source_verified"])
        with self.assertRaisesRegex(packaging.PackageError, "independently read Git"):
            packaging.verify_archive(altered, self.repo)

    def test_rejects_traversal_duplicate_and_unlisted_paths(self):
        result = self.package()
        for extra in ("../escape", "C:/escape", "root\\escape", "new-root/file.txt"):
            altered = self.root / ("path-" + hashlib.sha256(extra.encode()).hexdigest()[:8] + ".zip")
            shutil_copy = Path(result["archive"]).read_bytes()
            altered.write_bytes(shutil_copy)
            with zipfile.ZipFile(altered, "a") as bundle:
                bundle.writestr(extra, b"unlisted")
            with self.assertRaises(packaging.PackageError):
                packaging.verify_archive(altered)
        duplicate = self.root / "duplicate.zip"
        duplicate.write_bytes(Path(result["archive"]).read_bytes())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "a") as bundle:
                name = bundle.namelist()[0]
                bundle.writestr(name, b"duplicate")
        with self.assertRaisesRegex(packaging.PackageError, "duplicate"):
            packaging.verify_archive(duplicate)

    def test_rejects_gitlinks_and_symlinks_in_commit_without_following_them(self):
        head = self.git("rev-parse", "HEAD").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", "160000," + head + ",external-module")
        self.git("commit", "-m", "Synthetic gitlink")
        self.git("update-index", "--skip-worktree", "external-module")
        with self.assertRaisesRegex(packaging.PackageError, "Submodule"):
            self.package()
        self.git("update-index", "--force-remove", "external-module")
        blob = self.git("hash-object", "-w", "--stdin", input=b"../outside-target").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", "120000," + blob + ",external-link")
        self.git("commit", "-m", "Synthetic symlink")
        self.git("update-index", "--skip-worktree", "external-link")
        with self.assertRaisesRegex(packaging.PackageError, "Symbolic link"):
            self.package()

    def test_rejects_malformed_manifest_and_generated_entry_tamper(self):
        result = self.package()
        malformed = self.rewrite(result["archive"], "malformed.zip", lambda name, payload: b"[]" if name.endswith("/" + packaging.MANIFEST) else payload)
        with self.assertRaises(packaging.PackageError):
            packaging.verify_archive(malformed)
        tampered = self.rewrite(result["archive"], "entrypoint-tamper.zip", lambda name, payload: b"changed handoff" if name.endswith("/" + packaging.ENTRYPOINT) else payload)
        with self.assertRaises(packaging.PackageError):
            packaging.verify_archive(tampered)

    def test_standard_ssh_origin_allowed_and_embedded_credentials_rejected(self):
        ssh_origin = "ssh://git@github.com/huxiaoyang-code/knowledge-work-plugins.git"
        self.git("remote", "set-url", "origin", ssh_origin)
        result = self.package()
        _, manifest, _ = self.contents(result["archive"])
        self.assertEqual(manifest["repository_url"], ssh_origin)
        for origin in (
            "https://user:fixture-secret@github.com/huxiaoyang-code/knowledge-work-plugins.git",
            "ssh://git:fixture-secret@github.com/huxiaoyang-code/knowledge-work-plugins.git",
            "https://github.com/huxiaoyang-code/knowledge-work-plugins.git?token=fixture-secret",
        ):
            self.git("remote", "set-url", "origin", origin)
            with self.assertRaises(packaging.PackageError) as raised:
                self.package(output=self.root / "rejected-release")
            self.assertNotIn("fixture-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
