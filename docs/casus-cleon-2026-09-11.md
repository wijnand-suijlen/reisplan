# Casus: ontsporing bij Cléon, 11 september 2026

Op vrijdagavond 11 september 2026 ontspoorde een TER van Rouen naar Caen bij
**Cléon**, tussen Tourville-la-Rivière en Elbeuf-Saint-Aubin. Circa 180 reizigers,
44 gewonden, ORSEC/NOVI afgekondigd; de prefect van Seine-Maritime opende het
crisiscentrum om 20:00.

Dit is de eerste keer dat de eigen punctualiteitshistorie tegen een bekend,
extern gedocumenteerd incident is gelegd. Deze notitie legt vast wat erin te zien
was, wat niet, en wat dat over de pijplijn zegt.

Alle tijden hieronder zijn Europe/Paris.

## Hoe je dit reproduceert

Het dagarchief op R2 is publiek leesbaar, dus er hoeft niets op de VM te draaien
(dat zou de aggregator knijpen — zie `docs/geheugen-op-1gb.md`):

```sh
B=https://pub-2369cd93470e40528dc3aab9ab7fd5e7.r2.dev
curl -s -o stops-2026-09-11.parquet "$B/rt-archive/stops/2026-09-11.parquet"
curl -s -o cancels-2026-09-11.parquet "$B/rt-archive/cancels/2026-09-11.parquet"
```

`stops` bevat `ts, country, trip_id, service_date, cluster, delay_s`; `cancels`
bevat `ts, country, trip_id, service_date, segment`. Het archief wordt per
**afgesloten** dag geëxporteerd, dus de lopende dag zit er nooit in.

Twee dingen maakten de analyse mogelijk:

- **Franse clusters hebben `uic:`-ids**, en die zijn stabiel gebleven bij de
  cluster-id-wijziging van 12 september. Waarnemingen van vóór die wijziging zijn
  dus gewoon te koppelen aan het huidige `merged.duckdb`. Voor `nm:`-clusters geldt
  dat niet: die ids zijn hernummerd en oude archieven zijn daarop niet meer te
  joinen.
- **Franse `trip_id`'s bevatten de relatie**: `...::<uic-van>:<uic-naar>:...`, plus
  het treinnummer in het voorvoegsel `OCE<letters><nummer>`. Daarmee is de richting
  van een rit af te lezen zonder join.

## De trein

**TER 852086, Rouen Rive Droite → Caen.** Loopweg: Rouen RD – Elbeuf-Saint-Aubin –
Bourgtheroulde-Thuit-Hébert – Brionne – Serquigny – Bernay – Lisieux –
Mézidon-Canon – Moult-Argences – Frénouville-Cagny – Caen.

| tijd | wat de feed zei |
|---|---|
| 18:06:55 | negen haltes, overal 0 s vertraging |
| 19:12:46 | Rouen RD +300 s |
| 19:16:59 | alle acht resterende haltes +300 s |
| **19:57:58** | alle acht haltes ineens **+7200 s** |
| **20:16:33** | **geannuleerd**, acht segmenten: alles vanaf Bourgtheroulde tot Caen |
| daarna | geen enkele waarneming meer |

Het was de enige Rouen→Caen-rit in dat blok en de enige van de drie avondtreinen
die werd geannuleerd. De +300 s om 19:16 past op een trein die rond 19:25–19:30 bij
Cléon was.

**Voorbehoud.** Het archief legt vertraging en uitval vast, geen incidenten. Er
staat nergens "ontsporing". De identificatie is een gevolgtrekking uit tijd,
richting en uitval — sluitend, maar een gevolgtrekking. De snapshotcadans laat
bovendien een gat van **41 minuten** tussen 19:16:59 en 19:57:58, dus scherper dan
dat venster is het moment niet te bepalen. Dat is dezelfde cadansachterstand die in
`docs/geheugen-op-1gb.md` staat (snapshots op 46 % van het bedoelde ritme).

## Het vak loopt leeg, in beide richtingen

Om **19:57:58** krijgt elke trein in het vak tegelijk +7200 s:

| trein | relatie |
|---|---|
| 852034, 852038 | Caen → Rouen |
| 852086 | Rouen → Caen |
| 850624, 850626 | Yvetot → Elbeuf |
| 850628, 850629 | Elbeuf → Yvetot |

De laatste trein die **Tourville** passeerde is 850624 om 19:57:58. Bij
**Elbeuf-Saint-Aubin** houdt het op om **20:04:18**. Daarna ligt het vak de hele
nacht stil.

Om 20:37–20:40 volgen de annuleringen van 850628, 850630 en 850631.

## Doorwerking op de hoofdlijn

Zestien treinen liepen meer dan een half uur op, in beide richtingen, tot ver
buiten het getroffen vak:

| trein | relatie | vertraging |
|---|---|---|
| 13160 | Rouen → Paris Saint-Lazare | +200 min |
| 848961 | Amiens → Rouen | +200 min |
| 3129 | Paris Saint-Lazare → Le Havre | +190 min |
| 3131, 13145, 13149, 13151 | Paris Saint-Lazare → Rouen/Le Havre | +180 min |
| 848963, 3133 | Amiens → Rouen, Paris → Le Havre | +140 min |

De laatste meldingen komen om 23:53 binnen, de allerlaatste om 01:04.

## De dag erna

Niet tegen één referentiedag, maar tegen de hele reeks — twee dagen vergelijken
is te ruis­gevoelig, zoals de Vogezen-controle onderaan laat zien. Ritten per dag:

| dag | Rouen RD | Tourville | Elbeuf | Caen |
|---|---|---|---|---|
| za 29 aug | 127 | 8 | 28 | 76 |
| za 5 sep | 125 | 8 | 28 | 76 |
| do 10 sep | 183 | 10 | 52 | 132 |
| vr 11 sep | 181 | 10 | 51 | 131 |
| **za 12 sep** | **64** | **0** | **12** | **74** |

Een normale zaterdag geeft Rouen ~126, Tourville 8 en Elbeuf 28. Op 12 september
is dat 64, **0** en 12, terwijl Caen op 74 blijft staan — precies zoals verwacht
als de Caen-kant doordraait en het stuk richting Rouen eruit is.

De verklaring staat letterlijk in de `trip_id`'s. Op 5 september reden zes treinen
per richting **Caen ↔ Rouen** (`87444000 ↔ 87411017`). Op 12 september rijden
diezelfde zes per richting **Caen ↔ Elbeuf-Saint-Aubin** (`87444000 ↔ 87411173`).

De lijn is dus ingekort tot precies aan de ongevalslocatie. De Caen-kant draait
ongestoord door; het stuk Elbeuf – Tourville – Rouen is eruit gesneden. Rouen Rive
Droite is daarmee de grootste relatieve daling van alle grote Franse stations dat
weekend (−49 %, tegen −12 % voor Lille Flandres en −6 % voor Versailles Chantiers).

## Wat dit over de pijplijn zegt

### Het gat zit tussen de snelle en de langzame detectie

Er zijn twee mechanismen, en Cléon valt tussen beide door.

**De snelle weg, `blockades.py`**, eist twee verschillende geannuleerde ritten op
één segment binnen `WINDOW_S` (5400 s). Op `uic:8741117|uic:8741118` —
Elbeuf–Tourville, exact de ongevalslocatie — kwamen **vier** geannuleerde ritten
binnen (850626, 850628, 850629, 850631) tussen 20:16:33 en 20:40:44. De drempel
werd ruim gehaald en het segment is die avond correct als geblokkeerd gemarkeerd.
Dat werkte dus zoals bedoeld.

Maar op 12 september staat er geen enkele annulering meer op dat segment. De
treinen werden niet geannuleerd maar **opnieuw gepland als kortere relatie**
(Caen ↔ Elbeuf in plaats van Caen ↔ Rouen). Een ingekorte relatie levert geen
`cancel` op. Het venster liep dus rond **22:10 op 11 september** af en vanaf dat
moment zag de kaart een normale lijn. Geen valse passage — de blokkade verdampt
door tijdsverloop.

**De langzame weg, `closure_baseline.py`**, is precies voor dit geval gebouwd: hij
leidt stremmingen af uit *afwezigheid* in de statische dienstregeling, met een
baseline van `SAMPLE_DAYS = 35` dagen per dagtype en een `LOOKAHEAD_DAYS = 14`.
Een ingekorte relatie zou hij dus wel zien. Alleen draait hij in de **wekelijkse**
ETL, en de aggregator laadt het resultaat bij het starten.

Daar zit het gat. De verversing start maandag 00:00 (`statisch-vernieuwen.timer`).
Een ongeluk op vrijdagavond is dus zichtbaar zolang de annuleringen binnenkomen —
hier tot 22:10 — en daarna pas weer vanaf maandagnacht. **Het hele weekend valt
ertussenuit**, terwijl het spoor dicht lag.

Dit is geen ontwerpfout in een van beide modules; het is een ongedekt interval
tussen twee cadansen. Denkrichting, nog niet uitgewerkt: `closure_baseline` (of een
lichte variant ervan) vaker draaien dan wekelijks, of de blokkade laten
voortduren zolang een segment geen passages krijgt terwijl de baseline er wél
verkeer verwacht — dat laatste vergt geen nieuwe data, alleen het omdraaien van de
bewijslast bij het verlopen van het venster.

### Een tweede, grotere blinde vlek: stremmingen langer dan de baseline

`closure_baseline.py` zegt het zelf in zijn docstring: *"closures spanning (nearly)
the whole feed horizon push the baseline itself to zero and are invisible here — the
disruption feeds (NS/SNCF/NMBS) are the signal for those."*

Daar is in dit archief een levend voorbeeld van. De lijn
**Épinal – Saint-Dié-des-Vosges** ligt van **6 juli tot 6 november 2026** volledig
dicht voor een renovatie van 36 miljoen euro, gefinancierd door de Région Grand Est,
met bussen in de plaats. Vier maanden is ruim meer dan de 35 dagen baseline, dus de
majority vote leert dat géén verkeer daar normaal is en de stremming verdwijnt uit
beeld.

De aangewezen terugval is dan de storingsfeed — en juist die wordt niet gearchiveerd
(zie hieronder). We kunnen dus achteraf niet eens vaststellen óf SNCF het heeft
gemeld.

### Wat wél goed werkte

- Het archief bevatte alles wat nodig was, drie dagen na dato, zonder de VM te
  raken.
- De `uic:`-clusters overleefden de id-wijziging en bleven koppelbaar.
- De vertragingsopbouw en de doorwerking tot Parijs en Amiens zijn volledig
  gereconstrueerd.

## Wat ik niet hard kan maken

- Van de circa 40 Paris – Rouen – Le Havre-ritten die op 12 september ontbreken
  weet ik niet of dat allemaal doorwerking is of deels een andere oorzaak.
- **Gecorrigeerd.** In een eerdere versie stond hier dat Épinal en Saint-Dié
  dat weekend ~36 % daalden, als voorbeeld van achtergrondruis. Dat was fout: over
  de hele reeks is Épinal op zaterdag 44 (29 aug), 68 (5 sep) en 44 (12 sep). Niet
  12 september was afwijkend maar 5 september. De fout kwam voort uit het
  vergelijken van twee losse dagen in plaats van een reeks — dezelfde methode die
  ik hierboven voor Normandië heb vervangen. Het lage niveau zelf wordt verklaard
  door de stremming van 6 juli tot 6 november.
- Het archief van de lopende dag bestaat nog niet, dus de stand van vandaag is
  hiermee niet te zien.
- **Alerts worden nergens bewaard.** Niet in `rt-archive/` (archive.py exporteert
  precies drie tabellen: `seg`, `stops`, `cancels`) en ook niet in
  `observaties.sqlite` (`opslag.py` kent alleen `seg_obs`, `stop_obs` en
  `cancel_obs`). In `main.py` leven ze als `self.incidenten` en
  `self.alert_groups` — geheugenattributen die alleen de snapshot voeden en bij
  elke cyclus worden overschreven. De tekstuele verklaring van de vervoerder is dus
  niet drie dagen houdbaar maar één pollcyclus. Dat is een gemis dat deze casus
  blootlegt, en het weegt zwaarder door de blinde vlek hierboven: juist bij lange
  stremmingen is de storingsfeed de aangewezen bron.

## Bronnen

- [Déraillement d'un train entre Rouen et Caen — France 3 Normandie](https://france3-regions.franceinfo.fr/normandie/seine-maritime/rouen/deraillement-d-un-train-entre-rouen-et-caen-le-plan-orsec-nombreuses-victimes-declenche-evitez-le-secteur-3415802.html)
- [Travaux ligne Épinal – Saint-Dié – Strasbourg, été 2026 — Région Grand Est (PDF)](https://www.grandest.fr/wp-content/uploads/2026/06/06-18-26-cpresse-travaux-ligne-epinal-saint-die-strasbourg-ete-2026.pdf)
  — 36 miljoen euro, werken 6 juli t/m 6 november 2026, spoorverkeer Épinal –
  Saint-Dié onderbroken; deeltraject Saint-Dié – Colmar 6 juli t/m 7 augustus.
