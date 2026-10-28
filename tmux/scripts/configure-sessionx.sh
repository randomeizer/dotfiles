#!/usr/bin/env bash
set -euo pipefail

# Follow Stow's links so this works with folded directories and individual files.
script_path="${BASH_SOURCE[0]}"
while [[ -L "$script_path" ]]; do
  link_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
  link_target="$(readlink "$script_path")"
  if [[ "$link_target" == /* ]]; then script_path="$link_target"
  else script_path="$link_dir/$link_target"; fi
done
script_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
repo_root="$(cd "$script_dir/../.." && pwd -P)"

tmux -S "$1" set-option -g @sessionx-custom-paths "$repo_root"
tmux -S "$1" set-option -g @sessionx-x-path "$repo_root"
