"""Check checkout discovery for SessionX with the two Stow layouts."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "tmux/scripts/configure-sessionx.sh"


class SessionxPathsTests(unittest.TestCase):
    def test_direct_folded_and_individually_linked_script(self):
        with tempfile.TemporaryDirectory(prefix="sessionx paths ") as tmp:
            root = Path(tmp).resolve()
            checkout = root / "checkout with spaces"
            scripts = checkout / "tmux/scripts"
            scripts.mkdir(parents=True)
            script = scripts / SOURCE.name
            shutil.copy2(SOURCE, script)
            folded = root / "folded-tmux"
            folded.symlink_to(checkout / "tmux")
            separate = root / "separate/scripts"
            separate.mkdir(parents=True)
            (separate / SOURCE.name).symlink_to(os.path.relpath(script, separate))
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$SESSIONX_TEST_LOG"\n')
            fake_tmux.chmod(0o755)
            log = root / "calls"
            env = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"],
                       SESSIONX_TEST_LOG=str(log))
            for target in (script, folded / "scripts" / SOURCE.name, separate / SOURCE.name):
                with self.subTest(target=str(target)):
                    log.unlink(missing_ok=True)
                    subprocess.run(["/bin/bash", str(target), "/tmp/test socket"],
                                   env=env, check=True, capture_output=True, text=True)
                    self.assertEqual(log.read_text().splitlines(), [
                        f"-S /tmp/test socket set-option -g @sessionx-custom-paths {checkout}",
                        f"-S /tmp/test socket set-option -g @sessionx-x-path {checkout}",
                    ])

    def test_existing_stow_install_finds_new_unlinked_helper(self):
        with tempfile.TemporaryDirectory(prefix="sessionx bootstrap ") as tmp:
            root = Path(tmp).resolve()
            checkout = root / "checkout with spaces"
            scripts = checkout / "tmux/scripts"
            scripts.mkdir(parents=True)
            shutil.copy2(SOURCE, scripts / SOURCE.name)
            config = checkout / "tmux/tmux.conf"
            config.write_text("# existing config\n")
            installed = root / "config/tmux"
            installed.mkdir(parents=True)
            (installed / "tmux.conf").symlink_to(os.path.relpath(config, installed))
            self.assertFalse((installed / "scripts" / SOURCE.name).exists())
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_tmux = fake_bin / "tmux"
            fake_tmux.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$SESSIONX_TEST_LOG"\n')
            fake_tmux.chmod(0o755)
            log = root / "calls"
            env = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"],
                       SESSIONX_TEST_LOG=str(log))
            tmux_config = (SOURCE.parents[1] / "tmux.conf").read_text()
            line = next(line for line in tmux_config.splitlines() if line.startswith("run-shell '")
                        and "configure-sessionx.sh" in line)
            command = line[len("run-shell '"):-1]
            command = command.replace('$HOME/.config/tmux/tmux.conf', str(installed / "tmux.conf"))
            command = command.replace('#{socket_path}', '/tmp/test socket')
            subprocess.run(["/bin/sh", "-c", command], env=env, check=True,
                           capture_output=True, text=True)
            self.assertEqual(log.read_text().splitlines(), [
                f"-S /tmp/test socket set-option -g @sessionx-custom-paths {checkout}",
                f"-S /tmp/test socket set-option -g @sessionx-x-path {checkout}",
            ])


if __name__ == "__main__":
    unittest.main()
