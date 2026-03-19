# Modular zsh configuration - auto-source all .zsh files in ~/.config/zshrc
ZSH_CONFIG_DIR="$HOME/.config/zshrc"

for config in "$ZSH_CONFIG_DIR"/*.zsh(N); do
  [ -r "$config" ] && source "$config"
done
