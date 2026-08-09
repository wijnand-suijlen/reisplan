#!/usr/bin/env bash
# Eenmalige inrichting van een (GCP e2-micro) VM voor de reisplan-aggregator.
# Gebruik:  bash deploy/setup-vm.sh   (vanuit een verse clone van het repo, als gewone gebruiker)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "== 1. Basispakketten =="
sudo apt-get update -q
sudo apt-get install -y -q git curl

echo "== 2. Swap (e2-micro heeft 1 GB RAM; de merge-stap heeft meer nodig) =="
if ! sudo swapon --show | grep -q swapfile; then
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "== 3. uv installeren =="
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "== 4. Python-omgeving =="
cd "$REPO_DIR"
uv sync --all-packages

echo "== 5. .env controleren =="
if [ ! -f "$REPO_DIR/.env" ]; then
  echo "!! Maak eerst $REPO_DIR/.env aan met de API-keys (BE_*, CH_*) en draai dit script opnieuw."
  exit 1
fi

echo "== 6. Statische data bouwen (download -> filter -> merge; duurt op een e2-micro even) =="
uv run spike/s0_download.py
uv run spike/s2_filter_rail.py
uv run spike/s3_merge_dedup.py
uv run maak-segmenten

echo "== 7. systemd-services installeren =="
sed "s|@REPO@|$REPO_DIR|g; s|@USER@|$USER|g; s|@UV@|$(command -v uv)|g" \
  deploy/aggregator.service | sudo tee /etc/systemd/system/reisplan-aggregator.service >/dev/null
sed "s|@REPO@|$REPO_DIR|g; s|@USER@|$USER|g; s|@UV@|$(command -v uv)|g" \
  deploy/statisch-vernieuwen.service | sudo tee /etc/systemd/system/reisplan-statisch.service >/dev/null
sudo cp deploy/statisch-vernieuwen.timer /etc/systemd/system/reisplan-statisch.timer
sudo systemctl daemon-reload
sudo systemctl enable --now reisplan-aggregator.service reisplan-statisch.timer

echo "== Klaar. Status: =="
systemctl --no-pager status reisplan-aggregator.service | head -5
echo "Logs volgen met: journalctl -fu reisplan-aggregator"
