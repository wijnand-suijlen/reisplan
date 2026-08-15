"use strict";
/* Inspectiepagina: ruwe per-trein-data uit inspect/trains.json + inspect/details.json.
   Eén 4-uursartefact (24 u paste niet in het servergeheugen); de vensters
   (30 min/4 u) worden hier client-side gefilterd op last_ts.
   Contract: docs/inspectie-schema.md. */

const R2_BASE = "https://pub-2369cd93470e40528dc3aab9ab7fd5e7.r2.dev/";
const PARAMS = new URLSearchParams(location.search);
const DATA_BASE = PARAMS.get("data")
  || (location.hostname.endsWith("github.io") ? R2_BASE : "data/");
// ?edge=<rand-id> (via klik op de kaart) filtert op treinen die dat baanvak passeerden
const EDGE_ID = PARAMS.get("edge");
const EDGE_LABEL = PARAMS.get("label");

const REFRESH_MS = 120_000;
const DETAILS_MAX_AGE_MS = 300_000;
const SEVERITY_COLORS = ["#0ca30c", "#fab219", "#ec835a", "#d03b3b"]; // = KLEUREN op de kaart

// bins in minuten, kleurindex volgt de kleurklasse van de kaart (snapshot.py)
const BINS = [
  ["te vroeg", -Infinity, 0, 0],
  ["0–1", 0, 1, 0],
  ["1–2", 1, 2, 1],
  ["2–5", 2, 5, 2],
  ["5–10", 5, 10, 2],
  ["10–20", 10, 20, 3],
  ["20–60", 20, 60, 3],
  ["≥60", 60, Infinity, 3],
];

const el = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let allTrains = [];          // rij-objecten uit trains.json
let builtAt = null;          // Date van de laatste build (server)
let windowS = 14400;
let sortKey = "delay_s";
let sortDir = -1;            // -1 = aflopend
let selectedKey = null;
let details = null;          // { fetchedAt, trains }
let detailsPromise = null;
let edgePairs = null;        // rij-index -> [delta_s, ts] voor EDGE_ID (uit edges.json)
let edgeCancels = null;      // rij-index -> ts van uitvalmeldingen op EDGE_ID
let edgeRetried = false;

function trainKey(t) { return `${t.country}|${t.trip_id}|${t.service_date}`; }

async function fetchTrains() {
  let payload, edgesPayload = null;
  try {
    const wanted = [fetch(`${DATA_BASE}inspect/trains.json?t=${Date.now()}`)];
    if (EDGE_ID) wanted.push(fetch(`${DATA_BASE}inspect/edges.json?t=${Date.now()}`));
    const resps = await Promise.all(wanted);
    for (const resp of resps) if (!resp.ok) throw new Error(`http ${resp.status}`);
    payload = await resps[0].json();
    if (EDGE_ID) edgesPayload = await resps[1].json();
  } catch (e) {
    el("freshness").textContent = "gegevens niet bereikbaar";
    return;
  }
  const idx = Object.fromEntries(payload.cols.map((c, i) => [c, i]));
  allTrains = payload.rows.map((r, i) => {
    const t = { _idx: i };
    for (const c of payload.cols) t[c] = r[idx[c]];
    return t;
  });
  builtAt = new Date(payload.built_at);
  if (edgesPayload) {
    // edges.json verwijst naar rij-indices in trains.json: builds moeten matchen
    if (edgesPayload.built_at !== payload.built_at && !edgeRetried) {
      edgeRetried = true;
      setTimeout(fetchTrains, 3000);
      return;
    }
    edgeRetried = false;
    edgePairs = new Map((edgesPayload.edges[EDGE_ID] || []).map(([i, d, ts]) => [i, [d, ts]]));
    edgeCancels = new Map(((edgesPayload.cancels || {})[EDGE_ID] || []).map(([i, ts]) => [i, ts]));
  }
  render();
}

function updateFreshness() {
  if (!builtAt) return;
  const ageMin = Math.max(0, Math.round((Date.now() - builtAt.getTime()) / 60000));
  // artefacten worden elke 5 min gebouwd; veel ouder = aggregator draait niet en
  // dan lopen de vensters leeg (30 min als eerste)
  const stale = ageMin > 10;
  el("freshness").textContent =
    `${allTrains.length} treinen (4 u) · gegevens ${ageMin} min oud` +
    (stale ? " ⚠ verouderd — draait de aggregator?" : "");
  el("freshness").classList.toggle("stale", stale);
}

function visibleTrains() {
  const floor = Date.now() / 1000 - windowS;
  if (EDGE_ID) {
    if (!edgePairs) return [];
    // zelfde selectieregel als de kaartkleur: laatste passage over dít baanvak
    // binnen het venster. "Laatst gezien" (last_ts) is hier alleen informatief —
    // meefilteren zou stipte treinen laten wegvallen wier voorspellingen al
    // langer ongewijzigd zijn dan het venster breed is. Uitvalmeldingen op dit
    // baanvak (grondstof van de versperd-markering) tellen apart mee.
    return allTrains.filter((t) => {
      const pair = edgePairs.get(t._idx);
      const cancelTs = edgeCancels ? edgeCancels.get(t._idx) : undefined;
      t.edge_delta = pair && pair[1] >= floor ? pair[0] : null;
      t.edge_cancel_ts = cancelTs !== undefined && cancelTs >= floor ? cancelTs : null;
      return t.edge_delta !== null || t.edge_cancel_ts !== null;
    });
  }
  return allTrains.filter((t) => t.last_ts >= floor);
}

/* percentiel = inclusieve rang van de actuele vertraging binnen het venster;
   opgeheven treinen zonder vertragingswaarneming (delay_s null) doen niet mee */
function assignPercentiles(trains) {
  const withDelay = trains.filter((t) => t.delay_s !== null);
  const sorted = withDelay.map((t) => t.delay_s).sort((a, b) => a - b);
  for (const t of trains) {
    if (t.delay_s === null || !sorted.length) { t.percentile = null; continue; }
    let lo = 0, hi = sorted.length;      // bovengrens: aantal <= delay_s
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (sorted[mid] <= t.delay_s) lo = mid + 1; else hi = mid;
    }
    t.percentile = Math.round((100 * lo) / sorted.length);
  }
}

function formatLastSeen(t) {
  const d = new Date(t.last_ts * 1000);
  const time = d.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
  const day = d.toDateString() === new Date().toDateString()
    ? "" : d.toLocaleDateString("nl-NL", { weekday: "short" }) + " ";
  return `${day}${time}`;
}

function delayCell(delayS, cancelled) {
  if (delayS === null || delayS === undefined) {
    return `<td class="num cancel" title="als opgeheven gemeld — geen rijdende waarneming">✕</td>`;
  }
  const min = Math.round(delayS / 60);
  const cls = min < 0 ? " delay-neg" : min >= 10 ? " delay-high" : "";
  const mark = cancelled
    ? ` <span class="cancel" title="daarnaast (deels) als opgeheven gemeld">✕</span>` : "";
  return `<td class="num${cls}">${min > 0 ? "+" : ""}${min}${mark}</td>`;
}

function renderTable(trains) {
  const dir = sortDir;
  const key = sortKey;
  const sorted = [...trains].sort((a, b) => {
    const va = a[key], vb = b[key];
    const cmp = typeof va === "string"
      ? va.localeCompare(vb, "nl") : (va ?? -Infinity) - (vb ?? -Infinity);
    return dir * (cmp || a.last_ts - b.last_ts);
  });
  el("train-rows").innerHTML = sorted.map((t) => {
    const key = trainKey(t);
    const sel = key === selectedKey ? " class=\"selected\"" : "";
    const number = esc(t.train_number) + (t.route ? ` <span class="sub">${esc(t.route)}</span>` : "");
    const schedNote = t.sched_known ? "" : " <span class=\"sub\">(waargenomen)</span>";
    return `<tr data-key="${esc(key)}"${sel}>` +
      `<td>${esc(t.country)}</td>` +
      `<td class="clip" title="${esc(t.train_number)}">${number}</td>` +
      `<td class="clip" title="${esc(t.origin)}">${esc(t.origin ?? "?")}${schedNote}</td>` +
      `<td class="clip" title="${esc(t.destination)}">${esc(t.destination ?? "?")}</td>` +
      `<td>${esc((t.sched_dep || "–").slice(0, 5))}</td>` +
      delayCell(t.delay_s, t.cancelled) +
      (EDGE_ID ? delayCell(t.edge_delta, t.edge_cancel_ts !== null)
        .replace("<td class=\"num", "<td class=\"num edge-only") : "") +
      `<td class="num">${t.percentile === null ? "–" : "p" + t.percentile}</td>` +
      `<td class="clip-sm" title="${esc(t.last_stop)}">${formatLastSeen(t)}` +
      ` <span class="sub">${esc(t.last_stop ?? "")}</span></td>` +
      `<td class="num">${t.n_obs}</td></tr>`;
  }).join("");
  el("empty-note").hidden = sorted.length > 0;
  for (const th of document.querySelectorAll("#trains thead th")) {
    th.classList.toggle("sorted-asc", th.dataset.key === sortKey && sortDir === 1);
    th.classList.toggle("sorted-desc", th.dataset.key === sortKey && sortDir === -1);
  }
}

function renderHistogram(all) {
  const trains = all.filter((t) => t.delay_s !== null);
  const nCancelled = all.filter((t) => t.cancelled).length;
  const counts = BINS.map(() => 0);
  for (const t of trains) {
    const min = t.delay_s / 60;
    for (let b = 0; b < BINS.length; b++) {
      if (min >= BINS[b][1] && min < BINS[b][2]) { counts[b]++; break; }
    }
  }
  const W = 320, H = 170, pad = 4, bottom = 24, top = 16;
  const plotH = H - bottom - top;
  const maxCount = Math.max(1, ...counts);
  const bw = (W - pad * 2) / BINS.length;
  const parts = [`<line x1="${pad}" y1="${H - bottom}" x2="${W - pad}" y2="${H - bottom}" stroke="#d8d8d4"/>`];
  counts.forEach((n, b) => {
    const h = Math.round((plotH * n) / maxCount);
    const x = (pad + b * bw + 1).toFixed(1);
    const cx = (pad + b * bw + bw / 2).toFixed(1);
    const y = H - bottom - h;
    const pct = trains.length ? Math.round((100 * n) / trains.length) : 0;
    parts.push(`<g><title>${esc(BINS[b][0])} min: ${n} treinen (${pct}%)</title>` +
      (h ? `<rect x="${x}" y="${y}" width="${(bw - 2).toFixed(1)}" height="${h}" rx="2"` +
           ` fill="${SEVERITY_COLORS[BINS[b][3]]}"/>` : "") +
      (n ? `<text x="${cx}" y="${y - 3}" class="count">${n}</text>` : "") +
      `<text x="${cx}" y="${H - bottom + 12}" class="bin">${esc(BINS[b][0])}</text></g>`);
  });
  el("histogram").innerHTML = parts.join("");
  el("histogram-n").textContent = `· ${trains.length} treinen` +
    (nCancelled ? ` · ✕ ${nCancelled} met uitvalmelding` : "");
}

async function fetchDetails() {
  if (details && Date.now() - details.fetchedAt < DETAILS_MAX_AGE_MS) return details;
  if (!detailsPromise) {
    detailsPromise = fetch(`${DATA_BASE}inspect/details.json?t=${Date.now()}`)
      .then((resp) => { if (!resp.ok) throw new Error(`http ${resp.status}`); return resp.json(); })
      .then((payload) => { details = { fetchedAt: Date.now(), trains: payload.trains }; return details; })
      .finally(() => { detailsPromise = null; });
  }
  return detailsPromise;
}

async function renderDetail() {
  const pane = el("detail");
  if (!selectedKey) {
    pane.innerHTML = "<span class=\"hint\">klik een trein voor de hele dienst</span>";
    return;
  }
  const train = allTrains.find((t) => trainKey(t) === selectedKey);
  if (!train) { pane.innerHTML = "<span class=\"hint\">trein niet meer in de gegevens</span>"; return; }
  const head = `<h3>${esc(train.train_number)} <span class="sub">${esc(train.country)}` +
    `${train.route ? " · " + esc(train.route) : ""}</span></h3>` +
    `<div class="meta">trip_id ${esc(train.trip_id)} · dienstdag ${esc(train.service_date)}</div>`;
  pane.innerHTML = head + "<span class=\"hint\">laden…</span>";
  let data;
  try {
    data = (await fetchDetails()).trains[selectedKey];
  } catch (e) {
    pane.innerHTML = head + "<span class=\"hint\">details niet bereikbaar</span>";
    return;
  }
  if (!data) { pane.innerHTML = head + "<span class=\"hint\">geen details in dit artefact</span>"; return; }
  const banner = data.sched_known ? "" :
    "<div class=\"banner\">dienstregeling onbekend — bron niet koppelbaar aan GTFS;" +
    " stops op volgorde van waarneming</div>";
  const rows = data.stops.map(([name, arr, dep, delayS]) => {
    const unplanned = data.sched_known && arr === null && dep === null;
    const delay = delayS === null ? "<td class=\"num sub\">–</td>" : delayCell(delayS);
    return `<tr${unplanned ? " class=\"unplanned\"" : ""}><td title="${esc(name)}">${esc(name)}</td>` +
      `<td>${esc((arr || "–").slice(0, 5))}</td><td>${esc((dep || "–").slice(0, 5))}</td>${delay}</tr>`;
  }).join("");
  pane.innerHTML = head + banner +
    "<table><thead><tr><th>Station</th><th>Aank</th><th>Vertr</th>" +
    "<th class=\"num\" title=\"vertraging in minuten\">Vertr. (min)</th></tr></thead><tbody>" +
    rows + "</tbody></table>";
}

/* Kaartstatus van het gekozen baanvak: hetzelfde snapshot.json als de kaart
   (kleur, versperd, actieve werkzaamheden) + de baseline-blokken uit works.json.
   Zo staat naast de ruwe treindata precies wat de kaart er nú van maakt. */
const WERK_LABEL = { // labels als op de kaart (app.js)
  closed: "🚧 werkzaamheden — gepland buiten dienst",
  reduced: "🚧 werkzaamheden — aangepaste dienst",
  intl: "🌍 internationale verbinding gestremd",
};

function fmtBlok(d, h0, h1) {
  const dag = `${d.slice(6, 8)}-${d.slice(4, 6)}`;
  return `${dag} ${String(h0).padStart(2, "0")}–${String(h1 + 1).padStart(2, "0")} u`;
}

async function fetchMapStatus() {
  const pane = el("map-status");
  let snap, works;
  try {
    const resps = await Promise.all([
      fetch(`${DATA_BASE}snapshot.json?t=${Date.now()}`),
      fetch(`${DATA_BASE}inspect/works.json?t=${Date.now()}`),
    ]);
    snap = await resps[0].json();
    works = resps[1].ok ? await resps[1].json() : { edges: {} };
  } catch (e) {
    pane.innerHTML = "<span class=\"hint\">kaartstatus niet bereikbaar</span>";
    return;
  }
  const parts = [];
  const seg = (snap.seg || []).find(([id]) => id === EDGE_ID);
  if (seg) {
    const [, k, p90, n] = seg;
    parts.push(`<div><span class="dot" style="background:${SEVERITY_COLORS[k]}"></span>` +
      `kleurklasse ${k} · p90 opgelopen ${Math.round(p90 / 60)} min · ` +
      `${n} trein(en), 30 min</div>`);
  } else {
    parts.push("<div><span class=\"dot\" style=\"background:#9a9a97\"></span>" +
      "geen kleurwaarneming (grijs op de kaart)</div>");
  }
  if ((snap.blk || []).includes(EDGE_ID)) {
    parts.push("<div>🚫 <b>versperd</b> — ≥2 treinen binnen 90 min als opgeheven " +
      "gemeld, geen waargenomen passage sindsdien</div>");
  }
  for (const [src, sev, until, txt, randen] of snap.wrk || []) {
    if (!randen.includes(EDGE_ID)) continue;
    const extra = [until && `tot ${until}`, txt, `bron: ${src}`].filter(Boolean).join(" · ");
    parts.push(`<div>${WERK_LABEL[sev] || WERK_LABEL.reduced}` +
      `<br><span class="sub">${esc(extra)}</span></div>`);
  }
  const blokken = (works.edges || {})[EDGE_ID] || [];
  if (blokken.length) {
    const toon = blokken.slice(0, 8).map(([d, h0, h1]) => fmtBlok(d, h0, h1)).join(", ");
    parts.push(`<div>📅 geplande buitendienststelling (baseline: 0 geplande treinen): ` +
      `<span class="sub">${esc(toon)}${blokken.length > 8 ? ` +${blokken.length - 8} meer` : ""}</span></div>`);
  }
  const leeftijd = Math.max(0, Math.round((Date.now() - Date.parse(snap.t)) / 1000));
  parts.push(`<div class="sub">snapshot ${leeftijd}s oud</div>`);
  pane.innerHTML = parts.join("");
}

function render() {
  const trains = visibleTrains();
  assignPercentiles(trains);
  renderTable(trains);
  renderHistogram(trains);
  updateFreshness();
}

el("period").addEventListener("change", (e) => {
  windowS = Number(e.target.value);
  render();
});

document.querySelector("#trains thead").addEventListener("click", (e) => {
  const th = e.target.closest("th");
  if (!th) return;
  const key = th.dataset.key;
  if (key === sortKey) sortDir = -sortDir;
  else {
    sortKey = key;
    sortDir = ["delay_s", "edge_delta", "percentile", "n_obs"].includes(key) ? -1 : 1;
  }
  render();
});

el("train-rows").addEventListener("click", (e) => {
  const tr = e.target.closest("tr");
  if (!tr) return;
  selectedKey = tr.dataset.key === selectedKey ? null : tr.dataset.key;
  for (const row of el("train-rows").children)
    row.classList.toggle("selected", row.dataset.key === selectedKey);
  renderDetail();
});

if (EDGE_ID) {
  document.getElementById("trains").classList.add("edge-mode");
  const clear = new URLSearchParams(location.search);
  clear.delete("edge");
  clear.delete("label");
  const chip = el("edge-chip");
  chip.hidden = false;
  chip.innerHTML = `baanvak <b>${esc(EDGE_LABEL || EDGE_ID)}</b> ` +
    `<a href="inspectie.html${clear.toString() ? "?" + clear : ""}">filter wissen</a>`;
  el("empty-note").textContent =
    "geen passages of uitvalmeldingen op dit baanvak in dit venster";
  el("map-status-pane").hidden = false;
  fetchMapStatus();
  setInterval(fetchMapStatus, REFRESH_MS);
}

fetchTrains();
setInterval(fetchTrains, REFRESH_MS);
setInterval(updateFreshness, 30_000);
