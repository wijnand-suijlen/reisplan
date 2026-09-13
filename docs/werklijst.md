# Werklijst

Doorlopende lijst van wat openstaat, voor Claude en voor de eigenaar.

- **Hier staat alleen wát er moet gebeuren, door wie en wanneer.** De inhoud
  staat in `PLAN.md` of in een analyse onder `docs/`; elk punt verwijst ernaar.
- **Afgerond werk gaat eruit.** Wat het opleverde komt in een verslag
  (`docs/verslag-<datum>.md`) of in de analyse zelf.
- **Geen analyses in dit bestand.** Groeit een punt uit tot onderzoek, dan krijgt
  het een eigen document en blijft hier één regel over.
- Andere documenten verwijzen niet naar deze lijst; die verwijzing veroudert
  zodra een punt afgevinkt is.

## Met een datum

- [ ] **Cadansmeting over een etmaal** (zondag 13 sep; de verversing van
      zaterdag vervuilt een eerdere meting) — of alle taken op de VM hun bedoelde
      ritme halen na de ingrepen van 12 september (agents uit, buildvenster
      gehalveerd, dekkende index). Achtergrond: `docs/geheugen-op-1gb.md`.

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

- [ ] **Maandag 14 september na ~02:25: de tweede clusteringronde op de kaart
      controleren.** Wat er veranderde: `docs/verslag-2026-09-12.md`, "Tweede
      ronde". De verversing start zondag 22:00 UTC (= maandag 00:00 lokaal) en
      publiceert de nieuwe `segments.geojson` zodra de aggregator ná de mergefase
      opstart — naar de fasetijden van 12 september rond 02:25 lokaal, klaar rond
      04:25. Wat er dan moet kloppen:

      | meting | nu op de VM | verwacht |
      |---|---|---|
      | rechte-lijn-fallbacks | 2.130 van 29.158 (7,3 %) | ~1.738 van ~28.553 (**6,1 %**) |
      | clusters | 13.515 | ~13.408 |
      | clusterparen binnen 300 m | ~660 | ~627 |

      Let ook op: tussen ~02:25 en ~04:25 draait de aggregator met de nieuwe
      `merged.duckdb` maar nog de oude `eva_stations.json` (s10 draait in de
      laatste fase). De Duitse dekking is in dat venster dun; dat hoort zo en de
      afsluitende herstart dicht het.

- [ ] **Twee omleidingen meten als gratis validatie.** De vraag: veranderen de
      **stops** van die ritten, of alleen de rijtijd? Als alleen de rijtijd
      verandert, is dat de directe bevestiging dat geen enkele statische geometrie
      klopt. Te meten met `rt-archive/stops/<dag>.parquet`, zonder de VM. Tegelijk
      een toets op het blokkadegat uit de Cléon-casus. Achtergrond:
      `docs/hsl-omleidingen.md`, `docs/lijnvoering.md`.
      - **LGV Nord, 14 september – 25 oktober 2026**: treinen tussen Lille en
        Arras deels over de klassieke lijn; op **3 en 4 oktober** volledige
        onderbreking, alles inclusief Eurostar over klassiek spoor.
      - **NBS Nürnberg – Ingolstadt, 31 oktober – 11 december 2026**: volledig
        dicht, omleiding via de Altmühltalbahn en Treuchtlingen, +45 min.

## Claude

- [ ] **Alertfeeds één keer parsen en de CH-piek op de VM meten.** Stap 1 van
      `PLAN.md`, "Plan: verkeersinformatie vastleggen". Uitkomst bijschrijven in
      `docs/geheugen-op-1gb.md`.
- [ ] **Verkeersinformatie vastleggen**, stappen 2–6 van hetzelfde plan.
- [ ] **`planned_closures` nakijken.** Stond na de uitrol van 12 september op
      12.375 rand-dag-blokken tegen 3.255 lokaal. Als de kaart veel rode
      puntjeslijnen toont, is dat het eerste om te onderzoeken. Geen bewijs dat het
      fout is.
- [ ] **De HSL-kleuringsfout oplossen** (ontwerpwijziging), **de vijfde
      routeeraanpak meten** tegen `docs/nachttrein-testset.md`, en daarna **het
      lijnvoeringsplan herschrijven**. `docs/lijnvoering.md`, "Wat er eerst moet
      gebeuren".
- [ ] **`cluster_land`:** s4 in de pijplijn of de tabel weg.
      `docs/lijnvoering.md`, "Nog een artefact met hetzelfde euvel".
- [ ] **Het ongedekte interval tussen blokkade en baseline**, en stremmingen die
      langer duren dan de baseline. Ontwerpkeuze nog te maken.
      `docs/casus-cleon-2026-09-11.md`, "Wat dit over de pijplijn zegt".

## Eigenaar: beslissingen

- [ ] **Kaartnamen na de clustersamenvoeging.** De overlevende clusternaam is soms
      de Franse ("Anvers-Central" in plaats van "Antwerpen-Centraal"), omdat de
      naam van het eerste station in de groep komt en dat willekeurig is. Vraagt een
      voorkeursregel — bijvoorbeeld de naam uit de feed van het land waar het
      station ligt. Een keuze, geen bug; Claude bouwt het daarna.
- [ ] **DELFI opnemen naast `de_rv`, of vervangen.** `PLAN.md` spreekt van
      vervangen, `docs/lijnvoering.md` van opnemen.
- [ ] **Bewaartermijn van de ruwe alertmeldingen**, en of de laag
      `stationsinfo` standaard aan of uit staat. `PLAN.md`, "Plan:
      verkeersinformatie vastleggen".
- [ ] **Aparte R2-token overwegen** met schrijfrechten op alleen deze bucket. De
      repo is publiek; fork-PR's krijgen geen secrets, maar iedereen die naar
      `main` kan pushen kan ze via een workflow uitlezen.

## Later, niet urgent

Op volgorde van verwachte opbrengst:

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
  (`reisplan-aggregator-herstart.service` en `.timer`) en de gewijzigde starttijd van de verversing
  (maandag 00:00 lokaal; het spiekbriefje zegt nog 04:30 UTC).
