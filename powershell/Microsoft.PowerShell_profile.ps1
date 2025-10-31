# PowerShell profile to initialize Starship prompt
Invoke-Expression (&starship init powershell)

# Set up Homebrew environment
$(/opt/homebrew/bin/brew shellenv) | Invoke-Expression
