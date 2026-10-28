#!/usr/bin/env python3
"""Inspect and initialize missing campaign templates without overwriting files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dnd-session-review" / "scripts"))
from dnd_vault import configured_player_character, find_vault_root, load_campaign_config

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "templates"
TEMPLATE_NAMES = (
    "session-summary-template.md", "quest-template.md", "character-template.md",
    "location-template.md", "faction-template.md", "item-template.md", "creature-template.md",
)
START = "<!-- dnd-managed:start -->"
END = "<!-- dnd-managed:end -->"
NOTES = "## 📝 Notes"


def template_errors(name: str, text: str) -> List[str]:
    errors = []
    frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    if not frontmatter:
        errors.append("Missing frontmatter block")
    headings = set(text.splitlines())
    if name == "session-summary-template.md":
        required = ("## 🎲 Summary", "## 🕰️ Session Timeline", "## 🔑 Key Events")
        for key in ("session_number", "date"):
            if frontmatter and not re.search(rf"^{key}:\s*\S", frontmatter.group(1), re.M):
                errors.append(f"Missing frontmatter field: {key}")
    else:
        entity_type = name.removesuffix("-template.md")
        if frontmatter and not re.search(rf"^type:\s*[\"']?{entity_type}[\"']?\s*$", frontmatter.group(1), re.M):
            errors.append(f"Missing frontmatter type: {entity_type}")
        required = (("## 🎯 Objective", "## 🧵 Progress Log", NOTES) if entity_type == "quest"
                    else ("## 🌐 Overview", "## 🕰️ Session Timeline", NOTES))
        if text.count(START) != 1 or text.count(END) != 1 or text.find(START) > text.find(END):
            errors.append("Expected one ordered managed block")
        else:
            for heading in required:
                if heading != NOTES and heading in headings and not (text.index(START) < text.index(heading) < text.index(END)):
                    errors.append(f"Heading must be inside the managed block: {heading}")
        if NOTES in headings and text.find(NOTES) < text.find(END):
            errors.append("Manual Notes must follow the managed block")
        if text.splitlines().count(NOTES) > 1:
            errors.append("Expected one manual Notes section")
    for heading in required:
        if heading not in headings:
            errors.append(f"Missing heading: {heading}")
    return errors


def check_templates(vault: Path) -> Dict[str, Any]:
    missing = []
    invalid = {}
    templates = vault / "Templates"
    if templates.exists() and not templates.is_dir():
        return {"vault": str(vault), "ready": False, "missing": [],
                "invalid": {"Templates": ["Expected a directory"]}, "present": 0}
    for name in TEMPLATE_NAMES:
        path = templates / name
        label = f"Templates/{name}"
        if not path.exists() and not path.is_symlink():
            missing.append(label)
        elif not path.is_file():
            invalid[label] = ["Expected a readable Markdown file"]
        else:
            errors = template_errors(name, path.read_text(encoding="utf-8"))
            if errors:
                invalid[label] = errors
    player = configured_player_character(load_campaign_config(vault))
    return {"vault": str(vault), "ready": not missing and not invalid and player is not None,
            "missing": missing, "invalid": invalid,
            "present": len(TEMPLATE_NAMES) - len(missing) - len(invalid),
            "player_character": player, "needs_player_character": player is None}


def player_name(value: str) -> str:
    value = value.strip()
    if not value or "\n" in value or "\r" in value or value == "Party":
        raise ValueError("Specify the player's character name, rather than Party")
    return value


def render_template(name: str) -> str:
    text = (ASSETS / name).read_text(encoding="utf-8")
    errors = template_errors(name, text)
    if errors:
        raise ValueError(f"Invalid shared template {name}: {'; '.join(errors)}")
    return text


def initialize_templates(vault: Path, player_character: Optional[str] = None) -> Dict[str, Any]:
    before = check_templates(vault)
    if before["invalid"]:
        raise ValueError("Existing templates need repair; no files changed: " + json.dumps(before["invalid"], ensure_ascii=False))
    config = load_campaign_config(vault)
    player = player_character if player_character is not None else configured_player_character(config)
    if player is None:
        raise ValueError("Player character is not configured. Ask the user which character they play, then use init --player-character NAME.")
    player = player_name(player)
    planned = {label: render_template(Path(label).name) for label in before["missing"]}
    if planned:
        (vault / "Templates").mkdir(exist_ok=True)
    created = []
    for label, text in planned.items():
        # Exclusive creation also protects templates added after the preflight.
        with (vault / label).open("x", encoding="utf-8") as output:
            output.write(text)
        created.append(label)
    config_changed = config.get("player_character") != player
    if config_changed:
        config["player_character"] = player
        config.pop("focus_character", None)
        meta = vault / ".dnd-meta"
        meta.mkdir(exist_ok=True)
        (meta / "skill-config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dict(check_templates(vault), created=created,
                preserved=[f"Templates/{n}" for n in TEMPLATE_NAMES if f"Templates/{n}" not in created],
                player_character=player, config_updated=config_changed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "init"))
    parser.add_argument("--player-character", "--focus-character", dest="player_character",
                        help="The player's canonical character name, saved in campaign settings")
    args = parser.parse_args()
    try:
        if args.command == "check" and args.player_character is not None:
            parser.error("--player-character is only valid with init")
        vault = find_vault_root()
        result = check_templates(vault) if args.command == "check" else initialize_templates(vault, args.player_character)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ready": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
