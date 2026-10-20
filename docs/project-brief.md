# Projektbrief och beslut

Detta dokument bevarar användarens projektkrav och senare beslut från
uppstarten den 20 oktober 2026. Det beskriver **mål**, inte en lista över redan
implementerade funktioner. Aktuell status finns i [överlämningen](handoff.md).

## 1. Identitet och mål

- Repository: `MarcusSandell/GaddHub`, projektets användarnamn **GäddHub**.
- Den ursprungliga briefen hette **GuildSync**. `GuildSyncDB` är fortfarande det
  preliminära SavedVariables-namnet. Ingen ny repositoryomdöpning är beslutad.
- Plattform: World of Warcraft Forever. Användarens GetBuildInfo-skärmbild visar
  1.60.1, build 70450, interface 16001; insamlings-API:erna återstår att verifiera.
- Målgrupp: medlemmar i guilden Gädda.
- Mål: automatiskt samla, synkronisera, lagra och visa guildmedlemmars
  karaktärsdata på en privat, inloggningsskyddad webbportal.
- Offlinekaraktärer ska kunna visas genom senaste faktiskt mottagna snapshotet,
  med tydliga tidsstämplar. Detta är inte realtidsåtkomst till spelminnet.
- Ingen Discord-bot, inga Discord-kommandon och ingen Discord-inloggning ingår.

## 2. Senare beslut som ändrar genomförandeordningen

Den ursprungliga planen började med klientförstudie och addon. Användaren har
sedan uttryckligen beslutat följande:

1. Fjärrservern som ska tillhandahålla databasen är inte tillgänglig ännu.
   **Desktop-agenten byggs först** utan beroende av den.
2. Agenten ska starta automatiskt vid användarinloggning, ha systemfältsikon
   och kunna öppna ett inställningsfönster.
3. Fönstret ska låta användaren ange uppladdningsadress och gemensamt lösenord.
   Användaren väljer även de exportfiler som agenten ska läsa.
4. Agenten ska bearbeta SavedVariables lokalt, inte skicka hela Lua-filen:
   säker dataläsning, snapshotvalidering, lokal kö, dubblettkontroll och JSON POST.
5. Kommunikation ska alltid vara **HTTPS** med verifierade certifikat.
6. Det gemensamma lösenordet är en enkel åtkomstspärr för backend, inte en
   fullständig kontolösning. Användaren har godkänt **lokal klartextfil** och
   avstått från Windows Credential Manager. Det får inte hamna i Git.
7. Även Linuxanvändare ska kunna köra agenten. Godkänt upplägg är **en gemensam
   kodbas**, plattformsanpassningar och separata native byggda paket.
8. Agent och addon ska leva i samma repository i separata rotkataloger.
9. Färdigbyggda Windows-/Linuxpaket ska distribueras genom GitHub Releases i
   stället för att checkas in som stora binärer.
10. Projektkontext och releaseinstruktioner ska finnas i Markdown för nästa agent.
11. Windows ska dessutom ha en vanlig installer. Godkänt upplägg är PyInstaller
    för programmet och Inno Setup för installation, genväg och avinstallation.
    Linuxanvändare behöver ingen installer och behåller portabelt paket.

Uppstart innan någon har loggat in skulle kräva en systemtjänst. Nuvarande
överenskomna implementation gäller **grafisk användarinloggning**.

## 3. Målarkitektur

```text
WoW Forever-addon (Lua)
    -> SavedVariables på disk
    -> desktop-agent (Python, Windows/Linux)
    -> HTTPS API
    -> PostgreSQL
    -> autentiserad webbportal
```

| Del | Målstack och ansvar |
| --- | --- |
| Addon | Lua, tillåtna klient-API:er, modulär insamling, SavedVariables, status och slash-diagnostik |
| Agent | Python, filbevakning/polling, validering, beständig kö, återförsök, GUI och autostart |
| Backend | FastAPI, Pydantic, SQLAlchemy eller motsvarande, Alembic och PostgreSQL |
| Webb | Next.js, TypeScript, React, mörk responsiv design och serverkontrollerad åtkomst |
| Drift | En Linux-VPS med Docker Compose, HTTPS, health checks, persistenta volymer och separat backupdestination |

Rekommenderade backend-/webbstackar är inte installerade eller implementerade.
Autentiseringstjänst är inte vald; Supabase Auth är ett möjligt, inte beslutat,
alternativ. Använd etablerad sessions-/identitetshantering när den delen byggs.

## 4. Krav på klientförstudie och addon

Verifiera klientversion, addonmiljö, tillåtna API:er och faktisk serialisering innan
datatyper påstås stödas. Befintliga addons får användas som referens först efter
licenskontroll. Addonet får inte göra HTTP-anrop, läsa godtyckliga filer eller
kringgå spelklientens begränsningar.

Förstudien ska testa identitet, gear och talents i ett minimalt addon, undersöka
övriga datatyper och dokumentera API:er, fel, begränsningar samt reproducerbara
tester i [kompatibilitetsrapporten](wow-forever-compatibility.md).
När SavedVariables faktiskt skrivs måste testas, exempelvis vid reload/utloggning;
en spelhändelse innebär inte automatiskt en diskuppdatering.

En mock eller syntetisk fixture får bara bevisa transport-/schemahantering,
inte att spelet exporterar datan. Ingen `.toc`-klientversion ska gissas.

## 5. Datakrav och snapshots

Varje datatyp ska ha en separat insamlingsmodul i addonet:

| Datatyp | Avsedd information, där den är verifierbart tillgänglig |
| --- | --- |
| Karaktär | Namn, stabil identifierare, realm, klass, level, race, faction, spec/roll |
| Gear | Utrustad slot, item-ID/-namn/-länk, kvalitet, item level, enchants, gems, sockets och modifierare |
| Talents | Träd, valda talents, ranker, aktiv spec/build och insamlingstid |
| Professions | Profession, skill, max skill, specialisering och verifierade extrafält |
| Inventory | Väskor, slots, item-ID/-länk, antal och eventuella charges |
| Bank | Separat från inventory; skilj aldrig inspekterad från tom; separat synlighet |
| Recept | Recept-ID/-namn, profession, eventuella skillkrav och verifierad metadata |
| Historik | Faktiskt mottagna snapshots och jämförelser av verkligt observerade förändringar |

Karaktärsnamn ensamt får inte vara primärnyckel. En alternativ deterministisk
identitetsstrategi måste dokumenteras om klienten saknar stabil identifierare.
Den strategin är ännu inte vald eller verifierad.

Snapshots ska vara versionshanterade, inkludera addonversion och separera
insamlingstid från serverns mottagningstid. Det delade
[JSON-schemat](../schemas/snapshot-v1.schema.json) ska användas av agent/backend
och mot addonexporter i integrationstester.

Sektioner ska kunna ha `available`, `not_collected`, `unavailable`, `unsupported`
eller `error`. En tom datalista betyder en faktiskt insamlad tom lista, inte
saknade data. Nuvarande kontrakt utelämnar därför datafält för icke-`available`
sektioner, till skillnad från några av den ursprungliga briefens exempel.

Sparade builds ska ha namn, anteckningar, talentdata och skapad/uppdaterad tid.
De är referenssnapshots; lova inte automatisk återställning/import i spelet utan
verifierat stöd. Hitta inte på DPS-beräkningar eller historiska lagersaldon.

## 6. Agentkrav

- Stöd flera karaktärer och installationer, med explicit valda filer.
- Vänta på stabil fil, hantera lås och avbrutna skrivningar.
- Använd aldrig Lua-exekvering för att läsa SavedVariables.
- Validera format/version, beräkna innehållshash och undvik identiska uppladdningar.
- Behåll kö och lyckade kvittenser över omstarter.
- Återförsök nätverksfel, rate limits och tillfälliga serverfel med backoff.
- Visa tydliga fel för felaktig export, okänd version och nekad autentisering.
- Visa senaste lyckade synk. Logga inte lösenord eller hela privata payloads.
- Förifyll en tydligt markerad dummy-URL vid ny installation; skriv inte över
  användarens befintliga endpoint. Exempeladressen ska inte låtsas fungera.
- Visa en enkel aktivitetslogg längst ned i fönstret med filnamn, skickförsök,
  Success/Fail, sanerad felorsak och kommande retry eller nödvändig åtgärd.
- Efter användarbeslut används native filsystemevents som primär trigger.
  Filhändelser får inte vara enda sanningskällan: startkontroll och periodisk
  full omläsning behålls som säkerhetsnät, liksom stabilitetskontroll och retries.
- HTTPS och certifikatverifiering är obligatoriska även med ett enkelt lösenord.

Se [arkitekturen](architecture.md) och [protokollet](agent-protocol.md) för exakt
nuvarande implementation, storleksgränser och HTTP-beteende.

## 7. Backend, autentisering och databas: framtida krav

API:t ska versionshanteras under `/v1`. Hanterad autentisering bör inte
återimplementeras genom egna register/login-endpoints om leverantören sköter dem.
Använd e-postverifiering vid e-postregistrering och korrekt återställning,
sessionshantering samt brute-force-skydd.

Guildinbjudningar ska vara slumpmässiga, hashade i lagring, tidsbegränsade och
återkallbara. Medlemskap har roller `member`, `officer`, `admin` och explicit status.
Varje endpoint måste kontrollera identitet, roll, guild och karaktärsägarskap
server-side. Klientens `user_id` eller `guild_id` är aldrig tillräckligt bevis.

Målflöde för enheter: autentiserad medlem i guilden kopplar agenten via
tidsbegränsad engångskod, får separat begränsad enhetstoken och kan återkalla
den individuellt. Nuvarande delade lösenord implementerar **inte** detta.

Huvudentiteter enligt briefen:

- `users`, `guilds`, `guild_memberships`, `characters`
- `character_snapshots`, `equipment_items`, `talent_builds`, `professions`
- `inventory_snapshots` (bag/bank), `known_recipes`, `sync_devices`

Använd främmande nycklar, relevanta index/unikhetsregler och Alembic-migreringar
från tom databas. Fullt validerat snapshot kan lagras i JSONB; normalisera där
sökning, jämförelser eller integritet motiverar det.

Lagra tidigare snapshots oförändrade. Idempotens måste vara atomär även vid
parallella uppladdningar. Äldre snapshots får sparas som historik men inte
ersätta nyare aktuell status. Backend måste själv validera payload, schema och
storlek; agentens kontroll är inte en tillitsgräns.

### Avsedda endpointgrupper

Alla vägar nedan ligger under `/v1` och är **planerade**, inte implementerade:

| Grupp | Vägar |
| --- | --- |
| Auth | `POST /auth/register`, `/auth/login`, `/auth/logout`; `GET /auth/me` eller delegering till vald auth-tjänst |
| Guild | `POST /guilds`, `/guilds/join`; `GET /guilds/{guild_id}`, `/guilds/{guild_id}/members` |
| Admin | `PATCH /guilds/{guild_id}/members/{membership_id}`; `POST /guilds/{guild_id}/invites` |
| Enheter | `POST /devices/pair`; `GET /devices`; `POST /devices/{device_id}/revoke` |
| Synk | `POST /sync/snapshots`; `GET /sync/status`, `/sync/history` |
| Karaktärer | `GET /guilds/{guild_id}/characters`; `GET /characters/{character_id}` |
| Sektioner | `GET /characters/{character_id}/snapshots`, `/equipment`, `/talents`, `/professions`, `/inventory`, `/recipes`, `/history` med samma karaktärsprefix |
| Sök/jämför | `GET /guilds/{guild_id}/search`; `POST /guilds/{guild_id}/characters/compare` |

Alla endpoints behöver definierade modeller, autentiseringskrav, felkoder och
tester. Listor ska pagineras och rimlig filtrering ske på servern. Framtida
inbjudningsåterkallelse, buildhantering, dataexport och radering behöver också
tydliga API-kontrakt; briefens endpointlista täcker inte allt.

## 8. Webbportal, sekretess och drift

Portalen ska ha login/logout, guildöversikt/roster, karaktärsinspektion med
gear/talents/professions/inventory/bank/recept/historik, sparade builds,
professions-/craftingsökning, jämförelser, synkstatus, konto-/enhetsinställningar
och rollskyddad administration.

Roster ska ha sökning, sortering, paginering och filter på klass, level,
profession, tillgänglig gear/item level och senaste synk. Visa alltid relevanta
uppdateringstider och skillnaden mellan tomt och otillgängligt.

Guilddata ska vara privat som standard, med separat synlighet för inventory/bank,
administrativ auditlogg, dataexport, radering och beslutad retention. Samla inte in
chatloggar, spelkontolösenord eller ovidkommande persondata. Utforma information,
ändamål, lagringstid och radering med hänsyn till GDPR.

Framtida lokal helmiljö ska kunna startas via Docker Compose med PostgreSQL, API,
webb och eventuell reverse proxy. Det ska finnas konfigurationsmall utan riktiga
hemligheter, migreringar, health checks, strukturerade loggar och databasvolym.
Produktionsdrift kräver HTTPS, brandvägg, säker SSH samt automatiska backuper till
annan destination och testad återställning. Detta är ännu inte byggt.

## 9. Faser och MVP

Ursprungliga faser: klientförstudie/addon, lokal agent, backend/databas,
autentisering/webb, utökade datamoduler och stabilisering/release.
Agent-först-beslutet ovan ändrar startordningen men avskaffar inte klientkraven.

Första riktiga end-to-end-målet är:

1. Faktisk verifierad addonexport på disk.
2. Automatisk läsning/validering/uppladdning från agenten.
3. Säker lagring i PostgreSQL genom backend.
4. Skyddad karaktärssida för behörig guildmedlem.
5. Historik/jämförelse mot tidigare faktiskt snapshot.

MVP kräver dessutom att en admin kan skapa guild, medlemmar kan registrera sig
och gå med via inbjudan, koppla/revokera agenten, hantera flera karaktärer, se
gear/talents när tillgängliga och senaste lyckade synk, återhämta nätverksfel,
blockera cross-guild-åtkomst och köra projektet enligt README med automatiska
grundtester. Nuvarande agentprototyp uppfyller **inte** hela MVP-definitionen.

Testning ska omfatta klientladdning/export, avbrott/lås/dubbletter/återförsök,
behörigheter/idempotens/snapshotordning/migreringar, webbåtkomst/UX och hela kedjan.
Efter varje fas: kör relevanta tester, uppdatera dokumentation och redovisa
verifierat resultat, antaganden och återstående arbete.
