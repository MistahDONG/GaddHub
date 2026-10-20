# GäddHub: projektkontext för Copilot

Börja varje ny arbetssession med att läsa
[överlämningen](../docs/handoff.md) och
[krav och beslut](../docs/project-brief.md). Kontrollera sedan aktuell kod och
Git-status; dokumenterade testresultat är historiska, inte nya testkörningar.

## Viktiga projektbeslut

- Agent och addon ska finnas i samma repository, separat i `agent/` och `addon/`.
- Windows och Linux delar agentens synkkod. Plattformsspecifika funktioner finns
  i `windows.py`/`linux.py`, valda genom `platform.py`; duplicera inte applikationen.
- Användaren prioriterar agenten eftersom fjärrserver/databas ännu inte är
  tillgänglig. Backend och webbportal finns inte ännu. Addonets första testversion
  finns nu, men faktisk spelinsamling/export är inte verifierad.
- Lösenord ska enligt användarbeslut sparas i klartext i en lokal användarfil
  utanför repot, inte i Windows Credential Manager. HTTPS med certifikatkontroll
  är obligatoriskt. Verkliga lösenord ska inte finnas i kod, fixtures eller loggar.
- GetBuildInfo-skärmbilden visar 1.60.1, build 70450, interface 16001.
  Insamlings-API:er och faktisk export är fortfarande inte verifierade.
  Hitta inte på WoW-funktioner eller framställ syntetiska tester som klientbevis.
- Sektioners tillgänglighet ska vara explicit. Otillgänglig bank/recept/inventory
  får inte presenteras som verifierade tomma listor.
- Distribuera färdigbyggda paket genom GitHub Releases, inte i Git-historiken.
  Ingen Discord-integration ingår.

## Arbetsunderlag

- [Agentinstallation, tester och plattformsberoenden](../agent/README.md)
- [Arkitektur](../docs/architecture.md)
- [Export- och HTTPS-kontrakt](../docs/agent-protocol.md)
- [Klientkompatibilitet](../docs/wow-forever-compatibility.md)
- [Releaseguide](../docs/releases.md)

Kör relevanta tester efter kodändringar och uppdatera överlämningen med vad som
faktiskt verifierats, vad som återstår och eventuella blockerare. Linuxstöd eller
publicerade releaser får inte kallas verifierade enbart för att en workflow finns.
