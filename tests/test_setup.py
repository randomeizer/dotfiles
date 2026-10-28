"""Exercise the real Stow installer without touching the live home directory."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
CONFIG_DIRS = {
    "aerospace", "agents", "atuin", "ghostty", "hammerspoon", "karabiner",
    "nushell", "nvim", "powershell", "scripts",
    "sketchybar", "skhd", "ssh", "starship", "tmux", "wezterm", "zellij", "zshrc",
}


@unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix="dotfiles-source-")
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.template = Path(cls.fixture.name) / "checkout"
        files = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=REPO
        ).decode().split("\0")
        # Include new installer policy before the change has been staged.
        for relative in set(files) | {".stow-local-ignore"}:
            if not relative or not (REPO / relative).is_file():
                continue
            dest = cls.template / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, dest)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dotfiles-install-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.checkout = self.root / "checkout with spaces"
        shutil.copytree(self.template, self.checkout)
        self.home = self.root / "home"
        self.config = self.home / ".config"
        self.caller = self.root / "unrelated working directory"
        self.caller.mkdir()

    def run_setup(self, *args, entry="setup.sh", expected=0):
        result = subprocess.run(
            ["/bin/bash", str(self.checkout / entry), "--home", str(self.home), *args],
            cwd=self.caller, capture_output=True, text=True,
        )
        if expected == 0:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def snapshot(self):
        if not self.home.exists():
            return None
        result = {}
        for p in self.home.rglob("*"):
            if p.is_symlink():
                value = ("link", os.readlink(p))
            elif p.is_file():
                value = ("file", p.read_bytes())
            else:
                value = ("directory",)
            result[str(p.relative_to(self.home))] = (value, p.lstat().st_mtime_ns)
        return result

    def test_install_from_other_directory_has_expected_manifest(self):
        # Neither caller policy nor an unexpected source directory is deployed.
        (self.caller / ".stowrc").write_text("--ignore=.*\n")
        (self.checkout / "new-unapproved-config").mkdir()
        (self.checkout / "new-unapproved-config/config").write_text("not approved")
        (self.checkout / "tests").mkdir(exist_ok=True)
        (self.checkout / "tests/sentinel").write_text("repository only")
        self.run_setup()
        self.assertEqual({p.name for p in self.config.iterdir()}, CONFIG_DIRS)
        self.assertEqual(
            (self.config / "atuin/config.toml").resolve(),
            self.checkout / "atuin/config.toml",
        )
        self.assertEqual((self.home / ".zshrc").resolve(), self.checkout / "zshrc/.zshrc")
        self.assertEqual((self.home / ".hammerspoon").resolve(), self.config / "hammerspoon")
        self.assertFalse((self.home / ".ssh").exists())

    def test_repeat_install_does_not_change_paths_or_mtimes(self):
        self.run_setup()
        before = self.snapshot()
        self.run_setup()
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_does_not_create_missing_home(self):
        result = self.run_setup("--dry-run")
        self.assertIn("Would install", result.stdout)
        self.assertIn("Would link", result.stdout)
        self.assertIn("LINK: atuin/config.toml", result.stderr)
        self.assertFalse(self.home.exists())

    def test_dry_run_does_not_change_existing_home(self):
        self.config.mkdir(parents=True)
        before = self.snapshot()
        self.run_setup("--dry-run")
        self.assertEqual(self.snapshot(), before)

    def test_existing_native_files_and_directories_are_preserved(self):
        self.home.mkdir()
        (self.home / ".zshrc").write_text("my shell config\n")
        (self.home / ".hammerspoon").mkdir()
        (self.home / ".hammerspoon/init.lua").write_text("-- my desktop\n")
        result = self.run_setup()
        self.assertIn("Preserved existing path", result.stderr)
        self.assertEqual((self.home / ".zshrc").read_text(), "my shell config\n")
        self.assertEqual((self.home / ".hammerspoon/init.lua").read_text(), "-- my desktop\n")

    def test_native_unrelated_and_dangling_symlinks_are_preserved(self):
        self.home.mkdir()
        external = self.root / "external-shell"
        external.write_text("my shell\n")
        (self.home / ".zshrc").symlink_to(external)
        missing = self.root / "unmounted-desktop"
        (self.home / ".hammerspoon").symlink_to(missing)
        self.run_setup()
        self.assertEqual(os.readlink(self.home / ".zshrc"), str(external))
        self.assertEqual(os.readlink(self.home / ".hammerspoon"), str(missing))
        self.assertFalse(missing.exists())

    def test_stow_conflict_preserves_content_and_does_not_add_bridges(self):
        (self.config / "atuin").mkdir(parents=True)
        conflict = self.config / "atuin/config.toml"
        conflict.write_text("my Atuin settings\n")
        before = self.snapshot()
        self.run_setup(expected=1)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.home / ".zshrc").is_symlink())

    def test_conflicts_are_also_detected_in_dry_run(self):
        (self.config / "atuin").mkdir(parents=True)
        (self.config / "atuin/config.toml").write_text("keep\n")
        before = self.snapshot()
        self.run_setup("--dry-run", expected=1)
        self.assertEqual(self.snapshot(), before)

    def test_ssh_is_opt_in_and_preserves_existing_config(self):
        self.run_setup("--with-ssh")
        self.assertEqual((self.home / ".ssh/config").resolve(), self.checkout / "ssh/ssh-config")
        (self.home / ".ssh/config").unlink()
        (self.home / ".ssh/config").write_text("Host my-host\n")
        self.run_setup("--with-ssh")
        self.assertEqual((self.home / ".ssh/config").read_text(), "Host my-host\n")

    def test_explicit_relative_paths_are_resolved_from_caller(self):
        self.run_setup("--target", "../alternate config")
        target = self.root / "alternate config"
        self.assertEqual({p.name for p in target.iterdir()}, CONFIG_DIRS)
        self.assertEqual((self.home / ".zshrc").resolve(), self.checkout / "zshrc/.zshrc")

    def test_legacy_shell_entrypoint_uses_same_preservation_rules(self):
        self.run_setup()
        (self.home / ".zshrc").unlink()
        before = {p.name for p in self.home.iterdir()}
        self.run_setup(entry="setup-shells.sh")
        self.assertEqual((self.home / ".zshrc").resolve(), self.checkout / "zshrc/.zshrc")
        self.assertEqual({p.name for p in self.home.iterdir()}, before | {".zshrc"})
        (self.home / ".zshrc").unlink()
        (self.home / ".zshrc").symlink_to(self.root / "missing-shell")
        self.run_setup(entry="setup-shells.sh")
        self.assertEqual(os.readlink(self.home / ".zshrc"), str(self.root / "missing-shell"))

    def test_shell_only_requires_installed_config(self):
        self.run_setup(entry="setup-shells.sh", expected=1)
        self.assertFalse(self.home.exists())

    def test_symlinked_installer_resolves_checkout(self):
        link = self.caller / "install"
        link.symlink_to(self.checkout / "setup.sh")
        result = subprocess.run(
            ["/bin/bash", str(link), "--home", str(self.home)],
            cwd=self.caller, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.config / "atuin/config.toml").is_file())

    def test_nested_metadata_and_python_cache_are_not_deployed(self):
        cache = self.checkout / "nvim/__pycache__"
        cache.mkdir()
        (cache / "cache.pyc").write_bytes(b"generated")
        self.run_setup()
        self.assertFalse((self.config / "nvim/__pycache__").exists())
        self.assertFalse((self.config / "nvim/.gitignore").exists())

    def test_existing_correct_folded_config_link_is_kept(self):
        self.config.mkdir(parents=True)
        # Reproduce the old `stow .` layout with actual Stow-owned relative links.
        result = subprocess.run(
            ["stow", "--dir", str(self.checkout), "--target", str(self.config), "."],
            cwd=self.checkout, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = os.readlink(self.config / "aerospace")
        self.run_setup()
        self.assertEqual(os.readlink(self.config / "aerospace"), before)

    def test_missing_option_value_and_unknown_arguments_fail_without_writes(self):
        self.run_setup("--target", expected=1)
        self.run_setup("--unknown", expected=1)
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
