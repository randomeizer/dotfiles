# PowerShell profile to initialize Starship prompt
Invoke-Expression (&starship init powershell)

# Set up Homebrew environment — only in interactive PowerShell sessions
# Avoid running Homebrew (which uses `ps`) when running inside non-interactive
# sandboxes (like codex), which can cause "Operation not permitted" noise.
try {
	if ($Host -and $Host.UI -and $Host.UI.RawUI -ne $null) {
		if (Test-Path -Path '/opt/homebrew/bin/brew') {
			& '/opt/homebrew/bin/brew' shellenv | Invoke-Expression
		}
	}
} catch {
	# Be silent on errors to avoid polluting non-interactive stdout/stderr
}
