param([int]$Seconds = 60, [string]$Run = 'run1', [string]$WindowStyle = 'Normal')
# M23 (D-053): superseded visible-window runner. It predates hidden mode: it shows a window, plays sound and
# lets the title's vibration reach a connected controller. Unattended runs use run_milestone6.ps1 only.
if (-not $env:R3HD_LEGACY_VISIBLE_RUN) { throw 'Superseded runner (D-053): use tools\run_milestone6.ps1; a person may set R3HD_LEGACY_VISIBLE_RUN=1 to reproduce an old visible run.' }
# Bounded Milestone 3 run. The window is shown by default so the host swap chain really
# presents; the timeout is an experiment endpoint, never evidence of a successful boot.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $repo 'private/work/rex/out/build/win-amd64-release/r3hd.exe'
$work = Join-Path $repo "private/work/m3_runs/$Run"
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Force -Path $work | Out-Null
$arguments = @(
  "--game_data_root=$repo/private/extracted/5841123F",
  "--user_data_root=$repo/private/work/m2_user",
  "--cache_root=$repo/private/work/m2_cache",
  '--gpu_plugin=xenos', '--log_level=debug', '--log_flush_interval=1',
  "--log_file=$work/runtime.log"
)
$started = Get-Date
$p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $work -WindowStyle $WindowStyle -PassThru
$finished = $p.WaitForExit($Seconds * 1000)
if (-not $finished) { Stop-Process -Id $p.Id; $p.WaitForExit() }
$p.Refresh()
$result = [ordered]@{
  executable = $exe; arguments = $arguments; working_directory = $work; window_style = $WindowStyle
  seconds = $Seconds; started = $started.ToString('o'); ended = (Get-Date).ToString('o')
  timeout = -not $finished; exit_code = $p.ExitCode
  executable_sha256 = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $work 'run.json')
$result | ConvertTo-Json -Depth 4
