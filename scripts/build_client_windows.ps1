$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

$dist = 'dist'
$kind = $env:RSD_KIND
if (-not $kind) { $kind = 'client' }
$name = $env:RSD_NAME
if (-not $name) { $name = 'remote-ssh-desktop' }
$spec = if ($kind -eq 'server') { 'build_server_windows.spec' } else { 'build_client_windows.spec' }
