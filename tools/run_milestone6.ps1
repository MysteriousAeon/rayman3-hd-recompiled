param(
    [int]$Seconds = 420,
    [string]$Run = 'verification',
    [string]$Schedule = 'config/m5/idle.txt',
    [int]$AudioAfter = 0,
    # M8: -Play applies the human-playtest diagnostic profile (R3HD_PLAY, info-level log) to a hidden run;
    # -ExtraArgs appends runtime cvars for a bounded A/B experiment. Neither changes the hidden/XAM input path.
    [switch]$Play,
    [string[]]$ExtraArgs = @(),
    # M9 (D-032): licence mode of the hidden run. 1 = full version, the build default (the host sets bit 0, the
    # one bit the title tests); 0 = trial control (R3HD_TRIAL, runtime mask 0; reproduces the M5..M8 runs).
    # No other value is accepted, and license_mask stays refused in -ExtraArgs.
    [ValidateSet(0, 1)][int]$LicenseMask = 1,
    # M9: keep the isolated profile under private/work/m9_profiles/<name> so a later run can relaunch on it.
    [string]$UserRoot = '',
    # M13 (D-040): isolated test-only level entry. Passes the title's own developer option "-level:NAME" on the
    # guest command line (runtime setting cl); the title then starts in that level instead of its front end.
    # Hidden test runs only: tools\play.ps1 refuses cl, and cl stays refused in -ExtraArgs. Not normal progression.
    [string]$TestLevel = '',
    # G6-P77 (test only): the guest user that receives the scoped XAM schedule (R3HD_TEST_INPUT_USER). 0 = the M6
    # default (user 0; users 1-3 not connected). 1-3 = that user; user 0 then stays an idle connected pad. Hidden only.
    [ValidateSet(0, 1, 2, 3)][int]$TestInputUser = 0,
    # G6-P77 (test only): log the profile / save boundary XAM imports once per distinct call (R3HD_PROFILE_TRACE).
    [switch]$ProfileTrace,
    # G6-P79 (test only, D-328): the profile handoff prototype (R3HD_TEST_PROFILE_HANDOFF=1). Hidden runs only; off
    # unless this switch is given. Never a product setting.
    [switch]$ProfileHandoff,
    # G6-P80 (test only, D-329): user-scoped schedule events and scripted message-box answers
    # (R3HD_TEST_USER_EVENTS=1, m6_test_input.h / g6p80_test_dialog.h). Hidden runs only; off unless given.
    [switch]$UserEvents,
    # G6-P83 (D-332): select the legacy XamShowSigninUI notification (XN_SYS_SIGNINCHANGED on every call) for an A/B
    # (R3HD_SIGNIN_NOTIFY=legacy, g6p82_signin_notify.h). Off unless given: the run gets the state-change-aware default
    # and an inherited R3HD_SIGNIN_NOTIFY is cleared.
    [switch]$SigninNotifyLegacy
)
$ErrorActionPreference = 'Stop'

if ($Run -notmatch '^[A-Za-z0-9_-]+$' -or $Seconds -lt 1 -or $Seconds -gt 1500 -or $AudioAfter -lt 0) {
    throw 'Invalid bounded run'
}
if ($UserRoot -and $UserRoot -notmatch '^[A-Za-z0-9_-]+$') { throw 'UserRoot must be a simple name' }
if ($TestLevel -and $TestLevel -notmatch '^[A-Za-z0-9_]{1,24}$') { throw 'TestLevel must be a level directory name' }
if (Get-Process r3hd -ErrorAction SilentlyContinue) { throw 'Another r3hd is running' }
# M15: R3HD_HIDDEN_EXTRA (comma-separated --cvar=value list) reaches every hidden tool through the environment,
# like R3HD_GPU_WAIT; one -ExtraArgs string may also hold several settings. Same checks, recorded in run.json.
if ($env:R3HD_HIDDEN_EXTRA) { $ExtraArgs = @($ExtraArgs) + @($env:R3HD_HIDDEN_EXTRA) }
$ExtraArgs = @($ExtraArgs | ForEach-Object { $_ -split ',(?=--[a-z0-9_]+=)' } | Where-Object { $_ })
foreach ($extra in $ExtraArgs) {
    # M32: case-sensitive, so the check does not depend on the culture (a Turkish culture folds 'I' to a dotless i,
    # which a case-insensitive [A-Za-z] then refuses: --keybind_dpad_up=Numpad8,I was rejected).
    if ($extra -cnotmatch '^--[a-z0-9_]+=[A-Za-z0-9_.,-]*$') { throw "Invalid extra argument: $extra" }
    if ($extra -match '^--(license_mask|fullscreen|mnk_mode|game_data_root|user_data_root|log_file|cl)=') { throw "Extra argument not allowed in hidden runs: $extra" }
}

Add-Type @'
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

public sealed class M6ForegroundEvent {
    public uint EventTimeMs { get; set; }
    public string ObservedUtc { get; set; }
    public double ElapsedSeconds { get; set; }
    public long Hwnd { get; set; }
    public uint Pid { get; set; }
    public string ProcessName { get; set; }
}

public sealed class M6DesktopContext {
    public bool ThreadDesktopOk { get; set; }
    public bool ThreadDesktopIo { get; set; }
    public string ThreadDesktopName { get; set; }
    public bool InputDesktopOk { get; set; }
    public bool InputDesktopIo { get; set; }
    public string InputDesktopName { get; set; }
}

public sealed class M6BaselineDecision {
    public bool Allowed { get; set; }
    public string Mode { get; set; }
    public bool DesktopIsolationVerified { get; set; }
    public string RejectReason { get; set; }
}

public static class M6Focus {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr GetThreadDesktop(uint threadId);
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint desiredAccess);
    [DllImport("user32.dll", SetLastError = true)] private static extern bool CloseDesktop(IntPtr desktop);
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool GetUserObjectInformationW(IntPtr obj, int index, System.Text.StringBuilder info, int length, out int needed);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool GetUserObjectInformationW(IntPtr obj, int index, out int info, int length, out int needed);
    private const int UOI_NAME = 2;
    private const int UOI_IO = 6;
    private const uint DESKTOP_READOBJECTS = 0x0001;
    private delegate void EventProc(IntPtr hook, uint evt, IntPtr hwnd, int obj, int child, uint thread, uint time);
    [DllImport("user32.dll")] private static extern IntPtr SetWinEventHook(uint first, uint last, IntPtr mod, EventProc proc, uint pid, uint thread, uint flags);
    [DllImport("user32.dll")] private static extern bool UnhookWinEvent(IntPtr hook);
    [StructLayout(LayoutKind.Sequential)] private struct Msg {
        public IntPtr hwnd; public uint message; public UIntPtr wParam; public IntPtr lParam;
        public uint time; public int x, y; public uint priv;
    }
    [DllImport("user32.dll")] private static extern bool PeekMessage(out Msg msg, IntPtr hwnd, uint first, uint last, uint remove);

    private static bool TryGetDesktopInfo(IntPtr desktop, out bool ioActive, out string name) {
        ioActive = true;
        name = null;
        if (desktop == IntPtr.Zero) return false;
        int ioVal = 0;
        int needed = 0;
        if (!GetUserObjectInformationW(desktop, UOI_IO, out ioVal, 4, out needed)) return false;
        var sb = new System.Text.StringBuilder(256);
        if (!GetUserObjectInformationW(desktop, UOI_NAME, sb, sb.Capacity * 2, out needed)) return false;
        ioActive = (ioVal != 0);
        name = sb.ToString();
        return !string.IsNullOrEmpty(name);
    }

    public static M6DesktopContext QueryDesktopContext() {
        var ctx = new M6DesktopContext();
        bool tIo;
        string tName;
        IntPtr threadDesk = GetThreadDesktop(GetCurrentThreadId());
        if (TryGetDesktopInfo(threadDesk, out tIo, out tName)) {
            ctx.ThreadDesktopOk = true;
            ctx.ThreadDesktopIo = tIo;
            ctx.ThreadDesktopName = tName;
        }
        IntPtr inputDesk = OpenInputDesktop(0, false, DESKTOP_READOBJECTS);
        if (inputDesk != IntPtr.Zero) {
            try {
                bool iIo;
                string iName;
                if (TryGetDesktopInfo(inputDesk, out iIo, out iName)) {
                    ctx.InputDesktopOk = true;
                    ctx.InputDesktopIo = iIo;
                    ctx.InputDesktopName = iName;
                }
            } finally {
                CloseDesktop(inputDesk);
            }
        }
        return ctx;
    }

    public static bool IsThreadDesktopInputActive() {
        bool ioActive;
        string name;
        IntPtr threadDesk = GetThreadDesktop(GetCurrentThreadId());
        if (!TryGetDesktopInfo(threadDesk, out ioActive, out name)) return true; // fail closed
        return ioActive;
    }

    public static M6BaselineDecision EvaluateBaseline(IntPtr initialWindow, M6DesktopContext ctx) {
        bool isolated = ctx != null
            && ctx.ThreadDesktopOk && !ctx.ThreadDesktopIo
            && ctx.InputDesktopOk && ctx.InputDesktopIo
            && !string.IsNullOrEmpty(ctx.ThreadDesktopName)
            && !string.IsNullOrEmpty(ctx.InputDesktopName)
            && !string.Equals(ctx.ThreadDesktopName, ctx.InputDesktopName, StringComparison.OrdinalIgnoreCase);
        if (initialWindow != IntPtr.Zero) {
            return new M6BaselineDecision {
                Allowed = true,
                Mode = "foreground_window",
                DesktopIsolationVerified = isolated,
                RejectReason = null
            };
        }
        if (isolated) {
            return new M6BaselineDecision {
                Allowed = true,
                Mode = "isolated_non_input_desktop",
                DesktopIsolationVerified = true,
                RejectReason = null
            };
        }
        return new M6BaselineDecision {
            Allowed = false,
            Mode = "rejected",
            DesktopIsolationVerified = false,
            RejectReason = "No active application available for focus verification"
        };
    }

    public static readonly ConcurrentQueue<M6ForegroundEvent> Events = new ConcurrentQueue<M6ForegroundEvent>();
    public static volatile uint GamePid;
    public static volatile bool HookReady;
    public static volatile bool HookEverReady;
    public static string StartupError;
    public static string StopError;
    private static readonly ManualResetEvent Ready = new ManualResetEvent(false);
    private static Thread worker;
    private static volatile bool stop;
    private static EventProc callback;
    private static readonly Stopwatch Clock = new Stopwatch();

    public static string ProcessName(uint processId) {
        if (processId == 0) return null;
        try { using (Process p = Process.GetProcessById((int)processId)) return p.ProcessName; }
        catch { return null; }
    }

    private static void OnEvent(IntPtr h, uint evt, IntPtr hwnd, int obj, int child, uint thread, uint eventTime) {
        try {
            uint processId = 0;
            GetWindowThreadProcessId(hwnd, out processId);
            Events.Enqueue(new M6ForegroundEvent {
                EventTimeMs = eventTime,
                ObservedUtc = DateTime.UtcNow.ToString("o"),
                ElapsedSeconds = Clock.Elapsed.TotalSeconds,
                Hwnd = hwnd.ToInt64(),
                Pid = processId,
                ProcessName = ProcessName(processId)
            });
        } catch { /* A monitoring callback must never escape into user32. */ }
    }

    public static void Start() {
        M6ForegroundEvent discarded;
        while (Events.TryDequeue(out discarded)) { }
        GamePid = 0;
        HookReady = false;
        HookEverReady = false;
        StartupError = null;
        StopError = null;
        stop = false;
        Ready.Reset();
        Clock.Restart();
        worker = new Thread(delegate() {
            IntPtr hook = IntPtr.Zero;
            try {
                callback = OnEvent;
                hook = SetWinEventHook(3, 3, IntPtr.Zero, callback, 0, 0, 0);
                if (hook == IntPtr.Zero) {
                    StartupError = "SetWinEventHook(EVENT_SYSTEM_FOREGROUND) returned null";
                    Ready.Set();
                    return;
                }
                HookReady = true;
                HookEverReady = true;
                Ready.Set();
                while (!stop) {
                    Msg msg;
                    while (PeekMessage(out msg, IntPtr.Zero, 0, 0, 1)) { }
                    Thread.Sleep(5);
                }
            } catch (Exception ex) {
                StartupError = ex.ToString();
                Ready.Set();
            } finally {
                HookReady = false;
                if (hook != IntPtr.Zero && !UnhookWinEvent(hook)) StopError = "UnhookWinEvent failed";
            }
        });
        worker.IsBackground = true;
        worker.Name = "M6 foreground event monitor";
        worker.Start();
        if (!Ready.WaitOne(5000)) {
            stop = true;
            worker.Join(1000);
            throw new InvalidOperationException("Foreground event monitor did not become ready within 5 seconds");
        }
        if (!HookReady) {
            string detail = StartupError ?? "unknown WinEvent hook startup failure";
            Stop();
            throw new InvalidOperationException(detail);
        }
    }

    public static bool Stop() {
        if (worker == null) return true;
        stop = true;
        bool joined = worker.Join(5000);
        if (!joined) StopError = "Foreground event monitor did not stop within 5 seconds";
        return joined;
    }
}
'@

$repo = Split-Path -Parent $PSScriptRoot
# M46: R3HD_EXE runs another copy of the build (the LGPL DLL replacement test); default: the build tree.
$exe = if ($env:R3HD_EXE) { $env:R3HD_EXE } else { Join-Path $repo 'private/work/rex/out/build/win-amd64-release/r3hd.exe' }
$work = Join-Path $repo "private/work/m6_runs/$Run"
$userRootPath = if ($UserRoot) { Join-Path $repo "private/work/m9_profiles/$UserRoot" } else { Join-Path $work 'user' }
$licenseMode = if ($LicenseMask -eq 1) { 'full' } else { 'trial' }
$frameRequestPath = Join-Path $work 'frame.request'
$runtimeStarted = $null
$gameProcess = $null
$monitorStarted = $false
$monitorStartAttempted = $false
$runDirectoryCreated = $false
$forcedTermination = $false
$closeRequested = $false
$samples = New-Object 'System.Collections.Generic.List[object]'
$focusEvents = @()
$intervals = @()
$failureInfo = $null
$exitCode = $null
$initialForeground = $null
$finalForeground = $null
$desktopContext = $null
$baselineDecision = $null
$desktopBecameActive = $false
$gameFocusEvents = 0
$gameFocusSamples = 0
$sampleCount = 0
$pollCount = 0
$hookStopClean = $null
$arguments = @()
$watch = [System.Diagnostics.Stopwatch]::new()
$names = @('R3HD_NONINTRUSIVE', 'R3HD_TEST_SECONDS', 'R3HD_INPUT_SCHEDULE', 'R3HD_M5_CAPTURE', 'R3HD_FRAME_REQUEST', 'R3HD_AUDIO_CAPTURE', 'R3HD_AUDIO_AFTER', 'R3HD_PLAY', 'R3HD_TRIAL', 'R3HD_TEST_INPUT_USER', 'R3HD_PROFILE_TRACE', 'R3HD_TEST_PROFILE_HANDOFF', 'R3HD_TEST_USER_EVENTS', 'R3HD_SIGNIN_NOTIFY')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name) }

function ConvertTo-WindowsArgument([string]$Value) {
    # Encode one argv token using the CommandLineToArgvW backslash/quote rules.
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $slashes = 0
    foreach ($ch in $Value.ToCharArray()) {
        if ($ch -eq '\') { $slashes++; continue }
        if ($ch -eq '"') {
            [void]$builder.Append(('\' * (2 * $slashes + 1)))
            [void]$builder.Append('"')
        } else {
            if ($slashes) { [void]$builder.Append(('\' * $slashes)) }
            [void]$builder.Append($ch)
        }
        $slashes = 0
    }
    if ($slashes) { [void]$builder.Append(('\' * (2 * $slashes))) }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Get-FileSha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}

function Get-ForegroundIdentity([IntPtr]$Window) {
    [uint32]$observedPid = 0
    if ($Window -ne [IntPtr]::Zero) { [void][M6Focus]::GetWindowThreadProcessId($Window, [ref]$observedPid) }
    return [pscustomobject]@{
        hwnd = $Window.ToInt64()
        pid = $observedPid
        process = [M6Focus]::ProcessName($observedPid)
    }
}

function Build-ForegroundIntervals($ForegroundSamples, [double]$EndElapsedMs, [string]$EndUtc) {
    $result = New-Object 'System.Collections.Generic.List[object]'
    $current = $null
    foreach ($sample in $ForegroundSamples) {
        $identity = '{0}:{1}:{2}' -f $sample.hwnd, $sample.pid, $sample.process
        if ($null -eq $current -or $current.identity -ne $identity) {
            if ($null -ne $current) {
                $current.interval.end_elapsed_ms = $sample.elapsed_ms
                $current.interval.end_utc = $sample.utc
                $current.interval.duration_ms = $sample.elapsed_ms - $current.interval.start_elapsed_ms
                $result.Add($current.interval)
            }
            $interval = [ordered]@{
                start_elapsed_ms = $sample.elapsed_ms
                end_elapsed_ms = $null
                duration_ms = $null
                start_utc = $sample.utc
                end_utc = $null
                hwnd = $sample.hwnd
                pid = $sample.pid
                process = $sample.process
                sample_count = 1
            }
            $current = @{ identity = $identity; interval = $interval }
        } else {
            $current.interval.sample_count++
        }
    }
    if ($null -ne $current) {
        $current.interval.end_elapsed_ms = $EndElapsedMs
        $current.interval.end_utc = $EndUtc
        $current.interval.duration_ms = $EndElapsedMs - $current.interval.start_elapsed_ms
        $result.Add($current.interval)
    }
    return ,$result.ToArray()
}

try {
    if (Test-Path -LiteralPath $work) { throw 'Run already exists' }
    New-Item -ItemType Directory -Path $work | Out-Null
    $runDirectoryCreated = $true
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Game executable not found: $exe" }
    # M23 (D-053): fail closed. A hidden run must not be able to drive a controller's motors: refuse to launch
    # unless a binary of this build carries the haptics safeguard (tools\m23_haptics.h logs with this text).
    $hapticsGuard = $false
    foreach ($binary in @(Get-ChildItem -LiteralPath (Split-Path -Parent $exe) -File | Where-Object { $_.Extension -in '.exe', '.dll' -and $_.Name -match '^(r3hd|rex)' })) {
        $text = [System.Text.Encoding]::GetEncoding(28591).GetString([System.IO.File]::ReadAllBytes($binary.FullName))
        if ($text.Contains('M23 haptics policy={} physical_pad_drivers={}')) { $hapticsGuard = $true; break }
    }
    $text = $null
    if (-not $hapticsGuard) { throw 'Hidden run refused: this build has no controller-vibration safeguard (D-053). Rebuild with tools\build_milestone8.bat.' }
    $schedulePath = if ([System.IO.Path]::IsPathRooted($Schedule)) { $Schedule } else { Join-Path $repo $Schedule }
    if (-not (Test-Path -LiteralPath $schedulePath -PathType Leaf)) { throw "Input schedule not found: $schedulePath" }

    $scheduleCopy = Join-Path $work 'schedule.txt'
    Copy-Item -LiteralPath $schedulePath -Destination $scheduleCopy
    [System.IO.File]::WriteAllText($frameRequestPath, "0`n", [System.Text.Encoding]::ASCII)

    $initialWindow = [M6Focus]::GetForegroundWindow()
    $desktopContext = [M6Focus]::QueryDesktopContext()
    $baselineDecision = [M6Focus]::EvaluateBaseline($initialWindow, $desktopContext)
    if (-not $baselineDecision.Allowed) { throw $baselineDecision.RejectReason }
    if ($initialWindow -ne [IntPtr]::Zero) { $initialForeground = Get-ForegroundIdentity $initialWindow }
    $monitorStartAttempted = $true
    [M6Focus]::Start()
    $monitorStarted = $true

    $env:R3HD_NONINTRUSIVE = '1'
    $env:R3HD_TEST_SECONDS = "$Seconds"
    $env:R3HD_INPUT_SCHEDULE = $scheduleCopy
    [Environment]::SetEnvironmentVariable('R3HD_M5_CAPTURE', $null)
    $env:R3HD_FRAME_REQUEST = $frameRequestPath
    $env:R3HD_AUDIO_CAPTURE = Join-Path $work 'audio.f32'
    $env:R3HD_AUDIO_AFTER = "$AudioAfter"
    if ($Play) { $env:R3HD_PLAY = '1' } else { [Environment]::SetEnvironmentVariable('R3HD_PLAY', $null) }
    if ($LicenseMask -eq 0) { $env:R3HD_TRIAL = '1' } else { [Environment]::SetEnvironmentVariable('R3HD_TRIAL', $null) }
    if ($TestInputUser -ne 0) { $env:R3HD_TEST_INPUT_USER = "$TestInputUser" } else { [Environment]::SetEnvironmentVariable('R3HD_TEST_INPUT_USER', $null) }
    if ($ProfileTrace) { $env:R3HD_PROFILE_TRACE = '1' } else { [Environment]::SetEnvironmentVariable('R3HD_PROFILE_TRACE', $null) }
    if ($ProfileHandoff) { $env:R3HD_TEST_PROFILE_HANDOFF = '1' } else { [Environment]::SetEnvironmentVariable('R3HD_TEST_PROFILE_HANDOFF', $null) }
    if ($UserEvents) { $env:R3HD_TEST_USER_EVENTS = '1' } else { [Environment]::SetEnvironmentVariable('R3HD_TEST_USER_EVENTS', $null) }
    if ($SigninNotifyLegacy) { $env:R3HD_SIGNIN_NOTIFY = 'legacy' } else { [Environment]::SetEnvironmentVariable('R3HD_SIGNIN_NOTIFY', $null) }
    $logLevel = if ($Play) { 'info' } else { 'debug' }

    $arguments = @(
        "--game_data_root=$(if ($env:R3HD_GAME_DIR) { $env:R3HD_GAME_DIR } else { Join-Path $repo 'private/extracted/5841123F' })",
        "--user_data_root=$userRootPath",
        "--cache_root=$(Join-Path $repo 'private/work/m2_cache')",
        '--gpu_plugin=xenos', "--log_level=$logLevel", '--log_flush_interval=1',
        "--log_file=$(Join-Path $work 'runtime.log')", '--mnk_mode=false', '--fullscreen=false'
    ) + $ExtraArgs
    if ($TestLevel) { $arguments += "--cl=-level:$TestLevel" }
    $quotedArguments = ($arguments | ForEach-Object { ConvertTo-WindowsArgument ([string]$_) }) -join ' '
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $exe
    $startInfo.Arguments = $quotedArguments
    $startInfo.WorkingDirectory = $work
    $startInfo.UseShellExecute = $false
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $runtimeStarted = [DateTime]::UtcNow
    $watch.Start()
    $samples.Add([pscustomobject]@{
        elapsed_ms = 0.0
        utc = $runtimeStarted.ToString('o')
        kind = 'baseline'
        hwnd = $(if ($initialForeground) { $initialForeground.hwnd } else { 0 })
        pid = $(if ($initialForeground) { $initialForeground.pid } else { [uint32]0 })
        process = $(if ($initialForeground) { $initialForeground.process } else { $null })
    })
    $sampleCount++
    $gameProcess = [System.Diagnostics.Process]::Start($startInfo)
    if ($null -eq $gameProcess) { throw 'Game process creation returned null' }

    [M6Focus]::GamePid = [uint32]$gameProcess.Id
    $processInfo = [ordered]@{ pid = $gameProcess.Id; process = $gameProcess.ProcessName; work = $work; started_utc = $runtimeStarted.ToString('o') }
    $processInfo | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $work 'process.json') -Encoding UTF8

    $deadline = $watch.Elapsed.TotalSeconds + $Seconds + 30
    $cancelRequested = $false
    while (-not $gameProcess.HasExited -and $watch.Elapsed.TotalSeconds -lt $deadline) {
        if (Test-Path -LiteralPath (Join-Path $work 'cancel.request')) {
            $cancelRequested = $true
            break
        }
        $window = [M6Focus]::GetForegroundWindow()
        $identity = Get-ForegroundIdentity $window
        $sample = [pscustomobject]@{
            elapsed_ms = [Math]::Round($watch.Elapsed.TotalMilliseconds, 1)
            utc = [DateTime]::UtcNow.ToString('o')
            kind = 'poll'
            hwnd = $identity.hwnd
            pid = $identity.pid
            process = $identity.process
        }
        $samples.Add($sample)
        $sampleCount++
        $pollCount++
        if ($identity.pid -eq $gameProcess.Id) { $gameFocusSamples++ }
        if ($baselineDecision.Mode -eq 'isolated_non_input_desktop' -and [M6Focus]::IsThreadDesktopInputActive()) {
            $desktopBecameActive = $true
            if ($null -eq $failureInfo) {
                $failureInfo = [ordered]@{ message = 'NONINTRUSIVE FAILURE: isolated thread desktop became active input desktop'; kind = 'desktop_became_active' }
            }
            break
        }
        Start-Sleep -Milliseconds 100
        $gameProcess.Refresh()
    }
    if (-not $gameProcess.HasExited -and $cancelRequested) {
        if ($null -eq $failureInfo) { $failureInfo = [ordered]@{ message = 'Pilot requested bounded run cancellation'; kind = 'pilot_cancelled' } }
        try { $closeRequested = $gameProcess.CloseMainWindow() } catch { $closeRequested = $false }
        if ($closeRequested) { [void]$gameProcess.WaitForExit(5000) }
        $gameProcess.Refresh()
        if (-not $gameProcess.HasExited) {
            $forcedTermination = $true
            Stop-Process -Id $gameProcess.Id -Force -ErrorAction Stop
            [void]$gameProcess.WaitForExit(5000)
        }
    } elseif (-not $gameProcess.HasExited) {
        if ($null -eq $failureInfo) { $failureInfo = [ordered]@{ message = 'Game exceeded the bounded runtime deadline'; kind = 'timeout' } }
        try { $closeRequested = $gameProcess.CloseMainWindow() } catch { $closeRequested = $false }
        if ($closeRequested) { [void]$gameProcess.WaitForExit(5000) }
        $gameProcess.Refresh()
        if (-not $gameProcess.HasExited) {
            $forcedTermination = $true
            Stop-Process -Id $gameProcess.Id -Force -ErrorAction Stop
            [void]$gameProcess.WaitForExit(5000)
        }
    }
    $gameProcess.Refresh()
    if ($gameProcess.HasExited) { $exitCode = $gameProcess.ExitCode }
    if ($null -ne $exitCode -and $exitCode -ne 0 -and $null -eq $failureInfo) {
        $failureInfo = [ordered]@{ message = "Game process exited with code $exitCode"; kind = 'runtime_exit' }
    }
} catch {
    $failureInfo = [ordered]@{
        message = $_.Exception.Message
        kind = 'exception'
        type = $_.Exception.GetType().FullName
        error_id = $_.FullyQualifiedErrorId
        script_stack = $_.ScriptStackTrace
    }
} finally {
    if ($null -ne $gameProcess) {
        try {
            $gameProcess.Refresh()
            if (-not $gameProcess.HasExited) {
                try { $closeRequested = $gameProcess.CloseMainWindow() } catch { $closeRequested = $false }
                if ($closeRequested) { [void]$gameProcess.WaitForExit(5000) }
                $gameProcess.Refresh()
                if (-not $gameProcess.HasExited) {
                    $forcedTermination = $true
                    Stop-Process -Id $gameProcess.Id -Force -ErrorAction SilentlyContinue
                    [void]$gameProcess.WaitForExit(5000)
                }
            }
            $gameProcess.Refresh()
            if ($gameProcess.HasExited) { $exitCode = $gameProcess.ExitCode }
        } catch {
            if ($null -eq $failureInfo) {
                $failureInfo = [ordered]@{ message = $_.Exception.Message; kind = 'cleanup_exception'; type = $_.Exception.GetType().FullName }
            }
        }
    }
    if ($monitorStarted) {
        $hookStopClean = [M6Focus]::Stop()
        $focusEvents = @([M6Focus]::Events.ToArray())
        if ($gameProcess) { $gameFocusEvents = @($focusEvents | Where-Object { $_.Pid -eq $gameProcess.Id }).Count }
        if ($gameFocusEvents -gt 0 -and $null -eq $failureInfo) {
            $failureInfo = [ordered]@{ message = 'NONINTRUSIVE FAILURE: a foreground event belonged to the game process'; kind = 'game_foreground' }
        }
        if ($gameFocusSamples -gt 0 -and $null -eq $failureInfo) {
            $failureInfo = [ordered]@{ message = 'NONINTRUSIVE FAILURE: a 100 ms foreground sample belonged to the game process'; kind = 'game_foreground' }
        }
    }
    if ($watch.IsRunning) { $watch.Stop() }
    if ($runDirectoryCreated) {
        $finalWindow = [M6Focus]::GetForegroundWindow()
        if ($finalWindow -ne [IntPtr]::Zero) { $finalForeground = Get-ForegroundIdentity $finalWindow }
        $endUtc = [DateTime]::UtcNow.ToString('o')
        $endElapsedMs = $watch.Elapsed.TotalMilliseconds
        $intervals = Build-ForegroundIntervals $samples $endElapsedMs $endUtc
        $result = [ordered]@{
            mode = 'hidden-XAM'
            play_profile = [bool]$Play
            extra_arguments = $ExtraArgs
            license_mode = $licenseMode
            test_level = if ($TestLevel) { $TestLevel } else { $null }
            license_mask = $LicenseMask
            user_root = $userRootPath
            test_input_user = $TestInputUser
            profile_trace = [bool]$ProfileTrace
            profile_handoff = [bool]$ProfileHandoff
            user_events = [bool]$UserEvents
            signin_notify_on_change = -not [bool]$SigninNotifyLegacy
            signin_notify = $(if ($SigninNotifyLegacy) { 'legacy' } else { 'on_change' })
            started_utc = $(if ($runtimeStarted) { $runtimeStarted.ToString('o') } else { $null })
            finished_utc = $endUtc
            initial_foreground = $initialForeground
            final_foreground = $finalForeground
            initial_foreground_unchanged = ($null -ne $initialForeground -and $null -ne $finalForeground -and $initialForeground.hwnd -eq $finalForeground.hwnd -and $initialForeground.pid -eq $finalForeground.pid)
            focus_baseline_mode = $(if ($baselineDecision) { $baselineDecision.Mode } else { $null })
            desktop_isolation_verified = $(if ($baselineDecision) { $baselineDecision.DesktopIsolationVerified } else { $false })
            thread_desktop_io = $(if ($desktopContext -and $desktopContext.ThreadDesktopOk) { $desktopContext.ThreadDesktopIo } else { $null })
            input_desktop_accessible = $(if ($desktopContext) { $desktopContext.InputDesktopOk } else { $false })
            desktop_became_active = $desktopBecameActive
            foreground_events = $focusEvents
            foreground_intervals = $intervals
            foreground_samples = $samples.ToArray()
            interval_sample_ms = 100
            sample_count = $sampleCount
            poll_count = $pollCount
            sample_schedule = 'baseline plus foreground polls every 100 ms'
            game_foreground_events = $gameFocusEvents
            game_foreground_samples = $gameFocusSamples
            monitor_hook_ready = [M6Focus]::HookEverReady
            monitor_start_attempted = $monitorStartAttempted
            monitor_start_error = $(if ($monitorStartAttempted) { [M6Focus]::StartupError } else { $null })
            monitor_stop_clean = $hookStopClean
            monitor_stop_error = [M6Focus]::StopError
            close_requested = $closeRequested
            forced_termination = $forcedTermination
            exit_code = $exitCode
            seconds = $Seconds
            audio_after = $AudioAfter
            frame_request_path = $frameRequestPath
            frame_request_initial_id = 0
            frame_capture_max_readbacks = 8
            input_schedule = $(if (Test-Path -LiteralPath (Join-Path $work 'schedule.txt')) { Get-FileSha256 (Join-Path $work 'schedule.txt') } else { $null })
            arguments = $arguments
            executable_sha256 = $(if (Test-Path -LiteralPath $exe -PathType Leaf) { Get-FileSha256 $exe } else { $null })
            error = $failureInfo
        }
        try {
            $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $work 'run.json') -Encoding UTF8
            $result | ConvertTo-Json -Depth 8
        } catch {
            if ($null -eq $failureInfo) { $failureInfo = [ordered]@{ message = $_.Exception.Message; kind = 'report_write_exception' } }
            Write-Error "Unable to write run.json: $($_.Exception.Message)"
        }
    }
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name]) }
}

if ($null -ne $failureInfo) { throw [System.InvalidOperationException]::new([string]$failureInfo.message) }
