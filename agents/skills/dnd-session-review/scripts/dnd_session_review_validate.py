#!/usr/bin/env python3
"""Final validation checks for orchestrated dnd-session-review runs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Shared scripts belong to the installed suite; campaign data belongs to the vault.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dnd-session-review" / "scripts"))
from dnd_vault import find_vault_root, load_campaign_config

REPO_ROOT = find_vault_root()
CAMPAIGN_CONFIG = load_campaign_config(REPO_ROOT)

NOTES_DIR = REPO_ROOT / "Sessions" / "Notes"
SUMMARIES_DIR = REPO_ROOT / "Sessions" / "Summaries"
QUEST_MAP_PATH = REPO_ROOT / ".dnd-meta" / "quest-map.yaml"
META_SESSIONS_DIR = REPO_ROOT / ".dnd-meta" / "sessions"
WORLD_DIR = REPO_ROOT / "World"

WORLD_TYPE_DIR = {
    "character": WORLD_DIR / "Characters",
    "location": WORLD_DIR / "Locations",
    "faction": WORLD_DIR / "Factions",
    "item": WORLD_DIR / "Items",
    "creature": WORLD_DIR / "Creatures",
}
FORCED_ENTITY_TYPES = CAMPAIGN_CONFIG.get("forced_entity_types", {})
NOTABLE_ITEM_RE = re.compile(
    r"(artifact|relic|sigil|grimoire|map|letter|journal|amulet|ring|blade|sword|staff|wand|potion|mark|focus|knife|key|gem|orb)",
    re.IGNORECASE,
)
NON_NOTABLE_ITEM_RE = re.compile(
    r"(ration|soup|pasta|meal|rum|ale|beer|wine|cannon|charts|repair kits?|grappling hooks?|wadding|shield|eldritch blast|booming blade|misty step|darkness|alarm spell|alarm|vicious mockery|mirror image|form of dread|tales from beyond)",
    re.IGNORECASE,
)
NARRATIVE_BOILERPLATE_PHRASES = [
    "is a notable story asset in this arc.",
    "precise mechanics were not fully detailed in this session.",
    "no additional state changes were clearly documented in this session.",
    "how this thread will evolve across future sessions remains unclear.",
]

MANAGED_START = "<!-- dnd-managed:start -->"
MANAGED_END = "<!-- dnd-managed:end -->"


class ReviewValidationError(Exception):
    pass


@dataclass
class SessionRef:
    session_number: int
    date: str
    filename: str
    path: Path


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return normalize_space(lowered)


def forced_entity_type(canonical: str, entity_type: str) -> str:
    forced = FORCED_ENTITY_TYPES.get(normalize_name(canonical))
    if forced in WORLD_TYPE_DIR:
        return forced
    return entity_type


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ruby_yaml_to_json(text: str) -> Any:
    try:
        proc = subprocess.run(
            [
                "ruby",
                "-ryaml",
                "-rjson",
                "-e",
                "obj = YAML.load(STDIN.read); STDOUT.write(JSON.generate(obj))",
            ],
            input=text,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ReviewValidationError(f"Unable to parse YAML via ruby: {exc.stderr.strip()}") from exc
    return json.loads(proc.stdout)


def load_data(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = read_text(path).strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return ruby_yaml_to_json(raw)


def discover_sessions() -> List[SessionRef]:
    pattern = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s*-\s*Session\s*(?P<num>\d{1,3})\.md$")
    sessions: List[SessionRef] = []
    for path in sorted(NOTES_DIR.glob("*.md")):
        match = pattern.match(path.name)
        if not match:
            continue
        sessions.append(
            SessionRef(
                session_number=int(match.group("num")),
                date=match.group("date"),
                filename=path.name,
                path=path,
            )
        )
    if not sessions:
        raise ReviewValidationError("No session notes found in Sessions/Notes.")
    return sessions


def select_session(selector: Optional[str]) -> SessionRef:
    sessions = discover_sessions()
    by_number = sorted(sessions, key=lambda s: (s.session_number, s.date, s.filename))

    if selector is None:
        return by_number[-1]

    candidate = selector.strip().lower()
    if candidate == "latest session":
        return by_number[-1]

    match = re.search(r"session\s*(\d{1,3})", candidate)
    if not match:
        raise ReviewValidationError(f"Unsupported session selector: {selector}")

    requested = int(match.group(1))
    filtered = [s for s in sessions if s.session_number == requested]
    if not filtered:
        raise ReviewValidationError(f"No session note found for Session {requested:02d}.")
    return sorted(filtered, key=lambda s: (s.date, s.filename))[-1]


def session_meta_dir(session: SessionRef) -> Path:
    return META_SESSIONS_DIR / f"{session.date}-s{session.session_number:03d}"


def events_path_for(session: SessionRef) -> Path:
    return session_meta_dir(session) / "events.yaml"


def world_path_for(session: SessionRef) -> Path:
    return session_meta_dir(session) / "world.yaml"


def summary_path_for(session: SessionRef) -> Path:
    return SUMMARIES_DIR / f"{session.date} - Session {session.session_number:03d} - Summary.md"


def has_placeholders(text: str) -> bool:
    return "{{" in text or "}}" in text


def check_managed_and_notes(path: Path, text: str, errors: List[str], warnings: List[str]) -> None:
    if MANAGED_START not in text or MANAGED_END not in text:
        errors.append(f"{path.relative_to(REPO_ROOT)} missing managed markers")
    notes_count = len(re.findall(r"^##\s+📝\s+Notes\s*$", text, flags=re.MULTILINE))
    if notes_count == 0:
        warnings.append(f"{path.relative_to(REPO_ROOT)} missing `## 📝 Notes` section")
    elif notes_count > 1:
        errors.append(f"{path.relative_to(REPO_ROOT)} has duplicate `## 📝 Notes` sections")


def managed_block_text(text: str) -> str:
    match = re.search(
        re.escape(MANAGED_START) + r"\s*(.*?)\s*" + re.escape(MANAGED_END),
        text,
        flags=re.DOTALL,
    )
    if not match:
        return text
    return match.group(1)


def unescaped_table_wikilink_lines(text: str) -> List[int]:
    pattern = re.compile(r"\[\[[^\]]*(?<!\\)\|[^\]]+\]\]")
    lines: List[int] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("|") and pattern.search(line):
            lines.append(idx)
    return lines


def validate(session: SessionRef) -> Tuple[List[str], List[str], List[str]]:
    checks: List[str] = []
    errors: List[str] = []
    warnings: List[str] = []

    events_path = events_path_for(session)
    world_path = world_path_for(session)
    summary_path = summary_path_for(session)

    for required in [events_path, world_path, summary_path]:
        if not required.exists():
            errors.append(f"Missing required file: {required.relative_to(REPO_ROOT)}")
    if errors:
        return checks, errors, warnings

    checks.append(f"Found Stage 1 artifacts: `{events_path.relative_to(REPO_ROOT)}` and `{world_path.relative_to(REPO_ROOT)}`")
    checks.append(f"Found session summary: `{summary_path.relative_to(REPO_ROOT)}`")

    events_data = load_data(events_path, None)
    world_data = load_data(world_path, None)
    if not isinstance(events_data, dict):
        errors.append(f"Invalid YAML structure: {events_path.relative_to(REPO_ROOT)}")
        return checks, errors, warnings
    if not isinstance(world_data, dict):
        errors.append(f"Invalid YAML structure: {world_path.relative_to(REPO_ROOT)}")
        return checks, errors, warnings

    triage = world_data.get("triage_summary", {}) if isinstance(world_data.get("triage_summary"), dict) else {}
    open_count = int(triage.get("open_count", 0)) if str(triage.get("open_count", "")).isdigit() else 0
    if open_count > 0:
        errors.append(f"Triage is not resolved: world.yaml open_count={open_count}")
    else:
        checks.append("Triage gate passed: world.yaml open_count=0")

    summary_text = read_text(summary_path)
    if has_placeholders(summary_text):
        errors.append(f"{summary_path.relative_to(REPO_ROOT)} still contains template placeholders")
    else:
        checks.append("Summary contains no template placeholders")
    for line_no in unescaped_table_wikilink_lines(summary_text):
        errors.append(
            f"{summary_path.relative_to(REPO_ROOT)}:{line_no} unescaped wikilink pipe in table cell"
        )

    world_entities = world_data.get("entities", [])
    if not isinstance(world_entities, list):
        world_entities = []

    event_entries = events_data.get("events", [])
    if not isinstance(event_entries, list):
        event_entries = []

    def normalize_entity_type(value: str) -> Optional[str]:
        clean = normalize_space(value).lower()
        if clean in WORLD_TYPE_DIR:
            return clean
        return None

    def is_notable_item(value: str) -> bool:
        text = normalize_space(value)
        if not text:
            return False
        if NON_NOTABLE_ITEM_RE.search(text):
            return False
        return bool(NOTABLE_ITEM_RE.search(text))

    # Build alias/canonical coverage index so we can verify that event-level entities
    # were reviewed into world.yaml (resolved/triaged/ignored).
    world_entity_keys: Dict[Tuple[str, str], str] = {}
    for entry in world_entities:
        if not isinstance(entry, dict):
            continue
        canonical = normalize_space(str(entry.get("canonical_title", "")))
        mention = normalize_space(str(entry.get("mention", "")))
        entity_type_raw = normalize_entity_type(str(entry.get("entity_type", "")))
        entity_type = (
            forced_entity_type(canonical, entity_type_raw) if entity_type_raw else None
        )
        if not canonical or not entity_type:
            continue
        canonical_key = normalize_name(canonical)
        if canonical_key:
            world_entity_keys[(canonical_key, entity_type)] = canonical
        mention_key = normalize_name(mention)
        if mention_key:
            world_entity_keys[(mention_key, entity_type)] = canonical
        aliases = entry.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                alias_key = normalize_name(str(alias))
                if alias_key:
                    world_entity_keys[(alias_key, entity_type)] = canonical

    unresolved_event_entities: List[str] = []
    event_field_to_type = {
        "participants": "character",
        "locations": "location",
        "factions": "faction",
        "items": "item",
    }
    for event in event_entries:
        if not isinstance(event, dict):
            continue
        event_id = normalize_space(str(event.get("id", ""))) or "unknown-event"
        for field, entity_type in event_field_to_type.items():
            values = event.get(field, [])
            if not isinstance(values, list):
                continue
            for raw in values:
                value = normalize_space(str(raw))
                if not value:
                    continue
                key_name = normalize_name(value)
                if field == "items" and not is_notable_item(value):
                    continue

                # Primary check: same-type reviewed entity.
                key = (key_name, entity_type)
                # Fallback check: reviewed under any type (helps with canonical
                # remaps like participant mention represented as creature/item).
                in_any_type = any(
                    (key_name, candidate_type) in world_entity_keys for candidate_type in WORLD_TYPE_DIR.keys()
                )
                if key not in world_entity_keys and not in_any_type:
                    unresolved_event_entities.append(
                        f"{event_id} {field[:-1]} '{value}' has no reviewed world entity entry"
                    )

    if unresolved_event_entities:
        errors.extend(sorted(set(unresolved_event_entities)))
    else:
        checks.append("All event-level entities are represented in world.yaml for review tracking")

    required_world_files: Dict[Path, Dict[str, Any]] = {}
    for entry in world_entities:
        if not isinstance(entry, dict):
            continue
        canonical = normalize_space(str(entry.get("canonical_title", "")))
        entity_type = normalize_space(str(entry.get("entity_type", ""))).lower()
        entity_type = forced_entity_type(canonical, entity_type)
        if not canonical or entity_type not in WORLD_TYPE_DIR:
            continue
        if normalize_space(str(entry.get("resolution_status", ""))).lower() != "resolved":
            continue
        required_world_files[WORLD_TYPE_DIR[entity_type] / f"{canonical}.md"] = entry

    for path in sorted(required_world_files.keys()):
        if not path.exists():
            errors.append(f"Missing world file: {path.relative_to(REPO_ROOT)}")
            continue
        text = read_text(path)
        managed_text = managed_block_text(text)
        managed_lower = managed_text.lower()
        if has_placeholders(text):
            errors.append(f"{path.relative_to(REPO_ROOT)} still contains template placeholders")
        if re.search(r"\bunspecified\b", managed_text, flags=re.IGNORECASE):
            errors.append(f"{path.relative_to(REPO_ROOT)} contains `unspecified` in managed narrative")
        for phrase in NARRATIVE_BOILERPLATE_PHRASES:
            if phrase in managed_lower:
                errors.append(
                    f"{path.relative_to(REPO_ROOT)} contains scripted boilerplate phrase: {phrase!r}"
                )
        check_managed_and_notes(path, text, errors, warnings)
        for line_no in unescaped_table_wikilink_lines(text):
            errors.append(
                f"{path.relative_to(REPO_ROOT)}:{line_no} unescaped wikilink pipe in table cell"
            )
        expected_session_heading = (
            f"### [[{session.date} - Session {session.session_number:03d} - Summary|Session {session.session_number:03d}]]"
        )
        expected_session_heading_alt = (
            f"### [[Sessions/Summaries/{session.date} - Session {session.session_number:03d} - Summary|Session {session.session_number:03d}]]"
        )
        expected_last_updated = (
            f"- Last Updated Session: [[{session.date} - Session {session.session_number:03d} - Summary|Session {session.session_number:03d}]]"
        )
        expected_last_updated_alt = (
            f"- Last Updated Session: [[Sessions/Summaries/{session.date} - Session {session.session_number:03d} - Summary|Session {session.session_number:03d}]]"
        )
        has_timeline_update = (
            expected_session_heading in text or expected_session_heading_alt in text
        )
        has_last_updated = (
            expected_last_updated in text or expected_last_updated_alt in text
        )
        if not has_timeline_update and not has_last_updated:
            warnings.append(
                f"{path.relative_to(REPO_ROOT)} missing session-update marker for Session {session.session_number:03d}"
            )
    checks.append(f"Validated world files for resolved entities: {len(required_world_files)}")

    quest_map = load_data(QUEST_MAP_PATH, {"quests": {}})
    quests = quest_map.get("quests", {}) if isinstance(quest_map, dict) else {}
    if not isinstance(quests, dict):
        quests = {}

    existing_quest_files = 0
    for key, rel in quests.items():
        path = REPO_ROOT / str(rel)
        if not path.exists():
            warnings.append(f"Quest map points to missing file: {key} -> {rel}")
            continue
        existing_quest_files += 1
        text = read_text(path)
        if has_placeholders(text):
            errors.append(f"{path.relative_to(REPO_ROOT)} still contains template placeholders")
        for line_no in unescaped_table_wikilink_lines(text):
            errors.append(
                f"{path.relative_to(REPO_ROOT)}:{line_no} unescaped wikilink pipe in table cell"
            )
    checks.append(f"Validated quest-map entries: {existing_quest_files} existing files")

    return checks, errors, warnings


def write_report(
    session: SessionRef, checks: List[str], errors: List[str], warnings: List[str]
) -> Path:
    report_path = session_meta_dir(session) / "review-validation-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Session Review Validation Report",
        "",
        f"- Session: {session.date} Session {session.session_number:03d}",
        f"- Timestamp: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        "",
        "## Checks",
    ]
    if checks:
        lines.extend(f"- {item}" for item in checks)
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Errors")
    if errors:
        lines.extend(f"- {item}" for item in errors)
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Warnings")
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- None")

    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report_path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Final validation for orchestrated session review")
    p.add_argument("--session", default="latest session")
    p.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    return p


def main() -> int:
    args = parser().parse_args()
    session = select_session(args.session)
    checks, errors, warnings = validate(session)
    report = write_report(session, checks, errors, warnings)

    print(f"Session: {session.date} Session {session.session_number:03d}")
    print(f"Checks: {len(checks)}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"Report: {report.relative_to(REPO_ROOT)}")

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
