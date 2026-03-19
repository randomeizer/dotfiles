# External tool integrations

# If using Warp, bail out early to avoid conflicts
if [[ $TERM_PROGRAM == "WarpTerminal" ]]; then
    return
fi

# Sync shell-specific setup (symlinks, etc.) outside ~/.config
if [[ -x "$HOME/.config/scripts/config-sync.sh" ]]; then
    "$HOME/.config/scripts/config-sync.sh"
fi

# Starship prompt
if [[ -o interactive && -o zle ]]; then
    if command -v starship >/dev/null 2>&1; then
        eval "$(starship init zsh 2>/dev/null | sed '/^[[:space:]]*zle -N/d')"
    fi
fi
export STARSHIP_CONFIG="$HOME/.config/starship/starship.toml"

# Completions
source <(kubectl completion zsh) 2>/dev/null
complete -C '/usr/local/bin/aws_completer' aws 2>/dev/null

# Auto-suggestions (if available) — only in interactive shells
# Avoid running Homebrew commands in non-interactive or sandboxed shells
if [[ $- == *i* ]] && [[ -x /opt/homebrew/bin/brew ]] && [[ -f $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
    source "$(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh"
    bindkey '^w' autosuggest-execute
    bindkey '^e' autosuggest-accept
    bindkey '^u' autosuggest-toggle
fi

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
if command -v fzf >/dev/null 2>&1; then
    source <(fzf --zsh)
fi

# Directory-based environment loading (replaces oh-my-zsh autoenv)
if command -v direnv >/dev/null 2>&1; then
    eval "$(direnv hook zsh)"
fi

# Modern navigation tools
if command -v zoxide >/dev/null 2>&1; then
    eval "$(zoxide init zsh)"
fi

if command -v atuin >/dev/null 2>&1; then
    eval "$(atuin init zsh)"
fi
