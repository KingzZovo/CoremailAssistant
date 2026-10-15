; =========================================================================
; Inno Setup 脚本：Coremail 论客邮件智能协同助手 Windows 安装包
; 采用 LZMA2/Ultra64 固实压缩 (Solid Compression)，极大缩减体积并提供专业安装向导
; =========================================================================

#define MyAppName "CoremailAssistant"
#define MyAppDisplayName "Coremail 论客邮件智能协同助手"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.4"
#endif
#define MyAppPublisher "KingzZovo"
#define MyAppURL "https://github.com/KingzZovo/CoremailAssistant"
#define MyAppExeName "CoremailAssistant.exe"

[Setup]
; 唯一应用程序 GUID 标识
AppId={{C6E2A5D1-8F32-4720-B95F-9125D7E84BC3}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 安装到当前用户应用目录 (默认无需管理员权限 UAC 弹窗，支持绿色静默升级)
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppDisplayName}
AllowNoIcons=yes

; 输出目录与文件名
OutputDir=..\dist_installer
OutputBaseFilename=CoremailAssistant-Setup-v{#MyAppVersion}

; 极致高压缩比配置 (Solid LZMA2 Ultra64，体积直降 80%+)
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMADictionarySize=1048576
LZMANumBlockThreads=6

; 平台架构与权限
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 覆盖升级时自动检测并关闭旧版本运行中的进程
CloseApplications=yes
CloseApplicationsFilter=CoremailAssistant.exe
RestartApplications=no

WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenuicon"; Description: "创建开始菜单快捷方式"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; 打包主执行程序与运行时动态库
Source: "..\dist\CoremailAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 配置文件与数据目录（覆盖升级时不覆盖已有数据库）
Source: "..\dist\CoremailAssistant\data\*"; DestDir: "{app}\data"; Flags: onlyifdestdoesntexist recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppDisplayName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppDisplayName}}"; Flags: nowait postinstall skipifsilent
