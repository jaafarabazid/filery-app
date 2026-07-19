; Inno Setup script for Filery (Windows).
; Packages the PyInstaller onedir build into a single Setup.exe that installs into
; the user's programs folder behind a Start Menu shortcut, so the _internal folder
; is never exposed. Built by CI:
;   iscc /DMyAppVersion=0.9.3 packaging\filery.iss
; Paths below are relative to this .iss file (the packaging/ directory).

#define MyAppName "Filery"
#define MyAppPublisher "Jaafar Abazid"
#define MyAppURL "https://github.com/jaafarabazid/filery-app"
#define MyAppExeName "Filery.exe"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
; AppId uniquely identifies the app for upgrades/uninstall. Never change it.
AppId={{9F3B1C74-2E58-4A9D-9C1B-7A0E4D6F8B21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, which matters for an unsigned app.
PrivilegesRequired=lowest
OutputBaseFilename=Filery-{#MyAppVersion}-Windows-x64-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\Filery\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
