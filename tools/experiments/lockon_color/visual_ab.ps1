param(
  [Parameter(Mandatory=$true)][string]$Workspace,
  [ValidateSet('A','B')][string]$Mode='A',
  [switch]$Manual
)
# D-221 human out-of-range lock-on colour A/B. Without -Manual this is a dry run (no game). Only a person types PLAY.
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$work=(Resolve-Path -LiteralPath $Workspace).Path
$allowed=Join-Path $root 'private/work/lockon_color/acceptance'
if (-not $work.StartsWith($allowed+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Use a prepared private acceptance workspace' }
if (-not (Test-Path -LiteralPath (Join-Path $work 'acceptance.json'))) { throw 'Acceptance manifest missing' }
$manifest=Get-Content -Raw -LiteralPath (Join-Path $work 'acceptance.json') | ConvertFrom-Json
$build=Join-Path $root 'private/work/rex/out/build/win-amd64-release'
foreach ($name in 'r3hd.exe','rexruntime.dll') {
  $expected=$manifest.candidate_sha256.$name
  if (-not $expected -or (Get-FileHash -LiteralPath (Join-Path $build $name) -Algorithm SHA256).Hash -ine $expected) {
    throw "Candidate build changed ($name); prepare a fresh comparison workspace"
  }
}
$params=@{ Profile=$Mode; PlayRoot=(Join-Path $work 'play'); SettingsFile=(Join-Path $work ($Mode+'.json')); Mods='off' }
if (-not $Manual) { $params.DryRun=$true }
else {
  if (Get-Process r3hd -ErrorAction SilentlyContinue) { throw 'Exit the preceding game normally first' }
  Write-Host "Out-of-range lock-on comparison $Mode. A: original HD orange indicator. B: restored blue indicator. Other HD+ options match."
  Write-Host 'Continue the copied save, lock on to an enemy with the right trigger and back away until the dashed ring appears.'
  Write-Host 'Compare the dashed ring with the PC screenshot; the close-range ring and arrows should not change. Exit normally before the other case.'
  if ((Read-Host 'Type PLAY to start this human-controlled session') -cne 'PLAY') { return }
}
& (Join-Path $root 'tools/play.ps1') @params
if ($LASTEXITCODE) { exit $LASTEXITCODE }
