; installer.iss — Inno Setup script to build a real Windows installer.
;
; Inno Setup is FREE: https://jrsoftware.org/isdl.php
; After building the app folder (python build_exe.py), compile this with the
; Inno Setup Compiler (ISCC.exe installer.iss) to produce Setup.exe.
;
; The resulting Setup.exe:
;   • installs into Program Files
;   • creates Start Menu + (optional) Desktop shortcuts
;   • adds an uninstaller
;   • optionally adds the "Compress with MultiCompress" right-click menu

#define AppName "MultiCompress"
#define AppVersion "1.0.0"
#define AppPublisher "Sourabh Jangid"
#define AppExeName "MultiCompress.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\MultiCompress
DefaultGroupName=MultiCompress
UninstallDisplayIcon={app}\{#AppExeName}
OutputBaseFilename=MultiCompress-Setup-{#AppVersion}
SetupIconFile=docs\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Per-user install so NO admin rights are required:
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
; Bundle the entire PyInstaller output folder.
Source: "dist\MultiCompress\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MultiCompress"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall MultiCompress"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MultiCompress"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "contextmenu"; Description: "Add 'Compress with MultiCompress' to the right-click menu"; GroupDescription: "Integration:"

[Registry]
; Right-click menu entry (only if the user ticked the task above).
Root: HKCU; Subkey: "Software\Classes\*\shell\MultiCompress"; ValueType: string; ValueData: "Compress with MultiCompress"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\MultiCompress"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExeName}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\MultiCompress\command"; ValueType: string; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: contextmenu

[Run]
; Offer to launch the app after install finishes.
Filename: "{app}\{#AppExeName}"; Description: "Launch MultiCompress"; Flags: nowait postinstall skipifsilent
