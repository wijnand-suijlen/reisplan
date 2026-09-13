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

Zaterdag 12 september tegen zaterdag 5 september. De twee dagen zijn vergelijkbaar
(78.951 tegen 79.734 Franse waarnemingen), dus dit is geen meetartefact:

| station | za 5 sep | za 12 sep |
|---|---|---|
| **Tourville** | 8 | **0** |
| Elbeuf-Saint-Aubin | 28 | 12 |
| Brionne / Serquigny / Bernay / Lisieux | 12 / 13 / 31 / 45 | ongewijzigd |
| Rouen Rive Droite | 125 | **64** |

De verklaring staat letterlijk in de `trip_id`'s. Op 5 september reden zes treinen
per richting **Caen ↔ Rouen** (`87444000 ↔ 87411017`). Op 12 september rijden
diezelfde zes per richting **Caen ↔ Elbeuf-Saint-Aubin** (`87444000 ↔ 87411173`).

De lijn is dus ingekort tot precies aan de ongevalslocatie. De Caen-kant draait
ongestoord door; het stuk Elbeuf – Tourville – Rouen is eruit gesneden. Rouen Rive
Droite is daarmee de grootste relatieve daling van alle grote Franse stations dat
weekend (−49 %, tegen −12 % voor Lille Flandres en −6 % voor Versailles Chantiers).

## Wat dit over de pijplijn zegt

### `blockades.py` ziet de stremming twee uur, en daarna niet meer

De blokkadedetectie eist twee verschillende geannuleerde ritten op één segment
binnen `WINDOW_S` (5400 s), en één gerealiseerde passage wist de historie.

Op het segment `uic:8741117|uic:8741118` — Elbeuf–Tourville, exact de
ongevalslocatie — kwamen **vier** geannuleerde ritten binnen (850626, 850628,
850629, 850631) tussen 20:16:33 en 20:40:44. De drempel werd dus ruim gehaald en
het segment is die avond correct als geblokkeerd gemarkeerd. Zo hoort het te
werken.

**Maar op 12 september staat er geen enkele annulering meer op dat segment.** De
treinen werden niet geannuleerd, ze werden opnieuw gepland als Caen ↔ Elbeuf. Een
ingekorte relatie levert geen `cancel` op: het segment komt simpelweg niet meer in
de dienstregeling voor.

Gevolg: het venster van 5400 s liep rond **22:10 op 11 september** af, en vanaf dat
moment zag de kaart een normale lijn — terwijl het spoor de hele zaterdag dicht
lag. Er is geen valse "passage" die de blokkade wist; de blokkade verdampt gewoon
door tijdsverloop.

Dit is een echt gat, en het is het spiegelbeeld van waar de detectie voor is
ontworpen. Uitval betekent *"de trein rijdt vandaag niet"*; een ingekorte relatie
betekent *"deze verbinding bestaat deze week niet"*. Het tweede is het sterkere
signaal en wordt nu niet opgepikt.

Mogelijke richting, nog niet uitgewerkt: een relatie die van de ene dienstregeling
op de andere zijn eindpunt verlegt naar een station **op** de eigen route, terwijl
het weggevallen deel geen enkele passage meer krijgt, is een stremming. Dat vergt
een vergelijking tussen dienstregelingsversies, niet een venster van anderhalf uur.
Zie ook `docs/hsl-omleidingen.md`: daar zorgt hetzelfde mechanisme ervoor dat een
omleiding onzichtbaar blijft in de stops.

### Wat wél goed werkte

- Het archief bevatte alles wat nodig was, drie dagen na dato, zonder de VM te
  raken.
- De `uic:`-clusters overleefden de id-wijziging en bleven koppelbaar.
- De vertragingsopbouw en de doorwerking tot Parijs en Amiens zijn volledig
  gereconstrueerd.

## Wat ik niet hard kan maken

- Van de circa 40 Paris – Rouen – Le Havre-ritten die op 12 september ontbreken
  weet ik niet of dat allemaal doorwerking is of deels een andere oorzaak.
  Épinal en Saint-Dié-des-Vosges daalden dat weekend met ~36 % zonder enig verband
  met Normandië, dus er is achtergrondruis.
- Het archief van de lopende dag bestaat nog niet, dus de stand van vandaag is
  hiermee niet te zien.
- Er is geen alert- of storingsarchief: `alerts` en `disruptions_sncf` gaan alleen
  naar de snapshot, niet naar `rt-archive/`. De tekstuele verklaring van SNCF is
  dus achteraf niet meer op te halen. Dat is een gemis dat deze casus blootlegt.

## Bron van het incident zelf

- [Déraillement d'un train entre Rouen et Caen — France 3 Normandie](https://france3-regions.franceinfo.fr/normandie/seine-maritime/rouen/deraillement-d-un-train-entre-rouen-et-caen-le-plan-orsec-nombreuses-victimes-declenche-evitez-le-secteur-3415802.html)
