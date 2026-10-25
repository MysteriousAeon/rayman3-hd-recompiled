param([int]$Seconds = 360, [string]$Run = 'verification', [string]$Schedule = 'config/m5/progression.txt', [switch]$Follow)
# M23 (D-053): superseded visible-window runner. It predates hidden mode: it shows a window, plays sound and
# lets the title's vibration reach a connected controller. Unattended runs use run_milestone6.ps1 only.
if (-not $env:R3HD_LEGACY_VISIBLE_RUN) { throw 'Superseded runner (D-053): use tools\run_milestone6.ps1; a person may set R3HD_LEGACY_VISIBLE_RUN=1 to reproduce an old visible run.' }
$ErrorActionPreference = 'Stop'
if ($Run -notmatch '^[A-Za-z0-9_-]+$') { throw 'Run must be a simple name' }
if ($Seconds -lt 1 -or $Seconds -gt 900) { throw 'Seconds must be 1..900' }
$repo = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $repo 'private/work/rex/out/build/win-amd64-release/r3hd.exe'
$work = Join-Path $repo "private/work/m5_runs/$Run"
if (Test-Path -LiteralPath $work) { throw "Run already exists: $work" }
New-Item -ItemType Directory -Path $work -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $repo $Schedule) -Destination (Join-Path $work 'schedule.txt')
$env:R3HD_INPUT_SCHEDULE = Join-Path $work 'schedule.txt'
$env:R3HD_M5_CAPTURE = '1'
# -Follow: the runtime keeps reading key events appended to the run's schedule.txt (closed-loop pilot).
if ($Follow) { $env:R3HD_INPUT_FOLLOW = '1' } else { Remove-Item Env:R3HD_INPUT_FOLLOW -ErrorAction SilentlyContinue }
$arguments = @("--game_data_root=$repo/private/extracted/5841123F", "--user_data_root=$work/user", "--cache_root=$repo/private/work/m2_cache", '--gpu_plugin=xenos', '--log_level=debug', '--log_flush_interval=1', "--log_file=$work/runtime.log", '--mnk_mode=true', "--dump_shaders=$work/shaders")
$started = Get-Date
# Visible window is needed for the normal presentation and keyboard listener path.
$p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $work -WindowStyle Normal -PassThru
$finished = $p.WaitForExit($Seconds * 1000)
if (-not $finished) { Stop-Process -Id $p.Id; $p.WaitForExit() }
$p.Refresh()
$result = [ordered]@{ executable = $exe; arguments = $arguments; working_directory = $work; seconds = $Seconds; started = $started.ToString('o'); ended = (Get-Date).ToString('o'); timeout = -not $finished; exit_code = $p.ExitCode; keyboard = $true; schedule = $Schedule; executable_sha256 = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower() }
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $work 'run.json')
Remove-Item Env:R3HD_INPUT_SCHEDULE, Env:R3HD_M5_CAPTURE
$result | ConvertTo-Json -Depth 4
