# G5-P4b (D-248, E-481): private test wrapper. Loads Invoke-R3hdModsPlan, Test-R3hdOrderlyExit and
# Complete-R3hdStructuralSession from tools\play.ps1 (PowerShell parser; the definitions run unchanged) and calls one
# of them, or inspects / terminates exactly one test-owned process. Prints one JSON object. Starts no game.
#   plan     -Python -ModsRoot -Cache -Game -Stamp [-DryRun]
#   orderly  -Session [-ExitCode]
#   complete -Python -ModsRoot -Stamp -MarkerFile -Session [-ExitCode]
#   owner    -ProcId                         (name, path, command line, creation time, parent chain)
#   kill     -ProcId -Created -Needle -ExePath (re-verifies all three, then Stop-Process on that one id only)
param(
    [Parameter(Mandatory = $true)][ValidateSet('plan', 'orderly', 'complete', 'owner', 'kill')][string]$Action,
    [string]$Python = '', [string]$ModsRoot = '', [string]$Cache = '', [string]$Game = '', [string]$Stamp = '',
    [string]$Session = '', [string]$ExitCode = '', [string]$MarkerFile = '', [switch]$DryRun,
    [int]$ProcId = 0, [string]$Created = '', [string]$Needle = '', [string]$ExePath = ''
)
$ErrorActionPreference = 'Stop'
$tools = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$playScript = Join-Path $tools 'play.ps1'
$wanted = @('Invoke-R3hdModsPlan', 'Test-R3hdOrderlyExit', 'Complete-R3hdStructuralSession')
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($playScript, [ref]$null, [ref]$errors)
if ($errors.Count) { throw "play.ps1 does not parse" }
$defs = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $wanted -contains $n.Name }, $true))
if ($defs.Count -ne $wanted.Count) { throw "play.ps1 lacks the structural-session functions" }
foreach ($d in $defs) { Invoke-Expression $d.Extent.Text }
$code = if ($ExitCode -eq '') { $null } else { [int64]$ExitCode }

function Get-Owner([int]$Id) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$Id" -ErrorAction SilentlyContinue
    if (-not $p) { return $null }
    $chain = @()
    $parentId = [int]$p.ParentProcessId
    for ($i = 0; $i -lt 3 -and $parentId; $i++) {
        $q = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction SilentlyContinue
        if (-not $q) { break }
        $chain += [ordered]@{ pid = [int]$q.ProcessId; name = $q.Name; created = $q.CreationDate.ToUniversalTime().ToString('o') }
        $parentId = [int]$q.ParentProcessId
    }
    return [ordered]@{ pid = [int]$p.ProcessId; name = $p.Name; path = $p.ExecutablePath; command_line = $p.CommandLine
                       created = $p.CreationDate.ToUniversalTime().ToString('o'); parents = $chain }
}

$out = switch ($Action) {
    'plan' { Invoke-R3hdModsPlan $Python $tools $ModsRoot $Cache $Game '' $Stamp $DryRun.IsPresent }
    'orderly' { Test-R3hdOrderlyExit $Session $code }
    'complete' {
        $marker = Get-Content -LiteralPath $MarkerFile -Raw | ConvertFrom-Json
        Complete-R3hdStructuralSession $Python $tools $ModsRoot $Stamp $marker $Session $code
    }
    'owner' { [ordered]@{ owner = (Get-Owner $ProcId) } }
    'kill' {
        $o = Get-Owner $ProcId
        if (-not $o) { [ordered]@{ killed = $false; reason = 'no such process' } }
        elseif ($o.created -ne $Created -or -not ($o.command_line -and $o.command_line.Contains($Needle)) -or
                $o.path -ne $ExePath) {
            [ordered]@{ killed = $false; reason = 'ownership does not match'; owner = $o }
        } else {
            Stop-Process -Id $ProcId -Force
            [ordered]@{ killed = $true; owner = $o; at = (Get-Date).ToUniversalTime().ToString('o') }
        }
    }
}
$out | ConvertTo-Json -Depth 8 -Compress
