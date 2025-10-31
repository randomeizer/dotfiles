# Completion overrides
# This file loads last to ensure all aliases and integrations are defined first

# Fix completion for eza aliases to complete files instead of eza flags
# eza's completion is auto-loaded by homebrew via site-functions
if (( $+commands[eza] )); then
    # Remove eza's completion function installed by homebrew
    unfunction _eza 2>/dev/null
    
    # Clear any existing completions
    compdef -d l ll lt ltree 2>/dev/null
    
    # Simple wrapper that completes files/directories
    _eza_files() {
        _files
    }
    
    # Apply to our eza aliases
    compdef _eza_files l ll lt ltree
fi
