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

**Fase 0.5 — vertragingskaart (realtime netwerkvisualisatie)** *(toegevoegd én gebouwd 2026-08-09; NL+FR live, BE/CH wachten op keys — zie TODO.md. Aggregator: `uv run aggregator`; viewer: `python3 -m http.server 8137 -d web/vertragingskaart` → http://localhost:8137. Live geverifieerd tegen rijdendetreinen.nl: de storing Utrecht–Geldermalsen kleurde correct oranje. NB: OVapi-treinen zitten in `trainUpdates.pb`, niet in `tripUpdates.pb`.)*

Live kaart van alle spoorlijnen in de vijf landen, gekleurd naar **opgelopen vertraging per baanvak**: groen = minder dan 1 min (telt niet als vertraging), geel = 1–2 min, oranje = tot 10 min, rood = meer; met oorzaak-icoontjes bij incidenten (à la file-/ongevalsiconen in autonavigatie).

Aanpak:
1. **Segment-mapping**: per trein uit de GTFS-RT trip updates de delta-vertraging tussen opeenvolgende haltes berekenen; per station-paar aggregeren over de treinen van de afgelopen ~30 min (max of hoog percentiel). Delta (niet absolute vertraging) matcht de kleursemantiek: alleen het baanvak wáár tijd verloren gaat kleurt op.
2. **Geometrie**: infrastructuur-geodata per land (ProRail, Infrabel, SNCF Réseau, DB InfraGo, SBB — allemaal open) of OSM; in de ETL eenmalig per station-paar de lijnvoering over het net berekenen en cachen. Omzeilt het shapes-gat in de GTFS-feeds.
3. **Oorzaken**: GTFS-RT service alerts (cause-enum: ACCIDENT, STRIKE, WEATHER, …) + NS-storingen-API (rijke NL-oorzaken); mapping naar iconen, plaatsing per getroffen route/station (heuristiek).
4. **Architectuur**: de realtime-proxy wordt een **aggregator**: pollt elke 1–2 min alle landenfeeds (respecteert per-feed rate limits, bv. CH 5 req/min) en publiceert één compact netwerktoestand-snapshot (tientallen KB gzipped); clients pollen alleen dat snapshot. **Synergie**: snapshots archiveren = de FR/BE-punctualiteitscollector uit §3.1 — zelfde component, twee doelen.
5. **Oplevervorm**: eerst als webpagina (MapLibre GL JS op het snapshot-endpoint) om de keten te valideren vóór er Android-werk is; het app-kaartscherm (fase 1/3) hergebruikt endpoint en stijl.
6. **Beperking DE**: geen officiële landelijke realtime-feed; opties: DELFI/SIRI (achter registratie, inhoud verifiëren), roulerend de grootste stations via Timetables-API (60 req/min), of fragiel vendo. DE-dekking is in eerste instantie grofmaziger — de kaart moet dekkingskwaliteit per land eerlijk tonen. *Uitgewerkt 2026-08-10 in "Plan: realtime-data loggen + DE op de kaart" hieronder.*

**Verbeterlijst vertragingskaart** *(verzameld tijdens gebruik, 2026-08-10)*:
1. **Route-highlight bij klik**: klik op een baanvak → licht op welke lijnen/treinseries eroverheen rijden. Voorkomt de misinterpretatie dat aangrenzende gelijkgekleurde baanvakken één treinroute zijn (casus: Stendal–Wittenberge–Berlijn leek één route, maar was IC 57 + Hamburg-corridor + omgeleide Amsterdam–Berlijn-ritten).
2. **Incident-filter/clustering**: CH publiceert honderden geplande-werkzaamheden-alerts (🚧-wolk); filter op ernst/effect of clustering bij uitzoomen. *(2026-09-13, besluit eigenaar: geen losse iconen meer voor werkzaamheden — `CONSTRUCTION`/`MAINTENANCE` — want die staan al als gestippelde baanvakken op de kaart. Filter zit in de viewer, niet in de aggregator: de snapshot draagt ze nog. De rest van de incidentweergave hangt nu af van "Plan: verkeersinformatie vastleggen" hieronder.)*
3. **Dekkingsnuance "gastdata"**: DE kleurt deels via doorgaande treinen uit de NL/BE/CH-feeds terwijl het paneel "geen bron" zegt — toon dit als aparte status ("alleen internationale treinen").
4a. ✅ **Rand-gebaseerde aggregatie** *(gebouwd 2026-08-10, op verzoek eigenaar)*: de kaart kleurt niet langer per stationspaar maar per fysieke spoorrand (dissolve van de OSM-paden in s8; 27k getekende randen). Alle drie de dubbeltekening-oorzaken uit de s9-inventaris (onverfijnde expresses, duplicaat-stations, gedeelde corridors) zijn daarmee per constructie van de kaart verdwenen; duplicaat-clusters blijven wel een dataprobleem voor de reisplanner zelf (naamnormalisatie-verbeteringen blijven op de ETL-lijst).
4. ~~**v2-geometrie**~~ ✅ *Gebouwd 2026-08-10* (`spike/s8_geometrie.py`): OSM-spoorgraaf uit Geofabrik-extracten (6 landen, 4,1 M knopen → 617k randen), stations gesnapt (≤1500 m), 18.658 van 20.626 baanvakken over het echte spoor gerouteerd (A*, tolerantie 2,2×; 572 fallback-rechte-lijnen). Output `paar_geometrie.json.gz` (2 MB) gaat via R2 naar de VM. Herdraaien alleen nodig als het stationsbestand wezenlijk wijzigt.
5. **Gerealiseerde vs. voorspelde delta's + venstersemantiek**: trip updates bevatten ook voorspellingen voor toekomstige stops; overwegen alleen gepasseerde baanvakken te laten meekleuren, of voorspelling apart te stylen. Verwant: door de wijzigings-dedupe veroudert een stabiele vertraging uit het 30-min-venster terwijl de trein nog rijdt — netter is per actieve trip de laatste bekende delta vast te houden zolang de trip loopt ("grijs" betekent dan echt "geen trein", niet "geen nieuws").
6. **Drukte-kleurmodus** *(idee eigenaar 2026-08-10)*: schakelbare modus waarin niet vertraging maar treinfrequentie per baanvak de kleur bepaalt, van blauw (weinig) naar rood (druk). Twee varianten mogelijk: gepland (uit de statische dienstregeling, per uur exact te berekenen) en actueel (distinct treinen in het venster — zit al in de tooltip als `n`).
7. **Blokkade-weergave** *(idee eigenaar 2026-08-10)*: als een baanvak feitelijk versperd is, niet grijs laten wegvallen maar een **rode stippellijn** tekenen (à la wegafsluitingen in autonavigatie) totdat er daadwerkelijk weer een trein overheen rijdt. ✅ *Signaal (a) gebouwd 2026-08-10 (`blockades.py`): een baanvak is versperd bij ≥2 verschillende treinen CANCELED/SKIPPED (GTFS-RT; trip-level-cancels zonder stoplijst via statische ritopzoeking in merged.duckdb) of `cs="c"` (DE/IRIS) binnen 90 min, en opheffing uitsluitend door een geréaliseerde passage (eventtijd in het verleden; ontbreekt de tijd, dan geldt de melding als gerealiseerd). Snapshotveld `blk`; viewer tekent rode stippellijn + tooltipregel. Nog open: signalen (b) "alles ≥30 min vertraagd" en (c) NO_SERVICE-alerts, en de melding-zonder-eventtijd-aanname verfijnen samen met venstersemantiek (punt 5). Geplande buitendienststellingen vallen buiten dit signaal — zie punt 8.*
8. **Geplande werkzaamheden (buitendienststellingen)** *(casus eigenaar 2026-08-11: Ht–Gdm buiten dienst, kaart toonde grijs)*: geplande werkzaamheden zitten al in de statische GTFS verwerkt — geen trips → geen cancels → signaal 7a mist ze. ✅ *Gebouwd 2026-08-11, vier signalen. (i) **Generiek, alle landen** (`closure_baseline.py` in de wekelijkse ETL): baseline = mediaan geplande treinen per getekende rand per uurblok per dagtype (wd/za/zo) over 35 dagen; uren met 0 gepland tegen baseline ≥1 en ≥2 aaneengesloten uurblokken → tabel `planned_closures` (14 dagen vooruit), door de aggregator per snapshot gefilterd op nu. (ii) **NS-disruptions-API** (`disruptions_ns.py`, 300 s): werkzaamheden/storingen met stationsectie, periode en titel; stationscode→cluster via `stations.stop_code`. (iii) **SNCF Navitia** (`disruptions_sncf.py`, 600 s): NO_SERVICE-disruptions met since/until-filter (actief nu), deleted-stopketens via UIC→cluster. (iv) **NMBS-alerts** (`alert_closures.py`, op de bestaande BE-alertsfeed): NO_SERVICE-alerts zijn agency-only zonder stops/periode — trajectnaam uit de header ("Mol - Hasselt", fr-variant matcht `clusters.naam`) → keten → randen. Keten→randen gedeeld in `Statisch.chain_edges()` met hop-gelimiteerde BFS-fallback over de bladsegment-graaf (nodig: bij maandenlange sluitingen bestaat er geen doorgaande trein meer in de feed, en dan is de mediaan-baseline zelf óók 0 — de feeds zijn daar het enige signaal). Snapshotveld `wrk` (gegroepeerd, bron/ernst/tot/tekst); feed-meldingen winnen van het generieke signaal (dedupe). **Ernst-classificatie** (zelfde dag, na observatie eigenaar dat er treinen reden onder de werk-lijn): NS-situation-teksten van de *nu geldige* timespans bepalen de categorie — "tussen X en Y rijden er bussen/geen treinen" → dat deeltraject (op naam gemapt, NL-voorkeur bij duplicaat-clusternamen; onherleidbaar → hele sectie) **gepland buiten dienst** (rode puntjeslijn, tooltip zegt "gepland" — de bestaande rode streepjeslijn blijft de feitelijke versperring); "internationale dienstregeling aangepast" → **internationale verbinding gestremd** (blauwe puntjeslijn — de app is internationaal georiënteerd, dus die verdienen een eigen markering); overig ("minder treinen") → **aangepaste dienst** (oranje). BE-NO_SERVICE en het baseline-signaal zijn per definitie "buiten dienst"; SNCF-tripcancels tellen als aangepaste dienst (één uitgevallen trein bewijst geen sluiting — de blokkade-tracker is daar het rode signaal). Nog verfijnen: NMBS-alerts hebben geen periode (nachtelijke sluitingen kleuren ook overdag); CH-werkzaamheden-alerts projecteren (samen met punt 2/7c).*

### Plan: realtime-data loggen + DE op de kaart *(opgesteld 2026-08-10; DB-keys en DELFI-account zijn binnen en getest)*

Twee doelen, één component: (A) het realtime-archief op de VM opwaarderen tot een échte punctualiteitslog, en (B) Duitsland als volwaardige bron op de vertragingskaart via de DB Timetables API (60 req/min, getest 2026-08-10).

**Stap 0 — DELFI-realtime verifiëren** ✅ *(2026-08-10: DELFI biedt géén echtzeitdataset — alleen Sollfahrplandaten en Haltestellendaten. Timetables-rotatie is dus de route.)*

**Stap 1 — stationsset + EVA↔cluster-mapping (eenmalig, ETL).** ✅ *Gebouwd 2026-08-10: `spike/s10_station_eva_map.py` (draait wekelijks mee in vernieuw.sh; output `data/merged/eva_stations.json`). Leerpunten: IRIS-lookup matcht exact (naamvarianten nodig: "S Ostkreuz Bhf (Berlin)"→"Berlin Ostkreuz", stad-prefix uit coördinaten, str.→straße, koppeltekens); sommige hub-EVA's zijn lege hulzen waarvan de data op een meta-EVA zit (Berlin Hbf 8011160 → 8098160) — validatie loopt de meta-lijst af.*
- De Timetables API is station-gebaseerd en werkt op EVA-nummers; DELFI/merged gebruikt DHID-stop-ids. Eenmalige mappingtabel `eva ↔ cluster_id` in merged.duckdb, te bouwen uit een open DB-stationslijst (StaDa/RIS::Stations of de haltestellen-CSV) met dezelfde naam+afstand-matching als s3.
- Stationsselectie op basis van rail-tripaantallen per station in de DELFI-data: **Tier A** ±80 FV-/grote knooppunten, **Tier B** ±400 middelgrote knooppunten.

**Stap 2 — DB-Timetables-poller in de aggregator.** ✅ *Gebouwd 2026-08-10 (`db_timetables.py`, Engelstalig conform het nieuwe codetaal-besluit); live getest met de volledige 402-stationsset: 44 req/min (limiet 60), 620 trips gevolgd na 200 s warmup, 65 waargenomen baanvakken waarvan 47 (72%) op getekende randen mappen (155 randen zouden kleuren; wordt meer naarmate meer stations warm zijn). fchg gemeten: 0,07–0,8 MB per station. Mappingdekking: 402 van 480 kandidaat-clusters (rest is tram/U-Bahn, terecht overgeslagen).*

*Aanvulling (zelfde dag): **ppth-ketenuitbreiding** — paren gepollde stations zonder statische verfijning worden nu uitgesmeerd over het geplande pad van de trein zelf (`ppth` uit de planslices; tussenstations op naam naar clusters, ambigue namen uitgesloten, onresolveerbare overbrugd; delta gelijk verdeeld over de kettingschakels). Kost nul extra requests; koude test: 82% van de waarnemingen mapt op randen en +51% kleurbare randen t.o.v. ervoor. Live-effect gemeten: 22% → 26% van de DE-randen gekleurd ('s avonds).*

*Aanvulling 2 (zelfde dag): **stationsselectie omgebouwd van drukste-480 naar greedy edge-cover** — kies ankerstations zó dat zoveel mogelijk randen tussen twee gepollde stops van één treinserie liggen (dat is wat ppth kan inkleuren); de 60 drukste knooppunten blijven vaste kern, onbezette lijnen worden geopend met beide eindpunten. Twee valkuilen uit de eerste doorrekening (dank aan de eigenaar voor het doorvragen): grensoverschrijdende randen bliezen de teller op, en een statisch "gedekte" dunne lijn kleurt maar een fractie van de tijd binnen het 30-minutenvenster. Daarom rekent de selectie nu op één representatieve dienstdag en weegt het openen van lijnen naar verwachte kleurtijd (duty ≈ min(1, ritten/dag × 30 min / 19 u)). Eerlijke cijfers (alleen-DE, dienstdag di 2026-08-11, 43.070 trips): drukste-480 dekt 46% statisch / ~41% verwacht live; greedy-480 73% / ~60%. Gemeten werkelijkheid ligt daar structureel onder (EVA-skips, naamresolutie, avonddienst): huidige selectie voorspeld 41%, gemeten 26%. NB: s10 draait op de VM naast de live poller tegen hetzelfde 60 req/min-quotum — requesttempo daarom verlaagd naar ~13/min (run duurt ~50 min).*
- Nieuw brontype naast GTFS-RT: XML (IRIS-formaat), per station `/fchg/{eva}` pollen. Cadans: Tier A elke ~5 min, Tier B roulerend elke ~25 min; gemiddeld budget ≤45 req/min (limiet 60), backoff op 429.
- Trip-matching over stations: het IRIS-stop-id is `-{tripid}-{datum}-{stopindex}` — zelfde tripid op elk station, stopindex geeft de volgorde. Delta per baanvak = delay(B) − delay(A) van opeenvolgende gepollde stations; de bestaande verfijning (expresse-sprong uitsmeren) vult de niet-gepollde tussenstations in.
- Venstersemantiek (verbeterpunt 5) hier vanaf dag één: fchg bevat ook voorspellingen uren vooruit — alleen (bijna-)gerealiseerde events als seg-obs meetellen, verre voorspellingen niet of apart gevlagd.
- Absolute delays per station gaan als stop-obs de log in, net als bij de andere landen. Attributie op de kaart: CC BY Deutsche Bahn AG.

**Stap 3 — de log opwaarderen tot punctualiteitsarchief (alle vijf landen).** ✅ *Gebouwd 2026-08-10: `stop_obs2` (met dienstdatum, append-bij-verandering) vervangt de overschrijvende v1-tabel; `archive.py` exporteert afgesloten dagen als parquet naar R2 (`rt-archive/…`), met automatische backfill na downtime.*
- **Bug/gat**: `stop_obs` heeft PK (land, trip_id, cluster) zonder dienstdatum en overschrijft — dezelfde trein wist morgen zijn vertraging van vandaag. Fix: dienstdatum erbij en appenden-bij-verandering (v2-tabel, oude data laten staan); de definitieve vertraging per (trip, cluster, dienstdag) is straks de basis voor het overstapkans-model van fase 2.
- **Backup**: afgesloten dienstdagen dagelijks/wekelijks exporteren naar parquet (per land/maand) en uploaden naar R2; `observaties.sqlite` blijft werkvoorraad op de VM. vm-beheer.md bijwerken (het handmatige scp-recept vervalt).
- Groeischatting blijft MB's/dag; R2 free tier (10 GB) is jaren toereikend.

**Stap 4 — kaart en dekkingspaneel.** ✅ *Gebouwd 2026-08-10: DE-bron aan zodra `DB_CLIENT_ID`/`DB_API_KEY` in .env staan; paneel kent status "deels" ("live (knooppunten)").*
- DE-bron aan in config (status "ok"), maar het paneel moet dekkingskwaliteit eerlijk tonen: DE is **gedeeltelijk** (FV + knooppunten, geen vlakdekkend RV) — dit lost meteen verbeterpunt 3 (gastdata-nuance) mee op: DE toont dan "eigen bron: knooppunten + doorgaande internationale treinen".

**Risico's/meetpunten**: fchg-responsegrootte per station meten vóór de tier-groottes vastliggen (verwachting 50–300 KB bij grote stations; bepaalt of ~2,3k req/uur qua bandbreedte/CPU op de e2-micro past — verwachting: ruim); DB kan free-limieten eenzijdig wijzigen (ToU); rchg-varianten (elke 2 min, kleiner) zijn een optimalisatie voor later.

**Flankerend, los van realtime**: de statische merge van DE overzetten van gtfs.de op DELFI (nagemeten 2026-08-10: past ruim; geeft ook treinnummers — die maken de IRIS-matching robuuster) en dan s3/s5 herdraaien voor de nieuwe totaalgrootte van de vijflanden-dataset.

### Plan: verkeersinformatie vastleggen (alerts, storingen, oorzaken) *(opgesteld 2026-09-13)*

**Uitgangspunt (eigenaar, 2026-09-13).** Alle informatie over vertragingen en hun oorzaken wordt vastgelegd, zodat het statistische vertragingsmodel van fase 2 die kan gebruiken. De vertragingskaart toont de verkeersinformatie van alle landen op één homogene manier, zodat zichtbaar is óf we de juiste informatie vastleggen. Gevolg: **filteren gebeurt alleen in de weergave, nooit bij het vastleggen.** Een melding die niet op de kaart hoort — een werkzaamhedenalert, "voitures hors quai", een melding voor volgende week — komt wél in het archief.

**Stand nu.** Er wordt niets bewaard (zie `213e309` en `docs/casus-cleon-2026-09-11.md`). Alerts leven als `self.incidenten`/`self.alert_groups` één pollcyclus in het geheugen; `archive.py` exporteert alleen `seg`, `stops` en `cancels`. Hetzelfde geldt voor de NS- en SNCF-storingsfeeds. De DB-oorzaakcodes worden al opgehaald maar weggegooid.

**Wat de bronnen leveren** *(gemeten 2026-09-13, zondagmiddag/-avond)*:

| bron | omvang | waar een melding aan hangt | oorzaak |
|---|---|---|---|
| NL — OVapi GTFS-RT alerts | ~135 alerts, 0,07 MB | halte, vaak plus `route_id` | vrijwel altijd `UNKNOWN_CAUSE`/`MAINTENANCE`; de NS-storingen-API is de rijke NL-bron |
| FR — SNCF GTFS-RT alerts | ~440 alerts, 1 MB | verstoringen **alleen trip**: treinnummer (`OCESN17311F`), zonder `start_date`; alleen de stationsmededelingen hebben ook haltes (62 van 434) | `UNKNOWN`/`OTHER`/`MAINTENANCE`; de echte oorzaak staat alleen in de tekst |
| CH — opentransportdata GTFS-SA (JSON) | ~1.600 alerts, 16,6 MB JSON / 7,5 MB protobuf | halte, trip mét `startDate`, of route; elke gebeurtenis als tripalert én haltealert | 997 `CONSTRUCTION`, 563 `OTHER_CAUSE` |
| BE — NMBS GTFS-RT alerts (JSON) | ~48 alerts | **alleen vervoerder**; traject staat in de kop ("Gent-Sint-Pieters - Aalst"), geen `active_period` | 47 van 48 `CONSTRUCTION` |
| DE — DB Timetables `fchg` | al gepolld, 402 stations | `<m>`-elementen per trein en per halte, dus direct aan trip plus dienstdag | **gestructureerde oorzaakcodes** (`t="d"`, `c="43"`, …); daarnaast `t="h"` (HIM-storingen met from/to), `f`, `c`, `q`. Frankfurt Hbf alleen al: 1.341 berichten, 214 met vertragingscode |

Drie inhoudelijke bevindingen die het ontwerp raken:
- **`active_period` is geen "nu".** CH geeft een omhullende: "S8 valt uit Effretikon–Winterthur" heeft 13 sep 22:35 → 17 sep 05:20, terwijl het werk *jeweils* 's nachts is. Van de CH-werkzaamheden die volgens de periode actief zijn, loopt 226 langer dan 30 dagen. 391 zijn nog niet begonnen. Het echte ritme staat alleen in de beschrijving.
- **Wat op de kaart kwam was een scheve selectie.** De huidige code plaatst alleen alerts met een `stop_id`. In FR zijn dat juist de stationsmededelingen (54× "Rijtuigen buiten het perron": de trein is langer dan het perron; 8× kaartautomaat/lift defect). De 195 actieve verstoringen ("De trein heeft vertraging", "TER supprimé", "Dérangement d'un passage à niveau") hangen alleen aan een trip en vielen weg. De vertraging zelf kleurt wel mee via de trip updates; wat ontbrak is de verklaring.
- **Voor het model telt de tripkoppeling, niet de kaartpositie.** `stop_obs2` en `cancel_obs` hebben al `trip_id` en `service_date`. Een oorzaak die aan een concrete trein hangt is precies wat een vertragingsmodel nodig heeft.

**Ontwerp in vier lagen:**

1. **Vastleggen (aggregator, op de VM) — ruw en ongefilterd.**
   - Tabel `alert_versions` in `observaties.sqlite`: `source` (`nl-alerts`, `fr-alerts`, `ch-alerts`, `be-alerts`, `ns-disruptions`, `sncf-disruptions`), `country`, `alert_id`, `content_hash`, `first_seen`, `gone_ts` (leeg zolang de melding in de feed staat), `payload` (BLOB: het geserialiseerde GTFS-RT-`Alert`-bericht, of de ruwe JSON van een storing). Alle vertalingen en de volledige `informed_entity` blijven erin.
   - Een nieuwe rij alleen bij een nieuwe of gewijzigde melding; verdwijnt ze, dan `gone_ts` zetten. Het verloop is klein: in 15–25 minuten NL 2 weg, FR 19 nieuw/10 weg/1 gewijzigd, CH 1 nieuw/20 weg. De dedup-toestand is een dict `alert_id → 64-bit-hash` per bron (enkele duizenden sleutels) en wordt bij het opstarten opgewarmd uit de rijen zonder `gone_ts`. Anders logt een herstart alles opnieuw met `first_seen=nu` — dezelfde valkuil als bij `stop_obs2` (zie `opslag.py`).
   - Tabel `de_messages`: `service_date`, `trip_id`, `cluster`, `msg_id`, `type` (`d`/`h`/`f`/`c`/`q`), `code`, `category`, `valid_from`, `valid_to`, `ts`, `first_seen`. Dedup op `msg_id` plus trip plus halte. Kost geen extra requests: de berichten zitten al in de `fchg`-responses die `db_timetables.py` verwerkt.
2. **Archiveren.** `archive.py` krijgt `rt-archive/alerts/<dag>.parquet` en `rt-archive/de-messages/<dag>.parquet`. Een melding komt in elke dag waarin ze in de feed stond (`first_seen`…`gone_ts`). Op de VM geldt dezelfde retentie van 3 dagen als voor de observaties; R2 is de duurzame kopie.
3. **Koppelen en classificeren — offline, over het archief** (laptop of Actions, niet op de VM). Beide stappen zijn afgeleid en krijgen een versienummer, zodat een betere regel later het hele archief opnieuw kan doorrekenen.
   - *Koppeling* per land naar `(country, trip_id, service_date)`, `cluster` of rand. CH: `trip_id` plus `startDate` direct. FR: treinnummer uit de alert tegen het `OCESN<nummer>F`-voorvoegsel van de TU-trip-id's (13 sep: 410 van de 1.248 treinen in de TU-feed hebben een alert); de dienstdag uit `active_period` ∩ dienstregeling. NL: halte plus route plus tijdvenster. BE: trajectnaam → keten → randen (bestaat al in `alert_closures.py`). DE: al gekoppeld.
   - *Classificatie* naar een eigen, landonafhankelijke set, bijvoorbeeld: `vertraging-oorzaak`, `uitval`, `werkzaamheden`, `stremming`, `stationsinfo`, `drukte`, `overig`. De `cause`-enum van de bron is daarvoor onbruikbaar (FR: vrijwel altijd onbekend), dus het werk zit in tekstregels per bron. Voor CH ook het werkelijke ritme uit de "jeweils von … bis …"-zinnen.
4. **Weergave (kaart).** Op de VM een lichte versie van de classificatie (bronregels, geen archiefwerk) die de snapshot voedt:
   - iconen alleen voor wat nu geldt, ontdubbeld op tekst plus plaats;
   - geen iconen voor werkzaamheden (al gebouwd);
   - `stationsinfo` als uitschakelbare laag in plaats van weggegooid;
   - FR-tripalerts een positie geven via de haltes van de gekoppelde trein;
   - een **dekkingsoverzicht per land**: aantal meldingen per categorie en welk deel aan een trip gekoppeld is. Dat is het controle-instrument uit het uitgangspunt: het laat meteen zien dat BE geen tripkoppeling heeft en dat DE-oorzaken (nog) ontbreken.

**Geheugen (VM, 1 GB) — eerst meten, dan bouwen.**
- **Nu al een piek:** de CH-feed is 16,6 MB JSON. `parse_feed` doet `json.loads` plus `ParseDict`: lokaal gemeten ~100 MB Python-heap en +286 MB RSS, elke 10 minuten. Daarbovenop parseert `main.py` elke alertfeed **twee keer** (`verwerk_alerts` en daarna `edge_groups_from_alerts(parse_feed(pb))`, ook voor landen waar die functie direct `[]` teruggeeft).
  - Snelle winst, los van dit plan: één keer parsen.
  - Voor het vastleggen per entiteit hashen en serialiseren zonder de hele boom tweemaal vast te houden. Streaming JSON (`ijson`) is de terugvaloptie als de piek te hoog blijft. De protobufvariant van het CH-endpoint is volgens `config.py` corrupt; opnieuw proberen, want 7,5 MB protobuf parseert veel zuiniger.
  - Deze piek staat nog niet in `docs/geheugen-op-1gb.md`; daar bijschrijven met een meting op de VM (trap A, `diagnostics.py`).
- De dedup-toestand is verwaarloosbaar (enkele duizenden ints). Het schrijven gaat in batches per poll.

**Volume** *(schatting op basis van één zondagmeting; doordeweeks meten)*: FR ~1.700 versies/dag × ~2,3 KB ≈ 4 MB ruw, CH ~2.000 × ~4,7 KB ≈ 9 MB, NL/BE verwaarloosbaar. Parquet met zstd drukt de sterk herhalende teksten fors. DE-berichten zijn onbekend: `msg_id` is netbreed, dus hetzelfde bericht op meerdere stations telt één keer, maar dat moet gemeten worden. R2 (10 GB) is ruim.

**Volgorde:**
1. Snelle winst: alertfeeds één keer parsen; CH-piek op de VM meten en in het geheugenrapport zetten.
2. `alert_versions` voor de vier GTFS-RT-alertbronnen plus de NS- en SNCF-storingen, met opwarmen na herstart. Een etmaal draaien en volume en geheugen meten.
3. `de_messages` uit `fchg`. Pas na een meting van het extra geheugen in `db_timetables.py`; dat is de module waar de laatste onbegrensde container zat.
4. Export naar `rt-archive/`.
5. Offline koppeling en classificatie, gevalideerd tegen bekende casussen: Cléon (11 sep) en de twee aangekondigde omleidingen uit `docs/openstaand-uitrol.md`.
6. Kaart: categorieën, actief-filter, ontdubbelen, FR-tripposities, dekkingsoverzicht.

**Open voor de eigenaar:** hoe lang de ruwe payload bewaard blijft. Voorstel: onbeperkt op R2, gezien het volume. En of `stationsinfo` (perron, lift, kaartautomaat) standaard aan of uit staat op de kaart.

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
