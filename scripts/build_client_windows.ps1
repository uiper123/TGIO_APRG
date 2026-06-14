# Builds the Windows client binary using the PyInstaller spec file.
# The spec file is the single source of truth for hidden imports and build options.
#
# Environment variables:
#   PROJECT_ROOT - project root; defaults to current directory

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

$Root = if ($env:PROJECT_ROOT) { $env:PROJECT_ROOT } else { (Get-Location).Path }
$Dist = Join-Path $Root 'dist'
$Build = Join-Path $Root 'build'
$Spec = Join-Path $Root 'build_client_windows.spec'

if (Test-Path $Dist)  { Remove-Item -Recurse -Force $Dist  }
if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

Write-Host "Building $Spec -> $Dist"
$env:PROJECT_ROOT = $Root
pyinstaller --noconfirm --distpath $Dist --workpath $Build $Spec
Write-Host "build complete: $Dist"
