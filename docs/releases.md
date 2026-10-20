# Bygga och publicera agent och testaddon

Agent och addon ligger i samma repository men versionshanteras och paketeras
separat. Addon 0.1.0 är en första testversion, inte klientverifierad spelinsamling.

**Nuvarande status:** Windowsbygget för 0.1.2 är lokalt verifierat för GUI-start,
aktivitetsloggstart, exportvalidering och native filbevakning efter atomisk
filersättning, utan att invänta säkerhetskontroll. Windowsinstallern är ombyggd;
riktig installation, uppdatering och avinstallation testades för 0.1.0.
Installertesterna för 0.1.2 hoppades över för att skydda en befintlig
användarinstallation. Linuxbygge och
GitHub-releaseflöde är konfigurerade men inte körda i denna utvecklingssession.
Ingen release är publicerad. Följ stegen nedan; förekomsten av workflowen är inte
ett bevis på att en release redan finns.

## 1. Vad som byggs

| Plattform | Byggmiljö i CI | Fil |
| --- | --- | --- |
| Windows x64 | `windows-latest`, Python 3.12 x64 | `GaddHub-windows-x64.zip` |
| Windows-installer | PyInstaller-paket + Inno Setup 6 | `GaddHub-Setup-<version>-windows-x64.exe` |
| Linux x64 | Ubuntu 24.04, system-Python 3.12 | `GaddHub-linux-x64.tar.gz` |
| WoW-testaddon | Lua-källkod, arkiveras i Windowsjobbet | `GaddHub-addon-<addonversion>.zip` |

Addon-ZIP innehåller endast `GaddHub` med manifest och produktions-Lua, inte
API-testdubblar/tester. Dess version läses från `GaddHub.toc` i CI; uppdatera även
`Core.lua` när addonversionen ändras. Lägg inte till en gissad interface-version.
Första klientbeviset är 1.60.1/build 70450/interface 16001 från GetBuildInfo.
Se [addonets guide](../addon/README.md) för installation, test och lokalt ZIP-bygge.
De befintliga artifact-/draftrelease-stegen inkluderar även addon-ZIP:en.

Bygg varje plattform **nativt**. PyInstaller är inte en Windows-till-Linux-
korskompilator. Linuxpaketet är byggt mot Ubuntu 24.04/glibc 2.39, inte garanterat
för äldre glibc, Alpine/musl eller ARM. Ingen macOSrelease finns.

De portabla paketen innehåller en hel `GaddHub`-katalog med körbar fil och `_internal`.
Distribuera inte bara exe/binärfilen. Python ska inte behöva installeras separat
för det byggda paketet, men Linux behöver en kompatibel grafisk systemmiljö.
Paket är inte kodsignerade; Windows SmartScreen kan visa en varning.

Windowsinstallern lägger samma filer i `%LOCALAPPDATA%\Programs\GaddHub` som
standard, skapar startmenygenväg och registrerar avinstallation för användaren.
Ingen administratörselevation begärs. Linux distribueras endast portabelt;
ingen Linuxinstaller ska byggas.

Binärfiler, användarkonfiguration, lösenord och lokal databas får inte checkas in.
`build/` och `dist/` är Git-ignorerade. Nedladdningar publiceras på repositoryts
[GitHub Releases](https://github.com/MarcusSandell/GaddHub/releases).

## 2. Förbered källkoden

Kör alla lokala kommandon från **repo-roten**, inte från `agent/`.

1. Kontrollera `git status --short` och granska vilka ändringar som ska ingå.
   Lokala ändringar följer inte med en tagg förrän de committats. Kontrollera
   att den commit som ska taggas innehåller de senaste funktionerna.
2. Uppdatera versionen konsekvent. För närvarande finns agentversion i
   [pyproject.toml](../pyproject.toml),
   [__init__.py](../agent/src/gaddhub_agent/__init__.py). HTTP-`User-Agent` hämtar
   versionen därifrån automatiskt. Uppdatera också relevant
   dokumentation. Ändra inte `schema_version` enbart för att agenten får ny version.
3. Kör tester/kontroller nedan. Kontrollera att inga lösenord, privat exportdata
   eller lokala användarfiler finns bland filerna som ska committas.
4. Commit och push av endast granskade, avsedda filer görs innan en releasetagg.
   Använd inte `git add .` utan att först ha granskat alla otrackade filer.
5. Uppdatera [överlämningen](handoff.md) och
   [kompatibilitetsrapporten](wow-forever-compatibility.md) när faktiska bevis ändras.

Beroendena har för närvarande versionsintervall, inte låsta versioner. Byggen vid
olika datum kan därför få olika beroenden. Påstå inte att de är bitreproducerbara.

## 3. Windows: lokalt test och bygge

Python 3.12 x64 med tkinter krävs. Om miljön redan finns används den:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m ruff check agent schemas addon
.\.venv\Scripts\python.exe -m ruff format --check agent schemas addon
.\.venv\Scripts\python.exe -m pyright --pythonpath .venv\Scripts\python.exe
$env:GADDHUB_UI_TEST = "1"
.\.venv\Scripts\python.exe -m pytest agent\tests addon\tests -q
Remove-Item Env:\GADDHUB_UI_TEST
```

GUI-testerna öppnar tillfälligt ett fönster och en systemfältsikon. De kräver en
grafisk session. Linuxspecifika tester ska vara överhoppade på Windows.

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean agent\GaddHub.spec
$process = Start-Process -FilePath ".\dist\GaddHub\GaddHub.exe" -ArgumentList "--check-export", "agent\tests\fixtures\synthetic-savedvariables.lua" -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Paketets exportvalidering misslyckades" }
$process = Start-Process -FilePath ".\dist\GaddHub\GaddHub.exe" -ArgumentList "--check-export", "missing-export.lua" -Wait -PassThru
if ($process.ExitCode -ne 1) { throw "Saknad export avvisades inte korrekt" }
Compress-Archive -LiteralPath "dist\GaddHub" -DestinationPath "dist\GaddHub-windows-x64.zip" -Force
Get-FileHash -Algorithm SHA256 -LiteralPath "dist\GaddHub-windows-x64.zip"
```

`Start-Process -Wait` används eftersom exe:n är ett Windows GUI-program.
`missing-export.lua` ska inte finnas; välj ett annat säkert saknat filnamn om den
finns i din arbetskopia. Dessa kommandon validerar bara; de laddar inte upp data.
Undvik att återanvända gamla filer ur `dist/` som bevis på att senaste bygget lyckats.

### Kompilera Windowsinstallern

Installera Inno Setup 6 om det saknas:

```powershell
winget install --exact --id JRSoftware.InnoSetup --scope user
```

Efter ett lyckat PyInstaller-bygge:

```powershell
.\agent\installer\build.ps1
```

[Byggskriptet](../agent/installer/build.ps1) läser aktuell version från
`pyproject.toml` och kompilerar [Inno-skriptet](../agent/installer/GaddHub.iss).
Det söker efter `ISCC.exe` på PATH och i vanliga användar-/systeminstallationer.
Ange `-Compiler` vid en annan installation eller `-Python` om Pythonmiljön ligger
på annan plats. Installern hamnar i `dist\GaddHub-Setup-<version>-windows-x64.exe`.
Byggskriptet bygger inte om PyInstaller-programmet åt dig.

För separat integrationstest, exempel för version 0.1.2:

```powershell
$env:GADDHUB_INSTALLER = (Resolve-Path "dist\GaddHub-Setup-0.1.2-windows-x64.exe").Path
.\.venv\Scripts\python.exe -m pytest agent\tests\test_installer.py -q -rs
Remove-Item Env:\GADDHUB_INSTALLER
```

Kör detta i en **separat pytest-process**, inte med variabeln aktiverad för hela
testsviten: agent-/GUI-testerna håller avsiktligt en Windowsmutex tills deras
process avslutas, vilket ska blockera installation/avinstallation.

Testerna installerar till tillfällig katalog men använder riktiga användarposter
för startmeny/avinstallation och en egen syntetisk datamarkör. De städar sina
resurser och vägrar ändra befintlig GaddHub-installation, autostart eller genväg.
Överhoppade integrationstester är inte ett lyckat installationsbevis.
Kör därför helst på en ren testanvändare eller CI-runner.
Den installerade agentens testkörning får en isolerad datakatalog.

Verifierade scenarier omfattar startmenygenväg, avinstallationsregistrering,
installerad exportvalidering, uppdatering av befintlig autostart, databevarande,
avinstallationens autostartstädning och att en faktiskt körande installerad agent
blockerar både uppdatering och avinstallation.

### Användarbeteende

- Installerad standardplats: `%LOCALAPPDATA%\Programs\GaddHub`.
- Lokal konfiguration/lösenord/kö: `%LOCALAPPDATA%\GaddHub`, separat från programmet.
- Ny användare aktiverar autostart genom att spara inställningarna i agenten.
- En befintlig `GaddHubAgent`-autostartpost uppdateras till installerad exe.
- Startmenygenväg skapas. Slutförandesidan kan starta programmet.
- Tyst installation startar inte agenten automatiskt.
- Avsluta agenten med **Exit** innan uppdatering eller avinstallation, även om
  den körs från källkod/portabel katalog.
- Avinstalleraren tar bort program, genväg och sin egen autostartpost, men
  **behåller inställningar, klartextlösenord och kö**. Radera dessa manuellt från
  datakatalogen om de inte längre ska finnas kvar.
- Pekar autostart på en annan installation lämnas den posten orörd.

## 4. Linux: lokalt test och bygge

På Ubuntu 24.04 x86_64, i repo-roten:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-tk python3-gi gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 libgirepository-1.0-1 \
  desktop-file-utils xvfb xauth dbus-x11
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e ".[dev,build]"
.venv/bin/python -m ruff check agent schemas
.venv/bin/python -m ruff format --check agent schemas
.venv/bin/python -m pyright --pythonpath .venv/bin/python
GADDHUB_UI_TEST=1 GDK_BACKEND=x11 dbus-run-session -- \
  xvfb-run -a .venv/bin/python -m pytest agent/tests -q
.venv/bin/python -m PyInstaller --noconfirm --clean agent/GaddHub.spec
env -u DISPLAY -u WAYLAND_DISPLAY dist/GaddHub/GaddHub \
  --check-export agent/tests/fixtures/synthetic-savedvariables.lua
```

Den sista kommandoradens exitkod ska vara 0. Kontrollera också att ett faktiskt
saknat exportfilnamn ger exitkod 1. Avbryt vid misslyckat test/bygge; fortsätt inte
att paketera äldre utdata som om det vore den nya versionen.

```bash
tar -czf dist/GaddHub-linux-x64.tar.gz -C dist GaddHub
sha256sum dist/GaddHub-linux-x64.tar.gz
```

TAR bevarar körbarhetsrättigheter. Xvfb kontrollerar GUI-beteende, inte att en
indikator verkligen visas i GNOME/KDE/Wayland. Det behöver testas på riktiga
skrivbord innan Linuxreleasen godkänns.

## 5. GitHub Actions: bygg utan publicering

[Workflowen](../.github/workflows/agent.yml) heter **Agent tests and packages**.
Den körs vid branch-push, pull request, manuell start och `agent-v*`-taggar.

1. Pusha den granskade koden eller öppna en PR.
2. Öppna repositoryts **Actions** och välj workflowkörningen för rätt commit.
   Alternativt välj **Run workflow** på en pushad branch.
3. Båda jobben ska passera: tester, lint, typer, native bygge och validering av
   byggd körbar fil utan display. Windows bygger dessutom installern och kör
   de tre separata installationstesterna.
4. Hämta artifacts `GaddHub-windows-x64` och `GaddHub-linux-x64`.
   Actions artifact-nedladdningen kan lägga ett yttre ZIP runt själva paketfilen.

Windows kör GUI-tester. Linux installerar GTK/AppIndicator, använder en venv med
systempaket och kör GUI-tester via D-Bus/Xvfb. Native Linux-tester ska inte vara
överhoppade på Linux. Branch-/PR-/manuella körningar publicerar inte någon release.
Windows-artifacten innehåller både portabel ZIP och setup-exe.
Om Inno Setup saknas på Windows-runnern installeras det med Chocolatey.

Smoke-testet använder `Start-Process -Wait -PassThru` på Windows och läser
processens `ExitCode`, eftersom agenten är byggd som GUI-program. Direktstart
med `&` och omedelbar kontroll av `$LASTEXITCODE` kan annars rapportera fel
innan processen är klar, även om exporten är giltig. Giltig export ska ge 0
och saknad export 1; Linux behåller direktstart och `$LASTEXITCODE`.

### Manuellt testbygge trots testfel

Standardläget stoppar bygget vid testfel. För ett uttryckligt testbygge:

1. Pusha workflowändringen till standardbranchen.
2. Öppna **Actions → Agent tests and packages → Run workflow** och välj branch.
3. Aktivera **Build test artifacts despite failing tests (never create a release)**
   (`allow_test_failures`) och starta körningen.
4. Hämta `GaddHub-windows-x64-test-build` respektive
   `GaddHub-linux-x64-test-build` under **Artifacts**.

Alla tester körs fortfarande, inklusive smoke- och installertester, men testfel
stoppar inte paketering/uppladdning i detta manuella läge. Lint, typkontroll,
kompilering och arkivering måste fortfarande lyckas. En varning och en tabell
med teststegens faktiska `outcome` visas i körningssammanfattningen; ett grönt
jobb i detta läge betyder inte att alla tester passerat.

Valet är avstängt som standard och gäller inte push-/PR-/taggkörningar.
Manuella körningar kan aldrig skapa en release, inte heller när en tagg väljs.
Officiella releaseutkast kräver en `agent-v*`-taggpush och godkända tester
på båda plattformarna. Publicera inte dessa testartefakter som en release.

### Pyright hittar inte installerade paket

Om Pyright rapporterar saknade importer trots att installationen av
`.[dev,build]` lyckats, kontrollera vilken Pythoninterpreter typkontrollen använder.
Workflowen hämtar den fullständiga sökvägen från `sys.executable` och skickar den
till `--pythonpath`. Använd inte enbart `--pythonpath python`: lokalt gav det
19 fel och 4 varningar, medan samma kontroll med miljöns fullständiga
interpretersökväg gav 0 fel och 0 varningar.

Commit och pusha workflowändringen för att testa den i en ny körning.
**Re-run jobs** på den gamla körningen använder den gamla workflowversionen,
inte en senare lokal rättning. Windows-/Linuxbyggena måste fortfarande passera
i GitHub Actions innan en releasetagg skapas.

## 6. Tagga och skapa releaseutkast

Skapa inte taggen förrän ändringarna är committade, pushade och verifierade.
Följande är **exempelkommandon**, inte något agenten redan har utfört:

```powershell
git status --short
git --no-pager log -1 --oneline
git tag -a agent-v0.1.2 -m "GaddHub agent 0.1.2"
git push origin agent-v0.1.2
```

Förutsättningar: HEAD ska vara den avsedda verifierade committen och taggen ska
inte redan finnas. Använd aktuell versions tagg, inte alltid `agent-v0.1.2`.
Flytta eller skriv inte över en redan publicerad tagg; skapa en ny version.

Taggkörningen bygger båda plattformarna på nytt. Bara om **båda** lyckas skapas
ett **draft release** med:

- Windows ZIP
- Windows setup-exe
- Linux TAR.GZ
- `SHA256SUMS.txt` med hashar över de två arkiven och installern
- automatiskt genererade releaseanteckningar

Workflowen använder repositoryts `GITHUB_TOKEN`, inte en hemlighet incheckad i
koden. Byggjobben har läsrättighet, releasejobbet behöver `contents: write`.
Repository-/organisationspolicy kan blockera releaser; ett sådant fel måste
åtgärdas av behörig administratör, inte kringgås med incheckade tokens.
Om ett utkast redan finns kan `gh release create` misslyckas vid omkörning.
Inspektera det befintliga utkastet och dess commit/artefakter innan någon ändring;
publicera inte oavsiktligt blandade versioner.

## 7. Granska, testa och publicera

Öppna releaseutkastet i GitHub och kontrollera:

- rätt tagg/commit och överensstämmande agentversion;
- båda native CI-jobben är gröna för taggen;
- båda portabla paketfilerna, setup-exe och `SHA256SUMS.txt` finns;
- nedladdade arkiv matchar checksummefilen;
- paket kan packas upp/startas på rena Windows-/Linuxmaskiner;
- GUI, ikon eller fungerande fönsterfallback, lokal lösenordssparning,
  filsökvägar, autostart och avslut fungerar;
- HTTPS-uppladdning fungerar mot en kontrollerad kompatibel server;
- ingen privat export eller lokal inställning följt med i arkiven.

Prova också Windowsinstallern interaktivt: installationsplats, startmeny,
valfri programstart och avinstallation. Installera som vanlig användare utan UAC.
Kontrollera att befintlig konfiguration går att använda efter en uppdatering och
att lokala lösenord/kö finns kvar efter avinstallation enligt dokumenterat beteende.

Flytta installationen till permanent plats innan autostart sparas. På Windows
behövs en faktisk ny inloggning för slutlig autostartkontroll; på Linux behöver
programmenypost, autostart och skrivbordets ikonbeteende provas.

Redigera releaseanteckningarna med verklig verifieringsstatus, plattformskrav,
kända begränsningar och eventuell migration. Vid nuvarande prototypstatus är
**pre-release** lämpligt. Påstå inte verifierat spelstöd eller färdig MVP.
Klicka sedan manuellt **Publish release**. Att skapa en tagg publicerar inte
utkastet automatiskt.

SHA-256 kontrollerar filintegritet mot den publicerade listan men är inte
kodsignering eller en fristående garanti för utgivarens identitet.
