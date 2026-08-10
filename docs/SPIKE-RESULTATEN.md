# Spike-resultaten (fase 0)

*Uitgevoerd 2026-08-09 op de laptop (macOS, M-serie). Meetdata: `data/metingen.csv`; deelrapporten in `data/rapporten/`. Structuur volgt de zes spike-vragen uit PLAN.md §8.*

## 1. Hoe groot zijn de feeds werkelijk, en wat blijft er na rail-filtering over?

| Feed | Download | Uitgepakt | Trips vóór | Trips ná rail-filter |
|---|---|---|---|---|
| NL (OVapi) | 238 MB / 46 s | 1.547 MB | 1.007.188 | 39.636 |
| BE (NMBS) | 8,8 MB / 2 s | 130 MB | 65.702 | 58.455 |
| FR (SNCF) | 4,7 MB / 1 s | 80 MB | 47.296 | 44.957 |
| DE-FV (gtfs.de) | 0,4 MB | 2,7 MB | 5.261 | 5.261 |
| DE-RV (gtfs.de) | 11 MB / 2 s | 78 MB | 100.823 | 100.823 |
| DE-DELFI *(nagemeten 2026-08-10)* | 451 MB | 4.127 MB | 2.638.853 | 154.047 |
| CH (opentransportdata) | 211 MB / 35 s | 3.212 MB | 1.840.796 | 254.795 |

Totaal ~5 GB uitgepakt; na filtering en merge: **503.927 trips, 5,8 M stop_times, 39.080 stops, 3.791 routes, 243 agencies**. CH is (verrassend) de grootste feed, groter dan NL, en reikt diep in Frankrijk (stations tot Agde en Aix-en-Provence staan erin).

**Conclusie**: de aanname uit PLAN.md §2 klopt. NL en CH vergen filtering; BE/FR/DE zijn al (vrijwel) rail-only.

## 2. Wat kost de ETL, en past dat in een GitHub Actions-runner?

| Stap | Wall time | Piek-RSS |
|---|---|---|
| Download (alle 6) | ~90 s | — |
| Rail-filter (s2, alle 6) | ~7 s | 2,3 GB (CH) |
| Merge + dedup (s3) | 22,5 s | 1,2 GB |
| Export + compressie (s5) | 92 s | — |

Totaal < 4 minuten; disk ~6 GB. Een GitHub Actions-runner (7 GB RAM, 14 GB disk, 6 u limiet) kan dit **ruimschoots** aan. **Hostingbesluit §7.1 bevestigd**: dagelijkse ETL via Actions is haalbaar; dataset-distributie via R2/Releases.

DuckDB was de juiste keuze: het stop_times-filter op NL/CH (grootste query) bleef onder 2,3 GB en secondenwerk.

## 3. Hoe erg is het grensstation-/duplicatenprobleem?

- 13.511 stationsclusters, waarvan 3.649 met UIC-code; **1.885 clusters komen in ≥2 feeds voor** (rapport: `data/rapporten/grensstations.md`).
- UIC-dekking per feed (aandeel stations aan een UIC-cluster gekoppeld): **FR 99%, BE 87%, CH 44%, NL 6%, DE 3-6%**. NL/DE gebruiken eigen id's; daar draagt de naam+afstand-fallback (≤300 m) het werk — die clusterde o.a. Aachen Hbf correct over drie feeds.
- Duplicaat-treindetectie (≥80% overlappende (cluster, tijd±2 min)-events): werkt inhoudelijk — steekproef toonde échte matches (Léman Express-ritten die in CH- én FR-feed staan; NL↔DE-grensritten). De ruwe paartelling (222k) is echter **opgeblazen doordat dienstdagen genegeerd worden**: CH modelleert één trip per dag, FR één per patroon, dus dag-varianten multipliceren tegen elkaar. Distinct: o.a. 33k CH-trips ↔ 17k FR-trips, 580 DE-RV ↔ 487 NL.

**Lessen voor de productie-ETL**: (a) dedupliceren moet dienstdag-bewust; (b) naamnormalisatie moet suffixen als "(NL)" en spellingvarianten aankunnen — "Maastricht" (NL-feed) en "Maastricht (NL)" (BE-feed) clusterden nu niet samen, net als Randwyck/Randwijck; (c) beleid: nationale feed is de bron van waarheid op eigen grondgebied.

## 4. Zit er genoeg in de feeds voor de MVP-constraints?

- **Kolommen**: NL en BE zijn rijk (`bikes_allowed`, `wheelchair_accessible`, `platform_code`, `wheelchair_boarding` aanwezig). FR en DE-free missen dat alles én `trip_short_name` (treinnummers zitten daar in routenamen). CH heeft extended route types (100–117) en een `frequencies.txt` (in de ETL nog controleren of rail-trips die gebruiken).
- **Shapes**: alleen NL (3,9 MB parquet) — bevestigt het eerdere beeld.
- **Internationale treinen** (dekkingsmatrix: `data/rapporten/dekkingsmatrix.md`, 50.049 internationale trips):
  - **Eurostar zit in de NL-feed** (NS International; corridors BE-FR-NL en BE-FR-GB-NL, dus inclusief Londen) en als ex-Thalys in DE-RV; **niet in de BE- en FR-feeds**. Eurostar-dekking hangt dus aan de NL-feed.
  - Nightjet: in NL (NS Int), BE (NMBS), CH en DE. European Sleeper: NL + DE-RV. FlixTrain: alleen DE-RV. ICE International, IC Berlijn, EC Amsterdam-Brussel: aanwezig.
  - TGV Lyria rijdt onder SNCF-routecodes (001A/001B) in CH- en FR-feed; de merknaam staat nergens in de data.
  - **Geen van de verwachte diensten ontbreekt volledig** — de "zit nergens in"-lijst is leeg, met de kanttekening dat Eurostar Londen van één feed afhangt.

## 5. Hoe groot wordt de app-dataset, en is naïeve RAPTOR snel genoeg?

Compressie van de gemergde rail-only dataset (incl. clusters):

| Variant | Grootte |
|---|---|
| CSV onbewerkt | 771 MB (waarvan 9,1 M calendar_dates-rijen) |
| zip (deflate-9) | 77 MB |
| **tar.zst (19)** | **35 MB** |
| parquet + zstd | 37 MB |
| NL-shapes (parquet, apart) | 3,9 MB |

De "tientallen MB"-aanname klopt. **RAPTOR-prototype** (dienstdag 2026-08-12: 81.417 trips, 12.641 RAPTOR-routes; laden 1,1 s, 592 MB RSS):

| Query (vertrek) | Beste aankomst | Mediane querytijd |
|---|---|---|
| Amsterdam C → Lyon Part-Dieu (08:00) | 17:06 (4 overstapronden; 20:06 bij 2) | 41 ms |
| Utrecht C → Basel SBB (07:30) | 15:48; r1 vindt de directe **Nightjet** (aankomst 06:38 volgende dag) | 28 ms |
| Amsterdam C → Maastricht (09:00) | 12:55 met overstappen | 12 ms |
| Maastricht → Liège-Guillemins (09:00) | 09:50 direct | <1 ms |

Plausibiliteit: de op het oog vreemde Amsterdam→Maastricht-uitkomst bleek **correct** — de feed toont de IC2700/2900 op die dag ingekort tot Utrecht/Amsterdam (zomerwerkzaamheden), dus het overstapadvies klopt. Naïef Python zit 100× onder de vooraf gestelde 5-seconden-drempel ⇒ **on-device routering in Kotlin is ruim haalbaar**.

## 6. Archiveert transport.data.gouv.fr de Franse GTFS-RT al?

**Nee.** De "Ressources historisées"-sectie archiveert alleen de statische GTFS en NeTEx (dagelijkse versies); de vier realtime-feeds (GTFS-RT TU/SA, SIRI) worden niet gearchiveerd (gecheckt 2026-08-09). **De eigen collector in de fase-0.5-aggregator is dus noodzakelijk** voor Franse rit-niveau-punctualiteit — niet slechts nice-to-have.

## Beslissingen voor fase 1

1. **Hosting**: GitHub Actions-ETL + R2/Releases-distributie definitief haalbaar (marges ruim).
2. **Datasetformaat**: tar.zst of parquet+zstd (~35-40 MB); calendar_dates niet vooraf uitvouwen in het distributieformaat (comprimeert prima), wel bij het laden.
3. **ETL-verbeteringen**: dienstdag-bewuste dedup; betere naamnormalisatie ("(NL)"-suffix, spellingvarianten); nationale-feed-voorrang per grondgebied; CH-frequencies checken; 714/tram/metro-exclusies zijn gevalideerd.
4. **DELFI vervangt gtfs.de voor DE** — nagemeten 2026-08-10 (levering 20260810, registratie gedaan; bestand blijkt zonder login downloadbaar, URL gedateerd → ontdekstap in s0):
   - Horizon 25-07 t/m **12-12-2026** (volledig dienstregelingjaar) vs. 30 dagen bij gtfs.de-free.
   - Railfilter: 2.638.853 → 154.047 trips (1.204 routes, 17.461 stops, 2,18 M stop_times) in 4,3 s, piek 1,5 GB — past in de Actions-runner; gefilterd ~15 MB parquet.
   - **Rijker dan gtfs.de-free**: `trip_short_name` (treinnummers), `bikes_allowed`, `wheelchair_accessible`, `wheelchair_boarding`, `platform_code`, levels/pathways én **shapes** (2,8 MB parquet rail-only) — DE schuift daarmee bij de constraint-kolommen (§4) van "mist alles" naar de NL/BE-klasse, en NL is niet langer het enige land met shapes.
   - Internationale FV-dekking aanwezig: DB Fernverkehr, ÖBB, SBB, SNCF, Eurostar, FlixTrain, European Sleeper, PKP, ČD, Trenitalia.
   - Kanttekening: 154 k DELFI-trips vs. 106 k bij gtfs.de (FV+RV) — grotendeels de langere horizon; dedupmodel (§3) opnieuw ijken bij de merge.
5. **Eurostar** komt uit de NL-feed — monitoren dat dat zo blijft.
6. **RAPTOR**: architectuur bewezen; volgende stap is de Kotlin-port met voetpaden/transfers en dienstdag-runtime i.p.v. voor-uitgevouwen dag.

## Bekende beperkingen van de meting

- Duplicaat-paren tellen dag-varianten dubbel (mechanisme klopt, absolute aantallen niet).
- Checklist-zoektermen zijn ruw (de Nightjet-kolom overtelt door de zoekterm "en "); de corridor-matrix is leidend.
- RAPTOR getest op één dienstdag, zonder transfers.txt/voetpaden en zonder ontdubbelde duplicaat-trips; querytijden zijn daardoor een onderschatting van de definitieve dataset, maar de marge (100×) dekt dat ruim.
- FR-stops met buitenlandse UIC-prefixen buiten de vijf landen (bv. Spaanse 71-codes) kregen het land via polygonen, niet via UIC.
