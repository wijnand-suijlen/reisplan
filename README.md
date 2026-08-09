# Reisplan

Internationale treinreisplanner voor NL/BE/FR/DE/CH. Zie `CLAUDE.md` (projectstatus) en `PLAN.md` (ontwerp).

- `spike/` — fase 0: wegwerp-meetcode voor de datapijplijn-spike (resultaten: `docs/SPIKE-RESULTATEN.md`)
- `pipeline/aggregator/` — fase 0.5: realtime-aggregator (vertragingskaart + punctualiteitscollector)
- `web/vertragingskaart/` — statische MapLibre-viewer voor de vertragingskaart
- `docs/` — databronnen-inventaris, snapshot-schema, spike-resultaten
- `data/` — (gitignored) gedownloade feeds, tussenresultaten, realtime-archief
- `android/` — gereserveerd voor de app (fase 1)

Draaien: `uv sync`, daarna bv. `uv run --directory spike python s0_download.py`.
