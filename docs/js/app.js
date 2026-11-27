import { fetchPlayer, importToLichess, PlayerNotFound, ApiError } from "./api.js";
import { addLocalTime, DAYS, MODES } from "./parse.js";
import { tOpening, tReason } from "./i18n.js";
import {
  LENGTH_BINS, lengthBin, pct, filterGames, counts, groupWin, eloSummary, totalHours,
  mostCommon, movePace, streakEffect, openingTable, reasonShares, dayHourGrid, calendarGrid,
} from "./stats.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

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
  requestAnimationFrame(() => window.Plotly.react(el, traces, merged, { displayModeBar: false, responsive: true }));
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

const MY_TABS = [["stats", "📊 Statystyki"], ["hist", "📅 Historia"], ["time", "⏳ Czas"], ["open", "🔬 Debiuty"], ["ana", "🧠 Analiza"]];
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
  ({ stats: tabStats, hist: tabHist, time: tabTime, open: tabOpen, ana: tabAnalysis })[state.tab](el, g1);
  fitCharts();
}

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x.dataset.tab === tab));
  renderTab();
  $("#tabs").scrollIntoView({ behavior: "smooth", block: "start" });
}

// Wykresy w siatce rysowane są zanim siatka ułoży kolumny, więc po renderze dopasowujemy szerokość.
function fitCharts() {
  requestAnimationFrame(() => document.querySelectorAll("#tab-content .js-plotly-plot").forEach((c) => window.Plotly.Plots.resize(c)));
}

// ----- Moja analiza
function tabStats(el, games) {
  const c = counts(games);
  el.insertAdjacentHTML("beforeend", `<div class="metrics">
    ${metric("Partie", c.n)}${metric("W / R / P", `${c.W} / ${c.D} / ${c.L}`)}
    ${metric("Win%", `${pct(c.W, c.n)}%`)}${metric("Czas gry", `${totalHours(games)} h`)}</div>`);
  const favW = mostCommon(games.filter((g) => g.color === "w").map((g) => g.group));
  const favB = mostCommon(games.filter((g) => g.color === "b").map((g) => g.group));
  el.insertAdjacentHTML("beforeend", `<div class="callout"><b>Ulubione debiuty:</b><br>⚪ <b>${esc(favW ? tOpening(favW, state.opLang) : "Brak")}</b> &emsp;|&emsp; ⚫ <b>${esc(favB ? tOpening(favB, state.opLang) : "Brak")}</b></div>`);

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
// Polskie etykiety miesięcy: pierwszy tydzień każdego miesiąca.
function monthTicks(weeks) {
  const tickvals = [], ticktext = [];
  let last = -1;
  for (const w of weeks) {
    const m = Number(w.slice(5, 7)) - 1;
    if (m !== last) { tickvals.push(w); ticktext.push(MONTHS_PL[m]); last = m; }
  }
  return { tickvals: tickvals.slice(1), ticktext: ticktext.slice(1) };
}

function tabHist(el, games) {
  const cal = calendarGrid(games, games[games.length - 1].day);
  const calBox = chartBox(el, "Kalendarz aktywności (ostatnie 12 miesięcy)");
  calBox.classList.add("calendar");
  plot(calBox, [{
    type: "heatmap", x: cal.weeks, y: DAYS, z: cal.z, text: cal.text, xgap: 3, ygap: 3,
    colorscale: [[0, css("--bg")], [0.0001, css("--grid")], [1, css("--accent")]], zmin: 0,
    hovertemplate: "%{text}: %{z} partii<extra></extra>", hoverongaps: false, showscale: false,
  }], { yaxis: { autorange: "reversed", showgrid: false, fixedrange: true }, xaxis: { type: "date", showgrid: false, fixedrange: true, ...monthTicks(cal.weeks) }, margin: { l: 36, r: 10, t: 10, b: 24 } });

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
  const wdl = (r) => `<div class="wdl" title="W ${r.w} / R ${r.d} / P ${r.l}"><i style="width:${(r.w / r.n) * 100}%;background:var(--win)"></i><i style="width:${(r.d / r.n) * 100}%;background:var(--draw)"></i><i style="width:${(r.l / r.n) * 100}%;background:var(--loss)"></i></div>`;
  const cols = [{ key: "name", label: "Debiut" }, { key: "n", label: "Gry", num: true }, { key: "winPct", label: "Win%", num: true, fmt: (v) => `${v}%` }, { key: "bar", label: "W / R / P", html: wdl }];
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
  if (preset.group) $("#a-group").value = preset.group;

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
      </div>
    </div>`;
  };
  const draw = () => {
    $("#a-list").insertAdjacentHTML("beforeend", list.slice(shown, shown + PAGE).map((g, j) => card(g, shown + j)).join(""));
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
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
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
    const go = () => (window.Plotly ? startAnalysis() : setTimeout(go, 50));
    go();
  } else {
    $("#p1-nick").value = store.get("lastNick", "");
  }
  $("#p1-nick").addEventListener("change", (e) => store.set("lastNick", e.target.value.trim()));
}

init();
