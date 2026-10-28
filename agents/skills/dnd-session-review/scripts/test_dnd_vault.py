"""Regression checks for shared installation versus campaign data isolation."""

import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dnd_vault import configured_player_character, find_vault_root, load_campaign_config


class VaultResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.first = self.root / "first"
        self.second = self.root / "second"
        for vault in (self.first, self.second):
            (vault / "Sessions/Notes").mkdir(parents=True)

    def test_working_vault_and_nested_directory(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.cwd", return_value=self.first / "Sessions/Notes"):
                self.assertEqual(find_vault_root(), self.first)

    def test_explicit_other_vault_wins(self):
        with patch.dict(os.environ, {"DND_VAULT_ROOT": str(self.second)}):
            with patch("pathlib.Path.cwd", return_value=self.first):
                self.assertEqual(find_vault_root(), self.second)

    def test_invalid_explicit_path_does_not_fall_back(self):
        with patch.dict(os.environ, {"DND_VAULT_ROOT": str(self.root / "missing")}):
            with patch("pathlib.Path.cwd", return_value=self.first):
                with self.assertRaisesRegex(RuntimeError, "No D&D vault"):
                    find_vault_root()

    def test_outside_vault_fails_without_creating_metadata(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.cwd", return_value=self.root):
                with self.assertRaises(RuntimeError):
                    find_vault_root()
        self.assertFalse((self.root / ".dnd-meta").exists())

    def test_campaign_settings_are_isolated(self):
        (self.first / ".dnd-meta").mkdir()
        (self.first / ".dnd-meta/skill-config.json").write_text(json.dumps({
            "party_members": ["Hero"], "forced_entity_types": {"vessel": "location"}
        }))
        self.assertEqual(load_campaign_config(self.first)["party_members"], ["Hero"])
        self.assertEqual(load_campaign_config(self.second), {})

    def test_invalid_campaign_settings_fail(self):
        (self.first / ".dnd-meta").mkdir()
        (self.first / ".dnd-meta/skill-config.json").write_text('{"party_members": "Hero"}')
        with self.assertRaises(ValueError):
            load_campaign_config(self.first)

    def test_suite_scripts_use_working_vault_without_campaign_defaults(self):
        skills = Path(__file__).resolve().parents[2]
        scripts = [p for p in skills.glob("dnd-*/scripts/*.py")
                   if not p.name.startswith("test_")
                   and p.name not in {"dnd_vault.py", "extract_note_span.py", "dnd_session_setup.py"}]
        self.assertEqual(len(scripts), 6)
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.cwd", return_value=self.second):
                for script in scripts:
                    with self.subTest(script=script.name):
                        module = runpy.run_path(str(script))
                        self.assertEqual(module["REPO_ROOT"], self.second)
                        self.assertEqual(module["CAMPAIGN_CONFIG"], {})
                        self.assertEqual(module.get("DEFAULT_RESOLVER_ENTITIES", []), [])
                        self.assertEqual(module.get("FORCED_ENTITY_TYPES", {}), {})
                        if "EVENTS_LINT_SCRIPT" in module:
                            self.assertTrue(module["EVENTS_LINT_SCRIPT"].is_file())

    def test_player_character_precedence_and_legacy_compatibility(self):
        self.assertEqual(configured_player_character({"player_character": "Mira", "focus_character": "Rook"}), "Mira")
        self.assertEqual(configured_player_character({"focus_character": "Rook"}), "Rook")
        self.assertIsNone(configured_player_character({"focus_character": "Party"}))
        self.assertIsNone(configured_player_character({}))

    def test_invalid_player_settings_are_rejected(self):
        folder = self.first / ".dnd-meta"
        folder.mkdir()
        for value in ("", "Party", 42, "Mira\nHeading"):
            with self.subTest(value=value):
                (folder / "skill-config.json").write_text(json.dumps({"player_character": value}))
                with self.assertRaises(ValueError):
                    load_campaign_config(self.first)

    def test_legacy_summary_uses_player_aliases_and_canonical_identity(self):
        meta = self.first / ".dnd-meta"
        meta.mkdir()
        (meta / "skill-config.json").write_text(json.dumps({"player_character": "Mira Dawn"}))
        script = Path(__file__).parent / "dnd_session_review.py"
        with patch.dict(os.environ, {"DND_VAULT_ROOT": str(self.first)}):
            module = runpy.run_path(str(script))
        session = module["SessionRef"](1, "2026-10-18", "Session 01.md", self.first / "Sessions/Notes/Session 01.md")
        events = [{"text": text} for text in ("The gates open.", "The guards depart.", "Mira takes the key.")]
        resolver = {"entities": [{"canonical_title": "Mira Dawn", "entity_type": "character", "true_aliases": ["Mira"]}]}
        text = module["generate_summary"](session, {"session": {}, "events": events}, resolver)
        lens = text.split("## 🎯 Player Lens", 1)[1].split("## ", 1)[0]
        self.assertIn("takes the key", lens)
        self.assertNotIn("The gates open", lens)
        self.assertIn("**Player Character:** [[Mira Dawn]]", text)


if __name__ == "__main__":
    unittest.main()
