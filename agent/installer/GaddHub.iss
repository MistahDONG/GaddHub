#ifndef AppVersion
  #error Supply /DAppVersion=<agent version> when compiling this script.
#endif

[Setup]
AppId={{68CB44D8-14A0-480F-8475-324BF8335695}
AppName=GaddHub Agent
AppVersion={#AppVersion}
AppPublisher=GaddHub
AppPublisherURL=https://github.com/MarcusSandell/GaddHub
DefaultDirName={localappdata}\Programs\GaddHub
DefaultGroupName=GaddHub
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayIcon={app}\GaddHub.exe
OutputDir=..\..\dist
OutputBaseFilename=GaddHub-Setup-{#AppVersion}-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppMutex=Local\GaddHub.Agent.Running
SetupMutex=Local\GaddHub.Agent.Setup
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "swedish"; MessagesFile: "compiler:Languages\Swedish.isl"

[Files]
Source: "..\..\dist\GaddHub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\GaddHub"; Filename: "{app}\GaddHub.exe"; WorkingDir: "{app}"

[Registry]
Root: HKCU64; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "GaddHubAgent"; ValueData: """{app}\GaddHub.exe"" --background"; Check: HasExistingAutostart

[Run]
Filename: "{app}\GaddHub.exe"; Description: "{cm:LaunchProgram,GaddHub Agent}"; Flags: nowait postinstall skipifsilent

[Code]
function HasExistingAutostart: Boolean;
var
  Command: String;
begin
  Result := RegQueryStringValue(HKCU64,
    'Software\Microsoft\Windows\CurrentVersion\Run', 'GaddHubAgent', Command);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Log('Checking GaddHub autostart cleanup.');
    if RegQueryStringValue(HKCU64, 'Software\Microsoft\Windows\CurrentVersion\Run',
      'GaddHubAgent', Command) then
    begin
      if CompareText(Command, ExpandConstant('"{app}\GaddHub.exe" --background')) = 0 then
      begin
        Log('Removing autostart for this installation.');
        if not RegDeleteValue(HKCU64, 'Software\Microsoft\Windows\CurrentVersion\Run',
          'GaddHubAgent') then
          MsgBox('Could not remove the GaddHub autostart entry. Remove it manually in Windows startup settings.',
            mbError, MB_OK);
      end
      else
        Log('Autostart points elsewhere; preserving it.');
    end
    else
      Log('No autostart entry found.');
  end;
end;
