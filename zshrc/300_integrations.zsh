# External tool integrations

# If using Warp, bail out early to avoid conflicts
if [[ $TERM_PROGRAM == "WarpTerminal" ]]; then
    return
fi

export STARSHIP_CONFIG="$HOME/.config/starship/starship.toml"

# Shell hooks and keybindings only make sense in an interactive editor.
[[ -o interactive && -o zle ]] || return 0

# Cache generated integrations. Refresh when the executable or its path changes;
# write through a unique temporary file so concurrent shells never read partial output.
_dotfiles_cached_init() {
    setopt localoptions pipefail
    local tool="$1" executable cache_dir cache_file cache_header header temp
    (( $+commands[$tool] )) || return 0
    executable="$commands[$tool]"
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/dotfiles-shell/zsh"
    cache_file="$cache_dir/$tool.zsh"
    header="# dotfiles executable: $executable"
    cache_header=""
    # Do not replace an unrelated file or a symlink, including a dangling one.
    [[ ! -L "$cache_file" ]] || return 1
    [[ ! -e "$cache_file" || -f "$cache_file" ]] || return 1
    [[ ! -r "$cache_file" ]] || IFS= read -r cache_header < "$cache_file"
    [[ ! -e "$cache_file" || "$cache_header" == '# dotfiles executable: '* ]] || return 1
    if [[ ! -s "$cache_file" || "$cache_header" != "$header" || "$executable" -nt "$cache_file" ]]; then
        mkdir -p -- "$cache_dir" || return 1
        temp="$(mktemp "$cache_dir/.${tool}.XXXXXX")" || return 1
        if {
            print -r -- "$header"
            case "$tool" in
                starship) "$executable" init zsh | command sed '/^[[:space:]]*zle -N/d' ;;
                kubectl) "$executable" completion zsh ;;
                fzf) "$executable" --zsh ;;
                direnv) "$executable" hook zsh ;;
                zoxide|atuin) "$executable" init zsh ;;
            esac
        } > "$temp" 2>/dev/null && [[ "$(< "$temp")" != "$header" ]]; then
            mv -f -- "$temp" "$cache_file" || { rm -f -- "$temp"; return 1; }
        else
            rm -f -- "$temp"
            return 1
        fi
    fi
    source "$cache_file"
}

_dotfiles_cached_init starship || true
_dotfiles_cached_init kubectl || true
if (( $+commands[aws_completer] )); then
    complete -C "$commands[aws_completer]" aws 2>/dev/null
fi

# Auto-suggestions (if available) — only in interactive shells
# Avoid running Homebrew commands in non-interactive or sandboxed shells
for autosuggestions in /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh /usr/local/share/zsh-autosuggestions/zsh-autosuggestions.zsh; do
  if [[ -r "$autosuggestions" ]]; then
    source "$autosuggestions"
    bindkey '^w' autosuggest-execute
    bindkey '^e' autosuggest-accept
    bindkey '^u' autosuggest-toggle
    break
  fi
done
unset autosuggestions

# Emacs mode (default)
bindkey -e

# Word navigation keybindings (Alt+left/right)
bindkey '^[b' backward-word     # Alt+b
bindkey '^[f' forward-word      # Alt+f

# Custom word selection widgets
select-word-backward() {
  [[ -z $MARK ]] && MARK=$CURSOR
  zle backward-word
}

select-word-forward() {
  [[ -z $MARK ]] && MARK=$CURSOR
  zle forward-word
}

zle -N select-word-backward
zle -N select-word-forward

# Bind Shift+Alt+B and Shift+Alt+F for word selection
bindkey '^[B' select-word-backward
bindkey '^[F' select-word-forward

# FZF integration
# Set up fzf key bindings and fuzzy completion
# Provides: CTRL-T (files/dirs), CTRL-R (history), ALT-C (cd to dir)
_dotfiles_cached_init fzf || true

# Directory-based environment loading (replaces oh-my-zsh autoenv)
_dotfiles_cached_init direnv || true

# Modern navigation tools
_dotfiles_cached_init zoxide || true
_dotfiles_cached_init atuin || true
