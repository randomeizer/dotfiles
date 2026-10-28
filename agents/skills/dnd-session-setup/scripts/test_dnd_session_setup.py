"""Behavioral checks for missing-template setup and campaign preservation."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dnd_session_setup as setup


class TemplateSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name).resolve()
        self.notes = self.vault / "Sessions/Notes"
        self.notes.mkdir(parents=True)
        (self.notes / "2026-10-18 - Session 01.md").write_text("# Now\n\nA canonical note.\n")

    def snapshot(self):
        return {str(p.relative_to(self.vault)): p.read_bytes()
                for p in self.vault.rglob("*") if p.is_file()}

    def write_config(self, config):
        path = self.vault / ".dnd-meta/skill-config.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(config))
        return path

    def run_cli(self, *args):
        env = dict(os.environ, DND_VAULT_ROOT=str(self.vault), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, str(Path(setup.__file__)), *args],
                                env=env, cwd=self.notes, capture_output=True, text=True)
        return result, json.loads(result.stdout)

    def test_missing_check_is_read_only(self):
        before = self.snapshot()
        result, status = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(status["missing"]), 7)
        self.assertTrue(status["needs_player_character"])
        self.assertEqual(self.snapshot(), before)

    def test_fresh_vault_gets_seven_neutral_defaults(self):
        source_note = next(self.notes.iterdir()).read_bytes()
        status = setup.initialize_templates(self.vault, "Mira")
        self.assertTrue(status["ready"])
        self.assertEqual(len(status["created"]), 7)
        summary = (self.vault / "Templates/session-summary-template.md").read_text()
        self.assertIn("## 🎯 Player Lens", summary)
        self.assertIn("[[{{player_character}}]]", summary)
        self.assertNotIn("Mira", summary)
        self.assertEqual(next(self.notes.iterdir()).read_bytes(), source_note)
        self.assertEqual(json.loads((self.vault / ".dnd-meta/skill-config.json").read_text())["player_character"], "Mira")
        for path in (self.vault / "Templates").glob("*.md"):
            self.assertNotRegex(path.read_text(), r"Valen|Souvaar|The Voyage|Tonnik|Saffron")

    def test_named_viewpoint_preserves_unrelated_campaign_settings(self):
        config_path = self.write_config({"party_members": ["Mira"], "custom": {"tone": "serious"}})
        status = setup.initialize_templates(self.vault, "Mira")
        self.assertTrue(status["ready"])
        self.assertIn("## 🎯 Player Lens", (self.vault / "Templates/session-summary-template.md").read_text())
        config = json.loads(config_path.read_text())
        self.assertEqual(config, {"party_members": ["Mira"], "custom": {"tone": "serious"}, "player_character": "Mira"})

    def test_migrates_legacy_focus_without_baking_name_into_template(self):
        config_path = self.write_config({"focus_character": "Rook"})
        setup.initialize_templates(self.vault)
        self.assertIn("## 🎯 Player Lens", (self.vault / "Templates/session-summary-template.md").read_text())
        self.assertEqual(json.loads(config_path.read_text()), {"player_character": "Rook"})

    def test_partial_setup_preserves_custom_template_and_viewpoint(self):
        templates = self.vault / "Templates"
        templates.mkdir()
        custom = setup.render_template("session-summary-template.md") + "\n## 🪶 Custom Section\n\nManual prompt.\n"
        path = templates / "session-summary-template.md"
        path.write_bytes(custom.replace("\n", "\r\n").encode())
        original = path.read_bytes()
        config_path = self.write_config({"player_character": "Rook"})
        config_before = config_path.read_bytes()
        status = setup.initialize_templates(self.vault)
        self.assertEqual(len(status["created"]), 6)
        self.assertEqual(status["player_character"], "Rook")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(config_path.read_bytes(), config_before)

    def test_repeat_init_is_a_no_op(self):
        setup.initialize_templates(self.vault, "Mira")
        before = self.snapshot()
        result = setup.initialize_templates(self.vault)
        self.assertTrue(result["ready"])
        self.assertEqual(result["created"], [])
        self.assertEqual(self.snapshot(), before)

    def test_incompatible_existing_template_blocks_mutations(self):
        templates = self.vault / "Templates"
        templates.mkdir()
        (templates / "quest-template.md").write_text("My manually written template.\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Existing templates need repair"):
            setup.initialize_templates(self.vault)
        self.assertEqual(self.snapshot(), before)

    def test_manual_notes_inside_managed_block_are_rejected(self):
        text = setup.render_template("character-template.md")
        text = text.replace(setup.END, "").replace(setup.NOTES, setup.NOTES + "\n" + setup.END)
        self.assertIn("Manual Notes must follow the managed block", setup.template_errors("character-template.md", text))

    def test_broken_template_symlink_is_preserved(self):
        templates = self.vault / "Templates"
        templates.mkdir()
        link = templates / "quest-template.md"
        link.symlink_to(templates / "does-not-exist.md")
        self.assertIn("Templates/quest-template.md", setup.check_templates(self.vault)["invalid"])
        with self.assertRaises(ValueError):
            setup.initialize_templates(self.vault)
        self.assertTrue(link.is_symlink())

    def test_missing_asset_does_not_partially_initialize(self):
        with patch.object(setup, "ASSETS", self.vault / "no-assets"):
            with self.assertRaises(OSError):
                setup.initialize_templates(self.vault, "Mira")
        self.assertFalse((self.vault / "Templates").exists())

    def test_invalid_viewpoint_does_not_write_files(self):
        for name in ("", "Party", "Mira\nAnother Heading"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    setup.initialize_templates(self.vault, name)
                self.assertFalse((self.vault / "Templates").exists())

    def test_cli_setup_then_preflight_resumes_as_ready(self):
        result, status = self.run_cli("init", "--player-character", "Mira")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(status["ready"])
        before = self.snapshot()
        result, status = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(status["ready"])
        self.assertEqual(self.snapshot(), before)

    def test_missing_player_character_blocks_setup_without_writing(self):
        with self.assertRaisesRegex(ValueError, "Ask the user"):
            setup.initialize_templates(self.vault)
        self.assertFalse((self.vault / "Templates").exists())

    def test_setting_character_with_existing_templates_preserves_them(self):
        setup.initialize_templates(self.vault, "Mira")
        (self.vault / ".dnd-meta/skill-config.json").unlink()
        templates = {p.name: p.read_bytes() for p in (self.vault / "Templates").iterdir()}
        self.assertTrue(setup.check_templates(self.vault)["needs_player_character"])
        status = setup.initialize_templates(self.vault, "Rook")
        self.assertEqual(status["created"], [])
        self.assertEqual(status["player_character"], "Rook")
        self.assertEqual(templates, {p.name: p.read_bytes() for p in (self.vault / "Templates").iterdir()})


if __name__ == "__main__":
    unittest.main()
