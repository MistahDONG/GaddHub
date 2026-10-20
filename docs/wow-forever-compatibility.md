# WoW Forever-kompatibilitet

## Faktiskt klientbevis, 2026-10-20

Användaren körde `/dump GetBuildInfo()` i spelet och delade en skärmbild:

| Returvärde | Observerat |
| --- | --- |
| Klientversion | `1.60.1` |
| Build | `70450` |
| Builddatum | `Oct 15 2026` |
| Interface | `16001` |

Detta ersätter den tidigare textuppgiften build 69977. Addonets manifest använder
**16001**, inte ett gissat nummer utifrån versionssträngen.
Skärmbilden verifierar endast GetBuildInfo-resultatet. Ingen faktisk addonexport
eller insamling av utrustning/talents/bank har ännu verifierats i Forever.
Uppgifter om releasedatum eller plattformar i tidigare användartext är inte
självständigt verifierade och används inte som kompatibilitetsbevis.

## Implementerad testversion

[Addon 0.1.0](../addon/README.md) har kapabilitetskontroller, separata insamlare,
slashdiagnostik, events och `GuildSyncDB` enligt agentens oförändrade kontrakt.
Koden gör inga nätverksanrop, godtycklig filåtkomst eller skyddade spelåtgärder.

| Datatyp | Första implementation | Klientstatus |
| --- | --- | --- |
| Identitet | UnitGUID, namn/realm/class/level, UTC-tid | API-körning återstår; ingen namn-only fallback |
| Equipment | Item-ID/full länk per utrustad slot | Återstår i Forever |
| Talents | Classic talent-tab-adapter, annars unsupported | Returformat återstår i Forever |
| Professions | GetProfessions/GetProfessionInfo | Kan saknas; Classic skill-line-adapter återstår |
| Inventory | Strukturerat C_Container-format | Returformat återstår i Forever |
| Bank | Öppen personlig bank, Classic-konstanter | Bankåtkomst/slots återstår; stängd bank är inte tom |
| Recipes | Moderna kompletta API:er för öppen profession | Kan saknas; inga påhittade kompletta legacy-listor |
| SavedVariables | GaddHub.toc deklarerar GuildSyncDB | Faktisk sökväg/serialisering återstår |
| Diskuppdatering | Capture i minne, sista capture vid logout | Reload-/logouttidpunkt återstår i Forever |

Lokala tester exekverar addonets Lua 5.1-kod mot testdubblar och matar en
testserialiserad export genom agentens parser/schema/kö. De är inte klientbevis.
Tidigare syntetiska agentfixtures och lokala HTTPS-tester förblir transportbevis.

## API-underlag

Dokumentationen nedan användes för signaturer, inte som bevis för Forever-stöd.
Ingen annan addons källkod kopierades.

- [GetBuildInfo](https://warcraft.wiki.gg/wiki/API:GetBuildInfo)
- [Classic GetTalentInfo](https://warcraft.wiki.gg/wiki/API:GetTalentInfo/Classic)
- [GetInventoryItemID](https://warcraft.wiki.gg/wiki/API:GetInventoryItemID)
- [GetProfessionInfo](https://warcraft.wiki.gg/wiki/API:GetProfessionInfo)
- [C_Container.GetContainerItemInfo](https://warcraft.wiki.gg/wiki/API:C_Container.GetContainerItemInfo)
- [BagIndex och Classic-varningen](https://warcraft.wiki.gg/wiki/Enum.BagIndex)
- [C_TradeSkillUI.GetAllRecipeIDs](https://warcraft.wiki.gg/wiki/API:C_TradeSkillUI.GetAllRecipeIDs)
- [TradeSkillRecipeInfo](https://warcraft.wiki.gg/wiki/Structure_TradeSkillRecipeInfo)

## Nästa verifiering i klienten

1. Installera GaddHub, kör `/gaddhub capture` och `/gaddhub diag`.
2. Kontrollera vilka API:er som faktiskt finns och deras resultat, särskilt
   talents, professioner, containerstruktur och recept. Rapportera fel/statusar.
3. Testa tom/utrustad slot, väskändring, talentändring och professionsträning.
4. Öppna banken, samla, stäng banken och reloada. Kontrollera att bankobservationen
   behålls med ursprunglig tid och att senaste stängda bankstatus är unavailable.
5. Jämför export före/efter `/reload` och logout. Bekräfta konto-/installationssökväg,
   UTF-8, strängescapes, tomma tabeller och att inga globala referenstilldelningar
   behövs i den riktiga SavedVariables-serialiseringen.
6. Välj GaddHub.lua i agenten och verifiera parser/kö via Activity log.
   Dummy-endpointens nätverksfel är förväntat; ingen verklig backend finns ännu.
7. Lägg endast med tillåtelse till avidentifierad verklig export som regressionstest.
   Först därefter preciseras datamodeller och klientstödet kan kallas verifierat.
