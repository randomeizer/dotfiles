---
name: dnd-session-summarize-quests
description: Generate or update session summaries and persistent quest threads from analyzed and triaged session data, including strict Obsidian linkification and allowed next-session Previously updates.
---

# DnD Session Summarize Quests

## Shared Installation and Vault Scope

Read [vault layout and execution](../dnd-session-review/references/vault-layout.md) before running this skill in a new project.
Set `SKILLS_ROOT` to the absolute parent directory of the installed `dnd-session-*` skill folders, using the loaded skill's location. Keep the working directory in the target campaign vault; the installed skill directory is never the vault.

Run Stage 2 output generation.

## Steps

1. Ensure analysis exists and blocking triage items are resolved.
2. Before generation, inspect relevant active and completed quest files and `.dnd-meta/quest-map.yaml`. Prefer adding new evidence and progress to an existing quest when it advances that quest's goal. If it is materially unclear whether a candidate is part of an existing quest or a separate goal, ask the user before creating a parallel quest.
3. Run:

```bash
python3 "$SKILLS_ROOT/dnd-session-review/scripts/dnd_session_review.py" summarize-quests --session "<selector>"
```

4. Review quest output against existing threads and session evidence. Remove duplicate threads, keep distinct goals separate, and add Obsidian wikilinks between separate quests when later evidence connects them. Link those threads from the session summary where relevant. Update `.dnd-meta/quest-map.yaml` when a quest is renamed, merged, or removed.
5. Confirm generated outputs:
- `Sessions/Summaries/YYYY-MM-DD - Session XX - Summary.md`
- `Quests/Active/*.md` (and `Quests/Completed/*.md` when applicable)
- `.dnd-meta/quest-map.yaml`
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/markdown-lint-report.md`

6. Keep generated sections aligned to normalized template headings (including emoji-prefixed `##` headings).

7. Confirm allowed note mutation behavior for next session `Previously` section only.
