"""Exercise config sync against temporary paths, never the user's home."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts/lib/skill-sync.sh"


class SkillLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skill-sync-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source skills"
        self.target = self.root / "target skills"
        self.source.mkdir()
        self.target.mkdir()

    def sync(self):
        return subprocess.run(
            ["/bin/bash", "-euc", 'source "$1"; sync_skill_links "$2" "$3"',
             "_", str(LIB), str(self.source), str(self.target)],
            text=True, capture_output=True,
        )

    def test_create_and_repeat_are_idempotent(self):
        (self.source / "one skill").mkdir()
        self.assertEqual(self.sync().returncode, 0)
        link = self.target / "one skill"
        self.assertEqual(os.readlink(link), str(self.source / "one skill"))
        before = link.lstat().st_mtime_ns
        self.assertEqual(self.sync().returncode, 0)
        self.assertEqual(link.lstat().st_mtime_ns, before)

    def test_remove_only_stale_links_to_matching_managed_paths(self):
        managed = self.target / "removed"
        managed.symlink_to(self.source / "removed")
        unrelated = self.target / "other"
        unrelated.symlink_to(self.root / "unmounted" / "other")
        mismatch = self.target / "mismatch"
        mismatch.symlink_to(self.source / "different")
        self.assertEqual(self.sync().returncode, 0)
        self.assertFalse(managed.is_symlink())
        self.assertTrue(unrelated.is_symlink())
        self.assertTrue(mismatch.is_symlink())

    def test_missing_source_never_prunes(self):
        self.source.rmdir()
        link = self.target / "missing"
        link.symlink_to(self.source / "missing")
        self.assertEqual(self.sync().returncode, 0)
        self.assertTrue(link.is_symlink())

    def test_collisions_are_preserved_reported_and_do_not_stop_other_links(self):
        for name in ("file", "directory", "external", "dangling", "available"):
            (self.source / name).mkdir()
        (self.target / "file").write_text("keep")
        (self.target / "directory").mkdir()
        external = self.root / "external"
        external.mkdir()
        (self.target / "external").symlink_to(external)
        (self.target / "dangling").symlink_to(self.root / "missing")
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        for name in ("file", "directory", "external", "dangling"):
            self.assertIn(str(self.target / name), result.stderr)
        self.assertEqual((self.target / "file").read_text(), "keep")
        self.assertEqual(os.readlink(self.target / "external"), str(external))
        self.assertEqual(os.readlink(self.target / "dangling"), str(self.root / "missing"))
        self.assertEqual((self.target / "available").resolve(), self.source / "available")


class SyncRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sync-runner-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runner = self.root / "config-sync.sh"
        shutil.copy2(REPO / "scripts/config-sync.sh", self.runner)
        self.tasks = self.root / "config-sync.d"
        self.tasks.mkdir()
        self.marker = self.root / "ran"
        self.task("01-fail.sh", "exit 7")
        self.task("02-succeed.sh", 'printf done > "$SYNC_TEST_MARKER"')
        self.env = dict(os.environ, SYNC_TEST_MARKER=str(self.marker))

    def task(self, name, script):
        path = self.tasks / name
        path.write_text("#!/bin/bash\n" + script + "\n")
        path.chmod(0o755)

    def run_sync(self, *args):
        return subprocess.run(["/bin/bash", str(self.runner), *args], env=self.env,
                              capture_output=True, text=True)

    def test_startup_reports_failure_but_returns_success_and_continues(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0)
        self.assertIn("01-fail.sh (exit 7)", result.stderr)
        self.assertEqual(self.marker.read_text(), "done")

    def test_strict_returns_failure_after_running_all_tasks(self):
        result = self.run_sync("--strict", "--debug")
        self.assertEqual(result.returncode, 1)
        self.assertIn("01-fail.sh (exit 7)", result.stderr)
        self.assertIn("02-succeed.sh", result.stderr)
        self.assertNotIn("config sync completed", result.stderr.lower())
        self.assertEqual(self.marker.read_text(), "done")

    def test_strict_success_and_invalid_option(self):
        (self.tasks / "01-fail.sh").unlink()
        self.assertEqual(self.run_sync("--strict").returncode, 0)
        self.assertEqual(self.run_sync("--unknown").returncode, 2)


class TaskIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sync-tasks-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.scripts = self.root / "scripts"
        shutil.copytree(REPO / "scripts/config-sync.d", self.scripts / "config-sync.d")
        (self.scripts / "lib").mkdir()
        shutil.copy2(LIB, self.scripts / "lib/skill-sync.sh")
        self.source = self.root / "managed skills"
        self.source.mkdir()
        (self.source / "demo").mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for cli in ("codex", "copilot"):
            path = self.bin / cli
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"])

    def test_all_skill_tasks_use_shared_ownership_rules(self):
        tasks = {
            "00-codex-skills.sh": '"$HOME/.codex/skills"',
            "01-copilot-skills.sh": '"${COPILOT_HOME:-$HOME/.copilot}/skills"',
            "02-agent-skills.sh": '"$HOME/.agents/skills"',
        }
        for script, target_expression in tasks.items():
            with self.subTest(task=script):
                path = self.scripts / "config-sync.d" / script
                target = self.root / (script + " target")
                content = path.read_text().replace('"$HOME/.config/agents/skills"',
                                                   '"' + str(self.source) + '"')
                content = content.replace(target_expression, '"' + str(target) + '"')
                path.write_text(content)
                first = subprocess.run(["/bin/bash", str(path)], env=self.env,
                                       capture_output=True, text=True)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual((target / "demo").resolve(), self.source / "demo")
                (target / "demo").unlink()
                (target / "demo").symlink_to(self.root / "unrelated")
                second = subprocess.run(["/bin/bash", str(path)], env=self.env,
                                        capture_output=True, text=True)
                self.assertNotEqual(second.returncode, 0)
                self.assertIn("preserved conflicting path", second.stderr)
                self.assertEqual(os.readlink(target / "demo"), str(self.root / "unrelated"))

    def test_azt_preserves_an_unrelated_symlink(self):
        path = self.scripts / "config-sync.d/10-azt.sh"
        source = self.root / "managed-azt"
        source.write_text("#!/bin/sh\n")
        source.chmod(0o755)
        target_dir = self.root / "local-bin"
        target_dir.mkdir()
        (target_dir / "azt").symlink_to(self.root / "unrelated-azt")
        content = path.read_text().replace('$HOME/.config/scripts/azt', str(source))
        content = content.replace('$HOME/.local/bin', str(target_dir))
        path.write_text(content)
        result = subprocess.run(["/bin/bash", str(path)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preserved conflicting path", result.stderr)
        self.assertEqual(os.readlink(target_dir / "azt"), str(self.root / "unrelated-azt"))

    def test_stowed_task_finds_library_before_library_is_stowed(self):
        task = self.scripts / "config-sync.d/02-agent-skills.sh"
        target = self.root / "agent skills"
        content = task.read_text().replace('"$HOME/.config/agents/skills"',
                                           '"' + str(self.source) + '"')
        content = content.replace('"$HOME/.agents/skills"', '"' + str(target) + '"')
        task.write_text(content)
        installed = self.root / "installed/config-sync.d"
        installed.mkdir(parents=True)
        link = installed / task.name
        link.symlink_to(os.path.relpath(task, installed))
        result = subprocess.run(["/bin/bash", str(link)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((target / "demo").resolve(), self.source / "demo")


if __name__ == "__main__":
    unittest.main()
