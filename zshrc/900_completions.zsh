# Completion overrides and fixes
# This file loads last to ensure all aliases and integrations are defined first

# Fix completion for aliased commands
# When ls is aliased to eza, we want file completion not eza's flag completion
# eza's completion is installed by homebrew and gets loaded by compinit
if (( $+commands[eza] )); then
    # Unset eza completion to prevent it from being used
    unfunction _eza 2>/dev/null
    
    # Remove completion definitions for these commands
    compdef -d ls l lt ltree eza 2>/dev/null
    
    # Create simple file completion wrapper
    _ls_files() {
        _files
    }
    
    # Apply to all our ls-related aliases
    compdef _ls_files ls l lt ltree
fi
