---
name: dnd-session-quests
description: Generate or update quest files from Stage 1 metadata, the generated session summary, and source notes; classify priority/horizon and require explicit user confirmation for low-priority quests.
---

# DnD Session Quests

## Shared Installation and Vault Scope

Read [vault layout and execution](../dnd-session-review/references/vault-layout.md) before running this skill in a new project.
Set `SKILLS_ROOT` to the absolute parent directory of the installed `dnd-session-*` skill folders, using the loaded skill's location. Keep the working directory in the target campaign vault; the installed skill directory is never the vault.

Create/update quest threads for one session.

## Prerequisites

- Stage 1 exists for target session:
  - `.dnd-meta/sessions/YYYY-MM-DD-sNNN/events.yaml`
  - `.dnd-meta/sessions/YYYY-MM-DD-sNNN/world.yaml`
- Session summary exists:
  - `Sessions/Summaries/YYYY-MM-DD - Session NNN - Summary.md`

If prerequisites are missing, stop and report the exact missing file.

## Inputs

- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/events.yaml`
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/world.yaml`
- `Sessions/Summaries/YYYY-MM-DD - Session NNN - Summary.md`
- Session note at `session.source_note` from `events.yaml`
- Template: `Templates/quest-template.md`

## Output

- Create/update quest files in `Quests/Active/` (or `Quests/Completed/` for closed quests)
- Update `.dnd-meta/quest-map.yaml`

## Workflow

1. **Check the existing quest set first.** Read relevant files in `Quests/Active/` and `Quests/Completed/`, plus `.dnd-meta/quest-map.yaml`, before creating a quest. Compare each candidate's goal and new evidence with existing objectives. When the development advances an existing goal, update that quest instead of opening a parallel thread. Create a separate quest only when it has a distinct open goal that should be tracked independently.

   If it is unclear whether a candidate belongs in an existing quest or is a distinct goal, describe the likely match and intended distinction and ask the user before creating a parallel quest.

2. Scripted generation pass:

```bash
python3 "$SKILLS_ROOT/dnd-session-quests/scripts/dnd_session_quests.py" --session "<selector>"
```

Optional low-priority handling:

```bash
python3 "$SKILLS_ROOT/dnd-session-quests/scripts/dnd_session_quests.py" --session "<selector>" --include-low
python3 "$SKILLS_ROOT/dnd-session-quests/scripts/dnd_session_quests.py" --session "<selector>" --exclude-low
```

3. Model-driven review pass (required):
- Review generated/updated quest files against:
  - `events.yaml`
  - `world.yaml`
  - session summary
  - source note evidence spans
- Add/remove/tweak quests as needed:
  - fold developments into established quests when they advance the same goal
  - merge duplicate/near-duplicate quests when their goals are actually the same
  - keep distinct goals separate even when they share characters, clues, or a wider threat
  - when separate quests become connected, add Obsidian wikilinks between their quest pages and reflect the connection in relevant session summaries; do not merge them solely because a connection emerged
  - remove weak or purely tactical single-session items
  - adjust `status`, `priority`, `horizon`, objective wording, actions, and risks
  - improve `Latest Update`, evidence rows, and `🧵 Progress Log` entries so they reflect meaningful quest progress from each contributing summary
- If quest files are removed/renamed, keep `.dnd-meta/quest-map.yaml` in sync.

4. Consolidation pass (required):
- Run quest consolidation to collapse duplicate/near-duplicate threads and keep alias keys mapped to canonical files:

```bash
python3 "$SKILLS_ROOT/dnd-session-quests/scripts/dnd_session_quests.py" --consolidate-only
```

- Consolidation rules are stored in:
  - `.dnd-meta/quest-consolidation-rules.yaml`
- Keep this rules file updated when new duplicate patterns are found.

## Script Command

```bash
python3 "$SKILLS_ROOT/dnd-session-quests/scripts/dnd_session_quests.py" --session "<selector>"
```

Optional low-priority handling:

```bash
python3 "$SKILLS_ROOT/dnd-session-quests/scripts/dnd_session_quests.py" --session "<selector>" --include-low
python3 "$SKILLS_ROOT/dnd-session-quests/scripts/dnd_session_quests.py" --session "<selector>" --exclude-low
```

Consolidation only:

```bash
python3 "$SKILLS_ROOT/dnd-session-quests/scripts/dnd_session_quests.py" --consolidate-only
```

## Rules

- Analyze metadata first (`quest_candidates`, `quest_hooks`, event spans), then validate against summary + note evidence.
- Quests represent open goals/questions that are not completed within the same session.
- Assign `priority` (`high|medium|low`) and `horizon` (`short_term|long_term`) for each quest.
- Keep machine-friendly enum values in frontmatter (`status`, `priority`, `horizon`), but render human-readable wording in body sections (for example: `Not Started`, `Short-Term`).
- If any quest is `low` priority, get explicit user confirmation before including it.
  - In non-interactive mode, the script exits with guidance to rerun with `--include-low` or `--exclude-low`.
- Preserve manual prose outside managed blocks in existing quest files.
- Use canonical Obsidian wikilinks for resolved entities.
- In Markdown tables, escape piped wikilinks as `[[Target\|Label]]` (the link pipe must be escaped).
- `🧵 Progress Log` should not use generic metadata-update text. Each session entry should summarize a concrete development and/or evidence captured for the quest in that session.
