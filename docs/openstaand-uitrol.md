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

- [ ] **5. Cadansmeting over een etmaal** — of alle taken op de VM hun bedoelde
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
