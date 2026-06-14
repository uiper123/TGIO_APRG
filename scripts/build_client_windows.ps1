# Builds the Windows client or server binary using PyInstaller.
# Environment variables:
#   RSD_KIND  - "client" (default) or "server"
#   RSD_NAME  - output name; defaults below
#   PROJECT_ROOT - project root; defaults to the current directory

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

$Kind = if ($env:RSD_KIND) { $env:RSD_KIND } else { 'client' }
if ($Kind -eq 'server') {
  $Name = if ($env:RSD_NAME) { $env:RSD_NAME } else { 'remote-ssh-desktop-server' }
  $Entry = 'remote_ssh_desktop/server/main.py'
  $Console = $true
} else {
  $Name = if ($env:RSD_NAME) { $env:RSD_NAME } else { 'remote-ssh-desktop' }
  $Entry = 'remote_ssh_desktop/client/main.py'
  $Console = $false
}

$Root = if ($env:PROJECT_ROOT) { $env:PROJECT_ROOT } else { (Get-Location).Path }
$Dist = Join-Path $Root 'dist'
$Build = Join-Path $Root 'build'

if (Test-Path $Dist)  { Remove-Item -Recurse -Force $Dist  }
if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

$pyi = @(
  '--noconfirm', '--clean', '--onefile',
  '--name', $Name,
  '--distpath', $Dist,
  '--workpath', $Build,
  '--specpath', $Root,
  '--collect-submodules', 'asyncssh',
  '--collect-submodules', 'PIL',
  '--collect-submodules', 'mss'
)
if ($Kind -eq 'client') {
  $pyi += @('--collect-submodules', 'remote_ssh_desktop', '--collect-submodules', 'PySide6', '--hidden-import', 'PIL.ImageQt')
} else {
  $pyi += @(
    '--collect-submodules', 'remote_ssh_desktop.server',
    '--collect-submodules', 'remote_ssh_desktop.common',
    '--collect-submodules', 'remote_ssh_desktop.crypto',
    '--hidden-import', 'remote_ssh_desktop.version',
    '--hidden-import', 'Xlib',
    '--hidden-import', 'Xlib.ext',
    '--hidden-import', 'Xlib.ext.xtest',
    '--hidden-import', 'Xlib.ext.xfixes',
    '--exclude-module', 'PySide6'
  )
}
if ($Console) { $pyi += '--console' } else { $pyi += '--windowed' }
$pyi += $Entry

Write-Host "Running: pyinstaller $($pyi -join ' ')"
pyinstaller @pyi
Write-Host "build complete: $Dist"
