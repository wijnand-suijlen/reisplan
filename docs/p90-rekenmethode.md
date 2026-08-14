# De p90 achter de kaartkleur: rekenmethode, weging en bias

Hoe de vertragingskaart per baanvak aan zijn p90 komt, waarom dat zo berekend
wordt, en waarom de kaart en de inspectiepagina elkaar kunnen "tegenspreken".
Code: `main.py` (aggregatie, poll-loop), `snapshot.py` (kleurklassen),
`opslag.py` (wat er überhaupt gelogd wordt). Datacontracten:
`snapshot-schema.md` en `inspectie-schema.md`.

## De berekening

Elke minuut, bij het bouwen van het snapshot:

1. Pak alle `seg_obs`-rijen van de laatste **30 minuten**. Eén rij is één
   gelogde *opgelopen* vertraging (delta, seconden) van één trein over één
   spoorsegment — geen absolute vertraging.
2. Zet elke rij om naar de getekende rand(en) waar dat segment op ligt
   (`segment_randen`); een rand bestaat uit meerdere segmenten.
3. Per rand: gooi alle delta's op één hoop, sorteer, en neem het element op
   positie `int(0.9 * n)` — de p90. Daarnaast wordt `n_treinen` geteld als
   het aantal *unieke* trips op de rand.
4. `snapshot.py` vertaalt de p90 naar de kleurklasse: groen < 60 s,
   geel ≤ 120 s, oranje ≤ 600 s, rood > 600 s.

## Passages, niet treinen

De p90 gaat over **datapunten (passages)**, terwijl `n_treinen` over **unieke
treinen** gaat — twee verschillende grootheden in één tooltip. Eén trein
levert meerdere datapunten:

- **Eén punt per segment.** Een rand van 6 segmenten die je helemaal afrijdt =
  6 datapunten. Een trein die maar één segment van die rand raakt = 1 punt.
- **Eén punt per bijstelling.** `opslag.bewaar` logt een nieuwe rij zodra de
  delta-*schatting* voor (trein, segment) verandert; elke feed-poll kan de
  voorspelling herzien. Eén fysieke passage kan dus meermaals meetellen.

Gewicht in de p90 is daarmee evenredig met (bereden segmenten van de rand) ×
(aantal bijstellingen), niet met "één trein, één stem".

**Voorbeeld.** Rand van 6 segmenten; in het venster reed er één ICE overheen
die 5 min opliep, plus vier sprinters die elk één segment raakten en niets
opliepen. Datapunten: 6 × ~300 s en 4 × 0 s. De p90 van die tien waarden is
300 s → rood, terwijl 4 van de 5 treinen op tijd waren. De inspectiepagina
met baanvakfilter toont diezelfde situatie als vijf treinen: één met +5 en
vier met 0.

## Waarom zo?

- **Goedkoop en simpel.** Eén tabel-scan met venster op de ts-index en wat
  dicts in de minuut-loop; geen per-trein-reductie of identiteitsresolutie
  nodig. Op de e2-micro telt dat.
- **Dun venster, toch signaal.** In 30 minuten passeren op veel randen maar
  een paar treinen. Alle observaties meenemen geeft meer datapunten en dus
  een stabielere schatting dan één waarde per trein.
- **p90 in plaats van max/gemiddelde.** Eén foute meting of één pechvogel
  kleurt de rand niet meteen; een gemiddelde zou structurele vertraging juist
  wegmiddelen tegen de nullen.
- **Delta in plaats van absoluut.** De kaart wil laten zien *waar* vertraging
  ontstaat. Een trein die constant 40 min achter rijdt loopt niets meer op en
  kleurt terecht niets; zijn absolute vertraging is op de inspectiepagina te
  zien.

## Bekende bias en beperkingen

- **Lange doorrijders domineren.** Zie het voorbeeld: één vertragende trein
  over een lange rand weegt zwaarder dan meerdere stiptere treinen die er
  maar een stukje van berijden.
- **Alleen wijzigingen worden gelogd.** Een trein die na zijn eerste
  waarneming stabiel blijft (op tijd óf constant te laat) produceert geen
  nieuwe punten; treinen waarvan de schatting beweegt zijn dus
  oververtegenwoordigd. Dit is dezelfde eigenschap waardoor stabiele treinen
  uit korte vensters op de inspectiepagina vallen.
- **Bijstellingen tellen dubbel.** Een voorspelling die 0 → 60 → 120 gaat
  levert drie punten voor dezelfde fysieke passage.
- **Kleine n maakt p90 ≈ max.** Bij minder dan ~10 punten wijst
  `int(0.9 * n)` (afgekapt op het laatste element) naar het maximum of daar
  vlakbij; op rustige randen kleurt één vertraagde trein de rand dus in zijn
  eentje.
- **Dekking verschilt per land.** Delta's komen alleen uit paren van
  *expliciete* StopTimeUpdates (zie `snapshot-schema.md`); landen met karige
  feeds leveren minder en grovere punten.

## Kaart vs. inspectiepagina — drie verschillende getallen

| | Kaartkleur (p90) | Inspectietabel | Kolom "Δ baanvak" |
|---|---|---|---|
| Bron | `seg_obs` | `stop_obs2` | `seg_obs` via `edges.json` |
| Grootheid | *opgelopen* delta per segmentpassage | *absolute* vertraging, jongste observatie | *opgelopen* delta, laatste passage |
| Eenheid van telling | datapunt (passage/bijstelling) | trein | trein (laatste passage wint) |
| Venster | vast 30 min | 30 min / 4 u, client-side op `last_ts` | 30 min / 4 u op de passage-ts (zelfde selectieregel als de kaart) |
| Aggregatie | p90 over de hoop | geen (rij per trein); percentiel = rang binnen venster | geen |

Daardoor kán een rand rood zijn terwijl de tabel vooral nullen toont (één
lange oploper tussen korte stipte treinen), of andersom groen terwijl de
tabel hoge absolute vertragingen laat zien (iedereen rijdt constant 20 min
achter maar loopt niets meer op).

## Mogelijke verbeterpunten

Niet gepland, wel bewust genoteerd:

1. **Eerst per trein reduceren, dan p90 over treinen** — bijv. per
   (trein, rand) de laatste of mediane delta (zoals `edges.json` al doet) en
   dáár de p90 over. Eén trein, één stem; wel minder punten in het dunne
   venster, dus meer flikkering op rustige randen.
2. **Bijstellingen ontdubbelen** — per (trein, segment) alleen de laatste
   waarde in het venster meenemen (`arg_max` op ts). Haalt het dubbeltellen
   van herziene voorspellingen eruit tegen geringe extra querykosten.
3. **Minimum aantal punten of treinen voor een kleur** — onder de drempel
   grijs ("te weinig data") in plaats van een p90-die-eigenlijk-max-is.
   `n_treinen` zit al in het snapshot, dus dit kan ook puur client-side.
4. **n_punten naast n_treinen tonen** in de tooltip, zodat het gewicht van
   het oordeel zichtbaar is.

Wijzigingen hier moeten meetbaar blijven passen binnen het VM-budget
(zie CLAUDE.md, "Productieomgeving: krap geheugen") — de minuut-loop is
dezelfde loop die de feeds pollt.
