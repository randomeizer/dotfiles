#!/usr/bin/env bash
set -euo pipefail

script_path="${BASH_SOURCE[0]}"
while [[ -L "$script_path" ]]; do
  link_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
  link_target="$(readlink "$script_path")"
  if [[ "$link_target" == /* ]]; then script_path="$link_target"
  else script_path="$link_dir/$link_target"; fi
done
repo_dir="$(cd "$(dirname "$script_path")" && pwd -P)"

usage() {
  cat <<'EOF'
Usage: bootstrap.sh check [--home DIR] [--group shell|desktop|work]...
       bootstrap.sh install [--home DIR] [--install-packages] [--group shell|desktop|work]...

check inspects prerequisites and previews config installation without changes.
install deploys config; it installs packages only with --install-packages.
Selected groups are optional unless explicitly named. Core contains GNU Stow.
An alternate --home is for isolated installation; live config sync is skipped.
EOF
}

fail() { printf 'bootstrap: %s\n' "$*" >&2; exit 2; }
mode="${1:-}"
case "$mode" in check|install) shift ;; --help|-h) usage; exit 0 ;; *) usage >&2; exit 2 ;; esac
install_home="$HOME"
custom_home=false
install_packages=false
shell_group=false
desktop_group=false
work_group=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --home|--group)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail "$1 requires a value"
      if [[ "$1" == --home ]]; then
        install_home="$2"
        custom_home=true
      else
        case "$2" in shell) shell_group=true ;; desktop) desktop_group=true ;; work) work_group=true ;; *) fail "unknown group: $2" ;; esac
      fi
      shift 2 ;;
    --install-packages) install_packages=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done
[[ "$mode" == install || "$install_packages" == false ]] || fail '--install-packages requires install mode'
if [[ "$mode" == install && "$install_packages" == false ]] && \
   { [[ "$shell_group" == true ]] || [[ "$desktop_group" == true ]] || [[ "$work_group" == true ]]; }; then
  fail 'installing selected groups requires --install-packages'
fi

missing_required=0
tool_status() {
  local name="$1" required="$2"
  if command -v "$name" >/dev/null 2>&1; then
    printf '  found   %s\n' "$name"
  elif [[ "$required" == true ]]; then
    printf '  missing %s (selected)\n' "$name"
    missing_required=1
  else
    printf '  missing %s (optional)\n' "$name"
  fi
}
app_status() {
  local name="$1" app_path="$2" required="$3"
  if [[ -d "$app_path" ]]; then
    printf '  found   %s (%s)\n' "$name" "$app_path"
  elif [[ "$required" == true ]]; then
    printf '  missing %s at %s (selected)\n' "$name" "$app_path"
    missing_required=1
  else
    printf '  missing %s at %s (optional)\n' "$name" "$app_path"
  fi
}
check_skill_collisions() {
  local source="$1" target="$2" item name link
  for item in "$source"/*; do
    [[ -d "$item" ]] || continue
    name="${item##*/}"
    link="$target/$name"
    if [[ -L "$link" ]] && [[ "$(readlink "$link")" == "$item" ]]; then
      continue
    elif [[ -e "$link" || -L "$link" ]]; then
      printf '  sync collision: %s\n' "$link"
      missing_required=1
    fi
  done
}

if [[ "$mode" == check ]]; then
  printf 'Core prerequisites:\n'
  tool_status stow true
  tool_status brew false
  printf 'Shell tools:\n'
  for tool in nu starship carapace eza fzf zoxide atuin direnv tmux; do tool_status "$tool" "$shell_group"; done
  printf 'Desktop tools (standard /Applications location):\n'
  tool_status sketchybar "$desktop_group"
  app_status AeroSpace /Applications/AeroSpace.app "$desktop_group"
  app_status Hammerspoon /Applications/Hammerspoon.app "$desktop_group"
  printf 'Work tools:\n'
  for tool in kubectl az gh difft jless ast-grep just; do tool_status "$tool" "$work_group"; done
  if command -v stow >/dev/null 2>&1; then
    printf 'Configuration preview:\n'
    if preview="$(bash "$repo_dir/setup.sh" --dry-run --home "$install_home" 2>&1)"; then
      printf '  Stow preview passed.\n'
      while IFS= read -r line; do
        case "$line" in
          'Preserved existing path:'*|'Would link:'*|'Already linked:'*|'Would create config directory:'*)
            printf '  %s\n' "$line" ;;
        esac
      done <<< "$preview"
    else
      printf '%s\n' "$preview" >&2
      missing_required=1
    fi
  else
    printf '  Config preview skipped: install GNU Stow first.\n'
  fi
  if [[ "$custom_home" == false ]]; then
    printf 'Current-user sync collision preview:\n'
    sync_source="$HOME/.config/agents/skills"
    if [[ -d "$sync_source" ]]; then
      if command -v codex >/dev/null 2>&1; then check_skill_collisions "$sync_source" "$HOME/.codex/skills"; fi
      if command -v copilot >/dev/null 2>&1; then check_skill_collisions "$sync_source" "${COPILOT_HOME:-$HOME/.copilot}/skills"; fi
      check_skill_collisions "$sync_source" "$HOME/.agents/skills"
    else
      printf '  Skill collision preview deferred until shared skills are installed.\n'
    fi
    sync_azt="$HOME/.local/bin/azt"
    if [[ -L "$sync_azt" ]] && [[ "$(readlink "$sync_azt")" == "$HOME/.config/scripts/azt" ]]; then
      :
    elif [[ -e "$sync_azt" || -L "$sync_azt" ]]; then
      printf '  sync collision: %s\n' "$sync_azt"
      missing_required=1
    fi
  else
    printf 'Current-user sync collision preview skipped for alternate home.\n'
  fi
  exit "$missing_required"
fi

if [[ "$install_packages" == true ]]; then
  command -v brew >/dev/null 2>&1 || fail 'Homebrew is required for --install-packages; see https://brew.sh/'
  brew bundle install --no-upgrade --file="$repo_dir/bootstrap/Brewfile.core"
  [[ "$shell_group" == false ]] || brew bundle install --no-upgrade --file="$repo_dir/bootstrap/Brewfile.shell"
  [[ "$desktop_group" == false ]] || brew bundle install --no-upgrade --file="$repo_dir/bootstrap/Brewfile.desktop"
  [[ "$work_group" == false ]] || brew bundle install --no-upgrade --file="$repo_dir/bootstrap/Brewfile.work"
fi

command -v stow >/dev/null 2>&1 || fail 'GNU Stow is required; install it or use --install-packages'
bash "$repo_dir/setup.sh" --home "$install_home"
if [[ "$custom_home" == false ]]; then
  printf 'Running strict config sync for the current home.\n'
  bash "$repo_dir/scripts/config-sync.sh" --strict
else
  printf 'Skipped current-user config sync for alternate home: %s\n' "$install_home"
fi
