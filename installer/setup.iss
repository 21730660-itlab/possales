; Inno Setup script for the POS Windows installers.
; Two editions are built from the same program:
;   ISCC.exe /DAppVersion=1.3.0 /DEdition=electronics installer\setup.iss   -> POS_Setup_<version>.exe
;   ISCC.exe /DAppVersion=1.3.0 /DEdition=shop_ar     installer\setup.iss   -> ShopPOS_Arabic_Setup_<version>.exe
; Build the matching PyInstaller folder first (see build_installer.bat).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef Edition
  #define Edition "electronics"
#endif

#if Edition == "shop_ar"
  #define AppId "{{A3D9E2F1-5C7B-4E8A-9F16-3B2C1D0E7A55}"
  #define AppName "Shop POS"
  #define ShortcutName "نظام المتجر - Shop POS"
  #define ExeName "ShopPOS"
  #define DataFolder "ShopPOS"
  #define SetupName "ShopPOS_Arabic_Setup_" + AppVersion
#else
  #define AppId "{{6B2F1C4E-8D3A-4E7B-9C51-2A7F0D3E9B14}"
  #define AppName "Electronics POS"
  #define ShortcutName "Electronics POS"
  #define ExeName "POS"
  #define DataFolder "ElectronicsPOS"
  #define SetupName "POS_Setup_" + AppVersion
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename={#SetupName}
SetupIconFile=..\assets\pos.ico
UninstallDisplayIcon={app}\{#ExeName}.exe
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
#if Edition == "shop_ar"
; Always start in Arabic (when Arabic.isl is available) instead of following the Windows language.
ShowLanguageDialog=no
LanguageDetectionMethod=none
#endif

[Languages]
#if Edition == "shop_ar" && FileExists(AddBackslash(SourcePath) + "Arabic.isl")
Name: "arabic"; MessagesFile: "Arabic.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
; Shop data (database, backups, receipts). Every Windows user on the till may write here.
; It is NOT removed on uninstall, so sales history survives a reinstall or upgrade.
Name: "{commonappdata}\{#DataFolder}"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "..\dist\{#ExeName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "pos_installed.flag"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#ShortcutName}"; Filename: "{app}\{#ExeName}.exe"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#ShortcutName}"; Filename: "{app}\{#ExeName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
