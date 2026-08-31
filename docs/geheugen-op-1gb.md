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
naar 106 seconden. Punt 3 staat nog open.

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
anders raak je de `uv run`-parent, die op SIGUSR1 termineert.

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

## Nog open

- **De DE-plan-prune.** Plan-entries dateren via hun slice — de sleutel van
  `plan_slices` bevat al datum en uur — en ze met diezelfde TTL laten verlopen.
  Dat is de enige wijziging die de resterende ratchet raakt.
- **Daarna opnieuw 48 uur meten**, met dezelfde bodemvergelijking. Zonder die
  herhaling weten we niet of het lek gedicht is of dat er een tweede onder zat.
- **Van de lijst af:** het allocator-experiment. `MALLOC_ARENA_MAX` en
  `malloc_trim` hebben hier aantoonbaar niets te halen.
- **Op termijn:** het feedvolume groeit — NL verdubbelde in twee dagen van 40.000
  naar 90.000 segment-observaties per poll. Zet dat door, dan is niet het lek de
  bindende beperking maar de machine.
