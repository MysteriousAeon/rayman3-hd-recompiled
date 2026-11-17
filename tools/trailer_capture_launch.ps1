param([string]$Level = '', [switch]$List, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$collection = Join-Path $repo 'private/trailer_20261101'
$experiment = Join-Path $repo 'private/work/trailer_capture'
$manifest = Get-Content -LiteralPath (Join-Path $collection 'manifest.json') -Raw | ConvertFrom-Json
$points = @($manifest.points)
if ($List) { $points | Select-Object level,capture,checkpoint; return }
if (-not $Level) {
    Write-Host 'EXPERIMENTAL CAPTURE RUNTIME — F5 toggles score/Combo; HUD starts visible.'
    Write-Host 'Automated verification: Moor_00. Human score-gate observation: wood_11. Other levels are unverified.'
    for ($i=0; $i -lt $points.Count; $i++) { Write-Host ('{0,2}. {1}' -f ($i+1), $points[$i].level) }
    $choice = Read-Host 'Choose a number'
    $number = 0
    if (-not [int]::TryParse($choice,[ref]$number) -or $number -lt 1 -or $number -gt $points.Count) { throw 'Invalid choice' }
    $Level = $points[$number-1].level
}
$point = @($points | Where-Object { $_.level -ceq $Level -and $_.capture -ceq 'A' })
if ($point.Count -ne 1) { throw 'Choose a listed level' }
$point = $point[0]
if (Get-Process r3hd -ErrorAction SilentlyContinue) { throw 'Exit the game before launching another capture' }
$bin = Join-Path $experiment 'build'
$expected = Get-Content -LiteralPath (Join-Path $experiment 'runtime_hashes.json') -Raw | ConvertFrom-Json
foreach ($prop in $expected.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $bin $prop.Name) -Algorithm SHA256).Hash -ne $prop.Value) { throw 'Experimental runtime hash mismatch' }
}
$exeText = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes((Join-Path $bin 'r3hd.exe')))
if (-not $exeText.Contains('R3HD_PRIVATE_CAPTURE_BUILD_V1')) { throw 'Not a capture-enabled runtime' }
$source = [IO.Path]::GetFullPath((Join-Path $collection $point.user))
if (-not $source.StartsWith(([IO.Path]::GetFullPath($collection) + [IO.Path]::DirectorySeparatorChar),[StringComparison]::OrdinalIgnoreCase)) { throw 'Archive outside collection' }
foreach ($file in $point.files) {
    $path = [IO.Path]::GetFullPath((Join-Path $source $file.path))
    if (-not $path.StartsWith(($source + [IO.Path]::DirectorySeparatorChar),[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid archive path' }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $file.sha256) { throw 'Archive hash mismatch' }
}
$session = Join-Path $experiment ('recordings/' + $Level + '_' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
if (Test-Path -LiteralPath $session) { throw 'Refusing an existing recording home' }
New-Item -ItemType Directory -Path $session | Out-Null
Copy-Item -LiteralPath (Join-Path $collection 'template/settings.json'),(Join-Path $collection 'template/r3hd_home.json') -Destination $session
Copy-Item -LiteralPath (Join-Path $collection 'template/mods') -Destination $session -Recurse
$user = Join-Path $session 'profiles/trailer/user'
New-Item -ItemType Directory -Path (Split-Path -Parent $user) | Out-Null
Copy-Item -LiteralPath $source -Destination $user -Recurse
[IO.File]::WriteAllText((Join-Path $session 'capture_session.json'), (@{kind='R3HD_PRIVATE_CAPTURE_BUILD_V1';level=$Level} | ConvertTo-Json))
[IO.File]::WriteAllText((Join-Path $session 'hud.control'), "0 show`n")
foreach ($mode in @('hide','show')) {
    $caption = if ($mode -eq 'hide') { 'Hide HUD.cmd' } else { 'Show HUD.cmd' }
    $line = '@echo off' + "`r`n" + 'python "' + (Join-Path $repo 'tools/trailer_capture_control.py') + '" "' + $session + '" ' + $mode + "`r`n"
    [IO.File]::WriteAllText((Join-Path $session $caption),$line)
}
Get-ChildItem Env:R3HD_* | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:R3HD_CAPTURE_CONTROL = Join-Path $session 'hud.control'
Write-Host "EXPERIMENTAL RUNTIME: $bin"
Write-Host "FRESH RECORDING HOME: $session"
Write-Host "Load $($point.slot) in game. HUD starts visible. Press F5 to hide or restore score/Combo."
Write-Host 'Pause, cinematics, focus loss and keyboard-owning overlays restore the HUD. Press F5 again after returning.'
Write-Host 'Hide HUD.cmd / Show HUD.cmd remain an optional fallback in this recording home.'
$arguments = @{UserHome=$session;PlayRoot=$session;Profile='trailer';BinDir=$bin;GameDir=(Join-Path $manifest.installation 'data/content')}
if ($DryRun) { $arguments.DryRun = $true }
& (Join-Path $manifest.installation 'app/tools/play.ps1') @arguments
