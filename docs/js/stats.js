// Agregacje statystyk. Partie są posortowane od najstarszej.

export const LENGTH_BINS = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"];
export const lengthBin = (m) =>
  m <= 20 ? "0-20" : m <= 30 ? "21-30" : m <= 40 ? "31-40" : m <= 50 ? "41-50" : m <= 60 ? "51-60" : m <= 70 ? "61-70" : "71+";

export const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);

export function filterGames(games, f) {
  return games.filter((g) =>
    (!f.from || g.day >= f.from) && (!f.to || g.day <= f.to) &&
    (!f.mode || g.mode === f.mode) &&
    f.colors.includes(g.color) &&
    g.hour >= f.hourMin && g.hour <= f.hourMax);
}

export function counts(games) {
  const c = { W: 0, D: 0, L: 0, n: games.length };
  for (const g of games) c[g.result]++;
  return c;
}

// key → {n, w, winPct}
export function groupWin(games, keyFn) {
  const m = new Map();
  for (const g of games) {
    const k = keyFn(g);
    const e = m.get(k) || { n: 0, w: 0, d: 0, l: 0 };
    e.n++;
    if (g.result === "W") e.w++; else if (g.result === "D") e.d++; else e.l++;
    m.set(k, e);
  }
  for (const e of m.values()) e.winPct = pct(e.w, e.n);
  return m;
}

// Peak i aktualne ELO w trybie; przy kilku kontach bierzemy najlepsze.
export function eloSummary(games, mode) {
  const byAcc = new Map();
  for (const g of games) if (g.mode === mode) byAcc.set(g.account, [...(byAcc.get(g.account) || []), g]);
  if (!byAcc.size) return null;
  let peak = -1, current = -1;
  for (const list of byAcc.values()) {
    peak = Math.max(peak, ...list.map((g) => g.elo));
    current = Math.max(current, list[list.length - 1].elo); // ostatnia = najnowsza
  }
  return { peak, current };
}

export function totalHours(games) {
  let sec = 0;
  for (const g of games) for (const t of g.moveTimes) sec += t;
  if (sec > 0) return Math.round((sec / 3600) * 10) / 10;
  const est = { Bullet: 2, Blitz: 4, Rapid: 15 };
  const min = games.reduce((s, g) => s + (est[g.mode] ?? g.moves * 0.5 / 60), 0);
  return Math.round((min / 60) * 10) / 10;
}

export function mostCommon(values) {
  const m = new Map();
  for (const v of values) m.set(v, (m.get(v) || 0) + 1);
  let best = null, bn = 0;
  for (const [v, n] of m) if (n > bn) { best = v; bn = n; }
  return best;
}

// Średni czas ruchu w 10 segmentach partii.
export function movePace(games) {
  const labels = ["0-10", ...Array.from({ length: 9 }, (_, i) => `${(i + 1) * 10 + 1}-${(i + 2) * 10}`)];
  const sums = new Array(10).fill(0), ns = new Array(10).fill(0);
  let has = false;
  for (const g of games) {
    const v = g.moveTimes;
    if (v.length < 2) continue;
    has = true;
    v.forEach((t, i) => {
      const b = Math.min(Math.floor((i / v.length) * 10), 9);
      sums[b] += t; ns[b]++;
    });
  }
  if (!has) return [];
  return labels.map((label, i) => ({ label, avg: ns[i] ? Math.round((sums[i] / ns[i]) * 100) / 100 : null, n: ns[i] }))
    .filter((r) => r.avg !== null);
}

// Wynik po serii W/L w obrębie sesji (przerwa < 2 h).
export function streakEffect(games) {
  const SESSION_GAP = 7200;
  const buckets = new Map();
  let type = null, count = 0, lastTs = null;
  for (const g of games) {
    if (lastTs !== null && g.endTs - lastTs > SESSION_GAP) { type = null; count = 0; }
    if (type) {
      const key = `${type}|${Math.min(count, 5)}`;
      const e = buckets.get(key) || { n: 0, w: 0 };
      e.n++; if (g.result === "W") e.w++;
      buckets.set(key, e);
    }
    if (g.result === "W") { count = type === "W" ? count + 1 : 1; type = "W"; }
    else if (g.result === "L") { count = type === "L" ? count + 1 : 1; type = "L"; }
    else { type = null; count = 0; }
    lastTs = g.endTs;
  }
  const out = [];
  for (const [t, name] of [["W", "Po serii wygranych"], ["L", "Po serii porażek"]]) {
    for (let c = 1; c <= 5; c++) {
      const e = buckets.get(`${t}|${c}`);
      if (e) out.push({ type: name, streak: c === 5 ? "5+ z rzędu" : `${c} z rzędu`, winPct: pct(e.w, e.n), n: e.n });
    }
  }
  return out;
}

export function openingTable(games, keyFn, limit) {
  return [...groupWin(games, keyFn)].map(([name, e]) => ({ name, n: e.n, w: e.w, d: e.d, l: e.l, winPct: e.winPct }))
    .sort((a, b) => b.n - a.n).slice(0, limit);
}

export function reasonShares(games, result) {
  const sub = games.filter((g) => g.result === result);
  const m = new Map();
  for (const g of sub) m.set(g.reason, (m.get(g.reason) || 0) + 1);
  return { total: sub.length, items: [...m].sort((a, b) => b[1] - a[1]) };
}

// Skuteczność w siatce dzień tygodnia × godzina (null, gdy za mało partii).
export function dayHourGrid(games, minGames = 3) {
  const n = Array.from({ length: 7 }, () => new Array(24).fill(0));
  const w = Array.from({ length: 7 }, () => new Array(24).fill(0));
  for (const g of games) { n[g.dow][g.hour]++; if (g.result === "W") w[g.dow][g.hour]++; }
  const z = n.map((row, d) => row.map((c, h) => (c >= minGames ? pct(w[d][h], c) : null)));
  return { z, n };
}

// Liczba partii w każdym tygodniu (od poniedziałku): wiersz = rok, kolumna = tydzień roku (0–52).
// Tygodnie przed pierwszą i po ostatniej partii są puste (null).
export function weekGrid(games) {
  if (!games.length) return { years: [], z: [], text: [] };
  const DAY = 86400000;
  const mondayOf = (day) => {
    const d = new Date(`${day}T12:00:00`);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    return d;
  };
  const pad = (n) => String(n).padStart(2, "0");
  const cell = (d) => {
    const y = d.getFullYear();
    return [y, Math.floor(Math.round((d - new Date(y, 0, 1, 12)) / DAY) / 7)];
  };
  const perWeek = new Map();
  for (const g of games) {
    const k = cell(mondayOf(g.day)).join("|");
    perWeek.set(k, (perWeek.get(k) || 0) + 1);
  }
  const first = mondayOf(games[0].day), last = mondayOf(games[games.length - 1].day);
  const years = [];
  for (let y = first.getFullYear(); y <= last.getFullYear(); y++) years.push(y);
  const z = years.map(() => new Array(53).fill(null));
  const text = years.map(() => new Array(53).fill(""));
  for (let d = new Date(first); d <= last; d.setDate(d.getDate() + 7)) {
    const [y, w] = cell(d);
    const r = y - years[0];
    z[r][w] = perWeek.get(`${y}|${w}`) || 0;
    text[r][w] = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${y}`;
  }
  return { years, z, text };
}
