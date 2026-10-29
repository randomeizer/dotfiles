#!/usr/bin/env bash
# Catch drift between the creation and migration skill examples and references.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"
for skill in gwt-create-presenter gwt-migrate-presenter; do
  dir="agents/skills/$skill"
  for file in SKILL.md references/target-patterns.md assets/example/ExamplePresenter.java assets/example/ExampleView.java assets/example/ExampleViewImpl.java assets/example/ExampleModule.java assets/example/package-info.java; do
    if [[ ! -f "$dir/$file" ]]; then
      printf 'Missing skill resource: %s/%s\n' "$dir" "$file" >&2
      exit 1
    fi
  done
  if grep -En 'vims-app/src/|javax\.annotation\.Nonnull|@Nonnull' "$dir/SKILL.md" "$dir/references/target-patterns.md" "$dir/assets/example/"*.java; then
    printf 'Outdated path or nullness convention in %s\n' "$skill" >&2
    exit 1
  fi
  if ! grep -Eq 'public final class ExamplePresenter[[:space:]]*\{' "$dir/assets/example/ExamplePresenter.java"; then
    printf '%s example must show a plain final presenter\n' "$skill" >&2
    exit 1
  fi
done
if [[ ! -f agents/skills/gwt-migrate-presenter/references/stock-code-edit.md ]]; then
  printf 'Missing migration reference: stock-code-edit.md\n' >&2
  exit 1
fi
printf 'Presenter skill resources and conventions checked.\n'
