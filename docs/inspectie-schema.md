# Inspectie-artefacten (v1)

Contract tussen de aggregator (`pipeline/aggregator/src/aggregator/inspection.py`)
en de inspectiepagina (`web/vertragingskaart/inspectie.html`). Doel: de ruwe
per-trein-data achter de vertragingskaart inzichtelijk maken om ogenschijnlijke
tegenstrijdigheden op de kaart te kunnen herleiden.

Elke **300 s** bouwt de aggregator uit de laatste **24 uur** observaties drie
artefacten en uploadt ze naar R2 onder `inspect/` (gzip, `Cache-Control:
max-age=60`); lokaal staan kopieën in `web/vertragingskaart/data/inspect/`.
`trains.json` en `details.json` komen uit `stop_obs2` (observatielog, absolute
vertraging per stationscluster), `edges.json` uit `seg_obs` (opgelopen delta
per baanvak-passage). De pagina filtert de vensters (30 min / 4 u / 24 u) zelf
op `last_ts`, dus één 24-uursartefact bedient alle drie.

**Let op bij het duiden van "tegenstrijdigheden"**: de kaart kleurt op de p90
van de *opgelopen* vertraging per baanvak (`seg_obs`, delta per segmentpassage,
venster 30 min); deze artefacten tonen *absolute* vertraging per trein
(`stop_obs2`). Een trein met 40 min absolute vertraging die constant 40 min
achter rijdt, loopt niets meer op en kleurt het baanvak dus niet rood.

## inspect/trains.json

Compacte array-rijen met `cols`-header; één rij per (country, trip_id,
service_date):

```json
{
  "v": 1,
  "built_at": "2026-08-13T07:35:00Z",
  "window_s": 86400,
  "cols": ["country", "trip_id", "service_date", "train_number", "route",
           "origin", "destination", "sched_dep", "sched_arr",
           "delay_s", "last_stop", "first_ts", "last_ts", "n_obs", "sched_known"],
  "rows": [
    ["nl", "366476450", "20260811", "8077", "RS18",
     "Kerkrade Centrum", "Emmen", "06:59:00", "08:15:00",
     120, "Nijmegen", 1786512900, 1786514720, 14, true],
    ["de", "ICE 228", "20260813", "ICE 228", null,
     "Frankfurt(Main)Hbf", "Köln Hbf", null, null,
     300, "Köln Hbf", 1786513000, 1786514000, 3, false]
  ]
}
```

- `trip_id`: de **ruwe RT-id** uit de feed (in merged.duckdb geprefixt als
  `<feed>:<trip_id>`); voor DE het IRIS-label (`"ICE 228"`, `"iris:…"`).
- `train_number`: `trips.trip_short_name` → `trip_headsign` (FR zet het nummer
  daar) → `routes.route_short_name` → ruwe trip_id.
- `origin`/`destination`, `sched_dep`/`sched_arr`: eerste/laatste geplande stop
  uit `stop_times` (opeenvolgende stops in hetzelfde cluster samengevouwen).
  Tijden zijn **ruwe GTFS-strings in feed-lokale tijd** (kunnen boven 24:00
  uitkomen); nooit converteren. Bij `sched_known=false` zijn origin/destination
  de eerste/laatste *waargenomen* clusternaam en zijn de tijden `null`.
- `delay_s`: absolute vertraging (s) van de **jongste** observatie in het
  venster; `last_stop` is de clusternaam van diezelfde observatie. Negatief =
  te vroeg.
- `first_ts`/`last_ts` (unix-s) en `n_obs`: vensterstatistiek; de client
  filtert de periode op `last_ts`.
- `sched_known=false`: trip niet koppelbaar aan de statische GTFS (heel DE;
  incidenteel elders bij afwijkende id-formaten — precies wat je wilt zien in
  een debugtool).

Het **percentiel** in de UI staat bewust niet in het artefact: het is de
inclusieve rang van `delay_s` binnen alle treinen in het *gekozen venster* en
wordt client-side berekend.

## inspect/details.json

Hele dienst per trein, door de pagina pas geladen bij de eerste rijklik.
Sleutel: `"<country>|<trip_id>|<service_date>"` (trip_ids bevatten geen `|`).

```json
{
  "v": 1, "built_at": "2026-08-13T07:35:00Z", "window_s": 86400,
  "trains": {
    "nl|366476450|20260811": {
      "sched_known": true,
      "stops": [["Kerkrade Centrum", "06:59:00", "07:01:00", 120],
                ["Landgraaf", "07:06:00", "07:06:00", null]]
    },
    "de|ICE 228|20260813": {
      "sched_known": false,
      "stops": [["Frankfurt(Main)Hbf", null, null, 180],
                ["Köln Hbf", null, null, 300]]
    }
  }
}
```

- Per stop: `[stationsnaam, geplande_aankomst, gepland_vertrek, delay_s|null]`;
  `null`-vertraging = geen observatie voor dat cluster in het venster.
- Waargenomen clusters die **niet** in de planning voorkomen, staan achteraan
  met `null`-tijden (omleiding of mismatch in de clustering — bewust zichtbaar).
- `sched_known=false`: stops zijn de waargenomen clusters op volgorde van
  waarneming.

## inspect/edges.json

De koppeling baanvak ↔ treinen, voor het filter `inspectie.html?edge=<rand-id>`
(een klik op een baanvak op de kaart opent die URL, met `&label=` voor de
leesbare naam). Per getekende rand de treinen die er in het venster overheen
reden:

```json
{
  "v": 1, "built_at": "2026-08-13T07:35:00Z", "window_s": 86400,
  "edges": {
    "E1025057532-4335755650": [[412, 180, 1786514301], [87, 0, 1786514100]]
  }
}
```

- Per passage: `[rij-index in trains.json, delta_s, ts]`, aflopend op delta.
  `delta_s` is de **opgelopen** vertraging van de laatste passage van die trein
  over dit baanvak (`seg_obs`) — de getallen achter de kaartkleur, anders dan de
  absolute vertraging in de tabel. In de UI is dit de kolom "Δ baanvak".
- De rij-indices verwijzen naar dezelfde build; de pagina vergelijkt `built_at`
  van beide artefacten en haalt ze bij een mismatch opnieuw op.
- `seg_obs` heeft geen dienstdatum; een trip_id die binnen het venster op twee
  dienstdagen rijdt, wordt toegeschreven aan de rij waarvan het
  observatie-interval het dichtst bij de passage ligt.

## Kanttekeningen

- `stop_obs2` logt alleen **wijzigingen**; een trein waarvan de vertraging lang
  niet verandert, valt uit korte vensters (voetnoot op de pagina).
- Gemeten grootte: zie logregel `inspection: … trains, … detail stops, … bytes`
  van de aggregator (orde: ~1 MB + ~3 MB raw, ~85% kleiner over de lijn door
  gzip).
- De histogramkleuren op de pagina volgen de kleurklassen van de kaart
  (`snapshot.py`): groen < 1 min, geel ≤ 2 min, oranje ≤ 10 min, rood > 10 min.
