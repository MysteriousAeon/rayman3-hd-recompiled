; M29 (D-066): Inno Setup front end of the PRIVATE installer prototype of Rayman 3 HD Recompiled.
; M30 (D-067): the wizard asks only what installing needs (folder, game package, a starting profile); display and
; graphics settings belong to the Settings launcher (app\r3hd_launcher.exe), which the Finish page can open.
;
; The wizard collects the choices; tools\r3hd_installer.py (run from the extracted payload with its bundled Python)
; does all the work: payload integrity, game-data identity and extraction through r3hd_intake.py, the preset through
; r3hd_settings.py, the transactional install / update / repair, and the uninstall of installer-owned files only.
; The installer carries the staged payload (tools\r3hd_stage.py) and never any game data.
;
; Compile (private; never publish the output):
;   ISCC.exe /DPayloadDir=<stage>\payload /DOutputDir=<out> tools\installer\r3hd_setup.iss
; Silent / test use (no desktop interaction):
;   setup.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR=<home> /PACKAGE=<package file> [/PRESET=vanilla|hdplus|custom]
;             [/SET="key=value key=value"] [/VERIFYDATA=1] [/MERGETASKS="!desktopicon"] [/R3HDTEST=1] [/LOG=<file>]
;   /R3HDTEST=1 writes no uninstall registry entry and offers no launch (synthetic test folders). Its shortcuts go only
;   to the folders named by /STARTMENUDIR=<dir> and /DESKTOPDIR=<dir> (none without them); /CANCELAT=<permille> makes
;   the progress page request cancellation itself at that point (the same path as its Cancel button).
;   unins000.exe /VERYSILENT /SUPPRESSMSGBOXES [/REMOVEUSERDATA=1]
; M31 (D-068): the engine's real progress (R3HD_STEP / R3HD_PROGRESS lines) drives a progress page with a time
; estimate and a Cancel button that stops the engine before its commit (nothing changed); an optional desktop shortcut
; (checked by default; a declined or deleted one is not recreated by a repair or an update: the engine records the
; choice); the project icon (tools\make_r3hd_icon.py) for setup, shortcuts and the uninstall entry.
; M32 (D-069): the wizard stays responsive while the engine works. Inno Setup's Exec family disables the wizard for the
; whole wait (TWindowDisabler: it still paints, so the progress moved, but it could not be dragged and the Cancel
; button could not be clicked); the output callback enables it again, while Inno keeps pumping messages and owning the
; process handle. An optional Settings desktop shortcut (checked by default, the launcher's second icon: a gear) is
; recorded and treated like the Play shortcut.
; M48-P (D-087): the private PLAYTEST setup, compiled with /DBundledMod=<mod zip> /DFlagDir=<tools\m48p_flags.py output>
; (tools\m48p_build.py). Without BundledMod this script builds the English-only private setup exactly as before.
;   - Turkish and English (Inno's own Turkish.isl + r3hd_tr.isl; every string of this script is a custom message in
;     r3hd_en.isl / r3hd_tr.isl). The default follows the Windows UI language (English otherwise). The first page is
;     only the language choice: two flag buttons with a text button under each (mouse and keyboard); by the person's
;     choice (M48-P review) the wizard shows no notice or disclaimer page. Inno Setup cannot switch a running wizard's
;     language, so a different choice starts this setup again with /LANG and the folder, package and options chosen
;     so far, and closes the current wizard without a prompt (nothing was changed yet). Setup refuses to execute (or
;     copy) its own file before the installation starts (access denied), so the new instance is started through a
;     hidden "cmd /c start".
;   - The bundled Turkish translation is applied after the install by tools\r3hd_bundled_mods.py (M49 policy below:
;     a fresh installation follows the setup language; an existing one keeps its on / off choice, its order and any
;     newer version, and never gets a missing or removed copy back). /TURKISH=0|1|2|3 overrides it (tests).
;   - Gameplay subtitles (D-090): no wizard page; a preference set in Settings > Corrections. The engine turns them on
;     for a fresh HD+ installation (off for Vanilla and Custom on Vanilla); an existing one keeps its value.
;     /GAMEPLAYSUBS=all|original sets them explicitly (tests).
;   - Test builds only: /DDpiProxyFont=<pt> (dialog font size: the wizard scales by font base units as at a higher
;     DPI) and /DFastCompression.

#ifndef PayloadDir
  #error Define PayloadDir: ISCC /DPayloadDir=<stage>\payload
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef IconFile
  ; written by tools\launcher\build_launcher.bat (tools\make_r3hd_icon.py; a build output, never committed)
  #define IconFile "..\..\private\work\launcher\r3hd.ico"
#endif
; M49 (D-088): consumer presentation. One product name and version (config\release\payload.json); the language of a
; FRESH installation decides the bundled Turkish translation (Turkish: installed and turned on; English: not installed,
; its .zip is left in {app}\extras for Settings > Mods). An EXISTING installation keeps what it has: an installed copy
; is updated in place (on / off and order kept, a newer one kept), a missing or removed one is not added (--want 3).
; Silent: /TURKISH=0|1|2|3 overrides that choice (tests).
#define AppVersion "1.0.1"
#define AppTitle "Rayman 3 HD Recompiled"
#ifdef BundledMod
  #define Playtest
  #ifndef FlagDir
    #error Define FlagDir: ISCC /DFlagDir=<tools\m48p_flags.py output>
  #endif
  #define BundledModFile ExtractFileName(BundledMod)
  #define OutputName "Rayman3HDRecompiled-" + AppVersion + "-setup"
#else
  #define OutputName "Rayman3HDRecomp-" + AppVersion + "-setup"
  #define BundledModFile ""
#endif

[Setup]
AppId={{6F2C9A41-7D3B-4E58-B1A2-5841123F0029}
AppName={#AppTitle}
AppVersion={#AppVersion}
AppVerName=Rayman 3 HD Recompiled {#AppVersion}
AppPublisher=Rayman 3 HD Recompiled
#ifdef Playtest
WizardSizePercent=110
#endif
DefaultDirName={localappdata}\Rayman3HDRecomp
; M48-P: always show the folder page. Inno's default (auto) hides it when this AppId has an uninstall entry, and then
; the folder checks below never ran: the payload was not unpacked and the package check failed (exit code -1).
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
#ifdef FastCompression
Compression=lzma2/fast
SolidCompression=no
#else
Compression=lzma2/max
SolidCompression=yes
#endif
WizardStyle=modern
UsePreviousAppDir=yes
DirExistsWarning=no
AppendDefaultDirName=no
CreateUninstallRegKey=not IsTestMode
UninstallDisplayName={#AppTitle}
UninstallDisplayIcon={app}\app\r3hd_launcher.exe
; The Settings launcher holds this mutex (tools\launcher\r3hd_launcher.cpp): setup and uninstall ask to close it.
AppMutex=Rayman3HDRecompLauncher
SetupLogging=yes
DisableReadyPage=no
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage
SetupIconFile={#IconFile}
; The desktop shortcut choice is the engine's record (installer.json), not Inno Setup's registry memory.
UsePreviousTasks=no

[Languages]
; The first entry is the default when the Windows UI language matches none.
Name: "en"; MessagesFile: "compiler:Default.isl,r3hd_en.isl"
#ifdef Playtest
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl,r3hd_tr.isl"
#endif

#ifdef DpiProxyFont
[LangOptions]
DialogFontSize={#DpiProxyFont}
#endif

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{tmp}\payload"; Flags: dontcopy recursesubdirs
#ifdef Playtest
Source: "{#BundledMod}"; Flags: dontcopy
Source: "{#FlagDir}\flag_*.png"; Flags: dontcopy
; M49: the Turkish translation stays installable later (Settings > Mods > Install .zip); removed with the program.
Source: "{#BundledMod}"; DestDir: "{app}\extras"; Flags: ignoreversion
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; GroupDescription: "{cm:TaskGroup}"
Name: "settingsicon"; Description: "{cm:TaskSettings}"; GroupDescription: "{cm:TaskGroup}"

[Icons]
; Play: the title thumbnail of the person's own package, made locally by the engine (data\play_icon.ico, never
; shipped); without it the launcher's icon. Settings keeps its own (gear) icon.
Name: "{code:MenuDir}\Rayman 3 HD Recompiled"; Filename: "{app}\app\r3hd_launcher.exe"; Parameters: "--play"; WorkingDir: "{app}"; Comment: "{cm:PlayComment}"; Check: MenuShortcuts and not HasPlayIcon; AppUserModelID: "Rayman3HDRecompiled.Game"
Name: "{code:MenuDir}\Rayman 3 HD Recompiled"; Filename: "{app}\app\r3hd_launcher.exe"; Parameters: "--play"; WorkingDir: "{app}"; Comment: "{cm:PlayComment}"; IconFilename: "{app}\data\play_icon.ico"; Check: MenuShortcuts and HasPlayIcon; AppUserModelID: "Rayman3HDRecompiled.Game"
Name: "{code:MenuDir}\Rayman 3 HD Recompiled - Settings"; Filename: "{app}\app\r3hd_launcher.exe"; WorkingDir: "{app}"; Comment: "{cm:SettingsComment}"; IconFilename: "{app}\app\r3hd_launcher.exe"; IconIndex: 1; Check: MenuShortcuts; AppUserModelID: "Rayman3HDRecompiled.Settings"
Name: "{code:MenuDir}\Rayman 3 HD Recompiled - Uninstall"; Filename: "{uninstallexe}"; Check: MenuShortcuts
Name: "{code:DesktopDir}\Rayman 3 HD Recompiled"; Filename: "{app}\app\r3hd_launcher.exe"; Parameters: "--play"; WorkingDir: "{app}"; Comment: "{cm:PlayComment}"; Check: DesktopShortcut and not HasPlayIcon; AppUserModelID: "Rayman3HDRecompiled.Game"
Name: "{code:DesktopDir}\Rayman 3 HD Recompiled"; Filename: "{app}\app\r3hd_launcher.exe"; Parameters: "--play"; WorkingDir: "{app}"; Comment: "{cm:PlayComment}"; IconFilename: "{app}\data\play_icon.ico"; Check: DesktopShortcut and HasPlayIcon; AppUserModelID: "Rayman3HDRecompiled.Game"
Name: "{code:DesktopDir}\Rayman 3 HD Recompiled - Settings"; Filename: "{app}\app\r3hd_launcher.exe"; WorkingDir: "{app}"; Comment: "{cm:SettingsComment}"; IconFilename: "{app}\app\r3hd_launcher.exe"; IconIndex: 1; Check: SettingsShortcut; AppUserModelID: "Rayman3HDRecompiled.Settings"

[Run]
; M49: two independent boxes on the Finish page, run in this order only after Finish: the game (checked), then Settings
; (unchecked). The game is started first, so with both ticked Settings opens beside the starting game. Silent runs
; start nothing (skipifsilent); a cancelled setup never reaches Finish.
Filename: "{app}\app\r3hd_launcher.exe"; Parameters: "--play"; Description: "{cm:RunPlay}"; Flags: postinstall nowait skipifsilent; Check: not IsTestMode
Filename: "{app}\app\r3hd_launcher.exe"; Description: "{cm:RunSettings}"; Flags: postinstall nowait skipifsilent unchecked; Check: not IsTestMode
; Test mode (/R3HDTEST=1, a private desktop): the same boxes run the installed launcher without any window (play.ps1
; -DryRun through --play --dry-run --no-ui; the Settings model through --no-ui); their output goes to the setup log.
Filename: "{app}\app\r3hd_launcher.exe"; Parameters: "--play --dry-run --no-ui"; Description: "{cm:RunPlay}"; Flags: postinstall skipifsilent runhidden waituntilterminated logoutput runascurrentuser; Check: IsTestMode
Filename: "{app}\app\r3hd_launcher.exe"; Parameters: "--no-ui"; Description: "{cm:RunSettings}"; Flags: postinstall skipifsilent unchecked runhidden waituntilterminated logoutput runascurrentuser; Check: IsTestMode

[InstallDelete]
; M31: the desktop shortcut this installer made earlier, when the person now declines it.
Type: files; Name: "{code:DesktopDir}\Rayman 3 HD Recompiled.lnk"; Check: RemoveDeclinedDesktop
; M32: the same for the Settings desktop shortcut.
Type: files; Name: "{code:DesktopDir}\Rayman 3 HD Recompiled - Settings.lnk"; Check: RemoveDeclinedSettings
#ifdef Playtest
; D-108: an earlier setup's bundled translation .zip (1.0.0); this setup copies its own afterwards.
Type: files; Name: "{app}\extras\rayman3hd-turkish-*.zip"
#endif

[UninstallDelete]
; app\ holds the engine that the uninstaller runs, so it is removed after the engine has removed everything else.
Type: filesandordirs; Name: "{app}\app"
; The folder itself only when nothing is left in it (saves and settings stay unless the person chose otherwise).
Type: dirifempty; Name: "{app}"

[Code]
var
  PackagePage: TInputFileWizardPage;
  PresetPage: TInputOptionWizardPage;
  VerifyBox: TNewCheckBox;
  PayloadReady, Installed: Boolean;
  SourceRelease, SourceName: String;
  { M31: the engine's recorded desktop shortcut choice of an existing installation: '1', '0' or '' (none recorded) }
  RecordedDesktop: String;
  { M32: the same record for the Settings desktop shortcut }
  RecordedSettings: String;
  TasksPrepared: Boolean;
  { M31: the progress page of the engine run }
  ProgressPage: TOutputProgressWizardPage;
  CancelButton: TNewButton;
  EngineRunning, CancelRequested, Committing: Boolean;
  StepText, CancelFile: String;
  CancelAt, LastPermille: Integer;
  { M32: the wizard buttons' state before the engine run }
  NextWasEnabled, BackWasEnabled: Boolean;
  { M48-P: the playtest setup }
  LangPage: TWizardPage;
  LangTrButton, LangEnButton: TNewButton;
  LangTrFlag, LangEnFlag: TBitmapButton;
  Switching, PresetVisited: Boolean;
  InstalledSubs, TurkishAction, TurkishInstalledVersion, TurkishInstalledEnabled: String;
  TurkishOutcome, SubsOutcome, PostWarnings: String;
  { M48-P: the folder whose checks ran (payload unpacked, installation detected, preflight) }
  FolderChecked: String;

{ M32 (D-069): Win32 calls for the responsive wait (no structures, handles only). }
function EnableWindow(hWnd: HWND; bEnable: BOOL): BOOL; external 'EnableWindow@user32.dll stdcall';
function IsWindowEnabled(hWnd: HWND): BOOL; external 'IsWindowEnabled@user32.dll stdcall';

function IsTestMode: Boolean;
begin
  Result := ExpandConstant('{param:R3HDTEST|0}') = '1';
end;

function IsPlaytest: Boolean;
begin
#ifdef Playtest
  Result := True;
#else
  Result := False;
#endif
end;

{ M31: shortcut folders. A test run (/R3HDTEST=1) writes shortcuts only into the folders its parameters name. }
function MenuDir(Param: String): String;
begin
  if IsTestMode then Result := ExpandConstant('{param:STARTMENUDIR|}') else Result := ExpandConstant('{userprograms}');
end;

function DesktopDir(Param: String): String;
begin
  if IsTestMode then Result := ExpandConstant('{param:DESKTOPDIR|}') else Result := ExpandConstant('{userdesktop}');
end;

function MenuShortcuts: Boolean;
begin
  Result := MenuDir('') <> '';
end;

function SettingsLink: String;
begin
  Result := AddBackslash(DesktopDir('')) + 'Rayman 3 HD Recompiled - Settings.lnk';
end;

{ M32: the Settings desktop shortcut, chosen and recorded like the Play one (checked on fresh installs). }
function SettingsShortcut: Boolean;
begin
  if WizardSilent and (ExpandConstant('{param:TASKS|}') = '') and (ExpandConstant('{param:MERGETASKS|}') = '')
     and (RecordedSettings <> '') then
    Result := RecordedSettings = '1'
  else
    Result := WizardIsTaskSelected('settingsicon');
  Result := Result and (DesktopDir('') <> '');
end;

function DesktopLink: String;
begin
  Result := AddBackslash(DesktopDir('')) + 'Rayman 3 HD Recompiled.lnk';
end;

{ The desktop shortcut is made when the person keeps the task checked. A silent run without /TASKS or /MERGETASKS
  follows the installation's record, so a repair or an update never brings back a declined (or deleted) shortcut. }
function DesktopShortcut: Boolean;
begin
  if WizardSilent and (ExpandConstant('{param:TASKS|}') = '') and (ExpandConstant('{param:MERGETASKS|}') = '')
     and (RecordedDesktop <> '') then
    Result := RecordedDesktop = '1'
  else
    Result := WizardIsTaskSelected('desktopicon');
  Result := Result and (DesktopDir('') <> '');
end;

function PayloadPath(const Rel: String): String;
begin
  Result := ExpandConstant('{tmp}\payload\') + Rel;
end;

function ResultValue(const FileName, Key: String): String;
var
  Lines: TArrayOfString;
  I: Integer;
  S: String;
begin
  Result := '';
  if not LoadStringsFromFile(FileName, Lines) then Exit;
  for I := 0 to GetArrayLength(Lines) - 1 do begin
    S := Lines[I];
    if (Length(S) > 0) and (Ord(S[1]) = $FEFF) then Delete(S, 1, 1);
    if Copy(S, 1, Length(Key) + 1) = Key + '=' then begin
      Result := Copy(S, Length(Key) + 2, Length(S));
      Exit;
    end;
  end;
end;

{ Runs the engine hidden and waits; returns its exit code (-1 if it could not start). }
function RunEngine(const Args, ResultFile: String): Integer;
var
  Code: Integer;
begin
  DeleteFile(ResultFile);
  if not Exec(PayloadPath('app\python\python.exe'),
              '-B "' + PayloadPath('app\tools\r3hd_installer.py') + '" ' + Args + ' --result-file "' + ResultFile + '"',
              ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, Code) then
    Code := -1;
  Log('engine: ' + Args + ' -> ' + IntToStr(Code));
  Result := Code;
end;

function EngineMessage(const ResultFile: String; Code: Integer): String;
begin
  Result := ResultValue(ResultFile, 'MESSAGE');
  if Result = '' then Result := FmtMessage(CustomMessage('EngineFailed'), [IntToStr(Code)]);
end;

{ --- M31: progress of the install run ------------------------------------------------------------------------- }

function NextField(var S: String): String;
var
  P: Integer;
begin
  S := Trim(S);
  P := Pos(' ', S);
  if P = 0 then begin
    Result := S; S := '';
  end else begin
    Result := Copy(S, 1, P - 1); S := Copy(S, P + 1, Length(S));
  end;
end;

{ 'done/total' of a progress line }
procedure SplitCount(const F: String; var Done, Total: Int64);
var
  P: Integer;
begin
  P := Pos('/', F);
  Done := StrToInt64Def(Copy(F, 1, P - 1), 0);
  Total := StrToInt64Def(Copy(F, P + 1, Length(F)), 0);
end;

function EtaText(Eta: Integer): String;
begin
  if Eta < 0 then Result := CustomMessage('EtaEstimating')
  else if Eta < 60 then Result := CustomMessage('EtaUnderMinute')
  else if Eta < 120 then Result := CustomMessage('EtaMinute')
  else Result := FmtMessage(CustomMessage('EtaMinutes'), [IntToStr((Eta + 59) div 60)]);
end;

{ M48-P: the engine's step lines are English; the page shows the translated text of the engine's phases. }
function StepCaption(const Phase, EngineText: String): String;
begin
  Result := EngineText;
  if IsPlaytest and ((Phase = 'payload') or (Phase = 'extract') or (Phase = 'check') or (Phase = 'copy')
                     or (Phase = 'verify') or (Phase = 'commit')) then
    Result := CustomMessage('Step_' + Phase);
end;

{ The person's Cancel (or the test hook): the engine sees the file at its next progress step, discards its staged
  work and reports CANCELLED. From the commit on, nothing is cancelled any more. }
procedure RequestCancel;
begin
  if CancelRequested or Committing or not EngineRunning then Exit;
  CancelRequested := SaveStringToFile(CancelFile, 'cancel', False);
  Log('cancel requested: ' + CancelFile);
  CancelButton.Enabled := False;
  ProgressPage.SetText(CustomMessage('Cancelling'), '');
end;

procedure CancelButtonOnClick(Sender: TObject);
begin
  if MsgBox(CustomMessage('CancelConfirm'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    RequestCancel;
end;

{ M32 (D-069): Exec / ExecAndLogOutput disable the wizard for the whole wait (Inno Setup's TWindowDisabler) while still
  pumping messages, so the page painted but could be neither dragged nor clicked. The wizard is enabled again here,
  from the output callback on the main thread: Inno keeps pumping messages every 50 ms and still owns the process
  handle and its exit code; the wizard's own Cancel and close stay off on this page (Inno disables them), so the only
  ways out are the page's Cancel (a cancel file the engine honours before its commit) or the engine's end. }
procedure KeepWizardResponsive;
begin
  if not IsWindowEnabled(WizardForm.Handle) then begin
    EnableWindow(WizardForm.Handle, True);
    Log('wizard enabled during the engine run');
  end;
end;

procedure EngineOutput(const S: String; const Error, FirstLine: Boolean);
var
  Rest, Phase: String;
  Permille, Eta: Integer;
  FilesDone, FilesTotal, BytesDone, BytesTotal: Int64;
  Detail: String;
begin
  if not WizardSilent then KeepWizardResponsive;
  Log('engine: ' + S);
  if Error then Exit;
  Rest := S;
  if Copy(S, 1, 10) = 'R3HD_STEP ' then begin
    NextField(Rest);
    Phase := NextField(Rest);
    StepText := StepCaption(Phase, Rest);
    if Phase = 'commit' then begin
      Committing := True;
      CancelButton.Enabled := False;
    end;
    if not CancelRequested then ProgressPage.SetText(StepText + '...', '');
  end else if Copy(S, 1, 14) = 'R3HD_PROGRESS ' then begin
    NextField(Rest);
    Permille := StrToIntDef(NextField(Rest), 0);
    Eta := StrToIntDef(NextField(Rest), -1);
    Phase := NextField(Rest);
    SplitCount(NextField(Rest), FilesDone, FilesTotal);
    SplitCount(NextField(Rest), BytesDone, BytesTotal);
    if Permille > LastPermille then LastPermille := Permille;
    ProgressPage.SetProgress(LastPermille, 1000);
    Detail := '';
    if FilesTotal > 0 then Detail := FmtMessage(CustomMessage('DetailFiles'), [IntToStr(FilesDone), IntToStr(FilesTotal)]);
    if (BytesTotal >= 1048576) and (Phase <> 'payload') then
      Detail := Detail + ', ' + FmtMessage(CustomMessage('DetailMB'), [IntToStr(BytesDone div 1048576), IntToStr(BytesTotal div 1048576)]);
    if Phase <> 'done' then Detail := Detail + '  -  ' + IntToStr(LastPermille div 10) + ' %, ' + EtaText(Eta);
    if not CancelRequested then ProgressPage.SetText(StepText + '...', Detail);
    if (CancelAt >= 0) and (LastPermille >= CancelAt) then RequestCancel;
  end;
end;

{ The install run: hidden, with its output read line by line while it works (the wizard keeps painting). }
function RunInstallEngine(const Args, ResultFile: String): Integer;
var
  Code: Integer;
begin
  DeleteFile(ResultFile);
  CancelFile := ExpandConstant('{tmp}\cancel.flag');
  DeleteFile(CancelFile);
  CancelRequested := False; Committing := False; LastPermille := 0;
  CancelAt := -1;
  if IsTestMode then CancelAt := StrToIntDef(ExpandConstant('{param:CANCELAT|-1}'), -1);
  StepText := CustomMessage('Preparing');
  ProgressPage.SetText(StepText + '...', '');
  ProgressPage.SetProgress(0, 1000);
  CancelButton.Enabled := True;
  if not WizardSilent then ProgressPage.Show;
  { M32: the window is usable while the engine works, so the wizard's own navigation must not be }
  NextWasEnabled := WizardForm.NextButton.Enabled;
  BackWasEnabled := WizardForm.BackButton.Enabled;
  WizardForm.NextButton.Enabled := False;
  WizardForm.BackButton.Enabled := False;
  EngineRunning := True;
  try
    try
      if not ExecAndLogOutput(PayloadPath('app\python\python.exe'),
                              '-B "' + PayloadPath('app\tools\r3hd_installer.py') + '" ' + Args + ' --progress --cancel-file "' +
                              CancelFile + '" --result-file "' + ResultFile + '"',
                              ExpandConstant('{tmp}'), SW_SHOWNORMAL, ewWaitUntilTerminated, Code, @EngineOutput) then
        Code := -1;
    except
      Log('engine output: ' + GetExceptionMessage);
      Code := -1;
    end;
  finally
    EngineRunning := False;
    WizardForm.NextButton.Enabled := NextWasEnabled;
    WizardForm.BackButton.Enabled := BackWasEnabled;
    if not WizardSilent then ProgressPage.Hide;
  end;
  Log('engine: ' + Args + ' -> ' + IntToStr(Code));
  Result := Code;
end;

function VcRuntimePresent: Boolean;
begin
  Result := FileExists(ExpandConstant('{sys}\vcruntime140.dll')) and FileExists(ExpandConstant('{sys}\vcruntime140_1.dll'))
    and FileExists(ExpandConstant('{sys}\msvcp140.dll')) and FileExists(ExpandConstant('{sys}\msvcp140_atomic_wait.dll'));
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not VcRuntimePresent then begin
    SuppressibleMsgBox(CustomMessage('VcMissing'), mbCriticalError, MB_OK, IDOK);
    Result := False;
  end;
end;

function EnsurePayload: Boolean;
begin
  if not PayloadReady then begin
    ExtractTemporaryFiles('{tmp}\payload\*');
    PayloadReady := FileExists(PayloadPath('payload.json'));
    if not PayloadReady then Log('payload extraction failed');
  end;
  Result := PayloadReady;
end;

{ Play and Settings on the Finish page are alternatives: checking one clears the other. }
{ --- M48-P: language page --------------------------------------------------------------------------------------- }

function StartsWithText(const S, Prefix: String): Boolean;
begin
  Result := CompareText(Copy(S, 1, Length(Prefix)), Prefix) = 0;
end;

{ The parameters a restarted wizard keeps: the test switches and folders, nothing of Inno's own loader. }
function CarriedParams: String;
var
  I: Integer;
  P: String;
begin
  Result := '';
  for I := 1 to ParamCount do begin
    P := ParamStr(I);
    if StartsWithText(P, '/R3HDTEST=') or StartsWithText(P, '/STARTMENUDIR=') or StartsWithText(P, '/DESKTOPDIR=')
       or StartsWithText(P, '/CANCELAT=') or StartsWithText(P, '/VERIFYDATA=') or StartsWithText(P, '/MERGETASKS=')
       or StartsWithText(P, '/TASKS=') or (CompareText(P, '/SP-') = 0) then
      Result := Result + ' ' + AddQuotes(P)
    else if StartsWithText(P, '/LOG=') then
      { the new wizard logs beside the old one: <log>.<language>.log }
      Result := Result + ' ' + AddQuotes(P + '.' + ActiveLanguage + '.log');
  end;
end;

procedure SwitchLanguage(const Lang: String);
var
  Params: String;
  Code: Integer;
begin
  if Lang = ActiveLanguage then Exit;
  Params := '/LANG=' + Lang + ' /LANGSWITCH=1' + CarriedParams + ' ' + AddQuotes('/DIR=' + WizardDirValue);
  if PackagePage.Values[0] <> '' then Params := Params + ' ' + AddQuotes('/PACKAGE=' + PackagePage.Values[0]);
  if PresetVisited then Params := Params + ' /PRESETINDEX=' + IntToStr(PresetPage.SelectedValueIndex);
  Log('language switch: ' + ActiveLanguage + ' -> ' + Lang + ': ' + Params);
  if not Exec(ExpandConstant('{cmd}'), '/c start "" ' + AddQuotes(ExpandConstant('{srcexe}')) + ' ' + Params, '',
              SW_HIDE, ewNoWait, Code) then begin
    MsgBox(FmtMessage(CustomMessage('LangSwitchFailed'), [SysErrorMessage(Code)]), mbError, MB_OK);
    Exit;
  end;
  Switching := True;
  WizardForm.Close;
end;

procedure LangTrClick(Sender: TObject);
begin
  SwitchLanguage('tr');
end;

procedure LangEnClick(Sender: TObject);
begin
  SwitchLanguage('en');
end;

{ The flag bitmap for this DPI: 96 x 64 at 100 %, 120 / 144 / 192 at 125 / 150 / 200 % (tools\m48p_flags.py). }
function FlagFile(const Lang: String): String;
var
  H, W: Integer;
begin
  H := ScaleY(64);
  W := 96;
  if H >= 80 then W := 120;
  if H >= 96 then W := 144;
  if H >= 128 then W := 192;
  Result := 'flag_' + Lang + '_' + IntToStr(W) + '.png';
end;

function MakeLabel(Page: TWizardPage; const Text: String; Top: Integer; Bold: Boolean): TNewStaticText;
begin
  Result := TNewStaticText.Create(Page);
  Result.Parent := Page.Surface;
  Result.AutoSize := False;
  Result.WordWrap := True;
  Result.Left := 0;
  Result.Top := Top;
  Result.Width := Page.SurfaceWidth;
  if Bold then Result.Font.Style := [fsBold];
  Result.Caption := Text;
  WizardForm.AdjustLabelHeight(Result);
end;

procedure CreateLanguagePage;
var
  Prompt: TNewStaticText;
  ColW, Gap, Left0, Y: Integer;
begin
  LangPage := CreateCustomPage(wpWelcome, CustomMessage('LangPageTitle'), CustomMessage('LangPageDesc'));
  Prompt := MakeLabel(LangPage, 'Kurulum dilini seçin  /  Choose the setup language', ScaleY(28), True);
  Prompt.Alignment := taCenter;
  ExtractTemporaryFile(FlagFile('tr'));
  ExtractTemporaryFile(FlagFile('en'));
  ColW := ScaleX(140);
  Gap := ScaleX(48);
  Left0 := (LangPage.SurfaceWidth - 2 * ColW - Gap) div 2;
  Y := Prompt.Top + Prompt.Height + ScaleY(28);

  LangTrFlag := TBitmapButton.Create(LangPage);
  LangTrFlag.Parent := LangPage.Surface;
  LangTrFlag.AutoSize := True;
  LangTrFlag.PngImage.LoadFromFile(ExpandConstant('{tmp}\') + FlagFile('tr'));
  LangTrFlag.Caption := 'Türkçe (Turkish)';
  LangTrFlag.Hint := 'Türkçe';
  LangTrFlag.ShowHint := True;
  LangTrFlag.Cursor := crHand;
  LangTrFlag.Left := Left0 + (ColW - LangTrFlag.Width) div 2;
  LangTrFlag.Top := Y;
  LangTrFlag.OnClick := @LangTrClick;

  LangEnFlag := TBitmapButton.Create(LangPage);
  LangEnFlag.Parent := LangPage.Surface;
  LangEnFlag.AutoSize := True;
  LangEnFlag.PngImage.LoadFromFile(ExpandConstant('{tmp}\') + FlagFile('en'));
  LangEnFlag.Caption := 'English (İngilizce)';
  LangEnFlag.Hint := 'English';
  LangEnFlag.ShowHint := True;
  LangEnFlag.Cursor := crHand;
  LangEnFlag.Left := Left0 + ColW + Gap + (ColW - LangEnFlag.Width) div 2;
  LangEnFlag.Top := Y;
  LangEnFlag.OnClick := @LangEnClick;

  Y := Y + LangTrFlag.Height + ScaleY(10);
  LangTrButton := TNewButton.Create(LangPage);
  LangTrButton.Parent := LangPage.Surface;
  LangTrButton.Width := ColW;
  LangTrButton.Height := ScaleY(27);
  LangTrButton.Left := Left0;
  LangTrButton.Top := Y;
  LangTrButton.OnClick := @LangTrClick;

  LangEnButton := TNewButton.Create(LangPage);
  LangEnButton.Parent := LangPage.Surface;
  LangEnButton.Width := ColW;
  LangEnButton.Height := ScaleY(27);
  LangEnButton.Left := Left0 + ColW + Gap;
  LangEnButton.Top := Y;
  LangEnButton.OnClick := @LangEnClick;

  { the active language is marked by text (a check mark and bold), not only by colour }
  if ActiveLanguage = 'tr' then begin
    LangTrButton.Caption := '✓ &Türkçe';
    LangTrButton.Font.Style := [fsBold];
    LangEnButton.Caption := '&English';
  end else begin
    LangTrButton.Caption := '&Türkçe';
    LangEnButton.Caption := '✓ &English';
    LangEnButton.Font.Style := [fsBold];
  end;
end;

{ --- M48-P: playtest steps ---------------------------------------------------------------------------------------- }

{ M49: what this setup does with the Turkish translation: '1' install and turn on, '0' nothing (a fresh installation,
  by the setup language), '3' an existing installation (only an installed copy is updated; never added again);
  silent /TURKISH= overrides it. }
function TurkishWant: String;
begin
  if Installed then Result := '3'
  else if ActiveLanguage = 'tr' then Result := '1'
  else Result := '0';
  if WizardSilent and (ExpandConstant('{param:TURKISH|}') <> '') then begin
    Result := ExpandConstant('{param:TURKISH|}');
    if (Result <> '0') and (Result <> '2') and (Result <> '3') then Result := '1';
  end;
end;

{ The Turkish translation's state in this folder (r3hd_bundled_mods.py status), for the options page. }
procedure DetectTurkish;
var
  F: String;
  Code: Integer;
begin
  if TurkishWant = '0' then TurkishAction := 'skip_declined' else TurkishAction := 'install_enable';
  TurkishInstalledVersion := '';
  TurkishInstalledEnabled := '';
  if not Installed then Exit;
  ExtractTemporaryFile('{#BundledModFile}');
  F := ExpandConstant('{tmp}\bundled_status.txt');
  DeleteFile(F);
  if not Exec(PayloadPath('app\python\python.exe'), '-B "' + PayloadPath('app\tools\r3hd_bundled_mods.py') +
              '" status --home "' + WizardDirValue + '" --mod "' + ExpandConstant('{tmp}\{#BundledModFile}') +
              '" --want ' + TurkishWant + ' --result-file "' + F + '"', ExpandConstant('{tmp}'), SW_HIDE,
              ewWaitUntilTerminated, Code) then Code := -1;
  if Code = 0 then begin
    TurkishAction := ResultValue(F, 'ACTION');
    TurkishInstalledVersion := ResultValue(F, 'INSTALLED_VERSION');
    TurkishInstalledEnabled := ResultValue(F, 'ENABLED');
  end else
    TurkishAction := 'unknown';
  Log('Turkish preview in this folder: ' + TurkishAction + ' ' + TurkishInstalledVersion + ' enabled=' + TurkishInstalledEnabled);
end;

function OnOffText(const V: String): String;
begin
  if V = '1' then Result := CustomMessage('StateOn') else Result := CustomMessage('StateOff');
end;

{ D-090: the Turkish line of the ready memo (the options page is gone). }
function TurkishNoteText: String;
begin
  if TurkishAction = 'install_enable' then Result := CustomMessage('TurkishNoteFreshTr')
  else if TurkishAction = 'skip_declined' then Result := CustomMessage('TurkishNoteFreshEn')
  else if (TurkishAction = 'skip_absent') or (TurkishAction = 'skip_removed') then Result := CustomMessage('TurkishNoteAbsent')
  else if TurkishAction = 'upgrade' then
    Result := FmtMessage(CustomMessage('TurkishNoteUpgrade'), [TurkishInstalledVersion, OnOffText(TurkishInstalledEnabled)])
  else if TurkishAction = 'unchanged' then
    Result := FmtMessage(CustomMessage('TurkishNoteSame'), [OnOffText(TurkishInstalledEnabled)])
  else if TurkishAction = 'keep_newer' then
    Result := FmtMessage(CustomMessage('TurkishNoteNewer'), [TurkishInstalledVersion])
  else if TurkishAction = 'keep_different' then Result := CustomMessage('TurkishNoteDifferent')
  else Result := CustomMessage('TurkishNoteUnknown');
end;

procedure InitializeWizard;
begin
  PackagePage := CreateInputFilePage(wpSelectDir, CustomMessage('PackageTitle'), CustomMessage('PackageDesc'),
    CustomMessage('PackageText'));
  PackagePage.Add(CustomMessage('PackageLabel'), CustomMessage('PackageFilter'), '');
  { M32: /PACKAGE= also fills the page when the wizard is shown (a test drives it on a private desktop) }
  PackagePage.Values[0] := ExpandConstant('{param:PACKAGE|}');
  VerifyBox := TNewCheckBox.Create(PackagePage);
  VerifyBox.Parent := PackagePage.Surface;
  VerifyBox.Top := PackagePage.Edits[0].Top + PackagePage.Edits[0].Height + ScaleY(16);
  VerifyBox.Width := PackagePage.SurfaceWidth;
  { M48-P: scaled height (a fixed one clipped the caption at 125 % and above) }
  VerifyBox.Height := ScaleY(17);
  VerifyBox.Caption := CustomMessage('VerifyBox');
  PresetPage := CreateInputOptionPage(PackagePage.ID, CustomMessage('PresetTitle'), CustomMessage('PresetDesc'),
    CustomMessage('PresetText'), True, False);
  PresetPage.Add(CustomMessage('PresetVanilla'));
  PresetPage.Add(CustomMessage('PresetHdplus'));
  PresetPage.Add(CustomMessage('PresetCustom'));
  PresetPage.Add(CustomMessage('PresetKeep'));
  PresetPage.SelectedValueIndex := 0;
  if IsPlaytest then begin
    CreateLanguagePage;
  end;
  ProgressPage := CreateOutputProgressPage(CustomMessage('ProgressTitle'), CustomMessage('ProgressDesc'));
  CancelButton := TNewButton.Create(ProgressPage);
  CancelButton.Parent := ProgressPage.Surface;
  CancelButton.Caption := CustomMessage('CancelInstallButton');
  CancelButton.Width := ScaleX(150);
  CancelButton.Height := ScaleY(25);
  CancelButton.Top := ProgressPage.ProgressBar.Top + ProgressPage.ProgressBar.Height + ScaleY(24);
  CancelButton.Left := 0;
  CancelButton.OnClick := @CancelButtonOnClick;
end;

{ The wizard's own Cancel while the engine works asks the engine to stop instead of leaving it running. }
procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if Switching then begin
    { M48-P: a language switch closes this wizard; the new one has already started and nothing was changed }
    Cancel := True;
    Confirm := False;
  end else if EngineRunning then begin
    Cancel := False;
    Confirm := False;
    CancelButtonOnClick(nil);
  end;
end;

{ M49: the Finish page is the success message only (the person's review); the Turkish and subtitle outcomes go to the
  setup log. A step that failed (PostWarnings) is still shown here and in a message box. }
function FinishedText: String;
begin
  Result := CustomMessage('FinishedBase');
  if IsPlaytest and (PostWarnings <> '') then Result := Result + #13#10#13#10 + PostWarnings;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { M31: an existing installation whose desktop shortcut was declined (or deleted) keeps it that way. }
  if (CurPageID = wpSelectTasks) and not TasksPrepared then begin
    TasksPrepared := True;
    if Installed and (RecordedDesktop = '0') then WizardSelectTasks('!desktopicon');
    { M32: a Settings shortcut the person kept is offered checked again; a declined one stays unchecked }
    if Installed and (RecordedSettings = '1') then WizardSelectTasks('settingsicon');
    if Installed and (RecordedSettings = '0') then WizardSelectTasks('!settingsicon');
  end;
  if CurPageID = wpSelectTasks then
    Log('desktop task page: installed=' + IntToStr(Ord(Installed)) +
      ', selected="' + WizardSelectedTasks(False) + '"');
  if IsPlaytest then begin
    if CurPageID = PresetPage.ID then PresetVisited := True;
  end;
  if CurPageID = wpFinished then begin
    WizardForm.FinishedLabel.Caption := FinishedText;
    WizardForm.AdjustLabelHeight(WizardForm.FinishedLabel);
  end;
end;

function DetectInstalled: Boolean;
begin
  Installed := RunEngine('status --home "' + WizardDirValue + '"', ExpandConstant('{tmp}\status.txt')) = 0;
  RecordedDesktop := '';
  RecordedSettings := '';
  InstalledSubs := '';
  if Installed then begin
    RecordedDesktop := ResultValue(ExpandConstant('{tmp}\status.txt'), 'DESKTOP_SHORTCUT');
    { a shortcut this installer made and the person deleted since counts as declined }
    if (RecordedDesktop = '1') and (DesktopDir('') <> '') and not FileExists(DesktopLink) then RecordedDesktop := '0';
    RecordedSettings := ResultValue(ExpandConstant('{tmp}\status.txt'), 'SETTINGS_SHORTCUT');
    if (RecordedSettings = '1') and (DesktopDir('') <> '') and not FileExists(SettingsLink) then RecordedSettings := '0';
    InstalledSubs := ResultValue(ExpandConstant('{tmp}\status.txt'), 'GAMEPLAY_SUBTITLES');
  end;
  Log('existing installation: ' + IntToStr(Ord(Installed)) + ', recorded desktop shortcut: "' + RecordedDesktop +
      '", Settings shortcut: "' + RecordedSettings + '", gameplay subtitles: "' + InstalledSubs + '"');
  Result := Installed;
end;

{ M31: an existing shortcut of this installer is removed when the person now declines it. }
function RemoveDeclinedDesktop: Boolean;
begin
  Result := (RecordedDesktop = '1') and not DesktopShortcut and (DesktopDir('') <> '');
end;

function RemoveDeclinedSettings: Boolean;
begin
  Result := (RecordedSettings = '1') and not SettingsShortcut and (DesktopDir('') <> '');
end;

{ The folder's checks (payload, existing installation, preflight). M48-P: also run lazily from the package page, so
  no later page can run without them, whatever hides the folder page. }
function CheckFolder: Boolean;
var
  Code: Integer;
  F: String;
begin
  Result := False;
  if not EnsurePayload then begin
    MsgBox(CustomMessage('PayloadFailed'), mbCriticalError, MB_OK);
    Exit;
  end;
  DetectInstalled;
  if not Installed then begin
    F := ExpandConstant('{tmp}\preflight.txt');
    Code := RunEngine('preflight --home "' + WizardDirValue + '" --payload "' + PayloadPath('') + '."', F);
    if Code <> 0 then begin
      MsgBox(EngineMessage(F, Code), mbError, MB_OK);
      Exit;
    end;
  end;
  FolderChecked := WizardDirValue;
  Result := True;
end;

{ The pages that depend on the folder: the "keep" profile, the repair box, the playtest options. }
procedure PreparePagesForFolder;
begin
  PresetPage.CheckListBox.ItemEnabled[3] := Installed;
  VerifyBox.Enabled := Installed;
  if (ExpandConstant('{param:PRESETINDEX|}') <> '') and not PresetVisited then begin
    PresetPage.SelectedValueIndex := StrToIntDef(ExpandConstant('{param:PRESETINDEX|0}'), 0);
    PresetVisited := True;
  end else if Installed and not PresetVisited then PresetPage.SelectedValueIndex := 3;
  if (PresetPage.SelectedValueIndex = 3) and not Installed then PresetPage.SelectedValueIndex := 0;
  if IsPlaytest then begin
    DetectTurkish;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Code: Integer;
  F: String;
begin
  Result := True;
  { Silent runs: every check is the engine's, in PrepareToInstall (its message is the setup's error). }
  if WizardSilent then Exit;
  if (CurPageID = PackagePage.ID) and (FolderChecked <> WizardDirValue) then begin
    Log('folder checks had not run for ' + WizardDirValue + '; running them now');
    if not CheckFolder then begin
      Result := False; Exit;
    end;
    PreparePagesForFolder;
  end;
  if CurPageID = wpSelectDir then begin
    if not CheckFolder then begin
      Result := False; Exit;
    end;
    PreparePagesForFolder;
  end else if CurPageID = PackagePage.ID then begin
    if PackagePage.Values[0] = '' then begin
      if not Installed then begin
        MsgBox(CustomMessage('PackageNeeded'), mbError, MB_OK);
        Result := False;
      end;
      Exit;
    end;
    F := ExpandConstant('{tmp}\check.txt');
    WizardForm.NextButton.Enabled := False;
    try
      Code := RunEngine('check-source "' + PackagePage.Values[0] + '"', F);
    finally
      WizardForm.NextButton.Enabled := True;
    end;
    if Code <> 0 then begin
      MsgBox(CustomMessage('PackageUnusable') + #13#10#13#10 + EngineMessage(F, Code), mbError, MB_OK);
      Result := False; Exit;
    end;
    SourceRelease := ResultValue(F, 'RELEASE');
    SourceName := ResultValue(F, 'DISPLAY_NAME');
  end;
end;

{ The starting profile. Custom starts as Vanilla with no correction changed; the person picks the corrections in the
  Settings launcher. An explicit choice keeps the installation's display / graphics preferences (the engine). }
function PresetArgs: String;
begin
  Result := '';
  if WizardSilent then begin
    if ExpandConstant('{param:PRESET|}') <> '' then begin
      Result := ' --preset ' + ExpandConstant('{param:PRESET|}');
      if ExpandConstant('{param:SET|}') <> '' then Result := Result + ' --set ' + ExpandConstant('{param:SET|}');
    end;
    Exit;
  end;
  case PresetPage.SelectedValueIndex of
    0: Result := ' --preset vanilla';
    1: Result := ' --preset hdplus';
    2: Result := ' --preset custom --base vanilla';
  end;
end;

function PackageValue: String;
begin
  if WizardSilent then Result := ExpandConstant('{param:PACKAGE|}') else Result := PackagePage.Values[0];
end;

{ D-090: an explicit gameplay subtitle value (/GAMEPLAYSUBS, tests), or '' to keep what the engine stored: the
  preset's fresh default, or an existing installation's own choice. }
function SubsWanted: String;
begin
  Result := ExpandConstant('{param:GAMEPLAYSUBS|}');
  if (Result <> '') and (Result <> 'all') then Result := 'original';
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo,
  MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := CustomMessage('MemoFolder') + NewLine + Space + WizardDirValue + NewLine;
  if Installed then S := S + Space + CustomMessage('MemoExisting') + NewLine;
  S := S + NewLine + CustomMessage('MemoGameFiles') + NewLine;
  if PackageValue <> '' then
    S := S + Space + PackageValue + NewLine + Space + SourceName + ', ' + SourceRelease + ' ' + CustomMessage('MemoChecked') + NewLine
  else
    S := S + Space + CustomMessage('MemoKeepFiles') + NewLine;
  S := S + NewLine + CustomMessage('MemoProfile') + NewLine + Space + PresetPage.CheckListBox.ItemCaption[PresetPage.SelectedValueIndex] + NewLine;
  S := S + NewLine + CustomMessage('MemoDisplay') + NewLine + Space + CustomMessage('MemoDisplayLater') + NewLine;
  if IsPlaytest then begin
    S := S + NewLine + CustomMessage('MemoTurkish') + NewLine + Space;
    S := S + TurkishNoteText + NewLine;
  end;
  if MemoTasksInfo <> '' then S := S + NewLine + MemoTasksInfo + NewLine;
  Result := S + NewLine + CustomMessage('MemoSpace');
end;

{ M48-P: the steps after the install: hidden, read line by line so the wizard stays responsive. }
procedure StepOutput(const S: String; const Error, FirstLine: Boolean);
begin
  if not WizardSilent then KeepWizardResponsive;
  Log('step: ' + S);
end;

function RunStep(const Script, Args, ResultFile: String): Integer;
var
  Code: Integer;
begin
  DeleteFile(ResultFile);
  try
    if not ExecAndLogOutput(PayloadPath('app\python\python.exe'), '-B "' + PayloadPath('app\tools\' + Script) + '" ' +
                            Args + ' --result-file "' + ResultFile + '"', ExpandConstant('{tmp}'), SW_HIDE,
                            ewWaitUntilTerminated, Code, @StepOutput) then
      Code := -1;
  except
    Log('step output: ' + GetExceptionMessage);
    Code := -1;
  end;
  Log('step: ' + Script + ' ' + Args + ' -> ' + IntToStr(Code));
  Result := Code;
end;

procedure RunPlaytestSteps;
var
  F, Action, Want, Subs, Current: String;
  Code: Integer;
begin
  TurkishOutcome := ''; SubsOutcome := ''; PostWarnings := '';
  if not WizardSilent then begin
    ProgressPage.SetText(CustomMessage('StepTurkish'), '');
    ProgressPage.SetProgress(1000, 1000);
    CancelButton.Enabled := False;
    ProgressPage.Show;
  end;
  try
    Want := TurkishWant;
    ExtractTemporaryFile('{#BundledModFile}');
    F := ExpandConstant('{tmp}\bundled.txt');
    Code := RunStep('r3hd_bundled_mods.py', 'apply --home "' + WizardDirValue + '" --mod "' +
                    ExpandConstant('{tmp}\{#BundledModFile}') + '" --want ' + Want, F);
    Action := ResultValue(F, 'ACTION');
    if Code <> 0 then
      PostWarnings := FmtMessage(CustomMessage('TurkishFailed'), [EngineMessage(F, Code)])
    else if (Action = 'install_enable') or (Action = 'upgrade') or (Action = 'unchanged') then begin
      if ResultValue(F, 'ENABLED') = '1' then
        TurkishOutcome := FmtMessage(CustomMessage('TurkishDoneOn'), [ResultValue(F, 'INSTALLED_VERSION')])
      else
        TurkishOutcome := FmtMessage(CustomMessage('TurkishDoneOff'), [ResultValue(F, 'INSTALLED_VERSION')]);
    end else if Action = 'keep_newer' then
      TurkishOutcome := FmtMessage(CustomMessage('TurkishNoteNewer'), [ResultValue(F, 'INSTALLED_VERSION')])
    else if Action = 'keep_different' then TurkishOutcome := CustomMessage('TurkishNoteDifferent')
    else if (Action = 'skip_removed') or (Action = 'skip_absent') then TurkishOutcome := CustomMessage('TurkishNoteAbsent')
    else if Action = 'skip_declined' then TurkishOutcome := CustomMessage('TurkishNoteFreshEn')
    else TurkishOutcome := CustomMessage('TurkishNotInstalled');

    if not WizardSilent then ProgressPage.SetText(CustomMessage('StepSubs'), '');
    Subs := SubsWanted;
    F := ExpandConstant('{tmp}\status_after.txt');
    if RunEngine('status --home "' + WizardDirValue + '"', F) = 0 then Current := ResultValue(F, 'GAMEPLAY_SUBTITLES')
    else Current := '';
    if (Subs <> '') and (Subs <> Current) then begin
      F := ExpandConstant('{tmp}\subs.txt');
      Code := RunStep('r3hd_installer.py', 'set-option --home "' + WizardDirValue + '" --set gameplay_subtitles=' + Subs, F);
      if Code <> 0 then begin
        PostWarnings := PostWarnings + #13#10 + FmtMessage(CustomMessage('SubsFailed'), [EngineMessage(F, Code)]);
        Subs := Current;
      end;
    end else
      Subs := Current;
    if Subs = 'all' then SubsOutcome := CustomMessage('SubsDoneOn') else SubsOutcome := CustomMessage('SubsDoneOff');
    Log('playtest steps: Turkish ' + Action + ', gameplay subtitles ' + Subs);
  finally
    if not WizardSilent then ProgressPage.Hide;
  end;
  if (PostWarnings <> '') and not WizardSilent then MsgBox(Trim(PostWarnings), mbError, MB_OK);
end;

{ Post-1.0.1 UX: the engine wrote the Play icon from the person's package (r3hd_installer.py write_play_icon). }
function HasPlayIcon: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\data\play_icon.ico'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Args, F: String;
  Code: Integer;
begin
  Result := '';
  if not EnsurePayload then begin
    Result := CustomMessage('PayloadFailed'); Exit;
  end;
  if WizardSilent then DetectInstalled;
  Args := 'install --home "' + WizardDirValue + '" --payload "' + PayloadPath('') + '."' + PresetArgs;
  if ActiveLanguage = 'tr' then Args := Args + ' --ui-language tr'
  else Args := Args + ' --ui-language en';
  if PackageValue <> '' then Args := Args + ' --source "' + PackageValue + '"';
  if VerifyBox.Checked or (ExpandConstant('{param:VERIFYDATA|0}') = '1') then Args := Args + ' --verify-data';
  if DesktopShortcut then Args := Args + ' --desktop-shortcut 1' else Args := Args + ' --desktop-shortcut 0';
  if SettingsShortcut then Args := Args + ' --settings-shortcut 1' else Args := Args + ' --settings-shortcut 0';
  F := ExpandConstant('{tmp}\install.txt');
  Code := RunInstallEngine(Args, F);
  if ResultValue(F, 'CODE') = 'CANCELLED' then
    Result := CustomMessage('InstallCancelled')
  else if (Code = 0) and CancelRequested then begin
    { The request came after the engine's commit (before its "commit" step line reached the page): it completed. }
    Log('cancel request arrived after the commit; the installation completed');
    if not WizardSilent then MsgBox(CustomMessage('CancelTooLate'), mbInformation, MB_OK);
  end else if Code <> 0 then
    Result := EngineMessage(F, Code) + #13#10#13#10 + CustomMessage('NothingChanged');
  if (Result = '') and IsPlaytest then RunPlaytestSteps;
end;

{ M29 review: the engine is asked first. If it refuses (game or Settings running, another operation, unreadable state),
  the uninstaller stops before it deletes anything of its own, so app\ (and with it the engine) is never orphaned. }
function InitializeUninstall: Boolean;
var
  Code: Integer;
  F: String;
begin
  F := AddBackslash(GetTempDir) + 'r3hd_uninstall_check.txt';
  DeleteFile(F);
  if not Exec(ExpandConstant('{app}\app\python\python.exe'), '-B "' + ExpandConstant('{app}\app\tools\r3hd_installer.py') +
              '" uninstall --check --home "' + ExpandConstant('{app}') + '" --result-file "' + F + '"',
              ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then Code := -1;
  Result := Code = 0;
  if not Result then
    SuppressibleMsgBox(CustomMessage('UninstallRefused') + #13#10#13#10 + EngineMessage(F, Code), mbError, MB_OK, IDOK);
  DeleteFile(F);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Code: Integer;
  Args, Py, F: String;
  RemoveUser: Boolean;
begin
  if CurUninstallStep <> usUninstall then Exit;
  RemoveUser := ExpandConstant('{param:REMOVEUSERDATA|0}') = '1';
  if not UninstallSilent then
    RemoveUser := MsgBox(CustomMessage('UninstallUserData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Args := 'uninstall --home "' + ExpandConstant('{app}') + '" --from-uninstaller';
  if RemoveUser then Args := Args + ' --remove-user-data --confirm "' + ExpandConstant('{app}') + '"';
  Py := ExpandConstant('{app}\app\python\python.exe');
  F := ExpandConstant('{tmp}\uninstall.txt');
  if not Exec(Py, '-B "' + ExpandConstant('{app}\app\tools\r3hd_installer.py') + '" ' + Args + ' --result-file "' + F + '"',
              ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then Code := -1;
  Log('engine uninstall -> ' + IntToStr(Code));
  if (Code <> 0) and not UninstallSilent then
    MsgBox(FmtMessage(CustomMessage('UninstallPartial'), [EngineMessage(F, Code)]), mbError, MB_OK);
end;
