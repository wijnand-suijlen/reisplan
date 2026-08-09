# Databronnen — geverifieerde inventaris

*Onderzocht: 2026-08-09 (webverificatie; HEAD-requests op download-URLs waar mogelijk). Bronnen achter login zijn gemarkeerd als "niet extern geverifieerd". Prijs/beschikbaarheids-API's: zie aparte sectie onderaan (onderzoek loopt).*

## 1. Statische dienstregeling (GTFS)

| Land | Bron / URL | Grootte | Rail-only? | Shapes | Update | Toegang/licentie |
|------|-----------|---------|-----------|--------|--------|------------------|
| NL | OVapi: `https://gtfs.ovapi.nl/nl/gtfs-nl.zip` | 238 MB | nee — heel NL-OV, filter `route_type=2` | **ja** | dagelijks ~03:00 UTC | vrij; informele licentie (best-effort, User-Agent verplicht, If-Modified-Since bij polling) |
| BE | iRail-mirror: `https://gtfs.irail.be/nmbs/gtfs/latest.zip` | 8,8 MB | ja (NMBS/SNCB) | nee | dagelijks | vrij; officiële NMBS-route (data.belgianmobility.io) vereist licentie-acceptatie |
| FR | `https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip` | 4,7 MB | ja (TGV inOui+Ouigo, Intercités, TER) | nee | dagelijks; 151 dagen vooruit | vrij, ODbL |
| DE | gtfs.de: `https://download.gtfs.de/germany/fv_free/latest.zip` (Fernverkehr) + `rv_free/latest.zip` (Regionalverkehr) | 0,4 + 11 MB | ja | nee (alleen in betaald abo) | wekelijks+ | vrij, CC BY 4.0; **30 dagen geldigheid** |
| CH | opentransportdata.swiss GTFS-permalink (`…/timetable-2026-gtfs2020/permalink`) | 211 MB | nee — al het CH-OV, filteren | nee (bewust) | 2×/week | vrij via permalink |

Aandachtspunten:

- FR: oude per-segment-feeds (voyages/TER/IC apart) zijn dood sinds jan 2025; alleen de geconsolideerde feed is actueel. Ouigo niet als aparte agency onderscheidbaar; Transilien en Eurostar ontbreken. ~1000 duplicate stops in validatie.
- DE: DELFI (opendata-oepnv.de) is het alternatief met volledige dienstregelingsperiode — registratie vereist, bevat ál het OV, wekelijkse publicatie. Registratie waarschijnlijk de moeite waard vanwege de 30-dagenhorizon van gtfs.de-free.
- CH: trip/service-id's niet stabiel tussen publicaties. Alternatief mét shapes: gtfs.geops.ch (derde partij, niet geverifieerd).
- Shapes: alleen NL. Kaartweergave elders: geops-aggregaat, OSM-spoordata, of hemelsbrede lijnen in v1.
- Onbevestigd: volledigheid internationale treinen (ICE International/Eurostar) in de NL-feed; of gtfs.de FlixTrain bevat.

## 2. Realtime reisinformatie

| Land | Bron | Toegang | Limieten | Oordeel |
|------|------|---------|----------|---------|
| NL | NS Reisinformatie API (apiportal.ns.nl): trips, arrivals/departures, disruptions | registratie + key | ±5.000 req/dag (free; niet hard geverifieerd, catalogus achter login) | officieel, hoog |
| NL | OVapi GTFS-RT (tripupdates, vehiclePositions, alerts) | vrij; User-Agent + If-Modified-Since verplicht | — | data hoog; continuïteit middel (stichting, geen SLA) |
| NL | NDOV Loket (InfoPlus DVS/rit-info, ZeroMQ push) | registratie + overeenkomst, gratis | — | rijkste bron (spoorwijziging, vleugeltreinen); bewerkelijk |
| BE | NMBS officiële GTFS-RT (trip updates elke 30 s + alerts) via data.belgianmobility.io | registratie + licentie-acceptatie | — | officieel, hoog (portaalinhoud niet extern geverifieerd) |
| BE | iRail API (liveboard, connections, vehicle, disturbances) | vrij | 3 req/s per IP | onofficieel maar >10 jaar stabiel; middel |
| FR | GTFS-RT trip updates + alerts via proxy.transport.data.gouv.fr (TGV+IC+TER) | vrij | update elke 2 min; **alleen treinen die binnen 60 min rijden** | hoog beschikbaar, beperkte horizon |
| FR | SNCF API (api.sncf.com, Navitia) | token via e-mail | 5.000 req/dag free | middel-hoog; strategische toekomst onzeker |
| DE | DB API Marketplace — Timetables API (plan/fchg/rchg per station) | registratie + key | 60 req/min free; CC BY 4.0 | officieel, hoog; wel station-gebaseerd, geen landelijke GTFS-RT |
| DE | db-vendo-client / v6.db.transport.rest (bahn.de-endpoints) | vrij | ~60–100 req/min; actieve blocking | **fragiel** (outage juli 2026, README waarschuwt zelf); laag-middel |
| CH | opentransportdata.swiss GTFS-RT | API-key | **5 req/min** (feed is wel landelijk-compleet per download) | officieel, hoog |
| CH | OJP 2.0 (routeplanner-API) | API-key | 50 req/min, 20.000/dag free | officieel, hoog |

DE heeft géén officiële landelijke rail-GTFS-RT; DELFI levert NeTEx/SIRI achter registratie.

## 3. Materieelinzet / treinsamenstelling

| Land | Bron | Inhoud | Oordeel |
|------|------|--------|---------|
| NL | NS Virtual Train API (apiportal, achter login) | bakken, materieeltype, -nummers, zitplaatsen, faciliteiten, drukte per bak | officieel, hoog; docs afgeschermd |
| NL | NDOV/InfoPlus-ritinfo (vgl. open-source `rijdendetreinen/gotrain`) | samenstelling in ruwe feed | goed startpunt |
| BE | iRail `/composition` | per rijtuig: type, zitplaatsen, toiletten, airco, **fietsopslag, rolstoelsecties** | inhoudelijk rijk; onofficiële upstream, middel |
| DE | Wagenreihung V4 (bahn.expert-ecosysteem; vendo/RIS-endpoints) | wagenvolgorde ICE/IC/EC, groeiend regionaal | onofficieel; data middel, API-stabiliteit laag (endpoints wijzigen vaker) |
| CH | Train Formation Service (opentransportdata.swiss) | formaties stop-/voertuig-gebaseerd, incl. perronsectoren; plus statische "Jahresformation" | officieel, hoog; 50 req/min / 20.000 per dag free |
| FR | — | **bestaat niet publiek** | fallback: materieeltype statisch per lijn afleiden |

## 4. Drukteverwachting

- **NL**: NS crowdForecast (LOW/MEDIUM/HIGH per trip) + per-bak via Virtual Train — officieel, hoog.
- **CH**: Belegungsprognose (opentransportdata.swiss): dagelijkse dump, 3 maanden vooruit, per trein/halte — officieel, hoog; dekking SBB/BLS/Thurbo/SOB.
- **DE**: Auslastung alleen via onofficiële vendo-antwoorden (Fernverkehr, schaal 1–4) — fragiel.
- **BE**: iRail occupancy is crowdsourced (Spitsgids), dun — zwak.
- **FR**: niets gevonden.

## 5. Historische punctualiteit

- **NL**: rijdendetreinen.nl open data — alle ritten sinds 2019, storingen sinds 2011, CC BY 4.0, geen key. Referentiekwaliteit.
- **CH**: ist-daten (dagelijks) + archief 2016–heden op archive.opentransportdata.swiss — officieel.
- **DE**: geen officieel archief. Onofficieel: Bahn-Vorhersage open data (IRIS-dumps), piebro/deutsche-bahn-data (Parquet, ~99% dekking 2024–2026), Zugfinder (betaald). Bruikbaar, geen garanties.
- **FR**: SNCF régularité-datasets (TGV/TER/IC) — officieel maar **maandaggregaten per liaison**, geen rit-niveau.
- **BE**: iRail-logs (bewerkelijk); Infrabel opendata punctualiteit — nog te verifiëren.

## 6. Stations, perronhoogte, toegankelijkheid

- **DE**: RIS::Stations (perronhoogte/-lengte/sectoren, batch-sync), StaDa (faciliteiten), OpenStation API (DB InfraGo, open infrastructuurdata) — hoog.
- **NL**: NS Stations-API (achter login); ProRail perrongeodata open (CC0/CC BY; spoordata.nl); NL-perrons genormaliseerd 760 mm met legacy-uitzonderingen — hoog.
- **CH**: ATLAS + "Barrierefreiheit – Haltekanten" (PRM-perronranden, dagelijks) + SBB BehiG-dataset — hoog.
- **BE/FR**: geen bekende open perronhoogte-API; SNCF "accessibilité en gare"-datasets bestaan — te verifiëren.
- **OSM**: aanvulling (wheelchair, platform-tags); hoogte zelden ingevuld — niet als primaire bron.

## 7. Samenvattend risico-overzicht

- **Solide officieel/open**: CH (alles), NL (NS-portaal + OVapi/NDOV + rijdendetreinen), BE realtime (NMBS GTFS-RT), FR realtime (met 60-min-horizon), DB Timetables, stationsdata DE/NL/CH.
- **Onofficieel maar praktisch onmisbaar**: iRail (BE-samenstelling), bahn.expert Wagenreihung V4 (DE-samenstelling), db-vendo-client (DE Auslastung), DE-historiek (Bahn-Vorhersage, piebro).
- **Expliciet fragiel (aug 2026)**: alles rond bahn.de/vendo (actieve blocking, outage juli 2026); iRail-upstream.
- **Gaten**: FR-samenstelling (niets), FR/BE-drukteprognose, DE officiële historiek, DE landelijke GTFS-RT.
- **Achter login, nog hard te maken**: NS-productcatalogus/quota, RIS-quota, data.belgianmobility.io-inhoud, Infrabel-punctualiteit, SNCF-toegankelijkheidsdata.

## 8. Prijzen en reserveringsbeschikbaarheid

Kernonderscheid: **prijsindicatie** (vast/berekenbaar tarief) vs. **live dynamische prijs + beschikbaarheid** (query op boekingssysteem; officieel vrijwel altijd B2B-only).

| Land/dienst | Prijsindicatie (statisch) | Live dynamisch + beschikbaarheid |
|---|---|---|
| NL binnenland | **NS API `/v3/price`** — officieel, gratis: params o.a. adults/children, travelClass, discount-enum (0/20/40%); respons alle productvarianten in centen | n.v.t. (geen reserveringsplicht) |
| BE binnenland | km-tarief met plafond op 120 tariefkm (max 2e kl. ≈ €20,90 per 2026); tabellen alleen als PDF → eenmalig digitaliseren, jaarlijks (feb) bijwerken | n.v.t. |
| DE | — (alles dynamisch) | **db-vendo-client** — onofficieel, werkt (v6.11.1 juli 2026), BahnCard/`bestprice`/leeftijd; fragiel: blocking, ~60 req/min, 403 op datacenter-IP's |
| FR | SNCF open datasets (ODbL): TER/Intercités-barema's volledig; TGV inOui/Ouigo alleen **min–max-vork** per O-D; "tgvmax"-dataset voor MAX-beschikbaarheid | **feitelijk dicht**: sncf-connect achter Datadome, wrappers dood, officieel alleen B2B (OSDM, €10k garantie) |
| CH | **OJP Fare (beta)** op opentransportdata.swiss — live NOVA-tarief incl. Halbtax, gratis key, ~50 req/min; plus OSDM-offline-tarievenbestand | Supersavers/Saver Day Pass: alleen partner-API (b2p/NOVA, contractueel) — geen hobbyroute |
| NS International | — | geen route (B2B-only); corridor A'dam–Berlijn deels via db-vendo-client |
| Eurostar (incl. ex-Thalys) | — | geen route; partner-only API + actieve bot-bescherming. **Grootste gat** |
| Nightjet (ÖBB) | — | onofficiële nightjet.com-API (gedocumenteerd in `MartinLangbecker/night-train-apis`, ook European Sleeper); inmiddels captcha + proof-of-work — wisselvallig. ÖBB-HAFAS geeft prijzen maar niet de lig-/slaapcategorieën |

Aggregators: Trainline/Rail Europe/Distribusion/Omio = B2B-only, geen hobbyist-toegang. **All Aboard (allaboard.eu)** heeft de laagste drempel (publieke docs; dekking o.a. NS, SNCF, SBB) — B2B, prijs navragen. OSDM-sandboxes (o.a. **Benerail** — systeemleverancier NS/SNCB — en Bileto met echte data) zijn gratis en nuttig om te prototypen, maar productie-tarieven vergen altijd een carrier-contract.

Reisgezelschap-parameters per kanaal: NS API kent adults/children + kortings-enum (abonnement zelf mappen, geen leeftijden); db-vendo-client kent leeftijd + BahnCard maar praktisch 1 reiziger per query; OJP Fare kent Halbtax + klasse maar negeert leeftijd en meerdere reizigers. Consequentie: het reisgezelschap-model moet per kanaal degraderen (bv. prijs per reiziger apart opvragen en optellen).

Ontwerpimplicaties:

1. Bouw op de drie gratis officiële pijlers: NS API (NL-prijzen), opentransportdata.swiss (CH-tarieven), SNCF open datasets (FR-barema's + TGV-vork), plus een zelf gedigitaliseerde BE-tarieftabel.
2. Accepteer één onofficiële afhankelijkheid: db-vendo-client voor DE + ICE International — vanaf residentieel IP, met backoff, en met verwachting van periodiek onderhoud.
3. Eurostar/NS International: toon statische tariefvork of link door naar de boekingssite; programmatisch is er (aug 2026) niets houdbaars.
4. Kortingskaart-dekking: BahnCard via vendo, Halbtax via OJP Fare, NS-kortingsvarianten via NS API; SNCF Carte Avantage alleen in kanalen die niet te automatiseren zijn.
