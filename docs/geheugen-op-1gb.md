# Geheugen op één gigabyte

Postmortem van het geheugenonderzoek aan de aggregator, 26 – 31 augustus 2026
(commits `783ce5a` t/m `3c0ebd5`). Doel van dit document is niet het incident
vastleggen maar de lessen: de e2-micro heeft 969 MB en dat verandert niet,
terwijl het feedvolume groeit. Dit gaat dus vaker spelen.

Een visuele versie van dit rapport staat als artifact op
`https://claude.ai/code/artifact/5eb95948-4ff9-4e35-bcf9-47c7b3439995`.

## Wat het bleek te zijn

De aggregator liep in twee dagen naar ~900 MB anoniem geheugen, waarna de VM
permanent swapte en de vertragingskaart tot zestien minuten achterliep. Er waren
**drie afzonderlijke oorzaken** en ze verhulden elkaar:

1. **De inspectiebuild blies de ouder op.** Elke paar minuten een grote
   tijdelijke werkset in een langlevend proces. Verplaatst naar een kortlevend
   subproces (`jobs.py`): basisverbruik van 523 naar 306 MB.
2. **Een planningsfout hield permanent een kindproces in leven.** Het volgende
   buildmoment werd bij de *start* gestempeld terwijl builds langer duurden dan
   het interval. Duty cycle 100%. Stempelen ná afloop: 52%.
3. **Daaronder zat een echt lek**, in `db_timetables.py`: `plan` groeide in 48
   uur van 2.012 naar 179.331 entries, zonder één daling in 264 metingen.

Punt 1 en 2 zijn gerepareerd en brachten de p90 van de snapshotcadans van 487
naar 106 seconden. Punt 3 is gerepareerd in `215ddad` en **geverifieerd op 12
september** (zie "Verificatie van de DE-plan-prune" hieronder): die container
ratchet niet meer. De bodem stijgt desondanks door — er zat een tweede oorzaak
onder, en die is nog open.

## Symptomen

| Meting | Gezond | Na twee dagen |
|---|---|---|
| Snapshot-interval p90 | 65 s | 487 s |
| Snapshot-interval max | 65 s | 953 s |
| Load average | 0,68 | 5,63 |
| CPU in iowait | < 5 % | 95 – 97 % |
| Anoniem geheugen | ~350 MB | ~920 MB |
| Schijf gelezen | — | 226 GB / 2 dagen |

De degradatie was monotoon vanaf procesestart: over opeenvolgende vensters van
vier uur klom de p90 van 107 naar 291, 317, 430 en 487 seconden. Een nachtelijke
herstart zou dus hooguit een paar uur kopen; dat was de eerste optie die afviel.

## Het instrument

De memory map liet zien wáár het geheugen zat maar niet wat erin stond: 203
anonieme mappings, samen 789 MB gecommit, tegenover een `[heap]`-segment van
115 MB en 11 MB aan file-mappings. Groottes zonder types.

Daarvoor kwam `pipeline/aggregator/src/aggregator/diagnostics.py`, met twee
trappen:

- **Trap A** (altijd aan, verwaarloosbare kosten): elke tien minuten één regel
  met RSS/swap, `mallinfo2`, DuckDB's `duckdb_memory()`, het aantal anonieme
  mappings, `sys.getallocatedblocks()` en de omvang van elke bekende cache.
- **Trap B** (op afroep, `SIGUSR1`/`SIGUSR2`): heap-histogram per type,
  gesamplede deep sizes per benoemde cache, de arena-regels uit
  `sys._debugmallocstats()`, en `malloc_trim` met RSS ervoor en erna.

```
diag: rss=273M swap=33M | glibc arena=88M live=30M free=57M
    | duckdb=35M | anonmaps=55/519M | pyblocks=2763290
    | caches seg=513135 stop=339651 ... de_plan=2012 de_paths=1452
```

Triggeren: `pkill -USR1 -f "bin/aggregator$"`. Het `$`-anker is essentieel,
anders raak je de `uv run`-parent, die op SIGUSR1 termineert. De dump zelf kost
~4 s, maar staat achter de builds in de rij: reken op minuten waarin het proces
in D-state staat en niets logt. Dat is geen storing.

### Meten vanaf de laptop

```
ssh -F ~/.config/reisplan/ssh/config google_micro '<commando>'
```

Precies die vorm. Kaal `ssh google_micro` werkt niet vanuit de sandbox: `~/.ssh`
staat in `denyRead`, dus de alias lost niet op, en de permissieregel staat alleen
`Bash(ssh -F ~/.config/reisplan/ssh/config *)` toe. De config wijst naar een eigen
key en regelt zelf een proxytunnel (`~/.config/reisplan/ssh/proxytunnel.py`), want
de sandbox laat geen directe sockets naar buiten. Pushen naar GitHub kan niet
vanuit de sandbox — die key ligt bewust in `~/.ssh`; commit gerust en vraag de
eigenaar te pushen.

De reeksen waar de analyses in dit document op rusten:

```
# geheugen en cache-tellers
journalctl -u reisplan-aggregator --since "<start>" --no-pager -o short-iso | grep "diag: rss="
# cadans per taak
journalctl -u reisplan-aggregator --since "<start>" --no-pager -o short-iso \
  | grep -E "INFO snapshot:|(nl|fr|be|ch): [0-9]+ segment-obs|de: [0-9]+ stations"
# builds en hun timeouts
journalctl -u reisplan-aggregator --since "<start>" --no-pager \
  | grep -E "job (inspection|archive): (done in|killed after)"
# fouten
journalctl -u reisplan-aggregator --since "<start>" --no-pager \
  | grep -E "exited [0-9]|killed after|Traceback|diag: .*failed|poll mislukt|poll failed"
```

Twee valkuilen bij het lezen. Een herstart zet alle tellers op nul, dus alleen het
verloop telt, nooit de startwaarde — controleer met `systemctl show -p
ActiveEnterTimestamp` of de reeks één procesleven beslaat. En de diag-regel komt
elke 600 s maar staat achter de builds in dezelfde lus, dus de samples liggen
onregelmatig: reken met tijdstempels, niet met sample-indexen.

Draai geen zware ad-hocquery's op `observaties.sqlite` op de VM zelf. Een
`GROUP BY` over de hele tabel liep daar op 12 september minutenlang in D-state en
drukte de aggregator meetbaar in; haal het bestand op of werk met de snapshots
onder `data/rt-archief/snapshots/`.

## Zes hypotheses, in volgorde

Elke weerlegging bracht de volgende voort.

**1. Fragmentatie in de glibc main arena — weerlegd.** Het `[heap]`-segment was
115 MB van de ~920. Later bevestigd: `malloc_trim` gaf 40 MB terug van 645.

**2. Per-thread arena's van glibc — weerlegd.** Die zijn 64 MB per stuk en
zouden als zodanig in de map staan. De verdeling toonde 70 regio's van 1 MB,
40 van 2 MB en een staart tot 39 MB — geen enkel 64 MB-patroon.

**3. Jemalloc houdt vrijgegeven arena's vast, buiten DuckDB's `memory_limit` om
— weerlegd.** Goede theorie, want jemalloc doet dat inderdaad. Maar de
DuckDB-wheel (1.5.5, 60 MB) bevat nul jemalloc-symbolen; het is glibc malloc.

**4. De dedup-caches groeien onbegrensd — weerlegd.** Ze krómpen: over 5,9 uur
verloor de seg-cache 175.606 entries en de stop-cache 218.675, terwijl het
geheugen met 113 MB groeide.

**5. High-water-mark-retentie door de inspectiebuild — half waar.** De buildpiek
was echt; hem naar een subproces verplaatsen verlaagde de basis van 523 naar
306 MB. Maar als verklaring voor de *groei* hield het geen stand. obmalloc geeft
arena's wel degelijk terug: 10.421 van 10.734 gereclaimd, huidig aantal 313
tegen een highwater van 323, en het aantal anonieme mappings ademt (50 dalingen
in twee dagen). De slack is reëel — 190 MB levend in 313 MB arena's, dus ~138 MB
versnippering — maar begrensd en stabiel.

**6. Er is geen ratchet, de groei is diurnaal — weerlegd.** Scherp tegenargument:
`opslag._laatste` groeit de hele dienstdag door en wordt pas geleegd rond 08:00
UTC, en álle metingen tot dan liepen over vensters overdag. De toets was dus
dezelfde vensters op opeenvolgende dagen vergelijken.

## De beslissende meting

Binnen één venster van zes uur ziet echte groei er hetzelfde uit als de normale
opbouw van een dienstdag. Het onderscheid komt pas bij hetzelfde dagdeel op twee
dagen:

| Venster 08:00 – 11:00 UTC | n | min | mediaan | max |
|---|---|---|---|---|
| 28 augustus | 18 | 356 M | 385 M | 461 M |
| 29 augustus | 18 | 432 M | 462 M | 480 M |

Zelfde tijdstip, zelfde fase van de dienstdag, zelfde aantal metingen: de bodem
steeg 76 MB en de mediaan 77 MB in één etmaal. Dagbodems liepen 348 → 432 → 462.

## De oorzaak

| Container (DE-bron) | start | na 48 u | piek | dalingen |
|---|---|---|---|---|
| `plan` | 2.012 | **179.331** | 179.331 | **0** |
| `plan` (stations) | 34 | 404 | 404 | **0** |
| `trip_paths` | 1.452 | 10.042 | 14.989 | 130 |
| `trip_state` | 543 | 5.770 | 10.857 | 119 |
| `trip_labels` | 1.463 | 10.167 | 15.147 | 130 |

Drie van de vier ademen mee met de dienstdag. De vierde groeit strikt monotoon.

De onderliggende fout: er ís een noodrem, maar hij staat op de verkeerde as. De
code leegt een station zodra dát station meer dan 20.000 entries heeft; de groei
verdeelt zich over 404 stations, gemiddeld 440 elk. Die drempel wordt nooit
gehaald.

Waarom dit vijf dagen onzichtbaar bleef: de diagnostiek peilde `statisch`,
`opslag`, `blokkades` en `inspection._meta_cache` — precies de modules die
tijdens het onderzoek open stonden. De DE-bron had eigen state en zat in geen
enkele probe. Het heap-histogram liet de groei al zien als `PlanStop`-objecten,
maar die werden aangezien voor churn van de bouwlus.

## Resultaat

| Ronde | duur | rss+swap | p90 cadans | duty cycle |
|---|---|---|---|---|
| Uitgangssituatie | 5,9 u | 523 → 636 M | 487 s | — |
| Na subprocessen | 6,0 u | 306 → 412 M | 196 s | 100 % |
| Na planningsfix | 48 u | 348 → 480 M | **106 s** | **52 %** |

Over de laatste 48 uur: 2.345 snapshots, 286 inspectiebuilds, 45 archiefruns,
nul fouten of tracebacks. De p50 staat op 61 seconden — de bedoelde cadans.

Dat resultaat heeft niet standgehouden. Zie "Waar het elf dagen later staat".

## Verificatie van de DE-plan-prune

Gemeten 12 september 2026 op de run die sinds 7 september 08:10 UTC draait
(430 diag-samples). `de_plan` laat nu de zaagtand zien die de fix moest opleveren:

| middernacht Europe/Berlin | piek | dal |
|---|---|---|
| 8 sep 21:59 | 161.038 | 93.401 |
| 9 sep 22:06 | 184.645 | 92.490 |
| 10 sep 22:08 | 182.619 | 91.567 |
| 11 sep 22:14 | 181.843 | 92.126 |

Drie identieke cycli op rij: piek ~183k, dal ~92k, dat is de bedoelde retentie van
twee dienstdagen (~90k entries per dienstdag). Vergelijk de 48 uur vóór de fix:
2.012 → 179.331 met **nul** dalingen in 264 metingen. De prune grijpt, op het
juiste moment, en ruimt precies één dienstdag op.

Een tussenmeting op 2 september, 39 uur na de herstart, liet één daling zien
(1 sep 22:07, −17.577) en gaf toen nog géén uitsluitsel: de eerste middernacht
ruimde alleen de halve eerste dag op, dus de teller vulde nog naar zijn plafond.
Dat is de reden dat deze toets dagen kost en niet uren.

**Maar de bodem is niet vlak.** Minimum van `rss+swap` in het venster
08:00–11:00 UTC:

| dag | min | mediaan |
|---|---|---|
| 8 sep | 411 M | 446 M |
| 9 sep | 444 M | 480 M |
| 10 sep | 467 M | 487 M |
| 11 sep | 479 M | 498 M |

+33, +23, +12 MB per etmaal. De stijging remt af, maar `de_plan` zat vanaf
9 september al op zijn plafond en verklaart de laatste twee stappen dus niet meer.
Dit is uitkomst 2 van de verificatie: **plateau, tweede oorzaak eronder.**

Wat de heap dump van 2 september daarover zei — `de.plan` is niet de grootste post:

| cache | len | deep |
|---|---|---|
| `opslag._laatste_seg` | 234.105 | ~56 M |
| `statisch.segment_randen` | 30.719 | ~39 M |
| `opslag._laatste` | 4 | ~24 M |
| `de.plan` | 404 | ~19 M |
| `de.trip_paths` | 13.274 | ~16 M |
| `statisch._adjacency` | 13.515 | ~12 M |

`de.plan` kost 0,145 KB per entry, identiek aan de meting van 30 augustus
(~26 M bij 179.331 entries) — lineair, geen verrassing per entry. De verdachten
voor de resterende stijging staan onder "Nog open".

## Waar het elf dagen later staat

Gemeten over het etmaal 11 september 06:00 – 12 september 06:00 UTC. Per taak het
bedoelde ritme tegen het werkelijke:

| taak | bedoeld | n per etmaal | verwacht | gehaald | p50 | p90 | max |
|---|---|---|---|---|---|---|---|
| snapshot | 60 s | 669 | 1440 | **46 %** | 61 s | 304 s | 3829 s |
| nl-poll | 60 s | 590 | 1440 | **41 %** | 64 s | 340 s | 3348 s |
| be-poll | 60 s | 569 | 1440 | **40 %** | 64 s | 387 s | 4785 s |
| fr-poll | 120 s | 350 | 720 | **49 %** | 125 s | 656 s | 3318 s |
| ch-poll | 90 s | 396 | 960 | **41 %** | 99 s | 657 s | 3366 s |
| de-tick | 10 s | 2638 | 8640 | **31 %** | 12 s | 22 s | 3827 s |
| ns-storingen | 300 s | 150 | 288 | 52 % | 312 s | 1083 s | 3917 s |
| sncf-storingen | 600 s | 79 | 144 | 55 % | 1150 s | 1479 s | 4367 s |
| inspectiebuild | 300 s | 35 | ~147 | **24 %** | 1186 s | 5038 s | 13154 s |
| archiefrun | 3600 s | 19 | ~23 | 83 % | 4012 s | 4732 s | 11347 s |
| diag-sample | 600 s | 70 | 144 | 49 % | 1233 s | 1464 s | 4881 s |

De intervallen van de twee builds worden vanaf het *einde* van de vorige run
gestempeld, dus hun bedoelde aantal is `86400 / (interval + buildduur)`; voor de
inspectie is dat gerekend met de 289 s die eind augustus normaal was.

**Geen enkele taak haalt zijn ritme.** De p50 ziet er voor de pollers nog gezond
uit — de helft van de cycli loopt op tijd — maar de staart vreet het etmaal op:
van de 24 uur zit 13,7 uur in gaten groter dan de bedoelde 60 seconden, en 68
gaten van meer dan 300 seconden zijn samen goed voor 13,6 uur.

De DE-bron is het ergst af, en dat verklaart de lege Duitse kaart: 9.910
stationpolls per etmaal over 409 stations is **één ronde per 59 minuten**, terwijl
tier A elke 300 s en tier B elke 1500 s bedoeld is. De groene basislijn voor
Duitsland wordt gesynthetiseerd voor stops met een geplande tijd binnen
`EVENT_WINDOW_PAST_S` = 2700 s (45 minuten). Een ronde van 59 minuten is langer
dan dat venster, dus een deel van de Duitse stops wordt structureel nooit
waargenomen — niet vertraagd, niet op tijd, helemaal niet. Dekking op de kaart,
gemeten tegen de segmentgeometrie:

| land | baanvakken | in snapshot | dekking |
|---|---|---|---|
| **de** | **21.252** | **679** | **3,2 %** |
| nl | 4.126 | 721 | 17,5 % |
| be | 1.603 | 652 | 40,7 % |
| fr | 4.883 | 2.394 | 49,0 % |
| ch | 6.627 | 2.047 | 30,9 % |

(Landtoewijzing via ruwe bounding boxes op het middelpunt van elk baanvak, met
NL, BE en CH uitgesneden vóór DE; grensgebieden en Oostenrijk vallen daardoor een
enkele keer verkeerd. Voor ordes van grootte is dat ruim genoeg.)

Duitsland is 54 % van alle baanvakken op de kaart. Dit is géén regressie van
`215ddad`: archiefsnapshots van rond 05:20 UTC geven 2,6 % op 15 augustus, 3,3 %
op 29 augustus, 3,7 % op 2 september en 3,6 % nu. De DB Timetables-API is
station-bemonstering, geen landelijke feed — 409 sample­punten kunnen 21.252
baanvakken niet dekken zoals FR en CH dat doen. De API-limiet knelt daarbij niet:
`REQUEST_BUDGET_PER_MIN` staat op 45 en het feitelijke verbruik is naar schatting
~15/min. Wat knelt is dat de hoofdlus de DE-bron nog maar eens per ~38 s een slot
geeft in plaats van de bedoelde 10 s.

### De oorzaak van de vertraging: de inspectiebuild, en swap

De inspectiebuild is uit zijn budget gegroeid. In het etmaal:

- 35 builds **voltooid**, gemiddeld 775 s (was 289 s eind augustus)
- 35 builds **gekild op de timeout van 900 s** (`TIMEOUTS` in `jobs.py`)
- 1 archiefrun gekild op 3600 s

De helft van al het inspectiewerk wordt dus weggegooid en 300 s later opnieuw
begonnen. Inclusief de gekilde runs zit ~18 van de 24 uur in builds: een duty
cycle van ~75 %, tegen de 52 % waarop het onderzoek in augustus eindigde.

En daaronder: de machine wacht op schijf, niet op rekenkracht.

```
load average: 4,26  (2 vCPU)
vmstat:  us 1-3 %   sy 2-3 %   id 6-41 %   wa 53-90 %
free:    969 M totaal, 76 M vrij, 702 M swap in gebruik
```

53 tot 90 procent iowait bij 5 procent CPU-gebruik. Het is swap-thrash, precies
het beeld van eind augustus — alleen nu met een andere verdeling:

| | RSS | swap | totaal |
|---|---|---|---|
| aggregator (ouder) | 193 M | 319 M | 512 M |
| inspectie-kind (lopend) | 233 M | 23 M | 256 M |
| Google-agents (otelopscol, guest-agent, osconfig) | ~135 M | — | ~135 M |

512 + 256 + 135 = 903 M op een machine met 969 M. Er is geen ruimte: elke build
duwt de ouder de swap in, de ouder komt er traag weer uit, de build duurt daardoor
langer, en de volgende build staat al klaar. Dat is de terugkoppeling die alle elf
taken tegelijk onder hun ritme houdt.

Merk op dat de Google-agents ~14 % van het werkgeheugen opeisen voor telemetrie.

## Lessen

**1. Meet eerst, repareer daarna.** Vier van de zes hypotheses vielen om, en
drie klonken plausibel genoeg om er dagen aan te besteden. Wat ze deelden: ze
waren beredeneerd uit code en algemene kennis, niet gemeten.

**2. Je probes dekken wat je gelezen hebt, niet wat er is.** De probelijst groeide
organisch mee met de modules die toevallig openstonden. Dat voelde volledig en
was het niet. Inventariseer bij het bouwen van diagnostiek systematisch élk
object dat state vasthoudt — desnoods door de constructors af te lopen.

**3. Vergelijk bodems tussen dagen, geen hellingen binnen een dagdeel.** Een
workload met een dagritme laat elke zesuursmeting overdag stijgen. Dat is geen
groei, dat is de ochtend. Pas twee identieke vensters op opeenvolgende dagen
scheiden een ratchet van een ademhaling.

**4. Ken de blinde vlekken van je meetinstrument.** `gc.get_objects()` ziet geen
strings, bytes of ints — juist string-zware groei is onzichtbaar in het
histogram. `sys.getsizeof` telt alleen de container, niet de inhoud. De eigen
deep-size-schatter recurseert niet in dataclasses, waardoor precies de lekkende
container werd ondergerapporteerd. En `mallinfo2` rapporteert alleen de main
arena. Elk van die beperkingen is verdedigbaar; samen maakten ze dat "alle meters
staan vlak" iets heel anders betekende dan het leek.

**5. Als elke meter vlak staat en het geheugen groeit, mis je een meter.** Drie
rondes lang luidde de conclusie "geen enkele levende allocatie groeit". Dat was
letterlijk waar en inhoudelijk onjuist: de groeier stond niet in de lijst.
Behandel die combinatie als bewijs van een gat in de meting, niet als bewijs voor
een exotisch allocatormechanisme.

**6. Een noodrem op de verkeerde as is geen grens.** Bij elke cap hoort dezelfde
vraag: langs welke dimensie groeit dit ding werkelijk, en meet de grens langs
díe dimensie? Een cap die in de praktijk nooit afgaat is een comment, geen
mechanisme.

**7. Transiënte pieken in een langlevend proces verhogen de vloer.** Een build die
elke paar minuten een grote werkset opbouwt en weer vrijgeeft, laat arena's
achter waarin verspreid nog wat leeft. Op een ruime machine merk je dat nooit; op
een gigabyte is het het verschil tussen 523 en 306 MB basisverbruik. Zwaar,
periodiek werk hoort in een kortlevend proces.

**8. Plan intervallen vanaf het einde, niet vanaf de start.** Zodra builds langer
duurden dan hun interval (394 s tegen 300 s) stond de volgende al klaar zodra de
vorige eindigde. Eén regel verplaatsen bracht de duty cycle van 100% naar 52%.
Zulke bugs zijn onzichtbaar zolang het werk sneller is dan het interval, en
verschijnen precies wanneer het systeem het al zwaar heeft.

**9. Onderscheid begrensde slack van onbegrensde groei.** Er is 138 MB
versnippering in de obmalloc-arena's. Dat is veel, en het is niet het probleem —
het aantal arena's is stabiel. De 179.000 entries die nooit verdwijnen zijn dat
wel. Bij krap geheugen is de verleiding groot om de grootste post aan te pakken;
de juiste vraag is welke post *groeit*.

## Checklist bij nieuwe code op deze VM

- Elke container die state vasthoudt krijgt een expliciete grens — en die grens
  meet langs de as waarlangs hij groeit.
- Nieuwe langlevende state komt in de diagnostiekprobes. Anders bestaat hij niet.
- Zwaar of periodiek werk draait in een subproces, niet in de poll-lus of de
  onderhouds-thread.
- Geen `fetchall()` op tabellen die met het feedvolume meegroeien; itereer de
  cursor.
- Elke DuckDB-verbinding krijgt een eigen `memory_limit`; de default is 80% van
  het RAM.
- Een geheugenclaim toets je over minimaal 48 uur, met dezelfde dagdelen naast
  elkaar.
- Test zware DuckDB-wijzigingen lokaal met `REISPLAN_DUCKDB_MEM=600MB`; zonder
  limiet blijven deze bugs op de laptop onzichtbaar.

## Ingrepen van 12 september 2026

Na de meting hierboven doorgevoerd, op verzoek van de eigenaar:

**Op de VM, buiten reisplan** — `systemctl disable --now`:

| unit | RSS |
|---|---|
| `google-cloud-ops-agent` (+ fluent-bit, + otel-collector) | 86 M |
| `google-osconfig-agent` | 16 M |
| `exim4` (+ `exim4-base.timer`) | 7 M |

Effect direct na de ingreep: beschikbaar geheugen **143 → 335 MB**, page cache
210 → 280 MB, iowait van 53–90 % naar ~49 %. De guest-agent zelf
(`core_plugin`, 42 M) blijft staan: die regelt SSH-sleutels en metadata, en
uitzetten kan je buitensluiten. Terugdraaien is `systemctl enable --now` op
dezelfde units; je verliest tot die tijd Cloud Monitoring/Logging, niet de lokale
journal.

**In de code** — twee vensters:

- `WINDOW_S` in `inspection.py` van 4 naar 2 uur. Halveert de scan van de
  inspectiebuild (~152k → ~76k rijen `seg_obs`) en daarmee de buildduur, die op
  775 s gemiddeld zat tegen een interval van 300 s. De 4-uursknop op
  `inspectie.html` is meegegaan naar 2 uur; het artefact bediende beide vensters.
- `KLEUR_VENSTER_S` in `main.py` van 30 minuten naar 2 uur. Dit is géén
  geheugenmaatregel — het kost ~11 MB extra transiënte piek per snapshot en
  ongeveer twee keer zoveel rij-lookups per minuut. Het is een dekkingsmaatregel:
  bij ochtendspits geeft 30 min 57.274 observaties over 4.632 segmenten en 2 uur
  118.810 over 6.901 segmenten, dus **+49 % gekleurde baanvakken**. Dat raakt
  vooral Duitsland, waar één ronde langs de 409 stations ~59 minuten kost en een
  venster van een half uur dus principieel te kort is.

Beide vensters staan nu op 2 uur, waardoor kaart en inspectiepagina hetzelfde
tijdvak tonen.

## Nog open

Op volgorde van wat de meting van 12 september aanwijst. De maatregelen hierboven
zijn doorgevoerd; de rest niet — de eigenaar beslist wat er gebeurt.

- **Meet na.** Bovenstaande ingrepen zijn niet in samenhang nagemeten: doe de
  cadanstabel per taak opnieuw over een volledig etmaal en vergelijk. De
  verwachting is dat de builds weer binnen hun timeout vallen; of dat klopt, en
  wat het verruimde kleuringsvenster kost, is nog niet vastgesteld.
- **De dekkende index op `seg_obs`.** `venster_ruw()` gebruikt nu `seg_obs_ts`,
  een index op `ts` alleen, en doet daarna per rij een lookup buiten de index om:
  bij een venster van 2 uur zijn dat ~119.000 random reads per minuut over een
  bestand van 738 MB. Een index op `(ts, segment, delta_s, trip_id)` maakt die
  query dekkend en haalt die lookups volledig weg — dat is de tegenhanger van het
  verruimde venster. Aanmaken kost eenmalig een zware scan; plan dat bewust.

- **De inspectiebuild is de bindende beperking.** 775 s gemiddeld tegen een
  interval van 300 s, en de helft wordt gekild op de timeout van 900 s. `WINDOW_S`
  is daarom gehalveerd (zie hierboven); of dat genoeg is, moet de nameting
  uitwijzen. Zo niet: interval verhogen, of de build van de box halen (zie
  hieronder). Er is nog steeds niet gemeten wáár die 775 s precies in zitten.
- **De timeout begrenst de wandkloktijd niet strak.** Er staan runs in het log met
  `done in 989s` bij een `TIMEOUTS`-waarde van 900 s: `subprocess.run(timeout=…)`
  bewaakt zijn eigen wachttijd, de gelogde duur meet een ruimere span. Reken er
  niet op als harde bovengrens.
- **De diagnostiek is zelf een slachtoffer.** Trap A haalt 49 % van zijn ritme en
  trap B (`SIGUSR1`) kwam op 12 september in 30 minuten geen enkele keer aan bod:
  `diagnostics.run_if_due()` staat in dezelfde lus achter de builds, en die liepen
  onafgebroken. Zolang dat zo is, kun je het effect van elke maatregel hier niet
  meer meten.
- **De bodem stijgt nog steeds**, ook nu `de_plan` op zijn plateau zit: +23 en
  +12 MB op 10 en 11 september. Twee verdachten, in deze volgorde:
  `Opslag.venster_ruw()` trekt elke 60 s dertig minuten `seg_obs` in één
  `fetchall()`; en `opslag._laatste_seg` is met ~56 MB de grootste post in de heap
  dump en schommelt tussen 130k en 500k entries, met 65 waarschuwingen
  "dedup-cache boven 500000 na pruning" in 39 uur. Streamen in plaats van
  fetchall zou de eerste wegnemen.
- **De Duitse kaart is dun en dat is structureel.** 3,2 % dekking over 54 % van
  alle baanvakken. De rondetijd (59 min) moet onder `EVENT_WINDOW_PAST_S`
  (45 min) komen wil de groene basislijn überhaupt sluiten. `BATCH_SIZE` staat op
  4 en het API-budget is voor tweederde onbenut, dus daar zit de goedkoopste
  winst — maar pas nadat de hoofdlus weer lucht heeft, want de DE-bron krijgt nu
  eens per 38 s een slot in plaats van elke 10 s. Fundamenteel blijven 409
  sample­punten te weinig voor 21.252 baanvakken; vol kleuren vraagt een andere
  bron.
- **De vangnetten die er al zijn.** Een nachtelijke herstart (`RuntimeMaxSec` op
  de unit) is veilig — `_warm_caches()` in `opslag.py` dekt dat af — maar maskeert
  het probleem. De Google-agents (otelopscol en verwanten) kosten ~135 MB, 14 %
  van de machine, voor telemetrie die dit project niet gebruikt.
- **Van de lijst af:** het allocator-experiment. `MALLOC_ARENA_MAX` en
  `malloc_trim` hebben hier aantoonbaar niets te halen. En de DE-plan-prune zelf:
  die is geverifieerd en werkt.
- **Op termijn:** het feedvolume groeit — NL verdubbelde in twee dagen van 40.000
  naar 90.000 segment-observaties per poll. Zet dat door, dan is niet het lek de
  bindende beperking maar de machine. De meting van 12 september laat zien dat
  dat punt al bereikt is: geen enkele taak haalt nog zijn bedoelde ritme.
