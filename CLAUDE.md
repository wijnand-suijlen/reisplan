# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projectstatus

**Planningsfase — er wordt nog niet geprogrammeerd.** De eigenaar werkt het ontwerp eerst samen met Claude uit. Begin niet met implementeren zonder expliciete opdracht. Build-, test- en lint-commando's worden hier aangevuld zodra de techstack gekozen is.

Voertaal in dit project (documentatie, discussie, UI-teksten) is Nederlands. **Code is Engels** (besloten 2026-08-10: identifiers, commentaar, logmeldingen) — de oudere Nederlandstalige spike-/aggregatorcode wordt geleidelijk gemigreerd; nieuwe code altijd in het Engels.

## Wat dit project is

**Reisplan**: een internationale treinreisplanner-app voor Android (minimaal Android 15 als doelplatform van de eigenaar). Dekkingsgebied in eerste instantie: Nederland, België, Frankrijk, Duitsland en Zwitserland.

De app heeft twee modi:

### Planmodus

Reizen plannen: kortste/beste route onder door de gebruiker gekozen constraints. Bekende constraints (lijst is bewust nog niet volledig):

- **Vervoerder** — NS, Arriva, SNCB, SNCF Voyageurs, Ouigo, DB, SBB, etc.
- **Materieel** — VIRM, Protos, GTW, ICE, TGV, etc.
- **Toegankelijkheid** — instaphoogte, dubbeldekker vs. enkeldeks (relevant voor mensen die slecht ter been zijn)
- **Fietsvervoer** — type: fietsrijtuig, compartiment, op het balkon, etc.
- **Tariefgroep / tarieflimiet** — in NL: met/zonder toeslag, binnen/buiten spits; in FR (reserveringsplicht): welke tariefklassen nog beschikbaar zijn
- **Punctualiteitsgarantie** — geschatte kans dat de reis daadwerkelijk zo verloopt als gepland (op basis van historische punctualiteit)
- **Drukte** — verwachte drukte op trajecten zonder reserveringsplicht
- **Reserveringsplicht** — wel/niet verplicht reserveren per deeltraject

Weergave van een plan:
1. **Lijstweergave** — alleen overstappen; deeltrajecten uitklapbaar naar alle tussenstops
2. **Kaartweergave** — op basis van OpenStreetMap

Een gekozen reis kan worden **opgeslagen**. Bij een opgeslagen reis hoort een **boekingshulp**: stapsgewijze instructies hoe je deze reis boekt via de verschillende boekingssites (de app boekt zelf niet).

### Reismodus

Begeleiding tijdens de reis, op basis van een opgeslagen plan:

- Monitort voortdurend actuele reisinformatie (vertragingen, uitval, spoorwijzigingen)
- De reiziger kan zelf ook een vertraging invoeren als die er eerder weet van heeft (bijv. omgeroepen door de conducteur) — handmatige invoer gaat vóór op de feeds
- Herberekent **overstapkansen** op basis van realtime informatie
- Stelt bij gemiste aansluitingen of storingen een **omleiding** voor, inclusief eventuele meerkosten
- Beslissingsondersteuning bij ernstige storingen: is het beter in een overvolle trein te stappen, of een uur in een café bij het station te wachten op een rustiger/betrouwbaarder alternatief?

## Domeinkennis en aandachtspunten

- Reisadvies over vijf landen vereist het combineren van meerdere databronnen (dienstregelingen, realtime feeds, materieelinzet, tarieven, drukte, historische punctualiteit). Welke bronnen en API's gebruikt worden is een openstaande ontwerpbeslissing; per bron verschillen dekking, licentie en kwaliteit sterk per land.
- Materieelinzet (welk treinstel rijdt welke dienst) is in NL redelijk ontsloten, maar in andere landen veel lastiger te achterhalen — het ontwerp moet ermee omgaan dat constraints soms niet met zekerheid te beantwoorden zijn ("onbekend" is een geldige waarde).
- Tarieven en reserveringsbeschikbaarheid (m.n. Frankrijk) vergen mogelijk scraping of onofficiële API's; juridische en stabiliteitsrisico's meewegen in het ontwerp.
- Punctualiteitsgarantie en drukte-inschatting zijn statistische features: die hebben historische data nodig, wat opslag-/backendkeuzes beïnvloedt.

## Ontwerpbeslissingen

Besloten (2026-08-09):

- **Techstack**: native Android, Kotlin + Jetpack Compose
- **Routering**: eigen engine op GTFS-data (RAPTOR-achtig), zodat de constraints in de zoektocht zelf meegenomen kunnen worden — geen enkele externe planner-API ondersteunt ze
- **Architectuur**: minimale backend — een dunne datapijplijn/proxy (GTFS aggregeren en verkleinen, API-sleutels afschermen, realtime feeds doorgeven); routering en opslag zoveel mogelijk on-device
- **MVP**: Planmodus voor alle vijf landen, met een beperkte set constraints; Reismodus en statistische features (punctualiteit, drukte) in latere fases
- **Vertragingskaart** (fase 0.5, vóór de app): live kaart van alle spoorlijnen, gekleurd naar opgelopen vertraging per baanvak, met oorzaak-iconen; gevoed door een server-side feed-aggregator die tegelijk de punctualiteitscollector is
- **Distributie**: sideload/APK op eigen telefoon; geen Play Store (eventueel later)
- **Reserveringstreinen**: volwaardig in de planning (met reserveringsvlag); boekingsprijs waar mogelijk als filter, op basis van een reisgezelschap (reizigers met leeftijd en kortingskaarten)
- **Hosting**: free-tier (voorlopig: GitHub Actions voor ETL, Cloudflare R2/Workers voor distributie en proxy); eerst wordt de datapijplijn als fase-0-spike op de laptop geprototypet om de eisen te meten

## Productieomgeving: krap geheugen

De aggregator en de wekelijkse dataverversing draaien op een **GCP e2-micro met
1 GB RAM** (plus 4 GB swap). Alles wat DuckDB zwaar gebruikt (merge, maak-segmenten,
closure-baseline) moet daarom binnen `REISPLAN_DUCKDB_MEM=600MB` passen —
`deploy/vernieuw.sh` zet die limiet. Valkuilen die hier al fout gingen:
TEMP-tabellen zijn memory-only (gebruik een gewone, schijfgebackte tabel voor grote
tussenresultaten) en één all-feeds-query kan zelfs mét spilling een te grote
werkset hebben (verwerk per feed). **Test zware DuckDB-wijzigingen lokaal met
`REISPLAN_DUCKDB_MEM=600MB`** vóór ze naar de VM gaan; op de laptop (geen limiet)
blijven deze bugs anders onzichtbaar.

Nog open (zie PLAN.md voor de uitwerking):

- Definitieve databronnen per land (dienstregeling, realtime, materieel, tarieven)
- Kaartcomponent voor OSM-weergave (waarschijnlijk MapLibre of osmdroid)
- Welke constraints precies in de MVP zitten

Het ontwerp wordt uitgewerkt in **PLAN.md**; dat document is de actuele stand van de discussie.
