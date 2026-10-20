# Överlämning till nästa Copilot-agent

Senast uppdaterad: **2026-10-20**. Detta är en daterad statusbild. Kontrollera
aktuell Git-status och kod innan du fortsätter; rapporterade testresultat ska inte
presenteras som tester du själv just har kört.

## Läsordning

1. Detta dokument för status, beslut och nästa steg.
2. [Projektbrief](project-brief.md) för användarens krav och ändrad prioritering.
3. [Agentguide](../agent/README.md) för installation, GUI, tester och felsökning.
4. [Arkitektur](architecture.md) och [transportkontrakt](agent-protocol.md).
5. [Klientkompatibilitet](wow-forever-compatibility.md) före allt addonarbete.
6. [Releaseguide](releases.md) före byggning, taggning eller publicering.

Copilots automatiska startpunkt är
[.github/copilot-instructions.md](../.github/copilot-instructions.md).

## Vad som har hänt

- Repositoryt heter GäddHub. Briefen använde GuildSync; SavedVariables-namnet
  `GuildSyncDB` och JSON-kontraktet är preliminära.
- Användaren bad först om en commit, men arbetskopian var då ren. Det fanns redan
  initiala commits. Ingen implementation har committats av agenten i denna session.
- Eftersom ingen fjärrserver/databas finns tillgänglig byggdes agenten först.
- En Windows-agent med tray, GUI, lokal kö och HTTPS implementerades.
- Ursprunglig Credential Manager-lagring ersattes efter användarbeslut med lokal
  klartextfil. Återinför inte keyring av misstag som en förutsatt kravuppfyllelse.
- Linuxanpassning lades till i samma kodbas, inte som en separat applikation.
- Agent och addon fick separata rotkataloger. Addonkatalogen innehöll först
  bara dokumentation; första testimplementationen har nu tillkommit.
- CI och separata Windows-/Linuxpaket med releaseutkast konfigurerades.
- Projektkontext och releaseinstruktioner bevarades i Markdown.
- Därefter beställde användaren en **Windowsinstaller**, men ingen Linuxinstaller.
  Inno Setup har lagts ovanpå PyInstaller-paketet och byggts lokalt.
- Senaste önskemålet var en förifylld dummy-URL och ett enkelt felsökningsfält
  längst ned i fönstret. Detta är implementerat i **0.1.1**: reserverad
  `https://gaddhub.example.invalid/v1/sync/snapshots`, scrollbar aktivitetslogg
  med 500 rader, filnamn/försök/Success/Fail/felorsak/retry och bevarade filnamn
  i kön efter omstart. Befintlig endpoint skrivs inte över.
- Därefter beställde användaren native filbevakning i stället för polling som
  primär trigger. **0.1.2** använder watchdog på Windows/Linux med katalogevents,
  två sekunders stabilitetskontroll, startkontroll och säkerhetsomläsning var
  30:e sekund. Queue/retries är oberoende av nya events.
- Användaren har committat den tidigare implementationen som `db11e63`.
  Lokala `main` var en commit före `origin/main` vid senaste statuskontrollen.
  Watcherändringarna är inte committade; ingen commit/push/tagg görs automatiskt.
- Windows exe, ZIP och installer är ombyggda för 0.1.2. Användarens befintliga
  installation har inte ändrats eller stoppats; den behöver avslutas med
  **Exit** och uppdateras med den nya installern.

## Vad som finns och vad som är verifierat

### Senaste fasen: manuella testbyggen

- Körningen `39500713667` på commit `132a79e` stoppades före bygget av ett
  Tcl/Tk-initieringsfel i `test_log_is_visible_at_minimum_window_size`:
  159 passed, 5 skipped, 1 error. Alla 13 GUI-tester passerade lokalt vid
  efterföljande körning. Runnerfelets rotorsak är inte verifierad eller rättad.
- Användaren valde uttryckligen manuella testbyggen trots testfel, med fortsatt
  spärr för releaser. `workflow_dispatch` har nu booleanvalet
  `allow_test_failures`, avstängt som standard. Endast när valet aktiveras vid
  manuell start får pytest-, smoke- och installertester fallera utan att stoppa
  artefakter. Lint, typer och själva bygg-/arkivstegen får inte kringgås.
- Testartefakternas namn slutar på `-test-build`. Faktiska testutfall visas
  i en sammanfattning och körningen varnar att detta inte är releasematerial.
  Releasejobbet kräver nu uttryckligen taggpush, aldrig manuell körning.
  Vanliga push-/PR-/taggbyggen behåller testspärrarna.
- Lokalt verifierat med actionlint 1.7.7, 24 kombinationer av workflowens
  faktiska villkor (event, branch/tagg, input och testfel), samt exekvering av
  sammanfattningssteget med misslyckade testutfall. Ny manuell körning i
  GitHub Actions återstår efter commit/push.

### Senaste fasen: Pyright i GitHub Actions

- Körningen för rättningen, `39500165500` på commit `cc6ae0c`, kom vidare
  till Windowsbyggets smoke-test. Det kastade fel före utskriften
  `Valid export: 1 snapshot(s). No upload performed.` eftersom GUI-exe:n
  startades direkt och `$LASTEXITCODE` kontrollerades utan att invänta processen.
  Windowssteget använder nu `Start-Process -Wait -PassThru` och processens
  `ExitCode` för både giltig och saknad fil. Linuxstarten är oförändrad.
  Exakt rättat Windowssteg har körts lokalt mot det befintliga 0.1.2-paketet:
  giltig export gav 0 och saknad fil 1, trots avsiktligt gammalt
  `$LASTEXITCODE = 37`. Ny CI-körning återstår efter commit/push.
- Användaren har pushat till `MistahDONG/GaddHub`; lokal `origin` pekar nu dit.
  Actions-körningen `39499040863` misslyckades, med 19 fel och 4 varningar
  i Windowsjobbets `python -m pyright --pythonpath python`.
- Samma kommando återskapade lokalt exakt 19 fel och 4 varningar. Med den
  fullständiga interpretersökvägen från miljöns `sys.executable` gav Pyright
  0 fel och 0 varningar utan ändrade beroenden eller undertryckta diagnostikregler.
- Workflowen använder nu denna fullständiga sökväg för både Pyright-körning
  och `--pythonpath`. Den rättade Windows-/Linuxkörningen i CI återstår efter
  commit/push; ingen release eller lyckat Linuxbygge har verifierats här.
- Användaren rapporterar också att addonet skapade en riktig SavedVariables-fil.
  Filinnehåll, alla insamlingssektioner och agentens behandling av filen har
  ännu inte granskats. Detta ersätter inte klientverifiering av varje adapter.

### Senaste fasen: testaddon 0.1.0

- Användaren beställde addonet för speltest. GetBuildInfo-skärmbild visar
  **1.60.1, build 70450, Oct 15 2026, interface 16001**. Tidigare textuppgift
  build 69977 är ersatt; releasedatum/plattformar är inte självständigt verifierade.
- Addonet finns i `addon/GaddHub`, separat version **0.1.0**, med `GuildSyncDB`
  och oförändrat schema. Agenten är fortfarande **0.1.2**; ingen ny installer
  behövs för detta format. Agentens mappval/defaultsökväg är fortsatt uppskjutet
  på användarens uttryckliga besked; manuellt exportfilval gäller.
- Identitet kräver UnitGUID. Equipment, Classic-talents, modern profession/
  container-/receptadapter finns med runtimekontroller. Legacy skill-lines/recept
  och andra talent-system markeras unsupported tills de kan verifieras/adaptern byggas.
- Bank läses bara öppen. Senaste observationen av bank/recept behålls som eget
  snapshot med ursprunglig tid när senaste snapshotet inte längre har data där.
  Högst 100 totalt, inga delade tabellreferenser, ingen obegränsad eventhistorik.
  Recept är endast senaste observerade öppna profession, inte alla professioners union.
- Events har debounce; `/gaddhub capture`, `status`, `diag`, `help` finns.
  Addonet kan inte tvinga diskflush: använd reload/logout, verifiera i klienten.
- **160 passed, 5 skipped** för `pytest agent/tests addon/tests` med GUI aktiverat.
  **23 addontester** exekverar produktions-Lua i Lua 5.1 via Lupa, testar
  kapabiliteter, fel/UTF-8, bankretention/reload, nil-hål, kapacitet, events och
  serialiserad export genom riktig agentparser/schema/hash/SQLite-kö.
  Ruff, formatering och Pyright är godkända. Detta är testdubblar, inte spelbevis.
- CI testar båda katalogerna och arkiverar addon-ZIP med version från manifestet.
  Inga nya commits/push/taggar/releaser har skapats av agenten.
- Byggt paket: `dist/GaddHub-addon-0.1.0.zip` (8 256 byte). ZIP verifierad med
  exakt 10 produktionsfiler, rätt GaddHub-rot, interface 16001/version 0.1.0
  och samma bytes som källfilerna. Testdubblar/tester ingår inte.
- Nästa steg är att installera ZIP:en, köra `/gaddhub diag` och verifiera faktisk
  export/serialisering. Se `addon/README.md` och kompatibilitetsrapporten.

| Del | Implementationsstatus | Verifieringsstatus |
| --- | --- | --- |
| Lua-dataläsning och JSON-schema | Implementerat, begränsad grammar och resursgränser | Testat med syntetiska exporter |
| Kö, hash/dedupe, HTTP-hantering | Implementerat i SQLite/Python | Testat, även riktig lokal TLS-server |
| Windows GUI/tray/autostart/lås | Implementerat | GUI/tray/lås testade; registryautostart testad med mock, inte genom faktisk omstart |
| Lokal lösenordsfil och GUI-sparning | Implementerat | Roundtrip, felhantering och fönstersparning testade |
| Linux XDG/autostart/lås/tray | Implementerat | Portabla konfigurationstester körda på Windows; native Linux återstår |
| Windows PyInstaller-paket | Byggt lokalt | Packad exportvalidering godkänner giltig fil och avvisar saknad fil |
| Native filbevakning | Implementerat med watchdog | Riktiga Windows-events testade för skrivning, atomisk ersättning, återskapad fil/katalog, omkonfigurering och avslut; Linux native återstår |
| Windows Inno Setup-installer | 0.1.2 byggd lokalt | 0.1.0 installation/uppdatering/avinstallation testade; 0.1.2 integration överhoppad för att skydda befintlig installation |
| Linux PyInstaller-paket | Byggrecept/CI finns | Inget Linuxpaket byggt eller testat i denna session |
| GitHub Actions/Release | Workflow konfigurerad | Ingen remote körning, tagg eller publicering genomförd |
| Speladdon | 0.1.0 implementerat för test | Lua 5.1/testdubblar och agentkontrakt testade; verklig insamling/export återstår |
| Klientmetadata | Interface 16001 i manifest | GetBuildInfo-skärmbild: 1.60.1/build 70450; inga insamlings-API:er klientverifierade |
| Backend, PostgreSQL, auth, webb | Inte implementerat | Ingen full end-to-end-kedja |

Den nuvarande arbetsmiljön var Windows med Python 3.12.10. WSL/Linux kunde inte
köras och Docker fanns inte tillgängligt som alternativ. Det motiverar **inte**
att hävda Linuxkompatibilitet från Windowsresultaten.

### Senast faktiskt körda validering

Från repo-roten i en Windowsmiljö med installerade utvecklingsberoenden:

```powershell
$env:GADDHUB_UI_TEST = "1"
.\.venv\Scripts\python.exe -m pytest agent\tests -q
Remove-Item Env:\GADDHUB_UI_TEST
.\.venv\Scripts\python.exe -m ruff check agent schemas
.\.venv\Scripts\python.exe -m ruff format --check agent schemas
.\.venv\Scripts\python.exe -m pyright --pythonpath .venv\Scripts\python.exe
```

Resultat efter native filbevakning, version 0.1.2:

- **137 passed, 5 skipped** i vanliga pytest-sviten med GUI aktiverat. Två tester
  kräver native Linux (`flock`/desktopvalidering); tre installertester kräver
  separat explicit körning.
- Separat `GADDHUB_INSTALLER`-körning mot 0.1.2: **3 skipped** eftersom en
  användarinstallation redan finns. Inget installerades/avinstallerades av testerna.
  Tidigare 0.1.0-körning hade **3 passed** och testade faktisk installerad agentstart,
  blockering av uppdatering/avinstallation, genväg, autostart, uppdatering,
  databevarande och avinstallation. Det är inte ett nytt installationsbevis för 0.1.2.
- Ruff: godkänt. Formatering: **26 filer** godkända.
- Pyright: **0 errors, 0 warnings**.
- Windows native bygge med `agent/GaddHub.spec`: lyckat.
- Byggd exe: `--check-export` gav exit 0 för syntetisk fixture och exit 1 för
  saknad export. Ingen fil laddades upp av valideringskommandot.
- Packad GUI startades med isolerad LOCALAPPDATA och syntetisk export.
  Readiness-logg för **0.1.2** och aktiv native watcher verifierades.
  Atomisk filersättning gav två separata köade snapshots trots att både
  idle-/säkerhetsintervallet satts till 3600 sekunder; ingen säkerhetsskanning hann
  köras. Endpointen var lokal, med reserverad ej lyssnande port; ingen privat data
  skickades. Endast den egna testprocessen avslutades; testdatakatalogen städades.
- Lokal ZIP: `dist/GaddHub-windows-x64.zip`, även kopierad till tidigare
  `dist/GaddHub-windows.zip`. Båda innehåller ombyggd 0.1.2 och är Git-ignorerade.
- Byggd installer: `dist/GaddHub-Setup-0.1.2-windows-x64.exe`.
  Inno Setup 6.7.3 installerades lokalt via Winget för kompileringen.

Detta bevisar inte automatisk start efter verklig Windows-inloggning, funktion på
alla rena användardatorer, riktig speldata, produktionsserver eller Linuxdesktop.
Installerintegrationstesterna använder riktiga Windows-användarposter med skydd
mot befintlig installation/autostart/genväg; kör dem separat och helst på ren runner.

## Kodkarta

Alla sökvägar i tabellen är relativa till repo-roten.

| Fil/katalog | Ansvar |
| --- | --- |
| `pyproject.toml` | Gemensamt manifest, beroenden, CLI-entrypoint, test-/lint-/typinställningar |
| `agent/src/gaddhub_agent/app.py` | tkinter, inställningsflöde, tray, köad kommunikation mellan trådar |
| `agent/src/gaddhub_agent/platform.py` | OS-routing utan att importera Windowsmoduler på Linux |
| `agent/src/gaddhub_agent/windows.py` | LOCALAPPDATA, Run-registry, pythonw-startkommando, msvcrt-lås |
| `agent/src/gaddhub_agent/linux.py` | XDG-datakatalog, citerade `.desktop`-kommandon och flock |
| `agent/src/gaddhub_agent/credentials.py` | Endpointseparerade lösenord i lokal JSON-fil |
| `agent/src/gaddhub_agent/config.py` | Inställningar och HTTPS-URL-validering |
| `agent/src/gaddhub_agent/export.py` | Begränsad Lua-parser, JSON-schemavalidering och kanonisk hash |
| `agent/src/gaddhub_agent/store.py` | SQLite-kö, endpoint/hash-nyckel, återförsök och kvittenser |
| `agent/src/gaddhub_agent/sync.py` | Eventstyrd filinläsning, stabilitet, säkerhetskontroll, HTTP-status, backoff och statusrapportering |
| `agent/src/gaddhub_agent/watcher.py` | Native katalogbevakning, filtrering/coalescing, väckning, återanslutning och shutdown |
| `agent/tests/` | Parser-, credentials-, synk-, TLS-, CLI-, GUI- och plattformstester |
| `schemas/snapshot-v1.schema.json` | Delat, preliminärt schema paketerat som Python-resurs |
| `agent/GaddHub.spec`, `agent/launcher.py` | PyInstaller för native paket |
| `agent/installer/GaddHub.iss`, `agent/installer/build.ps1` | Användarspecifik Windowsinstaller, kompilering och avinstallation |
| `agent/tests/test_installer.py` | Opt-in integrationstest av verklig Windowsinstaller |
| `.github/workflows/agent.yml` | Windows/Linux test-, bygg-, artifact- och taggreleaseflöde |
| `addon/GaddHub/` | Testaddonets manifest, Core, Events och separata insamlingsmoduler |
| `addon/tests/` | Lua 5.1-testdubblar, verklig Lua-exekvering och agentkontraktstester |

## Beteenden som behöver bevaras

- Agenten skickar ett validerat snapshot som JSON, inte hela Lua-filen.
- File watcher är primär trigger, inte filpolling på varje tick.
  `poll_seconds` är maximal idle-tid för kö-/retrykontroll; callbacks väcker
  arbetstråden direkt, liksom inställningsändring och Exit.
  Bevara startkontroll, säkerhetsomläsning, stabilitetsväntan och oberoende retries.
  Watchertrådar får inte hantera GUI/SQLite/nätverk och måste stoppas vid avslut.
  Läs-events ignoreras så att agentens egen läsning inte skapar en loop.
  PyInstaller inkluderar native watchdog-backend uttryckligen.
- `.invalid`-endpointen är ett tydligt markerat exempel, inte en riktig server.
  Befintlig endpoint bevaras. Tom äldre endpoint får bara exempeltext i GUI:t
  tills användaren sparar.
- Loggen längst ned visar INFO och högre oberoende av filens `log_level`.
  Trådar skickar loggrader genom kön; GUI-handlern kopplas bort efter arbetarstopp.
  Inga lösenord, payloads, headers, svarsinnehåll eller råa nätverksundantag loggas.
- `uploads.source_name` migreras utan att tömma kön. `due()` behåller sin
  tre-tuple; `enqueue()` returnerar om snapshotet var nytt och tar valfritt filnamn.
  Äldre okända källnamn markeras uttryckligen och kompletteras vid omläsning.
- SavedVariables **exekveras aldrig**. Bara `GuildSyncDB` i en begränsad grammar
  accepteras. Verklig Forever-serialisering kan kräva ytterligare stödda syntaxfall.
- `available` kräver datafält; andra statusar får inte bära missvisande tomma data.
  Tomma Lua-`items` normaliseras till JSON-array, medan tom `build` är objekt.
- Filer måste vara stabila och läses periodiskt igen. Agenten kan bara se diskdata.
- Köposter och lösenord avgränsas per exakt endpoint. Serverbyte skickar inte
  gamla köposter automatiskt till den nya servern.
- 200/201/204 kvitterar; 401/403 pausar; 408/425/429/5xx återförsöks.
  Redirects följs inte. Backend ska kvittera dubbletter som lyckade, inte 409.
- `Retry now` återaktiverar även avvisade poster. Ingen tight retry-loop.
- Windows stängningskryss döljer till fungerande tray. Linux minimerar i stället
  för att riskera att användaren tappar åtkomsten när desktop saknar ikonstöd.
- GTK har egen eventlooptråd; tkinter manipuleras från huvudtråden.
- Autostart aktiveras när inställningarna sparas, vid användarinloggning.
- Installerad plats måste vara permanent innan autostart registreras.
- Windowsinstallern väljer normalt `%LOCALAPPDATA%\Programs\GaddHub` och
  uppdaterar en befintlig autostart dit. Avinstallation behåller lokala
  inställningar/lösenord/kö och tar bara bort autostart som pekar på installationen.
- `Local\GaddHub.Agent.Running` måste stämma mellan Windowskod och Inno-skript.
  Mutexen lever tills processen avslutas. Kör inte installertester i samma
  pytest-process som agent-/GUI-testerna, som avsiktligt håller mutexen.
- Lösenordsfilen är avsiktligt okrypterad, utanför repo. Inga riktiga lösenord
  får finnas i Git/loggar. HTTPS/TLS-kontroll får inte tas bort.

## Nästa arbete

1. Testa addon 0.1.0 i klienten enligt guiden och samla faktisk API-diagnostik/
   SavedVariables. Granska och committa avsedda addon-/CI-/dokumentationsändringar
   när användaren ber om det. Kontrollera aktuell Git-historik och pushbehörighet.
2. Efter godkänd commit/push: kör Actions för båda plattformarna. Åtgärda faktisk
   Linux-CI-feedback, särskilt GTK/PyInstaller, desktopfilvalidering och GUI-stopp.
3. Testa autostart på Windows och GNOME/KDE/Wayland på riktiga sessioner.
   Xvfb och `tray.visible` bevisar inte att användaren ser en ikon.
4. Testa nedladdade paket och Windowsinstaller interaktivt på rena maskiner. Publicera först ett granskat
   releaseutkast; ingen tagg/release har skapats här.
5. Klientversion/interface är nu kända. Skaffa faktisk export, verifiera
   API-returformaten och uppdatera kompatibilitetsrapporten. Implementera saknade
   adapters utifrån klientbevis. Tighta item-/talentmodeller först efter verkliga data.
6. Bygg sedan lokal backend/PostgreSQL/auth/webb enligt briefen. Delat lösenord
   bevisar inte guildmedlemskap eller karaktärsägarskap.

Kvarstående begränsningar: opaka item-/talentobjekt i schemat, ingen retention för
små kökvittenser, inga låsta beroendeversioner för reproducerbara releasebyggen,
ingen kodsignering och ingen native Linuxverifiering ännu. Dessa är inte
automatiskt uppdrag att bygga ut allt på en gång; följ användarens nästa prioritet.
