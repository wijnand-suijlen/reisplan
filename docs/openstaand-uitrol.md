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

      **Dit kan uit het R2-archief, niet op de VM** (gevonden 13 sep bij de
      Cléon-casus). De `ts`-kolom in `rt-archive/stops/<dag>.parquet` geeft de
      snapshotmomenten; met `lag()` per land krijg je de intervallen over een heel
      etmaal zonder de aggregator te knijpen. Eerste blik op 12 september:

      | land | snapshots | mediaan | p90 | grootste gat |
      |---|---|---|---|---|
      | de | 4.776 | 11 s | 22 s | 8.600 s |
      | nl | 1.059 | 63 s | 209 s | 8.544 s |
      | be | 810 | 63 s | 84 s | 8.771 s |
      | ch | 742 | 93 s | 147 s | 8.682 s |
      | fr | 566 | 123 s | 189 s | 5.537 s |

      Acht gaten boven de 30 minuten op één dag, met uitschieters van ruim twee
      uur. Let op de beperking: een `ts` verschijnt alleen als er íets veranderde,
      dus dit is een **ondergrens** voor de cadans, geen meting van het pollritme
      zelf. Voor de echte vraag — haalt elke taak zijn bedoelde ritme — is dit
      genoeg om de uitschieters te vinden, en pas daarna is de VM nodig.

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

> **Status: niet uitvoeren zoals het hier staat.** Een review op 13 september
> vond een groter defect (de HSL-kleuringsfout hieronder) en vijf bezwaren tegen
> de implementatievolgorde. Zie "Wat er eerst moet gebeuren".

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

Het foute A*-pad van een *verfijnde* sprong bepaalt alleen welke lijnen er op de
kaart stáán, niet welke kleuren: `delta.py:120` verdeelt waarnemingen over de
verfijnde bladsegmenten. Van de 3.164 randen die alleen door sprongen bereden
worden waren er 21 gekleurd in de snapshot van 12 september.

**Maar die geruststelling was verkeerd gericht** (gevonden bij review, 13 sep).
De fout zit niet in wat de verfijning *niet* kleurt maar in wat ze *wel* kleurt —
zie de volgende sectie. En 271 paren van meer dan 30 km hebben helemaal geen
verfijning; die kleuren, annuleren en tekenen wél rechtstreeks via hun A*-pad,
ook via `closure_baseline.py:77-82`.

## Het grootste bekende defect: de verfijning kiest de verkeerde corridor

`bouw_verfijning` (`verfijning.py:50`) accepteert een keten tot **1,3 × hemelsbreed
+ 3 km**. Een parallelle klassieke lijn past daar bijna altijd in. Gevolg, nagemeten
op de live kaart van 12 september:

`Schiphol – Rotterdam Centraal` is een sprong met **1.828 ritten**, verfijnd in 13
bladen over de **Oude Lijn**: Hoofddorp → Nieuw Vennep → Sassenheim → Leiden
Centraal → De Vink → Voorschoten → Mariahoeve → Laan v NOI → Den Haag HS → Delft →
Delft Campus → Schiedam Centrum → Rotterdam Centraal.

| | randen | gekleurd in de snapshot |
|---|---|---|
| eigen A*-pad van de sprong (de HSL-Zuid) | 5 | **2** |
| de 13 bladen (de Oude Lijn) | 39 | **39** |

Elke vertraging van Eurostar, IC direct en Thalys wordt dus over Leiden, Den Haag
en Delft uitgesmeerd terwijl de HSL grijs blijft. Zelfde patroon bij
`Köln Hbf – Frankfurt Flughafen Fernbf` (verfijnd via Köln Messe/Deutz, Porz,
Troisdorf, Wiesbaden). Parijs–Lyon gaat wél goed, omdat Le Creusot-TGV en
Mâcon-Loché als station bestaan.

Dit is een **kleuringsfout**, niet een tekenfout, en daarmee ernstiger dan het
A*-probleem waar dit onderzoek mee begon. Het is dezelfde onderliggende grens:
de verfijning kiest een corridor zonder te weten of de trein die rijdt.

Het cijfer "21 van de 3.164" kon dit per constructie niet zien — het telt kleur op
sprong-only-randen, terwijl de fout bestaat uit kleur op de *verkeerde* bladen.

### Vier aanpakken geprobeerd, alle vier stuk op dezelfde grens

| aanpak | lost op | breekt | gemeten |
|---|---|---|---|
| A* op afstand (huidig) | — | sluiproutes over dood spoor | IJzeren Rijn |
| A* op **reistijd** (`lengte/maxspeed`) | IJzeren Rijn verdwijnt | omweg van +222 km via Bordeaux bij Les Aubrais–Cahors | volledige run: 18.865 paden (was 18.577), 235 mislukt (was 569), 49,9 % identiek, mediaan +0,0 km, p90 +0,3 km |
| randen uitsluiten die **alleen door sprongen** bereden worden | — | hogesnelheidslijnen hebben per definitie geen tussenstations en vallen mee af | 3.164 randen, 15.461 km |
| **de verfijning volgen** in plaats van het A*-pad | IJzeren Rijn verdwijnt | 177 van de 3.164 verdwijnende randen liggen op spoor van ≥ 200 km/u | zie hierboven |
| **OSM-tags gebruiken in de A*** — nog niet geprobeerd | zou de IJzeren Rijn (`usage=industrial service=spur`) moeten uitsluiten zonder snelheid te belonen, dus zonder de Bordeaux-omweg | onbekend | 43,8 % van de 26.819 Nederlandse spoor-ways heeft zo'n tag, `usage=main` 45,9 % |

De rode draad: elke regel die een fout pad wegneemt, neemt ook een terecht pad
weg. Welke corridor een trein gebruikt staat nergens in de infrastructuurdata.
Snelheid weegt niet mee dat een nachttrein soms een uur stilstaat en dus helemaal
niet de snelste route hoeft te nemen.

### Er is nu een testset: `docs/nachttrein-testset.md`

Tot 13 september werd elke variant beoordeeld op één geval (de European Sleeper
over de IJzeren Rijn), en later op twee. Dat is te weinig: elke aanpak die op één
geval slaagt, faalt op het volgende. Daarom zijn alle nachttreinen door NL, BE, DE,
FR en CH nagelopen — 77 sprongen met vertrek tussen 18:00 en 02:00 en een gat van
meer dan vier uur — en vastgelegd als **vijftien testgevallen met de door de
vervoerder gepubliceerde route**: welke plaatsen de route moet aandoen en welke
niet, met bron per regel.

**Elke toekomstige routeervariant wordt hierop beoordeeld, niet op een los geval.**
Twee daarvan zijn de ijkpunten die elkaar uitsluiten: geval 1 (Hamburg–Brussel,
moet via Liège) en geval 9 (Les Aubrais–Cahors, moet over de POLT). Geen van de
vier gemeten varianten haalt beide.

De testset bevat ook een historische laag, teruggezocht tot de jaren zestig en waar
mogelijk verder. Die levert twee bruikbare feiten:

- **De corridors zijn ouder en stabieler dan de treinen.** Parijs–Liège–Köln–Berlijn
  ligt er sinds 1896, Amsterdam–Köln–Basel sinds 1928, de POLT sinds 1893, de Ligne
  des Alpes sinds 1875. Exploitanten wisselen om de paar jaar, het tracé niet.
- **Over de IJzeren Rijn rijdt sinds 1953 geen doorgaande reizigerstrein meer**
  (Neerpelt–Hamont sinds 1957; Roermond–grens buiten dienst in 1991). De router
  kiest dus een verbinding die zeventig jaar dood is, boven een die 130 jaar
  onafgebroken in gebruik is.

Dat laatste stuurt de vijfde aanpak: de straf hoort niet alleen op `service` en
`usage` te staan — die variant faalde met factor 10 — maar op de combinatie
`tracks`, `electrified` en `usage`, en zwaarder. Nog niet gemeten.

De testset corrigeerde meteen drie fouten in de eerste opzet ervan: Grenoble is bij
Parijs–Briançon géén verboden route maar de omleiding die sinds september 2025
actief is; Nîmes hoort bij de trein naar Cerbère, niet bij die naar Nice; en de
Nightjet Zürich–Hamburg rijdt via Bremen.

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

### De omleidingen maken een statische corridor onmogelijk

Nagezocht op 13 september, vastgelegd in `docs/hsl-omleidingen.md`: elke
hogesnelheidslijn in onze vijf landen heeft een klassieke lijn ernaast die als
uitwijkroute dienstdoet, en die wordt structureel gebruikt. HSL 1 ligt elke zomer
twee weken uit dienst, HSL 2 elke zomer tot 2031, de HSL-Zuid 112 dagen in 2028 en
50 in 2029, en het Duitse *Generalsanierung*-programma legt tot 2035 telkens
maandenlang een van 41 corridors plat.

Dat raakt dit plan in de kern. Bij een stremming rijdt de Intercity Direct
Schiphol–Rotterdam over de **Oude Lijn**, en passeert Leiden en Den Haag HS
**zonder te stoppen**. De feed ziet dan exact dezelfde sprong als anders. Er is
geen halte, geen rijtijd en geen OSM-tag waarmee de twee gevallen te scheiden zijn.

Daarmee is de HSL-kleuringsfout hierboven niet een bug met een statische
oplossing: de Oude Lijn is vandaag het verkeerde antwoord en in 2028 **112 dagen
lang het goede**. Alleen `shapes.txt` volgt een omleiding, want dat wordt per
dienstregelingsversie opnieuw gepubliceerd.

**Gevolg voor de volgorde hieronder**: de shape-integratie is geen verfijning voor
NL en DE meer, maar de enige aanpak die principieel klopt. Voor `be`, `fr` en `ch`
blijft A* nodig en moet de uitkomst expliciet als schatting gelden.

Eén waarschuwing uit hetzelfde onderzoek: straf geen "oud klassiek spoor", want
élke uitwijkroute is er zo een — de Oude Lijn (1847), de Gotthard Bergstrecke
(1882), de Lötschberg Bergstrecke (1913), de linke Rheinstrecke. Het bruikbare
onderscheid is niet *oud* maar *draagt geen doorgaand verkeer meer*.

### De voorgestelde volgorde

Per stationspaar, in deze volgorde het pad bepalen:

1. **Heeft de rit een `shape_id`?** Gebruik de shape. Exact, van de vervoerder.
2. **Rijdt dezelfde trein in een andere feed die wél shapes heeft?** `s3` berekent
   al 224.316 duplicaat-tripparen; DELFI wordt daar een grote leverancier in.
3. **Bestaat er een verfijningsketen?** Die is afgeleid uit andere treinen die op
   de tussenliggende stations stoppen, en had voor Les Aubrais–Cahors de POLT al
   goed. Alleen niet toepassen waar het pad over een hogesnelheidslijn loopt.
4. **Anders A***, met de bekende beperkingen.

### Bezwaren uit de review van 13 september — dit plan is zo niet uitvoerbaar

De volgorde is als *prioriteit* verdedigbaar, als *implementatie* niet.

- **Verkeerde plek.** `maak_segmenten.py` maakt geen geometrie; het consumeert
  `randen.json.gz` (regel 103-110). Geometrie ontstaat alleen in `s8_geometrie.py`.
  Een shape daar als losse polyline naast de A*-paden tekenen geeft op elke
  gedeelde corridor twee lijnen — precies de dubbeltekening die de randgebaseerde
  kaart moest oplossen (PLAN.md punt 4a). Shapes moeten in s8 **op de OSM-graaf
  gemap-matcht** worden.
- **Stap 2 bestaat niet in productie.** `vernieuw.sh:16` zet
  `REISPLAN_SLA_DUPDETECTIE_OVER=1` en `s3:362` slaat `dup_trips` dan over. De
  224.316 duplicaatparen zijn een lokaal gegeven. Bovendien matcht `dup_trips` op
  *rit*-niveau, niet op paar-niveau.
- **Een shape is niet eenduidig per paar.** Van de 809 NL-paren hebben er 33 meer
  dan één sub-shape, 17 daarvan meer dan 1 km uiteen: Schiphol–Rotterdam 1.820 via
  de HSL en 8 via de Oude Lijn, Hengelo–Bad Bentheim 115 tegen 111. Het model
  `segment → randen` neemt één pad per paar aan. Kies expliciet: meerderheid, unie,
  of een sleutel per shape.
- **Knippen verschilt per feed.** NL vult `shape_dist_traveled` voor 100 %; DELFI
  heeft die kolom niet, daar moet de stopcoördinaat op de polyline geprojecteerd
  worden. 64 projecties zijn dubbelzinnig, 255 stops liggen > 300 m van hun shape.
- **DELFI opnemen ís de "wezenlijke wijziging van de stationsset"** waar PLAN.md
  het over heeft: 968 van 17.461 DHID's hebben een herkenbare UIC, dus de rest
  herclustert en `randen.json.gz` moet mee. Plus 45 % meer `stop_times` op een
  merge die al per feed moet vanwege de 600 MB-grens. PLAN.md spreekt bovendien van
  DELFI *vervangen*, dit plan van *opnemen* — dat is eerst een beslissing.

### Wat er eerst moet gebeuren

1. **De HSL-kleuringsfout oplossen.** Dat is nu het grootste bekende defect en het
   plan bouwt stap 3 er juist op. `bouw_verfijning` mag een sprong niet op een keten
   leggen die een andere infrastructuur volgt dan de sprong zelf — wat betekent dat
   verfijning en geometrie niet langer onafhankelijk zijn. Ontwerpwijziging.
2. **De vijfde aanpak meten**, nu tegen `docs/nachttrein-testset.md` in plaats van
   tegen één geval: straf op `tracks`, `electrified` en `usage` in s8. Een middag
   werk, s8 draait lokaal in 47 s. Haalt een variant alle vijftien gevallen, dan is
   de shape-integratie geen urgentie meer maar een verfijning voor NL en DE.
3. **Dit plan herschrijven** op s8 als de plek waar shapes binnenkomen, met de vijf
   bezwaren hierboven als eisen.

### Werk dat daarna nodig is

- `s3_merge_dedup.py`: de shapes-tabel meenemen in de merge.
- `s0`/`s2`/`s3`: DELFI in de merge opnemen of `de_rv` vervangen — eerst beslissen.
- `s8_geometrie.py`: shapes map-matchen op de graaf; A* alleen waar geen shape is.
- Meten hoeveel van de Duitse paren DELFI werkelijk dekt, zodra dat kan.

### Nog een artefact met hetzelfde euvel

`cluster_land` komt uit `spike/s4_coverage_intl.py`, die niet in `vernieuw.sh`
staat. Na de cluster-id-wijziging van 12 september wijzen nog **3.649 van de
13.511 rijen** naar een bestaand cluster — precies de `uic:`-clusters. Lokaal
geeft de tabel daardoor stilzwijgend verkeerde antwoorden. Op de VM bestaat hij
niet en `statisch.py` doet een `LEFT JOIN`, dus productie loopt geen gevaar. Zelfde
klasse als `randen.json.gz`: een artefact gesleuteld op cluster-id's dat niet
meeververst. Ofwel s4 in de pijplijn, ofwel de tabel weg.

## Nieuw gat: het ongedekte interval tussen blokkade en baseline

Gevonden op 13 september bij het narekenen van de ontsporing bij Cléon van
11 september; volledig uitgewerkt in `docs/casus-cleon-2026-09-11.md`.

`blockades.py` markeerde het getroffen segment die avond correct als geblokkeerd —
vier geannuleerde ritten binnen het venster. Maar de dag erna stond er geen enkele
annulering meer op dat segment, terwijl het spoor de hele dag dicht lag: de treinen
werden niet geannuleerd maar **opnieuw gepland als kortere relatie**
(Caen ↔ Elbeuf-Saint-Aubin in plaats van Caen ↔ Rouen). Een ingekorte relatie
levert geen `cancel` op, dus liep het venster van 5400 s rond 22:10 af.

`closure_baseline.py` is precies voor dat geval gebouwd en zou het wél zien — maar
draait in de **wekelijkse** ETL, die maandag 00:00 start. Tussen 22:10 op vrijdag en
maandagnacht dekt dus geen van beide mechanismen de stremming. Het hele weekend
valt ertussenuit.

Geen ontwerpfout in een van beide modules, maar een ongedekt interval tussen twee
cadansen. Denkrichting: `closure_baseline` vaker draaien, of bij het verlopen van
het blokkadevenster de bewijslast omdraaien — een segment blijft geblokkeerd zolang
het geen passages krijgt terwijl de baseline er verkeer verwacht.

**Tweede blinde vlek, groter.** `closure_baseline.py` noemt hem zelf: een stremming
die bijna de hele feed-horizon beslaat duwt zijn eigen baseline naar nul
(`SAMPLE_DAYS = 35`). Levend voorbeeld in hetzelfde archief: Épinal –
Saint-Dié-des-Vosges ligt **6 juli t/m 6 november 2026** volledig dicht. De
aangewezen terugval is de storingsfeed — en juist die wordt niet gearchiveerd.

Kleiner, uit dezelfde casus: **er is geen alertarchief.** `alerts` en
`disruptions_sncf` gaan alleen naar de snapshot, niet naar `rt-archive/`, dus
achteraf is niet eens vast te stellen óf de vervoerder een stremming heeft gemeld.

## Twee omleidingen op komst: gratis validatie

Uit `docs/hsl-omleidingen.md`, met data die binnen deze planhorizon vallen. Beide
zijn een kosteloze toets op de stelling dat een omleiding onzichtbaar is in de
stops, en op het gat in `blockades.py` hierboven.

- **LGV Nord, 14 september – 25 oktober 2026**: treinen tussen Lille en Arras
  deels over de klassieke lijn; op **3 en 4 oktober** volledige onderbreking,
  alles inclusief Eurostar over klassiek spoor. Begint morgen.
- **NBS Nürnberg – Ingolstadt, 31 oktober – 11 december 2026**: volledig dicht,
  omleiding via de Altmühltalbahn en Treuchtlingen, +45 min.

De vraag die het archief kan beantwoorden: veranderen de **stops** van die ritten,
of alleen de rijtijd? Als alleen de rijtijd verandert, is dat de directe
bevestiging dat geen enkele statische geometrie klopt. Dat is met
`rt-archive/stops/<dag>.parquet` achteraf te meten, zonder de VM.

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
