param(
  [Parameter(Mandatory=$true)][string]$Workspace,
  [ValidateSet('A','B')][string]$Mode='A',
  [switch]$Manual
)
# D-219 human beam-colour A/B. Without -Manual this is a dry run (no game). Only a person types PLAY.
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$work=(Resolve-Path -LiteralPath $Workspace).Path
$allowed=Join-Path $root 'private/work/beam_color/acceptance'
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
  Write-Host "Beam color comparison $Mode. A: original HD orange beam and rings. B: restored purple beam and rings. Other HD+ options match."
  Write-Host 'Continue the copied save and walk to a power-up can before taking it.'
  Write-Host 'Compare the vertical beam and the rings above and below the can; the swirl around Rayman should not change. Exit normally before the other case.'
  if ((Read-Host 'Type PLAY to start this human-controlled session') -cne 'PLAY') { return }
}
& (Join-Path $root 'tools/play.ps1') @params
if ($LASTEXITCODE) { exit $LASTEXITCODE }
