# GäddHub

BARA FÖR MEDLEMMAR I GUILDEN GÄDDA 🐟

GäddHub ska samla karaktärsdata från WoW Forever och visa guildens senast
synkroniserade information på en privat webbportal.

## Repository-struktur

| Katalog | Innehåll |
| --- | --- |
| [agent/](agent/) | Gemensam Python-agent för Windows och Linux, tester och native paketering |
| [addon/](addon/) | Första Lua-testaddonet, installation, diagnostik och kontraktstester |
| [schemas/](schemas/) | Gemensamt, preliminärt snapshot-schema |
| [docs/](docs/) | Arkitektur, exportkontrakt och klientkompatibilitet |

Agent och addon utvecklas i **samma repository**, men hålls separerade direkt i
repo-roten. Python-manifestet `pyproject.toml` ligger i roten så att agenten kan
paketera det gemensamma schemat utan att duplicera det. Backend och webbportal
är ännu inte implementerade.

## Agent och nedladdningar

Agenten läser konfigurerade SavedVariables-filer, validerar data, köar lokalt och
laddar upp JSON via HTTPS. Windows och Linux delar parser, schema, kö och
uppladdningslogik; plattformsspecifika funktioner hålls separata.

Filändringar upptäcks primärt genom native filsystemevents. Agenten väntar på en
stabil fil innan den läser, kontrollerar filer vid start och säkerhetsläser dem
var 30:e sekund om events missas. Nätverksåterförsök kräver ingen ny filändring.

Se [agentens installations- och utvecklingsguide](agent/README.md) för
konfiguration, autostart, Linuxberoenden, tester och byggning.

Färdigbyggda paket distribueras via
[GitHub Releases](https://github.com/MarcusSandell/GaddHub/releases), inte som
binärfiler i Git-historiken. CI är konfigurerad för att bygga Windows x64 och
Ubuntu 24.04/Linux x64. Push av en `agent-v*`-tagg skapar ett releaseutkast efter
godkända tester och byggen; utkastet publiceras manuellt. Ingen release har
publicerats ännu.

### Installera på Windows

Windows får en **Inno Setup-installer**: `GaddHub-Setup-<version>-windows-x64.exe`.
Kör den för att installera för den aktuella användaren, normalt i
`%LOCALAPPDATA%\Programs\GaddHub`, utan administratörsrättigheter. Installern
skapar en startmenygenväg och registrerar avinstallation i Windows.

Starta programmet, ersätt exempeladressen
`https://gaddhub.example.invalid/v1/sync/snapshots` med rätt HTTPS-endpoint,
fyll i lösenord och exportfiler och välj **Save and sync**.
Exempeladressen är ingen fungerande server; befintlig serveradress bevaras vid
uppdatering. Längst ned visar **Activity log** filnamn, uppladdningsförsök,
**Success/Fail**, felorsak och nästa återförsök, utan att logga lösenord.
Autostart styrs fortfarande av agentens inställning. Befintlig autostart
flyttas till den installerade exe:n vid installation/uppdatering.
Avsluta agenten med **Exit** före uppdatering eller avinstallation.
Lokala inställningar, lösenord och kö **behålls vid avinstallation**.

Linux behöver ingen installer; använd det portabla TAR.GZ-paketet.
Windows ZIP finns kvar som portabelt alternativ.

## Bygg en release

### Testa addonet

Första testversionen är **GaddHub 0.1.0**, med interface **16001** från klientens
GetBuildInfo-skärmbild. Installera addonmappen i `Interface\AddOns`, kör
`/gaddhub capture` och `/gaddhub diag`, och reloada/logga ut för diskexport.
Välj sedan addonets SavedVariables-fil `GaddHub.lua` i agenten.
API-stöd och verklig diskexport behöver fortfarande verifieras i Forever.
Se [addonets installations- och testguide](addon/README.md) för exakta steg,
datastöd och begränsningar. Detta är separat från Windowsagentens installer.

### Bygg agenten och addonet

Alla kommandon körs från repo-roten. På Windows, med Python 3.12 x64:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m pytest agent\tests addon\tests -q
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean agent\GaddHub.spec
winget install --exact --id JRSoftware.InnoSetup --scope user
.\agent\installer\build.ps1
Compress-Archive -LiteralPath "dist\GaddHub" -DestinationPath "dist\GaddHub-windows-x64.zip" -Force
Compress-Archive -LiteralPath "addon\GaddHub" -DestinationPath "dist\GaddHub-addon-0.1.0.zip" -Force
```

Inno Setup behöver bara installeras om kompilatorn saknas. Byggskriptet läser
versionen från Python-manifestet och skapar installern i `dist`.

På Linux krävs ett native Linuxbygge med systemberoenden enligt
[releaseguiden](docs/releases.md); Windows kan inte korskompilera det paketet.
Hela `GaddHub`-katalogen ska distribueras, inte bara exe/binärfilen.

För release av båda plattformarna:

1. Uppdatera versionerna, testa och committa/pusha endast granskade filer.
2. Kontrollera Windows- och Linuxjobben i **Actions → Agent tests and packages**.
3. Tagga den avsedda committen, exempelvis `agent-v0.1.2`, och pusha taggen.
4. När båda native byggen lyckats skapar workflowen ett releaseutkast med
   Windows-installer, Windows ZIP, Linux TAR.GZ, addon-ZIP och SHA-256-checksummor.
5. Testa de nedladdade paketen, granska anteckningarna och publicera utkastet
   manuellt i **Releases**, lämpligen som pre-release under prototypfasen.

Se [fullständig releaseguide](docs/releases.md) för exakta kommandon, GUI-/TLS-
kontroller, Linuxberoenden, versionsställen och felsökning.

## Verifieringsstatus

Exportkontraktet är preliminärt. Ingen riktig WoW Forever-export eller
produktionsbackend är verifierad. Testdata är syntetiska. Linuxstödet behöver
native CI och test i användarnas skrivbordsmiljöer innan en Linuxrelease godkänns.

Senaste Windowskörningen för **agent 0.1.2 + addon 0.1.0**:
**160 tester godkända, 5 överhoppade**
(2 kräver Linux, 3 kräver separat installer-testkörning).
De 23 addontesterna exekverar riktig Lua 5.1-kod mot WoW-testdubblar och
validerar exporten i agenten; det är ännu inte bevis på fungerande spelinsamling.
Ruff, formatering och Pyright är gröna. Den ombyggda exe:n har också startats
med isolerad datakatalog och verifierats för GUI, loggstart, exportvalidering och
riktig filbevakning: atomisk filersättning gav ett nytt snapshot innan någon
periodisk säkerhetskontroll körts.
Installern är ombyggd; dess separata integrationstester hoppades över eftersom
en verklig användarinstallation finns och inte får ändras av testerna.
**0.1.0** hade tidigare 3 godkända verkliga installertester, inklusive uppdatering,
avinstallation och skydd för körande agent. Detta är daterad status, inte ett
löfte om att CI redan har körts eller att en release har publicerats.

## Kontext för nästa Copilot-agent

Startpunkten är [.github/copilot-instructions.md](.github/copilot-instructions.md).
Läs sedan:

- [Överlämning: aktuell status, kodkarta, testbevis och nästa steg](docs/handoff.md)
- [Projektbrief: mål, krav och senare användarbeslut](docs/project-brief.md)
- [Bygga, tagga och publicera releaser](docs/releases.md)
- [Arkitektur](docs/architecture.md)
- [Export- och uppladdningskontrakt](docs/agent-protocol.md)
- [Klientkompatibilitet och nästa addonsteg](docs/wow-forever-compatibility.md)

Uppdatera överlämningen efter nästa arbetsfas så att verifierade resultat och
återstående arbete inte försvinner mellan agentsessioner.
