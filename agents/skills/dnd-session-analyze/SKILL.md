---
name: dnd-session-analyze
description: Agent-authored Stage 1 analysis. Read a session note in two passes and produce strict-schema events.yaml + world.yaml, then lint and resolve triage interactively.
---

# DnD Session Analyze

## Shared Installation and Vault Scope

Read [vault layout and execution](../dnd-session-review/references/vault-layout.md) before running this skill in a new project.
Set `SKILLS_ROOT` to the absolute parent directory of the installed `dnd-session-*` skill folders, using the loaded skill's location. Keep the working directory in the target campaign vault; the installed skill directory is never the vault.

Run Stage 1 analysis for the target vault with agent-authored artifacts.

## Canonical Outputs

- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/events.yaml`
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/world.yaml`
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/events-lint-report.md`
- `.dnd-meta/sessions/YYYY-MM-DD-sNNN/world-lint-report.md`

## Scripts

Lint events output:

```bash
python3 "$SKILLS_ROOT/dnd-session-analyze/scripts/lint_events_yaml.py" --session "<selector>"
```

Lint world output:

```bash
python3 "$SKILLS_ROOT/dnd-session-analyze/scripts/lint_world_yaml.py" --session "<selector>"
```

Both scripts also accept explicit file paths:

```bash
python3 "$SKILLS_ROOT/dnd-session-analyze/scripts/lint_events_yaml.py" --file "<path-to-events.yaml>"
python3 "$SKILLS_ROOT/dnd-session-analyze/scripts/lint_world_yaml.py" --file "<path-to-world.yaml>" --events-file "<path-to-events.yaml>"
```

## Required Workflow

1. Resolve target session from user input (`Session XX` or `latest session`).
2. Pass 1 (events): Read `Sessions/Notes/...` and treat `Now` as primary scope; `Previously` is context only.
3. Author `events.yaml` from [events schema example](resources/events.yaml) schema.
4. Run `lint_events_yaml.py`; fix until zero errors.
5. Pass 2 (world): Re-read the same session note independently.
6. Author `world.yaml` from [world schema example](resources/world.yaml) schema, referencing `events[].id`.
7. Run `lint_world_yaml.py`; fix until zero errors.

## Interactive Triage Loop (Required)

After world lint passes, inspect `world.yaml` entities with:
- `resolution_status: triage_required`
- `resolution_status: unresolved`

Work each item with the user one-by-one. For each item:
1. Present mention, canonical candidate, entity type, confidence, event IDs, and evidence excerpt.
2. Ask for one explicit decision:
- link existing canonical
- create new canonical
- mark ignored
3. Apply the decision immediately to `world.yaml`.
4. Persist memory updates:
- update `.dnd-meta/entity-resolver.yaml` aliases/canonical entries
- append decision record to `.dnd-meta/triage-decisions.yaml`
5. Recompute `triage_summary` in `world.yaml`.
6. Re-run `lint_world_yaml.py`.

Repeat until zero `triage_required`/`unresolved` items remain.

## Completion Report

At completion, report:
- paths to `events.yaml` and `world.yaml`
- lint report paths and status
- triage item counts (`open`, `blocking`, `resolved`)
