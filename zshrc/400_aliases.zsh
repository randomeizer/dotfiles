# Directory navigation
alias ..="cd .."
alias ...="cd ../.."
alias ....="cd ../../.."
alias .....="cd ../../../.."
alias ......="cd ../../../../.."

# Modern tool replacements
alias cat=bat

# Eza aliases (keep ls as native ls to avoid completion conflicts)
if [[ "$TERM_PROGRAM" == "Apple_Terminal" ]]; then
  alias l="eza"
  alias ll="eza -l --git -a"
  alias lt="eza --tree --level=2 --long --git"
  alias ltree="eza --tree --level=2 --git"
else
  alias l="eza --icons"
  alias ll="eza -l --icons --git -a"
  alias lt="eza --tree --level=2 --long --icons --git"
  alias ltree="eza --tree --level=2 --icons --git"
fi

# Docker
alias dco="docker compose"
alias dps="docker ps"
alias dpa="docker ps -a"
alias dl="docker ps -l -q"
alias dx="docker exec -it"

# Utilities
alias cl='clear'

# Additional tool aliases (only for installed tools)
alias nm="nmap -sC -sV -oN nmap"
alias mat='osascript -e "tell application \"System Events\" to key code 126 using {command down}" && tmux neww "cmatrix"'

# K8S aliases (kubectl is installed)
alias k="kubectl"
alias ka="kubectl apply -f"
alias kg="kubectl get"
alias kd="kubectl describe"
alias kdel="kubectl delete"
alias kl="kubectl logs -f"
alias kgpo="kubectl get pod"
alias kgd="kubectl get deployments"
alias ke="kubectl exec -it"
alias kcns='kubectl config set-context --current --namespace'


# Navigation functions
cx() { cd "$@" && l; }
fcd() { cd "$(find . -type d -not -path '*/.*' | fzf)" && l; }
f() { echo "$(find . -type f -not -path '*/.*' | fzf)" | pbcopy }
fv() { nvim "$(find . -type f -not -path '*/.*' | fzf)" }
