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

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AMR Simulator"; Filename: "{app}\AMRSimulator.exe"

[Run]
Filename: "{app}\AMRSimulator.exe"; Description: "Launch AMR Simulator"; Flags: nowait postinstall skipifsilent
