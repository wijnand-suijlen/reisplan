# Lijnvoering: hoe een baanvak zijn spoorgeometrie krijgt

> **Status: niet uitvoeren zoals het hier staat.** Een review op 13 september
> vond een groter defect (de HSL-kleuringsfout hieronder) en vijf bezwaren tegen
> de implementatievolgorde. Zie "Wat er eerst moet gebeuren".

Onderzocht 12–13 september 2026, na een vraag over het label op een baanvak tussen
Weert en Roermond. Niets hiervan is geïmplementeerd.

## Het probleem

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

## Waar het wél in staat: `shapes.txt`

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

## De omleidingen maken een statische corridor onmogelijk

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

## De voorgestelde volgorde

Per stationspaar, in deze volgorde het pad bepalen:

1. **Heeft de rit een `shape_id`?** Gebruik de shape. Exact, van de vervoerder.
2. **Rijdt dezelfde trein in een andere feed die wél shapes heeft?** `s3` berekent
   al 224.316 duplicaat-tripparen; DELFI wordt daar een grote leverancier in.
3. **Bestaat er een verfijningsketen?** Die is afgeleid uit andere treinen die op
   de tussenliggende stations stoppen, en had voor Les Aubrais–Cahors de POLT al
   goed. Alleen niet toepassen waar het pad over een hogesnelheidslijn loopt.
4. **Anders A***, met de bekende beperkingen.

## Bezwaren uit de review van 13 september — dit plan is zo niet uitvoerbaar

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

## Wat er eerst moet gebeuren

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

## Werk dat daarna nodig is

- `s3_merge_dedup.py`: de shapes-tabel meenemen in de merge.
- `s0`/`s2`/`s3`: DELFI in de merge opnemen of `de_rv` vervangen — eerst beslissen.
- `s8_geometrie.py`: shapes map-matchen op de graaf; A* alleen waar geen shape is.
- Meten hoeveel van de Duitse paren DELFI werkelijk dekt, zodra dat kan.

## Nog een artefact met hetzelfde euvel

`cluster_land` komt uit `spike/s4_coverage_intl.py`, die niet in `vernieuw.sh`
staat. Na de cluster-id-wijziging van 12 september wijzen nog **3.649 van de
13.511 rijen** naar een bestaand cluster — precies de `uic:`-clusters. Lokaal
geeft de tabel daardoor stilzwijgend verkeerde antwoorden. Op de VM bestaat hij
niet en `statisch.py` doet een `LEFT JOIN`, dus productie loopt geen gevaar. Zelfde
klasse als `randen.json.gz`: een artefact gesleuteld op cluster-id's dat niet
meeververst. Ofwel s4 in de pijplijn, ofwel de tabel weg.
