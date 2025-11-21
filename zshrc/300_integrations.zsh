# External tool integrations

# If using Warp, bail out early to avoid conflicts
if [[ $TERM_PROGRAM == "WarpTerminal" ]]; then
    return
fi

# Starship prompt
export STARSHIP_CONFIG="$HOME/.config/starship/starship.toml"

eval "$(starship init zsh)"

# Completions
source <(kubectl completion zsh) 2>/dev/null
complete -C '/usr/local/bin/aws_completer' aws 2>/dev/null

# Auto-suggestions (if available)
if [[ -f $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
    source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh
    bindkey '^w' autosuggest-execute
    bindkey '^e' autosuggest-accept
    bindkey '^u' autosuggest-toggle
fi

# Key bindings
# Ensure emacs mode (not vi mode)
bindkey -e

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