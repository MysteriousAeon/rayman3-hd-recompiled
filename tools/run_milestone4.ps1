param([int]$Seconds = 120, [string]$Run = 'verification', [switch]$Keyboard)
# M23 (D-053): superseded visible-window runner. It predates hidden mode: it shows a window, plays sound and
# lets the title's vibration reach a connected controller. Unattended runs use run_milestone6.ps1 only.
if (-not $env:R3HD_LEGACY_VISIBLE_RUN) { throw 'Superseded runner (D-053): use tools\run_milestone6.ps1; a person may set R3HD_LEGACY_VISIBLE_RUN=1 to reproduce an old visible run.' }
# Bounded visible run. Keyboard input uses the SDK's existing MnK driver.
$ErrorActionPreference = 'Stop'
if ($Run -notmatch '^[A-Za-z0-9_-]+$') { throw 'Run must be a simple name' }
if ($Seconds -lt 1 -or $Seconds -gt 600) { throw 'Seconds must be 1..600' }
$repo = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $repo 'private/work/rex/out/build/win-amd64-release/r3hd.exe'
$work = Join-Path $repo "private/work/m4_runs/$Run"
if (Test-Path -LiteralPath $work) { throw "Run already exists: $work" }
New-Item -ItemType Directory -Path $work -Force | Out-Null
$arguments = @(
  "--game_data_root=$repo/private/extracted/5841123F",
  "--user_data_root=$repo/private/work/m2_user",
  "--cache_root=$repo/private/work/m2_cache",
  '--gpu_plugin=xenos', '--log_level=debug', '--log_flush_interval=1',
  "--log_file=$work/runtime.log"
)
if ($Keyboard) { $arguments += '--mnk_mode=true' }
$started = Get-Date
# Visible foreground interaction is the purpose of this run.
$p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $work -WindowStyle Normal -PassThru
$finished = $p.WaitForExit($Seconds * 1000)
if (-not $finished) { Stop-Process -Id $p.Id; $p.WaitForExit() }
$p.Refresh()
$result = [ordered]@{
  executable = $exe; arguments = $arguments; working_directory = $work; window_style = 'Normal'
  seconds = $Seconds; started = $started.ToString('o'); ended = (Get-Date).ToString('o')
  timeout = -not $finished; exit_code = $p.ExitCode; keyboard = $Keyboard.IsPresent
  executable_sha256 = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $work 'run.json')
$result | ConvertTo-Json -Depth 4
