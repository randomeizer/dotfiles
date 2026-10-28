#!/usr/bin/env bash
set -euo pipefail

# Resolve the checkout even when this entry point was invoked through a symlink.
script_path="${BASH_SOURCE[0]}"
while [[ -L "$script_path" ]]; do
  script_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
  link_target="$(readlink "$script_path")"
  if [[ "$link_target" == /* ]]; then
    script_path="$link_target"
  else
    script_path="$script_dir/$link_target"
  fi
done
repo_dir="$(cd "$(dirname "$script_path")" && pwd -P)"

usage() {
  cat <<'EOF'
Usage: setup.sh [--dry-run] [--home DIR] [--target DIR] [--with-ssh]
       setup.sh --shells-only [--dry-run] [--home DIR] [--target DIR]

Install allowlisted configuration directories with GNU Stow, then create native
Zsh and Hammerspoon bridges. Preserve existing files and unrelated symlinks.

  --dry-run      Show the plan without changing the home or target directory.
  --home DIR     Home directory for native bridges (default: $HOME).
  --target DIR   Config directory (default: <home>/.config).
  --with-ssh     Also link <home>/.ssh/config, if absent. Review SSH settings first.
  --shells-only  Only create the Zsh bridge for an already installed config tree.
  --help         Show this help.
EOF
}

fail() { printf 'setup: %s\n' "$*" >&2; exit 1; }
absolute_path() {
  if [[ "$1" == /* ]]; then printf '%s\n' "$1";
  else printf '%s/%s\n' "$PWD" "$1"; fi
}

dry_run=false
shells_only=false
with_ssh=false
install_home="$HOME"
config_dir=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) dry_run=true; shift ;;
    --shells-only) shells_only=true; shift ;;
    --with-ssh) with_ssh=true; shift ;;
    --home|--target)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail "$1 requires a directory"
      if [[ "$1" == --home ]]; then install_home="$2"; else config_dir="$2"; fi
      shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown argument: $1 (see --help)" ;;
  esac
done
install_home="$(absolute_path "$install_home")"
config_dir="$(absolute_path "${config_dir:-$install_home/.config}")"

# Existing user content wins. Never replace even a dangling unrelated symlink.
bridge() {
  local source="$1" target="$2"
  if [[ -L "$target" ]] && { [[ "$(readlink "$target")" == "$source" ]] || [[ "$target" -ef "$source" ]]; }; then
    printf 'Already linked: %s\n' "$target"
  elif [[ -e "$target" || -L "$target" ]]; then
    printf 'Preserved existing path: %s (wanted %s)\n' "$target" "$source" >&2
  elif [[ "$dry_run" == true ]]; then
    printf 'Would link: %s -> %s\n' "$target" "$source"
  else
    mkdir -p "$(dirname "$target")"
    ln -s "$source" "$target"
    printf 'Linked: %s -> %s\n' "$target" "$source"
  fi
}

if [[ "$shells_only" == false ]]; then
  command -v stow >/dev/null 2>&1 || fail 'GNU Stow is required'
  if [[ -e "$config_dir" && ! -d "$config_dir" ]]; then
    fail "config target is not a directory: $config_dir"
  fi
  if [[ -L "$config_dir" && ! -d "$config_dir" ]]; then
    fail "config target is a dangling symlink: $config_dir"
  fi
  if [[ "$dry_run" == false ]]; then
    mkdir -p "$config_dir"
  fi
  printf '%s allowlisted configuration: %s -> %s\n' \
    "$([[ "$dry_run" == true ]] && printf 'Would install' || printf 'Installing')" "$repo_dir" "$config_dir"
  stow_target="$config_dir"
  if [[ ! -d "$config_dir" ]]; then
    printf 'Would create config directory: %s\n' "$config_dir"
    # Stow needs an existing target even when simulating. Validate the fresh
    # install plan without creating the requested home or config directory.
    preview_dir="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-stow.XXXXXX")"
    trap 'rmdir "$preview_dir"' EXIT
    stow_target="$preview_dir"
  fi
  # The checkout's .stowrc and .stow-local-ignore are used from any caller cwd.
  # One Stow transaction detects all config conflicts before making links.
  stow_args=(--dir "$repo_dir" --target "$stow_target" --no-folding)
  [[ "$dry_run" == false ]] || stow_args+=(--simulate --verbose)
  (cd "$repo_dir" && stow "${stow_args[@]}" .)
elif [[ ! -r "$config_dir/zshrc/.zshrc" ]]; then
  fail "install the config tree before creating the Zsh bridge: $config_dir/zshrc/.zshrc"
fi

bridge "$config_dir/zshrc/.zshrc" "$install_home/.zshrc"
if [[ "$shells_only" == false ]]; then
  bridge "$config_dir/hammerspoon" "$install_home/.hammerspoon"
  if [[ "$with_ssh" == true ]]; then
    bridge "$config_dir/ssh/ssh-config" "$install_home/.ssh/config"
  fi
fi
