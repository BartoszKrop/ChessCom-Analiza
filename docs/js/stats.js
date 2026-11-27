// Agregacje statystyk. Partie są posortowane od najstarszej.

export const LENGTH_BINS = ["0-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71+"];
export const lengthBin = (m) =>
  m <= 20 ? "0-20" : m <= 30 ? "21-30" : m <= 40 ? "31-40" : m <= 50 ? "41-50" : m <= 60 ? "51-60" : m <= 70 ? "61-70" : "71+";

export const SESSION_GAP = 7200; // przerwa (s), po której zaczyna się nowa sesja

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

// Liczba partii w miesiącach: wiersz = rok, kolumna = miesiąc (0–11).
// Miesiące przed pierwszą i po ostatniej partii są puste (null).
export function monthGrid(games) {
  if (!games.length) return { years: [], z: [] };
  const per = new Map();
  for (const g of games) per.set(g.month, (per.get(g.month) || 0) + 1);
  const first = games[0].month, last = games[games.length - 1].month;
  const y0 = Number(first.slice(0, 4)), y1 = Number(last.slice(0, 4));
  const years = [], z = [];
  for (let y = y0; y <= y1; y++) {
    years.push(y);
    z.push(Array.from({ length: 12 }, (_, m) => {
      const k = `${y}-${String(m + 1).padStart(2, "0")}`;
      return k < first || k > last ? null : per.get(k) || 0;
    }));
  }
  return { years, z };
}

// Numer partii w sesji (przerwa > 2 h zaczyna nową sesję). Zwraca Map: "1".."9", "10+" → {n, w, winPct}.
export const SESSION_ORDER = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10+"];
export function sessionIndexWin(games) {
  let idx = 0, lastTs = null;
  const keyed = games.map((g) => {
    idx = lastTs !== null && g.endTs - lastTs <= SESSION_GAP ? idx + 1 : 1;
    lastTs = g.endTs;
    return { result: g.result, k: idx >= 10 ? "10+" : String(idx) };
  });
  return groupWin(keyed, (x) => x.k);
}

// Różnica rankingu (rywal − ja) w przedziałach co 100.
export const DIFF_ORDER = ["≤ −200", "−200…−101", "−100…−1", "0…99", "100…199", "≥ 200"];
export const diffBin = (d) => (d <= -200 ? DIFF_ORDER[0] : d <= -101 ? DIFF_ORDER[1] : d < 0 ? DIFF_ORDER[2] : d < 100 ? DIFF_ORDER[3] : d < 200 ? DIFF_ORDER[4] : DIFF_ORDER[5]);
export function ratingDiffWin(games) {
  return groupWin(games.filter((g) => g.elo && g.oppElo), (g) => diffBin(g.oppElo - g.elo));
}

// Porażki i wygrane na czas (Chess.com: timeout, Lichess: outoftime).
const ON_TIME = new Set(["timeout", "outoftime"]);
export function timeResults(games) {
  const out = [];
  for (const mode of [null, "Bullet", "Blitz", "Rapid"]) {
    const sub = mode ? games.filter((g) => g.mode === mode) : games;
    const losses = sub.filter((g) => g.result === "L"), wins = sub.filter((g) => g.result === "W");
    if (!sub.length) continue;
    const lt = losses.filter((g) => ON_TIME.has(g.reason)).length, wt = wins.filter((g) => ON_TIME.has(g.reason)).length;
    out.push({ mode: mode || "Wszystkie", losses: losses.length, lostOnTime: lt, lossPct: pct(lt, losses.length), wins: wins.length, wonOnTime: wt, winPct: pct(wt, wins.length) });
  }
  return out;
}

// Najczęstsi rywale (min. `minGames` partii).
export function opponents(games, minGames = 3) {
  const m = new Map();
  for (const g of games) {
    const k = `${g.opp}|${g.platform}`;
    const e = m.get(k) || { opp: g.opp, platform: g.platform, n: 0, w: 0, d: 0, l: 0, last: "" };
    e.n++; e[g.result === "W" ? "w" : g.result === "D" ? "d" : "l"]++; e.last = g.day;
    m.set(k, e);
  }
  return [...m.values()].filter((e) => e.n >= minGames && e.opp !== "Anonim")
    .map((e) => ({ ...e, winPct: pct(e.w, e.n), score: e.w - e.l }))
    .sort((a, b) => b.n - a.n);
}

// Podsumowanie miesiąca `month` (YYYY-MM) wobec poprzedniego.
export function prevMonth(month) {
  const [y, m] = month.split("-").map(Number);
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`;
}
export function monthSummary(games, month) {
  const sub = games.filter((g) => g.month === month);
  const c = counts(sub);
  const elo = {};
  for (const mode of ["Bullet", "Blitz", "Rapid"]) {
    const list = sub.filter((g) => g.mode === mode);
    if (!list.length) continue;
    const before = games.filter((g) => g.mode === mode && g.month < month && g.account === list[0].account);
    const start = before.length ? before[before.length - 1].elo : list[0].elo;
    elo[mode] = { end: list[list.length - 1].elo, change: list[list.length - 1].elo - start, n: list.length };
  }
  const ops = openingTable(sub, (g) => g.group, 1000).filter((o) => o.n >= 3);
  const byWin = ops.slice().sort((a, b) => b.winPct - a.winPct || b.n - a.n);
  return { month, n: c.n, w: c.W, d: c.D, l: c.L, winPct: pct(c.W, c.n), elo, best: byWin[0] || null, worst: byWin.length > 1 ? byWin[byWin.length - 1] : null };
}

// Drzewko debiutów: statystyki kolejnych ruchów po ścieżce `path` (lista posunięć SAN).
export function openingTree(games, path, movesOf) {
  const m = new Map();
  for (const g of games) {
    const mv = movesOf(g);
    if (mv.length <= path.length) continue;
    let ok = true;
    for (let i = 0; i < path.length; i++) if (mv[i] !== path[i]) { ok = false; break; }
    if (!ok) continue;
    const k = mv[path.length];
    const e = m.get(k) || { move: k, n: 0, w: 0, d: 0, l: 0 };
    e.n++; e[g.result === "W" ? "w" : g.result === "D" ? "d" : "l"]++;
    m.set(k, e);
  }
  return [...m.values()].map((e) => ({ ...e, winPct: pct(e.w, e.n) })).sort((a, b) => b.n - a.n);
}

// Szybkie poddania: porażki przez poddanie lub porzucenie przed `maxMoves` ruchem.
const RESIGN = new Set(["resigned", "resign", "abandoned"]);
export function quickResigns(games, maxMoves = 20) {
  const losses = games.filter((g) => g.result === "L");
  const quick = losses.filter((g) => RESIGN.has(g.reason) && g.moves < maxMoves);
  const byGroup = [...groupWin(quick, (g) => g.group)].map(([name, e]) => ({ name, n: e.n })).sort((a, b) => b.n - a.n).slice(0, 5);
  const byMode = ["Bullet", "Blitz", "Rapid"].map((mode) => {
    const l = losses.filter((g) => g.mode === mode), q = quick.filter((g) => g.mode === mode);
    return { mode, n: q.length, losses: l.length, pct: pct(q.length, l.length) };
  }).filter((r) => r.losses);
  return { n: quick.length, losses: losses.length, pct: pct(quick.length, losses.length), byGroup, byMode };
}
