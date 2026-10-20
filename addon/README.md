# GaddHub-addon 0.1.0 - första testversionen

Installationsfilerna finns i [GaddHub/](GaddHub/). Addonet samlar egna
karaktärsdata i `GuildSyncDB`, som desktop-agenten kan läsa utan ändrat schema.
Det gör inga nätverksanrop och skriver inte filer självt.

**Klientmål:** användarens skärmbild från `GetBuildInfo()` visar **1.60.1,
build 70450, interface 16001**. Det verifierar manifestets interface-nummer,
inte att insamlings-API:erna fungerar i Forever. De kontrolleras vid körning.
Detta är en testversion, inte en klientcertifierad release.

## Installera och testa

1. Avsluta spelklienten. Packa upp addon-ZIP:en i installationens
   `Interface\AddOns`. Resultatet ska vara
   `Interface\AddOns\GaddHub\GaddHub.toc`, inte en extra nästlad GaddHub-mapp.
2. Starta klienten och aktivera **GaddHub** i addonlistan.
3. Logga in och kör `/gaddhub capture`, sedan `/gaddhub diag`.
4. Öppna banken och vänta några sekunder. Öppna också ett professionsfönster
   för att testa recept, om de nödvändiga API:erna finns.
5. Kör `/reload` eller logga ut. Addonet uppdaterar data i minnet;
   **det är spelklienten som sparar SavedVariables till disk**. Den faktiska
   skrivtidpunkten och serialiseringen i Forever behöver fortfarande verifieras.
6. Välj den skapade `GaddHub.lua`-filen under **Add files** i desktop-agenten.
   I vanlig WoW-struktur ligger den under
   `WTF\Account\<konto>\SavedVariables\GaddHub.lua`; Forever-sökvägen måste
   bekräftas i installationen. Välj inte addonets Lua-källkod.
7. Följ **Activity log**. Utan fungerande backend ska uppladdningen misslyckas
   med synligt fel medan snapshotet behålls i kön; dummy-URL:en är ingen server.

Mappval/automatisk filsökning i agenten är uttryckligen uppskjutet.
Python eller separat Lua behöver inte installeras för att använda addonet.

## Kommandon och automatiska uppdateringar

- `/gaddhub capture` eller `/gaddhub sync`: uppdaterar snapshotet i minnet.
- `/gaddhub status` eller `/gaddhub diag`: version/build/interface, API-förekomst,
  senaste insamlingstid, sektionsstatus och fel.
- `/gaddhub help`: kort hjälp.

Inloggning, världsinträde, utrustning, väskor, talents, skills, bank och
professionshändelser schemalägger en samlad insamling efter en kort lugn period.
Vid utloggning görs ett direkt sista försök. Okända event ger en synlig varning;
manuell insamling finns kvar. Ingen tomgångspollning körs varje bildruta.

## Datastöd och begränsningar

Alla sex sektioner finns alltid, med explicit status. `unsupported`,
`unavailable`, `not_collected` och `error` har förklaring och saknar datafält.
Fel i en insamlingsmodul visas i chatten och förstör inte övriga sektioner.

| Del | Första adaptern |
| --- | --- |
| Identitet | Egen `UnitGUID`, namn, realm, class-token, level, valfritt race/faction. Saknad identitet stoppar exporten; inget ID uppfinns. |
| Equipment | Utrustade slots 1-19 med item-ID och tillgänglig full itemlänk. Separata item level-/gem-/enchantmodeller återstår; rå länk bevaras. |
| Talents | Classic-tabbar med talentindex, rad/kolumn, rank/maxrank via `GetNumTalentTabs`/`GetTalentInfo`. Andra talangsystem markeras unsupported. |
| Professions | `GetProfessions`/`GetProfessionInfo`, även sekundära professioner trots nil-hål. Classic skill-line-adapter återstår om dessa API:er saknas. |
| Inventory | Strukturerade `C_Container`-API:er, ryggsäck och klientens vanliga bag-slots. Item-ID, bag/slot, count och länk. Ingen blind legacy-tupletolkning. |
| Bank | Endast medan banken är öppen, med Classic bankkonstanter och container-API:er. Ingen guild-/warbank. Ej inläst bank får inte bli en tom lista. |
| Recipes | Kräver full `C_TradeSkillUI`-enumerering och kontroll av länkad/guilddata. Endast inlärda recept för just den öppna professionen. Legacy-vyns filtrerade rader presenteras inte som en komplett lista. |

**API:ernas förekomst och returformat i Forever är ännu inte testade i spelet.**
Professions- och receptsektionerna kan därför visa `unsupported` tills vi har
klientens diagnostik och kan skriva en verifierad adapter. Recept från alla
professioner aggregeras inte i denna version; senaste tillgängliga observationen
av en öppen profession bevaras.

Exporten behåller senaste snapshotet per GUID samt senaste snapshotet med
observerad bank respektive recept, högst **100 snapshots totalt**. Därmed
försvinner inte en bankobservation innan logout när banken stängs, och äldre
bankdata får inte en ny falsk insamlingstid. Gemensamma kandidater sparas bara
en gång, utan delade tabellreferenser. Detta är inte en komplett händelsehistorik.
Vid full export eller okänt befintligt DB-format ges fel utan att tidigare
snapshots skrivs över. Säkerhetskopiera SavedVariables före manuella ingrepp.

## Tester och ZIP-bygge

Från repo-roten med projektets utvecklingsmiljö:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m pytest addon\tests -q
.\.venv\Scripts\python.exe -m ruff check agent schemas addon
.\.venv\Scripts\python.exe -m pyright --pythonpath .venv\Scripts\python.exe
New-Item -ItemType Directory -Path dist -Force
Compress-Archive -LiteralPath addon\GaddHub -DestinationPath dist\GaddHub-addon-0.1.0.zip -Force
```

Testerna exekverar de riktiga addonfilerna i **Lua 5.1 via Lupa**, med uttryckliga
WoW-API-testdubblar. En testserialiserad export går genom agentens riktiga
parser, JSON-schema, hash och SQLite-kö. Detta bevisar Lua-/kontraktsbeteende,
**inte WoW Forevers API-stöd, diskserialisering eller framgångsrik spelintegration**.
Testdubblarna ligger utanför addonmappen och ingår inte i installationspaketet.
CI kör addon- och agenttester; Windowsjobbet arkiverar även addon-ZIP:en.

Agentversionen är separat (0.1.2); en ny agentinstaller behövs inte för detta
oförändrade exportformat. Addonversionen finns i manifestet och `Core.lua`.

Se [klientbevis och nästa verifiering](../docs/wow-forever-compatibility.md),
[exportkontraktet](../docs/agent-protocol.md) och
[överlämningen](../docs/handoff.md).
