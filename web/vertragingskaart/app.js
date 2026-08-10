"use strict";

const KLEUREN = ["#0ca30c", "#fab219", "#ec835a", "#d03b3b"]; // klasse 0-3 (gevalideerd statuspalet)

// op smalle schermen neemt de legenda het halve beeld in beslag: start ingeklapt
if (matchMedia("(max-width: 640px)").matches) {
  document.getElementById("legenda-details").removeAttribute("open");
}
const GEEN_DATA = "#9a9a97";
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
  for (const [id, k, p90, n] of snap.seg) {
    kaart.setFeatureState({ source: "segmenten", id }, { k, p90, n });
    nieuw.add(id);
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
    toon(e, `<div class="kop">${f.properties.lijnen}</div>${detail}`);
    kaart.getCanvas().style.cursor = "pointer";
  });
  kaart.on("mouseleave", "seg", () => {
    tip.hidden = true;
    kaart.getCanvas().style.cursor = "";
  });
}
