# PowerShell profile to initialize Starship prompt
$env:STARSHIP_CONFIG = "$HOME/.config/starship/starship.toml"
Invoke-Expression (&starship init powershell)

# Sync shell-specific setup (symlinks, etc.) outside ~/.config
$syncHelper = "$HOME/.config/scripts/config-sync.sh"
if ((Test-Path $syncHelper) -and (Get-Command bash -ErrorAction SilentlyContinue)) {
	& bash $syncHelper
}

# Set up Homebrew environment — only in interactive PowerShell sessions
# Avoid running Homebrew (which uses `ps`) when running inside non-interactive
# sandboxes (like codex), which can cause "Operation not permitted" noise.
try {
	if ($Host -and $Host.UI -and $null -ne $Host.UI.RawUI) {
		if (Test-Path -Path '/opt/homebrew/bin/brew') {
			& '/opt/homebrew/bin/brew' shellenv | Invoke-Expression
		}
	}
} catch {
	# Be silent on errors to avoid polluting non-interactive stdout/stderr
}
