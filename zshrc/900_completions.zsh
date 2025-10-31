# Completion overrides
# This file loads last to ensure all aliases and integrations are defined first

# Fix completion for eza aliases to complete files instead of eza flags
if (( $+commands[eza] )); then
    # Simple wrapper that completes files/directories
    _eza_files() {
        _files
    }
    
    # Apply to our eza aliases (but not eza itself, in case we use it directly)
    compdef _eza_files l ll lt ltree
fi
