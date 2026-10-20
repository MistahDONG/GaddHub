# Agentarkitektur

Projektets användarnamn är GäddHub; `GuildSyncDB` behålls som det preliminära
SavedVariables-namnet från GuildSync-briefen. Ingen omdöpning av repositoryt görs.

## Implementerat i detta steg

- Python 3.12+, gemensamt tkinter-fönster och valfritt pystray-stöd för Windows/Linux.
- Användarspecifik autostart via `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- Linux: XDG-datakatalog, `.desktop`-poster för autostart/programmeny och `flock`.
- Plattformsoberoende lösenordslagring i lokal `credentials.json`, i klartext enligt
  projektbeslut. Lösenorden hålls separata per endpoint och filen Git-ignoreras.
- Native filbevakning via watchdog, med storleks-/stabilitetskontroll,
  startkontroll och periodisk säkerhetsomläsning.
- Begränsad Lua-dataparser som inte exekverar kod.
- Versionshanterat JSON-schema i `schemas`, paketerat som resurs för agenten.
- SHA-256 över kanonisk JSON, beständig SQLite-kö och HTTPS POST.
- Separat bakgrundstråd för filhantering, kö och nätverk; tkinter används endast
  från huvudtråden. Systemfältets åtgärder förmedlas via en trådsäker kö.
- Native paketering med PyInstaller och automatiserade tester; CI-matris för
  Windows x64 och Ubuntu 24.04 x64. Taggar `agent-v*` ger releaseutkast med båda
  paketen, inte binärfiler i källkodshistoriken.
- Windowsinstaller med Inno Setup: användarspecifik installation, startmenygenväg
  och avinstallation. Linux behöver ingen installer.
- Förifylld, avsiktligt ogiltig exempel-HTTPS-adress för nya användare och en
  skrivskyddad aktivitetslogg längst ned i fönstret.

Källkoden ligger i `agent/src/gaddhub_agent`. Python-paketets manifest finns i roten
så att samma distribution kan inkludera det gemensamma schemat utan att duplicera
det. Backend, databas och webbportal implementeras inte i detta steg.
Addonets första testversion finns i `addon/GaddHub` med interface 16001 från
klientens GetBuildInfo-skärmbild. Den har separata insamlare och explicit
unsupported/error när API:er saknas eller ger oväntade resultat. Den är testad
mot Lua-API-testdubblar, inte ännu mot spelklientens verkliga export.

Addonet sparar `GuildSyncDB` kontogemensamt med senaste snapshot per UnitGUID
och senaste snapshot med observerad bank/recept, högst 100 totalt. Situationsdata
behåller originaltiden när en bank/professionsvy stängs. Eventburstar samlas ihop,
och slashkommandon ger manuell capture/diagnostik. Endast spelet skriver till
disk; addonet gör inte HTTP. Se `addon/README.md` för adapters och begränsningar.

`platform.py` väljer enbart `windows.py` eller `linux.py`. Parser, credentials,
SQLite-kö, HTTPS och inställningsmodeller känner inte till operativsystemets API:er.
På Windows används användarens LOCALAPPDATA; på Linux XDG_DATA_HOME (absolut)
med fallback till `~/.local/share`. Samtliga lokala agentfiler ligger i dess
`GaddHub`-underkatalog.

Linux-fönstret minimeras, aldrig göms helt, även om pystray rapporterar att ikonen
är synlig: en aktiv indikator är inte bevis för att skrivbordet faktiskt visar den.
GTK:s loop körs i egen tråd, medan tkinter stannar i huvudtråden.
Ikonimporten sker först när GUI:t startas, så exportvalidering inte kräver en
display eller fungerande systemfältsbackend. Saknat ikonstöd loggas och visas
uttryckligen i fönstret; synken kan fortsätta.

## Flöde

Konfigurerad `.lua` → stabil fil → begränsad parser → schemavalidering →
kanonisk JSON/hash → SQLite-kö → certifikatverifierad HTTPS → serverkvittens.

`watcher.py` använder watchdog Observer med Windows ReadDirectoryChangesW eller
Linux inotify. Kataloger bevakas icke-rekursivt och events filtreras mot exakt
konfigurerade filer. Create/modify/delete/move hanteras, inklusive atomisk
ersättning av filen; läsning/open/close-without-write triggar inte ny synk.
Callbacken köar endast berörda sökvägar i en låst mängd och väcker arbetstråden;
den använder inte tkinter, SQLite eller nätverk.

Arbetstråden samlar ihop events och återställer filens stabilitetsväntan även om
metadata inte ändrats. Storlek och ändringstid kontrolleras under väntan.
Efter stabilitetsperioden läses högst 8 MiB plus en kontrollbyte; metadata
kontrolleras igen efter läsningen. Inaktiva filer stat:as/läses inte varje tick.
En startkontroll och säkerhetsomläsning var 30:e sekund fångar missade events.
En samtidig filändring kan aldrig uteslutas helt genom metadata, så parsning och
schemavalidering är obligatoriska och felaktiga filer försöks igen senare.
Ingen åtkomst till spelets minne eller addonets nätverksfunktioner används.

Om exportkatalogen saknas bevakas närmaste befintliga förälder tills katalogen
skapats. Ändrade inställningar flyttar bevakningen. Döda bevakningstrådar upptäcks
och startas om; registreringsfel loggas uttryckligen och säkerhetsomläsningen
fortsätter. Bevakningen stoppas och join:as innan arbetstråden avslutas.
`poll_seconds` begränsar vilotiden för kö-/retrykontroll; events, inställningar
och Exit avbryter väntan direkt. Stabilitetsdeadline och säkerhetskontroll kan
förkorta väntan. Uppladdningsåterförsök kräver inte nya filändringar.

Hela filens snapshots valideras innan något från den läggs i kön. Vid nätverksavbrott
behålls kön över omstarter. Kvitterade payloads tas bort men hash och kvittenstid
behålls för dubblettkontroll. Köns payloads begränsas till 128 MiB; när gränsen nås
visas ett fel och filen försöks igen. Kvittenser är små men har ännu ingen
retentions-/städpolicy.

Kön är bunden till **exakt endpoint**. Byte av server skickar inte automatiskt
gamla köposter till en ny mottagare. Nu konfigurerade filer läses däremot in på nytt
för den nya endpointen. Gamla köposter finns kvar lokalt.

SQLite-kön lagrar källfilens basnamn, även över omstarter. Befintlig databas
migreras med en ny kolumn utan att köposter tas bort. Okända äldre filnamn markeras
uttryckligen och kan kompletteras när exporten läses om.

Python-loggning går både till roterande fil och via en köad handler till GUI:t.
Endast huvudtråden uppdaterar tkinter. GUI:t behåller de senaste 500 raderna,
visar INFO och högre oavsett filens inställda loggnivå och kopplar bort sin handler
vid avslut. Försök loggas före nätverksanropet; Success först efter godkänd
serverkvittens. Fel visar sanerad orsak och retrytid/paus/manuell åtgärd.
Lösenord, headers, payloads, svarsinnehåll och råa nätverksundantag loggas inte.
Filnamn citeras och kontrolltecken escape:as för att inte skapa falska loggrader.

Backoff börjar vid 2 sekunder och fördubblas till högst en timme, plus upp till fem
sekunders jitter. `Retry-After` (sekunder eller HTTP-datum) respekteras upp till 24
timmar. 401/403 pausar tills inställningarna sparas, manuell återförsökning sker
eller agenten startas om. Andra permanenta avvisningar kräver manuell återförsökning.

## Säkerhetsgränser

HTTPS är obligatoriskt. Certifikat verifieras, redirects följs inte och omgivningens
proxy-/`.netrc`-inställningar används inte. Därmed skickas inte lösenord vidare vid
omdirigering. Endast HTTP 200, 201 och 204 räknas som färdig serverkvittens; 202
betraktas inte som beständig lagring.

Det gemensamma lösenordet är en tillfällig åtkomstspärr. Det ersätter inte
guildisolering, enhetsåterkallelse eller verifiering av karaktärsägarskap.
Klientvalidering är ingen tillitsgräns: backend måste validera allt på nytt,
begränsa anropsstorlek, införa rate limits och göra idempotens atomärt.

Användarprofilens inställningar/kö/lösenordsfil skyddas av Windows
användarrättigheter, inte applikationskryptering. Den som kan läsa lösenordsfilen
kan använda det gemensamma lösenordet. Ingen inventering av andra addons eller
spelinstallationer utförs. Windows Credential Manager används inte längre;
befintliga användare behöver ange lösenordet på nytt.

Autostart gäller grafisk användarinloggning, inte uppstart före inloggning eller
en systemtjänst. Linux skriver XDG-autostart och programmenypost när inställningarna
sparas; Windows skriver Run-nyckeln. Flyttade installationer behöver sparas på nytt.

Windowsinstallern finns i `agent/installer/`. Den lägger programmet som standard
i `%LOCALAPPDATA%\Programs\GaddHub`, skilt från agentens datakatalog, och kräver
inte administratörsrättigheter. Befintlig autostart pekas om till installerad exe;
ny autostart skapas fortfarande genom agentens inställningsfönster.
En Windowsmutex hålls tills agentprocessen avslutas och kontrolleras av både
Setup och Uninstall. Körande agent ska avslutas via **Exit**, inte tvångsstängas.
Avinstalleraren tar bort sin egen autostart, inte en post som pekar på annan
installation, och lämnar lokal konfiguration/lösenord/kö kvar.

## Återstår

Verifierad addoninsamling/diskexport i klienten, faktisk backend, PostgreSQL och webbportal.
Linux native tester och paketbyggning är konfigurerade i CI men kan inte påstås
ha körts från Windowsmiljön. GNOME/KDE och Wayland behöver verkliga användartester;
Xvfb bevisar inte att en ikon visas i alla skrivbord. Första Linuxpaketet byggs
mot Ubuntu 24.04/glibc 2.39, inte alla Linuxdistributioner eller ARM.
Databasens historik/ordning kan inte garanteras av agenten: servern måste hålla
insamlingstid skild från mottagningstid och hindra äldre snapshots från att ersätta
nyare aktuell status. Borttagna exportfiler påverkar inte redan köade data.
