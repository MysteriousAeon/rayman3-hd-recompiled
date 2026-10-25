# M16 (D-045) regression for tools\play_savekeeper.ps1 on a synthetic profile in a temporary directory.
# No game data, no game process. Prints M16_SAVEKEEPER_TEST PASS|FAIL checks=N failures=M; exit code 0 / 1.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'play_savekeeper.ps1')
$script:checks = 0
$script:failures = 0
function Check([bool]$ok, [string]$what) {
    $script:checks++
    if (-not $ok) { $script:failures++; Write-Host "FAIL: $what" }
}
function New-Save([string]$Path, [string]$Level) {
    $bytes = New-Object byte[] 510
    [Text.Encoding]::ASCII.GetBytes('AAAA').CopyTo($bytes, 0)
    [Text.Encoding]::ASCII.GetBytes($Level).CopyTo($bytes, 152)
    New-Item -ItemType Directory -Path (Split-Path $Path) -Force | Out-Null
    [IO.File]::WriteAllBytes($Path, $bytes)
}
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('m16_savekeeper_' + [Guid]::NewGuid().ToString('N'))
try {
    $user = Join-Path $tmp 'profile\user'
    $history = Join-Path $tmp 'history'
    $slot = Join-Path $user 'B13EBABEBABEBABE\5841123F\00000001\RAY1\RAY1'

    $keeper = New-SaveKeeper $user $history
    Check (-not (Update-SaveKeeper $keeper 'before' -Final)) 'missing profile: no snapshot'
    Check (-not (Test-Path $history)) 'missing profile: no history directory'

    New-Save $slot 'intro_15'
    New-Item -ItemType Directory -Path (Join-Path $user 'achievements') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $user 'achievements\5841123F.toml') -Value '# test'
    Check (Update-SaveKeeper $keeper 'before' -Final) 'initial snapshot taken'
    Check ($keeper.Index -eq 1) 'index 1 after the initial snapshot'
    Check (Test-Path (Join-Path $history '000\user\B13EBABEBABEBABE\5841123F\00000001\RAY1\RAY1')) 'slot copied'
    Check (Test-Path (Join-Path $history '000\user\achievements\5841123F.toml')) 'achievements file copied'
    $meta = Get-Content -Raw (Join-Path $history '000\snapshot.json') | ConvertFrom-Json
    Check ($meta.reason -eq 'before') 'reason recorded'
    Check (@($meta.slots).Count -eq 1 -and $meta.slots[0].slot -eq 'RAY1' -and $meta.slots[0].level -eq 'intro_15') 'slot and level recorded'

    Check (-not (Update-SaveKeeper $keeper)) 'unchanged profile: no snapshot'
    Check (-not (Update-SaveKeeper $keeper)) 'unchanged profile: still none'
    Check ($keeper.Index -eq 1) 'index unchanged'

    Start-Sleep -Milliseconds 30
    New-Save $slot 'intro_17'
    Check (-not (Update-SaveKeeper $keeper)) 'changed profile: first poll only marks it pending'
    Check ($keeper.Index -eq 1) 'no copy on the first poll after a change'
    Check (Update-SaveKeeper $keeper) 'stable on the second poll: snapshot'
    $meta = Get-Content -Raw (Join-Path $history '001\snapshot.json') | ConvertFrom-Json
    Check ($meta.slots[0].level -eq 'intro_17') 'new level recorded'
    Check ($meta.reason -eq 'changed') 'default reason'

    Start-Sleep -Milliseconds 30
    New-Save $slot 'intro_20'
    Check (-not (Update-SaveKeeper $keeper)) 'pending again'
    Start-Sleep -Milliseconds 30
    New-Save $slot 'menu_00'
    Check (-not (Update-SaveKeeper $keeper)) 'changed again while pending: still not copied'
    Check (Update-SaveKeeper $keeper) 'copied once stable'
    $meta = Get-Content -Raw (Join-Path $history '002\snapshot.json') | ConvertFrom-Json
    Check ($meta.slots[0].level -eq 'menu_00') 'the stable state is what was copied'

    Start-Sleep -Milliseconds 30
    New-Save $slot 'wood_11'
    Check (Update-SaveKeeper $keeper 'after' -Final) 'final poll copies at once'
    Check (-not (Update-SaveKeeper $keeper 'after' -Final)) 'final poll on an unchanged profile copies nothing'
    Check ($keeper.Index -eq 4) 'four snapshots in total'

    # the source profile is only read
    $bytes = [IO.File]::ReadAllBytes($slot)
    Check ([Text.Encoding]::ASCII.GetString($bytes, 152, 7) -eq 'wood_11') 'source save untouched'
    Check (@(Get-ChildItem -LiteralPath $user -Recurse -File).Count -eq 2) 'no file added to the source profile'
    # earlier snapshots are not rewritten
    $old = [IO.File]::ReadAllBytes((Join-Path $history '000\user\B13EBABEBABEBABE\5841123F\00000001\RAY1\RAY1'))
    Check ([Text.Encoding]::ASCII.GetString($old, 152, 8) -eq 'intro_15') 'first snapshot still holds its level'

    # a file that is not a save (wrong magic) is not listed as a slot
    $other = Join-Path $user 'B13EBABEBABEBABE\5841123F\00000001\JUNK\JUNK'
    New-Item -ItemType Directory -Path (Split-Path $other) -Force | Out-Null
    [IO.File]::WriteAllBytes($other, (New-Object byte[] 510))
    Check (@(Get-SaveSlotLevels $user).Count -eq 1) 'non-save file is not a slot'

    # M18: progression state of a save (read only)
    function Set-Word([string]$Path, [int]$Offset, [int]$Value) {
        $b = [IO.File]::ReadAllBytes($Path); $b[$Offset + 3] = [byte]$Value; [IO.File]::WriteAllBytes($Path, $b)
    }
    $states = Join-Path $tmp 'states\user'
    $base = Join-Path $states 'B13EBABEBABEBABE\5841123F\00000001'
    New-Save (Join-Path $base 'A\A') 'wood_11'
    New-Save (Join-Path $base 'B\B') 'intro_15'; Set-Word (Join-Path $base 'B\B') 132 1; Set-Word (Join-Path $base 'B\B') 108 2
    New-Save (Join-Path $base 'C\C') 'endgame'; Set-Word (Join-Path $base 'C\C') 104 1; Set-Word (Join-Path $base 'C\C') 108 9
    New-Save (Join-Path $base 'D\D') 'EndGame'; Set-Word (Join-Path $base 'D\D') 108 9
    $byslot = @{}; foreach ($s in (Get-SaveSlotLevels $states)) { $byslot[$s.slot] = $s }
    Check ($byslot['A'].state -eq 'campaign' -and $byslot['A'].revisit -eq 0 -and $byslot['A'].end_of_game -eq 0) 'campaign save classified'
    Check ($byslot['B'].state -eq 'revisit' -and $byslot['B'].highest_world -eq 2) 'revisit save classified, highest world read'
    Check ($byslot['C'].state -eq 'finished' -and $byslot['C'].highest_world -eq 9) 'finished save in the hub is not stranded'
    Check ($byslot['D'].state -eq 'hub_unfinished') 'hub save with the campaign unfinished is flagged'
    $stranded = Get-StrandedSlots $states
    Check (@($stranded).Count -eq 1 -and $stranded[0] -eq 'D') 'only the stranded slot is reported'
    Check (@(Get-StrandedSlots $user).Count -eq 0) 'a normal profile reports none'
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
$state = if ($script:failures) { 'FAIL' } else { 'PASS' }
Write-Host "M16_SAVEKEEPER_TEST $state checks=$($script:checks) failures=$($script:failures)"
exit $(if ($script:failures) { 1 } else { 0 })
