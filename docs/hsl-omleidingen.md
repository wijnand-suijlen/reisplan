# Hogesnelheidslijnen en hun omleidingsroutes

Samengesteld 13 september 2026. Nagezocht: elke hogesnelheidscorridor in NL, BE,
DE, FR en CH, de klassieke lijn die ernaast ligt, en hoe stremmingen de afgelopen
veertig jaar zijn afgehandeld.

**Uitkomst vooraf, want die verandert het ontwerp.** Een sprong tussen twee
stations heeft geen vaste geometrie. Dezelfde trein, met exact dezelfde stops in de
feed, rijdt de ene week over de hogesnelheidslijn en de andere week over de
klassieke lijn ernaast. Dat is geen uitzondering maar een geplande, jaarlijks
terugkerende toestand, en op sommige corridors duurt hij maanden. Elke poging om
per baanvakpaar één juiste corridor vast te leggen is dus per constructie een
deel van het jaar fout.

---

## Het ijkgeval: Schiphol – Rotterdam

De HSL-Zuid (2009) loopt parallel aan de **Oude Lijn** (1847):
Amsterdam – Leiden – Den Haag HS – Delft – Schiedam – Rotterdam.

Bij een stremming rijden de treinen over de Oude Lijn, en — dit is het punt —
**ze stoppen daarbij niet in Leiden en Den Haag HS**, ze passeren die met
VMax 140. ProRail onderzoekt expliciet of ook het internationale verkeer tijdens
het onderhoud over delen van de Oude Lijn kan.

De feed ziet in beide gevallen precies hetzelfde: één sprong Schiphol → Rotterdam,
zonder tussenstops. Er is geen veld, geen tag en geen rijtijd waarmee je kunt zien
welke van de twee lijnen gereden is.

Dit is exact het defect dat in `docs/openstaand-uitrol.md` staat: `bouw_verfijning`
legt Schiphol–Rotterdam op de Oude Lijn (39 van 39 randen gekleurd) in plaats van
op de HSL (2 van 5). Dat is vandaag fout. Het is in 2028 **112 dagen lang goed.**

De herstelwerkzaamheden aan de kunstwerken:

| wanneer | wat |
|---|---|
| 2026 | weekendstremmingen, o.a. 28–30 maart en 5–7 september |
| **2028** | Hoofddorp – Rotterdam **112 dagen dicht**, vanaf 4 september; vier van de tien viaducten |
| **2029** | nog eens **50 dagen** voor het viaduct Zuidweg bij Rijpwetering |
| tot 2031 | verlengde weekendstremmingen voor de overige viaducten |

Opgeteld bijna een half jaar volledige stremming. De oorzaak is een
constructiefout: de lassen in tien viaducten zijn onvoldoende sterk, waardoor
scheurtjes ontstaan. Het gaat dus niet om regulier onderhoud maar om herstel van
een bouwfout, en de einddatum is 2031.

> Ter correctie van een aanname: de grote stremming loopt **niet nu**, maar vanaf
> 2028. In 2026 gaat het om weekenden. De structurele conclusie verandert daar
> niet door.

---

## Alle corridors, met hun uitwijkroute

| hogesnelheidslijn | open | klassieke lijn ernaast |
|---|---|---|
| HSL-Zuid (NL) | 2009 | Oude Lijn: Leiden – Den Haag HS – Delft – Schiedam (1847) |
| HSL 4 Antwerpen – grens (BE) | 2009 | Antwerpen – Roosendaal (lijn 12) |
| HSL 1 Brussel – Franse grens (BE) | 1997 | klassiek net via Doornik/Halle |
| HSL 2 Leuven – Ans (BE) | 2002 | lijn 36 Leuven – Landen – Liège |
| HSL 3 Liège – Duitse grens (BE) | 2009 | lijn 37 Liège – Verviers – Welkenraedt – Aachen |
| NBS Köln – Rhein/Main (DE) | 2002 | linke Rheinstrecke (Bonn – Remagen – Andernach – Koblenz) én rechte Rheinstrecke (Troisdorf – Unkel – Wiesbaden) |
| NBS Hannover – Würzburg (DE) | 1991 | Göttingen – Eisenach – Erfurt; Kassel – Gießen – Frankfurt |
| Riedbahn Frankfurt – Mannheim (DE) | — | via Darmstadt én via Mainz – Worms |
| NBS Nürnberg – Ingolstadt (DE) | 2006 | Altmühltalbahn via Treuchtlingen |
| Emmerich – Oberhausen (DE) | — | **Mönchengladbach – Venlo – 's-Hertogenbosch** |
| LGV Sud-Est (FR) | 1981 | PLM: Paris – Dijon – Mâcon – Lyon |
| LGV Nord (FR) | 1993 | Paris – Amiens/Douai – Arras – Lille |
| LGV Est (FR) | 2007/2016 | Paris – Nancy/Metz – Strasbourg |
| LGV Rhin-Rhône (FR) | 2011 | Dijon – Besançon – Belfort – Mulhouse |
| Gotthard-Basistunnel (CH) | 2016 | Gotthard **Bergstrecke** (1882), via Göschenen en Airolo |
| Lötschberg-Basistunnel (CH) | 2007 | Lötschberg **Bergstrecke** (1913), via Kandersteg en Goppenstein |

**Elke uitwijkroute is de historische lijn die de hogesnelheidslijn verving.** Geen
van die oude lijnen is opgeheven; ze liggen er als reserve. Dat is het spiegelbeeld
van de IJzeren Rijn, die wél dood is — en dat verschil is scherper dan "oud spoor"
of "enkelspoor". Zie het slot van dit document.

---

## Gedocumenteerde stremmingen en hoe ze zijn afgehandeld

### Nederland / Duitsland — Emmerich – Oberhausen

De belangrijkste vondst van dit onderzoek. De lijn Arnhem – Emmerich – Oberhausen
wordt driesporig gemaakt; sinds 15 februari 2025 wisselen volledige en enkelsporige
stremmingen elkaar af, tot medio 2026.

Tijdens de stremming worden de internationale treinen vanaf Köln omgeleid **via
Mönchengladbach Hbf en 's-Hertogenbosch, met een halte in Venlo**, ongeveer
30 minuten langer. De haltes **Düsseldorf Hbf, Duisburg Hbf, Oberhausen Hbf en
Arnhem Centraal vervallen**.

Dit verklaart drie dingen tegelijk:

- waarom de Nightjet Amsterdam–Basel van 2021 tot 2026 via Venlo reed, en vanaf
  mei 2026 weer via Arnhem;
- waarom de Rheingold van **1951 tot 1962** via Kaldenkirchen/Venlo reed in plaats
  van via Emmerich, en daarna terugging (zie `docs/tee-loopwegen.md`);
- waarom geval 3 in `docs/nachttrein-testset.md` twee geldige varianten heeft.

Venlo is geen alternatieve route van een bepaalde trein. **Venlo is de vaste
omleidingsroute van de corridor Arnhem–Emmerich**, al 75 jaar, en hij wordt
ingezet zodra Emmerich niet beschikbaar is.

### België — HSL 1, elke zomer twee weken

Infrabel vernieuwt HSL 1 voor 310 miljoen euro over tien jaar. Het meeste gebeurt
's nachts, maar **elke zomer ligt de lijn ongeveer twee weken volledig uit
dienst**. Eurostar en TGV INOUI gaan dan over het klassieke net; Eurostar rekent op
een half uur extra, zowel Brussel–Parijs als Brussel–Londen.

### België — HSL 2, elke zomer tot 2031

HSL 2 (Leuven–Ans) moet tegen 2031 volledig vernieuwd zijn, voor circa 59 miljoen
euro. Onderbrekingen in de zomer van 2025, 2026 en in de zomers 2028–2031,
gemiddeld twee weken per keer. In 2025 ging het om 24 km dwarsliggers tussen
Hoegaarden en Pousset, van 2 tot 17 augustus, met een aangepaste dienst over de
klassieke lijn Leuven – Landen – Liège.

### België/Nederland — de Beneluxtrein

Andersom is even leerzaam. De Beneluxtrein Amsterdam–Brussel reed van 1957 tot
2018 over de **klassieke** route via Roosendaal, en pas vanaf april 2018 over de
HSL. Tijdens het Fyra-debacle (9 december 2012 – 17 januari 2013) verdween de
klassieke trein even helemaal, om in februari 2013 terug te keren. De klassieke
corridor is hier dus de oude norm en de HSL de nieuwkomer.

### Duitsland — NBS Köln – Rhein/Main

In 2026 werd de linke Rheinstrecke tussen Köln en Mainz onderhouden van 20 juni tot
10 juli. Van 2 juli 21:00 tot 10 juli 05:00 gingen de treinen Köln–Koblenz om:
de haltes **Köln Hbf, Bonn Hbf, Remagen en Andernach vervielen**, vervangen door
**Köln Messe/Deutz en Bonn-Beuel**. Tot 60 minuten langer. De halfuurs-ICE-lijnen
Hamburg–Köln–Frankfurt Flughafen–Stuttgart–München en –Mannheim–Basel gingen
tussen Köln en Mannheim grotendeels over de Rijnlijn.

Let op de halteverschuiving: Köln Hbf → Köln Messe/Deutz en Bonn Hbf → Bonn-Beuel
zijn *andere stations*. Een omleiding verandert dus soms ook de stops in de feed —
maar dan wel op een manier die pas achteraf te herkennen is.

### Duitsland — NBS Hannover – Würzburg

Volledig vernieuwd tussen 2019 en 2024 voor 850 miljoen euro. Het deel
Kassel–Fulda lag van **1 april tot 9 december 2023** dicht. Göttingen–Nürnberg ging
om via **Eisenach en Erfurt** (met haltes daar); Kassel–Frankfurt via **Gießen**,
tweeuurs in plaats van uurs, en zonder de haltes Fulda, Hanau, Frankfurt Süd en
Frankfurt Flughafen. Tot 60 minuten langer.

### Duitsland — Riedbahn Frankfurt – Mannheim

**15 juli tot 14 december 2024** volledig dicht: geen ICE, geen regionaal verkeer,
geen S-Bahn, geen goederen, over 74 km. Het langeafstandsverkeer ging over twee
parallelle routes: **via Darmstadt** en **via Mainz en Worms**, ongeveer een half
uur langer.

### Duitsland — NBS Nürnberg – Ingolstadt

Van **31 oktober tot 11 december 2026** volledig dicht voor railvernieuwing in de
tunnels Irlahüll en Euerwang. Omleiding via de **Altmühltalbahn en Treuchtlingen**,
ongeveer 45 minuten langer tussen Ingolstadt en Nürnberg. ICE-lijn 28 rijdt alleen
nog Nürnberg–Hamburg (München vervalt als halte), lijn 29 wordt omgeleid met
+30 minuten. München–Berlin wordt ~45 minuten langer.

### Duitsland — het hele programma

De *Generalsanierung Hochleistungsnetz* saneert tussen 2024 en 2035 ruim
**4.000 streckenkilometer** in **41 corridors**, telkens met een maandenlange
volledige stremming. Afgerond of lopend: Riedbahn (2024), Emmerich–Oberhausen
(15.2.2025–17.5.2026), Berlin–Hamburg (1.8.2025–14.6.2026),
Hagen–Wuppertal–Köln (6.2–10.7.2026). Gepland 2026: Nürnberg–Regensburg,
Obertraubling–Passau, rechte Rheinstrecke Troisdorf–Wiesbaden. 2027:
Rosenheim–Salzburg, Lehrte–Berlin, Bremerhaven–Bremen, Fulda–Hanau. Vanaf 2028:
Köln–Koblenz–Mainz, München–Rosenheim, Hagen–Hamm, Lübeck–Hamburg.

Met andere woorden: in Duitsland is er de komende tien jaar **permanent** minstens
één hoofdcorridor omgeleid.

### Duitsland — Rastatt, 2017

Geen hogesnelheidslijn maar wel de belangrijkste noord-zuidas. Op 12 augustus 2017
zakte het spoor bij de tunnelbouw in Rastatt tot 30 cm weg. De Rheintalbahn lag
**zeven weken** dicht, tot 2 oktober. Duizenden treinen vielen uit of werden
omgeleid, deels via Frankrijk; de geschatte schade is twee miljard euro. Het
klassieke voorbeeld dat een omleidingsroute ook internationaal kan zijn.

### Frankrijk — LGV Sud-Est

Van **8 november 23:00 tot 13 november 2024 04:00** volledig dicht (101 uur) voor
de voorbereiding van nieuwe seingeving. De TGV's bleven rijden, maar **over de
klassieke lijn**, met fors langere rijtijden; de Bourgondische stations en alle
zuidoostelijke stations werden geraakt. Ook in maart 2024 was er een sluiting.
Structureel: TGV's naar Bourgogne-Franche-Comté en Zwitserland rijden sowieso over
de klassieke lijn tussen Dijon en Lyon, om niet voor enkele tientallen kilometers
een hogesnelheidspad te bezetten.

### Frankrijk — LGV Nord

Na een vernieuwingsprogramma voor het spoor (2015–2024) loopt sinds 2025 een
**tienjarig programma voor de wissels**. Van **14 september tot 25 oktober 2026**
rijden bepaalde treinen tussen Lille en Arras tijdelijk over de klassieke lijn.
Het zwaartepunt ligt op **3 en 4 oktober 2026**: dan wordt het verkeer in dat vak
volledig onderbroken en gaan alle treinen — Eurostar inbegrepen — over de
klassieke lijn.

### Frankrijk — de sabotage van 26 juli 2024

In de nacht van 25 op 26 juli 2024 werden gecoördineerde brandstichtingen gepleegd
in seinhuizen en kabelgoten bij de aftakkingen van de **LGV Atlantique, LGV Nord en
LGV Est**; een vierde aanslag op de LGV Sud-Est mislukte. 800.000 reizigers werden
geraakt, Eurostar inbegrepen. Het laat zien dat een omleiding ook van de ene op de
andere dag kan ontstaan, zonder aankondiging in welke dataset dan ook.

### Zwitserland — Gotthard-Basistunnel

Op **10 augustus 2023** ontspoorden 16 goederenwagens 17 km na de tunnelmond, door
een gebroken wielschijf. Het hele reizigersverkeer ging maandenlang over de
**Gotthard Bergstrecke**, tot 60 minuten langer; goederen deels via de Lötschberg.
Zeven kilometer spoor vernieuwd, schade circa 150 miljoen frank.

### Zwitserland — Lötschberg-Basistunnel

Bij stremming gaat het verkeer over de **Bergstrecke via Kandersteg en
Goppenstein**. In december 2023 drong water beide buizen binnen; in september 2019
ontspoorde een bouwtrein in de scheiteltunnel. Het onderhoudsconcept voorziet
bovendien in geregelde volledige stremmingen in de nacht van zondag op maandag,
plus vier weken in de zomer.

---

## Wat dit betekent voor de router

**1. Er bestaat geen statisch juist antwoord.** Voor Schiphol–Rotterdam zijn zowel
de HSL als de Oude Lijn juist, afhankelijk van de week. Hetzelfde geldt voor
Köln–Frankfurt (NBS of Rijnlijn), Parijs–Lyon (LGV of PLM), Arnhem–Oberhausen
(Emmerich of Venlo), Zürich–Lugano (basistunnel of Bergstrecke). Elke oplossing die
per baanvakpaar één corridor vastlegt, is een deel van het jaar aantoonbaar fout —
en dat deel is niet klein.

**2. Alleen `shapes.txt` volgt de omleiding.** De stops volgen hem niet (de trein
passeert Leiden zonder te stoppen), de rijtijd nauwelijks (een omleiding kost 30 tot
60 minuten, wat binnen de spreiding van een nachttrein valt), en de
infrastructuurtags helemaal niet. `shapes.txt` wordt per dienstregelingsversie
opnieuw gepubliceerd en volgt de omleiding dus wél. Dat verschuift de
shape-integratie uit `docs/openstaand-uitrol.md` van "verfijning voor NL en DE"
naar **de enige aanpak die principieel klopt**.

**3. Voor de feeds zonder shapes blijft het een schatting.** Van de zeven feeds
hebben alleen `nl` en `de_delfi` shapes. Voor `be`, `fr` en `ch` blijft A* nodig, en
daar moet de uitkomst dus expliciet als schatting worden behandeld — niet als
waarheid die de kleuring stuurt.

**4. Een strafactor op "oud klassiek spoor" is gevaarlijk.** De verleiding is om de
IJzeren Rijn uit te sluiten door secundair spoor te bestraffen. Maar élke
omleidingsroute in de tabel hierboven is precies zo'n oude klassieke lijn: de Oude
Lijn uit 1847, de Gotthard Bergstrecke uit 1882, de Lötschberg Bergstrecke uit
1913, de Altmühltalbahn, de linke Rheinstrecke. Die zijn geen van alle dood — ze
zijn de reserve.

Het onderscheid dat wél werkt is niet "oud" maar **"draagt geen doorgaand verkeer
meer"**. Over de IJzeren Rijn rijdt sinds 1953 geen doorgaande reizigerstrein; over
de Gotthard Bergstrecke rijdt er elke dag een. In OSM is dat het verschil tussen
een lijn zonder enige reizigersroute-relatie en een lijn met een volwaardige
dienst — niet tussen `usage=main` en `usage=branch`. Dat is de vorm die de vijfde
aanpak zou moeten aannemen; nog niet gemeten.

## Bronnen

- [In 2028 maandenlange stremming nodig voor herstel HSL-Zuid — treinreiziger.nl](https://www.treinreiziger.nl/in-2028-maandenlange-stremming-nodig-voor-herstel-hsl-zuid/) en [HSL moet bijna half jaar dicht](https://www.treinreiziger.nl/hsl-moet-opgeteld-bijna-half-jaar-dicht-voor-herstelwerk-stremming-veel-langer-dan-eerder-verwacht/)
- [Eerste herstel HSL-viaducten voorzien in 2028 — ProRail](https://www.prorail.nl/nieuws/eerste-herstel-hsl-viaducten-voorzien-in-2028-langere-buitendienststellingen-nodig)
- [Sperrpausen 2026 — Ausbaustrecke Emmerich–Oberhausen, DB InfraGO](https://www.emmerich-oberhausen.de/aktuelles/Unsere%20Sperrpausen%20im%20Jahr%202026)
- [Vernieuwing van de hogesnelheidslijn tussen Brussel en de Franse grens — Infrabel](https://infrabel.be/nl/project/vernieuwing-hsl1) en [HSL tussen Brussel en Frankrijk 18 dagen buiten gebruik — SpoorPro](https://www.spoorpro.nl/spoorbouw/2024/08/12/hsl-tussen-brussel-en-franse-grens-18-dagen-buiten-gebruik/)
- [Grote vernieuwing van hogesnelheidslijn Leuven–Luik — Infrabel](https://press.infrabel.be/grote-vernieuwing-van-hogesnelheidslijn-leuven-luik-met-inzet-van-onder-meer-een-700-meter-lange-werktrein)
- [Beneluxtrein — Wikipedia](https://nl.wikipedia.org/wiki/Beneluxtrein)
- [Linker Rhein: DB macht Umleiterstrecke zwischen Köln und Mainz fit — Deutsche Bahn](https://www.deutschebahn.com/de/presse/presse-regional/pr-duesseldorf-de/presseinformationen-regional/Linker-Rhein-DB-macht-Umleiterstrecke-zwischen-Koeln-und-Mainz-vor-Start-der-Korridorsanierung-Troisdorf-Unkel-weiter-fit--13952614)
- [Sanierung der Schnellfahrstrecke Hannover–Würzburg, Abschnitt Kassel–Fulda — Deutsche Bahn](https://www.deutschebahn.com/de/presse/presse-regional/Presseblog-zur-Sanierung-der-Schnellfahrstrecke-Hannover-Wuerzburg-im-Abschnitt-Kassel-Fulda-10588108)
- [Riedbahn-Sperrung zwischen Frankfurt und Mannheim — hessenschau.de](https://www.hessenschau.de/wirtschaft/riedbahn-sperrung-zwischen-frankfurt-und-mannheim-was-reisende-wissen-muessen-v4,riedbahn-sperrung-104.html)
- [Sperrung auf ICE-Strecke Nürnberg–Ingolstadt — Bahnblogstelle](https://bahnblogstelle.com/242063/sperrung-auf-ice-strecke-nuernberg-ingolstadt/)
- [Generalsanierung Hochleistungsnetz — Wikipedia](https://de.wikipedia.org/wiki/Generalsanierung_Hochleistungsnetz)
- [Rastatt Tunnel — Wikipedia](https://en.wikipedia.org/wiki/Rastatt_Tunnel) en [Rheintalbahn closure lifted on 2 October](https://www.tunnel-online.info/en/artikel/tunnel_Rheintalbahn_Closure_lifted_on_2_October-3020727.html)
- [La ligne TGV Paris-Lyon fermée du 9 au 12 novembre — ICI](https://www.ici.fr/infos/transports/sncf-la-ligne-a-grande-vitesse-paris-lyon-fermee-du-9-au-12-novembre-des-trajets-allonges-et-gares-non-desservies-7494972)
- [Renouvellement de la LGV Nord — SNCF Réseau](https://www.sncf-reseau.com/fr/projets/hauts-de-france/renouvellement-lgv-nord)
- [Sabotages sur le réseau ferroviaire français en 2024 — Wikipédia](https://fr.wikipedia.org/wiki/Sabotages_sur_le_r%C3%A9seau_ferroviaire_fran%C3%A7ais_en_2024)
- [Eisenbahnunfall im Gotthard-Basistunnel — Wikipedia](https://de.wikipedia.org/wiki/Eisenbahnunfall_im_Gotthard-Basistunnel)
- [Lötschberg-Basistunnel — Wikipedia](https://de.wikipedia.org/wiki/L%C3%B6tschberg-Basistunnel)
