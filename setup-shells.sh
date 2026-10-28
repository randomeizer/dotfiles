#!/usr/bin/env bash
set -euo pipefail

# Compatibility entry point; all bridge/conflict behavior lives in setup.sh.
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
exec bash "$repo_dir/setup.sh" --shells-only "$@"
