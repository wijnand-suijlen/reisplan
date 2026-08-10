# Diensten- en key-inventaris (opruimlijst)

*Doel: alles wat dit project buiten de eigen machines gebruikt, met de URL waar je
het beheert of opzegt. Geen geheime waarden in dit bestand — de keys zelf staan
alleen in `.env` (laptop en VM, beide buiten git) en in de GitHub-secrets.*

## Accounts met iets te verwijderen

| Dienst | Wat er van ons staat | Beheer-URL | Kosten |
|---|---|---|---|
| **GitHub** | repo `wijnand-suijlen/reisplan`; Actions-workflows (dagelijkse ETL, Pages); 4 secrets (`R2_*`); Pages-site | https://github.com/wijnand-suijlen/reisplan (Settings → Secrets / Pages / delete repo) | €0 |
| **Cloudflare** | R2-bucket `reisplan` (snapshot, segments, randen, dataset); publieke toegang via `https://pub-2369cd93470e40528dc3aab9ab7fd5e7.r2.dev`; 1 R2-API-token (Object Read & Write) | https://dash.cloudflare.com → R2 (bucket + Manage R2 API Tokens) | €0 (free tier; creditcard geregistreerd) |
| **Google Cloud** | project met de **e2-micro-VM** (aggregator + collector, systemd-services `reisplan-aggregator` en `reisplan-statisch`); budgetalarm | https://console.cloud.google.com → Compute Engine (VM verwijderen) en Billing (account sluiten) | €0 (always-free; hooguit centen egress) |
| **opentransportdata.swiss** (Zwitserland) | account + **4 API-keys**: GTFS-RT (`CH_API_KEY`), GTFS-SA (`CH_SA_KEY`), Train Formation (`CH_TRAINFORM_KEY`, nog ongebruikt, voor fase 2), OJP Fare (`CH_FARE_KEY`, idem) | https://api-manager.opentransportdata.swiss/ | €0 |
| **Belgian Mobility / NMBS** | account + subscription-key (`BE_API_KEY`, header `bmc-partner-key`) | https://data.belgianmobility.io/ (Developer Portal → Profile) | €0 |

## Waar de keys fysiek staan (bij opruimen ook legen)

- Laptop: `~/Documents/src/reisplan/.env`
- VM: `~/reisplan/.env` (op de e2-micro)
- GitHub: repo → Settings → Secrets and variables → Actions (`R2_ENDPOINT`,
  `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`)

## Gebruikt zónder account (niets op te zeggen)

- OVapi / gtfs.ovapi.nl (NL statisch + realtime; nette User-Agent verplicht)
- transport.data.gouv.fr + proxy (FR statisch + realtime)
- gtfs.de (DE-dienstregelingen), gtfs.irail.be (BE-mirror)
- Geofabrik (OSM-extracten, alleen tijdens geometrie-builds)
- tile.openstreetmap.org (basemap van de viewer), unpkg.com (MapLibre-CDN)

## Nog niet aangemaakt (staat op TODO.md; dus ook niets op te ruimen)

- DB API Marketplace (developers.deutschebahn.com) — voor DE op de kaart
- DELFI / opendata-oepnv.de — DE-dienstregeling verder dan 30 dagen
- NS API-portaal (apiportal.ns.nl) — fase 1/2 (prijzen, storingen, materieel)
- NDOV Loket (reisinformatiegroep.nl/ndovloket) — fase 2/3

## Volgorde bij volledig opruimen

1. VM verwijderen (GCP) → stopt de aggregator/collector.
2. GitHub-workflows uitzetten of repo verwijderen → stopt de nachtelijke ETL en Pages.
3. R2-bucket legen en verwijderen, API-token intrekken (Cloudflare).
4. API-keys intrekken bij opentransportdata.swiss en belgianmobility.io; accounts sluiten.
5. GCP-billingaccount en Cloudflare-account sluiten; lokale `.env` weggooien.
