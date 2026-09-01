# Openstaand: verificatie van de DE-plan-prune

**Status op 2026-09-01: wachten op meetdata. Uitvoeren vanaf woensdag 2 september
rond 11:00, of later — hoe langer het draait, hoe sterker het bewijs.**

Dit is een handoff. Alles wat nodig is om de meting uit te voeren en te
interpreteren staat hieronder; voorkennis van eerdere sessies is niet nodig. De
achtergrond staat in `docs/geheugen-op-1gb.md` (postmortem van het
geheugenonderzoek, 26–31 augustus 2026).

Verwijder dit bestand zodra de verificatie rond is en de uitkomst in
`docs/geheugen-op-1gb.md` verwerkt is.

## Toegang tot de VM

```
ssh -F ~/.config/reisplan/ssh/config google_micro '<commando>'
```

**Precies die vorm.** Kaal `ssh google_micro` werkt niet: `~/.ssh` staat in
`denyRead` van de sandbox, dus zelfs de alias lost niet op, en de permissieregel
in `~/.claude/settings.json` staat alleen `Bash(ssh -F ~/.config/reisplan/ssh/config *)`
toe. De config wijst naar een eigen key en regelt zelf een proxytunnel
(`~/.config/reisplan/ssh/proxytunnel.py`), want de sandbox laat geen directe
sockets naar buiten.

**Pushen naar GitHub kan niet vanuit de sandbox** — de GitHub-key ligt in
`~/.ssh` en is bewust onbereikbaar. Commit gerust; vraag de eigenaar te pushen.

## Wat er draait

- Commit **`215ddad`**, aggregator herstart **2026-08-31 18:43:35 UTC**.
- Voorgeschiedenis: `4b40db1` verplaatste de zware builds naar kortlevende
  subprocessen, `3c0ebd5` repareerde een planningsfout (duty cycle 100% → 52%)
  en voegde de `de_*`-probes en `anonmaps` toe aan de diagnostiek.

## Wat `215ddad` verandert

In `pipeline/aggregator/src/aggregator/db_timetables.py`, methode `_prune`:
plan-entries worden nu per dienstdag opgeruimd. De dienstdatum zit in de stop-id
(`{trip}-{yymmddHHMM}-{idx}`) en wordt gedecodeerd met het bestaande
`_split_stop_id`. Vloer is **gisteren** (Europe/Berlin), zodat een trein die vóór
middernacht vertrok zijn dienstdatum houdt zolang hij rijdt.

De oude klep (`len(entries) > 20_000` per station) blijft staan als backstop voor
ids zonder parsebare datum. Die klep wás het probleem: de groei verdeelt zich
over honderden stations met een paar honderd entries elk, dus 20.000 werd nooit
gehaald.

## De meting

```
# hoofdreeks
ssh -F ~/.config/reisplan/ssh/config google_micro \
  'journalctl -u reisplan-aggregator --since "2026-08-31 18:43" --no-pager -o short-iso | grep "diag: rss="'

# cadans
ssh -F ~/.config/reisplan/ssh/config google_micro \
  'journalctl -u reisplan-aggregator --since "2026-08-31 18:43" --no-pager -o short-iso | grep "INFO snapshot:" | grep -oE "^[0-9T:+-]+"'

# duty cycle
ssh -F ~/.config/reisplan/ssh/config google_micro \
  'journalctl -u reisplan-aggregator --since "2026-08-31 18:43" --no-pager -o short-iso | grep -E "job (inspection|archive): done"'

# fouten
ssh -F ~/.config/reisplan/ssh/config google_micro \
  'journalctl -u reisplan-aggregator --since "2026-08-31 18:43" --no-pager | grep -E "exited [0-9]|killed after|Traceback|diag: .*failed|de: poll mislukt"'

# optioneel: heap dump (kan minuten achter de builds in de rij staan)
ssh -F ~/.config/reisplan/ssh/config google_micro 'pkill -USR1 -f "bin/aggregator$"'
```

Het `$`-anker in `bin/aggregator$` is essentieel: zonder anker raak je ook de
`uv run`-parent, en diens default-actie op SIGUSR1 is *terminate*.

Een diag-regel ziet er zo uit:

```
diag: rss=272M swap=66M | glibc arena=60M mmap=42M live=28M free=32M
    | duckdb=42M tmp=0M | anonmaps=57/500M | pyblocks=2799758
    | caches seg=... stop=... | de_planst=67 de_plan=3896 de_paths=2333 ...
```

## Wat bewezen moet worden

### 1. Krijgt `de_plan` dalingen?

Dit is de kernvraag. Tel de dalingen over de hele reeks, zoals eerder gedaan.

| | vóór de fix (48 u op `3c0ebd5`) | verwacht na de fix |
|---|---|---|
| `de_plan` | 2.012 → 179.331 | plateau rond twee dienstdagen |
| dalingen | **0** op 264 metingen | zaagtand, ~1 val per etmaal |

Rond middernacht Europe/Berlin hoort een hele dienstdag weg te vallen. Blijft die
zaagtand uit, dan grijpt de prune niet — onderzoek dan in deze volgorde: wordt
`_prune` aangeroepen (regel ~398 in `db_timetables.py`), klopt de vloer, en zijn
de stop-ids in productie wel dateerbaar (`_split_stop_id` geeft `""` als de start
geen tien cijfers is).

Ter vergelijking: `de_paths`, `de_state` en `de_labels` pruneden altijd al goed
(130, 119 en 130 dalingen over 48 uur) — die horen onveranderd te ademen.

### 2. Is de dagbodem vlak?

Dit is de toets die telt, en de reden dat er dagen gewacht wordt. Binnen één
venster van zes uur ziet echte groei er hetzelfde uit als de normale opbouw van
een dienstdag; alleen hetzelfde dagdeel op twee dagen scheidt die twee.

Bepaal per kalenderdag het minimum van `rss+swap` en vergelijk **het venster
08:00–11:00 UTC** van opeenvolgende dagen. Referentie van vóór alle fixes:

| Venster 08:00–11:00 UTC | n | min | mediaan |
|---|---|---|---|
| 28 augustus | 18 | 356 M | 385 M |
| 29 augustus | 18 | 432 M | 462 M |

Dat was +76 MB bodemstijging per etmaal. Blijft de bodem nu vlak, dan is de
ratchet weg.

### 3. Geen regressie in cadans, duty cycle of de DE-bron

Referenties uit de vorige ronde (48 uur op `3c0ebd5`, alles gezond):

- snapshotcadans p50 **61 s**, p90 **106 s**, max 1827 s, 27 gaten >300 s
- duty cycle **52 %**; 286 inspectiebuilds (gem. 289 s), 45 archiefruns (gem. 157 s)
- nul fouten, nul tracebacks

Let extra op `de: poll mislukt` — de wijziging raakt de DE-bron.

## Startwaarden van deze run

Gemeten twaalf minuten na de herstart (2026-08-31 18:55 UTC):

```
rss=272M swap=66M (338M totaal) | anonmaps=57/500M | pyblocks=2799758
de_planst=67  de_plan=3896  de_slices=201  de_paths=2333  de_labels=2355
de_state=904  de_stops=1337
```

## Valkuilen

- **Een herstart zet `de_plan` op nul.** De startwaarde bewijst dus niets; alleen
  het verloop telt. Is er tussentijds herstart, begin de reeks dan bij die start.
- **De diag-regel komt elke 600 s, maar staat achter de builds in dezelfde lus.**
  De samples zijn daardoor onregelmatig verdeeld; reken met tijdstempels, niet
  met sample-indexen.
- **De deep size van `de.plan` in de heap dump is een ondergrens.** De schatter
  recurseert niet in dataclasses, dus de `PlanStop`-velden tellen niet mee. Op
  30 augustus stond hij op ~26 M bij 179.331 entries.
- **`gc.get_objects()` ziet geen strings, bytes of ints.** String-zware groei is
  onzichtbaar in het histogram; gebruik de cache-tellers.

## Uitkomsten en vervolg

- **Plateau én vlakke bodem** → de ratchet is weg. Werk de uitkomst bij in
  `docs/geheugen-op-1gb.md` (sectie "Nog open"), pas de regel in `CLAUDE.md` aan,
  en verwijder dit bestand. Beoordeel daarna of de resterende bodem acceptabel is
  op 969 MB.
- **Plateau maar bodem stijgt door** → er zit een tweede oorzaak onder. Volgende
  verdachte: `Opslag.venster_ruw()` doet elke 60 s een `fetchall()` van 30 minuten
  `seg_obs`; bij het huidige feedvolume is dat een forse minuutpiek. Streamen in
  plaats van fetchall zou dat wegnemen.
- **Nog steeds monotoon** → de prune grijpt niet; zie de drie controles bij punt 1.

Als vangnet bestaat altijd nog een nachtelijke herstart (`RuntimeMaxSec` op de
unit); `_warm_caches()` in `opslag.py` maakt dat veilig. Dat maskeert het
probleem wel, dus alleen inzetten als bewuste keuze.

Implementeer geen vervolgfix zonder dat de eigenaar erom vraagt (zie `CLAUDE.md`).
