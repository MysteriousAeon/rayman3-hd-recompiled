#!/usr/bin/env python3
"""Exercise the real Play preflight function on synthetic homes; never starts the game."""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r'''
param([string]$Source, [string]$Fixture)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Source, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'play.ps1 has parse errors' }
$func = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-R3hdRuntimeProblems' }, $true)
if (@($func).Count -ne 1) { throw 'Expected one runtime preflight function' }
$calls = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'Get-R3hdRuntimeProblems' }, $true)
if (@($calls).Count -ne 1 -or $calls[0].Extent.Text -cne 'Get-R3hdRuntimeProblems $homeRoot $bin $env:SystemRoot') { throw 'Expected the actual Play preflight call' }
. ([scriptblock]::Create($func[0].Extent.Text))
$fixtureHome = Join-Path $Fixture 'home'
$localBin = Join-Path $fixtureHome 'bin'
$fakeSystem = Join-Path $Fixture 'system'
$systemBin = Join-Path $fakeSystem 'System32'
New-Item -ItemType Directory -Path $localBin, $systemBin -Force | Out-Null
$statePath = Join-Path $fixtureHome 'installer.json'
$dlls = @('MSVCP140.dll', 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll')
function Fill([string]$dir) { foreach ($name in $dlls) { [IO.File]::WriteAllText((Join-Path $dir $name), 'synthetic') } }
function Check([string]$name, [bool]$condition) { if (-not $condition) { throw "FAIL $name" }; Write-Output "PASS $name" }
Fill $localBin
[IO.File]::WriteAllText($statePath, '{"distribution":"portable"}')
$errorsFound = @(Get-R3hdRuntimeProblems $fixtureHome $localBin $fakeSystem)
Check 'portable succeeds with local DLLs and no system DLLs' ($errorsFound.Count -eq 0)
[IO.File]::WriteAllText($statePath, '{"distribution":"installed"}')
$errorsFound = @(Get-R3hdRuntimeProblems $fixtureHome $localBin $fakeSystem)
Check 'installed requires system DLLs even with local DLLs' ($errorsFound.Count -eq 3 -and $errorsFound[0] -match 'install the Microsoft')
Remove-Item -LiteralPath $statePath
$errorsFound = @(Get-R3hdRuntimeProblems $fixtureHome $localBin $fakeSystem)
Check 'home without state uses system DLLs' ($errorsFound.Count -eq 3)
Fill $systemBin
$errorsFound = @(Get-R3hdRuntimeProblems $fixtureHome $localBin $fakeSystem)
Check 'system DLLs satisfy installed preflight' ($errorsFound.Count -eq 0)
[IO.File]::WriteAllText($statePath, '{"distribution":"portable"}')
Remove-Item -LiteralPath (Join-Path $localBin 'VCRUNTIME140_1.dll')
$errorsFound = @(Get-R3hdRuntimeProblems $fixtureHome $localBin $fakeSystem)
Check 'portable missing local DLL is refused despite system DLLs' ($errorsFound.Count -eq 1 -and $errorsFound[0] -match 'extract a fresh ZIP' -and $errorsFound[0] -match 'VCRUNTIME140_1.dll')
[IO.File]::WriteAllText($statePath, '{invalid')
$refused = $false
try { Get-R3hdRuntimeProblems $fixtureHome $localBin $fakeSystem | Out-Null } catch { $refused = $_.Exception.Message -match 'Cannot read installation state' }
Check 'malformed state fails clearly' $refused
[IO.File]::WriteAllText($statePath, '[]')
$refused = $false
try { Get-R3hdRuntimeProblems $fixtureHome $localBin $fakeSystem | Out-Null } catch { $refused = $_.Exception.Message -match 'Cannot read installation state' }
Check 'non-object state fails clearly' $refused
Write-Output 'R3HD_PORTABLE_PREFLIGHT PASS checks=7 game_starts=0'
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'tools/play.ps1')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='r3hd_preflight_') as tmp:
        fixture = Path(tmp)
        runner = fixture / 'test.ps1'
        runner.write_text(SCRIPT, encoding='utf-8')
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(runner), str(args.source.resolve()), str(fixture)],
                                text=True, capture_output=True)
        print(result.stdout, end='')
        if result.stderr:
            print(result.stderr, end='')
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
