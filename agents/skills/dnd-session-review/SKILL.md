---
name: dnd-session-review
description: Review a D&D session through template preflight, interactive setup when needed, analysis, triage, summaries, quests, world updates, and final validation.
---

# DnD Session Review

## Shared Installation and Vault Scope

Read [vault layout and execution](../dnd-session-review/references/vault-layout.md) before running this skill in a new project.
Set `SKILLS_ROOT` to the absolute parent directory of the installed `dnd-session-*` skill folders, using the loaded skill's location. Keep the working directory in the target campaign vault; the installed skill directory is never the vault.

Primary orchestration entry point.

## Intent

`$dnd-session-review` should coordinate work by handing off to sub-skills, not by running stage logic directly in `dnd_session_review.py`.

## Sub-Skill Handoff Order

0. Run the template and player-character preflight below; use `$dnd-session-setup` if needed.
1. `$dnd-session-analyze` for the target session.
2. `$dnd-session-triage` gate check (must be clear before downstream).
3. `$dnd-session-summarise` to generate/update the session summary.
4. `$dnd-session-quests` to generate/update quest files.
5. `$dnd-session-world-update` to update world files.
6. Final validation pass (command below).

## Template and Player Preflight

Before analysis or any generated output, run:

```bash
python3 "$SKILLS_ROOT/dnd-session-setup/scripts/dnd_session_setup.py" check
```

- Exit 0: all seven templates are compatible and the player's character is configured. Continue without setup questions or template edits.
- Exit 1: read and invoke [dnd-session-setup](../dnd-session-setup/SKILL.md). It asks which character the user plays when that setting is missing, and creates missing templates from shared defaults while preserving existing files. Resolve reported incompatibilities before proceeding.
- Exit 2: inspect the reported environment/path/configuration error; do not treat it as permission to populate another vault.

After setup, rerun the check and continue with the originally requested session selector. Do not stop at setup when the user requested a complete session review. Existing templates remain authoritative; setup is not a request to replace or restyle them.

## Orchestration Rules

- If Stage 1 artifacts are missing, run `$dnd-session-analyze` first.
- If triage reports open/blocking items, stop and return to `$dnd-session-analyze` triage resolution.
- Preserve manual prose outside managed blocks in downstream skills.
- Before adding a quest, have `$dnd-session-quests` compare it with the existing quest set and use the established thread when the new evidence advances the same goal. If later evidence connects distinct quests, link them with Obsidian wikilinks while keeping their separate goals clear.
- Prefer category-by-category world updates when quality issues are suspected.

## Final Validation (Code)

After all sub-skills complete, run:

```bash
python3 "$SKILLS_ROOT/dnd-session-review/scripts/dnd_session_review_validate.py" --session "<selector>"
```

This validator checks:
- required Stage 1 + summary files exist
- world triage gate is clear (`open_count = 0`)
- world files for resolved entities exist
- placeholder leakage (`{{...}}`) in summary/quests/world files
- expected managed markers and `## 📝 Notes` structure in world files
- unescaped piped wikilinks inside Markdown table cells

Report path:
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/review-validation-report.md`

Strict mode (warnings fail):

```bash
python3 "$SKILLS_ROOT/dnd-session-review/scripts/dnd_session_review_validate.py" --session "<selector>" --strict
```

## Legacy Backend Note

`python3 "$SKILLS_ROOT/dnd-session-review/scripts/dnd_session_review.py" ...` remains a legacy/debug backend path. The parent skill should default to sub-skill handoff plus final validation.
