#!/bin/bash

# Setup script for smart shell switching between zsh and nushell

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up smart shell switching..."

# Check if nushell is installed
if ! command -v nu &> /dev/null; then
    echo "❌ Nushell is not installed. Install it with:"
    echo "   brew install nushell"
    exit 1
else
    echo "✅ Nushell found at $(which nu)"
fi

# Check if starship is installed
if ! command -v starship &> /dev/null; then
    echo "❌ Starship is not installed. Install it with:"
    echo "   brew install starship"
    exit 1
else
    echo "✅ Starship found at $(which starship)"
fi

# Bridge the repo-managed zsh entrypoint into the shell-native location.
if [ -e "$HOME/.zshrc" ] && [ ! -L "$HOME/.zshrc" ]; then
    echo "⚠️  Skipping existing non-symlink: $HOME/.zshrc"
else
    ln -sfn "$HOME/.config/zshrc/.zshrc" "$HOME/.zshrc"
fi

# Bridge the repo-managed nushell config files into the shell-native location.
NUSHELL_CONFIG_DIR="$HOME/.config/nushell"
mkdir -p "$NUSHELL_CONFIG_DIR"
for nu_file in config.nu env.nu; do
    dest="$NUSHELL_CONFIG_DIR/$nu_file"
    src="$SCRIPT_DIR/nushell/$nu_file"
    if [ -e "$dest" ] && [ ! -L "$dest" ]; then
        echo "⚠️  Skipping existing non-symlink: $dest"
    else
        ln -sfn "$src" "$dest"
        echo "✅ Linked $dest"
    fi
done

echo "✅ Setup complete!"
echo ""
echo "Usage:"
echo "  From zsh: Run 'nu' (or 'nushell') to switch to nushell"
