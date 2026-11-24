; İndirici — Inno Setup kurulum betiği
; Derlemek için: ISCC.exe kurulum.iss  (veya derle.bat)

#define MyAppName "İndirici"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Zeki"
#define MyAppURL "https://github.com/Zeki-wq/intro"
#define MyAppExeName "Indirici.exe"

[Setup]
AppId={{A7C4E2F1-3B9D-4C6A-9E21-5D8B7F0C3A64}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion=1.2.0.0
VersionInfoDescription={#MyAppName} Kurulum
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
DefaultDirName={autopf}\Indirici
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
OutputDir=kurulum
OutputBaseFilename=Indirici-Setup-{#MyAppVersion}
SetupIconFile=assets\indirici.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes
MinVersion=10.0

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\Indirici\Indirici.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\Indirici\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "İndirici'yi başlat"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\indirici-hata.log"
Type: files; Name: "{app}\ayarlar.json"
Type: dirifempty; Name: "{app}"
