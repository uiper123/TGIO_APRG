# Universal Windows installer for remote-ssh-desktop.
# Usage:
#   Server + Client: iwr -useb https://raw.githubusercontent.com/uiper123/TGIO_APRG/main/scripts/install.ps1 | iex
#   Client only:     iwr -useb https://...install.ps1 | iex; Install-RSD -Component client
#   Server only:     iwr -useb https://...install.ps1 | iex; Install-RSD -Component server
#
# Downloads binaries to %LOCALAPPDATA%\remote-ssh-desktop and adds to PATH.

$ErrorActionPreference = 'Stop'
$REPO = 'uiper123/TGIO_APRG'
$InstallDir = Join-Path $env:LOCALAPPDATA 'remote-ssh-desktop'

function Get-LatestTag {
    $resp = Invoke-RestMethod "https://api.github.com/repos/$REPO/releases/latest"
    return $resp.tag_name
}

function Add-ToPath($Dir) {
    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    if ($userPath -notlike "*$Dir*") {
        [Environment]::SetEnvironmentVariable('PATH', "$userPath;$Dir", 'User')
        $env:PATH += ";$Dir"
        Write-Host "Added to PATH: $Dir"
    }
}

function Install-RSD {
    param([string]$Component = 'both')

    $Tag = Get-LatestTag
    Write-Host "=== remote-ssh-desktop installer ==="
    Write-Host "Latest release: $Tag | Component: $Component"
    Write-Host ""

    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

    $arch = if ([System.Environment]::Is64BitOperatingSystem) { 'x86_64' } else { 'x86' }

    if ($Component -eq 'client' -or $Component -eq 'both') {
        $name = "remote-ssh-desktop-client-windows-$arch.exe"
        $url  = "https://github.com/$REPO/releases/download/$Tag/$name"
        $dest = Join-Path $InstallDir 'remote-ssh-desktop.exe'
        Write-Host "Downloading client: $name"
        Invoke-WebRequest $url -OutFile $dest
        Write-Host "Client installed: $dest"
        Write-Host ""
        Write-Host "Run: remote-ssh-desktop"
    }

    if ($Component -eq 'server' -or $Component -eq 'both') {
        $name = "remote-ssh-desktop-server-windows-$arch.exe"
        $url  = "https://github.com/$REPO/releases/download/$Tag/$name"
        $dest = Join-Path $InstallDir 'remote-ssh-desktop-server.exe'
        Write-Host "Downloading server: $name"
        try {
            Invoke-WebRequest $url -OutFile $dest
            Write-Host "Server installed: $dest"
        } catch {
            Write-Warning "Windows server binary not available in this release (expected for now)."
        }
        Write-Host ""
        Write-Host "NOTE: The server captures the current Windows desktop session."
        Write-Host "Make sure OpenSSH Server is enabled:"
        Write-Host "  Settings > Apps > Optional Features > OpenSSH Server"
    }

    Add-ToPath $InstallDir

    Write-Host ""
    Write-Host "=== Done! Open a new terminal to use the commands ==="
}

Install-RSD
