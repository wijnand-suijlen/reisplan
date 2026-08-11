# TODO — registraties en keys aanvragen

*Onderzocht 2026-08-09. Alles hieronder is gratis en toegankelijk voor privépersonen; nergens een verbod op niet-commercieel hobbygebruik. Volgorde = urgentie voor het project. Tip: sla bij elke registratie de voorwaardentekst op die je accepteert (vooral bij NS, waar die alleen achter login zichtbaar is).*

---

## 1. Zwitserland — opentransportdata.swiss — ✅ GEDAAN (2026-08-09, CH live op de kaart; Train Formation- en OJP Fare-keys liggen klaar in .env voor fase 2)

- [ ] Account aanmaken op **https://api-manager.opentransportdata.swiss/** (e-mail, naam, wachtwoord min. 12 tekens met cijfer + speciaal teken)
- [ ] Daarna: "application" aanmaken → API kiezen → "Access with this plan" → token. **Max. 1 token per API**; wij hebben er straks meerdere nodig (GTFS-RT; later OJP, Train Formation, OJP Fare)

**Voorwaarden** (eigen platform-ToU, geen CC-licentie): data mag je verwerken, combineren en publiceren, ook commercieel. Bijzondere punten:
- Bronvermelding verplicht: de URL *opentransportdata.swiss* noemen in publicaties; bij meerdere bronnen volstaat één vermelding in de bronnenlijst.
- Bewerkte data publiceer je onder je **eigen naam** (niet alsof het van SBB komt) en moet je **even vaak actualiseren als de bron**.
- Harde rate limits per key: GTFS-RT **5 req/min**; OJP/Fare/Train Formation 50 req/min en 20.000 req/dag. Herhaald overschrijden ⇒ blokkade of betaald contract.
- Elke API-call vereist `Authorization: Bearer <key>` **én een User-Agent-header**.
- Geen aansprakelijkheid/garantie; misbruik ⇒ directe ban.
- Losse GTFS-bestandsdownloads blijven registratievrij — de key is alleen voor de API's.

## 2. België — data.belgianmobility.io — ✅ GEDAAN (2026-08-09, BE live op de kaart)

Goed nieuws: de oude route met ondertekende NMBS-licentie is vervangen door een self-service portaal van de Belgian Mobility Company (NMBS + De Lijn + STIB + TEC in één).

- [ ] Sign-up op **https://data.belgianmobility.io/** (Developer Portal) → zelf een "Standard subscription key" aanmaken (12.000 req/dag). Geen handtekening, geen wachttijd.
- [ ] Weetje: er is ook een **anonieme tier zonder account** (100 req/dag, 10 req/min) — genoeg om vast te testen voordat de key er is.

**Voorwaarden**: CC BY 4.0, hergebruik incl. commercieel toegestaan. Bijzondere punten:
- Verplichte attributievorm: *"Source: NMBS/SNCB – Open Data – [datum dataset-update]"*; bij bewerking: *"Contains data originally published by NMBS/SNCB, modified by [naam]"*.
- API-key is strikt persoonlijk; delen ⇒ onmiddellijke opschorting.
- Geen SLA op de gratis tiers; geen garantie op juistheid/beschikbaarheid.

## 3. Duitsland — DB API Marketplace — ✅ GEDAAN (2026-08-10; Client ID/key + X.509-cert in `~/.config/reisplan/db-api/`; Timetables API getest: 200 OK)

- [ ] DB-klantaccount (BahnID) aanmaken op **https://developers.deutschebahn.com/** → application aanmaken (Client ID + Secret goed bewaren) → abonneren op **Timetables API, "Nutzungsplan Free"** (60 req/min)
- Formeel is er een "Freischaltung" door DB; vermoedelijk automatisch, wachttijd onbekend.

**Voorwaarden**: de Timetables-*data* is CC BY 4.0 (attributie: Deutsche Bahn AG). De platform-ToU daarbovenop:
- Client Secret niet delen; niets doen dat het platform verstoort; DB mag limieten eenzijdig aanpassen.
- Beide partijen kunnen per direct opzeggen; DB kan bij schending blokkeren.
- Aandachtspunt: de ToU bevatten een vertrouwelijkheidsclausule die schuurt met de CC BY-licentie op de dataset — voor ons gebruik (data verwerken in eigen tool) geen praktisch probleem.
- De exacte per-API-voorwaarden die je bij het abonneren accepteert zitten achter login — even meelezen bij het aanvinken.

## 4. Duitsland — DELFI via opendata-oepnv.de — ✅ GEDAAN (2026-08-10; login in `~/.config/reisplan/delfi/credentials`; het GTFS-bestand zelf blijkt óók zonder login downloadbaar)

- [ ] Registreren op **https://www.opendata-oepnv.de/ht/de/standards/registrierung** (alleen Duitstalig; aanhef, naam, e-mail, wachtwoord; organisatie/project **optioneel** — privépersoon is prima). Vink de datasetgroep "Deutschlandweite Sollfahrplandaten (GTFS)" aan.
- Let op checkbox: je geeft DELFI e.V. toestemming je accountgegevens voor contact te gebruiken (EU-verordening vereist die registratie).

**Voorwaarden**: data CC BY 4.0, attributie **DELFI e.V.**; commercieel gebruik en doorlevering toegestaan. Platform-regels: geen overmatige belasting van de infrastructuur (wekelijkse bulkdownload is precies de bedoeling), merken niet gebruiken, toegang kan bij overlast worden ingetrokken, geen garanties. Publicatie: wekelijks op maandag, volledig dienstregelingjaar per levering.

## 5. Nederland — NS API-portaal — ✅ GEDAAN (2026-08-11, Reisinformatie-API-key in `~/.config/reisplan/ns-api/` en .env als `NS_API_KEY`; disruptions-endpoint live op de vertragingskaart. SNCF-key kwam dezelfde dag binnen: `~/.config/reisplan/sncf-api/`, .env `SNCF_API_KEY`)

- [ ] Account op **https://apiportal.ns.nl/** → registreer als **"Externe bezoeker"** → bevestigingsmail (paar minuten) → dan pas wordt de API-catalogus zichtbaar
- [ ] Subscription nemen op (t.z.t.): Reisinformatie API (incl. prijs-endpoint), Virtual Train API, Stations-API — key verschijnt op je profielpagina, mogelijk na goedkeuring
- [ ] **Sla bij het subscriben de gebruikersvoorwaarden op** — die zijn nergens publiek te lezen

**Wat er publiek over bekend is**: gratis, met limieten per product die NS eenzijdig kan aanpassen (indicatie: orde 100 calls/min op de Reisinformatie API); de API is expliciet bedoeld voor privé-/niet-commercieel gebruik (dat zijn wij); ga "verantwoordelijk om met de geboden capaciteit"; het NS-logo mag niet in eigen apps gebruikt worden.

## 6. Nederland — NDOV Loket (voor fase 2/3: ruwe spoorfeeds; kan wachten)

- [ ] Aanmelden via **https://reisinformatiegroep.nl/ndovloket** → "OV Datacollecties" → e-mail + wachtwoord + checkbox licentievoorwaarden (de oude flow met ondertekend terugsturen lijkt vervangen door digitale acceptatie; als er toch een overeenkomst per mail komt: gewoon tekenen, zie hieronder)
- Interessante collecties voor ons: IFF (treindienstregeling), RitInfo (actuele passeertijden), NS Treinposities, Verstoringsinformatie spoor, uitstapzijde-informatie

**Voorwaarden** (volledige tekst: reisinformatiegroep.nl/ndovloket/static/Licentievoorwaarden.pdf): **CC0** — de zorgeloosste van allemaal. Geen naamsvermeldingsplicht, doorlevering expliciet toegestaan, commercieel gebruik vrij. Bijzondere punten: het loket sluit elke aansprakelijkheid uit; "spoorbrongegevens zijn niet geschikt voor het interpreteren van OV-prestaties" (geen prestatie-analyses op baseren — voor onze punctualiteitsstatistiek gebruiken we toch rijdendetreinen.nl); SLA van het loket zelf: realtime doorlevering <3 s, ≥99% beschikbaar.

---

## Samenvatting attributieplichten (voor als de app/kaart iets publiceert)

| Bron | Vermelding |
|---|---|
| opentransportdata.swiss | URL "opentransportdata.swiss" als bron |
| Belgian Mobility | "Source: NMBS/SNCB – Open Data – [datum]" |
| DB Timetables | CC BY: Deutsche Bahn AG |
| DELFI | CC BY: DELFI e.V. |
| NS API | voorwaarden achter login — check bij registratie; logo-verbod |
| NDOV | geen (CC0) |
| OVapi (geen registratie) | informeel: nette User-Agent, If-Modified-Since, geen impersonatie van vervoerders |

*Niet geverifieerd (achter login): exacte NS-voorwaarden en -quota; DB per-API-voorwaarden bij het abonneren; of DB-"Freischaltung" en NS-subscriptions automatisch goedgekeurd worden. De onderzoeksdetails met bron-URLs staan in de sessie-rapporten; kernpunten zijn hierboven verwerkt.*
