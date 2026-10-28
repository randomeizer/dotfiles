#!/usr/bin/env bash
set -euo pipefail

# Orchestrator for shell configuration sync tasks
# Runs all executable scripts in the config-sync.d directory
# Call from zsh, nushell, powershell profiles to keep configs in sync
#
# Usage: config-sync.sh [--debug] [--strict]

DEBUG=false
STRICT=false
for arg in "$@"; do
  case "$arg" in
    --debug) DEBUG=true ;;
    --strict) STRICT=true ;;
    *) printf 'config-sync: unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

debug_msg() {
  if [[ "$DEBUG" == true ]]; then
    echo "[config-sync] $*" >&2
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_DIR="$SCRIPT_DIR/config-sync.d"

debug_msg "Starting config sync from $SCRIPT_DIR"

if [[ ! -d "$SYNC_DIR" ]]; then
  debug_msg "No config-sync.d directory found"
  exit 0
fi

# Run all tasks even if one fails; shell startup remains usable.
failed_tasks=()
for script in "$SYNC_DIR"/*; do
  if [[ -f "$script" ]] && [[ -x "$script" ]]; then
    debug_msg "Running $(basename "$script")"
    if "$script" "$@"; then
      :
    else
      task_status=$?
      failed_tasks+=("$(basename "$script") (exit $task_status)")
    fi
  fi
done

if (( ${#failed_tasks[@]} )); then
  printf 'config-sync: failed tasks: %s\n' "${failed_tasks[*]}" >&2
  [[ "$STRICT" == false ]] || exit 1
else
  debug_msg "Config sync completed"
fi
