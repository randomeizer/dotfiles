---
name: dnd-session-summarise
description: Generate a single session summary Markdown file from existing Stage 1 artifacts (`events.yaml` + `world.yaml`) and the source session note using `Templates/session-summary-template.md`.
---

# DnD Session Summarise

## Shared Installation and Vault Scope

Read [vault layout and execution](../dnd-session-review/references/vault-layout.md) before running this skill in a new project.
Set `SKILLS_ROOT` to the absolute parent directory of the installed `dnd-session-*` skill folders, using the loaded skill's location. Keep the working directory in the target campaign vault; the installed skill directory is never the vault.

Generate one session summary file only.

## Prerequisite

Stage 1 must already exist for the target session:

- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/events.yaml`
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/world.yaml`

If either file is missing, stop and report the missing prerequisite.

If the summary template or player-character setting is missing, use `$dnd-session-setup` to establish the player's character and create missing templates, then resume this stage.

## Inputs

- Stage 1 metadata in `events.yaml` and `world.yaml` (strong guidance)
- Session note text at `session.source_note` from `events.yaml` (canonical content)
- Template: `Templates/session-summary-template.md`
- Player character: `player_character` in `.dnd-meta/skill-config.json` (or a legacy non-Party `focus_character` setting)
- Span extractor helper: [span extractor](scripts/extract_note_span.py)

## Output

Create or overwrite exactly one file:

- `Sessions/Summaries/YYYY-MM-DD - Session NNN - Summary.md`

Use a three-digit session number (`NNN`, e.g. `001`, `012`, `137`).

Do not modify quests, world files, or session notes.

## Workflow

1. Resolve target session and open:
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/events.yaml`
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/world.yaml`
- `Templates/session-summary-template.md`
- `session.source_note` from `events.yaml`

2. Build evidence from metadata first, then confirm with note spans:
- Use `events[].start_index` and `events[].end_index` as span locators.
- Treat `events[].description`, `consequences`, `quest_hooks`, and `source_excerpt` as structured hints.
- Treat `world.yaml` resolved entities as canonical names/types for links.

3. Extract note spans with the helper script (do not use `dnd-session-review.py`):

```bash
python3 "$SKILLS_ROOT/dnd-session-summarise/scripts/extract_note_span.py" \
  --file "Sessions/Notes/2024-10-09 - Session 01.md" \
  --start "42:1" \
  --end "70:40"
```

- Default behavior clamps out-of-range columns to the nearest valid column for robustness against approximate metadata offsets.
- Add `--strict` if you need hard failure on out-of-range columns.

4. Populate `Templates/session-summary-template.md` with human-readable session content:
- Keep existing heading structure and emoji-prefixed `##` sections.
- Preserve the actual template's section order, including summary, session timeline, key events, Player Lens, and locations.
- Fill `{{player_character}}` and the summary's Player Character link from campaign settings, resolving known aliases to this vault's canonical title.
- Fill frontmatter from session metadata (`date`, `session_number`, `scope_used`).
- Keep chronology aligned to `events` order.
- Use `world.yaml` canonical titles for entity wikilinks.
- Do not include `Managed Updates` metadata sections in session summaries.

5. Link discipline:
- Auto-link only high-confidence resolved entities from `world.yaml`.
- If a mention is ambiguous or unresolved, leave plain text (no forced link).
- Use piped links when display text differs from canonical title.
- In Markdown tables, escape piped wikilinks as `[[Target\|Label]]`.

6. Final checks before write:
- Remove all template placeholders (`{{...}}`).
- Ensure summary is specific to the target session only.
- Ensure all claims are supported by metadata and/or note spans.
- Ensure filename uses `YYYY-MM-DD - Session NNN - Summary.md`.

## Content Rules

- Prioritize `Now` scope when present; use `Previously` only for continuity context.
- Metadata is strong guidance; source note text is final authority when conflicts appear.
- `## 🎯 Player Lens` interprets the configured player's character. Keep the character's identity in campaign settings and the summary's Player Character link, rather than embedding a name in the reusable heading. It adds interpretation grounded in evidence rather than repeating key events.
- In that lens section, emphasize:
  - Personal Stakes
  - Character Signals
  - Forward Pressure
- Keep uncertain facts in `## ❓ Open Questions & Uncertain Facts` with confidence labels.
