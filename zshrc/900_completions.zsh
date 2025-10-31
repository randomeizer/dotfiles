# Completion overrides and fixes
# This file loads last to ensure all aliases and integrations are defined first

# Fix completion for aliased commands
# When ls is aliased to eza, we want file completion not eza's flag completion
if (( $+commands[eza] )); then
    # Create wrapper completion that ignores the alias and completes files
    _ls_files() {
        _arguments '*:file or directory:_files'
    }
    
    compdef _ls_files ls l lt ltree
fi
