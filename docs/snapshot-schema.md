# Snapshot-schema vertragingskaart (v1)

Contract tussen aggregator, webviewer en (later) de Android-app. De geometrie zit **niet**
in het snapshot maar in het statische `segments.geojson` (gegenereerd door `maak-segmenten`);
het snapshot refereert segment-id's.

## segments.geojson

FeatureCollection; per feature: `id` = `"<cluster_a>|<cluster_b>"` (gesorteerd clusterpaar),
properties `van`/`naar` (stationsnamen), geometrie een LineString (v1: rechte lijn).

## snapshot.json

```json
{
  "v": 1,
  "t": "2026-08-09T18:32:00Z",
  "dekking": {
    "nl": {"status": "ok", "age_s": 41},
    "fr": {"status": "ok", "age_s": 95},
    "be": {"status": "uit"},
    "ch": {"status": "uit"},
    "de": {"status": "geen-bron"}
  },
  "seg": [["uic:8400058|uic:8400319", 3, 720, 4]],
  "inc": [{"land": "be", "cause": "STRIKE", "effect": "REDUCED_SERVICE",
            "txt": "…", "pos": [4.32, 50.85], "cluster": "uic:8814001"}]
}
```

- `dekking.status`: `ok` (met `age_s` = seconden sinds laatste geslaagde poll), `wacht`
  (aan maar nog geen geslaagde poll), `uit` (bron uitgeschakeld, key ontbreekt),
  `geen-bron` (land heeft geen bruikbare feed — DE in v1).
- `seg`-tuple: `[segment_id, kleurklasse, p90_delta_s, n_treinen]` over een venster van
  30 minuten. Kleurklasse: **0 groen (p90 ≤ 0 s), 1 geel (≤ 120 s), 2 oranje (≤ 600 s),
  3 rood (> 600 s)** — dit is *opgelopen* vertraging op het segment (delta), niet absolute
  vertraging. Segmenten zonder waarnemingen ontbreken; de client rendert die grijs
  ("geen data") — eerlijker dan groen, gezien de dekkingsverschillen per land.
- `inc`: alleen incidenten met een bepaalbare positie; `cause`/`effect` zijn de
  GTFS-RT-enums (`UNKNOWN_CAUSE` … `MEDICAL_EMERGENCY`).
- Delta's komen uitsluitend uit paren van **expliciete** StopTimeUpdates (GTFS-RT
  propageert delays impliciet; impliciete paren zijn per definitie 0).

Gemeten grootte: zie logregel "snapshot: … bytes" van de aggregator.
