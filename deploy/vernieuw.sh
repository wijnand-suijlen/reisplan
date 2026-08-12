#!/usr/bin/env bash
# Wekelijkse verversing van de statische data (aangeroepen door reisplan-statisch.service).
# Staat in het repo zodat gedragsverbeteringen via git pull meekomen zonder unit-herinstallatie.
#
# Fasen (de service draait ze apart, met een aggregator-stop rond de merge: de
# aggregator houdt merged.duckdb permanent read-only open — trip-lookups voor de
# blokkadedetectie — en dat gedeelde leesslot blokkeert DuckDB's schrijfslot):
#   voorbereiden  git pull, uv sync, feeds downloaden + filteren (aggregator draait door)
#   merge         s3-merge + maak-segmenten schrijven merged.duckdb (aggregator gestopt)
#   na            s10 EVA-stationskaart (read-only; aggregator draait weer)
# Zonder argument draaien alle fasen na elkaar (setup-vm.sh, lokaal gebruik).
set -euo pipefail
cd "$(dirname "$0")/.."

export REISPLAN_DUCKDB_MEM="${REISPLAN_DUCKDB_MEM:-600MB}"
export REISPLAN_SLA_DUPDETECTIE_OVER=1   # duplicaatdetectie is spike-rapportage; niet nodig voor de aggregator
export PATH="$HOME/.local/bin:$PATH"

fase="${1:-alles}"

if [ "$fase" = voorbereiden ] || [ "$fase" = alles ]; then
  git pull --ff-only
  uv sync --all-packages
  uv run spike/s0_download.py
  uv run spike/s2_filter_rail.py
fi

if [ "$fase" = merge ] || [ "$fase" = alles ]; then
  uv run spike/s3_merge_dedup.py
  uv run maak-segmenten
fi

if [ "$fase" = na ] || [ "$fase" = alles ]; then
  # EVA station map for the DE poller; non-fatal so a DB API hiccup never blocks the refresh
  if ! uv run spike/s10_station_eva_map.py; then
    echo "WARN: s10 EVA station map failed; aggregator keeps the previous eva_stations.json" >&2
  fi
fi
