# Reisplan — Ontwerpdocument

*Status: concept, in discussie. Laatst bijgewerkt: 2026-08-09.*

Dit document is de actuele stand van het ontwerp. Besluiten staan samengevat in CLAUDE.md; hier staat de uitwerking en de openstaande discussie.

## 1. Doel en uitgangspunten

Internationale treinreisplanner voor NL, BE, FR, DE, CH met twee modi:

- **Planmodus** — routes zoeken onder rijke, gebruikergekozen constraints (vervoerder, materieel, toegankelijkheid, fiets, tarief, punctualiteit, drukte, reserveringsplicht).
- **Reismodus** — realtime begeleiding onderweg: overstapkansen herberekenen, omleidingen voorstellen (incl. meerkosten), beslissingsondersteuning bij ernstige storingen.

Uitgangspunten:

- De app **boekt niet zelf**; ze genereert een boekingshulp (stapsgewijze instructies per boekingssite).
- "**Onbekend**" is een geldige waarde: veel constraint-data (materieel, drukte, tarieven) is niet in elk land beschikbaar. De planner moet daar eerlijk over zijn in plaats van te doen alsof.
- Voertaal: Nederlands.

## 2. Architectuurschets

```
┌─────────────────────────── Android-app (Kotlin/Compose) ──────────────────────────┐
│                                                                                   │
│  UI (Compose)          Routeringsengine (on-device)      Lokale opslag (Room)     │
│  - Planmodus           - RAPTOR-variant                  - gecomprimeerde         │
│  - Reismodus           - constraints als filters/        │  dienstregeling        │
│  - lijst/kaart           penalties in de zoektocht       - opgeslagen reizen      │
│    (MapLibre/OSM)                                        - verrijkingsdata        │
└───────────────────────────────────┬───────────────────────────────────────────────┘
                                    │ https
┌───────────────────────────────────┴───────────────────────────────────────────────┐
│                          Minimale backend (datapijplijn + proxy)                  │
│                                                                                   │
│  1. GTFS-ETL (batch, dagelijks/wekelijks):                                        │
│     download GTFS per land → filter op treinverkeer → merge → dedupliceer         │
│     grensstations → comprimeer → publiceer als downloadbare dataset voor de app   │
│  2. Verrijkings-ETL: materieelinzet, perronhoogtes, fietsregels, tariefvlaggen    │
│  3. Realtime-proxy: GTFS-RT / vervoerder-API's doorgeven, API-sleutels afschermen │
│  4. (latere fase) Historische opslag voor punctualiteits- en druktestatistiek     │
└───────────────────────────────────────────────────────────────────────────────────┘
```

Kernidee: de backend doet het zware, saaie werk (data ophalen, schoonmaken, verkleinen) zodat de telefoon een compacte, treinen-only dataset krijgt waarop de eigen engine snel kan zoeken — ook offline. Realtime gaat via de proxy zolang de app actief is.

**Waarom dit kan op een telefoon**: de volledige GTFS-feeds van deze landen zijn samen gigabytes (vooral DE bevat al het stads- en busvervoer), maar gefilterd op **alleen treinen** blijft daar naar verwachting enkele tientallen MB gecomprimeerd van over. Dat is on-device prima te doorzoeken met RAPTOR. De ETL-stap die dit filtert en merged is precies waarom de minimale backend bestaat. *(Datasetgrootte in een vroege spike valideren — dit is een aanname.)*

## 3. Databronnen per land

**Geverifieerd op 2026-08-09.** De volledige inventaris met URLs, limieten en licenties staat in **docs/databronnen.md**; hieronder de hoofdlijnen. Legenda: ✓ beschikbaar (officieel/open), ~ gedeeltelijk of alleen onofficieel, ✗ niet beschikbaar.

| Land | Dienstregeling (GTFS) | Realtime | Materieel | Punctualiteit (historisch) | Drukte | Tarieven |
|------|----------------------|----------|-----------|---------------------------|--------|----------|
| NL | ✓ OVapi (met shapes) | ✓ NS API + OVapi GTFS-RT + NDOV | ✓ NS Virtual Train | ✓ rijdendetreinen.nl (rit-niveau sinds 2019) | ✓ NS crowdForecast | ✓ NS prijs-API (binnenland); ✗ NS International |
| BE | ✓ NMBS (rail-only, klein) | ✓ officiële GTFS-RT (30 s) | ~ iRail composition (rijk, onofficieel) | ~ fragmentarisch | ✗ (alleen crowdsourced) | ~ km-tarief zelf berekenen (PDF-tabellen) |
| FR | ✓ geconsolideerde SNCF-feed | ~ GTFS-RT met **60-min-horizon**; SNCF/Navitia-API | ✗ bestaat niet publiek | ~ alleen maandaggregaten | ✗ | ~ TER/IC-barema's + TGV-prijsvork; live **dicht** |
| DE | ✓ gtfs.de rail-only, **30 dgn horizon** (DELFI = registratie) | ~ DB Timetables (officieel, per station) / vendo (fragiel) | ~ Wagenreihung V4 (onofficieel) | ~ alleen onofficiële archieven | ~ vendo Auslastung (fragiel) | ~ live via db-vendo-client (onofficieel, fragiel) |
| CH | ✓ opentransportdata.swiss | ✓ GTFS-RT + OJP (officieel) | ✓ Train Formation Service | ✓ ist-daten-archief 2016–heden | ✓ Belegungsprognose (3 mnd vooruit) | ✓ OJP Fare incl. Halbtax; ✗ supersavers |

### 3.1 Bevindingen die het ontwerp raken

Statische feeds:

- **De grootte-aanname klopt ruimschoots**: rail-only zijn BE/FR/DE samen ~25 MB; alleen NL (238 MB) en CH (211 MB) moeten in de ETL op treinverkeer gefilterd worden. De ETL past vrijwel zeker makkelijk in een GitHub Actions-runner.
- **Shapes-probleem**: alléén de NL-feed bevat geografische lijnvoering. Voor de kaartweergave elders: gtfs.geops.ch (derde-partij-aggregaat), lijnen afleiden uit OSM-spoordata, of in v1 hemelsbrede lijnen tussen stations.
- **DE-horizon**: gtfs.de-free is maar 30 dagen vooruit geldig. Verder vooruit plannen voor DE vereist DELFI-registratie (opendata-oepnv.de; waarschijnlijk de moeite waard) of een betaald abo.
- **FR-valkuil**: alleen de geconsolideerde SNCF-feed is nog actueel. Ouigo is daarin niet als aparte agency te onderscheiden — *door de eigenaar als onbelangrijk aangemerkt (2026-08-09), geen prioriteit*. Eurostar en Transilien ontbreken.
- **Internationale treinen zijn het zorgenkind — topprioriteit voor de spike** *(prioriteit door eigenaar bevestigd)*: de feeds zijn nationaal georganiseerd en internationale treinen van niet-nationale vervoerders (m.n. Eurostar) ontbreken in de FR-feed. Verwachting: Eurostar/ICE International/TGV-naar-buurland zitten (deels) in de NL- en BE-feeds omdat NS en NMBS ze in hun reisinformatie voeren — onbevestigd. De spike moet per feed een dekkingsmatrix van grensoverschrijdende treinen maken; voor treinen die nergens in zitten is een aanvullende bron of statische toevoeging nodig (bijv. community-aggregaten zoals die van Transitous, of handmatig onderhouden dienstregeling voor het handjevol ontbrekende series).

Realtime en verrijking:

- **CH en NL zijn vrijwel compleet officieel gedekt** (realtime, materieel, drukte, historische punctualiteit). BE heeft officiële realtime maar leunt voor samenstelling op het onofficiële iRail. FR heeft realtime met een **60-minuten-horizon** (vertragingen verder vooruit zijn onzichtbaar) en verder vrijwel niets.
- **DE is het fragielste land**: geen landelijke officiële GTFS-RT, samenstelling en drukte alleen via onofficiële bahn.de/vendo-endpoints die actief geblokkeerd worden (outage juli 2026). Officieel en stabiel is alleen de station-gebaseerde Timetables API (60 req/min, CC BY). Ontwerpconsequentie: de Reismodus moet per land een andere realtime-strategie aankunnen, en DE-features moeten degraderen zonder de reis te breken.
- **Materieel-constraints** (VIRM, instaphoogte, dubbeldeks) zijn in NL/BE/CH goed te doen, in FR niet (geen publieke samenstellingsdata — fallback: materieeltype statisch per lijn afleiden). Labelen als "voldoet / voldoet niet / onbekend" blijft het model.
- **Instaphoogte** is deels infrastructuurdata: perronhoogtes zijn open beschikbaar voor DE (RIS::Stations/OpenStation), NL (ProRail) en CH (ATLAS/BehiG); BE/FR onduidelijk.
- **Punctualiteitsstatistiek per rit** kan uit bestaande archieven voor NL (rijdendetreinen, sinds 2019) en CH (ist-daten, sinds 2016); DE alleen via onofficiële archieven (Bahn-Vorhersage, piebro); FR alleen maandaggregaten; BE fragmentarisch.
- **Eigen punctualiteitscollector voor FR (en BE)**: rit-niveau-statistiek voor FR vereist zelf samplen van de GTFS-RT-feed. Poll-interval 5–10 min volstaat (elke trein is ≥60 min zichtbaar; we willen de laatste vertraging vóór aankomst), volume ~1 MB/dag. Eerst checken of de historisatie van transport.data.gouv.fr de RT-feed al archiveert (spike-vraag); zo niet: gratis opties zijn GitHub Actions-cron in een publiek repo (cron is niet stipt — acceptabel voor statistiek), Cloudflare Workers-cron (CPU-limiet free tier meten) of de Oracle-free-VM. **Zo vroeg mogelijk laten draaien** (al in fase 0/1), want de verdelingen hebben maanden aan data nodig voordat fase 2 ze kan gebruiken; BE kan er vrijwel gratis bij.
- Meerdere goede bronnen zitten **achter een gratis registratie** (NS-portaal, DB Marketplace, CH api-manager, NMBS, DELFI, NDOV). Actiepunt voor fase 0/1: al deze accounts aanvragen.

Prijzen (details in docs/databronnen.md §8):

- **De prijs-als-filter-wens is haalbaar, maar per land verschillend van aard.** Officieel en gratis: NS prijs-API (NL binnenland, incl. kortingsvarianten), CH OJP Fare (incl. Halbtax), FR barema's + TGV-prijsvork (open datasets), BE via zelf gedigitaliseerde km-tarieftabel. Live dynamische prijzen: alleen DE (+ ICE International) via het onofficiële db-vendo-client.
- **Eurostar en NS International zijn het grote gat**: uitsluitend B2B met actieve bot-bescherming. Ontwerpkeuze: daar een tariefvork tonen en doorlinken naar de boekingssite (past bij de boekingshulp-filosofie: de app boekt toch al niet zelf).
- **Frankrijk-nuance t.o.v. het eerdere plan**: live TGV-prijzen zijn feitelijk onbereikbaar (Datadome), maar de officiële open datasets geven wél TER/IC-prijzen en een min–max-vork per TGV-traject — dat is genoeg voor een prijsfilter op indicatiebasis, zónder fase-4-scraping. Fase 4 ("het riskante randje") wordt daarmee kleiner of vervalt mogelijk.
- **Reisgezelschap degradeert per kanaal**: NS kent adults/children, vendo praktisch 1 reiziger per query (dus per reiziger apart opvragen en optellen), OJP Fare negeert leeftijden. Het prijsmodel moet per kanaal weten wat het wel/niet kon meenemen en dat tonen.

## 4. Routeringsengine

- **Algoritme**: RAPTOR als basis (round-based, werkt direct op dienstregelingen, geen zware preprocessing — belangrijk omdat de dataset dagelijks ververst). Voor meerdere criteria (tijd vs. overstappen vs. tariefgroep) de McRAPTOR-variant of gewogen som; keuze volgt uit experimenten.
- **Constraints in twee smaken**:
  - **Harde filters** (vervoerder uitsluiten, fiets moet mee, geen reserveringsplicht): trips wegfilteren vóór/tijdens de zoektocht. Goedkoop.
  - **Zachte voorkeuren** (punctualiteitskans, drukte, liever enkeldeks): als penalty in de kostenfunctie, of als na-ordening van de top-N resultaten. Statistische criteria zoals overstapzekerheid vergen per resultaat een kansberekening over de keten van overstappen.
- **Overstapkansen**: per overstap P(halen) schatten uit historische vertragingsverdelingen van de aanvoerende trein + minimale overstaptijd van het station. De keten-kans is het product; dat wordt de "punctualiteitsgarantie" van het hele advies. MVP kan starten met een grove heuristiek (buffer in minuten), statistiek komt later.
- **Grensstations**: feeds overlappen (bv. NS én DB kennen Emmerich/Bad Bentheim; Thalys/Eurostar zit in meerdere feeds). De ETL moet stations op UIC-code deduplicaten en dubbele internationale treinen ontdubbelen — dit is klassiek de valkuil bij multi-land GTFS.

## 5. Constraintmodel (datamodel-schets)

Elk deeltraject (trip-segment) draagt attributen; elk attribuut mag `onbekend` zijn:

- `vervoerder` — uit GTFS (agency), soms te verfijnen (Ouigo vs. SNCF Voyageurs zit soms in één feed)
- `materieeltype` — uit verrijkingsbron; afgeleiden: `instaphoogte`, `dubbeldeks`, `gelijkvloerse instap`
- `fietsvervoer` — {niet, balkon, compartiment, fietsrijtuig, reservering-verplicht}
- `reservering` — {vrij, aanbevolen, verplicht}
- `tariefvlaggen` — landspecifiek: NL {toeslag, spits}, FR {tariefklasse + beschikbaarheid}, …
- `drukteverwachting` — {laag, middel, hoog, onbekend}
- `punctualiteitsprofiel` — vertragingsverdeling (latere fase)
- `prijs` — per reisoptie (niet per segment alleen): actuele boekingsprijs voor het opgegeven reisgezelschap, bruikbaar als filter/sortering; `onbekend` toegestaan

### Reisgezelschap

De prijs hangt af van wie er meereist, dus een plan-aanvraag bevat een **reisgezelschap**: een lijst reizigers met per reiziger:

- `leeftijd` — als getal, niet als categorie: de leeftijdsgrenzen verschillen per land (NL: <4 gratis, 4–11 Railrunner; DE: <6 gratis, 6–14 gratis bij ouder; CH: <6 gratis, 6–16 met Junior-Karte; FR/BE weer anders). Door leeftijden op te slaan kan elk landspecifiek tariefmodel er zijn eigen categorieën uit afleiden.
- `kortingskaarten/abonnementen` — BahnCard 25/50, Halbtax/GA, NS-abonnementsvormen, SNCF Avantage, etc. Bepalend voor zowel prijsindicatie als welk boekingskanaal de juiste prijs geeft.
- eventueel `fiets mee` en `beperkt mobiel` per reiziger, zodat toegankelijkheids- en fietsconstraints aan personen hangen in plaats van aan de hele aanvraag

Prijs kent twee niveaus van waarheid: **prijsindicatie** (uit tariefregels berekenbaar, bv. NL-vaste tarieven, CH-kilometertarief) en **live prijs/beschikbaarheid** (dynamische prijzen bij reserveringstreinen; vereist query op boekingssystemen, vaak alleen onofficieel). De UI moet tonen welk van de twee je ziet.

## 6. Fasering

**Fase 0 — spike: datapijplijn-prototype op de laptop** *(zie §8)*

**Fase 0.5 — vertragingskaart (realtime netwerkvisualisatie)** *(toegevoegd 2026-08-09 op verzoek eigenaar)*

Live kaart van alle spoorlijnen in de vijf landen, gekleurd naar **opgelopen vertraging per baanvak**: groen = geen, geel = tot 2 min, oranje = tot 10 min, rood = meer; met oorzaak-icoontjes bij incidenten (à la file-/ongevalsiconen in autonavigatie).

Aanpak:
1. **Segment-mapping**: per trein uit de GTFS-RT trip updates de delta-vertraging tussen opeenvolgende haltes berekenen; per station-paar aggregeren over de treinen van de afgelopen ~30 min (max of hoog percentiel). Delta (niet absolute vertraging) matcht de kleursemantiek: alleen het baanvak wáár tijd verloren gaat kleurt op.
2. **Geometrie**: infrastructuur-geodata per land (ProRail, Infrabel, SNCF Réseau, DB InfraGo, SBB — allemaal open) of OSM; in de ETL eenmalig per station-paar de lijnvoering over het net berekenen en cachen. Omzeilt het shapes-gat in de GTFS-feeds.
3. **Oorzaken**: GTFS-RT service alerts (cause-enum: ACCIDENT, STRIKE, WEATHER, …) + NS-storingen-API (rijke NL-oorzaken); mapping naar iconen, plaatsing per getroffen route/station (heuristiek).
4. **Architectuur**: de realtime-proxy wordt een **aggregator**: pollt elke 1–2 min alle landenfeeds (respecteert per-feed rate limits, bv. CH 5 req/min) en publiceert één compact netwerktoestand-snapshot (tientallen KB gzipped); clients pollen alleen dat snapshot. **Synergie**: snapshots archiveren = de FR/BE-punctualiteitscollector uit §3.1 — zelfde component, twee doelen.
5. **Oplevervorm**: eerst als webpagina (MapLibre GL JS op het snapshot-endpoint) om de keten te valideren vóór er Android-werk is; het app-kaartscherm (fase 1/3) hergebruikt endpoint en stijl.
6. **Beperking DE**: geen officiële landelijke realtime-feed; opties: DELFI/SIRI (achter registratie, inhoud verifiëren), roulerend de grootste stations via Timetables-API (60 req/min), of fragiel vendo. DE-dekking is in eerste instantie grofmaziger — de kaart moet dekkingskwaliteit per land eerlijk tonen.

**Fase 1 — MVP (Planmodus, 5 landen)**
1. Backend-ETL: rail-only GTFS van 5 landen mergen tot één compacte dataset (productieversie van de fase-0-spike)
2. On-device RAPTOR op die dataset; A→B met vertrektijd. Treinen met reserveringsplicht doen gewoon mee in de planning, met duidelijke reserveringsvlag
3. Constraints uit direct beschikbare data: vervoerder, reserveringsplicht, fiets (waar bekend)
4. Lijstweergave met uitklapbare tussenstops; opslaan van reizen
5. Kaartweergave (MapLibre + OSM; shapes uit GTFS)
6. Boekingshulp v1: statische, regelgebaseerde instructies per vervoerderscombinatie

**Fase 2 — verrijking**
- Materieel/toegankelijkheid (NL, BE, CH eerst), perronhoogtes, tariefvlaggen NL
- Reisgezelschap-invoer + **prijsindicatie** uit tariefregels en officiële prijs-API's waar die bestaan
- Punctualiteitsstatistiek + overstapkans-model; drukte waar beschikbaar

**Fase 3 — Reismodus**
- Realtime-monitoring van de opgeslagen reis via de proxy (app-actief + periodieke achtergrondsync; Android 15 is streng op achtergrondwerk — ontwerpkeuze: foreground service tijdens de reis)
- Handmatige vertraging invoeren (overrulet de feed)
- Heradvisering bij gemiste overstap, met meerkosten-indicatie
- Beslissingsondersteuning "instappen of wachten": verwachte-aankomsttijdverdeling van beide opties tonen, plus drukte

**Fase 4 — het riskante randje** *(kleiner geworden na het bronnenonderzoek: FR-live is feitelijk dicht, maar FR-prijsindicatie kan gewoon officieel in fase 2)*
- **Live prijzen DE + ICE International** via db-vendo-client (onofficieel, fragiel, uitschakelbaar per bron)
- Nightjet-prijzen/beschikbaarheid via de onofficiële nightjet-API (captcha/PoW-risico)
- Drukte-crowdsourcing door gebruikers zelf?

## 7. Besloten open vragen

1. **Backend-hosting** *(besloten 2026-08-09)*: free-tier, en eerst de datapijplijn prototypen op de laptop om netwerk-/compute-eisen te meten (fase 0, §8). Voorlopige hostingkeuze voor fase 1:
   - **ETL**: GitHub Actions scheduled workflow (gratis; ruim voldoende voor een batchjob die enkele keren per week draait) — mits de spike uitwijst dat geheugen/disk van een Actions-runner volstaan.
   - **Datasetdistributie**: Cloudflare R2 (10 GB gratis, geen egress-kosten) of GitHub Releases.
   - **Realtime-proxy**: Cloudflare Workers free tier (ruim genoeg voor één gebruiker).
   - Zodra fase 2 een database voor historische statistiek nodig heeft: heroverwegen — dan is een klein VPS (Oracle Cloud Always Free, of ~€4/mnd Hetzner) logischer dan serverless.
2. Verificatie databronnen: onderzoek loopt; resultaten worden in §3 verwerkt.
3. Hoe tonen we tegenstrijdige of ontbrekende data in de UI zonder de gebruiker te overspoelen? *(open)*
4. **Distributie** *(besloten)*: voorlopig geen Play Store; sideload/APK op eigen telefoon. Play Store eventueel later bij positieve feedback. Consequentie: geen Play-policybeperkingen in het ontwerp, wel zelf updates regelen (de app kan simpelweg een APK-download aanbieden).
5. **Reserveringstreinen** *(besloten)*: volwaardig opnemen in de planning met reserveringsvlag. Actuele boekingsprijs waar mogelijk erbij betrekken zodat prijs als filter kan dienen; daarvoor is het reisgezelschap-model in §5 toegevoegd.

## 8. Fase 0 — spike: datapijplijn-prototype (op de laptop)

**✅ Uitgevoerd 2026-08-09 — alle zes vragen beantwoord in `docs/SPIKE-RESULTATEN.md`.** Kernuitkomsten: dataset 35 MB (tar.zst), ETL < 4 min / 2,3 GB piek (past ruim in GitHub Actions → hostingbesluit §7.1 bevestigd), naïeve RAPTOR 0–41 ms per query (on-device ruim haalbaar), Eurostar zit in de NL-feed (incl. Londen), geen enkele verwachte internationale dienst ontbreekt volledig, en de FR GTFS-RT wordt níet gearchiveerd door transport.data.gouv.fr (eigen collector noodzakelijk).

Doel was: de kernaannames valideren vóór er iets aan de app gebouwd wordt.

Vragen die de spike moet beantwoorden:
1. Hoe groot zijn de vijf GTFS-feeds werkelijk (download én uitgepakt), en hoeveel blijft er over na filteren op treinverkeer?
2. Hoeveel geheugen/CPU/tijd kost de ETL (download → filter → merge → comprimeer)? Past dat in een GitHub Actions-runner?
3. Hoe erg is het grensstation-/duplicatenprobleem in de praktijk (zelfde ICE in DE- én NL-feed, UIC-codes aanwezig of niet)?
4. Zit er genoeg in de feeds voor de MVP-constraints (agency-detail, shapes voor de kaart, fiets-/reserveringsvelden)?
5. Hoe groot wordt de gecomprimeerde app-dataset, en is een naïeve RAPTOR daarop snel genoeg? (desnoods een wegwerp-prototype van de zoekkern, los van Android)
6. Archiveert de historisatie van transport.data.gouv.fr de Franse GTFS-RT-feed al? (bepaalt of we een eigen punctualiteitscollector voor FR/BE moeten bouwen — zie §3.1)

Aanpak: klein Python- of Kotlin-scriptje per stap, wegwerpcode, meten en opschrijven. De uitkomsten bepalen de definitieve hostingkeuze (§7.1) en het datasetformaat.
