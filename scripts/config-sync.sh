#!/usr/bin/env bash
set -euo pipefail

# Orchestrator for shell configuration sync tasks
# Runs all executable scripts in the config-sync.d directory
# Call from zsh, nushell, powershell profiles to keep configs in sync
#
# Usage: config-sync.sh [--debug]

DEBUG=false
if [[ "${1:-}" == "--debug" ]]; then
  DEBUG=true
fi

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

# Run all executable scripts in config-sync.d in lexicographic order
for script in "$SYNC_DIR"/*; do
  if [[ -f "$script" ]] && [[ -x "$script" ]]; then
    debug_msg "Running $(basename "$script")"
    "$script" "$@" || true  # Continue on error to avoid breaking shell startup
  fi
done

debug_msg "Config sync completed"
