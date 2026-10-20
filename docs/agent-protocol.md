# Preliminärt export- och uppladdningskontrakt v1

Detta kontrakt används av agenten och första testaddonet, men är inte ett
verifierat WoW Forever-diskformat. Den riktiga exporten måste granskas innan
klientkompatibilitet kan påstås.

## SavedVariables

Agenten accepterar en UTF-8-fil med en enda tilldelning:

```lua
GuildSyncDB = {
    schema_version = 1,
    snapshots = {
        -- Ett eller flera snapshots enligt snapshot-v1.schema.json.
    },
}
```

`snapshots` kan innehålla upp till 100 snapshots, exempelvis senaste snapshotet
för varje karaktär i det aktuella spelkontot. Flera installationer anges som flera
filer i agentens fönster. Endast snapshots som finns på disk kan behandlas;
förändringar som skrivs över innan nästa diskexport kan inte återskapas.

Testaddon 0.1.0 behåller senaste snapshotet per GUID samt senaste snapshot med
observerad bank respektive recept. Dessa situationssnapshots behåller sin
ursprungliga UTC-tid när fönstren stängs; senaste stängda bankstatus kan alltså
vara unavailable samtidigt som en äldre bankobservation finns kvar. Recept
gäller endast senaste observerade öppna profession, inte en komplett sammanslagen
lista från alla professioner. Dubbelvalda snapshots sparas bara en gång och inga
tabellreferenser delas mellan exporterade poster. Taket är fortfarande 100.

Parsern stöder data-tabeller, strängnycklar, sekventiella arrayer med implicit
index eller `[1]`, booleska värden, nil, decimaltal, vanliga radkommentarer och
citerade UTF-8-strängar med `\n`, `\r`, `\t`, escaped citattecken/backslash och
decimala byte-escapes. Den stöder inte Lua-uttryck, funktioner, globala referenser,
glesa/blandade tabeller, long-bracket-strängar eller godtycklig kod. Dubbla
tabellnycklar avvisas. Okända format ger synliga fel, inte exekvering.

Gränser: 8 MiB per fil, 2 MiB kanonisk JSON per snapshot, 32 nivåers
tabellnästling och 200 000 värden per fil.

## Snapshot-schema

Det gemensamma schemat finns i `schemas/snapshot-v1.schema.json`.
Identitet, UTC-insamlingstid, addonversion, schema_version och samtliga sex
sektioners status krävs. `character_id` måste tillhandahållas av exportören;
agenten hittar inte på stabila karaktärs-ID:n.

Sektionerna har status `available`, `not_collected`, `unavailable`, `unsupported`
eller `error`. Endast `available` får innehålla `items` respektive talent-`build`,
och då är fältet obligatoriskt. Till skillnad från briefens strukturella exempel
utelämnas alltså tomma datalistor för otillgängliga sektioner, för att skilja
okänt innehåll från ett verifierat tomt resultat.

Lua saknar separata tomma objekt/arrayer. Tomma `items = {}` normaliseras därför
till JSON `[]`. En tom talent-`build = {}` förblir ett objekt.

Datatypsspecifika item-/talentfält är ännu preliminära, opaka JSON-objekt med
storleksbegränsning, inte verifierade modeller för gear, recept eller talents.
De måste preciseras efter klientförstudien; produktion får inte anta att ett
godkänt transportformat betyder att klientdata är äkta eller semantiskt verifierad.

## HTTPS POST

Användaren konfigurerar hela endpointen; agenten lägger inte till någon API-sökväg.
Rekommenderad framtida sökväg är `/v1/sync/snapshots`.

Headers:

```text
Authorization: Bearer <gemensamt-losenord>
Content-Type: application/json
Idempotency-Key: <sha256-hex>
User-Agent: GaddHub-Agent/0.1.2
```

Body är **ett snapshot direkt**, inte en Lua-fil eller en batchwrapper.
Hashen beräknas över exakt de skickade UTF-8-bytesen: JSON med sorterade nycklar,
utan separatorblanksteg och med Unicode oförändrad. Detta är agentens
deterministiska serialisering, inte ett påstående om RFC 8785-kompatibilitet.
Servern kan kontrollera hashen över mottagen body och måste även validera schemat.

Svar:

| Svar | Agentens beteende |
| --- | --- |
| 200, 201, 204 | Snapshot färdigbehandlat; kvittera lokalt |
| 401, 403 | Pausa uppladdning; visa autentiseringsfel |
| 408, 425, 429, 5xx | Återförsök med backoff; respektera Retry-After |
| Redirect/övriga svar | Behåll som avvisat; kräv manuell återförsökning |
| Nätverks-/TLS-fel | Behåll i kön och återförsök |

Servern ska returnera 200/204 även om samma snapshot redan lagrats. En dubblett
ska inte ge 409 i detta kontrakt. Om anslutningen bryts efter lagring men före
kvittens kommer agenten skicka samma hash igen; serveridempotens är därför ett krav.
Svarskroppen läses inte och behöver inte innehålla någon JSON.

Det gemensamma lösenordet ska inte lagras i backendkällkod eller skrivas till
accessloggar. Produktionsservern behöver betrott TLS-certifikat och separat säker
konfiguration av hemligheten.
