"""Exercise bootstrap decisions using fake commands and an isolated checkout."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bootstrap test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.checkout = self.root / "checkout with spaces"
        self.checkout.mkdir()
        shutil.copy2(REPO / "bootstrap.sh", self.checkout / "bootstrap.sh")
        shutil.copytree(REPO / "bootstrap", self.checkout / "bootstrap")
        (self.checkout / "scripts").mkdir()
        self.log = self.root / "calls"
        self.fake_script(self.checkout / "setup.sh", "setup", "BOOTSTRAP_TEST_SETUP_STATUS")
        self.fake_script(self.checkout / "scripts/config-sync.sh", "sync", "BOOTSTRAP_TEST_SYNC_STATUS")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fake_script(self.bin / "stow", "stow", "BOOTSTRAP_TEST_STOW_STATUS")
        self.fake_script(self.bin / "brew", "brew", "BOOTSTRAP_TEST_BREW_STATUS")
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + "/usr/bin:/bin",
                        BOOTSTRAP_TEST_LOG=str(self.log))

    def fake_script(self, filename, label, status_var):
        filename.write_text('#!/bin/bash\nprintf "%s:%s\\n" "' + label +
                            '" "$*" >> "$BOOTSTRAP_TEST_LOG"\nexit "${' + status_var + ':-0}"\n')
        filename.chmod(0o755)

    def run_bootstrap(self, *args, env=None):
        return subprocess.run(["/bin/bash", str(self.checkout / "bootstrap.sh"), *args],
                              cwd=self.root, env=env or self.env, capture_output=True, text=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_check_is_read_only_and_does_not_run_brew_or_sync(self):
        isolated = self.root / "not created"
        result = self.run_bootstrap("check", "--home", str(isolated))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(isolated.exists())
        self.assertEqual(self.calls(), [f"setup:--dry-run --home {isolated}"])
        self.assertIn("optional", result.stdout)

    def test_selected_missing_tools_and_stow_failure_are_reported(self):
        result = self.run_bootstrap("check", "--home", str(self.root / "home"), "--group", "shell")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing nu (selected)", result.stdout)
        (self.bin / "stow").unlink()
        self.log.unlink(missing_ok=True)
        result = self.run_bootstrap("check", "--home", str(self.root / "home"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Config preview skipped", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_failed_preview_is_reported(self):
        env = dict(self.env, BOOTSTRAP_TEST_SETUP_STATUS="1")
        result = self.run_bootstrap("check", "--home", str(self.root / "home"), env=env)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.calls()), 1)

    def test_alternate_home_never_runs_current_user_sync(self):
        isolated = self.root / "test home"
        result = self.run_bootstrap("install", "--home", str(isolated))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [f"setup:--home {isolated}"])
        self.assertIn("Skipped current-user config sync", result.stdout)

    def test_install_only_runs_selected_brewfiles_when_explicitly_requested(self):
        result = self.run_bootstrap("install", "--install-packages", "--group", "shell", "--group", "work")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(calls[:3], [
            f"brew:bundle install --no-upgrade --file={self.checkout}/bootstrap/Brewfile.core",
            f"brew:bundle install --no-upgrade --file={self.checkout}/bootstrap/Brewfile.shell",
            f"brew:bundle install --no-upgrade --file={self.checkout}/bootstrap/Brewfile.work",
        ])
        self.assertEqual(calls[-1], "sync:--strict")
        self.assertFalse(any("Brewfile.desktop" in call for call in calls))

    def test_failures_stop_later_mutations(self):
        env = dict(self.env, BOOTSTRAP_TEST_BREW_STATUS="1")
        result = self.run_bootstrap("install", "--install-packages", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.log.unlink()
        env = dict(self.env, BOOTSTRAP_TEST_SETUP_STATUS="1")
        result = self.run_bootstrap("install", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.log.unlink()
        env = dict(self.env, BOOTSTRAP_TEST_SYNC_STATUS="1")
        result = self.run_bootstrap("install", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls()[-1], "sync:--strict")

    def test_invalid_options_do_not_invoke_installers(self):
        for args in (("check", "--install-packages"), ("check", "--group", "bad"),
                     ("install", "--group", "shell"), ("install", "--home")):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_bootstrap(*args).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_current_user_sync_preview_detects_collisions_without_mutating_links(self):
        source = self.root / "managed"
        target = self.root / "agent-target"
        source.mkdir()
        target.mkdir()
        (source / "demo").mkdir()
        link = target / "demo"
        link.symlink_to(self.root / "unrelated")
        bootstrap = self.checkout / "bootstrap.sh"
        script = bootstrap.read_text()
        for old, new in [
            ('$HOME/.config/agents/skills', str(source)),
            ('$HOME/.agents/skills', str(target)),
            ('$HOME/.local/bin/azt', str(self.root / "azt")),
            ('$HOME/.config/scripts/azt', str(self.root / "managed-azt")),
        ]:
            script = script.replace(old, new)
        bootstrap.write_text(script)
        result = self.run_bootstrap("check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(f"sync collision: {link}", result.stdout)
        self.assertEqual(os.readlink(link), str(self.root / "unrelated"))
        link.unlink()
        link.symlink_to(source / "demo")
        result = self.run_bootstrap("check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("sync collision:", result.stdout)


if __name__ == "__main__":
    unittest.main()
