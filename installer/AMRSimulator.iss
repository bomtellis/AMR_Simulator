; Build with ISCC after running build.ps1. All inputs are local at install time.
#ifndef AppVersion
  #define AppVersion "0.1.0-dev"
#endif
#ifndef SourceDir
  #define SourceDir "build\dist\AMRSimulator"
#endif
[Setup]
AppId={{F11500E1-1BF4-47AB-83A0-0208A01B6952}
AppName=AMR Simulator
AppVersion={#AppVersion}
AppPublisher=AMR Simulator
DefaultDirName={localappdata}\Programs\AMR Simulator
DefaultGroupName=AMR Simulator
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=build\setup
OutputBaseFilename=AMR-Simulator-Setup-dev
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AMRSimulator.exe
DisableProgramGroupPage=yes
CloseApplications=yes

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AMR Simulator"; Filename: "{app}\AMRSimulator.exe"

[Run]
Filename: "{app}\AMRSimulator.exe"; Description: "Launch AMR Simulator"; Flags: nowait postinstall skipifsilent

[Code]
const
  PreviousKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{F11500E1-1BF4-47AB-83A0-0208A01B6952}_is1';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Root: Integer;
  Command, Uninstaller, Version, OldExecutable, Checksum: String;
  ExitCode, Attempt: Integer;
begin
  Result := '';
  Root := HKCU64;
  if not RegQueryStringValue(Root, PreviousKey, 'UninstallString', Command) then begin
    Root := HKCU32;
    if not RegQueryStringValue(Root, PreviousKey, 'UninstallString', Command) then
      Exit;
  end;
  Uninstaller := RemoveQuotes(Trim(Command));
  if not FileExists(Uninstaller) then begin
    Result := 'The previous AMR Simulator uninstaller is missing. Repair or remove that installation in Windows Installed apps, then run Setup again.';
    Exit;
  end;
  RegQueryStringValue(Root, PreviousKey, 'DisplayVersion', Version);
  Log('Removing registered AMR Simulator version ' + Version + ': ' + Uninstaller);
  WizardForm.StatusLabel.Caption := 'Removing previous AMR Simulator ' + Version + '...';
  OldExecutable := ExtractFilePath(Uninstaller) + 'AMRSimulator.exe';
  Checksum := MakePendingFileRenameOperationsChecksum;
  if not Exec(Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' +
      ExpandConstant('{tmp}\AMR-previous-uninstall.log') + '"', '', SW_HIDE,
      ewWaitUntilTerminated, ExitCode) then begin
    Result := 'Could not start the previous uninstaller: ' + SysErrorMessage(ExitCode);
    Exit;
  end;
  if ExitCode <> 0 then begin
    Result := 'The previous installation could not be removed (exit ' + IntToStr(ExitCode) + '). Close AMR Simulator and its workers, then retry.';
    Exit;
  end;
  if Checksum <> MakePendingFileRenameOperationsChecksum then begin
    NeedsRestart := True;
    Result := 'Restart Windows to finish removing the previous installation, then run this installer again.';
    Exit;
  end;
  for Attempt := 1 to 30 do begin
    if not FileExists(OldExecutable) and not RegValueExists(Root, PreviousKey, 'UninstallString') then
      Break;
    Sleep(100);
  end;
  if FileExists(OldExecutable) or RegValueExists(Root, PreviousKey, 'UninstallString') then
    Result := 'The previous installation is still present. Close AMR Simulator and its workers, then retry.'
  else
    Log('Previous AMR Simulator removed successfully; installing {#AppVersion}.');
end;
