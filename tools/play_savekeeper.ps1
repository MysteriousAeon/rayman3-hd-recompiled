# Save keeper for tools\play.ps1 (M16, D-045). Functions only; dot-sourced.
#
# The title keeps one save slot per game and rewrites it at every level change, so after a session only the last
# level's save exists. The keeper copies the whole profile ("user root") into a history directory before the
# game starts and again every time its files have changed and then stayed unchanged for one poll, so each level
# a person reaches leaves a genuine save entry point behind (register one with tools\m12_save_entry.py).
# It only reads the profile: nothing in it is modified, renamed or deleted, and the game is not touched.
# History lives under private\play\save_history\<session>\NNN\user and is never committed.

function Get-ProfileFingerprint([string]$UserRoot) {
    if (-not (Test-Path -LiteralPath $UserRoot)) { return '' }
    $root = (Resolve-Path -LiteralPath $UserRoot).Path
    $rows = @(Get-ChildItem -LiteralPath $root -Recurse -File | Sort-Object FullName | ForEach-Object {
        '{0}|{1}|{2}' -f $_.FullName.Substring($root.Length), $_.Length, $_.LastWriteTimeUtc.Ticks
    })
    return ($rows -join "`n")
}

# Slot name and level name of every save in a profile (metadata only: magic check and the level-name field).
function Get-SaveSlotLevels([string]$UserRoot) {
    $slots = @()
    if (-not (Test-Path -LiteralPath $UserRoot)) { return ,$slots }
    foreach ($file in @(Get-ChildItem -LiteralPath $UserRoot -Recurse -File)) {
        if ($file.Directory.Name -ne $file.Name) { continue }
        if ($file.Directory.Parent.Name -ne '00000001') { continue }
        try { $bytes = [IO.File]::ReadAllBytes($file.FullName) } catch { continue }
        if ($bytes.Length -lt 184) { continue }
        if ([Text.Encoding]::ASCII.GetString($bytes, 0, 4) -ne 'AAAA') { continue }
        $end = 152
        while ($end -lt 184 -and $bytes[$end] -ne 0) { $end++ }
        $level = [Text.Encoding]::ASCII.GetString($bytes, 152, $end - 152)
        # M18 (RE_NOTES "M18"): progression words of the save record, read only. state:
        #   campaign        normal play
        #   revisit         written while a completed world is being revisited (the campaign's level is in the backup)
        #   finished        end-of-game flag set
        #   hub_unfinished  the save resumes in the end-of-game hub although the campaign is not finished: the
        #                   revisit defect of D-047 (only possible with -Revisit original or an older build)
        $endOfGame = Get-SaveWord $bytes 104
        $revisit = Get-SaveWord $bytes 132
        $state = if ($endOfGame -ne 0) { 'finished' } elseif ($level -ieq 'endgame') { 'hub_unfinished' }
                 elseif ($revisit -ne 0) { 'revisit' } else { 'campaign' }
        $slots += [ordered]@{ slot = $file.Name; level = $level; state = $state; highest_world = (Get-SaveWord $bytes 108)
                              revisit = $revisit; end_of_game = $endOfGame }
    }
    return ,$slots
}

function Get-SaveWord([byte[]]$Bytes, [int]$Offset) {
    return ([int64]$Bytes[$Offset] -shl 24) -bor ([int64]$Bytes[$Offset + 1] -shl 16) -bor ([int64]$Bytes[$Offset + 2] -shl 8) -bor [int64]$Bytes[$Offset + 3]
}

# Slots whose save resumes in the end-of-game hub with the campaign unfinished (D-047). Empty in normal use.
function Get-StrandedSlots([string]$UserRoot) {
    $found = @()
    $all = Get-SaveSlotLevels $UserRoot
    foreach ($entry in $all) { if ($entry.state -eq 'hub_unfinished') { $found += $entry.slot } }
    return $found
}

function New-SaveKeeper([string]$UserRoot, [string]$HistoryRoot) {
    return @{ UserRoot = $UserRoot; HistoryRoot = $HistoryRoot; Index = 0; Last = $null; Pending = $null }
}

function Save-ProfileSnapshot($Keeper, [string]$Reason) {
    # The index is taken before copying: if the copy fails (the title is rewriting a file), the next attempt
    # uses a new folder. A folder without snapshot.json is an incomplete copy.
    $index = $Keeper.Index
    $Keeper.Index = $index + 1
    $dest = Join-Path $Keeper.HistoryRoot ('{0:D3}' -f $index)
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    Copy-Item -LiteralPath $Keeper.UserRoot -Destination (Join-Path $dest 'user') -Recurse
    [ordered]@{
        index = $index
        reason = $Reason
        time = (Get-Date).ToString('o')
        slots = @(Get-SaveSlotLevels (Join-Path $dest 'user'))
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $dest 'snapshot.json') -Encoding UTF8
}

# One poll. A changed profile is copied once it has looked the same on two consecutive polls (so a file is not
# copied while the title is still writing it), or at once with -Final. Returns $true when a snapshot was taken.
function Update-SaveKeeper($Keeper, [string]$Reason = 'changed', [switch]$Final) {
    $now = Get-ProfileFingerprint $Keeper.UserRoot
    if ($now -eq '') { return $false }
    if ($null -ne $Keeper.Last -and $now -eq $Keeper.Last) { $Keeper.Pending = $null; return $false }
    if ($Final -or ($null -ne $Keeper.Pending -and $now -eq $Keeper.Pending)) {
        Save-ProfileSnapshot $Keeper $Reason
        $Keeper.Last = $now
        $Keeper.Pending = $null
        return $true
    }
    $Keeper.Pending = $now
    return $false
}
