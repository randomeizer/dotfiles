# Completion overrides and fixes
# This file loads last to ensure all aliases and integrations are defined first

# Fix completion for aliased commands
# When ls is aliased to eza, ensure tab completion still works for files/directories
if (( $+commands[eza] )); then
    compdef _files ls l lt ltree
fi
