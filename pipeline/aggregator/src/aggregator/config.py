"""Bronnenconfiguratie. Landen gaan 'aan' zodra hun key in .env staat — geen codewijziging."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo-root
DATA = ROOT / "data"
RT_ARCHIEF = DATA / "rt-archief"
MERGED_DB = DATA / "merged" / "merged.duckdb"
WEB_DATA = ROOT / "web" / "vertragingskaart" / "data"

USER_AGENT = "reisplan-aggregator/0.1 (hobbyproject; wijnand.suijlen@proton.me)"


def laad_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for regel in env.read_text().splitlines():
            regel = regel.strip()
            if regel and not regel.startswith("#") and "=" in regel:
                k, v = regel.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


@dataclass
class SourceConfig:
    land: str
    feed_prefix: str          # prefix van stop_ids in merged.duckdb ("nl", "fr", …)
    tu_url: str | None        # GTFS-RT trip updates
    alerts_url: str | None    # GTFS-RT service alerts
    interval_s: int
    headers: dict             # voor de trip-updates-URL
    enabled: bool
    status: str               # "ok"/"uit"/"geen-bron" voor het dekkingspaneel
    alerts_headers: dict | None = None  # CH geeft per API een eigen key; None = zelfde als headers


def bronnen() -> list[SourceConfig]:
    laad_env()
    ch_key = os.environ.get("CH_API_KEY")
    be_key = os.environ.get("BE_API_KEY")
    return [
        SourceConfig(
            land="nl", feed_prefix="nl",
            tu_url="https://gtfs.ovapi.nl/nl/trainUpdates.pb",  # tripUpdates.pb = bus/tram; treinen zitten hier
            alerts_url="https://gtfs.ovapi.nl/nl/alerts.pb",
            interval_s=60, headers={"User-Agent": USER_AGENT}, enabled=True, status="ok",
        ),
        SourceConfig(
            land="fr", feed_prefix="fr",
            tu_url="https://proxy.transport.data.gouv.fr/resource/sncf-gtfs-rt-trip-updates",
            alerts_url="https://proxy.transport.data.gouv.fr/resource/sncf-gtfs-rt-service-alerts",
            interval_s=120, headers={"User-Agent": USER_AGENT}, enabled=True, status="ok",
        ),
        SourceConfig(
            land="ch", feed_prefix="ch",
            tu_url=os.environ.get("CH_TU_URL", "https://api.opentransportdata.swiss/la/gtfs-rt"),
            alerts_url=os.environ.get("CH_SA_URL", "https://api.opentransportdata.swiss/la/gtfs-sa")
            if os.environ.get("CH_SA_KEY") else None,
            interval_s=90,
            headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {ch_key}"} if ch_key else {},
            alerts_headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {os.environ.get('CH_SA_KEY')}"}
            if os.environ.get("CH_SA_KEY") else None,
            enabled=bool(ch_key), status="ok" if ch_key else "uit",
        ),
        SourceConfig(
            land="be", feed_prefix="be",
            tu_url=os.environ.get("BE_TU_URL"),  # invullen na registratie belgianmobility
            alerts_url=os.environ.get("BE_ALERTS_URL"),
            interval_s=60,
            headers={"User-Agent": USER_AGENT, "Ocp-Apim-Subscription-Key": be_key} if be_key else {},
            enabled=bool(be_key and os.environ.get("BE_TU_URL")), status="ok" if be_key else "uit",
        ),
        SourceConfig(
            land="de", feed_prefix="de_rv",
            tu_url=None, alerts_url=None, interval_s=0, headers={},
            enabled=False, status="geen-bron",
        ),
    ]
