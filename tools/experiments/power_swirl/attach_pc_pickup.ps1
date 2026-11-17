# Attach only to the person's existing PC session. Never starts or controls a game.
[CmdletBinding()]
param(
    [string]$GameExe = 'D:\Games\Rayman 3\Rayman3.exe',
    [ValidateRange(0, 2147483647)][int]$GameProcessId = 0,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$observer = Join-Path $PSScriptRoot 'pc_event_watch.py'
$pythonExe = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
if ($CheckOnly) {
    & $pythonExe $observer --preflight --game $GameExe
    exit $LASTEXITCODE
}
$candidates = @(Get-Process -Name Rayman3 -ErrorAction SilentlyContinue)
if ($GameProcessId -eq 0) {
    if ($candidates.Count -ne 1) {
        throw 'Launch the PC game yourself. Exactly one Rayman3 process must already exist, or specify -GameProcessId.'
    }
    $GameProcessId = $candidates[0].Id
} elseif (@($candidates | Where-Object Id -eq $GameProcessId).Count -ne 1) {
    throw 'The specified existing process is not named Rayman3.'
}
$stamp = Get-Date -Format 'yyyyMMddTHHmmssfff'
$unique = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$outFile = Join-Path $repoRoot "private\work\power_swirl\pc_pickup\pickup_${stamp}_${unique}.jsonl"
Write-Host 'Waiting for READY. Then return to the game and collect ONE power-up without punching. Recording lasts 45 seconds.'
& $pythonExe $observer --pid $GameProcessId --game $GameExe --seconds 45 --out $outFile
exit $LASTEXITCODE
