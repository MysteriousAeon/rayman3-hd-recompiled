param(
  [Parameter(Mandatory=$true)][string]$Workspace,
  [ValidateSet('A','B')][string]$Mode='A',
  [switch]$Manual
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$work=(Resolve-Path -LiteralPath $Workspace).Path
$allowed=Join-Path $root 'private/work/power_swirl/acceptance'
if (-not $work.StartsWith($allowed+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Use a prepared private acceptance workspace' }
if (-not (Test-Path -LiteralPath (Join-Path $work 'acceptance.json'))) { throw 'Acceptance manifest missing' }
$manifest=Get-Content -Raw -LiteralPath (Join-Path $work 'acceptance.json') | ConvertFrom-Json
$exe=Join-Path $root 'private/work/rex/out/build/win-amd64-release/r3hd.exe'
if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ine $manifest.candidate_executable_sha256) { throw 'Candidate build changed; prepare a fresh comparison workspace' }
$params=@{ Profile=$Mode; PlayRoot=(Join-Path $work 'play'); SettingsFile=(Join-Path $work ($Mode+'.json')); Mods='off' }
if (-not $Manual) { $params.DryRun=$true }
else {
  if (Get-Process r3hd -ErrorAction SilentlyContinue) { throw 'Exit the preceding game normally first' }
  Write-Host "Swirl comparison $Mode. A: original HD swirl behavior. B: restored swirl. Other HD+ options match."
  Write-Host 'Continue the copied save. Collect a power-up, move away from the can, and watch expiration.'
  Write-Host 'Compare placement, color, animation/fade and unrelated effects. Exit normally before the other case.'
  if ((Read-Host 'Type PLAY to start this human-controlled session') -cne 'PLAY') { return }
}
& (Join-Path $root 'tools/play.ps1') @params
if ($LASTEXITCODE) { exit $LASTEXITCODE }
