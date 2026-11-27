import { fetchPlayer, importToLichess, PlayerNotFound, ApiError, cacheGet, cacheSet } from "./api.js?v=47";
import { renderBoard } from "./board.js?v=47";
import { patterns } from "./insights.js?v=47";
import { startTrainer } from "./trainer.js?v=47";
import { addLocalTime, DAYS, MODES, sanMoves } from "./parse.js?v=47";
import { tOpening, tReason } from "./i18n.js?v=47";
import {
  LENGTH_BINS, lengthBin, pct, filterGames, counts, groupWin, eloSummary, totalHours,
  mostCommon, movePace, streakEffect, openingTable, reasonShares, dayHourGrid, monthGrid,
  sessionIndexWin, SESSION_ORDER, ratingDiffWin, DIFF_ORDER, timeResults, quickResigns, opponents, monthSummary, prevMonth, openingTree,
} from "./stats.js?v=47";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Plotly (duży plik) ładujemy dopiero przy pierwszym wykresie, żeby strona startowa była lekka.
const PLOTLY_URL = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js";
let plotlyPromise = null;
function ensurePlotly() {
  if (window.Plotly) return Promise.resolve(window.Plotly);
  plotlyPromise ||= new Promise((resolve, reject) => {
    const sc = document.createElement("script");
    sc.src = PLOTLY_URL;
    sc.onload = () => resolve(window.Plotly);
    sc.onerror = () => { plotlyPromise = null; reject(new Error("Nie udało się wczytać biblioteki wykresów (brak internetu?)")); };
    document.head.appendChild(sc);
  });
  return plotlyPromise;
}

// ---------------------------------------------------------------- ustawienia
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* brak dostępu */ } },
};

const state = {
  scope: "single",
  data: null,     // { name, profile, games, platforms, sources: [[user, plat], ...] }
  rival: null,    // { name, plat, user, games }
  view: "my",
  tab: null,
  opLang: store.get("opLang", "pl"),
  filters: { from: "", to: "", mode: "", colors: ["w", "b"], hourMin: 0, hourMax: 23 },
  anaPreset: null, // np. { group } po kliknięciu debiutu
};

function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 2200);
}

// ---------------------------------------------------------------- ostatnio wyszukiwani
function getRecent() {
  try { return JSON.parse(store.get("recent", "[]")) || []; } catch { return []; }
}

function saveRecent(entry) {
  const id = (e) => [e.scope, e.user, e.plat, e.user2 || "", e.plat2 || ""].join("|").toLowerCase();
  const list = [entry, ...getRecent().filter((e) => id(e) !== id(entry))].slice(0, 6);
  store.set("recent", JSON.stringify(list));
}

function renderRecent() {
  const list = getRecent();
  const el = $("#recent");
  el.classList.toggle("hidden", !list.length);
  if (!list.length) return;
  const label = (e) => e.scope === "single" ? `${e.user} · ${e.plat === "Lichess" ? "Lichess" : "Chess.com"}`
    : `${e.user} ${e.scope === "merge" ? "+" : "vs"} ${e.user2}`;
  el.innerHTML = `<span class="recent-title">Ostatnio:</span>` + list.map((e, i) => `<button type="button" data-i="${i}">${esc(label(e))}</button>`).join("");
  el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const e = list[Number(b.dataset.i)];
    setScope(e.scope);
    $("#p1-nick").value = e.user; $("#p1-plat").value = e.plat;
    if (e.user2) { $("#p2-nick").value = e.user2; $("#p2-plat").value = e.plat2; }
    startAnalysis();
  }));
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  store.set("theme", theme);
  if (state.data) renderTab();
}

// ---------------------------------------------------------------- wykresy
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

function plot(el, traces, layout = {}) {
  const base = {
    paper_bgcolor: css("--card"), plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: css("--muted"), size: isNarrow() ? 11 : 12 }, margin: { l: 50, r: 10, t: 36, b: 50 },
    legend: { orientation: "h", y: 1.02, yanchor: "bottom", x: 0, xanchor: "left" },
    xaxis: { gridcolor: css("--grid"), zerolinecolor: css("--grid"), showgrid: false },
    yaxis: { gridcolor: css("--grid"), zerolinecolor: css("--grid") },
    hoverlabel: { namelength: -1 },
  };
  const merged = { ...base, ...layout, xaxis: { ...base.xaxis, ...layout.xaxis }, yaxis: { ...base.yaxis, ...layout.yaxis } };
  // Rysujemy w następnej klatce, gdy siatka (np. dwa wykresy obok siebie) ma już docelowe szerokości.
  return ensurePlotly().then((P) => new Promise((resolve) => requestAnimationFrame(() => resolve(P.react(el, traces, merged, { displayModeBar: false, responsive: true }))))).catch((e) => { el.innerHTML = `<div class="info">${esc(e.message)}</div>`; });
}

const isNarrow = () => window.innerWidth < 640;
const shortName = (n, max = 12) => (n.length > max ? n.slice(0, max - 1) + "…" : n);

// Przy długim zakresie dzienne słupki są nieczytelne: grupujemy po tygodniach albo miesiącach.
function activityBucket(games) {
  if (!games.length) return { key: (g) => g.day, label: "dzień" };
  const spanDays = (games[games.length - 1].endTs - games[0].endTs) / 86400;
  if (spanDays > 540) return { key: (g) => `${g.month}-01`, label: "miesiąc" };
  if (spanDays > 120) {
    return {
      key: (g) => {
        const d = new Date(g.date); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - g.dow);
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      },
      label: "tydzień",
    };
  }
  return { key: (g) => g.day, label: "dzień" };
}

function chartBox(parent, title) {
  if (title) parent.insertAdjacentHTML("beforeend", `<h3>${esc(title)}</h3>`);
  const div = document.createElement("div");
  div.className = "chart";
  parent.appendChild(div);
  return div;
}

function info(parent, text) {
  parent.insertAdjacentHTML("beforeend", `<div class="info">${esc(text)}</div>`);
}

function table(parent, cols, rows, { scroll = false, onRow = null } = {}) {
  // cols: [{key, label, num, fmt, html}]; scroll: ogranicza wysokość długich tabel; onRow: klik w wiersz
  const wrap = document.createElement("div");
  wrap.className = scroll ? "table-wrap scroll" : "table-wrap";
  let sortKey = null, asc = false;
  const draw = () => {
    const data = sortKey ? [...rows].sort((a, b) => (a[sortKey] > b[sortKey] ? 1 : -1) * (asc ? 1 : -1)) : rows;
    wrap.innerHTML = `<table><thead><tr>${cols.map((c) => `<th class="${c.num ? "num" : ""} ${c.nowrap ? "nowrap" : ""}" data-k="${c.key}">${esc(c.label)}</th>`).join("")}</tr></thead>
      <tbody>${data.map((r, i) => `<tr data-i="${i}" class="${onRow ? "clickable" : ""}">${cols.map((c) => `<td class="${c.num ? "num" : ""} ${c.nowrap ? "nowrap" : ""}">${c.html ? c.html(r) : esc(c.fmt ? c.fmt(r[c.key]) : r[c.key])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    if (onRow) wrap.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => onRow(data[Number(tr.dataset.i)])));
    wrap.querySelectorAll("th").forEach((th) => th.addEventListener("click", () => {
      asc = sortKey === th.dataset.k ? !asc : false;
      sortKey = th.dataset.k;
      draw();
    }));
  };
  draw();
  parent.appendChild(wrap);
}

function metric(label, value, sub = "") {
  return `<div class="metric"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</div>`;
}

// Słupki Win%: bez koloru gracza kolorujemy względem 50%, a małe próbki (< 10 partii) przygaszamy.
const SMALL_SAMPLE = 10;
const winBar = (m, order, name, color) => {
  const keys = order.filter((k) => m.has(k));
  const y = keys.map((k) => m.get(k).winPct);
  const n = keys.map((k) => m.get(k).n);
  return {
    type: "bar", name, x: keys, y,
    text: n.map((v) => `${v} partii${v < SMALL_SAMPLE ? ", mała próbka" : ""}`), hovertemplate: "%{x}: %{y}% (%{text})<extra></extra>",
    textposition: "none",
    marker: color
      ? { color, opacity: n.map((v) => (v < SMALL_SAMPLE ? 0.35 : 1)) }
      : { color: y, cmin: 35, cmax: 65, colorscale: [[0, css("--loss")], [0.5, css("--draw")], [1, css("--win")]], opacity: n.map((v) => (v < SMALL_SAMPLE ? 0.35 : 1)) },
  };
};
const LINE50 = { shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 50, y1: 50, line: { dash: "dot", width: 1, color: "rgba(160,160,160,.7)" } }] };

// Przyciski zakresu i znacznik aktualnego rankingu na wykresach ELO.
function eloLayout() {
  return {
    xaxis: {
      rangeselector: {
        buttons: [
          { count: 1, step: "month", stepmode: "backward", label: "1M" },
          { count: 6, step: "month", stepmode: "backward", label: "6M" },
          { count: 1, step: "year", stepmode: "backward", label: "1R" },
          { step: "all", label: "Całość" },
        ],
        bgcolor: css("--bg"), activecolor: css("--accent"), font: { color: css("--text") }, x: 0, y: 1.02, yanchor: "bottom",
      },
      type: "date", tickformat: "%m.%Y",
    },
    legend: { orientation: "h", y: 1.02, yanchor: "bottom", x: 1, xanchor: "right" },
    margin: { l: 50, r: 50, t: 44, b: 40 },
  };
}

function eloTraces(list, name, color) {
  const last = list[list.length - 1];
  return [
    { type: "scatter", mode: "lines", name, x: list.map((g) => g.date), y: list.map((g) => g.elo), line: { color, width: 1.6 }, hovertemplate: "%{x|%d.%m.%Y}: %{y}<extra>" + esc(name) + "</extra>" },
    { type: "scatter", mode: "markers+text", showlegend: false, x: [last.date], y: [last.elo], text: [String(last.elo)], textposition: "middle right", textfont: { color, size: 12 }, marker: { color, size: 8 }, hoverinfo: "skip", cliponaxis: false },
  ];
}

// ---------------------------------------------------------------- pobieranie
function progressUI(el) {
  const bar = el.querySelector(".bar"), label = el.querySelector("span");
  el.classList.remove("hidden");
  return {
    update(done, total, text) { bar.style.width = `${total ? Math.min(100, (done / total) * 100) : 0}%`; label.textContent = text; },
    hide() { el.classList.add("hidden"); bar.style.width = "0"; },
  };
}

async function load(user, plat, progressEl) {
  const p = progressUI(progressEl);
  p.update(0, 0, `Pobieranie ${user} (${plat})...`);
  try {
    const out = await fetchPlayer(user, plat, (d, t, txt) => p.update(d, t, txt));
    if (!out.games.length) throw new ApiError(`Gracz ${user} nie ma partii bullet/blitz/rapid na ${plat}.`);
    out.games.forEach(addLocalTime);
    return out;
  } catch (e) {
    if (e instanceof PlayerNotFound) throw new Error(`Nie znaleziono gracza ${user} na ${plat}.`);
    throw e;
  } finally {
    p.hide();
  }
}

const mergeGames = (...lists) => lists.flat().sort((a, b) => a.endTs - b.endTs);

function showError(el, err) {
  el.textContent = err ? (err.message || String(err)) : "";
  el.classList.toggle("hidden", !err);
}

async function startAnalysis(e) {
  e?.preventDefault();
  const btn = $("#start-btn");
  const n1 = $("#p1-nick").value.trim(), p1 = $("#p1-plat").value;
  const n2 = $("#p2-nick").value.trim(), p2 = $("#p2-plat").value;
  if (!n1 || (state.scope !== "single" && !n2)) return;
  btn.disabled = true;
  showError($("#start-error"), null);
  try {
    const a = await load(n1, p1, $("#progress"));
    if (state.scope === "single") {
      state.data = { name: a.profile.name, profile: a.profile, games: a.games, platforms: [p1], sources: [[n1, p1]] };
      state.rival = null;
      state.view = "my";
    } else {
      const b = await load(n2, p2, $("#progress"));
      if (state.scope === "merge") {
        state.data = { name: `${a.profile.name} + ${b.profile.name}`, profile: a.profile, games: mergeGames(a.games, b.games), platforms: [...new Set([p1, p2])], sources: [[n1, p1], [n2, p2]] };
        state.rival = null;
        state.view = "my";
      } else {
        state.data = { name: a.profile.name, profile: a.profile, games: a.games, platforms: [p1], sources: [[n1, p1]] };
        state.rival = { name: b.profile.name, user: n2, plat: p2, games: b.games };
        state.view = "compare";
      }
    }
    const url = new URL(location.href);
    url.search = "";
    url.searchParams.set("user", n1);
    url.searchParams.set("platform", p1);
    if (state.scope !== "single") { url.searchParams.set("user2", n2); url.searchParams.set("platform2", p2); url.searchParams.set("mode", state.scope); }
    history.replaceState(null, "", url);
    saveRecent({ scope: state.scope, user: n1, plat: p1, user2: state.scope === "single" ? "" : n2, plat2: p2 });
    resetFilters();
    showResults();
  } catch (err) {
    showError($("#start-error"), err);
  } finally {
    btn.disabled = false;
  }
}

async function refresh() {
  const btn = $("#refresh-btn");
  btn.disabled = true;
  showError($("#results-error"), null);
  try {
    const parts = [];
    for (const [u, p] of state.data.sources) parts.push(await load(u, p, $("#progress2")));
    state.data.games = mergeGames(...parts.map((x) => x.games));
    if (state.rival) state.rival.games = (await load(state.rival.user, state.rival.plat, $("#progress2"))).games;
    renderResults();
  } catch (err) {
    showError($("#results-error"), err);
  } finally {
    btn.disabled = false;
  }
}

async function loadRival(e) {
  e.preventDefault();
  const user = $("#rival-nick").value.trim(), plat = $("#rival-plat").value;
  if (!user) return;
  showError($("#results-error"), null);
  try {
    const r = await load(user, plat, $("#progress2"));
    state.rival = { name: r.profile.name, user, plat, games: r.games };
    const url = new URL(location.href);
    url.searchParams.set("user2", user); url.searchParams.set("platform2", plat); url.searchParams.set("mode", "compare");
    history.replaceState(null, "", url);
    resetFilters();
    state.tab = null;
    renderResults();
  } catch (err) {
    showError($("#results-error"), err);
  }
}

function changePlayer() {
  state.data = null; state.rival = null; state.tab = null;
  history.replaceState(null, "", location.pathname);
  $("#results").classList.add("hidden");
  $("#start").classList.remove("hidden");
  renderRecent();
}

// ---------------------------------------------------------------- filtry
function dataRange() {
  const all = [...state.data.games, ...(state.rival?.games || [])];
  let min = "", max = "";
  for (const g of all) { if (!min || g.day < min) min = g.day; if (!max || g.day > max) max = g.day; }
  return [min, max];
}

function setPreset(days) {
  const [min, max] = dataRange();
  let from = min;
  if (days > 0) {
    const d = new Date(`${max}T12:00:00`); d.setDate(d.getDate() - days + 1);
    const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    from = k > min ? k : min;
  }
  $("#f-from").value = from; $("#f-to").value = max;
  document.querySelectorAll("#presets button").forEach((b) => b.classList.toggle("on", Number(b.dataset.days) === days));
}

function resetFilters() {
  setPreset(0);
  $("#f-mode").value = ""; $("#f-h1").value = 0; $("#f-h2").value = 23;
  $("#f-white").classList.add("on"); $("#f-black").classList.add("on");
  readFilters(false);
}

function readFilters(render = true) {
  const f = state.filters;
  f.from = $("#f-from").value; f.to = $("#f-to").value; f.mode = $("#f-mode").value;
  f.colors = [$("#f-white").classList.contains("on") && "w", $("#f-black").classList.contains("on") && "b"].filter(Boolean);
  const h1 = Number($("#f-h1").value), h2 = Number($("#f-h2").value);
  f.hourMin = Math.min(h1, h2); f.hourMax = Math.max(h1, h2);
  $("#f-hours-label").textContent = `${f.hourMin}:00 – ${f.hourMax}:59`;

  // Krótkie podsumowanie widoczne przy zwiniętym panelu.
  const [min, max] = dataRange();
  const parts = [];
  const preset = document.querySelector("#presets button.on");
  if (preset && preset.dataset.days !== "0") parts.push(preset.textContent);
  else if (f.from !== min || f.to !== max) parts.push(`${f.from} – ${f.to}`);
  if (f.mode) parts.push(f.mode);
  if (f.colors.length === 1) parts.push(f.colors[0] === "w" ? "tylko białe" : "tylko czarne");
  if (!f.colors.length) parts.push("brak koloru!");
  if (f.hourMin > 0 || f.hourMax < 23) parts.push(`${f.hourMin}:00–${f.hourMax}:59`);
  $("#filter-summary").textContent = parts.length ? `· ${parts.join(" · ")}` : "";
  if (render) renderTab();
}

// ---------------------------------------------------------------- widoki
function showResults() {
  $("#start").classList.add("hidden");
  $("#results").classList.remove("hidden");
  state.tab = null;
  renderResults();
}

const MY_TABS = [["stats", "📊 Statystyki"], ["ins", "💡 Wnioski"], ["hist", "📅 Historia"], ["time", "⏳ Czas"], ["open", "🔬 Debiuty"], ["ana", "🧠 Analiza"]];
const CMP_TABS = [["cstats", "📊 Ogólne"], ["chist", "📅 Historia"], ["ctime", "⏳ Czas"], ["copen", "🔬 Debiuty"], ["h2h", "🥊 H2H"]];

function renderResults() {
  const d = state.data;
  $("#player-name").textContent = d.name;
  const av = $("#avatar");
  av.onerror = () => av.classList.add("hidden");
  if (d.profile.avatar) { av.src = d.profile.avatar; av.classList.remove("hidden"); } else av.classList.add("hidden");
  document.querySelectorAll("#view button").forEach((b) => b.classList.toggle("on", b.dataset.view === state.view));

  const cmp = state.view === "compare";
  $("#rival-box").classList.toggle("hidden", !cmp || !!state.rival);

  $("#elo-cards").innerHTML = MODES.slice().reverse().map((m) => {
    const s = eloSummary(d.games, m);
    if (!cmp || !state.rival) return metric(`${m} (peak / teraz)`, s ? `${s.peak} / ${s.current}` : "– / –");
    const r = eloSummary(state.rival.games, m);
    return metric(`${m}: obecne`, `${s?.current ?? "–"} / ${r?.current ?? "–"}`, `Peak: ${s?.peak ?? "–"} / ${r?.peak ?? "–"}`);
  }).join("");

  const showContent = !cmp || state.rival;
  $("#filters").classList.toggle("hidden", !showContent);
  $("#tabs").classList.toggle("hidden", !showContent);
  $("#tab-content").classList.toggle("hidden", !showContent);
  if (!showContent) return;

  let tabs = cmp ? CMP_TABS : MY_TABS;
  if (cmp && !d.platforms.includes(state.rival.plat)) tabs = tabs.filter(([k]) => k !== "h2h");
  if (!state.tab) state.tab = store.get("tab:" + (cmp ? "cmp" : "my"), null);
  if (!tabs.some(([k]) => k === state.tab)) state.tab = tabs[0][0];
  $("#tabs").innerHTML = tabs.map(([k, l]) => `<button data-tab="${k}" class="${k === state.tab ? "on" : ""}">${l}</button>`).join("")
    + (cmp ? `<button data-tab="__rival" title="Zmień rywala">🔄 Inny rywal</button>` : "");
  renderTab();
}

function renderTab() {
  if (!state.data || $("#results").classList.contains("hidden")) return;
  const el = $("#tab-content");
  el.innerHTML = "";
  const f = state.filters;
  const g1 = filterGames(state.data.games, f);
  if (state.view === "compare") {
    if (!state.rival) return;
    const g2 = filterGames(state.rival.games, f);
    ({ cstats: tabCompareStats, chist: tabCompareHist, ctime: tabCompareTime, copen: tabCompareOpen, h2h: tabH2H })[state.tab](el, g1, g2);
    fitCharts();
    return;
  }
  if (!g1.length) return info(el, "Brak partii dla wybranych filtrów.");
  ({ stats: tabStats, ins: tabInsights, hist: tabHist, time: tabTime, open: tabOpen, ana: tabAnalysis })[state.tab](el, g1);
  fitCharts();
}

function switchTab(tab) {
  state.tab = tab;
  if (tab !== "__rival") store.set("tab:" + (state.view === "compare" ? "cmp" : "my"), tab);
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x.dataset.tab === tab));
  renderTab();
  $("#tabs").scrollIntoView({ behavior: "smooth", block: "start" });
}

// Wykresy w siatce rysowane są zanim siatka ułoży kolumny, więc po renderze dopasowujemy szerokość.
function fitCharts() {
  requestAnimationFrame(() => window.Plotly && document.querySelectorAll("#tab-content .js-plotly-plot").forEach((c) => window.Plotly.Plots.resize(c)));
}

// ----- Moja analiza
const MONTHS_FULL = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień"];
const monthName = (ym) => `${MONTHS_FULL[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;
const signed = (v) => (v > 0 ? `+${v}` : String(v));
const wdlBar = (r) => `<div class="wdl" title="W ${r.w} / R ${r.d} / P ${r.l}"><i style="width:${(r.w / r.n) * 100}%;background:var(--win)"></i><i style="width:${(r.d / r.n) * 100}%;background:var(--draw)"></i><i style="width:${(r.l / r.n) * 100}%;background:var(--loss)"></i></div>`;

// ----- Wnioski
function tabInsights(el, games) {
  const overall = pct(counts(games).W, games.length);

  // Podsumowanie miesiąca
  const month = games[games.length - 1].month;
  const cur = monthSummary(games, month), prev = monthSummary(games, prevMonth(month));
  el.insertAdjacentHTML("beforeend", `<h3>Podsumowanie: ${monthName(month)}</h3>`);
  const delta = (a, b, unit = "") => (prev.n ? `${signed(a - b)}${unit} vs ${monthName(prev.month).split(" ")[0]}` : "brak partii miesiąc wcześniej");
  const eloCards = Object.entries(cur.elo).map(([m, e]) => metric(`${m}`, e.end, `${signed(e.change)} w tym miesiącu`)).join("");
  el.insertAdjacentHTML("beforeend", `<div class="metrics">
    ${metric("Partie", cur.n, delta(cur.n, prev.n))}${metric("Win%", `${cur.winPct}%`, delta(cur.winPct, prev.winPct, " pp"))}${eloCards}</div>`);
  const op = (o) => `<b>${esc(tOpening(o.name, state.opLang))}</b> (${o.winPct}% z ${o.n})`;
  if (cur.best) el.insertAdjacentHTML("beforeend", `<div class="callout">Najlepszy debiut: ${op(cur.best)}${cur.worst ? `<br>Najsłabszy: ${op(cur.worst)}` : ""}</div>`);

  // Numer partii w sesji
  const ses = sessionIndexWin(games);
  plot(chartBox(el, "Win% wg numeru partii w sesji"), [winBar(ses, SESSION_ORDER, "Win%")], { ...LINE50, yaxis: { range: [0, 100], title: { text: "Win %" } }, xaxis: { type: "category", title: { text: "Która partia w sesji (przerwa > 2 h = nowa sesja)" } } });
  const drop = SESSION_ORDER.slice(1).find((k) => ses.get(k)?.n >= SMALL_SAMPLE && ses.get(k).winPct <= overall - 5);
  info(el, drop
    ? `Od ${drop}. partii w sesji wygrywasz wyraźnie rzadziej (${ses.get(drop).winPct}% przy średniej ${overall}%). Dobry moment na przerwę.`
    : `Liczba partii w sesji nie obniża wyraźnie Twoich wyników (średnio ${overall}%).`);

  // Siła rywala
  const diff = ratingDiffWin(games);
  plot(chartBox(el, "Win% wg siły rywala"), [winBar(diff, DIFF_ORDER, "Win%")], { ...LINE50, yaxis: { range: [0, 100], title: { text: "Win %" } }, xaxis: { type: "category", title: { text: "Ranking rywala minus Twój" } } });
  const weak = [DIFF_ORDER[0], DIFF_ORDER[1]].map((k) => diff.get(k)).filter(Boolean);
  const wn = weak.reduce((s, e) => s + e.n, 0), ww = weak.reduce((s, e) => s + e.w, 0);
  if (wn >= SMALL_SAMPLE) info(el, `Z rywalami słabszymi o ponad 100 pkt wygrywasz ${pct(ww, wn)}% (${wn} partii).`);

  // Na czas
  el.insertAdjacentHTML("beforeend", "<h3>Partie rozstrzygnięte na czas</h3>");
  table(el, [
    { key: "mode", label: "Tryb" },
    { key: "lossPct", label: "Porażki na czas", num: true, nowrap: true, html: (r) => `${r.lossPct}% <span class="muted">(${r.lostOnTime}/${r.losses})</span>` },
    { key: "winPct", label: "Wygrane na czas", num: true, nowrap: true, html: (r) => `${r.winPct}% <span class="muted">(${r.wonOnTime}/${r.wins})</span>` },
  ], timeResults(games));

  // Szybkie poddania
  const qr = quickResigns(games);
  el.insertAdjacentHTML("beforeend", `<h3 title="Porażki przez poddanie albo porzucenie partii przed 20. ruchem">Szybkie poddania (przed 20. ruchem) ⓘ</h3>`);
  if (!qr.n) info(el, "Brak szybkich poddań. Walczysz do końca 💪");
  else {
    el.insertAdjacentHTML("beforeend", `<div class="metrics">${metric("Szybkie poddania", qr.n, `${qr.pct}% wszystkich porażek`)}${qr.byMode.map((r) => metric(r.mode, `${r.pct}%`, `${r.n} z ${r.losses} porażek`)).join("")}</div>`);
    el.insertAdjacentHTML("beforeend", `<div class="callout">Najczęściej w debiutach: ${qr.byGroup.map((o) => `<b>${esc(tOpening(o.name, state.opLang))}</b> (${o.n})`).join(", ")}</div>`);
  }

  // Rywale
  const opps = opponents(games);
  el.insertAdjacentHTML("beforeend", "<h3>Najczęstsi rywale</h3>");
  if (!opps.length) return info(el, "Brak rywali z co najmniej 3 partiami.");
  const nem = opps.filter((o) => o.n >= 5).sort((a, b) => a.score - b.score || b.n - a.n)[0];
  if (nem && nem.score < 0) el.insertAdjacentHTML("beforeend", `<div class="callout">Nemezis: <b>${esc(nem.opp)}</b> · ${nem.n} partii · W ${nem.w} / R ${nem.d} / P ${nem.l} · Win ${nem.winPct}% · Lose ${nem.lossPct}%</div>`);
  table(el, [
    { key: "opp", label: "Rywal" }, { key: "n", label: "Gry", num: true }, { key: "winPct", label: "Win%", num: true, fmt: (v) => `${v}%` }, { key: "lossPct", label: "Lose%", num: true, fmt: (v) => `${v}%` },
    { key: "bar", label: "W / R / P", html: wdlBar }, { key: "last", label: "Ostatnio", nowrap: true, fmt: (d) => `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(2, 4)}` },
  ], opps.slice(0, 20), { onRow: (r) => { state.anaPreset = { opp: r.opp }; switchTab("ana"); } });
  el.insertAdjacentHTML("beforeend", `<div class="info small">Kliknij rywala, żeby zobaczyć wasze partie.</div>`);
}

// Drzewko debiutów: kolejne ruchy z Win%, klik schodzi głębiej.
const movesCache = new WeakMap();
const movesOf = (g) => {
  let m = movesCache.get(g);
  if (!m) { m = sanMoves(g.pgn, 12); movesCache.set(g, m); }
  return m;
};
function openingTreeBox(el, games) {
  el.insertAdjacentHTML("beforeend", `<h3>🌳 Drzewko debiutów</h3>`);
  const box = document.createElement("div");
  el.appendChild(box);
  let color = "w", path = [];
  const fmtPath = (p) => p.map((m, i) => (i % 2 === 0 ? `${i / 2 + 1}. ${m}` : m)).join(" ");
  const draw = () => {
    const sub = games.filter((g) => g.color === color);
    const rows = openingTree(sub, path, movesOf);
    const total = rows.reduce((s, r) => s + r.n, 0);
    box.innerHTML = `<div class="tree-head">
        <div class="seg small"><button data-c="w" class="${color === "w" ? "on" : ""}">⚪ Białe</button><button data-c="b" class="${color === "b" ? "on" : ""}">⚫ Czarne</button></div>
        <div class="crumbs"><button data-d="0">Start</button>${path.map((m, i) => `<span>›</span><button data-d="${i + 1}">${esc(i % 2 === 0 ? `${i / 2 + 1}. ${m}` : m)}</button>`).join("")}</div>
      </div>
      <div class="info small">${path.length ? `Po ${esc(fmtPath(path))}: ${total} partii.` : `${total} partii.`} ${path.length % 2 === (color === "w" ? 0 : 1) ? "Twój ruch." : "Ruch rywala."} Kliknij ruch, żeby zejść głębiej.</div>`;
    box.querySelectorAll("[data-c]").forEach((b) => b.addEventListener("click", () => { color = b.dataset.c; path = []; draw(); }));
    box.querySelectorAll("[data-d]").forEach((b) => b.addEventListener("click", () => { path = path.slice(0, Number(b.dataset.d)); draw(); }));
    if (!rows.length) return info(box, "Brak dalszych ruchów w zapisanych partiach.");
    table(box, [
      { key: "move", label: "Ruch", nowrap: true }, { key: "n", label: "Gry", num: true },
      { key: "winPct", label: "Win%", num: true, fmt: (v) => `${v}%` }, { key: "bar", label: "W / R / P", html: wdlBar },
    ], rows.slice(0, 12), { onRow: (r) => { if (path.length < 11) { path = [...path, r.move]; draw(); } } });
  };
  draw();
}

function tabStats(el, games) {
  const c = counts(games);
  el.insertAdjacentHTML("beforeend", `<div class="metrics">
    ${metric("Partie", c.n)}${metric("W / R / P", `${c.W} / ${c.D} / ${c.L}`)}
    ${metric("Win%", `${pct(c.W, c.n)}%`)}${metric("Czas gry", `${totalHours(games)} h`)}</div>`);
  const favW = mostCommon(games.filter((g) => g.color === "w").map((g) => g.group));
  const favB = mostCommon(games.filter((g) => g.color === "b").map((g) => g.group));
  el.insertAdjacentHTML("beforeend", `<div class="callout"><b>Ulubione debiuty:</b><div class="fav"><span>⚪ <b>${esc(favW ? tOpening(favW, state.opLang) : "Brak")}</b></span><span>⚫ <b>${esc(favB ? tOpening(favB, state.opLang) : "Brak")}</b></span></div></div>`);

  const byMode = MODES.map((m) => [m, games.filter((g) => g.mode === m)]).filter(([, l]) => l.length).sort((a, b) => b[1].length - a[1].length);
  for (const [m, list] of byMode) {
    const accounts = [...new Set(list.map((g) => g.account))];
    plot(chartBox(el, `Ranking ${m}`), accounts.flatMap((acc, i) => eloTraces(list.filter((g) => g.account === acc), acc, i ? css("--draw") : css("--accent"))), eloLayout());
  }

  const grid = document.createElement("div");
  grid.className = "grid2";
  el.appendChild(grid);
  for (const [res, title, palette] of [["W", "Sposób wygranej", ["#16a34a", "#22c55e", "#38bdf8", "#2563eb", "#0ea5e9"]], ["L", "Sposób porażki", ["#dc2626", "#f97316", "#ec4899", "#fb7185", "#f59e0b"]]]) {
    const r = reasonShares(games, res);
    if (!r.total) continue;
    const box = document.createElement("div");
    grid.appendChild(box);
    plot(chartBox(box, title), [{ type: "pie", hole: 0.4, labels: r.items.map(([k]) => tReason(k)), values: r.items.map(([, v]) => v), marker: { colors: palette }, sort: false }]);
  }
}

const MONTHS_PL = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];

function tabHist(el, games) {
  const cal = monthGrid(games);
  const calBox = chartBox(el, "Kalendarz aktywności (partie w miesiącu)");
  calBox.style.height = `${Math.max(cal.years.length * 34 + 40, 110)}px`;
  plot(calBox, [{
    type: "heatmap", x: MONTHS_PL, y: cal.years.map(String), z: cal.z, xgap: 3, ygap: 3,
    text: cal.z.map((row) => row.map((v) => (v ? String(v) : ""))), texttemplate: "%{text}",
    textfont: { color: css("--text"), size: isNarrow() ? 9 : 11 },
    colorscale: [[0, css("--bg")], [0.0001, css("--grid")], [1, css("--accent")]], zmin: 0,
    hovertemplate: "%{x} %{y}: %{z} partii<extra></extra>", hoverongaps: false, showscale: false,
  }], {
    yaxis: { type: "category", autorange: "reversed", showgrid: false, fixedrange: true },
    xaxis: { type: "category", showgrid: false, fixedrange: true, side: "top" },
    margin: { l: 44, r: 10, t: 24, b: 10 },
  });

  const b = activityBucket(games);
  const days = [...new Set(games.map(b.key))].sort();
  const by = (res) => { const m = new Map(); games.forEach((g) => g.result === res && m.set(b.key(g), (m.get(b.key(g)) || 0) + 1)); return days.map((d) => m.get(d) || 0); };
  plot(chartBox(el, `Aktywność i wyniki (partie na ${b.label})`), [
    { type: "bar", name: "Przegrane", x: days, y: by("L"), marker: { color: css("--loss") } },
    { type: "bar", name: "Remisy", x: days, y: by("D"), marker: { color: css("--draw") } },
    { type: "bar", name: "Wygrane", x: days, y: by("W"), marker: { color: css("--win") } },
  ], { barmode: "stack", xaxis: { type: "date", tickformat: b.label === "dzień" ? "%d.%m" : "%m.%Y" } });

  el.insertAdjacentHTML("beforeend", "<h3>Wyniki miesięczne</h3>");
  const months = [...groupWin(games, (g) => g.month)].sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([month, e]) => ({ month, n: e.n, w: e.w, d: e.d, l: e.l, winPct: e.winPct }));
  table(el, [
    { key: "month", label: "Miesiąc", nowrap: true }, { key: "n", label: "Gry", num: true }, { key: "w", label: "W", num: true },
    { key: "d", label: "R", num: true }, { key: "l", label: "P", num: true }, { key: "winPct", label: "Win%", num: true, fmt: (v) => `${v}%` },
  ], months, { scroll: true });
}

function tabTime(el, games) {
  const hours = Array.from({ length: 24 }, (_, i) => i);
  el.insertAdjacentHTML("beforeend", `<div class="info small">Zielone słupki: powyżej 50% wygranych, czerwone: poniżej. Przygaszone: mniej niż ${SMALL_SAMPLE} partii, więc wynik jest mało wiarygodny.</div>`);
  plot(chartBox(el, "Skuteczność wg godzin"), [winBar(groupWin(games, (g) => g.hour), hours, "Win%")], { ...LINE50, yaxis: { range: [0, 100], title: { text: "Win %" } }, xaxis: { dtick: isNarrow() ? 3 : 1, title: { text: "Godzina" } } });
  const dayBar = winBar(groupWin(games, (g) => g.dow), [0, 1, 2, 3, 4, 5, 6], "Win%");
  plot(chartBox(el, "Skuteczność wg dni"), [{ ...dayBar, x: dayBar.x.map((d) => DAYS[d]) }], { ...LINE50, yaxis: { range: [0, 100], title: { text: "Win %" } } });

  const hm = dayHourGrid(games);
  const hmBox = chartBox(el, "Kiedy grasz najlepiej (dzień × godzina)");
  hmBox.classList.add("tall");
  plot(hmBox, [{
    type: "heatmap", x: hours, y: DAYS, z: hm.z, customdata: hm.n, zmin: 30, zmax: 70, xgap: 2, ygap: 2,
    colorscale: [[0, css("--loss")], [0.5, css("--grid")], [1, css("--win")]],
    hovertemplate: "%{y}, %{x}:00 · win %{z}% (%{customdata} partii)<extra></extra>", hoverongaps: false,
    colorbar: { title: { text: "Win %" }, thickness: 10, outlinewidth: 0 },
  }], { yaxis: { autorange: "reversed", showgrid: false }, xaxis: { dtick: isNarrow() ? 3 : 1, showgrid: false }, margin: { l: 40, r: 10, t: 10, b: 30 } });
  el.insertAdjacentHTML("beforeend", `<div class="info small">Puste pola: mniej niż 3 partie w danej godzinie i dniu.</div>`);

  plot(chartBox(el, "Skuteczność wg długości partii"), [winBar(groupWin(games, (g) => lengthBin(g.moves)), LENGTH_BINS, "Win%")], { ...LINE50, yaxis: { range: [0, 100], title: { text: "Win %" } }, xaxis: { type: "category", title: { text: "Ruchy" } } });

  const pace = movePace(games);
  if (pace.length) plot(chartBox(el, "Tempo ruchu w trakcie partii"), [{ type: "scatter", mode: "lines+markers", x: pace.map((p) => p.label), y: pace.map((p) => p.avg), line: { color: css("--accent") }, name: "s / ruch" }], { yaxis: { title: { text: "Śr. sekundy / ruch" } }, xaxis: { type: "category", title: { text: "Segment partii (%)" } } });
  else { el.insertAdjacentHTML("beforeend", "<h3>Tempo ruchu w trakcie partii</h3>"); info(el, "Brak danych zegara dla wybranych partii."); }

  const st = streakEffect(games);
  el.insertAdjacentHTML("beforeend", `<h3 title="Wynik kolejnej partii po serii w obrębie jednej sesji (przerwa < 2 h)">Wpływ serii na wyniki ⓘ</h3>`);
  if (!st.length) return info(el, "Za mało partii w sesjach.");
  const box = chartBox(el);
  plot(box, ["Po serii wygranych", "Po serii porażek"].map((type, i) => {
    const r = st.filter((x) => x.type === type);
    return { type: "bar", name: type, x: r.map((x) => x.streak), y: r.map((x) => x.winPct), text: r.map((x) => `${x.winPct}%`), customdata: r.map((x) => x.n), hovertemplate: "%{x}: %{y}% (%{customdata} partii)<extra></extra>", textposition: "outside", marker: { color: i ? css("--loss") : css("--win") } };
  }), { barmode: "group", yaxis: { range: [0, 118], title: { text: "Win % następnej partii" } } });
}

function tabOpen(el, games) {
  const grid = document.createElement("div");
  grid.className = "grid2";
  el.appendChild(grid);
  const cols = [{ key: "name", label: "Debiut" }, { key: "n", label: "Gry", num: true }, { key: "winPct", label: "Win%", num: true, fmt: (v) => `${v}%` }, { key: "bar", label: "W / R / P", html: wdlBar }];
  const openGames = (group, color) => { state.anaPreset = { group, color }; switchTab("ana"); };
  for (const [c, label] of [["w", "⚪ Białe"], ["b", "⚫ Czarne"]]) {
    const box = document.createElement("div");
    grid.appendChild(box);
    box.insertAdjacentHTML("beforeend", `<h3>${label}</h3>`);
    const sub = games.filter((g) => g.color === c);
    if (!sub.length) { info(box, "Brak partii"); continue; }
    const rows = openingTable(sub, (g) => g.group, 15).map((r) => ({ ...r, group: r.name, name: tOpening(r.name, state.opLang) }));
    table(box, cols, rows, { onRow: (r) => openGames(r.group, c) });
    const det = document.createElement("details");
    det.innerHTML = `<summary style="cursor:pointer;margin:10px 0">Szczegółowe warianty</summary>`;
    box.appendChild(det);
    table(det, cols, openingTable(sub, (g) => g.opening, 20));
    box.insertAdjacentHTML("beforeend", `<div class="info small">Kliknij debiut, żeby zobaczyć jego partie.</div>`);
  }
  openingTreeBox(el, games);
}

// ----- Analiza silnikiem
let engineMod = null;
async function engine() {
  if (!engineMod) {
    engineMod = await import("./engine.js?v=47");
    engineMod.useCache(cacheGet, cacheSet);
  }
  return engineMod;
}
const sfKey = (g) => `sf|v3|${g.link}`; // ten sam klucz co w engine.js
// Kategorie ruchów jak na Chess.com: znaczek, nazwa i kolor.
const KIND = {
  brilliant: { mark: "!!", name: "Genialny ruch", short: "Genialne", color: "#1baca6", list: true },
  great: { mark: "!", name: "Świetny ruch", short: "Świetne", color: "#5c8bb0", list: true },
  best: { mark: "★", name: "Najlepszy ruch", short: "Najlepsze", color: "#81b64c" },
  excellent: { mark: "✓✓", name: "Znakomity ruch", short: "Znakomite", color: "#96bc4b" },
  good: { mark: "✓", name: "Dobry ruch", short: "Dobre", color: "#97af8b" },
  inaccuracy: { mark: "?!", name: "Niedokładność", short: "Niedokładności", color: "#e6b800", list: true, err: true },
  mistake: { mark: "?", name: "Błąd", short: "Błędy", color: "#e58f2a", list: true, err: true },
  miss: { mark: "✕", name: "Przeoczenie", short: "Przeoczenia", color: "#ff7769", list: true, err: true },
  blunder: { mark: "??", name: "Błąd rażący", short: "Błędy rażące", color: "#ca3431", list: true, err: true },
};
// Własne ikony SVG zamiast emoji (te same na każdym systemie).
const SVG = (d, fill) => `<svg viewBox="0 0 16 16" aria-hidden="true" ${fill ? 'fill="#fff"' : 'fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"'}>${d}</svg>`;
const KIND_ICON = {
  best: SVG('<path d="M8 1.4l1.9 4.1 4.5.5-3.3 3.1.9 4.4L8 11.2 4 13.5l.9-4.4L1.6 6l4.5-.5z"/>', true),
  excellent: SVG('<path d="M2.5 7h2.6v6.5H2.5zM6.2 7l2-4.1c1-.2 1.9.7 1.6 1.7L9.3 7h3.5c.9 0 1.5.8 1.3 1.6l-1.1 3.9c-.2.7-.8 1-1.4 1H6.2z"/>', true),
  good: SVG('<path d="M3 8.5l3.2 3.2L13 4.8"/>'),
  miss: SVG('<path d="M4 4l8 8M12 4l-8 8"/>'),
};
const badge = (kind, cls = "") => `<span class="bdg ${cls}${KIND_ICON[kind] ? " ico" : ""}" style="--bc:${KIND[kind].color}" title="${KIND[kind].name}">${KIND_ICON[kind] || KIND[kind].mark}</span>`;
// Powód błędu (z engine.explainMove) po polsku.
const PIECE_PL = { 1: "pion", 2: "dwa pionki", 3: "figurę", 4: "figurę i pionka", 5: "wieżę", 6: "wieżę i pionka", 8: "wieżę i figurę", 9: "hetmana" };
function whyText(w) {
  if (!w) return "";
  if (w.code === "missedMate") return `Przeoczony mat w ${w.n}`;
  if (w.code === "allowedMate") return `Dopuszczony mat rywala w ${w.n}`;
  if (w.code === "material") return `Strata materiału: ${PIECE_PL[w.pts] || `${w.pts} pkt`}`;
  if (w.code === "wasted") return "Zmarnowana przewaga";
  return "";
}
const isBadMove = (p) => p.mine && ["blunder", "mistake", "miss"].includes(p.kind);
const PHASES = [["open", "Debiut"], ["middle", "Gra środkowa"], ["end", "Końcówka"]];
const fmtEval = (v) => {
  if (Math.abs(v) > 9000) return `${v < 0 ? "−" : ""}M${Math.max(1, Math.round((10000 - Math.abs(v)) / 10))}`;
  const x = Math.abs(v / 100).toFixed(1);
  return v > 0 ? `+${x}` : v < 0 ? `−${x}` : "0.0";
};
const moveLabel = (p, i) => `${p.no}.${i % 2 ? ".." : ""} ${p.san}`;

// Otwiera (albo zamyka) panel analizy zaraz pod `anchor`.
async function openSfPanel(anchor, g) {
  const next = anchor.nextElementSibling;
  if (next?.classList.contains("sf-panel")) {
    const same = next.dataset.link === g.link;
    next.remove();
    if (same) return;
  }
  const panel = document.createElement("div");
  panel.className = "sf-panel card";
  panel.dataset.link = g.link;
  anchor.after(panel);
  runSf(panel, g);
}

async function runSf(panel, g, deep = false) {
  panel.innerHTML = `<div class="progress"><div class="bar"></div><span>Uruchamiam silnik…</span></div>
    <button class="link-btn sf-cancel">Anuluj</button>`;
  panel.querySelector(".sf-cancel").addEventListener("click", async () => { (await engine()).cancelAnalysis(); });
  try {
    const eng = await engine();
    const res = await eng.analyzeGame(g, {
      depth: deep ? eng.deepDepth() : eng.defaultDepth(),
      onProgress: (d, t) => {
        panel.querySelector(".bar").style.width = `${(d / t) * 100}%`;
        panel.querySelector(".progress span").textContent = `Analiza: pozycja ${d} z ${t}`;
      },
    });
    if (!res) return panel.remove();
    sfViewer(panel, g, res, eng, () => runSf(panel, g, true));
    document.querySelectorAll(`.gc-sf[data-link="${CSS.escape(g.link)}"]`).forEach((b) => (b.textContent = `🔍 ${Math.round(res.accuracy)}%`));
  } catch (err) {
    panel.innerHTML = `<div class="error">${esc(err.message || "Analiza się nie udała.")}</div>`;
  }
}

// Tabela ocen ruchów: Ty kontra rywal, jak podsumowanie partii na Chess.com.
function summaryTable(r) {
  const rows = KIND_LIST.filter((k) => r.counts[k] || r.countsOpp[k]).map((k) =>
    `<tr><td>${badge(k, "sm")} ${KIND[k].short}</td><td class="num${r.counts[k] ? "" : " zero"}">${r.counts[k]}</td><td class="num${r.countsOpp[k] ? "" : " zero"}">${r.countsOpp[k]}</td></tr>`).join("");
  return `<table class="sf-sum"><thead><tr><th></th><th class="num">Ty</th><th class="num">Rywal</th></tr></thead>
    <tbody><tr class="acc"><td>Celność</td><td class="num">${r.accuracy}%</td><td class="num">${r.accuracyOpp}%</td></tr>${rows}</tbody></table>`;
}
const KIND_LIST = ["brilliant", "great", "best", "excellent", "good", "inaccuracy", "mistake", "miss", "blunder"];

function sfViewer(panel, g, r, eng, onDeeper) {
  const N = r.plies.length;
  let flip = g.color === "b";
  const bad = r.plies.map((p, i) => ({ p, i })).filter(({ p }) => isBadMove(p));
  let cur = bad.length ? bad[0].i + 1 : N;

  panel.innerHTML = `
    <div class="sf-main">
      <div class="sf-boardcol">
        <div class="sf-boardwrap"><div class="evalbar"><div class="fill"></div><span></span></div><div class="board"></div></div>
        <div class="sf-nav">
          <button data-nav="first" aria-label="Początek">⏮</button><button data-nav="prev" aria-label="Poprzedni ruch">◀</button>
          <button data-nav="next" aria-label="Następny ruch">▶</button><button data-nav="last" aria-label="Koniec">⏭</button>
          <button data-nav="flip" aria-label="Obróć planszę (R)">⇅</button><button data-nav="full" aria-label="Pełny ekran (F)" title="Pełny ekran (F)">⛶</button>
          <div class="sf-nav2"><button data-nav="train" class="train-btn" title="Znajdź właściwy ruch w swoich błędach">🎯 Ćwicz błędy</button><button data-nav="err" class="err-btn">Następny błąd ›</button></div>
        </div>
      </div>
      <div class="sf-side">
        <div class="sf-info"></div>
        ${summaryTable(r)}
        <div class="sf-movelist"></div>
      </div>
    </div>`;
  const boardEl = panel.querySelector(".board"), info = panel.querySelector(".sf-info"), listEl = panel.querySelector(".sf-movelist");

  // Lista ruchów: numer, ruch białych, ruch czarnych.
  let rows = "";
  for (let i = 0; i < N; i += 2) {
    const cell = (j) => {
      const p = r.plies[j];
      if (!p) return "<span></span>";
      const k = KIND[p.kind];
      return `<button class="mv${p.mine ? "" : " opp"}" data-p="${j + 1}">${esc(p.san)}${k.list ? badge(p.kind, "sm") : ""}</button>`;
    };
    rows += `<span class="no">${i / 2 + 1}.</span>${cell(i)}${cell(i + 1)}`;
  }
  listEl.innerHTML = `<div class="mvgrid">${rows}</div>`;

  // Wykres oceny.
  const chart = chartBox(panel, "Ocena pozycji (dla białych)");
  chart.classList.add("short");
  const y = r.evals.map((v) => Math.max(-6, Math.min(6, v / 100)));
  const marks = r.plies.map((p, i) => ({ p, i })).filter(({ p }) => p.mine && ["brilliant", "great", "mistake", "miss", "blunder"].includes(p.kind));
  const cursor = () => [{ type: "line", x0: cur / 2, x1: cur / 2, yref: "paper", y0: 0, y1: 1, line: { color: css("--muted"), width: 1, dash: "dot" } }];
  plot(chart, [
    { type: "scatter", mode: "lines", x: y.map((_, i) => i / 2), y, fill: "tozeroy", line: { color: css("--accent"), width: 1.5 }, fillcolor: "rgba(129,182,76,.22)", hovertemplate: "ruch %{x:.1f}: %{y:+.1f}<extra></extra>" },
    { type: "scatter", mode: "markers", x: marks.map(({ i }) => (i + 1) / 2), y: marks.map(({ i }) => y[i + 1]), marker: { color: marks.map(({ p }) => KIND[p.kind].color), size: 10, line: { color: "#fff", width: 1 } }, text: marks.map(({ p, i }) => moveLabel(p, i) + KIND[p.kind].mark), hovertemplate: "%{text}<extra></extra>" },
  ], { showlegend: false, shapes: cursor(), yaxis: { range: [-6.3, 6.3], zeroline: true, title: { text: "pionki" } }, xaxis: { title: { text: "Ruch (kliknij, żeby przejść)" } }, margin: { l: 44, r: 10, t: 10, b: 40 } })
    .then(() => chart.on?.("plotly_click", (ev) => go(Math.round(ev.points[0].x * 2))));
  panel.insertAdjacentHTML("beforeend", `<div class="info small">Stockfish 18 lite w Twojej przeglądarce, głębokość ${r.depth || 12}. ${r.depth < eng.deepDepth() ? `<button class="link-btn sf-deeper">🔬 Głębsza analiza (ok. 4× dłużej)</button> ` : ""}Zielona strzałka: ostatnio zagrany ruch, niebieska: ruch, który należało zagrać zamiast niego. Oceny jak na Chess.com: genialny to dobre poświęcenie, świetny to jedyny dobry ruch, reszta zależy od tego, ile ruch zyskuje albo traci. Strzałki ← → na klawiaturze albo przesunięcie palcem po planszy zmieniają ruch.</div>`);

  const bestSanAt = (i) => (i < N ? r.plies[i].bestSan || r.plies[i].san : null);

  function update() {
    const last = cur ? r.plies[cur - 1] : null;
    // Zielona strzałka: ruch właśnie zagrany. Niebieska: ruch, który należało zagrać zamiast niego (z pozycji przed nim).
    const arrows = [];
    const instead = last && last.bestSan && (KIND[last.kind].err || last.drop >= 3) ? r.best?.[cur - 1] : null;
    if (last) arrows.push({ from: last.from, to: last.to, color: "#3aa655" });
    if (instead) arrows.push({ from: instead.slice(0, 2), to: instead.slice(2, 4), color: "#4a90d9" });

    renderBoard(boardEl, { fen: r.fens[cur], flip, anim: animate && last ? { from: last.from, to: last.to } : null, last: last ? [last.from, last.to] : null, lastColor: last && KIND[last.kind].list ? KIND[last.kind].color : "", arrows, badge: last ? { sq: last.to, html: badge(last.kind, "board") } : null });

    const ev = r.evals[cur];
    const white = eng.winChance(ev);
    const fill = panel.querySelector(".evalbar .fill");
    fill.style.height = `${white}%`;
    fill.style.top = flip ? "0" : "auto";
    fill.style.bottom = flip ? "auto" : "0";
    panel.querySelector(".evalbar span").textContent = fmtEval(ev);
    panel.querySelector(".evalbar span").className = (ev >= 0) !== flip ? "low" : "high";

    let html = "";
    if (!last) html = `<div class="sf-move">Pozycja początkowa</div>`;
    else {
      const k = KIND[last.kind];
      html = `<div class="sf-move">${badge(last.kind)} <b>${esc(moveLabel(last, cur - 1))}</b> <span class="muted">${last.mine ? "Twój ruch" : "ruch rywala"}</span></div>
        <div class="sf-verdict" style="--k:${k.color}"><b>${k.name}</b>${last.drop >= 1 ? ` · −${Math.round(last.drop)}% szans na wygraną` : ""}</div>
        ${whyText(last.why) ? `<div class="sf-why">${esc(whyText(last.why))}</div>` : ""}`;
      if (instead) html += `<div class="legend"><span><i style="background:#3aa655"></i>zagrany ruch</span><span><i style="background:#4a90d9"></i>ruch, który należało zagrać</span></div>`;
      if (last.bestSan && (k.err || last.kind === "good" || last.kind === "excellent")) {
        html += `<div class="${k.err ? "" : "muted"}">${k.err ? "Lepiej było" : "Najlepszy był"}: <b>${esc(k.err && last.line.length ? last.line.slice(0, 4).join(" ") : last.bestSan)}</b>${k.err ? ` <button class="link-btn" data-nav="prev">◀ pokaż</button>` : ""}</div>`;
      }
    }
    html += `<div class="muted">Ocena: <b>${fmtEval(ev)}</b>${bestSanAt(cur) ? ` · najlepsze teraz: <b>${esc(bestSanAt(cur))}</b>` : ""}</div>`;
    info.innerHTML = html;

    listEl.querySelectorAll(".mv.on").forEach((b) => b.classList.remove("on"));
    const on = listEl.querySelector(`.mv[data-p="${cur}"]`);
    if (on) {
      on.classList.add("on");
      const top = on.offsetTop; // listEl ma position: relative
      if (top < listEl.scrollTop || top > listEl.scrollTop + listEl.clientHeight - 30) listEl.scrollTop = top - listEl.clientHeight / 2;
    }
    if (chart.layout) window.Plotly.relayout(chart, { shapes: cursor() });
    panel.querySelector('[data-nav="err"]').disabled = !bad.length;
  }
  let animate = false;
  function go(i) { const n = Math.max(0, Math.min(N, i)); animate = n === cur + 1; cur = n; update(); animate = false; }
  function toggleFull(on = !panel.classList.contains("full")) {
    panel.classList.toggle("full", on);
    document.body.classList.toggle("noscroll", on);
    panel.querySelector('[data-nav="full"]').classList.toggle("on", on);
    if (chart.layout) window.Plotly.Plots.resize(chart);
  }
  panel._closeFull = () => toggleFull(false);

  panel.addEventListener("click", (e) => {
    const b = e.target.closest("[data-nav], [data-p]");
    if (!b) return;
    if (b.dataset.p) return go(Number(b.dataset.p));
    const nav = b.dataset.nav;
    if (nav === "first") go(0);
    else if (nav === "prev") go(cur - 1);
    else if (nav === "next") go(cur + 1);
    else if (nav === "last") go(N);
    else if (nav === "flip") { flip = !flip; update(); }
    else if (nav === "full") toggleFull();
    else if (nav === "train") startTrainer(panel, g, r, flip, () => update());
    else if (nav === "err" && bad.length) go((bad.find(({ i }) => i + 1 > cur) || bad[0]).i + 1);
  });
  panel.querySelector(".sf-deeper")?.addEventListener("click", onDeeper);
  panel.tabIndex = 0;
  panel.addEventListener("keydown", (e) => {
    if (panel.classList.contains("training")) return;
    const map = { ArrowLeft: cur - 1, ArrowRight: cur + 1, Home: 0, End: N };
    if (e.key in map) { e.preventDefault(); go(map[e.key]); }
    else if (e.key === "f" || e.key === "F") toggleFull();
    else if (e.key === "r" || e.key === "R") { flip = !flip; update(); }
    else if (e.key === "Escape" && panel.classList.contains("full")) toggleFull(false);
    else if (e.key === "j" || e.key === "J") go((bad.find(({ i }) => i + 1 > cur) || bad[0])?.i + 1);
    else if (e.key === "k" || e.key === "K") { const b = [...bad].reverse().find(({ i }) => i + 1 < cur) || bad[bad.length - 1]; if (b) go(b.i + 1); }
  });
  let tx = null;
  boardEl.addEventListener("touchstart", (e) => { tx = e.touches[0].clientX; }, { passive: true });
  boardEl.addEventListener("touchend", (e) => {
    if (tx === null) return;
    const dx = e.changedTouches[0].clientX - tx;
    if (Math.abs(dx) > 40) go(cur + (dx < 0 ? 1 : -1));
    tx = null;
  });
  update();
  panel.focus({ preventScroll: true });
}

// ----- Analiza wielu partii
function batchBox(el, getList) {
  el.insertAdjacentHTML("beforeend", `<details class="card sf-batch">
    <summary>📈 Analiza wielu partii naraz</summary>
    <div class="sf-batch-head">
      <div class="sf-batch-ctl"><label>Ostatnie <select id="b-n"><option>10</option><option selected>20</option><option>50</option><option>100</option></select> partii</label>
      <button id="b-go" class="primary">Analizuj</button></div></div>
    <div class="info small">Bierze partie z listy poniżej (z jej filtrami), od najnowszej.</div>
    <div id="b-prog"></div><div id="b-out"></div>
    <div class="info small">Partie już przeanalizowane są zapamiętane w przeglądarce, więc liczą się tylko nowe. Na telefonie jedna partia to kilka–kilkanaście sekund.</div>
  </details>`);
  let running = false;
  $("#b-go").addEventListener("click", async () => {
    const eng = await engine();
    if (running) { eng.cancelAnalysis(); return; }
    const games = getList().slice(0, Number($("#b-n").value));
    if (!games.length) return;
    running = true;
    $("#b-go").textContent = "Przerwij";
    $("#b-prog").innerHTML = `<div class="progress"><div class="bar"></div><span>Start…</span></div>`;
    const bar = $("#b-prog .bar"), lbl = $("#b-prog span");
    const { results, cancelled } = await eng.analyzeMany(games, {
      onProgress: (gi, gt, d, t) => {
        bar.style.width = `${((gi + (t ? d / t : 0)) / gt) * 100}%`;
        lbl.textContent = t ? `Partia ${gi + 1} z ${gt} · pozycja ${d}/${t}` : `Gotowe ${gi} z ${gt}`;
      },
      onResult: (g, r) => document.querySelectorAll(`.gc-sf[data-link="${CSS.escape(g.link)}"]`).forEach((b) => (b.textContent = `🔍 ${Math.round(r.accuracy)}%`)),
    });
    running = false;
    $("#b-go").textContent = "Analizuj";
    $("#b-prog").innerHTML = cancelled ? `<div class="info small">Przerwano. Pokazuję ${results.length} przeanalizowanych partii.</div>` : "";
    if (results.length) renderBatch($("#b-out"), results, eng);
  });
}

function renderBatch(out, results, eng) {
  out.innerHTML = "";
  const rs = results.slice().sort((a, b) => a.game.endTs - b.game.endTs);
  const n = rs.length;
  const avg = (f) => Math.round((rs.reduce((s, x) => s + f(x), 0) / n) * 10) / 10;
  out.insertAdjacentHTML("beforeend", `<div class="metrics">
    ${metric("Partie", n)}${metric("Średnia celność", `${avg((x) => x.res.accuracy)}%`)}
    ${metric("?? na partię", avg((x) => x.res.blunders))}${metric("? na partię", avg((x) => x.res.mistakes))}</div>`);

  // Celność w kolejnych partiach + średnia krocząca z 5.
  const acc = rs.map((x) => x.res.accuracy);
  const roll = acc.map((_, i) => { const w = acc.slice(Math.max(0, i - 4), i + 1); return Math.round((w.reduce((s, v) => s + v, 0) / w.length) * 10) / 10; });
  const resColor = { W: css("--win"), D: css("--draw"), L: css("--loss") };
  plot(chartBox(out, "Celność w kolejnych partiach"), [
    { type: "scatter", mode: "markers", name: "partia", x: rs.map((_, i) => i + 1), y: acc, marker: { color: rs.map((x) => resColor[x.game.result]), size: 8 }, text: rs.map((x) => `${x.game.day} vs ${x.game.opp}`), hovertemplate: "%{text}: %{y}%<extra></extra>" },
    { type: "scatter", mode: "lines", name: "średnia z 5", x: rs.map((_, i) => i + 1), y: roll, line: { color: css("--accent"), width: 2 } },
  ], { yaxis: { range: [0, 100], title: { text: "Celność %" } }, xaxis: { title: { text: "Partia (od najstarszej)" }, dtick: n > 20 ? 5 : 1 } });

  // Celność i błędy wg fazy.
  const ph = Object.fromEntries(PHASES.map(([k]) => [k, { acc: 0, moves: 0, blunder: 0, mistake: 0, inaccuracy: 0 }]));
  for (const { res } of rs) for (const p of res.plies) {
    if (!p.mine || !ph[p.phase]) continue;
    const e = ph[p.phase];
    e.moves++; e.acc += eng.moveAccuracy(p.drop);
    if (KIND[p.kind].err) e[p.kind === "miss" ? "mistake" : p.kind]++;
  }
  const phases = PHASES.filter(([k]) => ph[k].moves);
  const grid = document.createElement("div");
  grid.className = "grid2";
  out.appendChild(grid);
  const b1 = document.createElement("div"), b2 = document.createElement("div");
  grid.append(b1, b2);
  const phAcc = phases.map(([k]) => Math.round((ph[k].acc / ph[k].moves) * 10) / 10);
  plot(chartBox(b1, "Celność wg fazy partii"), [{ type: "bar", x: phases.map(([, l]) => l), y: phAcc, text: phAcc.map((v) => `${v}%`), textposition: "outside", marker: { color: css("--accent") }, customdata: phases.map(([k]) => ph[k].moves), hovertemplate: "%{x}: %{y}% (%{customdata} ruchów)<extra></extra>" }],
    { yaxis: { range: [0, 110], title: { text: "Celność %" } } });
  const per100 = (k, kind) => Math.round((ph[k][kind] / ph[k].moves) * 1000) / 10;
  plot(chartBox(b2, "Błędy na 100 Twoich ruchów"), ["blunder", "mistake", "inaccuracy"].map((kind) => ({
    type: "bar", name: KIND[kind].mark + " " + KIND[kind].name.toLowerCase(), x: phases.map(([, l]) => l), y: phases.map(([k]) => per100(k, kind)), marker: { color: KIND[kind].color },
  })), { barmode: "stack" });
  if (phases.length > 1) {
    const worst = phases[phAcc.indexOf(Math.min(...phAcc))];
    info(out, `Najwięcej tracisz w fazie: ${worst[1].toLowerCase()} (celność ${Math.min(...phAcc)}%). Debiut = ruchy 1–12, końcówka = najwyżej 6 figur na planszy.`);
  }

  const pats = patterns(rs);
  if (pats.length) out.insertAdjacentHTML("beforeend", `<h3>Wzorce w Twojej grze</h3><ul class="patterns">${pats.map((x) => `<li>${esc(x.text)}</li>`).join("")}</ul>`);

  out.insertAdjacentHTML("beforeend", "<h3>Najsłabsze partie</h3>");
  const resName = RESULT_ICON;
  const worstGames = rs.slice().sort((a, b) => a.res.accuracy - b.res.accuracy).slice(0, 5);
  const wrap = document.createElement("div");
  out.appendChild(wrap);
  table(wrap, [
    { key: "day", label: "Data", nowrap: true, fmt: (d) => `${d.slice(8, 10)}.${d.slice(5, 7)}` }, { key: "opp", label: "Rywal", fmt: (v) => shortName(v, 14) }, { key: "res", label: "Wynik" },
    { key: "acc", label: "Celność", num: true, fmt: (v) => `${v}%` }, { key: "bl", label: "??", num: true },
  ], worstGames.map((x) => ({ day: x.game.day, opp: x.game.opp, res: resName[x.game.result], acc: x.res.accuracy, bl: x.res.blunders, g: x.game })),
  { onRow: (row) => openSfPanel(wrap, row.g) });
  info(out, "Kliknij partię, żeby otworzyć ją na szachownicy.");
}

const RESULT_ICON = { W: "🟢", L: "🔴", D: "⚪️" };
const MODE_ICON = { Blitz: "⚡️", Rapid: "😴", Bullet: "💨" };

function tabAnalysis(el, games) {
  const preset = state.anaPreset || {};
  state.anaPreset = null;
  const groups = [...new Set(games.map((g) => g.group))].sort((a, b) => tOpening(a, state.opLang).localeCompare(tOpening(b, state.opLang)));
  el.insertAdjacentHTML("beforeend", `<div class="game-pick">
    <label>Rywal <input id="a-opp" autocomplete="off" placeholder="Szukaj po nicku"></label>
    <label>Debiut <select id="a-group"><option value="">Wszystkie</option>${groups.map((g) => `<option value="${esc(g)}">${esc(tOpening(g, state.opLang))}</option>`).join("")}</select></label>
    <label>Wynik <select id="a-res"><option value="">Wszystkie</option><option value="W">Wygrane</option><option value="D">Remisy</option><option value="L">Przegrane</option></select></label>
    <label>Dzień <input type="date" id="a-day"></label>
  </div>
  <div id="a-count" class="info small"></div>
  <div id="a-list" class="game-list"></div>
  <button id="a-more" class="more hidden">Pokaż więcej</button>`);
  batchBox(el, () => list);
  if (preset.group) $("#a-group").value = preset.group;
  if (preset.opp) $("#a-opp").value = preset.opp;

  const PAGE = 25;
  let list = [], shown = 0;
  const card = (g, i) => {
    const res = { W: ["Wygrana", "win"], D: ["Remis", "draw"], L: ["Porażka", "loss"] }[g.result];
    const time = `${g.day} ${String(g.hour).padStart(2, "0")}:${String(g.date.getMinutes()).padStart(2, "0")}`;
    return `<div class="game-card ${res[1]}">
      <div class="gc-main">
        <div class="gc-top"><b class="gc-res">${res[0]}</b> <span class="gc-meta">${MODE_ICON[g.mode] || ""} ${g.mode} · ${g.color === "w" ? "⚪" : "⚫"} · ${g.moves} ruchów · ${time}</span></div>
        <div class="gc-opp">vs <b>${esc(g.opp)}</b> (${g.oppElo}) · Ty: ${g.elo}</div>
        <div class="gc-open">${esc(tOpening(g.group, state.opLang))}${g.opening && g.opening !== g.group ? ` · <span class="muted">${esc(g.opening)}</span>` : ""}</div>
      </div>
      <div class="gc-actions">
        ${g.link ? `<a href="${esc(g.link)}" target="_blank" rel="noopener">${g.platform === "Lichess" ? "Lichess" : "Chess.com"}</a>` : ""}
        ${g.platform === "Lichess" ? "" : `<button data-i="${i}" class="gc-ana">Analiza Lichess</button>`}
        ${g.link ? `<button data-i="${i}" data-link="${esc(g.link)}" class="gc-sf">🔍 Stockfish</button>` : ""}
      </div>
    </div>`;
  };
  const draw = () => {
    const page = list.slice(shown, shown + PAGE);
    $("#a-list").insertAdjacentHTML("beforeend", page.map((g, j) => card(g, shown + j)).join(""));
    // Partie przeanalizowane wcześniej: pokazujemy celność na przycisku.
    page.forEach(async (g) => {
      if (!g.link) return;
      const r = await cacheGet(sfKey(g));
      if (r) document.querySelectorAll(`.gc-sf[data-link="${CSS.escape(g.link)}"]`).forEach((b) => (b.textContent = `🔍 ${Math.round(r.accuracy)}%`));
    });
    shown = Math.min(shown + PAGE, list.length);
    $("#a-more").classList.toggle("hidden", shown >= list.length);
  };
  const refill = () => {
    const opp = $("#a-opp").value.trim().toLowerCase(), grp = $("#a-group").value, r = $("#a-res").value, day = $("#a-day").value;
    list = games.filter((g) => (!opp || g.opp.toLowerCase().includes(opp)) && (!grp || g.group === grp) && (!r || g.result === r)
      && (!day || g.day === day) && (!preset.color || !grp || g.color === preset.color)).slice().reverse();
    $("#a-count").textContent = list.length ? `${list.length} partii, od najnowszej.` : "Brak partii dla podanych kryteriów.";
    $("#a-list").innerHTML = ""; shown = 0;
    draw();
  };
  ["#a-opp", "#a-group", "#a-res", "#a-day"].forEach((sel) => $(sel).addEventListener("input", () => { preset.color = null; refill(); }));
  $("#a-more").addEventListener("click", draw);
  $("#a-list").addEventListener("click", async (e) => {
    const sf = e.target.closest(".gc-sf");
    if (sf) return openSfPanel(sf.closest(".game-card"), list[Number(sf.dataset.i)]);
    const btn = e.target.closest(".gc-ana");
    if (!btn) return;
    const g = list[Number(btn.dataset.i)];
    btn.disabled = true; btn.textContent = "Wysyłanie...";
    const url = await importToLichess(g.pgn);
    if (url) {
      btn.outerHTML = `<a href="${esc(url)}" target="_blank" rel="noopener" class="primary-link">Otwórz analizę ➡️</a>`;
      window.open(url, "_blank", "noopener");
    } else {
      try { await navigator.clipboard.writeText(g.pgn); } catch { /* brak uprawnień */ }
      btn.outerHTML = `<a href="https://lichess.org/paste" target="_blank" rel="noopener">PGN w schowku → wklej na Lichess</a>`;
    }
  });
  refill();
}

// ----- Porównanie
const names = () => [state.data.name, state.rival.name];

function tabCompareStats(el, g1, g2) {
  const [u1, u2] = names();
  const c1 = counts(g1), c2 = counts(g2);
  el.insertAdjacentHTML("beforeend", `<div class="metrics">
    ${metric("Partie", `${c1.n} / ${c2.n}`)}
    ${metric("Win%", `${pct(c1.W, c1.n)}% / ${pct(c2.W, c2.n)}%`)}
    ${metric("Remisy", `${pct(c1.D, c1.n)}% / ${pct(c2.D, c2.n)}%`)}
    ${metric("Porażki", `${pct(c1.L, c1.n)}% / ${pct(c2.L, c2.n)}%`)}
    ${metric("Czas gry", `${totalHours(g1)} h / ${totalHours(g2)} h`)}</div>`);

  const grid = document.createElement("div");
  grid.className = "grid3";
  el.appendChild(grid);
  for (const m of MODES.slice().reverse()) {
    const a = g1.filter((g) => g.mode === m), b = g2.filter((g) => g.mode === m);
    if (!a.length && !b.length) continue;
    const box = document.createElement("div");
    grid.appendChild(box);
    plot(chartBox(box, `ELO ${m}`), [[a, u1, "--p1"], [b, u2, "--p2"]].filter(([l]) => l.length).flatMap(([l, n, c]) => eloTraces(l, n, css(c))), eloLayout());
  }

  const grid2 = document.createElement("div");
  grid2.className = "grid2";
  el.appendChild(grid2);
  for (const [res, title] of [["W", "Jak wygrywają?"], ["L", "Jak przegrywają?"]]) {
    const box = document.createElement("div");
    grid2.appendChild(box);
    const traces = [[g1, u1, "--p1"], [g2, u2, "--p2"]].map(([l, n, c]) => {
      const r = reasonShares(l, res);
      return { type: "bar", name: n, x: r.items.map(([k]) => tReason(k)), y: r.items.map(([, v]) => Math.round((v / r.total) * 1000) / 10), text: r.items.map(([, v]) => `${Math.round((v / r.total) * 100)}%`), customdata: r.items.map(([, v]) => v), textposition: isNarrow() ? "none" : "outside", cliponaxis: false, hovertemplate: "%{x}: %{customdata} partii (%{y}%)<extra>%{fullData.name}</extra>", marker: { color: css(c) } };
    });
    plot(chartBox(box, title), traces, { barmode: "group", yaxis: { title: { text: "%" } } });
  }
}

function tabCompareHist(el, g1, g2) {
  const [u1, u2] = names();
  const b = activityBucket(mergeGames(g1, g2));
  const perDay = (l) => { const m = new Map(); l.forEach((g) => m.set(b.key(g), (m.get(b.key(g)) || 0) + 1)); return [...m].sort(); };
  plot(chartBox(el, `Porównanie aktywności (partie na ${b.label})`), [[g1, u1, "--p1"], [g2, u2, "--p2"]].map(([l, n, c]) => {
    const d = perDay(l);
    return { type: "bar", name: n, x: d.map(([k]) => k), y: d.map(([, v]) => v), marker: { color: css(c) } };
  }), { barmode: "group", xaxis: { type: "date", tickformat: b.label === "dzień" ? "%d.%m" : "%m.%Y" } });
  const per = (l) => { const m = new Map(); l.forEach((g) => m.set(g.month, (m.get(g.month) || 0) + 1)); return m; };
  const m1 = per(g1), m2 = per(g2);
  const months = [...new Set([...m1.keys(), ...m2.keys()])].sort().reverse();
  el.insertAdjacentHTML("beforeend", "<h3>Partie miesięcznie</h3>");
  table(el, [{ key: "month", label: "Miesiąc", nowrap: true }, { key: "a", label: shortName(u1), num: true }, { key: "b", label: shortName(u2), num: true }],
    months.map((month) => ({ month, a: m1.get(month) || 0, b: m2.get(month) || 0 })), { scroll: true });
}

function tabCompareTime(el, g1, g2) {
  const [u1, u2] = names();
  const pair = (keyFn, order, labelFn = (x) => x) => [[g1, u1, "--p1"], [g2, u2, "--p2"]].map(([l, n, c]) => {
    const t = winBar(groupWin(l, keyFn), order, n, css(c));
    return { ...t, x: t.x.map(labelFn) };
  });
  plot(chartBox(el, "Skuteczność wg godzin"), pair((g) => g.hour, Array.from({ length: 24 }, (_, i) => i)), { ...LINE50, barmode: "group", yaxis: { range: [0, 100], title: { text: "Win %" } }, xaxis: { dtick: isNarrow() ? 3 : 1 } });
  plot(chartBox(el, "Skuteczność wg dni"), pair((g) => g.dow, [0, 1, 2, 3, 4, 5, 6], (d) => DAYS[d]), { ...LINE50, barmode: "group", yaxis: { range: [0, 100], title: { text: "Win %" } }, xaxis: { categoryorder: "array", categoryarray: DAYS } });
  plot(chartBox(el, "Skuteczność wg długości partii"), pair((g) => lengthBin(g.moves), LENGTH_BINS), { ...LINE50, barmode: "group", yaxis: { range: [0, 100], title: { text: "Win %" } }, xaxis: { type: "category", categoryorder: "array", categoryarray: LENGTH_BINS } });
  const p = [[g1, u1, "--p1"], [g2, u2, "--p2"]].map(([l, n, c]) => { const r = movePace(l); return { type: "scatter", mode: "lines+markers", name: n, x: r.map((x) => x.label), y: r.map((x) => x.avg), line: { color: css(c) } }; });
  if (p.some((t) => t.x.length)) plot(chartBox(el, "Tempo ruchu w trakcie partii"), p, { yaxis: { title: { text: "Śr. sekundy / ruch" } }, xaxis: { type: "category" } });
}

function tabCompareOpen(el, g1, g2) {
  const [u1, u2] = names();
  el.insertAdjacentHTML("beforeend", `<div class="info">1 = <b style="color:var(--p1)">${esc(u1)}</b> · 2 = <b style="color:var(--p2)">${esc(u2)}</b> · % = skuteczność (win%)</div>`);
  const grid = document.createElement("div");
  grid.className = "grid2";
  el.appendChild(grid);
  for (const [c, label] of [["w", "⚪ Białe"], ["b", "⚫ Czarne"]]) {
    const box = document.createElement("div");
    grid.appendChild(box);
    box.insertAdjacentHTML("beforeend", `<h3>${label}</h3>`);
    const key = (g) => tOpening(g.group, state.opLang);
    const a = groupWin(g1.filter((g) => g.color === c), key), b = groupWin(g2.filter((g) => g.color === c), key);
    const rows = [...new Set([...a.keys(), ...b.keys()])].map((name) => ({
      name, an: a.get(name)?.n || 0, aw: a.get(name)?.winPct || 0, bn: b.get(name)?.n || 0, bw: b.get(name)?.winPct || 0,
    })).sort((x, y) => y.an + y.bn - (x.an + x.bn)).slice(0, 20);
    if (!rows.length) { info(box, "Brak partii"); continue; }
    table(box, [
      { key: "name", label: "Debiut" }, { key: "an", label: "Gry 1", num: true }, { key: "aw", label: "% 1", num: true, fmt: (v) => `${v}%` },
      { key: "bn", label: "Gry 2", num: true }, { key: "bw", label: "% 2", num: true, fmt: (v) => `${v}%` },
    ], rows);
  }
}

function tabH2H(el, g1) {
  const [u1, u2] = names();
  const h = g1.filter((g) => g.opp.toLowerCase() === state.rival.user.toLowerCase() && g.platform === state.rival.plat);
  if (!h.length) return info(el, `Brak bezpośrednich partii między ${u1} a ${u2} (przy obecnych filtrach).`);
  const c = counts(h);
  el.insertAdjacentHTML("beforeend", `<div class="h2h">
    <div><div class="name" style="color:var(--p1)" title="${esc(u1)}">${esc(u1)}</div><div class="score" style="color:var(--p1)">${c.W}</div></div>
    <div><div class="name">REMISY</div><div class="score">${c.D}</div></div>
    <div><div class="name" style="color:var(--p2)" title="${esc(u2)}">${esc(u2)}</div><div class="score" style="color:var(--p2)">${c.L}</div></div></div>`);
  let w = 0, l = 0;
  const cw = h.map((g) => (w += g.result === "W")), cl = h.map((g) => (l += g.result === "L"));
  const x = h.map((_, i) => i + 1);
  plot(chartBox(el, "Wyścig zwycięstw"), [
    { type: "scatter", mode: "lines", name: u1, x, y: cw, line: { color: css("--p1") } },
    { type: "scatter", mode: "lines", name: u2, x, y: cl, line: { color: css("--p2") } },
  ], { xaxis: { title: { text: "Nr partii" } }, yaxis: { title: { text: "Suma zwycięstw" } } });
  el.insertAdjacentHTML("beforeend", "<h3>Historia spotkań</h3>");
  const res = { W: "Wygrana", D: "Remis", L: "Porażka" };
  table(el, [{ key: "day", label: "Data", nowrap: true }, { key: "mode", label: "Tryb" }, { key: "res", label: "Wynik", nowrap: true }, { key: "moves", label: "Ruchy", num: true }, { key: "opening", label: "Debiut" }],
    h.slice().reverse().map((g) => ({ ...g, res: `${g.color === "w" ? "⚪" : "⚫"} ${res[g.result]}` })), { scroll: true });
}

// ---------------------------------------------------------------- start
function setScope(scope) {
  state.scope = scope;
  document.querySelectorAll("#scope button").forEach((b) => b.classList.toggle("on", b.dataset.scope === scope));
  $("#p2-row").classList.toggle("hidden", scope === "single");
  $("#p2-nick").required = scope !== "single";
  $("#start-btn").textContent = { single: "Analizuj", merge: "Połącz i analizuj", compare: "Uruchom porównanie" }[scope];
  if (scope === "merge") $("#p2-plat").value = $("#p1-plat").value === "Lichess" ? "Chess.com" : "Lichess";
}

let wasNarrow = isNarrow();
window.addEventListener("resize", () => {
  if (isNarrow() !== wasNarrow) { wasNarrow = isNarrow(); renderTab(); }
});

function init() {
  $("#theme").value = store.get("theme", "chesscom");
  applyTheme($("#theme").value);
  $("#op-lang").value = state.opLang;
  $("#theme").addEventListener("change", (e) => applyTheme(e.target.value));
  $("#op-lang").addEventListener("change", (e) => { state.opLang = e.target.value; store.set("opLang", state.opLang); renderTab(); });

  document.querySelectorAll("#scope button").forEach((b) => b.addEventListener("click", () => setScope(b.dataset.scope)));
  $("#start-form").addEventListener("submit", startAnalysis);
  $("#refresh-btn").addEventListener("click", refresh);
  $("#change-btn").addEventListener("click", changePlayer);
  $("#rival-form").addEventListener("submit", loadRival);
  document.querySelectorAll("#view button").forEach((b) => b.addEventListener("click", () => { state.view = b.dataset.view; state.tab = null; renderResults(); }));
  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.tab === "__rival") { state.rival = null; renderResults(); return; }
    state.tab = b.dataset.tab;
    store.set("tab:" + (state.view === "compare" ? "cmp" : "my"), state.tab);
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
    renderTab();
  });
  ["#f-from", "#f-to"].forEach((s) => $(s).addEventListener("change", () => {
    document.querySelectorAll("#presets button").forEach((b) => b.classList.remove("on"));
    readFilters();
  }));
  $("#f-mode").addEventListener("change", () => readFilters());
  ["#f-h1", "#f-h2"].forEach((s) => {
    $(s).addEventListener("input", () => { $("#f-hours-label").textContent = `${Math.min($("#f-h1").value, $("#f-h2").value)}:00 – ${Math.max($("#f-h1").value, $("#f-h2").value)}:59`; });
    $(s).addEventListener("change", () => readFilters());
  });
  document.querySelectorAll("#presets button").forEach((b) => b.addEventListener("click", () => { setPreset(Number(b.dataset.days)); readFilters(); }));
  $("#share-btn").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(location.href); toast("Link skopiowany"); }
    catch { toast("Nie udało się skopiować. Skopiuj adres z paska przeglądarki."); }
  });
  renderRecent();
  if ("serviceWorker" in navigator) {
    const controlled = !!navigator.serviceWorker.controller;
    navigator.serviceWorker.register("sw.js").catch(() => {});
    // Pierwsza wizyta na komputerze: gdy service worker przejmie stronę, przeładowujemy ją raz, żeby dostała
    // nagłówki izolacji (wielowątkowy silnik). Pomijamy, gdy analiza już trwa albo to telefon.
    const desktop = (navigator.hardwareConcurrency || 0) >= 4 && !/Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
    if (!controlled && desktop && !self.crossOriginIsolated) {
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        let done = false;
        try { done = sessionStorage.getItem("coi-reload") === "1"; sessionStorage.setItem("coi-reload", "1"); } catch { done = true; }
        if (!done && $("#results").classList.contains("hidden")) location.reload();
      });
    }
  }
  ["#f-white", "#f-black"].forEach((s) => $(s).addEventListener("click", () => { $(s).classList.toggle("on"); readFilters(); }));

  // Link z nickiem (?user=...&platform=...) od razu uruchamia analizę i działa jako zakładka.
  const q = new URLSearchParams(location.search);
  const scope = ["merge", "compare"].includes(q.get("mode")) && q.get("user2") ? q.get("mode") : "single";
  if (q.get("platform")) $("#p1-plat").value = q.get("platform") === "Lichess" ? "Lichess" : "Chess.com";
  setScope(scope);
  if (q.get("platform2")) $("#p2-plat").value = q.get("platform2") === "Lichess" ? "Lichess" : "Chess.com";
  if (q.get("user2")) $("#p2-nick").value = q.get("user2");
  if (q.get("user")) {
    $("#p1-nick").value = q.get("user");
    startAnalysis();
  } else {
    $("#p1-nick").value = store.get("lastNick", "");
  }
  $("#p1-nick").addEventListener("change", (e) => store.set("lastNick", e.target.value.trim()));
}

init();
