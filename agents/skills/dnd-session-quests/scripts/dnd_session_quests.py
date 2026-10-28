#!/usr/bin/env python3
"""Generate/update quest files for a session from Stage 1 metadata + summary + note spans."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Shared scripts belong to the installed suite; campaign data belongs to the vault.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dnd-session-review" / "scripts"))
from dnd_vault import find_vault_root, load_campaign_config

REPO_ROOT = find_vault_root()
CAMPAIGN_CONFIG = load_campaign_config(REPO_ROOT)
META_SESSIONS_DIR = REPO_ROOT / ".dnd-meta" / "sessions"
QUEST_MAP_PATH = REPO_ROOT / ".dnd-meta" / "quest-map.yaml"
QUEST_CONSOLIDATION_RULES_PATH = REPO_ROOT / ".dnd-meta" / "quest-consolidation-rules.yaml"
QUESTS_ROOT_DIR = REPO_ROOT / "Quests"
QUESTS_ACTIVE_DIR = QUESTS_ROOT_DIR / "Active"
QUESTS_COMPLETED_DIR = QUESTS_ROOT_DIR / "Completed"
SUMMARIES_DIR = REPO_ROOT / "Sessions" / "Summaries"
TEMPLATE_PATH = REPO_ROOT / "Templates" / "quest-template.md"

MANAGED_START = "<!-- dnd-managed:start -->"
MANAGED_END = "<!-- dnd-managed:end -->"

HIGH_MARKERS = {
    "urgent",
    "attack",
    "ambush",
    "threat",
    "hostile",
    "danger",
    "critical",
    "immediate",
    "deadline",
    "mission",
    "investigate",
}

LOW_MARKERS = {
    "monitor",
    "maybe",
    "potential",
    "possible",
    "flag",
    "odd behavior",
    "might",
    "could",
    "rumor",
    "unclear",
}

SHORT_MARKERS = {
    "before departure",
    "leave dawn",
    "two week",
    "immediate",
    "this mission",
    "now",
    "next session",
    "on arrival",
}

LONG_MARKERS = {
    "ongoing",
    "monitor",
    "long",
    "eventually",
    "politic",
    "alliance",
    "mystery",
    "unknown",
    "larger events",
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "near",
    "before",
    "after",
    "their",
    "there",
    "what",
    "when",
    "where",
    "which",
    "while",
    "have",
    "been",
    "was",
    "were",
    "are",
    "is",
    "to",
    "of",
    "in",
    "on",
    "a",
    "an",
}

LEGACY_DEFAULT_RISK = "Following this thread may consume limited session time."


class QuestError(RuntimeError):
    pass


@dataclass
class SessionRef:
    session_number: int
    date: str
    meta_dir: Path
    events_path: Path
    world_path: Path
    source_note: Path
    summary_path: Path


@dataclass
class QuestFileMeta:
    path_rel: str
    keys: List[str]
    title: str
    objective: str
    priority: str
    status: str


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return normalize_space(lowered)


def slugify(value: str) -> str:
    slug = normalize_name(value).replace(" ", "-")
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def normalize_keyword(value: str) -> str:
    normalized = normalize_name(value).replace(" ", "-")
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized


def dedupe_preserve(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str, dry_run: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return
    path.write_text(text, encoding="utf-8")


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
        raise QuestError(f"Unable to parse YAML via ruby: {exc.stderr.strip()}") from exc
    return json.loads(proc.stdout)


def json_to_ruby_yaml(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    try:
        proc = subprocess.run(
            [
                "ruby",
                "-ryaml",
                "-rjson",
                "-e",
                "obj = JSON.parse(STDIN.read); puts YAML.dump(obj)",
            ],
            input=payload,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise QuestError(f"Unable to serialize YAML via ruby: {exc.stderr.strip()}") from exc
    return proc.stdout


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


def dump_data(path: Path, data: Any, dry_run: bool) -> None:
    payload = json_to_ruby_yaml(data)
    write_text(path, payload if payload.endswith("\n") else payload + "\n", dry_run)


def split_frontmatter(text: str) -> Tuple[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        return "", text
    return match.group(0), text[match.end() :]


def upsert_managed_block(text: str, managed: str) -> str:
    replacement = f"{MANAGED_START}\n{managed.rstrip()}\n{MANAGED_END}"
    pattern = re.compile(re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END), re.DOTALL)
    if pattern.search(text):
        return pattern.sub(replacement, text)

    stripped = text.rstrip()
    if not stripped:
        return replacement + "\n"
    return stripped + "\n\n" + replacement + "\n"


def ensure_notes_section(body: str) -> str:
    if re.search(r"^##\s+📝\s+Notes\s*$", body, re.MULTILINE):
        return body
    tail = "\n## 📝 Notes\n\n- Add manual notes here. Keep this section outside the managed block.\n"
    return body.rstrip() + "\n" + tail


def discover_stage1_sessions() -> List[SessionRef]:
    sessions: List[SessionRef] = []
    if not META_SESSIONS_DIR.exists():
        return sessions

    dir_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})-s(\d{3})$")
    for entry in META_SESSIONS_DIR.iterdir():
        if not entry.is_dir():
            continue
        match = dir_pattern.match(entry.name)
        if not match:
            continue

        date = match.group(1)
        session_number = int(match.group(2))
        events_path = entry / "events.yaml"
        world_path = entry / "world.yaml"
        if not events_path.exists() or not world_path.exists():
            continue

        events_data = load_data(events_path, {})
        source_note = ""
        if isinstance(events_data, dict):
            session_block = events_data.get("session", {})
            if isinstance(session_block, dict):
                # Paths may contain meaningful internal spaces; trim only the ends.
                source_note = str(session_block.get("source_note", "")).strip()
        if not source_note:
            source_note = f"Sessions/Notes/{date} - Session {session_number:02d}.md"

        summary_path = resolve_summary_path(date, session_number)
        sessions.append(
            SessionRef(
                session_number=session_number,
                date=date,
                meta_dir=entry,
                events_path=events_path,
                world_path=world_path,
                source_note=REPO_ROOT / source_note,
                summary_path=summary_path,
            )
        )

    sessions.sort(key=lambda s: (s.session_number, s.date))
    return sessions


def resolve_summary_path(date: str, session_number: int) -> Path:
    preferred = SUMMARIES_DIR / f"{date} - Session {session_number:03d} - Summary.md"
    if preferred.exists():
        return preferred

    fallback_2d = SUMMARIES_DIR / f"{date} - Session {session_number:02d} - Summary.md"
    if fallback_2d.exists():
        return fallback_2d

    pattern = re.compile(
        rf"^{re.escape(date)}\s*-\s*Session\s*0*{session_number}\s*-\s*Summary(?:\s*-\s*V\d+)?\.md$"
    )
    candidates = [p for p in SUMMARIES_DIR.glob("*.md") if pattern.match(p.name)]

    non_versioned = [p for p in candidates if not re.search(r"\s-\sV\d+\.md$", p.name)]
    pool = non_versioned or candidates
    if pool:
        pool.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return pool[0]

    return preferred


def select_session(selector: str) -> SessionRef:
    sessions = discover_stage1_sessions()
    if not sessions:
        raise QuestError("No Stage 1 session artifacts found in .dnd-meta/sessions")

    lowered = normalize_space(selector).lower()
    if not lowered or "latest" in lowered:
        chosen = sessions[-1]
    else:
        number_match = re.search(r"(\d{1,3})", lowered)
        if number_match:
            target = int(number_match.group(1))
            matches = [s for s in sessions if s.session_number == target]
            if not matches:
                raise QuestError(f"No Stage 1 artifacts found for Session {target:03d}")
            chosen = matches[-1]
        else:
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", lowered)
            if not date_match:
                raise QuestError(f"Unable to resolve session selector: {selector!r}")
            target_date = date_match.group(1)
            matches = [s for s in sessions if s.date == target_date]
            if not matches:
                raise QuestError(f"No Stage 1 artifacts found for date {target_date}")
            chosen = matches[-1]

    if not chosen.events_path.exists() or not chosen.world_path.exists():
        raise QuestError("Session missing Stage 1 artifacts (events.yaml and/or world.yaml)")
    if not chosen.source_note.exists():
        raise QuestError(f"Missing source note: {chosen.source_note.relative_to(REPO_ROOT)}")
    if not chosen.summary_path.exists():
        raise QuestError(
            "Missing session summary. Run $dnd-session-summarise first. "
            f"Expected: {chosen.summary_path.relative_to(REPO_ROOT)}"
        )
    return chosen


def parse_index(raw: str) -> Optional[Tuple[int, int]]:
    if not raw or ":" not in raw:
        return None
    left, right = raw.split(":", 1)
    try:
        line = int(left)
        col = int(right)
    except ValueError:
        return None
    if line < 1 or col < 1:
        return None
    return line, col


def extract_note_span_snippet(note_lines: List[str], start_raw: str, end_raw: str, max_chars: int = 220) -> str:
    start = parse_index(start_raw)
    end = parse_index(end_raw)
    if not start or not end or not note_lines:
        return ""

    s_line, s_col = start
    e_line, e_col = end
    if s_line > len(note_lines):
        return ""

    e_line = min(e_line, len(note_lines))
    s_line = max(1, s_line)
    s_col = max(1, s_col)
    e_col = max(1, e_col)

    if s_line == e_line:
        line = note_lines[s_line - 1]
        if not line:
            return ""
        s_col = min(s_col, max(1, len(line)))
        e_col = min(e_col, max(1, len(line)))
        if e_col < s_col:
            return ""
        text = line[s_col - 1 : e_col]
    else:
        chunks: List[str] = []
        first = note_lines[s_line - 1]
        s_col = min(s_col, max(1, len(first))) if first else 1
        chunks.append(first[s_col - 1 :] if first else "")

        for line_no in range(s_line + 1, e_line):
            chunks.append(note_lines[line_no - 1])

        last = note_lines[e_line - 1]
        e_col = min(e_col, max(1, len(last))) if last else 1
        chunks.append(last[:e_col] if last else "")
        text = "\n".join(chunks)

    snippet = normalize_space(text)
    if len(snippet) > max_chars:
        snippet = snippet[: max_chars - 1].rstrip() + "…"
    return snippet


def tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t and t not in STOPWORDS]


def jaccard_similarity(left: str, right: str) -> float:
    a = set(tokenize(left))
    b = set(tokenize(right))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def confidence_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 0.9:
        return "high"
    if score >= 0.75:
        return "medium"
    return "low"


def classify_priority(text: str, status: str, confidence: float) -> Tuple[str, str]:
    lowered = normalize_space(text).lower()
    score = 0

    score += sum(1 for marker in HIGH_MARKERS if marker in lowered)
    score -= sum(1 for marker in LOW_MARKERS if marker in lowered)

    if status in {"active", "blocked"}:
        score += 1
    if status in {"deferred", "not_started"}:
        score -= 1

    if confidence >= 0.9:
        score += 1
    elif confidence < 0.7:
        score -= 1

    if score >= 3:
        return "high", "Immediate risk/impact markers or strong mission pressure detected."
    if score <= -1:
        return "low", "Monitoring/uncertain signal with lower immediate impact."
    return "medium", "Important open thread, but without immediate crisis markers."


def classify_horizon(text: str) -> Tuple[str, str]:
    lowered = normalize_space(text).lower()
    short_hits = sum(1 for marker in SHORT_MARKERS if marker in lowered)
    long_hits = sum(1 for marker in LONG_MARKERS if marker in lowered)

    if long_hits > short_hits:
        return "long_term", "Likely to evolve across multiple sessions."
    return "short_term", "Likely actionable within the next one or two sessions."


def sanitize_filename(title: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "", title).strip()
    safe = re.sub(r"\s+", " ", safe)
    return safe or "Untitled Quest"


def quest_dir_for_status(status: str) -> Path:
    if status in {"completed", "failed", "abandoned"}:
        return QUESTS_COMPLETED_DIR
    return QUESTS_ACTIVE_DIR


def normalize_quest_rel(path_rel: str, status: str, title: str) -> str:
    rel = normalize_space(path_rel).replace("\\", "/")
    filename = f"{sanitize_filename(title)}.md"
    default_rel = str((quest_dir_for_status(status) / filename).relative_to(REPO_ROOT)).replace("\\", "/")

    if not rel:
        return default_rel

    if rel.startswith("Sessions/Quests/"):
        return f"Quests/Active/{Path(rel).name}"

    if rel.startswith("Quests/Completed/"):
        return rel

    if rel.startswith("Quests/Active/"):
        file_name = Path(rel).name
        base = quest_dir_for_status(status)
        return str((base / file_name).relative_to(REPO_ROOT)).replace("\\", "/")

    return default_rel


def summary_link(session: SessionRef) -> str:
    return f"[[{session.summary_path.stem}]]"


def table_escape(value: str) -> str:
    text = normalize_space(str(value))
    return re.sub(r"(?<!\\)\|", r"\\|", text)


def escape_wikilink_pipes_in_tables(text: str) -> str:
    link_pattern = re.compile(r"\[\[([^\]]*?)(?<!\\)\|([^\]]+)\]\]")
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        if line.lstrip().startswith("|"):
            line = link_pattern.sub(r"[[\1\\|\2]]", line)
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def human_status(value: str) -> str:
    mapping = {
        "not_started": "Not Started",
        "active": "Active",
        "blocked": "Blocked",
        "completed": "Completed",
        "failed": "Failed",
        "abandoned": "Abandoned",
    }
    key = normalize_space(value).lower()
    return mapping.get(key, normalize_space(value).replace("_", " ").title())


def human_priority(value: str) -> str:
    mapping = {
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "critical": "Critical",
    }
    key = normalize_space(value).lower()
    return mapping.get(key, normalize_space(value).replace("_", " ").title())


def human_horizon(value: str) -> str:
    mapping = {
        "short_term": "Short-Term",
        "long_term": "Long-Term",
    }
    key = normalize_space(value).lower()
    return mapping.get(key, normalize_space(value).replace("_", " ").title())


def normalize_summary_wikilink(value: str) -> str:
    match = re.search(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", value)
    if not match:
        return value
    target = normalize_space(match.group(1)).replace("\\", "/")
    if target.startswith("Sessions/Summaries/"):
        target = Path(target).stem
    elif target.endswith(".md"):
        target = Path(target).stem
    return f"[[{target}]]"


def build_entity_index(world_data: Dict[str, Any]) -> Dict[str, Tuple[str, str]]:
    index: Dict[str, Tuple[str, str]] = {}
    entities = world_data.get("entities", []) if isinstance(world_data, dict) else []
    if not isinstance(entities, list):
        return index

    for item in entities:
        if not isinstance(item, dict):
            continue
        canonical = normalize_space(str(item.get("canonical_title", "")))
        entity_type = normalize_space(str(item.get("entity_type", "unknown"))).lower()
        if not canonical:
            continue

        names: List[str] = [canonical]
        mention = normalize_space(str(item.get("mention", "")))
        if mention:
            names.append(mention)
        aliases = item.get("aliases", [])
        if isinstance(aliases, list):
            names.extend(normalize_space(str(a)) for a in aliases if normalize_space(str(a)))

        for name in names:
            index[normalize_name(name)] = (canonical, entity_type)
    return index


def resolve_entity(name: str, index: Dict[str, Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    return index.get(normalize_name(name))


def link_entity(name: str, index: Dict[str, Tuple[str, str]]) -> str:
    resolved = resolve_entity(name, index)
    if not resolved:
        return name
    canonical, _ = resolved
    if normalize_name(name) == normalize_name(canonical):
        return f"[[{canonical}]]"
    return f"[[{canonical}|{name}]]"


def candidate_keywords(text: str) -> List[str]:
    out = []
    for token in tokenize(text):
        if len(token) < 4:
            continue
        keyword = normalize_keyword(token)
        if keyword:
            out.append(keyword)
    return dedupe_preserve(out)[:8]


def title_from_hook(hook: str) -> str:
    cleaned = normalize_space(hook).rstrip(".")
    if not cleaned:
        return "Follow Up"
    if len(cleaned) > 72:
        cleaned = cleaned[:72].rstrip()
    return cleaned[0].upper() + cleaned[1:]


def build_candidates(events_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()

    raw_candidates = events_data.get("quest_candidates", [])
    if not isinstance(raw_candidates, list):
        raw_candidates = []

    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        title = normalize_space(str(item.get("title", "")))
        description = normalize_space(str(item.get("description", "")))
        key = normalize_keyword(str(item.get("key", ""))) or slugify(title or description)
        status = normalize_space(str(item.get("status", "active"))).lower() or "active"
        if status in {"completed", "failed", "abandoned"}:
            continue
        if not key:
            continue

        source_event_ids = item.get("source_event_ids", [])
        if not isinstance(source_event_ids, list):
            source_event_ids = []

        raw_keywords = item.get("keywords", [])
        if not isinstance(raw_keywords, list):
            raw_keywords = []

        candidate = {
            "key": key,
            "title": title or title_from_hook(description or key.replace("-", " ")),
            "objective": description or title,
            "status": status,
            "confidence": float(item.get("confidence", 0.75) or 0.75),
            "source_event_ids": [normalize_space(str(eid)) for eid in source_event_ids if normalize_space(str(eid))],
            "keywords": dedupe_preserve(
                [normalize_keyword(str(k)) for k in raw_keywords if normalize_keyword(str(k))]
            ),
            "source": "quest_candidates",
        }
        candidates.append(candidate)
        seen_keys.add(key)

    events = events_data.get("events", [])
    if not isinstance(events, list):
        events = []

    for ev in events:
        if not isinstance(ev, dict):
            continue
        hooks = ev.get("quest_hooks", [])
        if not isinstance(hooks, list):
            continue
        event_id = normalize_space(str(ev.get("id", "")))
        event_conf = float(ev.get("confidence", 0.75) or 0.75)

        for hook in hooks:
            hook_text = normalize_space(str(hook))
            if not hook_text:
                continue
            if any(jaccard_similarity(hook_text, c.get("objective", "")) >= 0.66 for c in candidates):
                continue

            key = slugify(hook_text)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            candidates.append(
                {
                    "key": key,
                    "title": title_from_hook(hook_text),
                    "objective": hook_text,
                    "status": "proposed",
                    "confidence": event_conf,
                    "source_event_ids": [event_id] if event_id else [],
                    "keywords": candidate_keywords(hook_text),
                    "source": "event_hooks",
                }
            )

    return dedupe_candidates(candidates)


def status_rank(status: str) -> int:
    order = {
        "active": 4,
        "blocked": 3,
        "proposed": 2,
        "deferred": 1,
        "not_started": 1,
    }
    return order.get(normalize_space(status).lower(), 0)


def dedupe_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for candidate in candidates:
        merged = False
        for existing in out:
            title_sim = jaccard_similarity(candidate.get("title", ""), existing.get("title", ""))
            objective_sim = jaccard_similarity(
                candidate.get("objective", ""), existing.get("objective", "")
            )
            if candidate.get("key") != existing.get("key") and max(title_sim, objective_sim) < 0.55:
                continue

            if status_rank(candidate.get("status", "")) > status_rank(existing.get("status", "")):
                existing["status"] = candidate.get("status", existing.get("status"))
            existing["confidence"] = max(
                float(existing.get("confidence", 0.75) or 0.75),
                float(candidate.get("confidence", 0.75) or 0.75),
            )
            existing["source_event_ids"] = dedupe_preserve(
                existing.get("source_event_ids", []) + candidate.get("source_event_ids", [])
            )
            existing["keywords"] = dedupe_preserve(
                existing.get("keywords", []) + candidate.get("keywords", [])
            )
            merged = True
            break

        if not merged:
            out.append(dict(candidate))

    return out


def summary_signal_lines(summary_text: str) -> List[Tuple[str, str]]:
    _, body = split_frontmatter(summary_text)
    section = ""
    out: List[Tuple[str, str]] = []

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        clean = normalize_space(line)
        if not clean:
            continue

        if line.startswith("## "):
            section = normalize_space(re.sub(r"^##\s+", "", line))
            continue
        if line.startswith("# "):
            continue
        if line.startswith("|"):
            continue
        if clean.startswith("**Date:**") or clean.startswith("**Location(s):**") or clean.startswith("**Party Composition:**"):
            continue

        # Strip basic list/number prefixes for matching quality.
        signal = re.sub(r"^\s*[-*]\s+", "", clean)
        signal = re.sub(r"^\s*\d+\.\s+", "", signal)
        signal = normalize_space(signal)
        if not signal:
            continue
        out.append((section, signal))

    return out


def summary_line_score(section: str, line: str) -> int:
    section_l = section.lower()
    line_l = line.lower()
    score = 0

    if "plot threads" in section_l:
        score += 5
    elif "open questions" in section_l:
        score += 5
    elif "key events" in section_l:
        score += 4
    elif "session timeline" in section_l:
        score += 3
    elif "summary" in section_l:
        score += 2

    if line.startswith("**Ongoing:**") or line.startswith("**New Leads:**"):
        score += 2
    if "unresolved" in line_l or "unknown" in line_l or "question" in line_l:
        score += 1

    return score


def find_summary_hints(summary_text: str, candidate: Dict[str, Any]) -> List[str]:
    lines = summary_signal_lines(summary_text)
    probe_text = " ".join(
        [candidate.get("title", ""), candidate.get("objective", ""), " ".join(candidate.get("keywords", []))]
    )
    tokens = [t for t in tokenize(probe_text) if len(t) >= 4]
    if not tokens:
        return []

    scored: List[Tuple[int, str]] = []
    for section, line in lines:
        lowered = line.lower()
        if any(tok in lowered for tok in tokens):
            scored.append((summary_line_score(section, line), line))

    if not scored:
        return []

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked_lines = dedupe_preserve([line for _, line in scored])
    return ranked_lines[:2]


def summarize_progress_line(text: str, max_len: int = 180) -> str:
    clean = normalize_space(text).strip("- ")
    clean = re.sub(r"^\*\*[^*]+:\*\*\s*", "", clean)
    clean = re.sub(r"^\*\*[^*]+\*\*:\s*", "", clean)
    clean = clean.rstrip(".")
    if not clean:
        return ""
    if len(clean) <= max_len:
        return clean
    clipped = clean[:max_len].rsplit(" ", 1)[0].strip()
    if not clipped:
        clipped = clean[:max_len].strip()
    return clipped.rstrip(".") + "..."


def build_progress_bullets(latest_update: str, evidence_rows: List[Tuple[str, str, str]]) -> List[str]:
    bullets: List[str] = []

    latest_summary = summarize_progress_line(latest_update, max_len=180)
    if latest_summary:
        bullets.append(f"- Key development: {latest_summary}.")

    if evidence_rows:
        evidence_summary = summarize_progress_line(evidence_rows[0][0], max_len=160)
        if evidence_summary and normalize_name(evidence_summary) != normalize_name(latest_summary):
            bullets.append(f"- Evidence noted: {evidence_summary}.")

    if not bullets:
        bullets.append("- Referenced this session for continued tracking.")

    return bullets


def heading_stem(heading: str) -> str:
    match = re.search(r"\[\[([^\]|]+)", heading)
    if not match:
        return ""
    return Path(match.group(1)).stem


def find_progress_heading_index(lines: List[str], heading: str) -> Optional[int]:
    for idx, line in enumerate(lines):
        if normalize_space(line) == normalize_space(heading):
            return idx

    target_stem = heading_stem(heading)
    if not target_stem:
        return None

    for idx, line in enumerate(lines):
        if not normalize_space(line).startswith("### [["):
            continue
        if target_stem and target_stem in line:
            return idx
    return None


def extract_existing_progress_content(body: str) -> List[str]:
    match = re.search(
        r"^##\s+🧵\s+Progress\s+Log\s*$([\s\S]*?)(?=^##\s+|^<!--\s*dnd-managed:end\s*-->\s*$|\Z)",
        body,
        re.MULTILINE,
    )
    if not match:
        return []
    content = match.group(1).strip("\n")
    if not content:
        return []
    lines = []
    for line in content.splitlines():
        clean = normalize_space(line)
        if clean in {MANAGED_START, MANAGED_END}:
            continue
        lines.append(line)
    return lines


def merge_progress(existing_lines: List[str], heading: str, bullets: List[str]) -> List[str]:
    content = list(existing_lines)
    idx = find_progress_heading_index(content, heading)

    if idx is None:
        if content and content[-1].strip() != "":
            content.append("")
        content.append(heading)
        content.extend(bullets)
        return content

    next_heading_idx = len(content)
    for i in range(idx + 1, len(content)):
        if normalize_space(content[i]).startswith("### [["):
            next_heading_idx = i
            break

    existing_section = content[idx + 1 : next_heading_idx]
    existing_clean: List[str] = []
    managed_prefixes = (
        "- Key development:",
        "- Evidence noted:",
        "- Referenced this session for continued tracking.",
    )
    for line in existing_section:
        clean_line = normalize_space(line)
        if re.match(r"^- Added/updated from Session \d{3} metadata review\.$", clean_line):
            continue
        if any(clean_line.startswith(prefix) for prefix in managed_prefixes):
            continue
        existing_clean.append(line)
    normalized_existing = {normalize_space(line) for line in existing_clean}

    for bullet in bullets:
        if normalize_space(bullet) in normalized_existing:
            continue
        existing_clean.append(bullet)
        normalized_existing.add(normalize_space(bullet))

    return content[: idx + 1] + existing_clean + content[next_heading_idx :]


def format_progress_lines(lines: List[str]) -> List[str]:
    formatted: List[str] = []
    for idx, line in enumerate(lines):
        clean = normalize_space(line)
        formatted.append(line)
        if not clean.startswith("### [["):
            continue
        next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
        if normalize_space(next_line) == "":
            continue
        formatted.append("")
    return formatted


def strip_managed_artifacts(body: str) -> str:
    without_blocks = re.sub(
        re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END),
        "",
        body,
        flags=re.DOTALL,
    )
    without_markers = re.sub(
        r"^<!--\s*dnd-managed:(?:start|end)\s*-->\s*$\n?",
        "",
        without_blocks,
        flags=re.MULTILINE,
    )
    without_orphans = re.sub(
        r"^###\s+\[\[[^\]]+\]\]\n- Added/updated from Session \d{3} metadata review\.\n?",
        "",
        without_markers,
        flags=re.MULTILINE,
    )
    compact = re.sub(r"\n{3,}", "\n\n", without_orphans).strip("\n")
    return compact + "\n" if compact else ""


def insert_managed_before_notes(body: str, managed: str) -> str:
    block = f"{MANAGED_START}\n{managed.rstrip()}\n\n{MANAGED_END}"
    notes_match = re.search(r"^##\s+📝\s+Notes\s*$", body, re.MULTILINE)
    if not notes_match:
        stripped = body.rstrip()
        if stripped:
            return stripped + "\n\n" + block + "\n"
        return block + "\n"

    before = body[: notes_match.start()].rstrip("\n")
    after = body[notes_match.start() :].lstrip("\n")
    if before:
        return before + "\n\n" + block + "\n\n" + after
    return block + "\n\n" + after


def render_managed_block(payload: Dict[str, Any]) -> str:
    lines: List[str] = []

    lines.append("## 🎯 Objective")
    lines.append("")
    lines.append(f"- {payload['objective']}")
    lines.append("")

    lines.append("## 📌 Current Status")
    lines.append("")
    lines.append(f"- **Status:** {human_status(payload['status'])}")
    lines.append(f"- **Latest Update:** {payload['latest_update']}")
    lines.append(f"- **Blockers:** {payload['blockers']}")
    lines.append("")

    lines.append("## ⚖️ Priority & Horizon")
    lines.append("")
    lines.append(f"- **Priority:** {human_priority(payload['priority'])}")
    lines.append(f"- **Horizon:** {human_horizon(payload['horizon'])}")
    lines.append(f"- **Rationale:** {payload['priority_rationale']} {payload['horizon_rationale']}")
    lines.append("")

    lines.append("## 🧾 Clues & Evidence")
    lines.append("")
    lines.append("| Evidence | Source | Confidence |")
    lines.append("|---|---|---|")
    for row in payload["evidence_rows"]:
        lines.append(f"| {table_escape(row[0])} | {table_escape(row[1])} | {table_escape(row[2])} |")
    lines.append("")

    lines.append("## ✅ Action Plan (Next Steps)")
    lines.append("")
    for idx, action in enumerate(payload["next_actions"], start=1):
        lines.append(f"{idx}. {action}")
    lines.append("")

    lines.append("## 🏁 Success Criteria")
    lines.append("")
    for criterion in payload["success_criteria"]:
        lines.append(f"- {criterion}")
    lines.append("")

    lines.append("## ⚠️ Risks & Complications")
    lines.append("")
    for risk in payload["risks"]:
        lines.append(f"- {risk}")
    lines.append("")

    lines.append("## 🔗 Related Entities")
    lines.append("")
    lines.append(f"- **Characters:** {', '.join(payload['related']['characters']) if payload['related']['characters'] else 'none recorded'}")
    lines.append(f"- **Factions:** {', '.join(payload['related']['factions']) if payload['related']['factions'] else 'none recorded'}")
    lines.append(f"- **Locations:** {', '.join(payload['related']['locations']) if payload['related']['locations'] else 'none recorded'}")
    lines.append(f"- **Items:** {', '.join(payload['related']['items']) if payload['related']['items'] else 'none recorded'}")
    lines.append("")

    lines.append("## ❓ Open Questions")
    lines.append("")
    for question in payload["open_questions"]:
        lines.append(f"- {question}")
    lines.append("")

    lines.append("## 🧵 Progress Log")
    lines.append("")
    lines.extend(format_progress_lines(payload["progress_lines"]))

    return "\n".join(lines).rstrip() + "\n"


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def frontmatter_block(payload: Dict[str, Any]) -> str:
    lines: List[str] = ["---"]
    lines.append("type: quest")
    lines.append(f"status: {payload['status']}")
    lines.append(f"priority: {payload['priority']}")
    lines.append(f"horizon: {payload['horizon']}")
    lines.append(f"owner: {payload['owner']}")
    lines.append(f"created_session: {yaml_quote(payload['created_session_link'])}")
    lines.append(f"last_updated_session: {yaml_quote(payload['summary_link'])}")
    lines.append(f"source_summary: {yaml_quote(payload['summary_link'])}")
    lines.append(f"source_note: {yaml_quote(payload['source_note'])}")
    lines.append(f"last_reviewed_at: {yaml_quote(payload['timestamp'])}")

    keywords = payload.get("keywords", [])
    if keywords:
        lines.append("keywords:")
        for item in keywords:
            lines.append(f"  - {item}")
    else:
        lines.append("keywords: []")

    event_ids = payload.get("source_event_ids", [])
    if event_ids:
        lines.append("source_event_ids:")
        for item in event_ids:
            lines.append(f"  - {yaml_quote(item)}")
    else:
        lines.append("source_event_ids: []")

    lines.append("---")
    return "\n".join(lines) + "\n"


def status_from_candidate(status: str) -> str:
    status = normalize_space(status).lower()
    mapping = {
        "active": "active",
        "proposed": "not_started",
        "deferred": "not_started",
        "blocked": "blocked",
        "not_started": "not_started",
        "completed": "completed",
        "failed": "failed",
        "abandoned": "abandoned",
    }
    return mapping.get(status, "active")


def build_payload(
    candidate: Dict[str, Any],
    session: SessionRef,
    events_map: Dict[str, Dict[str, Any]],
    summary_text: str,
    note_lines: List[str],
    entity_index: Dict[str, Tuple[str, str]],
    existing_body: str,
) -> Dict[str, Any]:
    title = normalize_space(candidate.get("title", "")) or candidate["key"].replace("-", " ").title()
    objective = normalize_space(candidate.get("objective", "")) or title
    raw_status = status_from_candidate(candidate.get("status", "active"))
    confidence = float(candidate.get("confidence", 0.75) or 0.75)

    priority, priority_rationale = classify_priority(
        f"{title} {objective} {' '.join(candidate.get('keywords', []))}",
        raw_status,
        confidence,
    )
    horizon, horizon_rationale = classify_horizon(f"{title} {objective}")

    source_event_ids = dedupe_preserve(candidate.get("source_event_ids", []))
    hints = find_summary_hints(summary_text, candidate)
    latest_update = hints[0] if hints else f"Flagged from Session {session.session_number:03d} metadata and notes."

    related: Dict[str, List[str]] = {
        "characters": [],
        "factions": [],
        "locations": [],
        "items": [],
    }

    evidence_rows: List[Tuple[str, str, str]] = []
    for event_id in source_event_ids:
        ev = events_map.get(event_id)
        if not ev:
            continue

        for key, bucket in [
            ("participants", "characters"),
            ("factions", "factions"),
            ("locations", "locations"),
            ("items", "items"),
        ]:
            values = ev.get(key, [])
            if not isinstance(values, list):
                continue
            for raw_name in values:
                name = normalize_space(str(raw_name))
                if not name:
                    continue
                linked = link_entity(name, entity_index)
                if linked.startswith("[["):
                    related[bucket].append(linked)

        excerpt = normalize_space(str(ev.get("source_excerpt", "")))
        if not excerpt:
            excerpt = extract_note_span_snippet(
                note_lines,
                normalize_space(str(ev.get("start_index", ""))),
                normalize_space(str(ev.get("end_index", "")),),
            )
        if not excerpt:
            excerpt = normalize_space(str(ev.get("description", "")))

        start_idx = normalize_space(str(ev.get("start_index", "")))
        end_idx = normalize_space(str(ev.get("end_index", "")))
        source_ref = summary_link(session)
        if start_idx and end_idx:
            source_ref = f"{source_ref} (Notes {start_idx}-{end_idx})"

        if excerpt:
            evidence_rows.append((excerpt, source_ref, confidence_label(ev.get("confidence"))))

    related = {k: dedupe_preserve(v)[:6] for k, v in related.items()}

    if not evidence_rows:
        evidence_rows = [(objective, summary_link(session), confidence_label(confidence))]
    evidence_rows = evidence_rows[:3]

    blockers = "none confirmed"
    if priority == "high":
        blockers = "time pressure and hostile actor interference"

    next_actions = [
        f"Gather one concrete, verifiable fact advancing: {objective.rstrip('.')}.",
        "Assign a party lead to report findings in the next session summary.",
    ]
    if horizon == "long_term":
        next_actions[1] = "Track movement each session and reassess escalation criteria."

    success_criteria = [
        "The objective can be answered with evidence-backed facts.",
        "Result and impact are recorded in a later session summary.",
    ]

    existing_risks = extract_section_bullets(existing_body, "⚠️ Risks & Complications")
    if existing_risks == [LEGACY_DEFAULT_RISK]:
        existing_risks = []

    risks = existing_risks or infer_risks(
        title=title,
        objective=objective,
        latest_update=latest_update,
        priority=priority,
        horizon=horizon,
        events_map=events_map,
        source_event_ids=source_event_ids,
    )
    if priority == "low":
        risks.append("Signal may be noise; avoid over-investment before corroboration.")
    risks = dedupe_preserve(risks)

    open_questions = [
        f"What evidence would decisively resolve: {objective.rstrip('.')}?",
    ]

    progress_lines = extract_existing_progress_content(existing_body)
    normalized_progress: List[str] = []
    for line in progress_lines:
        if normalize_space(line).startswith("### [[") and session.summary_path.stem in line:
            normalized_progress.append(f"### {summary_link(session)}")
            continue
        normalized_progress.append(line)
    progress_lines = normalized_progress
    current_heading = f"### {summary_link(session)}"
    current_bullets = build_progress_bullets(latest_update, evidence_rows)
    progress_lines = merge_progress(progress_lines, current_heading, current_bullets)

    created_link = summary_link(session)
    existing_fm, _ = split_frontmatter(existing_body)
    if existing_fm:
        created_match = re.search(r"^created_session:\s*(.+)$", existing_fm, re.MULTILINE)
        if created_match:
            created_link = normalize_space(created_match.group(1)).strip('"') or created_link
    created_link = normalize_summary_wikilink(created_link)

    return {
        "key": candidate["key"],
        "title": title,
        "objective": objective,
        "status": raw_status,
        "priority": priority,
        "priority_rationale": priority_rationale,
        "horizon": horizon,
        "horizon_rationale": horizon_rationale,
        "owner": "shared",
        "latest_update": latest_update,
        "blockers": blockers,
        "evidence_rows": evidence_rows,
        "next_actions": next_actions,
        "success_criteria": success_criteria,
        "risks": risks,
        "open_questions": open_questions,
        "related": related,
        "progress_lines": progress_lines,
        "keywords": dedupe_preserve(candidate.get("keywords", []) + candidate_keywords(objective))[:10],
        "source_event_ids": source_event_ids,
        "summary_link": summary_link(session),
        "created_session_link": created_link,
        "source_note": str(session.source_note.relative_to(REPO_ROOT)),
        "timestamp": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def merge_with_template(payload: Dict[str, Any], existing_text: Optional[str]) -> str:
    if existing_text:
        _, body = split_frontmatter(existing_text)
    else:
        template = read_text(TEMPLATE_PATH)
        _, body = split_frontmatter(template)

    body = strip_managed_artifacts(body)
    body = ensure_notes_section(body)
    body = insert_managed_before_notes(body, render_managed_block(payload))
    output = frontmatter_block(payload) + body.lstrip("\n")
    return escape_wikilink_pipes_in_tables(output)


def review_low_priority(candidates: List[Dict[str, Any]], include_low: bool, exclude_low: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    low = [c for c in candidates if c.get("priority") == "low"]
    if not low:
        return candidates, []

    if include_low:
        return candidates, []

    if exclude_low:
        kept = [c for c in candidates if c.get("priority") != "low"]
        return kept, low

    if not sys.stdin.isatty():
        print("Low-priority quest review required.")
        print("Re-run with --include-low or --exclude-low, or run interactively to review one by one.")
        for item in low:
            print(f"- {item['title']} ({item['key']}): {item['priority_rationale']}")
        raise SystemExit(2)

    approved_keys = set()
    for item in low:
        answer = input(
            f"Include low-priority quest '{item['title']}'? [y/N]: "
        ).strip().lower()
        if answer in {"y", "yes"}:
            approved_keys.add(item["key"])

    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for item in candidates:
        if item.get("priority") != "low":
            kept.append(item)
            continue
        if item["key"] in approved_keys:
            kept.append(item)
        else:
            dropped.append(item)
    return kept, dropped


def quest_priority_rank(priority: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(normalize_space(priority).lower(), 0)


def quest_status_rank(status: str) -> int:
    status_n = normalize_space(status).lower()
    if status_n == "active":
        return 3
    if status_n in {"blocked", "not_started"}:
        return 2
    if status_n in {"completed", "failed", "abandoned"}:
        return 1
    return 0


def parse_frontmatter_data(text: str) -> Dict[str, Any]:
    frontmatter, _ = split_frontmatter(text)
    if not frontmatter:
        return {}
    raw = re.sub(r"\A---\n", "", frontmatter)
    raw = re.sub(r"\n---\n?\Z", "\n", raw)
    try:
        parsed = ruby_yaml_to_json(raw)
    except QuestError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def extract_quest_objective(text: str) -> str:
    match = re.search(
        r"^##\s+🎯\s+Objective\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        re.MULTILINE,
    )
    if not match:
        return ""
    block = match.group(1)
    for line in block.splitlines():
        clean = normalize_space(line)
        if clean.startswith("- "):
            return normalize_space(clean[2:]).rstrip(".")
    return ""


def extract_section_bullets(text: str, heading: str) -> List[str]:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return []

    bullets: List[str] = []
    for line in match.group(1).splitlines():
        clean = normalize_space(line)
        if clean.startswith("- "):
            bullets.append(normalize_space(clean[2:]))
    return dedupe_preserve([item for item in bullets if item])


def infer_risks(
    title: str,
    objective: str,
    latest_update: str,
    priority: str,
    horizon: str,
    events_map: Dict[str, Dict[str, Any]],
    source_event_ids: List[str],
) -> List[str]:
    corpus_parts = [title, objective, latest_update]
    for event_id in source_event_ids:
        event = events_map.get(event_id)
        if not isinstance(event, dict):
            continue
        for key in ("title", "description", "source_excerpt"):
            value = normalize_space(str(event.get(key, "")))
            if value:
                corpus_parts.append(value)
    corpus = normalize_name(" ".join(corpus_parts))

    risks: List[str] = []
    if any(term in corpus for term in ("pirate", "boarding", "ambush", "hostile", "attack", "callis")):
        risks.append("Escalation from organized hostile actors is likely if this thread is pursued openly.")
    if any(term in corpus for term in ("cannon", "ship", "voyage", "mast", "sea", "naval")):
        risks.append("Operational pressure on the vessel could limit options before objective progress is secured.")
    if any(term in corpus for term in ("interrogate", "prisoner", "capture", "captain")):
        risks.append("Information from a captive source may be incomplete, coerced, or intentionally misleading.")
    if any(term in corpus for term in ("asmodeus", "infernal", "cult")):
        risks.append("Infernal-affiliated links may expose the party to hidden sponsors and second-order retaliation.")
    if any(term in corpus for term in ("feign", "deception", "disguise", "cover")):
        risks.append("If the deception plan is exposed early, tactical leverage may collapse quickly.")

    if priority == "high":
        risks.append("Delay increases the chance that adversaries reposition before evidence can be confirmed.")
    if horizon == "long_term":
        risks.append("Without session-by-session checkpoints, this thread can drift and become stale.")

    if not risks:
        risks.append("Lead quality is still developing; commit only after one corroborating data point.")
    return dedupe_preserve(risks)


def should_merge_quests(left: QuestFileMeta, right: QuestFileMeta) -> bool:
    title_sim = jaccard_similarity(left.title, right.title)
    objective_sim = jaccard_similarity(left.objective, right.objective)
    max_sim = max(title_sim, objective_sim)
    token_overlap = set(tokenize(left.title + " " + left.objective)) & set(
        tokenize(right.title + " " + right.objective)
    )

    if len(token_overlap) < 2:
        return False
    if title_sim >= 0.72 and objective_sim >= 0.58:
        return True
    if objective_sim >= 0.76:
        return True
    return max_sim >= 0.86


def choose_canonical_meta(items: List[QuestFileMeta]) -> QuestFileMeta:
    return sorted(
        items,
        key=lambda item: (
            quest_priority_rank(item.priority),
            quest_status_rank(item.status),
            -len(item.keys),
            -len(item.title),
            item.path_rel,
        ),
        reverse=True,
    )[0]


def normalize_wikilink_target(value: str) -> str:
    target = normalize_space(value).replace("\\", "/")
    if target.startswith("./"):
        target = target[2:]
    target = target.lstrip("/")
    if target.lower().endswith(".md"):
        target = target[:-3]
    return normalize_space(target).lower()


def build_wikilink_redirect_index(path_redirects: Dict[str, str]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for old_rel, canonical_rel in path_redirects.items():
        old_norm = normalize_space(old_rel).replace("\\", "/")
        canonical_norm = normalize_space(canonical_rel).replace("\\", "/")
        if not old_norm or not canonical_norm:
            continue
        variants = {
            normalize_wikilink_target(old_norm),
            normalize_wikilink_target(re.sub(r"\.md$", "", old_norm, flags=re.IGNORECASE)),
            normalize_wikilink_target(Path(old_norm).stem),
        }
        for variant in variants:
            if variant and variant not in index:
                index[variant] = canonical_norm
    return index


def rewrite_wikilink_targets(text: str, redirect_index: Dict[str, str]) -> Tuple[str, int]:
    if not redirect_index:
        return text, 0

    replacements = 0
    wikilink_pattern = re.compile(r"\[\[([^\]|]+)(\|[^\]]+)?\]\]")

    def repl(match: re.Match[str]) -> str:
        nonlocal replacements
        raw_target = match.group(1)
        suffix = match.group(2) or ""
        target_norm = normalize_wikilink_target(raw_target)
        canonical_rel = redirect_index.get(target_norm)
        if not canonical_rel:
            return match.group(0)

        cleaned = normalize_space(raw_target)
        uses_path = "/" in cleaned or "\\" in cleaned or cleaned.startswith(".")
        keep_ext = cleaned.lower().endswith(".md")
        if uses_path:
            new_target = canonical_rel if keep_ext else re.sub(r"\.md$", "", canonical_rel, flags=re.IGNORECASE)
        else:
            new_target = Path(canonical_rel).stem

        if normalize_space(raw_target) == normalize_space(new_target):
            return match.group(0)
        replacements += 1
        return f"[[{new_target}{suffix}]]"

    updated = wikilink_pattern.sub(repl, text)
    return updated, replacements


def update_consolidation_backlinks(path_redirects: Dict[str, str], dry_run: bool) -> Dict[str, int]:
    redirect_index = build_wikilink_redirect_index(path_redirects)
    if not redirect_index:
        return {"files_updated": 0, "links_updated": 0}

    files_updated = 0
    links_updated = 0
    skip_roots = {".codex", ".dnd-meta"}
    redirected_files = {
        normalize_space(path).replace("\\", "/")
        for path in path_redirects.keys()
    }

    for path in REPO_ROOT.rglob("*.md"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in skip_roots for part in rel.parts):
            continue
        if normalize_space(str(rel)).replace("\\", "/") in redirected_files:
            continue
        original = read_text(path)
        updated, changed = rewrite_wikilink_targets(original, redirect_index)
        if changed == 0:
            continue
        links_updated += changed
        files_updated += 1
        write_text(path, updated, dry_run)

    return {"files_updated": files_updated, "links_updated": links_updated}


def consolidate_quest_map(
    quest_map: Dict[str, Any], dry_run: bool
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    quests = quest_map.get("quests", {})
    if not isinstance(quests, dict):
        return quest_map, {
            "clusters": 0,
            "remapped_keys": 0,
            "rule_remaps": 0,
            "deleted_files": [],
            "backlink_files_updated": 0,
            "backlink_links_updated": 0,
        }

    path_to_keys: Dict[str, List[str]] = {}
    for key, value in quests.items():
        if not isinstance(value, str):
            continue
        rel = normalize_space(value).replace("\\", "/")
        if not rel.startswith("Quests/"):
            continue
        path_to_keys.setdefault(rel, []).append(key)

    rule_remaps = 0
    rules_data = load_data(QUEST_CONSOLIDATION_RULES_PATH, {"aliases": {}})
    aliases = rules_data.get("aliases", {}) if isinstance(rules_data, dict) else {}
    if isinstance(aliases, dict):
        for alias_key, canonical_key in aliases.items():
            if not isinstance(alias_key, str) or not isinstance(canonical_key, str):
                continue
            alias_key_n = normalize_space(alias_key)
            canonical_key_n = normalize_space(canonical_key)
            if not alias_key_n or not canonical_key_n:
                continue
            canonical_path = quests.get(canonical_key_n)
            if not isinstance(canonical_path, str) or not canonical_path:
                continue
            current_path = quests.get(alias_key_n)
            if current_path != canonical_path:
                quests[alias_key_n] = canonical_path
                rule_remaps += 1

    metas: List[QuestFileMeta] = []
    for path_rel, keys in path_to_keys.items():
        path = REPO_ROOT / path_rel
        if not path.exists():
            continue
        text = read_text(path)
        fm = parse_frontmatter_data(text)
        _, body = split_frontmatter(text)
        metas.append(
            QuestFileMeta(
                path_rel=path_rel,
                keys=list(keys),
                title=normalize_space(path.stem),
                objective=extract_quest_objective(body),
                priority=normalize_space(str(fm.get("priority", ""))),
                status=normalize_space(str(fm.get("status", ""))),
            )
        )

    if len(metas) < 2:
        return quest_map, {
            "clusters": 0,
            "remapped_keys": 0,
            "rule_remaps": rule_remaps,
            "deleted_files": [],
            "backlink_files_updated": 0,
            "backlink_links_updated": 0,
        }

    parent = list(range(len(metas)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(metas)):
        for j in range(i + 1, len(metas)):
            if should_merge_quests(metas[i], metas[j]):
                union(i, j)

    clusters: Dict[int, List[QuestFileMeta]] = {}
    for idx, meta in enumerate(metas):
        clusters.setdefault(find(idx), []).append(meta)

    remapped_keys = 0
    deleted_files: List[str] = []
    merged_cluster_count = 0
    path_redirects: Dict[str, str] = {}

    for _, members in clusters.items():
        if len(members) < 2:
            continue
        merged_cluster_count += 1
        canonical = choose_canonical_meta(members)
        canonical_rel = canonical.path_rel
        for member in members:
            if member.path_rel == canonical_rel:
                continue
            path_redirects[member.path_rel] = canonical_rel
            for key in member.keys:
                current = quests.get(key)
                if current != canonical_rel:
                    quests[key] = canonical_rel
                    remapped_keys += 1

    backlink_updates = update_consolidation_backlinks(path_redirects, dry_run)

    referenced = {
        normalize_space(str(path)).replace("\\", "/")
        for path in quests.values()
        if isinstance(path, str)
    }
    for path_rel in path_to_keys.keys():
        if path_rel in referenced:
            continue
        path = REPO_ROOT / path_rel
        if path.exists():
            deleted_files.append(path_rel)
            if not dry_run:
                path.unlink()

    return quest_map, {
        "clusters": merged_cluster_count,
        "remapped_keys": remapped_keys,
        "rule_remaps": rule_remaps,
        "deleted_files": deleted_files,
        "backlink_files_updated": backlink_updates["files_updated"],
        "backlink_links_updated": backlink_updates["links_updated"],
    }


def run(args: argparse.Namespace) -> int:
    if args.consolidate_only:
        quest_map = load_data(QUEST_MAP_PATH, {"schema_version": 2, "quests": {}})
        if not isinstance(quest_map, dict):
            quest_map = {"schema_version": 2, "quests": {}}
        quest_map.setdefault("schema_version", 2)
        quest_map.setdefault("quests", {})
        if not isinstance(quest_map["quests"], dict):
            quest_map["quests"] = {}

        quest_map, consolidation = consolidate_quest_map(quest_map, args.dry_run)
        dump_data(QUEST_MAP_PATH, quest_map, args.dry_run)
        print("Quest consolidation pass complete.")
        print(f"Merged clusters: {consolidation['clusters']}")
        print(f"Remapped keys: {consolidation['remapped_keys']}")
        print(f"Rule remaps: {consolidation['rule_remaps']}")
        print(f"Backlink files updated: {consolidation['backlink_files_updated']}")
        print(f"Backlink links updated: {consolidation['backlink_links_updated']}")
        print(f"Deleted duplicate files: {len(consolidation['deleted_files'])}")
        if consolidation["deleted_files"]:
            print("Deleted files:")
            for item in consolidation["deleted_files"]:
                print(f"- {item}")
        return 0

    session = select_session(args.session)
    events_data = load_data(session.events_path, {})
    world_data = load_data(session.world_path, {})
    summary_text = read_text(session.summary_path)
    note_text = read_text(session.source_note)
    note_lines = note_text.splitlines()

    if not isinstance(events_data, dict) or not isinstance(world_data, dict):
        raise QuestError("Invalid Stage 1 artifact format (expected YAML object)")

    candidates = build_candidates(events_data)
    if not candidates:
        print("No quest candidates found from metadata.")
        return 0

    events = events_data.get("events", [])
    if not isinstance(events, list):
        events = []
    events_map = {
        normalize_space(str(item.get("id", ""))): item
        for item in events
        if isinstance(item, dict) and normalize_space(str(item.get("id", "")))
    }

    entity_index = build_entity_index(world_data)
    QUESTS_ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    QUESTS_COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
    quest_map = load_data(QUEST_MAP_PATH, {"schema_version": 2, "quests": {}})
    if not isinstance(quest_map, dict):
        quest_map = {"schema_version": 2, "quests": {}}
    quest_map.setdefault("schema_version", 2)
    quest_map.setdefault("quests", {})
    if not isinstance(quest_map["quests"], dict):
        quest_map["quests"] = {}

    enriched: List[Dict[str, Any]] = []
    for candidate in candidates:
        key = candidate["key"]
        existing_rel = quest_map["quests"].get(key)
        existing_text = ""
        if isinstance(existing_rel, str) and existing_rel:
            existing_path = REPO_ROOT / existing_rel
            if existing_path.exists():
                existing_text = read_text(existing_path)

        payload = build_payload(
            candidate,
            session,
            events_map,
            summary_text,
            note_lines,
            entity_index,
            existing_text,
        )
        payload["existing_rel"] = existing_rel if isinstance(existing_rel, str) else ""
        enriched.append(payload)

    selected, excluded_low = review_low_priority(
        enriched, include_low=args.include_low, exclude_low=args.exclude_low
    )

    written: List[str] = []
    updated: List[str] = []
    for payload in selected:
        key = payload["key"]
        path_rel = normalize_quest_rel(
            payload.get("existing_rel", ""), payload["status"], payload["title"]
        )
        path = REPO_ROOT / path_rel

        existing_text = read_text(path) if path.exists() else None
        output = merge_with_template(payload, existing_text)

        write_text(path, output, args.dry_run)
        quest_map["quests"][key] = str(path.relative_to(REPO_ROOT))

        if existing_text is None:
            written.append(str(path.relative_to(REPO_ROOT)))
        else:
            updated.append(str(path.relative_to(REPO_ROOT)))

    consolidation = {"clusters": 0, "remapped_keys": 0, "rule_remaps": 0, "deleted_files": []}
    if not args.no_consolidate:
        quest_map, consolidation = consolidate_quest_map(quest_map, args.dry_run)

    dump_data(QUEST_MAP_PATH, quest_map, args.dry_run)

    print(f"Session: {session.date} Session {session.session_number:03d}")
    print(f"Summary source: {session.summary_path.relative_to(REPO_ROOT)}")
    print(f"Note source: {session.source_note.relative_to(REPO_ROOT)}")
    print(f"Candidates: {len(candidates)}")
    print(f"Included: {len(selected)}")
    print(f"Excluded low priority: {len(excluded_low)}")
    print(f"Created: {len(written)}")
    print(f"Updated: {len(updated)}")

    if written:
        print("Created files:")
        for item in written:
            print(f"- {item}")
    if updated:
        print("Updated files:")
        for item in updated:
            print(f"- {item}")
    if excluded_low:
        print("Excluded low-priority quests:")
        for item in excluded_low:
            print(f"- {item['title']} ({item['key']})")
    if not args.no_consolidate:
        print("Consolidation:")
        print(f"- Merged clusters: {consolidation['clusters']}")
        print(f"- Remapped keys: {consolidation['remapped_keys']}")
        print(f"- Rule remaps: {consolidation['rule_remaps']}")
        print(f"- Backlink files updated: {consolidation['backlink_files_updated']}")
        print(f"- Backlink links updated: {consolidation['backlink_links_updated']}")
        print(f"- Deleted duplicate files: {len(consolidation['deleted_files'])}")

    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate/update quest files from session metadata")
    p.add_argument("--session", default="latest session")
    p.add_argument("--include-low", action="store_true", help="Include low-priority quest candidates")
    p.add_argument("--exclude-low", action="store_true", help="Exclude low-priority quest candidates")
    p.add_argument("--no-consolidate", action="store_true", help="Skip post-generation consolidation pass")
    p.add_argument("--consolidate-only", action="store_true", help="Run consolidation pass without session generation")
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.include_low and args.exclude_low:
        print("ERROR: choose only one of --include-low or --exclude-low", file=sys.stderr)
        return 2

    try:
        return run(args)
    except QuestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
