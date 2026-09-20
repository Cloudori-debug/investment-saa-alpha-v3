; SAA Alpha — Inno Setup script (Unicode)
; 1) powershell -File scripts\bundle_runtime.ps1
; 2) Open this file in Inno Setup Compiler → Build
; 3) Output: packaging\Output\SAAAlphaSetup.exe

#define MyAppName "코스피 알파 스크리너"
#define MyAppNameEn "KOSPI Alpha Screener"
#define MyAppVersion "3.0.1"
#define MyAppPublisher "Cloudori"
#define MyAppURL "https://github.com/Cloudori-debug/investment-saa-alpha-v3"
; Built portable tree (must exist before compile)
#define MySourceDir "..\dist\SAA-Alpha-portable"

[Setup]
AppId={{A7C3E9D1-5B42-4F8A-9E21-0B1C2D3E4F50}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={localappdata}\SAA-Alpha
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=SAAAlphaSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile=install_info_ko.txt
SetupIconFile=icons\saa_alpha.ico
UninstallDisplayIcon={app}\saa_alpha.ico
UninstallDisplayName={#MyAppName}
ArchitecturesInstallIn64BitMode=x64compatible
; Keep user ledger across upgrades
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Install Korean.isl language pack with Inno Setup if you want a full KO wizard UI.

[Tasks]
Name: "desktopicon"; Description: "바탕 화면 아이콘 만들기"; GroupDescription: "추가 아이콘:"; Flags: unchecked

[Files]
; Full portable tree. data\* only if missing so upgrades keep positions/target.
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "data\*"
Source: "{#MySourceDir}\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist uninsneveruninstall
; Icon always present for shortcuts
Source: "icons\saa_alpha.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Launch_SAA.bat"; WorkingDir: "{app}"; IconFilename: "{app}\saa_alpha.ico"
Name: "{group}\제거 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Launch_SAA.bat"; WorkingDir: "{app}"; IconFilename: "{app}\saa_alpha.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Launch_SAA.bat"; Description: "지금 실행"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; Do NOT delete user data by default — operator may want ledger after uninstall
Type: filesandordirs; Name: "{app}\.venv"
Type: files; Name: "{app}\LAST_UPDATE.txt"
Type: files; Name: "{app}\PACKAGED.txt"
