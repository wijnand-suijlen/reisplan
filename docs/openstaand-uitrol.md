# Openstaand: uitrol van de cluster-id-fix en de Actions-publicatie

Werklijst bij de wijzigingen van 12 september 2026. **Verwijder dit bestand zodra
alles afgevinkt is.** Achtergrond: `docs/geheugen-op-1gb.md`.

## Waar het over gaat, in één alinea

Stations zonder UIC-code kregen een cluster-id uit een oplopende teller, die elke
merge opnieuw begon. Daardoor verloor `randen.json.gz` — het enige artefact dat
een merge overleeft — zijn sleutels, en werd 30,7 % van de kaart een rechte lijn
tussen twee stations in plaats van het echte spoor. De id's komen nu uit de
inhoud (`84ecd46`), de geometrie staat in de repo (`a58e199`), en `laad_randen()`
faalt niet meer stil. Daarmee kan GitHub Actions de publicerende kant worden
waarvoor het in augustus ontworpen is.

## Uitrol afgerond, 12 september 15:37 UTC

Verversing 11:09 → 15:34 (4 u 25 min; de aggregator lag stil 12:13–13:32).
Units geïnstalleerd, aggregator herstart om 15:36. Alles wat hieronder als
"Claude 1–4" stond is gedaan.

| meting | vóór | ná |
|---|---|---|
| rechte-lijn-fallbacks op de kaart | 11.971 van 38.992 (30,7 %) | **2.130 van 29.158 (7,3 %)** |
| gekleurde baanvakken in de snapshot | 6.494 | **11.241** |
| statisch plafond van de stationsselectie (s10) | 7.204 randen | **12.321 randen** |
| clusters | 13.428 | 13.515 (3.641 met uic) |

Per land — let op dat de kolom "baanvakken" krimpt: de verdwenen features zijn de
rechte lijnen die er nooit hadden moeten staan.

| land | baanvakken | rechte lijnen | in snapshot |
|---|---|---|---|
| de | 21.252 → 14.654 | 7.736 → **1.135** | 679 → **1.412** |
| nl | 4.126 → 3.193 | 1.010 → **78** | 721 → **1.608** |
| be | 1.603 → 1.500 | 145 → **41** | 652 → **999** |
| fr | 4.883 → 4.881 | 193 → 191 | 2.394 → **3.740** |
| ch | 6.627 → 4.435 | 2.386 → **190** | 2.047 → **3.471** |

Frankrijk is vrijwel onveranderd, precies zoals de diagnose voorspelde: de Franse
dienstregeling was in dat maandje het minst verschoven, dus daar bleven de
sleutels toevallig kloppen.

**Twee oorzaken, niet één.** De snapshot ging van 6.494 naar 11.241, maar dat is
de som van twee ingrepen van dezelfde dag: het kleuringsvenster van 30 min naar
2 uur bracht het naar ~9.600, de geometriefix deed de rest. De fallback-cijfers en
het s10-plafond zijn wél zuiver aan de cluster-id-fix toe te schrijven.

De VM en GitHub Actions produceerden onafhankelijk van elkaar **exact dezelfde**
`segments.geojson`-regel (29.158 randen, 2.130 fallbacks) uit dezelfde feeds en
dezelfde meegecommitte geometrie. Dat is het bewijs dat de sleutels nu stabiel
zijn: vóór de fix waren twee merge-runs het per definitie oneens.

---

## Wat Claude doet

- [x] ~~**1. Verversing afwachten en controleren.** Gestart 11:09 UTC, duurt ~6,5 uur.
      Letten op: geen tracebacks, `clusters:`-regel met ~13.500 clusters,
      `segments.geojson:`-regel met een laag fallback-aandeel.

- [x] ~~**2. Unit-bestanden installeren** (vergt `daemon-reload`, dus pas ná de
      verversing). Drie bestanden zijn gewijzigd:
      - `deploy/statisch-vernieuwen.timer` — wekelijks naar maandag 00:00
        Nederlandse tijd in plaats van 04:30 UTC
      - `deploy/statisch-vernieuwen.service` — herstart de aggregator na de
        na-fase, zodat de nieuwe `eva_stations.json` geladen wordt
      - `deploy/aggregator-herstart.service` — `ExecCondition` die de nachtelijke
        herstart overslaat zolang de verversing draait

- [x] ~~**3. Aggregator herstarten** na het installeren, zodat hij de nieuwe
      `eva_stations.json` en `merged.duckdb` oppakt. Deze ene keer handmatig; vanaf
      volgende week doet de service het zelf.

- [x] ~~**4. Nameten en rapporteren**~~ ✅ *zie de tabel hierboven.* Oude tekst: Verwacht: rechte-lijn-aandeel van 30,7 % naar
      ~6 %, en 82,4 % van de Duitse stationsparen met echte spoorgeometrie in
      plaats van 2,3 %. Uitkomst verwerken in `docs/geheugen-op-1gb.md`.

- [ ] **5. Cadansmeting over een etmaal** (zondag 13 sep; de verversing van
      zaterdag vervuilt een eerdere meting) — of alle taken op de VM hun bedoelde
      ritme halen na de ingrepen van vanochtend (agents uit, buildvenster
      gehalveerd, dekkende index). Kan pas zondag, want de verversing van vandaag
      vervuilt de meting.

- [x] ~~**6. De dubbele upload uitzetten**~~ ✅ *gedaan 12 sep, maar andersom dan
      gepland.* Ik wilde de upload uit `main.py` halen; dat was verkeerd om.
      `segments.geojson` moet passen bij de rand-id's in `snapshot.json`, en die komt
      van de aggregator uit diens eigen `merged.duckdb`. Actions merged dagelijks, de
      VM wekelijks — dus juist Actions moet de geojson niet publiceren. Bijkomend
      argument dat pas bij de meting bleek: `aws s3 cp` comprimeert niet, dus Actions
      zette er 9,8 MB neer waar de aggregator 1,9 MB gzipt met `ContentEncoding`.
      `segments.geojson` is uit de R2-stap van `etl.yml` gehaald; de gzipte versie is
      handmatig teruggezet (16:04).

---

## Tweede ronde, 12 september 16:00–18:00 UTC — **nog niet geverifieerd**

Ná de uitrol hierboven is er nog aan de clustering en de workflows gewerkt. Die
wijzigingen staan op `main` maar zijn op de VM **nog niet zichtbaar**: de kaart
wordt alleen door de VM gepubliceerd, en die pakt nieuwe code pas op bij de
wekelijkse verversing.

| commit | wat |
|---|---|
| `18fb8ad` | pages: checkout v7, upload-pages-artifact v5, deploy-pages v5 — geverifieerd groen |
| `f2df65d` | etl: checkout v7, upload-artifact v7, setup-uv **v10.1.0** — geverifieerd groen |
| `a9e8948` | clusteringfout 1 en 2: gridcelgrens + landsuffix, 77 duplicaten weg |
| `e2f5f3e` | synoniementabel + **ß-fold gerepareerd**, 33 duplicaten weg |

- [ ] **7. Maandag 14 september na ~02:25 controleren of dit klopt op de kaart.**
      De verversing start zondag 22:00 UTC (= maandag 00:00 lokaal) en publiceert
      de nieuwe `segments.geojson` zodra de aggregator ná de mergefase opstart —
      naar de fasetijden van 12 september rond 02:25 lokaal, klaar rond 04:25.
      Wat er dan moet kloppen:

      | meting | nu op de VM | verwacht |
      |---|---|---|
      | rechte-lijn-fallbacks | 2.130 van 29.158 (7,3 %) | ~1.738 van ~28.553 (**6,1 %**) |
      | clusters | 13.515 | ~13.408 |
      | clusterparen binnen 300 m | ~660 | ~627 |

      Let ook op: tussen ~02:25 en ~04:25 draait de aggregator met de nieuwe
      `merged.duckdb` maar nog de oude `eva_stations.json` (s10 draait in de
      laatste fase). De Duitse dekking is in dat venster dun; dat hoort zo en de
      afsluitende herstart dicht het.

- [ ] **8. Kaartnamen nakijken.** Door de samenvoegingen is de overlevende
      clusternaam soms de Franse: de tooltip gaat "Anvers-Central" tonen in plaats
      van "Antwerpen-Centraal". De naam komt van het eerste station in de groep en
      dat is willekeurig. Vraagt een voorkeursregel — bijvoorbeeld de naam uit de
      feed van het land waar het station ligt — maar dat is een keuze, geen bug.

- [ ] **9. `planned_closures` nakijken.** Stond na de uitrol op 12.375 rand-dag-
      blokken tegen 3.255 lokaal. Als de kaart veel rode puntjeslijnen toont, is
      dat het eerste om te onderzoeken. Geen bewijs dat het fout is.

## Wat jij doet

### ~~A. Controleren dat Actions het nu goed doet~~ ✅ *gedaan 12 sep: 2.130 van 29.158 fallbacks (7,3 %), geen tracebacks, geen id-botsingen*

De dagelijkse ETL draait vanzelf om 03:30 UTC, maar je kunt hem ook meteen
starten: **Actions → dataset-etl → Run workflow**. Ik kan dat zelf niet; mijn
token heeft alleen Contents-rechten, geen Actions.

Waar je op let in het log, bij de stap *Segments-geojson*:

```
segments.geojson: <N> getekende randen (<M> rechte-lijn-fallbacks); ...
```

Goed is M/N rond de 6 %. Ging het mis, dan staat er `16062 van 16062` zoals elke
dag tot nu toe — of faalt de stap hard met "geen spoorgeometrie", wat betekent dat
`randen.json.gz` niet in de checkout zit.

### ~~B. De R2-sleutels op GitHub zetten~~ ✅ *gedaan 12 sep; geverifieerd doordat `dataset.tar.zst` (35,4 MB) voor het eerst in R2 verscheen*

GitHub → de repo → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Vier keer, exact deze namen:

| Secret | Waarde |
|---|---|
| `R2_ENDPOINT` | uit `/home/wijnandsuijlen/reisplan/.env` op de VM |
| `R2_BUCKET` | idem |
| `R2_ACCESS_KEY_ID` | idem |
| `R2_SECRET_ACCESS_KEY` | idem |

Uitlezen:

```
ssh -F ~/.config/reisplan/ssh/config google_micro 'grep ^R2_ ~/reisplan/.env'
```

**Waarom pas daarna:** tot de VM op de nieuwe cluster-id's draait, zouden Actions
en de VM twee verschillende `segments.geojson` naar dezelfde R2-sleutel schrijven.

**Overweeg een aparte R2-token** met schrijfrechten op alleen deze bucket. De repo
is publiek; fork-PR's krijgen geen secrets, maar iedereen die naar `main` kan
pushen kan ze via een workflow uitlezen.

### ~~C. Beslissen over de starttijd~~ ✅ *besloten 12 sep: middernacht blijft*

Overwogen is zondag 22:00 lokaal, voor twee uur extra marge op de ochtendspits.
Afgewezen, en om een betere reden dan de marge: om 22:00 rijden de laatste
zondagse treinen nog. De 78 minuten dat de aggregator stilligt zouden dan precies
over dat staartje vallen, en die ritten worden dan niet geregistreerd — de
punctualiteitshistorie krijgt elke week een gat op hetzelfde moment. Vanaf
middernacht valt de stilstand rond 02:15–03:35, wanneer er vrijwel niets rijdt.

De prijs is dat de staart (s10, read-only) tot ~06:30 doorloopt en de spits kan
raken als een feed uitschiet. Dat is de goedkopere van de twee kwaden: s10 laat de
aggregator gewoon draaien.

### ~~D. De git-credential-keten rechtzetten~~ ✅ *gedaan 12 sep*

---

## Eigendom van de R2-objecten, zoals het nu staat

| object | eigenaar | waarom |
|---|---|---|
| `snapshot.json` | VM, elke minuut | enige bron |
| `segments.geojson` | VM, bij aggregator-start | moet bij de snapshot passen; wordt gzipt |
| `dataset.tar.zst` | Actions, dagelijks | de VM draait `s5_compress` niet |
| `randen.json.gz` | de repo | traag bewegende invoer sinds `a58e199` |

## Plan: hoe een baanvak zijn lijnvoering krijgt

Onderzocht 12–13 september 2026, na een vraag over het label op een baanvak tussen
Weert en Roermond. Niets hiervan is geïmplementeerd.

### Het probleem

`spike/s8_geometrie.py` routeert elk paar opeenvolgende stops met A* over het
OSM-spoornet. Bij stops die dicht op elkaar liggen gaat dat goed. Bij een **lange
sprong** — een trein die honderden kilometers geen stop heeft — kiest de A* een
pad dat over infrastructuur klopt maar niet de route is die de trein rijdt.

Twee gevallen, allebei nachttreinen, allebei uit de dienstregeling geverifieerd:

| trein | sprong | duur |
|---|---|---|
| European Sleeper Berlijn–Parijs (NMBS-feed) | Hamburg-Harburg → Bruxelles-Midi | 9 u 16 |
| Intercités de Nuit Parijs–Toulouse (SNCF-feed) | Les Aubrais → Cahors | 5 u 53 |

De eerste werd over de **IJzeren Rijn** gerouteerd (Weert–Hamont, op Nederlands
gebied al jaren buiten dienst, in OSM getagd `usage=industrial service=spur
maxspeed=40 electrified=no`). De tweede over de POLT via Limoges, wat juist
correct is.

**De schade is beperkt en cosmetisch.** `delta.py` verdeelt waarnemingen over de
*verfijnde* bladsegmenten, niet over de grove sprong. Gemeten op de snapshot van
12 september: van de 3.164 randen die alleen door sprongen bereden worden zijn er
**21 gekleurd** (0,7 %). De IJzeren Rijn is wél getekend en **niet** gekleurd. Het
foute pad bepaalt dus welke lijnen er op de kaart stáán, niet welke kleuren.

### Vier aanpakken geprobeerd, alle vier stuk op dezelfde grens

| aanpak | lost op | breekt | gemeten |
|---|---|---|---|
| A* op afstand (huidig) | — | sluiproutes over dood spoor | IJzeren Rijn |
| A* op **reistijd** (`lengte/maxspeed`) | IJzeren Rijn verdwijnt | omweg van +222 km via Bordeaux bij Les Aubrais–Cahors | volledige run: 18.865 paden (was 18.577), 235 mislukt (was 569), 49,9 % identiek, mediaan +0,0 km, p90 +0,3 km |
| randen uitsluiten die **alleen door sprongen** bereden worden | — | hogesnelheidslijnen hebben per definitie geen tussenstations en vallen mee af | 3.164 randen, 15.461 km |
| **de verfijning volgen** in plaats van het A*-pad | IJzeren Rijn verdwijnt | 177 van de 3.164 verdwijnende randen liggen op spoor van ≥ 200 km/u | zie hierboven |

De rode draad: elke regel die een fout pad wegneemt, neemt ook een terecht pad
weg. Welke corridor een trein gebruikt staat nergens in de infrastructuurdata.
Snelheid weegt niet mee dat een nachttrein soms een uur stilstaat en dus helemaal
niet de snelste route hoeft te nemen.

### Waar het wél in staat: `shapes.txt`

GTFS heeft hier een standaardonderdeel voor: `shapes.txt` geeft per rit de
werkelijke lijnvoering als polyline. Van de zeven feeds hebben er twee dat, en ze
staan al op schijf:

| feed | ritten met `shape_id` | unieke shapes | gefilterd |
|---|---|---|---|
| `de_delfi` | 154.047 / 154.047 (100 %) | 19.122 | 2,9 MB parquet |
| `nl` | 39.636 / 39.636 (100 %) | 517 | 3,9 MB parquet |

`be`, `fr`, `ch`, `de_fv` en `de_rv` leveren geen shapes — nagekeken in de
gedownloade archieven zelf. De SNCF-GTFS die wij ophalen
(`Export_OpenData_SNCF_GTFS_NewTripId.zip`) bevat acht bestanden en geen shapes,
ondanks wat zoekresultaten beweren. Voor European Sleeper is geen open data
gevonden.

**Twee dingen liggen ongebruikt:**
- `s2_filter_rail.py` filtert de shapes keurig naar `shapes_f`, maar
  `s3_merge_dedup.py` neemt de tabel niet mee. De kolom `trips.shape_id` overleeft
  wél — 100 % van de NL-ritten heeft er een — maar er is geen shapes-tabel om hem
  op te zoeken.
- **DELFI zit helemaal niet in de merge.** `stop_times` bevat alleen `de_fv` en
  `de_rv`. De enige Duitse bron mét lijnvoering wordt gedownload, gefilterd en
  daarna genegeerd.

Potentiële dekking, met 20.490 stationsparen waarvan 4.513 grove sprongen:

| bron | paren | grove sprongen |
|---|---|---|
| NL (exact gemeten) | 809 (3,9 %) | 231 (5,1 %) |
| DE via DELFI (**schatting**, zie hieronder) | 11.148 (54,4 %) | 2.040 (45,2 %) |
| samen | **11.880 (58,0 %)** | **2.226 (49,3 %)** |
| rest (BE/FR/CH) — houdt A* | 9.083 (44,3 %) | 2.394 (53,0 %) |

De Duitse 54,4 % is een **kandidaatstelling, geen dekking**: geteld is welke paren
`de_rv`/`de_fv` bedienen, met de aanname dat DELFI die ook kent. Aannemelijk
(154.047 ritten tegen 100.823) maar niet gecontroleerd, omdat DELFI's haltes niet
in `stop_cluster` staan. Dat is pas hard te maken nadat DELFI meegemergd is.

### De voorgestelde volgorde

Per stationspaar, in deze volgorde het pad bepalen:

1. **Heeft de rit een `shape_id`?** Gebruik de shape. Exact, van de vervoerder.
2. **Rijdt dezelfde trein in een andere feed die wél shapes heeft?** `s3` berekent
   al 224.316 duplicaat-tripparen; DELFI wordt daar een grote leverancier in.
3. **Bestaat er een verfijningsketen?** Die is afgeleid uit andere treinen die op
   de tussenliggende stations stoppen, en had voor Les Aubrais–Cahors de POLT al
   goed. Alleen niet toepassen waar het pad over een hogesnelheidslijn loopt.
4. **Anders A***, met de bekende beperkingen.

### Werk dat daarvoor nodig is

- `s3_merge_dedup.py`: de shapes-tabel meenemen in de merge.
- `s0`/`s2`/`s3`: DELFI in de merge opnemen.
- `maak_segmenten.py`: shapes verkiezen boven het A*-pad; pas terugvallen op de
  verfijning en daarna op A*.
- Meten hoeveel van de Duitse paren DELFI werkelijk dekt, zodra dat kan.

### Nog een artefact met hetzelfde euvel

`cluster_land` komt uit `spike/s4_coverage_intl.py`, die niet in `vernieuw.sh`
staat. Na de cluster-id-wijziging van 12 september wijzen nog **3.649 van de
13.511 rijen** naar een bestaand cluster — precies de `uic:`-clusters. Lokaal
geeft de tabel daardoor stilzwijgend verkeerde antwoorden. Op de VM bestaat hij
niet en `statisch.py` doet een `LEFT JOIN`, dus productie loopt geen gevaar. Zelfde
klasse als `randen.json.gz`: een artefact gesleuteld op cluster-id's dat niet
meeververst. Ofwel s4 in de pijplijn, ofwel de tabel weg.

## Later, niet urgent

Uit het onderzoek van vandaag, op volgorde van verwachte opbrengst:

- **`BATCH_SIZE` in `db_timetables.py`** van 4 omhoog. De hoofdlus heeft weer lucht
  en het API-budget is voor tweederde onbenut; de Duitse rondetijd gaat dan van
  ~37 naar ~21 minuten, ruim onder het observatievenster van 45. Raakt de dekking,
  niet het geheugen.
- **De inspectiebuild van de VM halen.** Minder dringend sinds `WINDOW_S` op 2 uur
  staat en de builds van 775 s naar ~150 s gingen, maar het blijft de zwaarste
  taak op de machine.
- **Geheugenopties die nog open liggen**: `_laatste_seg` compacter (~40 MB, de
  waarde is nu een tuple van 240 bytes per entry), `CACHE_MAX` verlagen (~20 MB),
  `TRIP_STATE_TTL_S` naar 2 uur (~10 MB).
- **`VACUUM` op `observaties.sqlite`** — nu niet nodig. De dekkende index heeft de
  vrije lijst opgesoupeerd (0 vrije pagina's) en het hete leespad raakt de tabel
  niet meer aan.
- **s8 opnieuw draaien** is alleen nodig als de stationsset wezenlijk wijzigt — nu
  de id's stabiel zijn, klopt die aanname uit PLAN.md weer. Het kan niet op de VM
  (4,3 GB piek, gemeten); het kan lokaal in 47 s, of in GitHub Actions.
- **`docs/vm-beheer.md`** bijwerken met de twee nieuwe units
  (`reisplan-aggregator-herstart`) en de gewijzigde starttijd van de verversing.
