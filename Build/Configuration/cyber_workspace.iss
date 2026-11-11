; CYBER WORKSPACE — Inno Setup script — v1.0.0-rc.1
; Build (after build_windows.ps1 or PyInstaller):
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" Build\Configuration\cyber_workspace.iss
; Relative paths are resolved against THIS file's directory (Build/Configuration).
; The finished setup lands in Installer\Windows\.

#define MyAppName "CYBER WORKSPACE"
#define MyAppVersion "1.0.0-rc.1"
#define MyAppPublisher "CYBER WORKSPACE"
#define MyAppExeName "CyberWorkspace.exe"
#define RepoRoot "..\.."

[Setup]
AppId={{7C21B53A-3F5E-4B7F-9C6A-C1B2D4E5F601}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\CyberWorkspace
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; App icon (taskbar, shortcuts, add/remove programs)
SetupIconFile={#RepoRoot}\Source\Windows\assets\icon\cyber_workspace.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardSmallImageFile={#RepoRoot}\Source\Windows\assets\icon\app_icon_256.png
OutputDir={#RepoRoot}\Installer\Windows
OutputBaseFilename=CyberWorkspace-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#RepoRoot}\dist\CyberWorkspace\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; user data lives in %APPDATA%\CyberWorkspace and is intentionally preserved
Type: files; Name: "{app}\*.log"
