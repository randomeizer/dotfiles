"""Exercise startup with isolated config/cache paths and fake integrations."""

import json
import fcntl
from concurrent.futures import ThreadPoolExecutor
import os
import pty
from pathlib import Path
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import time
import unittest


REPO = Path(__file__).resolve().parents[1]


class ZshStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zsh-startup-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls"
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + "/usr/bin:/bin",
                        ZDOTDIR=str(self.root), XDG_CACHE_HOME=str(self.root / "cache"),
                        STARTUP_TEST_LOG=str(self.log), TERM="xterm", TERM_PROGRAM="test")
        self.config = REPO / "zshrc/300_integrations.zsh"

    def fake_tool(self, name, failure=False):
        path = self.bin / name
        path.write_text('#!/bin/sh\nprintf "%s\\n" "' + name + '" >> "$STARTUP_TEST_LOG"\n'
                        'printf "typeset -g DOTFILES_TEST_INITIALIZED=yes\\n"\n'
                        + ('exit 7\n' if failure else 'exit 0\n'))
        path.chmod(0o755)
        return path

    def run_zsh(self, interactive):
        args = ["/bin/zsh", "-f"] + (["-i"] if interactive else [])
        args += ["-c", 'source "$1"; print -r -- "${DOTFILES_TEST_INITIALIZED:-missing}"',
                 "fixture", str(self.config)]
        return subprocess.run(args, env=self.env, capture_output=True, text=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_noninteractive_and_missing_tools_do_not_generate_caches(self):
        self.fake_tool("starship")
        result = self.run_zsh(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.root / "cache").exists())
        (self.bin / "starship").unlink()
        result = self.run_zsh(True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("command not found", result.stderr)
        self.assertFalse((self.root / "cache").exists())

    def test_cold_warm_tool_change_and_failed_refresh(self):
        tools = ["starship", "kubectl", "fzf", "direnv", "zoxide", "atuin"]
        for name in tools:
            self.fake_tool(name)
        first = self.run_zsh(True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("yes", first.stdout)
        self.assertCountEqual(self.calls(), tools)
        warm = self.run_zsh(True)
        self.assertEqual(warm.returncode, 0, warm.stderr)
        self.assertEqual(len(self.calls()), len(tools))
        cache = self.root / "cache/dotfiles-shell/zsh/starship.zsh"
        old = cache.read_bytes()
        tool = self.fake_tool("starship", failure=True)
        timestamp = cache.stat().st_mtime + 5
        os.utime(tool, (timestamp, timestamp))
        failed = self.run_zsh(True)
        self.assertEqual(failed.returncode, 0, failed.stderr)
        self.assertEqual(cache.read_bytes(), old)
        self.assertEqual(self.calls().count("starship"), 2)
        self.fake_tool("starship")
        os.utime(tool, (timestamp, timestamp))
        refreshed = self.run_zsh(True)
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        self.assertEqual(self.calls().count("starship"), 3)

    def test_concurrent_shells_leave_a_complete_cache(self):
        self.fake_tool("starship")
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.run_zsh(True), range(4)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("yes", result.stdout)
        cache_dir = self.root / "cache/dotfiles-shell/zsh"
        self.assertIn("DOTFILES_TEST_INITIALIZED=yes", (cache_dir / "starship.zsh").read_text())
        self.assertEqual([p.name for p in cache_dir.iterdir()], ["starship.zsh"])

    def test_unrelated_cache_file_and_dangling_link_are_preserved(self):
        self.fake_tool("starship")
        cache = self.root / "cache/dotfiles-shell/zsh/starship.zsh"
        cache.parent.mkdir(parents=True)
        cache.write_text("# user content\n")
        self.assertEqual(self.run_zsh(True).returncode, 0)
        self.assertEqual(cache.read_text(), "# user content\n")
        self.assertEqual(self.calls(), [])
        cache.unlink()
        cache.symlink_to(self.root / "missing")
        self.assertEqual(self.run_zsh(True).returncode, 0)
        self.assertTrue(cache.is_symlink())
        self.assertFalse((self.root / "missing").exists())


@unittest.skipUnless(shutil.which("nu"), "Nushell is required")
class NushellStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nu-startup-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls"
        self.home = self.root / "fixture-home"
        self.data = self.root / "data"
        (self.root / "config/nushell").mkdir(parents=True)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + "/usr/bin:/bin",
                        XDG_DATA_HOME=str(self.data), XDG_CONFIG_HOME=str(self.root / "config"),
                        STARTUP_TEST_LOG=str(self.log), TERM="xterm")
        env = (REPO / "nushell/env.nu").read_text()
        config = (REPO / "nushell/config.nu").read_text()
        original_home = "let home = ($env.HOME? | default $nu.home-dir)"
        for name, contents in (("env.nu", env), ("config.nu", config)):
            contents = contents.replace(original_home, "let home = " + json.dumps(str(self.home)))
            if name == "env.nu":
                contents = contents.replace("path add /opt/homebrew/bin", "path add " + json.dumps(str(self.bin)))
                contents = contents.replace("path add '~/.local/bin'", "")
                contents = contents.replace("path add ($env.HOME | path join 'go' 'bin')", "")
            (self.root / name).write_text(contents)
        self.nu = shutil.which("nu")

    def fake_tool(self, name, failure=False):
        path = self.bin / name
        output = 'export-env { $env.DOTFILES_TEST_STARSHIP = "ready" }' if name == "starship" else "# carapace init"
        path.write_text('#!/bin/sh\nprintf "%s\\n" "' + name + '" >> "$STARTUP_TEST_LOG"\n'
                        "printf '%s\\n' '" + output + "'\n" + ('exit 7\n' if failure else 'exit 0\n'))
        path.chmod(0o755)
        return path

    def run_nu(self, interactive):
        args = [self.nu, "--env-config", str(self.root / "env.nu"), "--config", str(self.root / "config.nu")]
        if interactive:
            args.append("-i")
        args += ["-c", '$env.DOTFILES_TEST_STARSHIP? | default "missing"']
        return subprocess.run(args, env=self.env, capture_output=True, text=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def run_repl(self):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        def attach_tty():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        process = subprocess.Popen(
            [self.nu, "--env-config", str(self.root / "env.nu"), "--config", str(self.root / "config.nu")],
            env=self.env, stdin=slave, stdout=slave, stderr=slave, preexec_fn=attach_tty,
        )
        os.close(slave)
        output = b""
        try:
            deadline = time.monotonic() + 10
            sent = False
            cursor_queries = 0
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output += chunk
                    # Reedline asks the terminal for its cursor position. A PTY
                    # has no terminal emulator, so supply a valid response.
                    new_queries = output.count(b"\x1b[6n")
                    for _ in range(new_queries - cursor_queries):
                        os.write(master, b"\x1b[1;1R")
                    cursor_queries = new_queries
                if not sent and b'> ' in output:
                    os.write(master, b'print $"DOTFILES_MARKER=($env.DOTFILES_TEST_STARSHIP? | default missing)"\n')
                    sent = True
                if b'DOTFILES_MARKER=ready\r\n' in output:
                    return output.decode(errors="replace")
                if process.poll() is not None and not ready:
                    break
            self.fail("interactive Nu did not load the cached prompt: " + output[-3000:].decode(errors="replace"))
        finally:
            os.close(master)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    def test_noninteractive_does_not_generate_and_missing_tools_are_safe(self):
        self.fake_tool("starship")
        self.fake_tool("carapace")
        result = self.run_nu(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.home / ".cache/carapace/init.nu").exists())
        (self.bin / "starship").unlink()
        (self.bin / "carapace").unlink()
        result = self.run_nu(True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("command not found", result.stderr.lower())

    def test_config_without_env_file_skips_unavailable_cache_helper(self):
        self.fake_tool("starship")
        result = subprocess.run(
            [self.nu, "--config", str(self.root / "config.nu"), "-i", "-c", 'print "ok"'],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)
        self.assertNotIn("command not found", result.stderr.lower())
        self.assertFalse((self.data / "nushell/vendor/autoload/starship.nu").exists())

    def test_refresh_cache_and_preserve_user_autoload(self):
        self.fake_tool("starship")
        self.fake_tool("carapace")
        first = self.run_nu(True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertCountEqual(self.calls(), ["starship", "carapace"])
        self.assertIn("DOTFILES_MARKER=ready", self.run_repl())
        warm = self.run_nu(True)
        self.assertEqual(warm.returncode, 0, warm.stderr)
        self.assertEqual(len(self.calls()), 2)
        cache = self.data / "nushell/vendor/autoload/starship.nu"
        self.assertTrue(cache.is_file())
        old = cache.read_bytes()
        tool = self.fake_tool("starship", failure=True)
        timestamp = cache.stat().st_mtime + 5
        os.utime(tool, (timestamp, timestamp))
        failed = self.run_nu(True)
        self.assertEqual(failed.returncode, 0, failed.stderr)
        self.assertEqual(cache.read_bytes(), old)
        tool.unlink()
        missing = self.run_nu(True)
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertFalse(cache.exists())
        cache.write_text("# user-managed autoload\n")
        preserved = self.run_nu(True)
        self.assertEqual(preserved.returncode, 0, preserved.stderr)
        self.assertEqual(cache.read_text(), "# user-managed autoload\n")
        cache.unlink()
        user_file = self.root / "user-starship.nu"
        user_file.write_text("# dotfiles executable: old-path\n# user content\n")
        cache.symlink_to(user_file)
        self.fake_tool("starship")
        with_symlink = self.run_nu(True)
        self.assertEqual(with_symlink.returncode, 0, with_symlink.stderr)
        self.assertTrue(cache.is_symlink())
        self.assertEqual(user_file.read_text(), "# dotfiles executable: old-path\n# user content\n")
        cache.unlink()
        cache.symlink_to(self.root / "missing-user-cache")
        dangling = self.run_nu(True)
        self.assertEqual(dangling.returncode, 0, dangling.stderr)
        self.assertTrue(cache.is_symlink())
        self.assertFalse((self.root / "missing-user-cache").exists())

    def test_concurrent_shells_leave_complete_generated_files(self):
        self.fake_tool("starship")
        self.fake_tool("carapace")
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(lambda _: self.run_nu(True), range(3)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        starship = self.data / "nushell/vendor/autoload/starship.nu"
        carapace = self.home / ".cache/carapace/init.nu"
        self.assertIn('DOTFILES_TEST_STARSHIP = "ready"', starship.read_text())
        self.assertIn("# carapace init", carapace.read_text())
        self.assertEqual(list(starship.parent.glob("*.tmp")), [])
        self.assertEqual(list(carapace.parent.glob("*.tmp")), [])


@unittest.skipUnless(shutil.which("pwsh"), "PowerShell is required")
class PowerShellStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pwsh-startup-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls"
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + "/usr/bin:/bin",
                        XDG_CACHE_HOME=str(self.root / "cache"), STARTUP_TEST_LOG=str(self.log))
        self.profile = self.root / "profile.ps1"
        contents = (REPO / "powershell/Microsoft.PowerShell_profile.ps1").read_text()
        # Avoid invoking the machine's Homebrew during synthetic interactive tests.
        contents = contents.replace('/opt/homebrew/bin/brew', str(self.root / 'missing-brew'))
        self.original = contents
        self.profile.write_text(contents)
        self.pwsh = shutil.which("pwsh")

    def fake_starship(self, failure=False):
        tool = self.bin / "starship"
        tool.write_text('#!/bin/sh\nprintf "starship:%s\\n" "$*" >> "$STARTUP_TEST_LOG"\n'
                        '''printf '%s\\n' '$env:DOTFILES_TEST_STARSHIP = "ready"'\n'''
                        + ('exit 7\n' if failure else 'exit 0\n'))
        tool.chmod(0o755)
        return tool

    def force_interactive(self):
        original = '$dotfilesInteractive = try { -not [Console]::IsInputRedirected -and -not $dotfilesNonInteractive -and (-not $dotfilesOneShot -or $dotfilesNoExit) } catch { $false }'
        self.assertIn(original, self.original)
        self.profile.write_text(self.original.replace(original, '$dotfilesInteractive = $true'))

    def run_pwsh(self):
        command = f'. "{self.profile}"; if ($env:DOTFILES_TEST_STARSHIP) {{ $env:DOTFILES_TEST_STARSHIP }} else {{ "missing" }}'
        return subprocess.run([self.pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                              env=self.env, capture_output=True, text=True)

    def test_noninteractive_does_not_generate_or_run_missing_tools(self):
        self.fake_starship()
        result = self.run_pwsh()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("missing", result.stdout)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / "cache/dotfiles-shell/powershell").exists())

    def test_interactive_cache_refresh_failure_and_missing_tool(self):
        self.force_interactive()
        tool = self.fake_starship()
        first = self.run_pwsh()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("ready", first.stdout)
        self.assertEqual(self.log.read_text().splitlines(), ["starship:init powershell --print-full-init"])
        warm = self.run_pwsh()
        self.assertEqual(warm.returncode, 0, warm.stderr)
        self.assertIn("ready", warm.stdout)
        self.assertEqual(self.log.read_text().splitlines(), ["starship:init powershell --print-full-init"])
        cache = self.root / "cache/dotfiles-shell/powershell/starship.ps1"
        old = cache.read_bytes()
        self.fake_starship(failure=True)
        timestamp = cache.stat().st_mtime + 5
        os.utime(tool, (timestamp, timestamp))
        failed = self.run_pwsh()
        self.assertEqual(failed.returncode, 0, failed.stderr)
        self.assertEqual(cache.read_bytes(), old)
        tool.unlink()
        missing = self.run_pwsh()
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn("missing", missing.stdout)

    def test_unrelated_cache_file_and_dangling_link_are_preserved(self):
        self.force_interactive()
        self.fake_starship()
        cache = self.root / "cache/dotfiles-shell/powershell/starship.ps1"
        cache.parent.mkdir(parents=True)
        cache.write_text("# user content\n")
        result = self.run_pwsh()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cache.read_text(), "# user content\n")
        self.assertFalse(self.log.exists())
        cache.unlink()
        cache.symlink_to(self.root / "missing")
        result = self.run_pwsh()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(cache.is_symlink())
        self.assertFalse((self.root / "missing").exists())


if __name__ == "__main__":
    unittest.main()
