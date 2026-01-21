#!/usr/bin/env bash
set -euo pipefail

# Orchestrator for shell configuration sync tasks
# Runs all executable scripts in the config-sync.d directory
# Call from zsh, nushell, powershell profiles to keep configs in sync

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_DIR="$SCRIPT_DIR/config-sync.d"

if [[ ! -d "$SYNC_DIR" ]]; then
  exit 0
fi

# Run all executable scripts in config-sync.d in lexicographic order
for script in "$SYNC_DIR"/*; do
  if [[ -f "$script" ]] && [[ -x "$script" ]]; then
    "$script" || true  # Continue on error to avoid breaking shell startup
  fi
done
