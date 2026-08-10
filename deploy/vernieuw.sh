#!/usr/bin/env bash
# Wekelijkse verversing van de statische data (aangeroepen door reisplan-statisch.service).
# Staat in het repo zodat gedragsverbeteringen via git pull meekomen zonder unit-herinstallatie.
set -euo pipefail
cd "$(dirname "$0")/.."

export REISPLAN_DUCKDB_MEM="${REISPLAN_DUCKDB_MEM:-600MB}"
export REISPLAN_SLA_DUPDETECTIE_OVER=1   # duplicaatdetectie is spike-rapportage; niet nodig voor de aggregator
export PATH="$HOME/.local/bin:$PATH"

git pull --ff-only
uv sync --all-packages
uv run spike/s0_download.py
uv run spike/s2_filter_rail.py
uv run spike/s3_merge_dedup.py
uv run maak-segmenten
# EVA station map for the DE poller; non-fatal so a DB API hiccup never blocks the refresh
if ! uv run spike/s10_station_eva_map.py; then
  echo "WARN: s10 EVA station map failed; aggregator keeps the previous eva_stations.json" >&2
fi
