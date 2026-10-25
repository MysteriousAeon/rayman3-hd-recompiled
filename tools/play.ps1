<#
.SYNOPSIS
    Launch the native Rayman 3 HD build for a human playtest: visible window, real keyboard and controller.

.DESCRIPTION
    Starts r3hd.exe with the M8 playtest profile (R3HD_PLAY): no hidden mode, no scheduled input, no
    game-derived dumps, no per-key trace. Everything the session writes stays under private/play/:
      profiles/<Profile>/user   persistent profile and save data (never deleted by this script)
      cache                     shader cache
      sessions/<timestamp>      runtime.log, m2_faults.log, crash record, session.json
    See reports/milestone8/PLAYTEST.md for controls and what to report.

    Licence mode (D-032, reports/milestone9/REPORT.md):
      -License full    default, and the default of r3hd.exe itself (user decision, D-032: the game files are
                       assumed legally obtained). The host sets license_mask=1 (bit 0 only, the bit the title
                       tests); the title runs as the full version and saves under the profile directory. This
                       is a runtime compatibility setting; nothing verifies ownership or any Xbox Live
                       entitlement.
      -License trial   sets R3HD_TRIAL for this launch: the runtime reports mask 0 and the title runs as its
                       trial (trailer at start-up, "Unlock Full Game", Load and Album dimmed, no saving).
    The mode is printed at launch and recorded in session.json. license_mask is refused in -ExtraArgs.

    Rendering resolution (D-042, reports/milestone15/REPORT.md):
      -RenderScale auto   default. The title renders a 1280x720 image; the host renderer draws it N times larger
                          along each axis (render targets, depth, viewports, resolves) and the title still sees
                          1280x720. auto picks the smallest N whose image covers the target: the display mode in
                          -Fullscreen (2560x1440 -> 2, i.e. a native 2560x1440 3D image), the window size
                          otherwise (1280x720 window -> 1).
      -RenderScale 1      original resolution (1280x720, stretched to the window): the compatibility mode.
      -RenderScale 2|3    2560x1440 or 3840x2160 internal image, whatever the window size.
    The choice is printed at launch and recorded in launch.json / session.json. resolution_scale and
    draw_resolution_scale_x / _y are refused in -ExtraArgs.

    Display mode (M30, D-067): -Display windowed (default) | fullscreen; -Fullscreen is the same as
    -Display fullscreen. Like the rendering resolution, cursor and save clock it is a preference that an
    installation's settings.json may hold (the Settings launcher saves it); a parameter named here wins.

    Window size and diagnostics (M31, D-068): -WindowSize auto|1280x720|1600x900|1920x1080|2560x1440 (physical
    pixels, windowed only, fitted to the primary display) and -Diagnostics standard|detailed. Both are preferences
    of settings.json as well. Standard keeps at most two rotated runtime logs, samples repetitive known runtime
    lines, and in an installed home removes session folders beyond the 10 newest (never save_history).

    Automated agents must not start the visible window: only -DryRun and -Collect are unattended-safe.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\play.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\play.ps1 -Fullscreen
    Borderless fullscreen at the desktop resolution; on a 2560x1440 display the 3D image is rendered at 2560x1440.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\play.ps1 -Fullscreen -RenderScale 1
    Fullscreen at the original 1280x720 rendering resolution (stretched), for comparison.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\play.ps1 -Fullscreen -Profile second
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\play.ps1 -License trial
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\play.ps1 -Collect
#>
param(
    [string]$Profile = 'default',
    [ValidateSet('trial', 'full')][string]$License = 'full',
    [switch]$Fullscreen,
    # M30 (D-067): the display mode as a registry setting (a preference kept in settings.json). -Fullscreen is the
    # same as -Display fullscreen and, like any parameter named on the command line, wins over the saved choice.
    [ValidateSet('windowed', 'fullscreen')][string]$Display = 'windowed',
    # M31 (D-068): the window's client size in physical pixels (windowed only). auto = the runtime's 1280x720 window
    # scaled by the Windows display scaling, as before. A size is converted to the logical size the runtime takes
    # (it multiplies by the scaling) and reduced to the largest that fits the primary display's work area. It never
    # changes the guest video mode (m31_runtime_patch.py) or the rendering resolution. -Width / -Height (logical
    # pixels, developer use) win over it.
    [ValidateSet('auto', '1280x720', '1600x900', '1920x1080', '2560x1440')][string]$WindowSize = 'auto',
    [ValidateSet('auto', '1', '2', '3')][string]$RenderScale = 'auto',
    # M31 (D-068): 'standard' bounds what a session records: at most two rotated runtime logs (5 MB each) beside the
    # current one, repetitive known runtime lines sampled (R3HD_PLAY sessions), and in an installed home the 10
    # newest session folders (save_history is never touched). 'detailed' = the M30 behaviour (20 rotations, every
    # line); the session count limit of an installed home still applies.
    [ValidateSet('standard', 'detailed')][string]$Diagnostics = 'standard',
    [ValidateSet('off', 'on')][string]$DiscordPresence = 'on',
    # D-102 / D-105: DualSense light bar by world and power-up, and a gentle R2 resistance armed in gameplay;
    # both off by default, independent of each other and of the presets; a non-DualSense pad is never written.
    # D-108: the resistance force in percent of the D-105 force (0 = no resistance, the trigger cleared); read once at
    # game start. A new installation's Settings store both options on (the parameter defaults stay the vanilla column).
    [ValidateSet('off', 'on')][string]$DualSenseLight = 'off',
    [ValidateSet('off', 'on')][string]$DualSenseTrigger = 'off',
    [ValidateRange(0, 100)][int]$DualSenseTriggerStrength = 30,
    # M16 (D-043): 'precise' delivers the guest vblank at its deadline (regular frame starts); 'pinned' keeps
    # the SDK's millisecond polling. Default precise since M17 (D-046): it gives the title the constant 16 ms
    # simulation step of an exact 60 Hz vblank; 'pinned' remains for comparison.
    [ValidateSet('pinned', 'precise')][string]$Pacing = 'precise',
    # M18 (D-047): 'fixed' applies the revisit-mode compatibility correction (a finished or re-chosen revisit
    # returns to the campaign instead of the end-of-game hub); 'original' keeps the title's own behaviour.
    [ValidateSet('fixed', 'original')][string]$Revisit = 'fixed',
    # M21 (D-050): 'auto' hides the mouse cursor over the game window while that window has the focus (mouse
    # movement shows it for a few seconds; focus loss, minimize and exit always show it). 'visible' keeps the
    # SDK's always-visible cursor. Nothing moves, confines or captures the pointer in either mode.
    [ValidateSet('auto', 'visible')][string]$Cursor = 'auto',
    # M21 (D-050): 'local' gives the title this PC's time zone, so the save list shows local time; 'utc' keeps
    # the SDK's answer (no zone: the title shows UTC). Saves and the guest clock are UTC in both modes.
    [ValidateSet('local', 'utc')][string]$SaveClock = 'local',
    # M23 (D-052, D-054): 'original' draws the two-layer translucent sheets of the `tvt_tVT` shader (haze in The
    # Bog of Murk, clouds in the Land of the Livid Dead) as the Xbox 360 HD release does: both layers on the
    # first layer's texture coordinates. 'separate' gives the second layer its own coordinates and scroll
    # offset, as the title's own vertex shader and the original pixel shader in its source file do. Supported
    # enhancement, off by default here. -WaterLayers is the option's first name and still works.
    [Alias('WaterLayers')][ValidateSet('original', 'separate')][string]$LayerCoords = 'original',
    # M26 (D-058): texture pages the Xbox 360 HD release stores the other way up from their meshes (the
    # Robo-Pirate statues of Hoodlum Headquarters): 'original' = the release's own data, 'corrected' = those
    # listed pages are mirrored top to bottom as they are read (exact, nothing written to disk). Supported
    # enhancement, off by default here.
    [ValidateSet('original', 'corrected')][string]$TextureOrient = 'original',
    # M44 (D-081, experimental): 'original' shows a voiced line's subtitle during gameplay only as the Xbox 360 HD
    # release does (in cinematic mode, or for the title's own short list of lines); 'all' lets the title's own
    # subtitle update show every voiced line it starts, with its own text and timing. D-090: a preference (Settings).
    [ValidateSet('original', 'all')][string]$GameplaySubtitles = 'original',
    # M27 (D-060): a preset from config/settings/registry.json (vanilla, hdplus, custom) and / or a settings file
    # written by tools\r3hd_settings.py write. Without either, the defaults above are the vanilla preset. A
    # parameter named on the command line always wins over the preset.
    [ValidateSet('', 'vanilla', 'hdplus', 'custom')][string]$Preset = '',
    [string]$SettingsFile = '',
    # M32 (D-069): a keyboard layout of config/controls/keymap.json for this launch (modern, original_pc); without it
    # the settings file's keys apply, else the keymap's default layout. keybind_* settings in -ExtraArgs win over both.
    [string]$KeyLayout = '',
    # M33 (D-070): 'on' applies the enabled, valid data-only mods of PLAYROOT\mods (HOME\mods); 'off' launches the
    # game's own data whatever is enabled (the no-mod fallback). Mods are never part of Vanilla / HD+ / Custom.
    [ValidateSet('on', 'off')][string]$Mods = 'on',
    # M28 (D-063): where things live, highest precedence first: these parameters, then R3HD_GAME_DIR /
    # R3HD_BIN_DIR / R3HD_PLAY_ROOT, then a per-user home (-UserHome, else R3HD_HOME: HOME\data\content, HOME\bin,
    # HOME itself for profiles / cache / sessions, HOME\settings.json), then the repository's private\ layout.
    # tools\r3hd_paths.py resolve gives the same answer; m28_portable_regression.py keeps them equal.
    [string]$UserHome = '',
    [string]$GameDir = '',
    [string]$BinDir = '',
    [string]$PlayRoot = '',
    [switch]$NoKeyboard,
    [switch]$Mouse,
    [ValidateSet('info', 'debug', 'warn')][string]$LogLevel = 'info',
    [int]$Width = 0,
    [int]$Height = 0,
    # Extra runtime cvars, e.g. -ExtraArgs --vsync=false. Passed through unchanged; recorded in session.json.
    [string[]]$ExtraArgs = @(),
    # Print and validate the launch without starting anything.
    [switch]$DryRun,
    # Bundle the text diagnostics of the most recent session into diagnostics.zip (still private).
    [switch]$Collect,
    # Print the log census of an existing session or run directory and exit (starts nothing).
    [string]$Summarize = '',
    # Only with the user's explicit approval for that one launch.
    [switch]$AllowFromAgent
)
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$homeRoot = if ($UserHome) { $UserHome } elseif ($env:R3HD_HOME) { $env:R3HD_HOME } else { '' }
# A relative path given by a parameter, a variable or the home is taken from the current directory and made absolute
# (tools\r3hd_paths.py does the same); the repository default is left exactly as it always was.
function ConvertTo-FullPath([string]$Path) { return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path) }
if ($homeRoot) { $homeRoot = ConvertTo-FullPath $homeRoot }
function Resolve-R3hdPath([string]$Explicit, [string]$EnvName, [string]$HomeRelative, [string]$Legacy) {
    if ($Explicit) { return (ConvertTo-FullPath $Explicit) }
    $fromEnv = [Environment]::GetEnvironmentVariable($EnvName)
    if ($fromEnv) { return (ConvertTo-FullPath $fromEnv) }
    if ($homeRoot) { return $(if ($HomeRelative) { Join-Path $homeRoot $HomeRelative } else { $homeRoot }) }
    return (Join-Path $repo $Legacy)
}
$bin = Resolve-R3hdPath $BinDir 'R3HD_BIN_DIR' 'bin' 'private/work/rex/out/build/win-amd64-release'
$exe = Join-Path $bin 'r3hd.exe'
$game = Resolve-R3hdPath $GameDir 'R3HD_GAME_DIR' 'data\content' 'private/extracted/5841123F'
$play = Resolve-R3hdPath $PlayRoot 'R3HD_PLAY_ROOT' '' 'private/play'
$legacyPlay = ($play -eq (Join-Path $repo 'private/play'))
$historyText = if ($legacyPlay) { 'private\play\save_history' } else { Join-Path $play 'save_history' }
$sessions = Join-Path $play 'sessions'
# A home's settings.json is the installer's saved choice; it applies when neither -Preset nor -SettingsFile is named.
$homeSettings = if ($homeRoot) { Join-Path $homeRoot 'settings.json' } else { '' }
if ($homeSettings -and -not $Preset -and -not $SettingsFile -and (Test-Path -LiteralPath $homeSettings -PathType Leaf)) { $SettingsFile = $homeSettings }
$xexSha256 = '77a4df54340aebcc79eb0f0053938c03b8efd2efdd3ffee26c00fdfef3c6e8ca'

function Get-FileSha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}

function Get-PrimaryDisplayMode {
    # Current mode of the primary display in physical pixels; $null if the query fails.
    try {
        Add-Type -Namespace R3hd -Name Display -MemberDefinition @'
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
public struct DEVMODE {
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
    public short dmSpecVersion; public short dmDriverVersion; public short dmSize; public short dmDriverExtra;
    public int dmFields; public int dmPositionX; public int dmPositionY; public int dmDisplayOrientation;
    public int dmDisplayFixedOutput; public short dmColor; public short dmDuplex; public short dmYResolution;
    public short dmTTOption; public short dmCollate;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
    public short dmLogPixels; public int dmBitsPerPel; public int dmPelsWidth; public int dmPelsHeight;
    public int dmDisplayFlags; public int dmDisplayFrequency; public int dmICMMethod; public int dmICMIntent;
    public int dmMediaType; public int dmDitherType; public int dmReserved1; public int dmReserved2;
    public int dmPanningWidth; public int dmPanningHeight;
}
[DllImport("user32.dll", CharSet = CharSet.Ansi)]
public static extern bool EnumDisplaySettingsA(string deviceName, int modeNum, ref DEVMODE devMode);
'@ -ErrorAction Stop
        $mode = New-Object R3hd.Display+DEVMODE
        $mode.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($mode)
        if ([R3hd.Display]::EnumDisplaySettingsA([NullString]::Value, -1, [ref]$mode) -and $mode.dmPelsWidth -gt 0 -and $mode.dmPelsHeight -gt 0) {
            return @($mode.dmPelsWidth, $mode.dmPelsHeight, $mode.dmDisplayFrequency)
        }
    } catch { }
    return $null
}

function Get-PrimaryWorkArea {
    # M31: the primary display's work area (physical pixels) and its DPI, read per-monitor DPI aware on this thread
    # only (the previous awareness is restored; nothing on the desktop changes). $null if the query fails.
    try {
        Add-Type -Namespace R3hd -Name Monitor -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
[StructLayout(LayoutKind.Sequential)] public struct MONITORINFO { public int cbSize; public RECT rcMonitor; public RECT rcWork; public int dwFlags; }
[DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
[DllImport("user32.dll")] public static extern IntPtr MonitorFromPoint(POINT point, int flags);
[DllImport("user32.dll")] public static extern bool GetMonitorInfoW(IntPtr monitor, ref MONITORINFO info);
[DllImport("shcore.dll")] public static extern int GetDpiForMonitor(IntPtr monitor, int type, out uint dpiX, out uint dpiY);
[DllImport("user32.dll")] public static extern bool AdjustWindowRectExForDpi(ref RECT rect, int style, bool menu, int exStyle, uint dpi);
'@ -ErrorAction Stop
        $old = [R3hd.Monitor]::SetThreadDpiAwarenessContext([IntPtr](-4))
        try {
            $monitor = [R3hd.Monitor]::MonitorFromPoint((New-Object R3hd.Monitor+POINT), 1)
            $info = New-Object R3hd.Monitor+MONITORINFO
            $info.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($info)
            [uint32]$dpiX = 0; [uint32]$dpiY = 0
            if (-not [R3hd.Monitor]::GetMonitorInfoW($monitor, [ref]$info)) { return $null }
            if ([R3hd.Monitor]::GetDpiForMonitor($monitor, 0, [ref]$dpiX, [ref]$dpiY) -ne 0 -or $dpiX -lt 48) { return $null }
            # The frame of a resizable window (WS_OVERLAPPEDWINDOW, as SDL creates it) at this DPI.
            $frame = New-Object R3hd.Monitor+RECT
            if (-not [R3hd.Monitor]::AdjustWindowRectExForDpi([ref]$frame, 0x00CF0000, $false, 0, $dpiX)) { return $null }
            return [ordered]@{ width = $info.rcWork.Right - $info.rcWork.Left; height = $info.rcWork.Bottom - $info.rcWork.Top
                dpi = [int]$dpiX; frame_width = $frame.Right - $frame.Left; frame_height = $frame.Bottom - $frame.Top }
        } finally { if ($old -ne [IntPtr]::Zero) { [void][R3hd.Monitor]::SetThreadDpiAwarenessContext($old) } }
    } catch { return $null }
}

function Get-WindowPlan([string]$Size, $Area) {
    # M31 (D-068): the client size in physical pixels for -WindowSize, fitted to the work area, and the logical size
    # the runtime is given (it multiplies by the display scaling, SDL_GetWindowDisplayScale). Pure: tested by
    # tools\m31_regression.py with made-up work areas.
    $sizes = @('2560x1440', '1920x1080', '1600x900', '1280x720')
    $dpi = if ($Area) { [int]$Area.dpi } else { 96 }
    if ($Size -eq 'auto') {
        $w = [int][Math]::Round(1280 * $dpi / 96.0); $h = [int][Math]::Round(720 * $dpi / 96.0)
        return [ordered]@{ requested = 'auto'; width = $w; height = $h; logical_width = 0; logical_height = 0; dpi = $dpi; fitted = $false
            note = $(if ($Area) { 'runtime default window, 1280x720 scaled by the display scaling' } else { 'runtime default window (display not read)' }) }
    }
    $pick = $Size
    $fitted = $false
    if ($Area) {
        $fits = { param($s) $p = $s -split 'x'; ([int]$p[0] + $Area.frame_width) -le $Area.width -and ([int]$p[1] + $Area.frame_height) -le $Area.height }
        if (-not (& $fits $pick)) {
            $fitted = $true
            $pick = $sizes | Where-Object { [int](($_ -split 'x')[0]) -lt [int](($Size -split 'x')[0]) -and (& $fits $_) } | Select-Object -First 1
            if (-not $pick) {
                # Nothing listed fits (a small or very scaled screen): the largest 16:9 client that does.
                $h = [Math]::Min($Area.height - $Area.frame_height, [Math]::Floor(($Area.width - $Area.frame_width) * 9 / 16))
                $h = [int]([Math]::Max(360, $h) - ([Math]::Max(360, $h) % 2))
                $w = [int][Math]::Floor($h * 16 / 9); $w -= $w % 2
                $pick = "${w}x$h"
            }
        }
    }
    $p = $pick -split 'x'
    $w = [int]$p[0]; $h = [int]$p[1]
    return [ordered]@{ requested = $Size; width = $w; height = $h
        logical_width = [int][Math]::Round($w * 96.0 / $dpi); logical_height = [int][Math]::Round($h * 96.0 / $dpi); dpi = $dpi; fitted = $fitted
        note = $(if (-not $Area) { 'display not read: taken as 100 % scaling, not fitted' } elseif ($fitted) { "reduced to fit the work area $($Area.width)x$($Area.height)" } else { 'fits' }) }
}

function Get-SessionsToPrune([string]$Root, [int]$Keep) {
    # M31 (D-068): session folders (timestamp names only) beyond the $Keep newest; never anything else.
    $all = @(Get-ChildItem -LiteralPath $Root -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d{8}-\d{6}$' } | Sort-Object Name)
    if ($all.Count -le $Keep) { return @() }
    return @($all[0..($all.Count - $Keep - 1)])
}

function Get-LogFiles([string]$Session) {
    # runtime.N.log are older rotations (highest N first), runtime.log is the newest part.
    $rotated = @(Get-ChildItem -LiteralPath $Session -Filter 'runtime.*.log' -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Name -replace '^runtime\.(\d+)\.log$', '$1') } -Descending)
    $current = Join-Path $Session 'runtime.log'
    $files = @($rotated | ForEach-Object { $_.FullName })
    if (Test-Path -LiteralPath $current) { $files += $current }
    return ,$files
}

function Get-LogCensus([string]$Session) {
    # guest_license_masks: every distinct value the title received from XamContentGetLicenseMask in this session.
    $census = [ordered]@{ lines = 0; warning = 0; error = 0; critical = 0; stub_imports = 0; guest_license_masks = @(); last_lines = @() }
    $masks = New-Object 'System.Collections.Generic.SortedSet[string]'
    $tail = New-Object 'System.Collections.Generic.Queue[string]'
    foreach ($file in (Get-LogFiles $Session)) {
        foreach ($line in [System.IO.File]::ReadLines($file)) {
            $census.lines++
            if ($line.Contains('] [warning] ')) { $census.warning++ }
            elseif ($line.Contains('] [error] ')) { $census.error++ }
            elseif ($line.Contains('] [critical] ')) { $census.critical++ }
            if ($line.Contains(' stub=true count=1 ')) { $census.stub_imports++ }
            if ($line.Contains('M6 license ') -and $line -match ' mask=([0-9A-Fa-f]{8})') { [void]$masks.Add($Matches[1].ToUpperInvariant()) }
            $tail.Enqueue($line); if ($tail.Count -gt 15) { [void]$tail.Dequeue() }
        }
    }
    $census.guest_license_masks = @($masks)
    # M11: first-chance host exceptions seen by the vectored handler (m2_faults.log). Thread naming (406D1388)
    # and the guest-raise transport (E0473458) are routine; any other code is listed, because fail-fast codes
    # such as C0000374 never reach the last-chance crash record. Symbolise with tools/m11_symbolize.py.
    $faults = [ordered]@{}
    $faultLog = Join-Path $Session 'm2_faults.log'
    if (Test-Path -LiteralPath $faultLog) {
        foreach ($line in [System.IO.File]::ReadLines($faultLog)) {
            if ($line -match '^M2 exception code=([0-9A-Fa-f]{8})') {
                $code = $Matches[1].ToUpperInvariant()
                if ($code -ne '406D1388' -and $code -ne 'E0473458') { $faults[$code] = 1 + [int]$faults[$code] }
            }
        }
    }
    $census.host_fault_codes = @($faults.Keys | ForEach-Object { "$_ x$($faults[$_])" })
    $census.last_lines = @($tail.ToArray())
    return $census
}

if ($Profile -notmatch '^[A-Za-z0-9_-]+$') { throw 'Profile must be a simple name' }
foreach ($extra in $ExtraArgs) {
    if ($extra -notmatch '^--[a-z0-9_]+=') { throw "Extra arguments look like --name=value: $extra" }
    if ($extra -match '^--(game_data_root|user_data_root|cache_root|log_file|gpu_plugin)=') { throw "Set by the launcher: $extra" }
    if ($extra -match '^--(resolution_scale|draw_resolution_scale_x|draw_resolution_scale_y)=') { throw 'The rendering resolution is chosen with -RenderScale auto|1|2|3, not through -ExtraArgs' }
    if ($extra -match '^--license_mask=') { throw 'The licence mode is chosen with -License full|trial, not through -ExtraArgs' }
    if ($extra -match '^--cl=') { throw 'The guest command line (developer options such as -level:) is for hidden test runs only: tools\run_milestone6.ps1 -TestLevel' }
}

if ($Summarize) {
    if (-not (Test-Path -LiteralPath $Summarize -PathType Container)) { throw "Not a directory: $Summarize" }
    $census = Get-LogCensus (Resolve-Path -LiteralPath $Summarize).Path
    $census.Remove('last_lines')
    $census.crash_report = (Test-Path -LiteralPath (Join-Path $Summarize 'r3hd_crash.txt'))
    $census | ConvertTo-Json
    exit 0
}

if ($Collect) {
    $latest = Get-ChildItem -LiteralPath $sessions -Directory -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
    if (-not $latest) { throw "No playtest session under $sessions" }
    $zip = Join-Path $latest.FullName 'diagnostics.zip'
    $items = @(Get-ChildItem -LiteralPath $latest.FullName -File | Where-Object { $_.Name -match '\.(log|txt|json|dmp)$' })
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
    Compress-Archive -LiteralPath ($items | ForEach-Object { $_.FullName }) -DestinationPath $zip
    Write-Host "Diagnostics of session $($latest.Name): $zip"
    Write-Host 'The archive contains file names and addresses from the game; keep it private.'
    exit 0
}

# --- presets (M27, D-060) ----------------------------------------------------------------------
# tools\r3hd_settings.py is the one resolver; it decides every setting a parameter did not name explicitly.
# M30: -Fullscreen is an explicit -Display fullscreen.
if ($Fullscreen) {
    if ($PSBoundParameters.ContainsKey('Display') -and $Display -ne 'fullscreen') { throw '-Fullscreen and -Display windowed contradict each other' }
    $Display = 'fullscreen'
    $PSBoundParameters['Display'] = 'fullscreen'
}
$presetLabel = 'vanilla (launcher defaults)'
$presetWarnings = @()
$keyboard = $null
# M32 (D-069): the resolver runs for every launch, because it also gives the keyboard map; without -Preset or
# -SettingsFile its preset values are the parameter defaults above (m27_settings_regression.py keeps them equal).
if ($true) {
    $settingParams = [ordered]@{ Revisit = 'revisit'; Pacing = 'pacing'; Display = 'display'; Cursor = 'cursor'; SaveClock = 'save_clock';
        RenderScale = 'render_scale'; LayerCoords = 'layer_coords'; TextureOrient = 'texture_orient'; WindowSize = 'window_size';
        Diagnostics = 'diagnostics'; GameplaySubtitles = 'gameplay_subtitles'; DiscordPresence = 'discord_presence'; DualSenseLight = 'dualsense_light'; DualSenseTrigger = 'dualsense_trigger';
        DualSenseTriggerStrength = 'dualsense_trigger_strength' }
    $resolverArgs = @((Join-Path $PSScriptRoot 'r3hd_settings.py'), 'resolve')
    if ($Preset) { $resolverArgs += @('--preset', $Preset) }
    if ($SettingsFile) { $resolverArgs += @('--settings', $SettingsFile) }
    $explicit = @($settingParams.Keys | Where-Object { $PSBoundParameters.ContainsKey($_) } |
        ForEach-Object { "$($settingParams[$_])=$(Get-Variable -Name $_ -ValueOnly)" })
    if ($explicit.Count) { $resolverArgs += '--explicit'; $resolverArgs += $explicit }
    if ($KeyLayout) { $resolverArgs += @('--key-layout', $KeyLayout) }
    # M29 (D-066): an installed copy (HOME\app\tools\play.ps1) carries its own Python runtime in HOME\app\python; a
    # repository has none there and uses Python from PATH, as before.
    $bundledPython = Join-Path $repo 'python\python.exe'
    $python = if (Test-Path -LiteralPath $bundledPython -PathType Leaf) { $bundledPython } else { 'python' }
    try { $resolverOut = & $python @resolverArgs | Out-String } catch { throw "The settings resolver (presets and the keyboard map) needs Python 3.11 on PATH in a repository: $($_.Exception.Message)" }
    if (-not $resolverOut.Trim()) { throw "Settings resolver failed without a result (exit code $LASTEXITCODE): tools\r3hd_settings.py" }
    $resolved = $resolverOut | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $resolved.result -ne 'resolved') { throw "Settings refused: $($resolved.code): $($resolved.detail)" }
    foreach ($name in $settingParams.Keys) { Set-Variable -Name $name -Value ([string]$resolved.values.($settingParams[$name])) }
    if ($Preset -or $SettingsFile) { $presetLabel = $resolved.label }
    $presetWarnings = @($resolved.warnings)
    $keyboard = $resolved.keyboard
}
# M32: the keyboard map's runtime arguments. A keybind_* setting named in -ExtraArgs replaces the map's for that input
# (explicit wins); a combination with a modifier there ("Shift+Up") needs the runtime's exact modifier matching.
$keyArgs = @()
$keyText = 'none (-NoKeyboard)'
if (-not $NoKeyboard) {
    $named = @($ExtraArgs | Where-Object { $_ -match '^--keybind_[a-z_]+=' } | ForEach-Object { ($_ -split '=', 2)[0] })
    $keyArgs = @($keyboard.args | Where-Object { $named -notcontains (($_ -split '=', 2)[0]) })
    if (@($ExtraArgs | Where-Object { $_ -match '^--keybind_[a-z_]+=.*\+' }).Count -or @($ExtraArgs | Where-Object { $_ -match '^--mnk_modifier_keys=' }).Count) {
        $keyArgs = @($keyArgs | Where-Object { $_ -notmatch '^--mnk_modifier_keys=' })
    }
    $keyText = "$($keyboard.layout_name) ($($keyboard.state)$(if ($named.Count) { "; -ExtraArgs name $($named.Count) input(s)" }))"
}

# --- preflight ---------------------------------------------------------------------------------
$problems = @()
# M30: an installed copy (HOME\installer.json) is repaired by its installer, a repository is rebuilt.
$installed = $homeRoot -and (Test-Path -LiteralPath (Join-Path $homeRoot 'installer.json') -PathType Leaf)
$binHint = if ($installed) { 'run the installer again and choose this folder to repair it' } else { 'build with: cmd /c tools\build_milestone8.bat' }
$dataHint = if ($installed) { 'run the installer again and choose this folder to repair it; it may ask for your game package' } else { 'see tools\r3hd_intake.py' }
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { $problems += "Executable missing: $exe ($binHint)" }
foreach ($dll in 'rexruntime.dll', 'rexgpu-xenos.dll', 'ffmpeg.dll', 'mspack.dll') {
    if (-not (Test-Path -LiteralPath (Join-Path $bin $dll) -PathType Leaf)) { $problems += "Runtime library missing next to the executable: $dll ($binHint)" }
}
foreach ($dll in 'MSVCP140.dll', 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll') {
    if (-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot "System32\$dll"))) { $problems += "Microsoft Visual C++ runtime missing: $dll (install the Microsoft Visual C++ Redistributable 2015-2022 x64 from aka.ms/vs/17/release/vc_redist.x64.exe)" }
}
$xex = Join-Path $game 'Default.xex'
if (-not (Test-Path -LiteralPath $xex -PathType Leaf)) { $problems += "Extracted game content missing: $xex ($dataHint)" }
elseif ((Get-FileSha256 $xex) -ne $xexSha256) { $problems += "Default.xex does not match the hash this build was translated from ($dataHint)" }
if (Get-Process r3hd -ErrorAction SilentlyContinue) { $problems += 'Another r3hd.exe is already running (Rayman 3 HD is already open)' }
if ($problems.Count) { $problems | ForEach-Object { Write-Host "PREFLIGHT: $_" }; throw 'Preflight failed' }

$stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
$session = Join-Path $sessions $stamp
$user = Join-Path $play "profiles/$Profile/user"
$cache = Join-Path $play 'cache'
$arguments = @(
    "--game_data_root=$game", "--user_data_root=$user", "--cache_root=$cache",
    '--gpu_plugin=xenos', "--log_level=$LogLevel", '--log_flush_interval=1',
    "--log_file=$(Join-Path $session 'runtime.log')",
    "--mnk_mode=$((-not $NoKeyboard).ToString().ToLowerInvariant())",
    "--fullscreen=$(($Display -eq 'fullscreen').ToString().ToLowerInvariant())"
)
if ($Mouse) { $arguments += '--mnk_mouse=true' }
# M31 (D-068): diagnostics. standard = two rotated logs at most (the runtime keeps 20 by default).
if ($Diagnostics -eq 'standard') { $arguments += '--log_max_files=2' }
# Window size (M31). -Width / -Height are logical pixels as before; -WindowSize is physical and converted here.
$window = $null
if ($Width -gt 0 -and $Height -gt 0) {
    $arguments += "--window_width=$Width"; $arguments += "--window_height=$Height"
    $window = [ordered]@{ requested = "-Width $Width -Height $Height (logical)"; width = $Width; height = $Height; logical_width = $Width; logical_height = $Height; dpi = 0; fitted = $false; note = 'explicit -Width / -Height' }
} elseif ($Display -ne 'fullscreen') {
    $window = Get-WindowPlan $WindowSize (Get-PrimaryWorkArea)
    if ($window.logical_width -gt 0) { $arguments += "--window_width=$($window.logical_width)"; $arguments += "--window_height=$($window.logical_height)" }
}
# Rendering resolution (D-042). The target is the display mode in fullscreen (physical pixels, read with
# EnumDisplaySettings so desktop scaling does not shrink it), otherwise the window's physical size (M31).
$target = [ordered]@{ width = 1280; height = 720; source = 'default window' }
if ($Display -eq 'fullscreen') {
    $mode = Get-PrimaryDisplayMode
    if ($mode) { $target = [ordered]@{ width = $mode[0]; height = $mode[1]; source = 'primary display mode' } }
    else { $target.source = 'display mode unavailable, assumed 1280x720' }
} elseif ($window) { $target = [ordered]@{ width = $window.width; height = $window.height; source = "window ($($window.note))" } }
$windowText = if ($window) { "$($window.width)x$($window.height) ($($window.note); -WindowSize $WindowSize)" } else { 'not used (fullscreen)' }
# M31 (D-068): an installed home keeps its 10 newest sessions (this one included); a repository keeps all.
$sessionLimit = 10
$prune = if ($installed) { @(Get-SessionsToPrune $sessions ($sessionLimit - 1)) } else { @() }
if ($RenderScale -eq 'auto') {
    $scale = [Math]::Max([Math]::Ceiling($target.width / 1280.0), [Math]::Ceiling($target.height / 720.0))
    $scale = [int][Math]::Min(3, [Math]::Max(1, $scale))
} else { $scale = [int]$RenderScale }
$arguments += "--resolution_scale=$scale"
$arguments += $keyArgs
$renderText = "$(1280 * $scale)x$(720 * $scale) internal image (scale $scale, -RenderScale $RenderScale), shown in $($target.width)x$($target.height) ($($target.source))"
$arguments += $ExtraArgs
# The host sets licence bit 0 by default (D-032); trial mode is requested through R3HD_TRIAL. No mask is passed here.
$licenseMask = if ($License -eq 'full') { 1 } else { 0 }
$licenseText = if ($licenseMask -eq 1) { 'full version (build default: license_mask=1; a compatibility setting, not verified ownership)' }
               else { 'trial (R3HD_TRIAL: license_mask=0; no saving)' }

# M33 (D-070): data-only mods under PLAYROOT\mods (an installation: HOME\mods). tools\r3hd_mods.py validates them and
# compiles the enabled ones into a verified plan under the cache, named in R3HD_MODS_PLAN; the runtime overlays it on
# game-file reads and never writes a game file. A mod that does not apply is left out with a note; -Mods off, no
# enabled mod or an unreadable mod list launches the game's own data. Never part of Vanilla / HD+ / Custom.
$modsRoot = Join-Path $play 'mods'
$modsText = 'none installed'
$modsPlan = ''
$achText = ''
$modsNotes = @()
if ($Mods -eq 'off') { $modsText = 'off (-Mods off)' }
elseif (Test-Path -LiteralPath (Join-Path $modsRoot 'state.json') -PathType Leaf) {
    $modsArgs = @((Join-Path $PSScriptRoot 'r3hd_mods.py'), $(if ($DryRun) { 'list' } else { 'plan' }), '--json',
        '--mods-root', $modsRoot, '--cache', (Join-Path $cache 'mods'), '--game-dir', $game)
    if ($homeRoot) { $modsArgs += @('--home', $homeRoot) }
    $modsOut = $null
    try { $modsOut = (& $python @modsArgs | Out-String) | ConvertFrom-Json } catch { $modsOut = $null }
    if (-not $modsOut -or $modsOut.result -ne 'ok') {
        $modsText = 'none applied'
        $modsNotes += "the mod list could not be used ($(if ($modsOut) { "$($modsOut.code): $($modsOut.detail)" } else { 'no result' })); the game's own data is used"
    } else {
        foreach ($m in @($modsOut.mods)) {
            if ($m.enabled -and $m.state -ne 'active') { $modsNotes += "$($m.id) is not applied: $($m.code) $($m.detail)" }
            foreach ($s in @($m.shadowed)) { if ($s) { $modsNotes += "$($m.id): $s is covered by a mod of higher priority" } }
        }
        $active = @($modsOut.active)
        $modsText = if ($active.Count) { "$($active -join ', ') ($($modsOut.ranges) ranges)" } else { 'none enabled' }
        if (-not $DryRun -and $active.Count -and $modsOut.plan) { $modsPlan = [string]$modsOut.plan }
        # D-101: display text for the Achievements overlay from the active mods (English where none or stale).
        if (-not $DryRun -and $active.Count -and $modsOut.achievement_text) { $achText = [string]$modsOut.achievement_text }
    }
}

if ($DryRun) {
    Write-Host 'DRY RUN - nothing was started.'
    Write-Host "executable : $exe"
    Write-Host "sha256     : $(Get-FileSha256 $exe)"
    Write-Host "session    : $session"
    Write-Host "profile    : $user"
    Write-Host "game data  : $game"
    Write-Host "bin dir    : $bin"
    Write-Host "play root  : $play"
    Write-Host "settings   : $SettingsFile"
    Write-Host "licence    : $licenseText"
    Write-Host "preset     : $presetLabel"
    $presetWarnings | ForEach-Object { Write-Host "preset note: $_" }
    Write-Host "display    : $Display"
    Write-Host "window     : $windowText"
    Write-Host "rendering  : $renderText"
    Write-Host "diagnostics: $Diagnostics; sessions kept: $(if ($installed) { "$sessionLimit newest (would remove $($prune.Count))" } else { 'all (not an installed home)' })"
    Write-Host "revisit    : $Revisit"
    Write-Host "cursor     : $Cursor"
    Write-Host "save clock : $SaveClock"
    Write-Host "layer coord: $LayerCoords"
    Write-Host "texture ori: $TextureOrient"
    Write-Host "gameplay sub: $GameplaySubtitles"
    Write-Host "dualsense  : light=$DualSenseLight trigger=$DualSenseTrigger strength=$DualSenseTriggerStrength"
    Write-Host "keyboard   : $keyText"
    Write-Host "mods       : $modsText"
    $modsNotes | ForEach-Object { Write-Host "mods note  : $_" }
    $arguments | ForEach-Object { Write-Host "argument   : $_" }
    exit 0
}
$agent = $env:AI_AGENT -or $env:CLAUDECODE -or $env:CLAUDE_CODE_SESSION_ID
if ($agent -and -not $AllowFromAgent) {
    throw 'This shell belongs to an automated agent. The visible playtest window is started by a person (or with -AllowFromAgent after explicit approval).'
}

# --- launch ------------------------------------------------------------------------------------
# M31 (D-068): older session folders of an installed home; a folder that cannot be removed is left for next time.
$pruned = 0
foreach ($old in $prune) { try { Remove-Item -LiteralPath $old.FullName -Recurse -Force -ErrorAction Stop; $pruned++ } catch { } }
New-Item -ItemType Directory -Path $session, $user, $cache -Force | Out-Null
# Written before the launch so the selected licence mode is on record even if this script is interrupted.
[ordered]@{ session = $stamp; profile = $Profile; preset = $presetLabel; settings_file = $SettingsFile; license_mode = $License; license_mask = $licenseMask; display = $Display; window = $window; render_scale = $scale; render_scale_option = $RenderScale; pacing = $Pacing; revisit = $Revisit; cursor = $Cursor; save_clock = $SaveClock; layer_coords = $LayerCoords; texture_orient = $TextureOrient; gameplay_subtitles = $GameplaySubtitles; diagnostics = $Diagnostics; dualsense_light = $DualSenseLight; dualsense_trigger = $DualSenseTrigger; dualsense_trigger_strength = $DualSenseTriggerStrength; keyboard = $keyText; mods = $modsText; mods_notes = $modsNotes; sessions_removed = $pruned; render_target = $target; arguments = $arguments } |
    ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $session 'launch.json') -Encoding UTF8
$testOnly = 'R3HD_NONINTRUSIVE', 'R3HD_TEST_SECONDS', 'R3HD_INPUT_SCHEDULE', 'R3HD_INPUT_FOLLOW', 'R3HD_M5_CAPTURE',
    'R3HD_FRAME_REQUEST', 'R3HD_AUDIO_CAPTURE', 'R3HD_AUDIO_AFTER', 'R3HD_M5_VB_RESIDENCY_CACHE', 'R3HD_PLAY', 'R3HD_TRIAL',
    'R3HD_FRAME_TRACE', 'R3HD_VBLANK_SPIN_US', 'R3HD_TEST_WORLD_END',
    'R3HD_SAVE_FAULT', 'R3HD_SAVE_COMMIT', 'R3HD_CURSOR', 'R3HD_TIMEZONE',
    'R3HD_M22_DRAW_TRACE', 'R3HD_M22_AUDIO', 'R3HD_AUDIO_AUDIBLE', 'R3HD_M24_EVENTS', 'R3HD_DIAGNOSTICS', 'R3HD_KEYMAP_TEST', 'R3HD_DISCORD', 'R3HD_DS_LIGHT', 'R3HD_DS_TRIGGER', 'R3HD_DS_TRIGGER_STRENGTH', 'R3HD_ACH_TEXT'
$saved = @{}
foreach ($name in $testOnly) { $saved[$name] = [Environment]::GetEnvironmentVariable($name); [Environment]::SetEnvironmentVariable($name, $null) }
$env:R3HD_PLAY = '1'
$env:R3HD_DISCORD = $DiscordPresence
$env:R3HD_DS_LIGHT = $DualSenseLight
$env:R3HD_DS_TRIGGER = $DualSenseTrigger
$env:R3HD_DS_TRIGGER_STRENGTH = [string]$DualSenseTriggerStrength
$savedVblank = $env:R3HD_VBLANK
$env:R3HD_VBLANK = $(if ($Pacing -eq 'precise') { 'deadline' } else { 'poll' })
$savedRevisit = $env:R3HD_REVISIT
$env:R3HD_REVISIT = $Revisit
$savedLayers = $env:R3HD_LAYER_COORDS
$savedWater = $env:R3HD_WATER_LAYERS
$env:R3HD_LAYER_COORDS = $LayerCoords
$env:R3HD_WATER_LAYERS = $null
$savedOrient = $env:R3HD_TEXTURE_ORIENT
$env:R3HD_TEXTURE_ORIENT = $TextureOrient
$savedGameplaySubs = $env:R3HD_GAMEPLAY_SUBTITLES
$env:R3HD_GAMEPLAY_SUBTITLES = $GameplaySubtitles
# M33: the verified mod plan, or none (a value from the caller's environment never reaches a playtest).
$savedModsPlan = $env:R3HD_MODS_PLAN
$env:R3HD_MODS_PLAN = $(if ($modsPlan) { $modsPlan } else { $null })
if ($achText) { $env:R3HD_ACH_TEXT = $achText }
# M21: set after the test-only names were cleared above; the finally block restores the caller's values.
if ($Cursor -eq 'visible') { $env:R3HD_CURSOR = 'visible' }
if ($SaveClock -eq 'utc') { $env:R3HD_TIMEZONE = 'utc' }
# M31: the runtime samples its repetitive known lines in a playtest session unless detailed diagnostics are chosen.
if ($Diagnostics -eq 'detailed') { $env:R3HD_DIAGNOSTICS = 'detailed' }
if ($License -eq 'trial') { $env:R3HD_TRIAL = '1' }
$started = Get-Date
$exitCode = $null
try {
    $quoted = ($arguments | ForEach-Object { '"' + ($_ -replace '(\\+)$', '$1$1') + '"' }) -join ' '
    Write-Host "Licence mode: $licenseText"
    Write-Host "Preset: $presetLabel"
    $presetWarnings | ForEach-Object { Write-Host "Preset note: $_" }
    Write-Host "Rendering: $renderText"
    Write-Host "Frame pacing: $Pacing"
    Write-Host "Revisit mode: $Revisit"
    Write-Host "Mouse cursor: $Cursor; save clock: $SaveClock; layer coordinates: $LayerCoords; texture orientation: $TextureOrient; gameplay subtitles: $GameplaySubtitles"
    Write-Host "Mods: $modsText"
    $modsNotes | ForEach-Object { Write-Host "Mods note: $_" }
    Write-Host "Starting r3hd (session $stamp). Close the window or press Alt+F4 to quit."
    # M16 (D-045): keep a copy of the profile as it is now and after every change (one save entry per level
    # reached). Read-only on the profile; a keeper problem never stops or delays the session.
    $keeper = $null
    try {
        . (Join-Path $PSScriptRoot 'play_savekeeper.ps1')
        $keeper = New-SaveKeeper $user (Join-Path $play "save_history/$stamp")
        [void](Update-SaveKeeper $keeper 'before the session' -Final)
    } catch { Write-Host "Save keeper unavailable: $($_.Exception.Message)"; $keeper = $null }
    $process = Start-Process -FilePath $exe -ArgumentList $quoted -WorkingDirectory $session -PassThru
    while (-not $process.WaitForExit(2000)) {
        if ($keeper) { try { [void](Update-SaveKeeper $keeper 'changed during the session') } catch { $keeper.Pending = $null } }
    }
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    if ($keeper) { try { [void](Update-SaveKeeper $keeper 'after the session' -Final) } catch { } }
    # M18 (D-047): a save that resumes in the end-of-game hub with the campaign unfinished cannot reach the Tower
    # of the Leptys. Read-only check; the profile is not changed.
    try {
        foreach ($slot in @(Get-StrandedSlots $user)) {
            Write-Host "WARNING: save '$slot' now resumes in the end-of-game hub although the campaign is not finished."
            Write-Host "         Earlier states of this profile are under $historyText (see reports\milestone18\REPORT.md)."
        }
    } catch { }
} finally {
    foreach ($name in $testOnly) { [Environment]::SetEnvironmentVariable($name, $saved[$name]) }
    $env:R3HD_VBLANK = $savedVblank
    $env:R3HD_REVISIT = $savedRevisit
    $env:R3HD_LAYER_COORDS = $savedLayers
    $env:R3HD_WATER_LAYERS = $savedWater
    $env:R3HD_TEXTURE_ORIENT = $savedOrient
    $env:R3HD_GAMEPLAY_SUBTITLES = $savedGameplaySubs
    $env:R3HD_MODS_PLAN = $savedModsPlan
}
$ended = Get-Date

# --- summary -----------------------------------------------------------------------------------
$census = Get-LogCensus $session
$crash = Join-Path $session 'r3hd_crash.txt'
$result = [ordered]@{
    session = $stamp
    profile = $Profile
    preset = $presetLabel
    license_mode = $License
    license_mask = $licenseMask
    license_note = 'configured runtime setting; not an entitlement or ownership check'
    display = $Display
    window = $window
    render_scale = $scale
    render_target = $target
    diagnostics = $Diagnostics
    keyboard = $keyText
    pacing = $Pacing
    cursor = $Cursor
    save_clock = $SaveClock
    layer_coords = $LayerCoords
    texture_orient = $TextureOrient
    gameplay_subtitles = $GameplaySubtitles
    mods = $modsText
    started = $started.ToString('o')
    ended = $ended.ToString('o')
    seconds = [Math]::Round(($ended - $started).TotalSeconds, 1)
    exit_code = $exitCode
    exit_hex = ('{0:X8}' -f ([int64]$exitCode -band 0xFFFFFFFFL))
    clean_exit = ($exitCode -eq 0)
    crash_report = (Test-Path -LiteralPath $crash)
    save_snapshots = $(if ($keeper) { $keeper.Index } else { 0 })
    save_history = $(if ($keeper -and $keeper.Index) { $(if ($legacyPlay) { "private/play/save_history/$stamp" } else { Join-Path $play "save_history/$stamp" }) } else { $null })
    executable_sha256 = Get-FileSha256 $exe
    arguments = $arguments
    log = $census
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $session 'session.json') -Encoding UTF8

Write-Host ''
Write-Host "Session $stamp ended after $($result.seconds) s, exit code $exitCode (0x$($result.exit_hex))."
Write-Host "Licence mode: $License (configured mask $licenseMask; the title received: $(if ($census.guest_license_masks.Count) { $census.guest_license_masks -join ', ' } else { 'no query logged' }))."
Write-Host "Log: $($census.lines) lines, $($census.warning) warnings, $($census.error) errors, $($census.critical) critical, $($census.stub_imports) stubbed imports first reached."
if ($result.crash_report) { Write-Host 'CRASH RECORD:'; Get-Content -LiteralPath $crash | ForEach-Object { Write-Host "  $_" } }
elseif ($exitCode -ne 0) { Write-Host 'Abnormal exit without a crash record; the last log lines are in session.json.' }
if ($census.host_fault_codes.Count) { Write-Host "Host exceptions recorded in m2_faults.log: $($census.host_fault_codes -join ', ')" }
if ($result.save_snapshots) { Write-Host "Profile snapshots kept: $($result.save_snapshots) under $($result.save_history) (private; one per save change)" }
Write-Host "Diagnostics: $session"
Write-Host 'To bundle them: powershell -ExecutionPolicy Bypass -File tools\play.ps1 -Collect'
exit $(if ($exitCode -eq 0) { 0 } else { 1 })
