# Testset: gedocumenteerde routes van nachttreinen

Samengesteld 13 september 2026. **Doel**: elke wijziging aan de routering in
`spike/s8_geometrie.py` toetsen aan routes die de vervoerder zelf publiceert, in
plaats van aan één geval dat toevallig goed uitvalt.

Waarom juist nachttreinen: ze hebben gaten van vier tot achttien uur tussen twee
stops, en over zo'n afstand zijn er meestal meerdere plausibele corridors. Ze
rijden bovendien niet noodzakelijk de snelste of de kortste route — een nachttrein
staat soms een uur stil om niet te vroeg aan te komen. Elke kostfunctie die op
lengte of tijd optimaliseert kan daar dus principieel naast zitten.

## Hoe je hem gebruikt

Per sprong staat hieronder welke plaatsen de route **moet** aandoen en welke
**niet**. Route de sprong, zet de doorlopen randen om in de dichtstbijzijnde
clusternamen, en toets. Een variant is pas geloofwaardig als hij op alle
gedocumenteerde sprongen slaagt — niet op één.

Bron per regel: `exploitant` = gepubliceerd door de vervoerder of een
vakpublicatie, `feed` = door de eigen stops van de rit vastgelegd, `afgeleid` =
redenering, nog niet bevestigd.

## De data waarop dit rust

77 sprongen in `merged.duckdb` met vertrek tussen 18:00 en 02:00 en een gat van
meer dan vier uur, gegroepeerd naar dienst. De query staat onderaan.

---

# Historische achtergrond: welke corridors liggen vast en welke schuiven

Nagezocht vanaf de jaren zestig en, waar de bron verder terugging, vanaf de
oprichting van de verbinding. De uitkomst verandert hoe je naar het routeerprobleem
moet kijken.

**De corridors zijn veel ouder en veel stabieler dan de treinen die erover rijden.**
De exploitanten wisselen om de paar jaar — CIWL, DB, City Night Line, ÖBB Nightjet,
European Sleeper — maar de spoorlijn waarover ze 's nachts rijden ligt er meestal
al meer dan een eeuw en is in die eeuw niet verlegd. Dat is precies de eigenschap
waar een router op mag leunen.

## Stabiel gebleven

| corridor | sinds | gebruikt door | geval |
|---|---|---|---|
| Paris – Mons – **Liège** – Aachen – Köln – Hannover – Berlin | **1896** (Nord-Express) | Nord-Express 1896–1990er, nu European Sleeper | 1 |
| Amsterdam – Utrecht – **Arnhem/Zevenaar** – Duisburg – Köln – Mainz – Mannheim – Karlsruhe – Freiburg – Basel | **1928** (Rheingold) | Rheingold 1928–1987, EC Rembrandt/Berner Oberland tot 2002, ICE tot 2024, nu Nightjet | 3 |
| Paris – Dijon – Lyon – Marseille – Toulon – Nice | **1886** (Calais-Méditerranée-Express) | Train Bleu 1922–2007, nu Intercités de Nuit | 12 |
| Paris – Vierzon – Châteauroux – Limoges – Brive – Cahors – Montauban – Toulouse (POLT) | **1893** voltooid, 1926 geëlektrificeerd | Capitole 1967–1991, nu Intercités de Nuit | 9, 11 |
| Valence – Crest – Die – Veynes – Gap – Briançon (Ligne des Alpes) | **1875** tot Gap | nu Intercités de Nuit | 10 |
| Hamburg – Hannover – Göttingen – Karlsruhe – Freiburg – Lörrach | decennia als autoreisezug | DB Autozug, nu BTE/Urlaubs-Express | 14 |

Vier van de zes gevallen waar de testset op steunt volgen dus een tracé dat al
vóór 1930 lag. De Rijnvalleiroute Köln–Mainz–Mannheim–Karlsruhe–Freiburg–Basel
komt in vijf van de veertien gevallen terug en is in geen enkele periode verlegd.

## Wél veranderd — en dat zijn de valstrikken

**Amsterdam – Basel: de grensovergang is drie keer verschoven.**
Van 1928 tot 2016 liep alles via Arnhem/Zevenaar–Emmerich. De Nightjet begon in
2021 met een omleiding via **Venlo** (oorspronkelijk wegens werkzaamheden) en hield
die aan. Vanaf mei 2026 rijdt hij weer via Arnhem. De corridor ten zuiden van Köln
bleef al die tijd dezelfde. Wie een routeerregel bouwt op "nachttreinen naar
Zwitserland gaan via Venlo" legt dus een vijfjarige uitzondering vast als wet.

**Paris – Briançon: er zijn twee routes en de omleiding is nú actief.**
Normaal Valence–Livron–Crest–Die–Veynes. Wegens meerjarige werkzaamheden tussen
Livron en Veynes-Dévoluy is de nachttrein sinds **september 2025** omgeleid over de
historische Ligne des Alpes via **Grenoble**. Beide zijn juist, afhankelijk van de
datum. Mijn eerste versie van deze testset zette Grenoble op "mag niet"; dat was
fout.

**De IJzeren Rijn: al 70 jaar geen doorgaande reizigerstrein.**
Weert–Hamont verloor het reizigersvervoer in **1953**, Neerpelt–Hamont in **1957**.
In mei 1991 ging Herkenbosch–Dalheim op verzoek van de Deutsche Bundesbahn dicht en
werden Budel–Weert en Roermond–grens buiten dienst gesteld. ProRail vernieuwde
Budel–Weert in 2007 voor zeer beperkt goederenvervoer; België reactiveerde lijn 19
tot Hamont in 2014 en elektrificeerde die in 2020.

Dit is het harde feit van de hele verzameling: de A* op afstand routeert de
European Sleeper over een verbinding waarover **sinds 1953 geen doorgaande
reizigerstrein meer heeft gereden**, terwijl de route die hij had moeten kiezen —
Köln–Aachen–Liège — sinds 1896 onafgebroken in gebruik is. Het onderscheid is niet
subtiel, en het is niet met afstand te maken.

**Hele netwerken zijn verdwenen, niet verlegd.** Amsterdam–Italië eindigde in 2003,
Amsterdam–Zwitserland in 2016, en bij de dienstregelingswissel van december 2016
verdween City Night Line in zijn geheel. De nachttreinen die sinds 2021 terugkomen
nemen de oude corridors weer op. Er is dus geen geleidelijke verschuiving waar een
model naartoe kan bewegen: er is een gat van vijf jaar en daarna hetzelfde tracé.

## Wat dit betekent voor de kostfunctie

De stabiliteit zit in de **lijn**, niet in de trein. De lijnen die deze treinen
gebruiken zijn hoofdlijnen: dubbelsporig, geëlektrificeerd, al een eeuw in
doorgaand gebruik. De lijn waarover de router de fout in gaat is enkelsporig, was
tot 2020 niet geëlektrificeerd en heeft sinds 1957 geen doorgaande dienst gehad.

Dat pleit ervoor de strafactor niet alleen op `service` en `usage` te zetten — die
variant faalde — maar op de combinatie **`tracks`, `electrified` en `usage`**, en
zwaarder dan factor 10. Nog niet gemeten; zie de tabel onderaan.

## Waar de historische gegevens vandaan komen

Er is geen downloadbaar bestand met historische loopwegen. Wat er wel is:

- [kursbucharchiv.de](http://www.kursbucharchiv.de/) — privéarchief met Duitse
  Kursbücher van 1880 tot heden. Niet vrij te downloaden; de beheerder maakt
  kopieën op aanvraag tegen kostprijs. Bruikbaar voor een gerichte vraag over één
  loopweg in één jaar, niet voor bulk.
- [deutsches-kursbuch.de](https://www.deutsches-kursbuch.de/) — scans 1914–1944,
  dus te oud voor onze vraag.
- [Liste der Nachtzugverbindungen in Deutschland](https://de.wikipedia.org/wiki/Liste_der_Nachtzugverbindungen_in_Deutschland)
  — de bruikbaarste losse bron: loopwegen mét tussenstations voor de meeste
  huidige verbindingen, plus opheffingsjaren.

---

# De gevallen

## 1. European Sleeper — Parijs/Brussel – Hamburg – Berlijn

Sprongen in de feed (`be`): `Hamburg-Harburg ↔ Bruxelles-Midi` (9,4 u),
`Hamburg-Harburg ↔ Aarschot` (9,8 u), `Hamburg-Harburg ↔ Hergenrath-Frontière`
(7,3 u), `Berlin-Gesundbrunnen ↔ Hamburg-Harburg` (4,5 u).

| | |
|---|---|
| **moet aandoen** | Mons, Liège, Aachen, Köln |
| **mag niet** | Venlo, Roermond, Weert, Hamont, Neerpelt (de IJzeren Rijn) |
| stabiel sinds | 1896 (Nord-Express, zelfde corridor) |
| bron | exploitant: *"via Aulnoye-Aymeries, Mons, Liège, and Hamburg"* |

**Dit is het ijkgeval.** De productieroutering (A* op afstand) gaat hier fout via
de IJzeren Rijn; A* op reistijd vindt Köln–Aachen–Liège en is dus juist.

Let op: de exploitant noemt **Luik als stop**, maar die staat niet in de
NMBS-feed. Stond hij erin, dan was de sprong gesplitst en was dit probleem voor
deze trein grotendeels weg. De feed is hier incompleet, niet alleen de router.

## 2. European Sleeper — Brussel/Amsterdam – Berlijn/Praag

Sprongen (`nl`, `de_rv`): `Deventer → Berlin Hbf` (6,4 u),
`Deventer → Berlin-Gesundbrunnen` (6,1 u).

| | |
|---|---|
| **moet aandoen** | Bad Bentheim, Osnabrück, Hannover |
| bron | feed (Bad Bentheim en Rheine komen als eigen stops voor) |

## 3. Nightjet Amsterdam – Basel – Zürich

Sprongen (`ch`): `Amsterdam Centraal → Offenburg` (8,6 u),
`Singen (Hohentwiel) → Amsterdam Centraal` (9,8 u).

| | |
|---|---|
| **moet aandoen** | Utrecht, Duisburg, Düsseldorf, Köln, Bonn, Koblenz, Mainz, Frankfurt, Mannheim, Karlsruhe, Offenburg, Freiburg, Basel |
| variant NL | Arnhem (1928–2016 en weer vanaf mei 2026) of Eindhoven–Venlo (2021–2026) |
| stabiel sinds | 1928 ten zuiden van Köln; het Nederlandse deel is drie keer gewisseld |
| bron | exploitant (NS International, Wikipedia-loopweg NJ 402/403) |

Let op de valstrik: **Venlo is hier een geldige variant**, terwijl het bij geval 1
fout is. Een regel die Venlo categorisch uitsluit faalt dus.

Nagezocht op 13 september: Venlo is hier geen eigenaardigheid van deze trein maar
**de vaste omleidingsroute van de corridor Arnhem–Emmerich**. Bij de driesporige
uitbouw Emmerich–Oberhausen worden de internationale treinen vanaf Köln omgeleid
via Mönchengladbach, Venlo en 's-Hertogenbosch, waarbij Düsseldorf, Duisburg,
Oberhausen en Arnhem als halte vervallen. Dezelfde omweg reed de TEE Rheingold al
van 1951 tot 1962. Zie `docs/hsl-omleidingen.md` en `docs/tee-loopwegen.md`.

## 4. Nightjet Amsterdam – Innsbruck/Wenen

| | |
|---|---|
| **moet aandoen** | Amersfoort of Arnhem, Deventer, Bad Bentheim |
| bron | exploitant/NS International — **let op**: één secundaire bron beweert dat de Wenen-tak via Frankfurt en Passau rijdt in plaats van via Bad Bentheim. Niet opgelost. |

## 5. Nightjet Zürich – Praag

Sprongen (`ch`): `Praha hl.n. → Zürich HB` (18,2 u), `Offenburg ↔ Praha` (10,7 u),
`Mannheim ↔ Praha` (8,7 u), `Singen → Leipzig` (8,4 u).

| | |
|---|---|
| **moet aandoen** | Basel, Freiburg, Offenburg, Karlsruhe, Mannheim, Frankfurt, **Erfurt**, Leipzig, Dresden, Bad Schandau, Děčín |
| **mag niet** | Nürnberg, München (de zuidelijke route) |
| bron | exploitant (loopweg EC/EN 458/459) |

De sprong van 18,2 uur is de langste in de hele dataset en daarmee het scherpste
testgeval: hij overspant half Duitsland met twee plausibele corridors.

## 6. Nightjet Brussel – Wenen

Sprongen (`be`): `Koblenz Hbf ↔ München Ost` (6,3 u), `München Ost → Bonn-Beuel`
(6,2 u).

| | |
|---|---|
| **moet aandoen** | Verviers, Aachen, Köln, Bonn, Koblenz, Rosenheim, Salzburg, Linz, St. Pölten |
| bron | exploitant voor de uiteinden |

Het middenstuk Koblenz–München laat de exploitant zelf open. Rijnvallei via Mainz,
Frankfurt en Würzburg is aannemelijk maar **niet bevestigd** — afgeleid.

## 7. Nightjet Basel – Berlijn/Leipzig

Sprongen (`ch`): `Basel Bad Bf ↔ Leipzig Hbf` (7,4 u),
`Basel Bad Bf → Berlin Ostbahnhof` (7,3 u), `Berlin Ostbahnhof ↔ Freiburg` (6,9 u).

| | |
|---|---|
| **moet aandoen** | Freiburg, Offenburg, Karlsruhe, Mannheim, Frankfurt, Erfurt, Leipzig |
| bron | afgeleid: deelt de corridor met geval 5 tot Leipzig — **niet los bevestigd** |

Niet verwarren met ICE 100/101 Basel–Berlin, die overdag via Köln en het Ruhrgebied
rijdt. Dat is een heel andere corridor en géén geldig ijkpunt voor de nachttrein.

## 8. Nightjet Zürich – Hamburg

Sprongen (`ch`): `Zürich HB → Mannheim Hbf` (6,9 u), `Zürich HB → Heidelberg`
(6,1 u), `Heidelberg → Hamburg-Altona` (4,1 u), `Hamburg-Altona ↔ Offenburg` (8,8 u).

| | |
|---|---|
| **moet aandoen** | Basel, Freiburg, Offenburg, Karlsruhe, Heidelberg, Frankfurt, Göttingen, Hannover, Bremen |
| bron | exploitant (loopweg NJ 470/471) |

De loopweg gaat via **Bremen**, niet rechtstreeks Hannover–Hamburg. Een router die
de kortste weg Hannover–Hamburg neemt zit er hier naast zonder dat de feed dat
verraadt.

## 9. Intercités de Nuit — Parijs – Toulouse/Latour-de-Carol

Sprongen (`fr`): `Les Aubrais ↔ Cahors` (5,9 u), `Les Aubrais ↔ Toulouse Matabiau`
(9,9 u), `Les Aubrais ↔ Montauban` (9,8 u), `Les Aubrais ↔ Auterive` (8,9 u),
`Les Aubrais ↔ Souillac` (7,7 u).

| | |
|---|---|
| **moet aandoen** | Vierzon, Châteauroux, Limoges Bénédictins, Brive-la-Gaillarde, Souillac, Gourdon |
| **mag niet** | Bordeaux, Angoulême, Tours, Agen |
| stabiel sinds | 1893 (POLT voltooid), geëlektrificeerd 1926 |
| bron | exploitant + feed; SNCF bevestigt expliciet dat er tussen Montauban en Les Aubrais geen commerciële stop is |

**Dit is het tweede ijkgeval.** A* op afstand doet het hier goed (479 km over de
POLT); A* op reistijd gaat 222 km om via Bordeaux en is dus fout. Samen met geval
1 sluit dit paar elke variant uit die maar één van beide goed heeft.

## 10. Intercités de Nuit — Parijs – Briançon

Sprongen (`fr`, `ch`): `Paris Austerlitz ↔ Veynes Dévoluy` (11,9 u),
`↔ Crest` (10,0 u), `↔ Gap` (9,3 u), `↔ Chorges` (9,4 u).

| | |
|---|---|
| **moet aandoen** | Valence, Veynes, Gap |
| variant | normaal Livron–**Crest**–Die–Veynes; sinds september 2025 omgeleid via **Grenoble**–Veynes wegens meerjarig werk tussen Livron en Veynes |
| stabiel sinds | 1875 (aankomst van de trein in Gap) |
| bron | exploitant (Rail Passion over de omleiding) + feed (Crest is een eigen stop) |

Beide varianten zijn juist, afhankelijk van de datum. Zolang Crest in de feed als
eigen stop voorkomt, is de Die-route actief en pint de feed hem al vast.

## 11. Intercités de Nuit — Parijs – Rodez/Albi

Sprongen: `Paris Austerlitz ↔ Saint-Denis-Près-Martel` (11,5 u),
`Figeac → Paris Austerlitz` (9,0 u).

| | |
|---|---|
| **moet aandoen** | Vierzon, Châteauroux, Limoges, Brive-la-Gaillarde |
| bron | feed (dezelfde POLT als geval 9 tot Brive) |

## 12. Intercités de Nuit — Parijs – Nice

Sprong: `Paris Austerlitz ↔ Marseille Blancarde` (10,9 u).

| | |
|---|---|
| **moet aandoen** | Dijon, Lyon, Valence, Avignon, Marseille, Toulon |
| stabiel sinds | 1886 (Calais-Méditerranée-Express), Train Bleu 1922–2007 |
| bron | exploitant (historische loopweg) — de exacte uitgang uit Parijs vanaf Austerlitz is **afgeleid** |

## 13. Intercités de Nuit — Parijs – Cerbère/Portbou

Sprong: `Paris Austerlitz ↔ Nîmes Centre` (9,8 u).

| | |
|---|---|
| **moet aandoen** | Rhônedal tot Nîmes, daarna Montpellier, Sète, Béziers, Narbonne, Perpignan |
| **mag niet** | Toulouse |
| bron | exploitant (stoppenlijst Paris–Cerbère) |

In de eerste versie van deze testset zat Nîmes bij geval 12; dat is fout, het is
een aparte trein die bij Tarascon van de Nice-corridor afbuigt.

## 14. Intercités de Nuit — Parijs – Hendaye/Tarbes

Sprong: `Les Aubrais ↔ Biganos Facture` (7,8 u).

| | |
|---|---|
| **moet aandoen** | Bordeaux Saint-Jean |
| bron | feed (Biganos ligt op de lijn Bordeaux–Arcachon/Hendaye) |

## 15. Autoreisezug Hamburg – Lörrach

Sprong (`de_rv`): `Lörrach Gbf ARZ ↔ Hamburg-Altona` (11,0 u).

| | |
|---|---|
| **moet aandoen** | Hannover, Göttingen, Karlsruhe, Baden-Baden, Offenburg, Freiburg |
| bron | exploitant (BTE/Urlaubs-Express stoppenlijst) |

Autoreisezug, dus nauwelijks reizigersstops onderweg. Structureel dezelfde valkuil
als een nachttrein, en hij bevestigt onafhankelijk de Rijnvalleicorridor uit de
gevallen 3, 5, 7 en 8.

---

## Wat nog niet gedocumenteerd is

De gevallen 4 (loopweg naar Wenen), 6 (Koblenz–München), 7 (los bewijs) en 12 (de
uitgang uit Parijs) rusten deels op redenering. Wie die opzoekt maakt de testset
sterker.

## De query

```sql
WITH s AS (SELECT st.feed, st.trip_id, sc.cluster_id, st.dep_s,
      row_number() OVER (PARTITION BY st.feed, st.trip_id ORDER BY st.stop_sequence::INT) rn
   FROM stop_times st JOIN stop_cluster sc USING (stop_id) WHERE st.dep_s IS NOT NULL),
h AS (SELECT a.feed, a.trip_id, a.cluster_id ca, b.cluster_id cb, b.dep_s-a.dep_s gat,
             (a.dep_s/3600)%24 uur_vertrek
      FROM s a JOIN s b ON a.feed=b.feed AND a.trip_id=b.trip_id AND b.rn=a.rn+1
      WHERE a.cluster_id<>b.cluster_id AND b.dep_s>a.dep_s)
SELECT x.naam, y.naam, max(h.gat)/3600.0, count(DISTINCT h.trip_id)
FROM h JOIN clusters x ON x.cluster_id=h.ca JOIN clusters y ON y.cluster_id=h.cb
WHERE h.gat > 4*3600 AND (h.uur_vertrek >= 18 OR h.uur_vertrek <= 2)
GROUP BY 1,2 ORDER BY 3 DESC;
```

## Stand van de varianten op deze testset

Alleen de gevallen 1 en 9 zijn tot nu toe gemeten:

| variant | 1. Hamburg–Brussel | 9. Les Aubrais–Cahors |
|---|---|---|
| A* op afstand (productie) | fout (IJzeren Rijn) | **goed** (POLT, 479 km) |
| A* op reistijd, onbegrensd | **goed** (Köln–Aachen–Liège) | fout (via Bordeaux, 701 km) |
| A* op reistijd, geklemd 40–120 | fout (via Antwerpen) | **goed** |
| A* met strafactor 10 op `service`/`usage` | fout (IJzeren Rijn blijft) | **goed** |
| A* met straf op `tracks`+`electrified`+`usage` | nog niet gemeten | nog niet gemeten |

Geen enkele gemeten variant haalt beide. De dertien andere gevallen zijn nog niet
gemeten. De laatste regel komt voort uit de historische analyse hierboven en is de
eerstvolgende die het proberen waard is.

## Bronnen

- [IJzeren Rijn — Wikipedia](https://nl.wikipedia.org/wiki/IJzeren_Rijn) en
  [Spoorlijn Weert–Roermond — Somda RailWiki](https://railwiki.nl/index.php/Spoorlijn_Weert_-_Roermond)
- [Nord Express](https://www.trains-worldexpresses.com/500/505.htm) en
  [European Sleeper Paris–Brussel–Berlijn](https://tripbytrip.org/2025/11/12/european-sleeper-to-operate-paris-brussels-berlin-night-train-route-from-march-2026/)
- [Rheingold (train) — Wikipedia](https://en.wikipedia.org/wiki/Rheingold_(train))
- [Internationaal treinverkeer (Nederland) — Wikipedia](https://nl.wikipedia.org/wiki/Internationaal_treinverkeer_(Nederland))
- [Liste der Nachtzugverbindungen in Deutschland — Wikipedia](https://de.wikipedia.org/wiki/Liste_der_Nachtzugverbindungen_in_Deutschland)
- [Night train Amsterdam–Zürich — NS International](https://www.nsinternational.com/en/trains/nighttrain/night-train-zurich)
- [Train bleu — Wikipédia](https://fr.wikipedia.org/wiki/Train_bleu_(train))
- [Le patrimoine ferroviaire de la ligne POLT — SNCF Réseau](https://www.sncf-reseau.fr/fr/reportages/patrimoine-ferroviaire-polt)
- [Les Intercités de nuit Paris–Briançon détournés par la ligne des Alpes — Rail Passion](https://www.railpassion.fr/reseaux-francais/les-intercites-de-nuit-paris-briancon-detournes-par-la-ligne-des-alpes/)
- [Autozug Hamburg–Lörrach](https://www.bahndampf.de/autoreisezug/autozug-hamburg-loerrach)
- [Kursbucharchiv](http://www.kursbucharchiv.de/)
