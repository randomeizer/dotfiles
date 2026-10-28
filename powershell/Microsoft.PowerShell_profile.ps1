# PowerShell profile to initialize Starship prompt
$env:STARSHIP_CONFIG = "$HOME/.config/starship/starship.toml"
$dotfilesProcessArgs = [Environment]::GetCommandLineArgs()
$dotfilesNonInteractive = @($dotfilesProcessArgs | Where-Object { $_ -match '^-(NonInteractive|NonI)$' }).Count -gt 0
$dotfilesOneShot = @($dotfilesProcessArgs | Where-Object { $_ -match '^-(Command|c|File|f|EncodedCommand|e)$' }).Count -gt 0
$dotfilesNoExit = @($dotfilesProcessArgs | Where-Object { $_ -match '^-NoExit$' }).Count -gt 0
$dotfilesInteractive = try { -not [Console]::IsInputRedirected -and -not $dotfilesNonInteractive -and (-not $dotfilesOneShot -or $dotfilesNoExit) } catch { $false }


# Set up Homebrew environment — only in interactive PowerShell sessions
# Avoid running Homebrew (which uses `ps`) when running inside non-interactive
# sandboxes (like codex), which can cause "Operation not permitted" noise.
try {
	if ($dotfilesInteractive -and $Host -and $Host.UI -and $null -ne $Host.UI.RawUI) {
		if (Test-Path -Path '/opt/homebrew/bin/brew') {
			& '/opt/homebrew/bin/brew' shellenv | Invoke-Expression
		}
	}
} catch {
	# Be silent on errors to avoid polluting non-interactive stdout/stderr
}

if ($dotfilesInteractive) {
	$dotfilesStarship = Get-Command starship -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
	if ($null -ne $dotfilesStarship) {
		$dotfilesCacheRoot = if ($env:XDG_CACHE_HOME) { $env:XDG_CACHE_HOME } else { Join-Path $HOME '.cache' }
		$dotfilesCacheDir = Join-Path $dotfilesCacheRoot 'dotfiles-shell/powershell'
		$dotfilesCacheFile = Join-Path $dotfilesCacheDir 'starship.ps1'
		$dotfilesHeader = "# dotfiles executable: $($dotfilesStarship.Source)"
		$dotfilesValid = $false
		try {
			$dotfilesCacheItem = Get-Item -LiteralPath $dotfilesCacheFile -Force -ErrorAction SilentlyContinue
			if ($null -ne $dotfilesCacheItem) {
				if ($dotfilesCacheItem.LinkType -or $dotfilesCacheItem.PSIsContainer) { throw 'Cache path is not a managed file' }
				$dotfilesReader = [IO.File]::OpenText($dotfilesCacheFile)
				try { $dotfilesCachedHeader = $dotfilesReader.ReadLine() } finally { $dotfilesReader.Dispose() }
				if ($dotfilesCachedHeader -notlike '# dotfiles executable: *') { throw 'Cache file is not managed' }
				$dotfilesValid = $dotfilesCachedHeader -eq $dotfilesHeader -and (Get-Item -LiteralPath $dotfilesStarship.Source).LastWriteTimeUtc -le (Get-Item -LiteralPath $dotfilesCacheFile).LastWriteTimeUtc
			}
			if (-not $dotfilesValid) {
				$dotfilesGenerated = & $dotfilesStarship.Source init powershell --print-full-init 2>$null
				if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($dotfilesGenerated -join "`n"))) {
					[IO.Directory]::CreateDirectory($dotfilesCacheDir) | Out-Null
					$dotfilesTemp = Join-Path $dotfilesCacheDir ([IO.Path]::GetRandomFileName())
					try {
						[IO.File]::WriteAllText($dotfilesTemp, "$dotfilesHeader`n$($dotfilesGenerated -join "`n")`n", [Text.UTF8Encoding]::new($false))
						[IO.File]::Move($dotfilesTemp, $dotfilesCacheFile, $true)
						$dotfilesValid = $true
					} finally {
						if (Test-Path -LiteralPath $dotfilesTemp) { Remove-Item -LiteralPath $dotfilesTemp -Force }
					}
				}
			}
			if ($dotfilesValid) { . $dotfilesCacheFile }
		} catch {
			# Optional prompt setup must not prevent the shell from starting.
		}
	}
}
