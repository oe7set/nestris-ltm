; Inno Setup 6/7 script for NestrisLTM (built by packaging\build.ps1).
;
; - installs dist\NestrisLTM (PyInstaller folder) to Program Files
; - PostgreSQL: uses an existing installation or downloads and installs
;   PostgreSQL 18 silently (SHA-256 verified); its service is set to start
;   automatically
; - Mosquitto: same, then writes the NestrisLTM broker config
;   (persistence for queued QoS 1 results; the old config is backed up)
; - firewall rules for the HTTP port and MQTT, limited to the local subnet
; - writes the database connection into the user's config.toml
;   ("nestris-ltm.exe configure"), optional autostart, and shows the result of
;   "nestris-ltm.exe check" at the end
;
; Needs admin rights (services, firewall). Per-user steps (config, autostart)
; run as the user who started the setup.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "NestrisLTM"
#define GuiExe "NestrisLTM.exe"
#define CliExe "nestris-ltm.exe"
#define HttpPort "7990"

; Pinned third-party installers. To update: change URL and hash together
; (sha256 of the downloaded file); see docs/OPERATIONS.md.
#define PgVersion "18"
#define PgUrl "https://get.enterprisedb.com/postgresql/postgresql-18.6-2-windows-x64.exe"
#define PgSha256 "5de1182b7f8c823c6be13d9de9a5bca56d1d856ae18e1029afbd8ef3ba5573d6"
#define MqUrl "https://mosquitto.org/files/binary/win64/mosquitto-2.1.2-install-windows-x64.exe"
#define MqSha256 "58008ad7a22ada0b4073afa415801746e027c5f583e4fa52d0f4e9193b98d6aa"

[Setup]
AppId={{C3E2B7A4-1F5D-4E8B-A0F2-5B6C7D8E9F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Retroverse
AppPublisherURL=https://retroverse.at
DefaultDirName={autopf}\NestrisLTM
DefaultGroupName=Retroverse
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\dist
OutputBaseFilename=NestrisLTM-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#GuiExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.CompApp=NestrisLTM
en.CompApp=NestrisLTM
de.CompPg=PostgreSQL {#PgVersion} (Datenbank) – installieren, falls nicht vorhanden
en.CompPg=PostgreSQL {#PgVersion} (database) – install if missing
de.CompMq=Mosquitto (MQTT-Broker) – installieren, falls nicht vorhanden, und für NestrisLTM einrichten
en.CompMq=Mosquitto (MQTT broker) – install if missing and configure for NestrisLTM
de.TaskAutostart=NestrisLTM bei der Windows-Anmeldung im Tray starten
en.TaskAutostart=Start NestrisLTM in the tray when Windows signs in
de.TaskFirewall=Firewall-Regeln anlegen (Port {#HttpPort} und 1883, nur lokales Netz)
en.TaskFirewall=Add firewall rules (ports {#HttpPort} and 1883, local subnet only)
de.TaskDesktop=Desktop-Verknüpfung anlegen
en.TaskDesktop=Create a desktop shortcut
de.DbTitle=Datenbank (PostgreSQL)
en.DbTitle=Database (PostgreSQL)
de.DbFound=Gefunden: %1. Gib das Passwort des Datenbank-Benutzers ein (leer = vorhandene NestrisLTM-Einstellung behalten).
en.DbFound=Found: %1. Enter the password of the database user (empty = keep the current NestrisLTM setting).
de.DbNew=PostgreSQL ist nicht installiert und wird jetzt mitinstalliert. Lege das Passwort für den Datenbank-Benutzer "postgres" fest (mind. 8 Zeichen, gut aufbewahren).
en.DbNew=PostgreSQL is not installed and will be installed now. Choose the password of the database user "postgres" (at least 8 characters; keep it safe).
de.DbExternal=Keine lokale Installation gewählt: Verbindung zu einem vorhandenen PostgreSQL-Server.
en.DbExternal=No local installation selected: connect to an existing PostgreSQL server.
de.DbHost=Server:
en.DbHost=Server:
de.DbPort=Port:
en.DbPort=Port:
de.DbUser=Benutzer:
en.DbUser=User:
de.DbPassword=Passwort:
en.DbPassword=Password:
de.DbPassword2=Passwort wiederholen:
en.DbPassword2=Repeat password:
de.ErrPwShort=Das Passwort braucht mindestens 8 Zeichen.
en.ErrPwShort=The password needs at least 8 characters.
de.ErrPwMatch=Die Passwörter stimmen nicht überein.
en.ErrPwMatch=The passwords do not match.
de.ErrPwQuote=Das Passwort darf kein Anführungszeichen (") enthalten.
en.ErrPwQuote=The password must not contain a double quote (").
de.ErrPort=Ungültiger Port.
en.ErrPort=Invalid port.
de.StatusPg=PostgreSQL wird installiert (das dauert einige Minuten) …
en.StatusPg=Installing PostgreSQL (this takes a few minutes) …
de.StatusMq=Mosquitto wird installiert …
en.StatusMq=Installing Mosquitto …
de.StatusMqConf=Mosquitto wird eingerichtet …
en.StatusMqConf=Configuring Mosquitto …
de.StatusFw=Firewall-Regeln …
en.StatusFw=Firewall rules …
de.StatusConf=NestrisLTM wird konfiguriert und geprüft …
en.StatusConf=Configuring and checking NestrisLTM …
de.ErrInstall=%1 konnte nicht installiert werden (Code %2). NestrisLTM wird trotzdem installiert; siehe docs\OPERATIONS.md.
en.ErrInstall=%1 could not be installed (code %2). NestrisLTM is installed anyway; see docs\OPERATIONS.md.
de.CheckTitle=Prüfung
en.CheckTitle=Check
de.CheckDesc=Ergebnis von "nestris-ltm check": Datenbank, MQTT-Broker und HTTP-Port.
en.CheckDesc=Result of "nestris-ltm check": database, MQTT broker and HTTP port.
de.CheckHint=Nach dem Start: Admin-Oberfläche öffnet sich, beim ersten Mal wird dort das Admin-Konto angelegt.
en.CheckHint=After the start the admin UI opens; the first time it asks you to create the admin account.
de.LaunchNow=NestrisLTM jetzt starten
en.LaunchNow=Start NestrisLTM now

[Components]
Name: "app"; Description: "{cm:CompApp}"; Types: full compact custom; Flags: fixed
Name: "postgres"; Description: "{cm:CompPg}"; Types: full
Name: "mosquitto"; Description: "{cm:CompMq}"; Types: full

[Tasks]
Name: "autostart"; Description: "{cm:TaskAutostart}"
Name: "firewall"; Description: "{cm:TaskFirewall}"
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; Flags: unchecked

[Files]
Source: "..\dist\NestrisLTM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "mosquitto\mosquitto.conf"; DestDir: "{app}\mosquitto"; Flags: ignoreversion
Source: "..\config.example.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\OPERATIONS.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#GuiExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#GuiExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#GuiExe}"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{app}\{#CliExe}"; Parameters: "autostart off"; Flags: runhidden waituntilterminated; RunOnceId: "AutostartOff"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""NestrisLTM (HTTP)"""; Flags: runhidden waituntilterminated; RunOnceId: "FwHttp"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Mosquitto MQTT (NestrisLTM)"""; Flags: runhidden waituntilterminated; RunOnceId: "FwMqtt"

[Code]
var
  DbPage: TInputQueryWizardPage;
  CheckPage: TOutputMsgMemoWizardPage;
  DownloadPage: TDownloadWizardPage;
  PgService, PgFoundText: String;
  PgInstalled, MqInstalled: Boolean;

{ ------------------------------------------------------------ detection }

procedure DetectPostgres;
var
  Names: TArrayOfString;
  I: Integer;
  Port: Cardinal;
  Version: String;
begin
  PgInstalled := False;
  PgService := '';
  if RegGetSubkeyNames(HKLM, 'SOFTWARE\PostgreSQL\Installations', Names) then
    for I := 0 to GetArrayLength(Names) - 1 do
    begin
      { The newest installation wins (the keys sort by version). }
      if RegQueryStringValue(HKLM, 'SOFTWARE\PostgreSQL\Installations\' + Names[I], 'Service ID', PgService) then
      begin
        PgInstalled := True;
        RegQueryStringValue(HKLM, 'SOFTWARE\PostgreSQL\Installations\' + Names[I], 'Version', Version);
        PgFoundText := 'PostgreSQL ' + Version + ' (' + PgService + ')';
        if RegQueryDWordValue(HKLM, 'SOFTWARE\PostgreSQL\Services\' + PgService, 'Port', Port) then
          DbPage.Values[1] := IntToStr(Port);
      end;
    end;
end;

procedure DetectMosquitto;
begin
  MqInstalled := FileExists(ExpandConstant('{commonpf64}\mosquitto\mosquitto.exe'));
end;

function InstallPostgres: Boolean;
begin
  Result := WizardIsComponentSelected('postgres') and not PgInstalled;
end;

function InstallMosquitto: Boolean;
begin
  Result := WizardIsComponentSelected('mosquitto') and not MqInstalled;
end;

{ ------------------------------------------------------------ wizard }

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  DbPage := CreateInputQueryPage(wpSelectTasks, CustomMessage('DbTitle'), '', '');
  DbPage.Add(CustomMessage('DbHost'), False);
  DbPage.Add(CustomMessage('DbPort'), False);
  DbPage.Add(CustomMessage('DbUser'), False);
  DbPage.Add(CustomMessage('DbPassword'), True);
  DbPage.Add(CustomMessage('DbPassword2'), True);
  DbPage.Values[0] := GetPreviousData('DbHost', '127.0.0.1');
  DbPage.Values[1] := GetPreviousData('DbPort', '5432');
  DbPage.Values[2] := GetPreviousData('DbUser', 'postgres');

  CheckPage := CreateOutputMsgMemoPage(wpInfoAfter, CustomMessage('CheckTitle'), CustomMessage('CheckDesc'),
    CustomMessage('CheckHint'), '');

  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
  DetectPostgres;
  DetectMosquitto;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'DbHost', DbPage.Values[0]);
  SetPreviousData(PreviousDataKey, 'DbPort', DbPage.Values[1]);
  SetPreviousData(PreviousDataKey, 'DbUser', DbPage.Values[2]);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = DbPage.ID then
  begin
    if InstallPostgres then
    begin
      DbPage.SubCaptionLabel.Caption := CustomMessage('DbNew');
      DbPage.Values[0] := '127.0.0.1';
      DbPage.Values[2] := 'postgres';
    end
    else if PgInstalled then
      DbPage.SubCaptionLabel.Caption := FmtMessage(CustomMessage('DbFound'), [PgFoundText])
    else
      DbPage.SubCaptionLabel.Caption := CustomMessage('DbExternal');
    { Host and user of a new local server are fixed. }
    DbPage.Edits[0].Enabled := not InstallPostgres;
    DbPage.Edits[2].Enabled := not InstallPostgres;
    DbPage.Edits[4].Enabled := InstallPostgres;
    DbPage.PromptLabels[4].Enabled := InstallPostgres;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
begin
  Result := True;
  if CurPageID = DbPage.ID then
  begin
    Port := StrToIntDef(Trim(DbPage.Values[1]), 0);
    if (Port < 1) or (Port > 65535) then
    begin
      MsgBox(CustomMessage('ErrPort'), mbError, MB_OK);
      Result := False;
    end
    else if Pos('"', DbPage.Values[3]) > 0 then
    begin
      MsgBox(CustomMessage('ErrPwQuote'), mbError, MB_OK);
      Result := False;
    end
    else if InstallPostgres and (Length(DbPage.Values[3]) < 8) then
    begin
      MsgBox(CustomMessage('ErrPwShort'), mbError, MB_OK);
      Result := False;
    end
    else if InstallPostgres and (DbPage.Values[3] <> DbPage.Values[4]) then
    begin
      MsgBox(CustomMessage('ErrPwMatch'), mbError, MB_OK);
      Result := False;
    end;
  end
  else if (CurPageID = wpReady) and (InstallPostgres or InstallMosquitto) then
  begin
    DownloadPage.Clear;
    if InstallPostgres then
      DownloadPage.Add('{#PgUrl}', 'postgresql-setup.exe', '{#PgSha256}');
    if InstallMosquitto then
      DownloadPage.Add('{#MqUrl}', 'mosquitto-setup.exe', '{#MqSha256}');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        if DownloadPage.AbortedByUser then
          Log('Download aborted by user.')
        else
          SuppressibleMsgBox(AddPeriod(GetExceptionMessage), mbCriticalError, MB_OK, IDOK);
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

{ ------------------------------------------------------------ install steps }

procedure Status(const Text: String);
begin
  WizardForm.StatusLabel.Caption := Text;
  WizardForm.FilenameLabel.Caption := '';
end;

function RunSecret(const Exe, Params: String): Integer;
begin
  { Never logs the parameters: they may hold a password. }
  if not Exec(Exe, Params, '', SW_HIDE, ewWaitUntilTerminated, Result) then
    Result := -1;
  Log(Format('%s -> %d', [Exe, Result]));
end;

function Run(const Exe, Params: String): Integer;
begin
  Log(Exe + ' ' + Params);
  Result := RunSecret(Exe, Params);
end;

procedure EnableService(const Name: String);
begin
  Run(ExpandConstant('{sys}\sc.exe'), 'config "' + Name + '" start= auto');
  Run(ExpandConstant('{sys}\net.exe'), 'start "' + Name + '"');
end;

procedure SetupPostgres;
var
  Code: Integer;
begin
  if InstallPostgres then
  begin
    Status(CustomMessage('StatusPg'));
    PgService := 'postgresql-x64-{#PgVersion}';
    Code := RunSecret(ExpandConstant('{tmp}\postgresql-setup.exe'),
      '--mode unattended --unattendedmodeui none --disable-components stackbuilder' +
      ' --superpassword "' + DbPage.Values[3] + '" --serverport ' + Trim(DbPage.Values[1]) +
      ' --servicename ' + PgService);
    if Code <> 0 then
      SuppressibleMsgBox(FmtMessage(CustomMessage('ErrInstall'), ['PostgreSQL', IntToStr(Code)]), mbError, MB_OK, IDOK);
  end;
  { An existing installation may be set to manual start: NestrisLTM needs it at boot. }
  if PgService <> '' then
    EnableService(PgService);
end;

procedure SetupMosquitto;
var
  Code: Integer;
  Conf, Ours, Current: AnsiString;
begin
  if not WizardIsComponentSelected('mosquitto') then
    Exit;
  if InstallMosquitto then
  begin
    Status(CustomMessage('StatusMq'));
    Code := Run(ExpandConstant('{tmp}\mosquitto-setup.exe'), '/S');
    if Code <> 0 then
    begin
      SuppressibleMsgBox(FmtMessage(CustomMessage('ErrInstall'), ['Mosquitto', IntToStr(Code)]), mbError, MB_OK, IDOK);
      Exit;
    end;
  end;
  Status(CustomMessage('StatusMqConf'));
  Conf := ExpandConstant('{commonpf64}\mosquitto\mosquitto.conf');
  LoadStringFromFile(ExpandConstant('{app}\mosquitto\mosquitto.conf'), Ours);
  if not LoadStringFromFile(Conf, Current) then
    Current := '';
  if Current <> Ours then
  begin
    if (Current <> '') and not FileExists(Conf + '.before-nestrisltm') then
      FileCopy(Conf, Conf + '.before-nestrisltm', True);
    ForceDirectories(ExpandConstant('{commonappdata}\mosquitto'));
    SaveStringToFile(Conf, Ours, False);
    Run(ExpandConstant('{sys}\net.exe'), 'stop mosquitto');
  end;
  EnableService('mosquitto');
end;

procedure SetupFirewall;
var
  Netsh: String;
begin
  if not WizardIsTaskSelected('firewall') then
    Exit;
  Status(CustomMessage('StatusFw'));
  Netsh := ExpandConstant('{sys}\netsh.exe');
  Run(Netsh, 'advfirewall firewall delete rule name="NestrisLTM (HTTP)"');
  Run(Netsh, 'advfirewall firewall add rule name="NestrisLTM (HTTP)" dir=in action=allow protocol=TCP localport={#HttpPort} remoteip=localsubnet profile=any');
  if WizardIsComponentSelected('mosquitto') then
  begin
    Run(Netsh, 'advfirewall firewall delete rule name="Mosquitto MQTT (NestrisLTM)"');
    Run(Netsh, 'advfirewall firewall add rule name="Mosquitto MQTT (NestrisLTM)" dir=in action=allow protocol=TCP localport=1883 remoteip=localsubnet profile=any');
  end;
end;

procedure ConfigureApp;
var
  Code: Integer;
  Cli, Params, Report: String;
  Lines: TArrayOfString;
  I: Integer;
  Text: String;
begin
  Status(CustomMessage('StatusConf'));
  Cli := ExpandConstant('{app}\{#CliExe}');
  Params := 'configure --db-host ' + AddQuotes(Trim(DbPage.Values[0])) +
    ' --db-port ' + Trim(DbPage.Values[1]) + ' --db-user ' + AddQuotes(Trim(DbPage.Values[2]));
  if DbPage.Values[3] <> '' then
    Params := Params + ' --db-password "' + DbPage.Values[3] + '"';
  ExecAsOriginalUser(Cli, Params, '', SW_HIDE, ewWaitUntilTerminated, Code);
  Log('configure -> ' + IntToStr(Code));

  if WizardIsTaskSelected('autostart') then
    ExecAsOriginalUser(Cli, 'autostart on', '', SW_HIDE, ewWaitUntilTerminated, Code)
  else
    ExecAsOriginalUser(Cli, 'autostart off', '', SW_HIDE, ewWaitUntilTerminated, Code);

  { Let a freshly (re)started broker and database come up before the check. }
  Sleep(3000);
  Report := ExpandConstant('{tmp}\check.txt');
  ExecAsOriginalUser(ExpandConstant('{cmd}'), '/C ""' + Cli + '" check > "' + Report + '" 2>&1"', '',
    SW_HIDE, ewWaitUntilTerminated, Code);
  Text := '';
  if LoadStringsFromFile(Report, Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
      Text := Text + Lines[I] + #13#10;
  CheckPage.RichEditViewer.Lines.Text := Text;
end;

procedure StopApp;
var
  Code: Integer;
begin
  { The tray app hides on close: end it hard; ingest state is spooled to disk. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#GuiExe}', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopApp;
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    SetupPostgres;
    SetupMosquitto;
    SetupFirewall;
    ConfigureApp;
  end;
end;

function InitializeUninstall: Boolean;
begin
  StopApp;
  Result := True;
end;
