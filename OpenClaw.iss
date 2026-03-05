; OpenClaw 安装包脚本（单文件 exe 版）
; 使用方法：
; 1. 确保已经用 PyInstaller 生成 dist\OpenClaw.exe
; 2. 在 Inno Setup 中打开本脚本并编译，生成 OpenClaw-Setup.exe

[Setup]
AppName=OpenClaw 公众号写作助手
AppVersion=1.0.0
AppPublisher=YourName
DefaultDirName={pf}\OpenClaw
DefaultGroupName=OpenClaw
OutputBaseFilename=OpenClaw-Setup
Compression=lzma
SolidCompression=yes
DisableDirPage=no
DisableProgramGroupPage=no
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
; 可选：是否创建桌面快捷方式
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "额外图标："; Flags: unchecked

[Files]
; 注意：请根据实际路径调整 Source
; 例如：D:\openClaw\dist\OpenClaw.exe
Source: "D:\openClaw\dist\OpenClaw\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
; 开始菜单快捷方式
Name: "{group}\OpenClaw 公众号写作助手"; Filename: "{app}\OpenClaw.exe"

; 桌面快捷方式（可选）
Name: "{commondesktop}\OpenClaw 公众号写作助手"; Filename: "{app}\OpenClaw.exe"; Tasks: desktopicon

[Run]
; 安装完成后询问是否立即运行
Filename: "{app}\OpenClaw.exe"; Description: "安装完成后运行 OpenClaw"; Flags: nowait postinstall skipifsilent

