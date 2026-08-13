"use strict";

const KLEUREN = ["#0ca30c", "#fab219", "#ec835a", "#d03b3b"]; // klasse 0-3 (gevalideerd statuspalet)

// op smalle schermen neemt de legenda het halve beeld in beslag: start ingeklapt
if (matchMedia("(max-width: 640px)").matches) {
  document.getElementById("legenda-details").removeAttribute("open");
}
const GEEN_DATA = "#9a9a97";
// werkzaamheden-ernst: closed = gepland buiten dienst, reduced = aangepaste dienst,
// intl = alleen internationaal verkeer gestremd (binnenlands rijdt gewoon)
const WERK_KLEUR = { closed: "#d03b3b", reduced: "#e8940a", intl: "#2456c9" };
const WERK_LABEL = {
  closed: "🚧 werkzaamheden — gepland buiten dienst",
  reduced: "🚧 werkzaamheden — aangepaste dienst",
  intl: "🌍 internationale verbinding gestremd",
};
const WERK_RANG = { closed: 3, intl: 2, reduced: 1 };
const CAUSE_ICOON = {
  ACCIDENT: "💥", TECHNICAL_PROBLEM: "🔧", CONSTRUCTION: "🚧", MAINTENANCE: "🚧",
  STRIKE: "✊", WEATHER: "🌧️", MEDICAL_EMERGENCY: "🚑", POLICE_ACTIVITY: "🚓",
  DEMONSTRATION: "📢", HOLIDAY: "📅", UNKNOWN_CAUSE: "⚠️", OTHER_CAUSE: "⚠️",
};
const LAND_NAAM = { nl: "NL", be: "BE", fr: "FR", de: "DE", ch: "CH" };
// Databron: ?data=<url> wint altijd; op GitHub Pages standaard de R2-bucket; lokaal "data/".
const R2_BASE = "https://pub-2369cd93470e40528dc3aab9ab7fd5e7.r2.dev/";
const DATA_BASE = new URLSearchParams(location.search).get("data")
  || (location.hostname.endsWith("github.io") ? R2_BASE : "data/");

const kaart = new maplibregl.Map({
  container: "kaart",
  center: [5.5, 49.5],
  zoom: 5.2,
  style: {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [
      { id: "osm", type: "raster", source: "osm" },
      // basemap dempen zodat de datakleuren dominant zijn
      { id: "was", type: "background", paint: { "background-color": "#fcfcfb", "background-opacity": 0.55 } },
    ],
  },
});

let bekendeSegmenten = new Set();
let werkInfo = new Map(); // rand-id -> {src, until, txt} uit snap.wrk

kaart.on("load", async () => {
  kaart.addSource("segmenten", { type: "geojson", data: `${DATA_BASE}segments.geojson`, promoteId: "id" });

  // witte casing = scheiding van de drukke basemap
  kaart.addLayer({
    id: "seg-casing", type: "line", source: "segmenten",
    paint: { "line-color": "#fcfcfb", "line-width": 4.5, "line-opacity": 0.9 },
  });
  kaart.addLayer({
    id: "seg", type: "line", source: "segmenten",
    paint: {
      "line-color": ["case",
        ["==", ["feature-state", "k"], 0], KLEUREN[0],
        ["==", ["feature-state", "k"], 1], KLEUREN[1],
        ["==", ["feature-state", "k"], 2], KLEUREN[2],
        ["==", ["feature-state", "k"], 3], KLEUREN[3],
        GEEN_DATA],
      "line-width": ["case", [">=", ["coalesce", ["feature-state", "k"], -1], 1], 3, 2],
      "line-opacity": ["case", ["==", ["coalesce", ["feature-state", "k"], -1], -1], 0.45, 0.95],
    },
  });
  // werkzaamheden: puntjeslijn, kleur naar ernst (onder de blok-laag: de-facto wint)
  kaart.addLayer({
    id: "seg-werk", type: "line", source: "segmenten",
    paint: {
      "line-color": ["match", ["coalesce", ["feature-state", "werk"], ""],
        "closed", WERK_KLEUR.closed, "intl", WERK_KLEUR.intl, WERK_KLEUR.reduced],
      "line-width": 4.5,
      "line-dasharray": [0.8, 1.2],
      "line-opacity": ["case", ["!=", ["coalesce", ["feature-state", "werk"], ""], ""], 1, 0],
    },
  });
  // versperde baanvakken: rode stippellijn eroverheen (à la wegafsluitingen)
  kaart.addLayer({
    id: "seg-blok", type: "line", source: "segmenten",
    paint: {
      "line-color": KLEUREN[3],
      "line-width": 3.5,
      "line-dasharray": [1.4, 1.6],
      "line-opacity": ["case", ["boolean", ["feature-state", "blok"], false], 1, 0],
    },
  });
  koppelTooltip();
  await ververs();
  setInterval(ververs, 60_000);
});

async function ververs() {
  let snap;
  try {
    snap = await (await fetch(`${DATA_BASE}snapshot.json?t=${Date.now()}`)).json();
  } catch {
    document.getElementById("snapshot-leeftijd").textContent = "snapshot niet bereikbaar";
    return;
  }

  const nieuw = new Set();
  const blok = new Set(snap.blk || []);
  werkInfo = new Map();
  for (const [src, sev, until, txt, randen] of snap.wrk || []) {
    for (const id of randen) { // bij overlap wint de zwaarste categorie
      const oud = werkInfo.get(id);
      if (!oud || (WERK_RANG[sev] || 0) > (WERK_RANG[oud.sev] || 0)) {
        werkInfo.set(id, { src, sev, until, txt });
      }
    }
  }
  for (const [id, k, p90, n] of snap.seg) {
    kaart.setFeatureState({ source: "segmenten", id },
      { k, p90, n, blok: blok.has(id), werk: werkInfo.get(id)?.sev ?? "" });
    nieuw.add(id);
  }
  for (const id of blok) {
    if (!nieuw.has(id)) { // versperd zónder kleurwaarnemingen — het normale geval
      kaart.setFeatureState({ source: "segmenten", id }, { blok: true });
      nieuw.add(id);
    }
  }
  for (const [id, w] of werkInfo) {
    if (!nieuw.has(id)) { // buiten dienst zónder waarnemingen — het normale geval
      kaart.setFeatureState({ source: "segmenten", id }, { werk: w.sev });
      nieuw.add(id);
    }
  }
  for (const id of bekendeSegmenten) {
    if (!nieuw.has(id)) kaart.removeFeatureState({ source: "segmenten", id });
  }
  bekendeSegmenten = nieuw;

  toonIncidenten(snap.inc);

  const leeftijd = Math.round((Date.now() - Date.parse(snap.t)) / 1000);
  document.getElementById("snapshot-leeftijd").textContent =
    `${snap.seg.length} baanvakken met waarnemingen · snapshot ${leeftijd}s oud`;

  document.getElementById("dekking").innerHTML = Object.entries(snap.dekking)
    .map(([land, d]) => {
      const st = (d.status === "ok" || d.status === "deels") && d.age_s > 300 ? "oud" : d.status;
      const label = { ok: "live", deels: "live (knooppunten)", wacht: "wacht", uit: "uit (key)", "geen-bron": "geen bron", oud: "verouderd" }[st] || st;
      return `<span class="land st-${st.replace(" ", "-")}"><span class="stip"></span>${LAND_NAAM[land] || land} ${label}</span>`;
    })
    .join("");
}

let incidentMarkers = [];

function toonIncidenten(incidenten) {
  // DOM-markers i.p.v. symbol-layer: emoji renderen onafhankelijk van kaart-glyphs
  for (const m of incidentMarkers) m.remove();
  incidentMarkers = incidenten.map((i) => {
    const el = document.createElement("span");
    el.className = "incident";
    el.textContent = CAUSE_ICOON[i.cause] || "⚠️";
    const tip = document.getElementById("tooltip");
    el.addEventListener("mouseenter", (e) => {
      tip.innerHTML = `<div class="kop">${el.textContent} ${i.cause} (${i.land.toUpperCase()})</div><span class="sub">${i.txt || ""}</span>`;
      tip.hidden = false;
      tip.style.left = `${e.clientX + 14}px`;
      tip.style.top = `${e.clientY + 14}px`;
    });
    el.addEventListener("mouseleave", () => { tip.hidden = true; });
    return new maplibregl.Marker({ element: el }).setLngLat(i.pos).addTo(kaart);
  });
}

function koppelTooltip() {
  const tip = document.getElementById("tooltip");
  const toon = (e, html) => {
    tip.innerHTML = html;
    tip.hidden = false;
    tip.style.left = `${e.point.x + 14}px`;
    tip.style.top = `${e.point.y + 14}px`;
  };
  kaart.on("mousemove", "seg", (e) => {
    const f = e.features[0];
    const st = kaart.getFeatureState({ source: "segmenten", id: f.id });
    const detail = st.k === undefined
      ? `<span class="sub">geen recente waarneming</span>`
      : `<span class="sub">p90 opgelopen: ${Math.round(st.p90 / 60)} min · ${st.n} trein(en), 30 min</span>`;
    const versperd = st.blok ? `<div>🚫 versperd — treinen vallen hier uit</div>` : "";
    let werk = "";
    if (werkInfo.has(f.id)) {
      const w = werkInfo.get(f.id);
      const extra = [w.until && `tot ${w.until}`, w.txt].filter(Boolean).join(" · ");
      werk = `<div>${WERK_LABEL[w.sev] || WERK_LABEL.reduced}${extra ? `<br><span class="sub">${extra}</span>` : ""}</div>`;
    }
    toon(e, `<div class="kop">${f.properties.lijnen}</div>${versperd}${werk}${detail}`);
    kaart.getCanvas().style.cursor = "pointer";
  });
  kaart.on("mouseleave", "seg", () => {
    tip.hidden = true;
    kaart.getCanvas().style.cursor = "";
  });
  // klik op een baanvak → inspectiepagina gefilterd op die rand. Niet als
  // laag-klik: die eist een exacte pixeltreffer en mist een 2px-lijn vrijwel
  // altijd — daarom zelf zoeken met een tolerantiebox rond het klikpunt.
  kaart.on("click", (e) => {
    const t = 6;
    const box = [[e.point.x - t, e.point.y - t], [e.point.x + t, e.point.y + t]];
    const f = kaart.queryRenderedFeatures(box, { layers: ["seg"] })[0];
    if (!f) return;
    const url = new URL("inspectie.html", location.href);
    url.searchParams.set("edge", f.id);
    if (f.properties.lijnen) url.searchParams.set("label", f.properties.lijnen);
    const data = new URLSearchParams(location.search).get("data");
    if (data) url.searchParams.set("data", data);
    window.open(url, "_blank");
  });
}
