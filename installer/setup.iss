; Inno Setup script for the Electronics POS Windows installer.
; Build POS first with PyInstaller (see build_installer.bat), then:
;   ISCC.exe /DAppVersion=1.1.0 installer\setup.iss
; The installer is written to dist\POS_Setup_<version>.exe

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B2F1C4E-8D3A-4E7B-9C51-2A7F0D3E9B14}
AppName=Electronics POS
AppVersion={#AppVersion}
AppPublisher=Electronics POS
DefaultDirName={autopf}\Electronics POS
DefaultGroupName=Electronics POS
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=POS_Setup_{#AppVersion}
SetupIconFile=..\assets\pos.ico
UninstallDisplayIcon={app}\POS.exe
UninstallDisplayName=Electronics POS
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Dirs]
; Shop data (database, backups, receipts). Every Windows user on the till may write here.
; It is NOT removed on uninstall, so sales history survives a reinstall or upgrade.
Name: "{commonappdata}\ElectronicsPOS"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "..\dist\POS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "pos_installed.flag"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\Electronics POS"; Filename: "{app}\POS.exe"
Name: "{group}\Shop data folder"; Filename: "{commonappdata}\ElectronicsPOS"
Name: "{group}\Uninstall Electronics POS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Electronics POS"; Filename: "{app}\POS.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\POS.exe"; Description: "Start Electronics POS now"; Flags: nowait postinstall skipifsilent
