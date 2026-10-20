# GäddHub-agent (0.1.2)

Agenten bevakar konfigurerade SavedVariables-filer, läser ett begränsat Lua-dataformat,
validerar snapshots, köar dem lokalt och laddar upp JSON via HTTPS. Den har en ikon i
Windows systemfält eller Linux-skrivbordets indikatorfält samt ett inställningsfönster. Ingen fjärrdatabas
behövs för att utveckla eller testa agenten.

**Status:** Agenten är implementerad mot ett preliminärt kontrakt. Ingen faktisk
WoW Forever-export eller produktionsbackend är ännu verifierad. Testfilen är
syntetisk. Detta är inte en färdig end-to-end-integration med spelet.

### Starta från källkod

Windows 10/11 med Python 3.12 eller senare, inklusive tkinter, krävs.
Kör i PowerShell från repositoryts rot:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\pythonw.exe -m gaddhub_agent
```

I fönstret:

1. Ange **hela HTTPS-endpointen**. Förifylld adress är
   `https://gaddhub.example.invalid/v1/sync/snapshots`: ett avsiktligt icke-fungerande
   exempel som måste ersättas med en riktig serveradress. Befintlig konfigurerad
   adress behålls vid uppdatering.
2. Ange backendens gemensamma lösenord. Det sparas **i klartext i en lokal fil**,
   separat för varje endpoint, utanför repot.
   Använd utskrivbara ASCII-tecken utan blanksteg.
3. Välj addonets specifika `.lua`-exportfiler. Flera konton/installationer stöds
   genom flera filer; varje fil kan innehålla flera karaktärers snapshots.
4. Låt autostart vara markerad och klicka **Save and sync**.

Filbevakningen använder `watchdog` med operativsystemets events: Windows
ReadDirectoryChangesW och Linux inotify. Katalogerna bevakas, men bara valda
exportfiler triggar inläsning. Både skrivning och ersättning via temporär fil/
namnändring fångas. Flera events samlas ihop och filen måste därefter vara stabil
i minst två sekunder innan den läses.

Agenten läser även vid start och gör en säkerhetsomläsning var 30:e sekund.
Om bevakningen inte kan starta eller tappar en katalog visas ett loggmeddelande;
säkerhetskontrollen fortsätter och bevakningen återställs när det går.
Uppladdningskön och dess återförsök fungerar oberoende av nya filhändelser.
När inställningarna sparas uppdateras bevakade kataloger och vid **Exit** stoppas
bevakningens trådar.

Autostart sker **vid inloggning för den aktuella Windows-användaren**, inte före
inloggning som en systemtjänst. Registreringen använder användarens Windows Run-nyckel
och kräver inte administratörsrättigheter. Avmarkera och spara för att ta bort den.

Stängningskrysset döljer fönstret. Öppna genom att klicka på systemfältsikonen
eller högerklick → **Open GaddHub**. Välj **Exit** för att
avsluta agenten. Windows kan placera ikonen under systemfältets dolda ikoner.
Vid körning från källkod får repositoryt och Python-miljön inte flyttas efter
autostartregistreringen; spara inställningarna igen om installationen flyttas.

### Linux

Agenten körs nativt på Linux och läser SavedVariables även om spelet körs via Wine,
Lutris eller liknande. Välj filen i rätt Wine-prefix; agenten startar inte spelet.
En grafisk användarsession krävs för inställningsfönstret.

Första byggmålet är **Ubuntu 24.04 x86_64** (glibc 2.39). Andra distributioner och
ARM är inte verifierade. Ett Linux-paket måste byggas på Linux, inte på Windows.

För källkörning/byggning på Ubuntu 24.04, från repositoryts rot:

```bash
sudo apt-get install python3-venv python3-tk python3-gi gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 libgirepository-1.0-1 desktop-file-utils
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e ".[dev,build]"
.venv/bin/python -m gaddhub_agent
```

Systempaketen ger GTK/AppIndicator-stöd. `--system-site-packages` gör systemets
PyGObject tillgängligt i Python-miljön. Källkörning med annan Pythoninstallation
kräver motsvarande fungerande tkinter/PyGObject-installation.

Efter **Save and sync** skapas en startpost i
`~/.local/share/applications/gaddhub-agent.desktop`. Markerad autostart skapar
även `~/.config/autostart/gaddhub-agent.desktop`. `XDG_DATA_HOME` och
`XDG_CONFIG_HOME` respekteras om de är absoluta sökvägar. Avmarkerad autostart
tar bort autostartposten men behåller programmenyposten.

Linux-fönstret **minimeras i stället för att döljas**, även vid autostart, så att
det går att nå från fönsterlistan oberoende av systemfältsstöd. Ikonklick kan öppna
en meny där man väljer **Open GaddHub**, beroende på skrivbordet. GNOME kan kräva
ett AppIndicator-tillägg för att visa ikonen. GTK:s händelseloop körs separat
från tkinter. Om ikonstödet saknas visas en varning och synken fortsätter via
fönstret. En andra start skapar inte en andra agent, utan visar att den redan körs.

Linuxversionen måste fortfarande verifieras nativt i CI och mot riktiga
GNOME/KDE-sessioner. Windowskörda tester av Linuxkonfiguration ersätter inte detta.

### Bygg och hämta paket

För versionshantering, fullständiga verifieringskommandon, taggning och publicering,
följ [releaseguiden](../docs/releases.md). Nedan är en kort lokal byggöversikt.
Alla kommandon körs från repo-roten.

Windowsinstallern byggs ovanpå PyInstaller-paketet:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean agent\GaddHub.spec
.\agent\installer\build.ps1
```

Byggskriptet kräver **Inno Setup 6**, exempelvis installerat med
`winget install --exact --id JRSoftware.InnoSetup --scope user`.
Utdata är `dist\GaddHub-Setup-<version>-windows-x64.exe`.
Den installerar normalt i `%LOCALAPPDATA%\Programs\GaddHub`, skapar
startmenygenväg och avinstallerare, utan administratörsrättigheter.
Källorna finns i [installer/](installer/).

Vid ny installation aktiveras autostart när användaren sparar agentinställningarna.
Om en autostartpost redan finns uppdaterar installern den till installerad exe.
Avinstallation tar endast bort autostart om den pekar på just den installationen;
inställningar, lösenord och kö lämnas kvar i datakatalogen.
Avsluta agenten med **Exit** före uppdatering/avinstallation; dess Windowsmutex
hindrar annars installern från att ändra körande program.
Slutförandesidan erbjuder att starta agenten; tysta installationer gör det inte.

Det portabla Windowsalternativet finns också kvar:

Starta `dist\GaddHub\GaddHub.exe`. Behåll **hela** katalogen, inklusive `_internal`,
tillsammans. Python behöver inte installeras separat på måldatorn.
Flytta paketet till dess permanenta plats **innan** autostart aktiveras.
Paketet är inte kodsignerat; Windows SmartScreen kan därför visa en varning.

På Linux:

```bash
.venv/bin/python -m PyInstaller --noconfirm --clean agent/GaddHub.spec
tar -czf dist/GaddHub-linux-x64.tar.gz -C dist GaddHub
```

Kör `dist/GaddHub/GaddHub`. Behåll hela katalogen även på Linux. Linuxpaketet
förutsätter kompatibel glibc och en grafisk desktopmiljö; det är inte en universell
AppImage eller ett paket för Alpine/musl. Bygg på en äldre Linuxbas om äldre glibc
ska stödjas. Flytta paketet till permanent plats innan inställningarna sparas.

Byggda paket hör hemma i [GitHub Releases](https://github.com/MarcusSandell/GaddHub/releases),
inte i Git-historiken. Källkod för båda systemen finns här i samma repository.
Workflowen `.github/workflows/agent.yml` testar och bygger båda paketen nativt:

- `GaddHub-windows-x64.zip`
- `GaddHub-Setup-<version>-windows-x64.exe`
- `GaddHub-linux-x64.tar.gz`

Varje lyckad push/PR/manuell workflowkörning ger nedladdningsbara Actions-artifacts.
En pushad tagg med prefixet `agent-v`, exempelvis `agent-v0.1.2`, skapar efter
godkända byggen ett **releaseutkast** med plattformspaketen, Windowsinstallern och `SHA256SUMS.txt`.
Granska och publicera utkastet manuellt på GitHub. Ingen tagg har skapats eller
release publicerats som del av denna implementation.

### Tester och validering

```powershell
.\.venv\Scripts\python.exe -m pytest agent\tests -q
.\.venv\Scripts\python.exe -m ruff check agent schemas
.\.venv\Scripts\python.exe -m ruff format --check agent schemas
.\.venv\Scripts\python.exe -m pyright --pythonpath .venv\Scripts\python.exe
.\.venv\Scripts\python.exe -m gaddhub_agent --check-export agent\tests\fixtures\synthetic-savedvariables.lua
```

Valideringskommandot laddar inte upp något. Windows-gränssnittet kan dessutom
smoketestas i en interaktiv session (visar tillfälligt en ikon och ett fönster):

```powershell
$env:GADDHUB_UI_TEST = "1"
.\.venv\Scripts\python.exe -m pytest agent\tests\test_app.py agent\tests\test_windows.py -q
Remove-Item Env:\GADDHUB_UI_TEST
```

De automatiserade HTTPS-testerna startar en tillfällig lokal TLS-server med en
test-CA, verifierar riktiga HTTP-anrop och kontrollerar att obetrodda certifikat
avvisas. Produktionsagenten har ingen inställning som stänger av TLS-verifiering.
Tester, kodkontroller och paketvalidering är konfigurerade för GitHub Actions
på Windows och Ubuntu. Linuxspecifika fillås-/desktoptester körs bara på Linux.
Linux UI-tester körs med Xvfb och D-Bus:

```bash
sudo apt-get install xvfb xauth dbus-x11 desktop-file-utils
GADDHUB_UI_TEST=1 GDK_BACKEND=x11 dbus-run-session -- \
  xvfb-run -a .venv/bin/python -m pytest agent/tests -q
```

### Lokala filer och felsökning

Inställningar, kö och roterande loggar ligger i `%LOCALAPPDATA%\GaddHub`:
På Linux används `$XDG_DATA_HOME/GaddHub`, eller `~/.local/share/GaddHub` om
variabeln saknas/är relativ. Samtliga nedanstående filer ligger i samma datakatalog.

- `settings.json`: endpoint, valda filer, autostart, loggnivå och intervall.
- `credentials.json`: lösenord i klartext, separat för varje endpoint.
- `sync.sqlite3`: beständig kö, avvisade snapshots och kvittenser för dubblettkontroll.
- `agent.log`: sanerade status-/felmeddelanden, utan lösenord eller snapshots.

Längst ned i fönstret finns **Activity log**, en skrivskyddad, scrollbar logg med
de senaste 500 raderna, klockslag och nivå. **Clear log** tömmer bara fönstrets
historik, inte loggfilen eller synkkön. Fönsterhistoriken börjar om när agenten
startas; tidigare händelser finns i den roterande `agent.log`.

Loggen visar filändringar, väntan på stabil fil, validering och dubbletter.
Uppladdning loggas **före** nätverksanropet, med filnamn, serveradress och
försöksnummer. Därefter visas exempelvis:

```text
12:30:00 INFO Attempting to send snapshot from file "GuildSync.lua" to server https://gaddhub.example.invalid/v1/sync/snapshots (attempt 1).
12:30:01 WARNING Fail: snapshot from file "GuildSync.lua" to server https://gaddhub.example.invalid/v1/sync/snapshots. Connection failed: DNS lookup, connection refused or server/network unavailable. Next retry in 2.3 seconds.
```

Med en fungerande server och HTTP 200/201/204 visas i stället **Success**.
Agenten skickar snapshots från filen, inte hela Lua-filen. Filnamnet sparas i kön
så även återförsök efter omstart kan identifieras. Äldre köposter utan filnamn
markeras uttryckligen tills motsvarande export lästs om.

Timeout, anslutningsproblem, TLS-fel och HTTP-status skiljs åt. Vid fel visas
automatisk retrytid, paus för lösenordsfel eller behov av manuell återförsökning.
Saknad konfiguration och lokala filfel visas också. Loggen innehåller aldrig
lösenord, Authorization-header, hela snapshots, serversvarens innehåll eller
råa nätverksundantag.

Lösenordet ligger i datakatalogens `credentials.json`, utan kryptering.
Tomt lösenordsfält behåller det sparade lösenordet för den angivna endpointen.
Gamla endpointlösenord kan tas bort manuellt ur filen när agenten är avslutad.
Filen är Git-ignorerad som extra skydd mot oavsiktlig incheckning.
Om du använde versionen med Windows Credential Manager behöver lösenordet anges
och sparas igen. Äldre poster under `GaddHub.Agent` används inte längre och kan
tas bort manuellt i Windows Credential Manager.

Filbaserad lösenordslagring, synkkö och HTTPS delas mellan systemen. Datakatalog,
autostart och enkelinstanslås väljs utifrån operativsystemet.
Detta ändrar inte HTTPS-kravet eller certifikatverifieringen.

Kön innehåller privata karaktärsdata okrypterat i användarprofilen. Skydda
Windows-kontot och disken, exempelvis med BitLocker. Endast redan valda filer läses;
agenten söker inte igenom datorns spelinstallationer automatiskt.

- **401/403:** uppladdningar pausas. Rätta lösenordet och spara, eller välj **Retry now**.
- **429/nätverksfel/5xx:** automatiska återförsök med exponentiell backoff och jitter.
- **Övriga avvisningar:** behålls som avvisade i kön; inga täta återförsök.
  **Retry now** försöker även dessa igen.
- **Felaktig/låst export:** felet visas; filen kontrolleras igen.
- **TLS-fel:** åtgärda servercertifikatet; HTTP och certifikatundantag stöds inte.
- **Ingen ny data:** SavedVariables ändras inte nödvändigtvis förrän klienten sparar
  till disk. Agenten kan inte läsa förändringar som endast finns i spelets minne.

Intervallen `stable_seconds`, `poll_seconds` och `rescan_seconds` kan konfigureras
i inställningsfilen när agenten är avslutad. Standardvärdena är 2, 2 respektive 30
sekunder. `stable_seconds` styr väntan efter ett event, `rescan_seconds` styr
säkerhetsomläsning/återanslutning av bevakning och `poll_seconds` är den maximala
vilotiden för arbetstrådens kö-/retrykontroll, inte filpolling. Events, sparade
inställningar och avslut väcker tråden direkt. Under stabilitetsväntan eller
återhämtning från filfel kan filen kontrolleras oftare.
`log_level` kan vara `DEBUG`,
`INFO`, `WARNING` eller `ERROR` och styr filens loggnivå. Fönstrets aktivitetslogg
visar alltid INFO och högre så att uppladdningsförsök går att följa.

### Kontrakt och nästa steg

- [Aktuell överlämning och kodkarta](../docs/handoff.md)
- [Projektbrief och användarbeslut](../docs/project-brief.md)
- [Releaseguide](../docs/releases.md)
- [Arkitektur och begränsningar](../docs/architecture.md)
- [Export- och uppladdningskontrakt](../docs/agent-protocol.md)
- [WoW Forever-kompatibilitet](../docs/wow-forever-compatibility.md)
- [Gemensamt snapshot-schema](../schemas/snapshot-v1.schema.json)

Första [testaddonet](../addon/README.md) exporterar nu agentens befintliga format.
Klientens GetBuildInfo visar interface 16001; nästa steg är att verifiera verkliga
API-resultat/diskexport och implementera backendens mottagning. Det gemensamma
lösenordet är endast en grundläggande åtkomstspärr, inte bevis på användaridentitet,
guildmedlemskap eller karaktärsägarskap. En framtida privat guildportal behöver
separat användarautentisering och återkallbara enhetstokens.
