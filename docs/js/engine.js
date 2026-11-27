// Analiza partii Stockfishem (wersja lite) w Web Workerze, bez serwera.
// Gdy strona jest „cross-origin isolated” (service worker dodaje nagłówki COOP/COEP), używamy wersji wielowątkowej.
// Pliki silnika leżą w docs/vendor/stockfish (GPLv3, https://github.com/nmrugg/stockfish.js).

import { Chess } from "../vendor/chess.js";
import { sanMoves } from "./parse.js?v=48";

const engineUrl = (file) => new URL(`../vendor/stockfish/${file}`, import.meta.url).href;

// Liczba wątków silnika: 1 bez izolacji (np. Safari, pierwsza wizyta), inaczej do 4 (zostawiamy rdzeń dla strony).
export function pickThreads(isolated = typeof crossOriginIsolated !== "undefined" && crossOriginIsolated, cores = navigator.hardwareConcurrency || 2, mobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent || "")) {
  if (!isolated || mobile || typeof SharedArrayBuffer === "undefined") return 1;
  return Math.max(1, Math.min(4, cores - 1));
}
export let engineThreads = 1;
export const defaultDepth = () => (pickThreads() >= 3 ? 18 : 16);
export const deepDepth = () => (pickThreads() >= 3 ? 22 : 20);

// Szansa wygranej (0–100) z oceny w centypionach, wzór jak na Lichess.
export const winChance = (cp) => 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
// Celność ruchu z utraty szansy wygranej (wzór Lichess).
export const moveAccuracy = (drop) => Math.max(0, Math.min(100, 103.1668 * Math.exp(-0.04354 * Math.max(0, drop)) - 3.1669));

// Celność całej partii wzorem Lichess (zbliżonym do CAPS z Chess.com): średnia z (a) średniej ważonej zmiennością pozycji
// i (b) średniej harmonicznej celności ruchów. Harmoniczna mocno karze pojedyncze poważne błędy, zwykła średnia je „rozmywa”.
// evals: ocena białych w każdej pozycji (n+1), drops: utrata szansy wygranej w każdym z n ruchów, whiteMoves: czy ruch i to ruch białych.
export function gameAccuracy(evals, drops, isMine) {
  const n = drops.length;
  const wins = evals.map(winChance);
  const w = Math.min(8, Math.max(2, Math.floor(n / 10)));
  const sd = (a) => { const m = a.reduce((x, y) => x + y, 0) / a.length; return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / a.length); };
  const windows = [];
  for (let i = 0; i < Math.min(w, wins.length) - 2; i++) windows.push(wins.slice(0, w));
  for (let i = 0; i + w <= wins.length; i++) windows.push(wins.slice(i, i + w));
  const acc = [], wt = [];
  for (let i = 0; i < n; i++) {
    if (!isMine(i)) continue;
    // Ruch bez straty (najlepszy lub poprawiający pozycję) = 100; inaczej wzór + 1 pkt „premii za niepewność analizy”.
    acc.push(drops[i] <= 0 ? 100 : Math.min(100, Math.max(0, moveAccuracy(drops[i]) + 1)));
    wt.push(Math.min(12, Math.max(0.5, sd(windows[Math.min(i, windows.length - 1)] || [50]))));
  }
  if (!acc.length) return 0;
  const weighted = acc.reduce((x, a, i) => x + a * wt[i], 0) / wt.reduce((x, y) => x + y, 0);
  const harmonic = acc.length / acc.reduce((x, a) => x + 1 / Math.max(a, 0.5), 0);
  return Math.round(((weighted + harmonic) / 2) * 10) / 10;
}
// Kategorie ruchów jak na Chess.com. Utrata szansy wygranej: >= 20 błąd rażący, >= 10 błąd, >= 5 niedokładność.
export const ERROR_KINDS = ["inaccuracy", "mistake", "miss", "blunder"];
export const KIND_ORDER = ["brilliant", "great", "best", "excellent", "good", "inaccuracy", "mistake", "miss", "blunder"];
export function classify(drop) {
  if (drop >= 20) return "blunder";
  if (drop >= 10) return "mistake";
  if (drop >= 5) return "inaccuracy";
  return null;
}

// Ocena jednego ruchu.
// drop: utrata szansy wygranej (0–100), isBest: zagrany ruch == najlepszy silnika, gap: przewaga najlepszego
// ruchu nad drugim (szansa wygranej, null gdy nieznana), winBefore/winAfter: szansa wygranej gracza przed/po ruchu,
// sacrifice: ruch poświęca materiał, prevOppError: poprzedni ruch rywala był błędem.
export function classifyMove({ drop, isBest, gap = null, winBefore = 50, winAfter = 50, sacrifice = false, prevOppError = false }) {
  const err = classify(drop);
  if (err === "blunder") return "blunder";
  if (err === "mistake") return prevOppError ? "miss" : "mistake";
  if (err === "inaccuracy") return "inaccuracy";
  if (sacrifice && drop < 3 && winAfter >= 40 && winBefore < 90) return "brilliant";
  if (isBest && gap !== null && gap >= 12 && winBefore < 90 && winAfter >= 25) return "great";
  if (isBest) return "best";
  if (drop < 2) return "excellent";
  return "good";
}

// Wartość materiału (P=1, N=B=3, R=5, Q=9) białych minus czarnych z FEN.
const PIECE_VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9 };
export function materialDiff(fen) {
  let d = 0;
  for (const ch of fen.split(" ")[0]) {
    const v = PIECE_VALUE[ch.toLowerCase()];
    if (v) d += ch === ch.toUpperCase() ? v : -v;
  }
  return d;
}

// Czy ruch ze `fenAfter` (pozycja po ruchu) i linią silnika `line` (SAN) zostawia gracza o >= 2 punkty materiału na minusie
// względem pozycji `fenBefore`? Liczymy parzystą liczbę półruchów linii (wymiany nie liczą się jako poświęcenie).
export function isSacrifice(fenBefore, fenAfter, line, moverWhite) {
  if (!line || line.length < 2) return false;
  const k = Math.min(line.length, 4) - (Math.min(line.length, 4) % 2);
  try {
    const c = new Chess(fenAfter);
    for (let i = 0; i < k; i++) c.move(line[i]);
    const sign = moverWhite ? 1 : -1;
    return sign * (materialDiff(c.fen()) - materialDiff(fenBefore)) <= -2;
  } catch { return false; }
}

const MATE_CP = 10000;
export const evalToCp = (e) => (e.mate != null ? Math.sign(e.mate || 1) * (MATE_CP - Math.abs(e.mate) * 10) : e.cp);

// Zmiana materiału (z perspektywy grającego) po odegraniu `sans` z pozycji `fen`.
export function materialDelta(fen, sans, moverWhite) {
  try {
    const c = new Chess(fen);
    for (const san of sans) c.move(san);
    return (moverWhite ? 1 : -1) * (materialDiff(c.fen()) - materialDiff(fen));
  } catch { return 0; }
}

// Dlaczego ruch był błędem? Oceny w centypionach z perspektywy grającego.
// Zwraca {code: "missedMate" | "allowedMate" | "material" | "wasted" | "position", n?, pts?}.
export function explainMove({ fenBefore, san, bestLine = [], afterLine = [], evalBefore, evalAfter, moverWhite }) {
  const MATE = MATE_CP - 500;
  const mateIn = (cp) => Math.max(1, Math.round((MATE_CP - Math.abs(cp)) / 10));
  if (evalBefore >= MATE && evalAfter < MATE) return { code: "missedMate", n: mateIn(evalBefore) };
  if (evalAfter <= -MATE && evalBefore > -MATE) return { code: "allowedMate", n: mateIn(evalAfter) };
  const played = materialDelta(fenBefore, [san, ...afterLine.slice(0, 3)], moverWhite);
  const best = bestLine.length ? materialDelta(fenBefore, bestLine.slice(0, 4), moverWhite) : 0;
  if (best - played >= 2) return { code: "material", pts: best - played };
  if (winChance(evalBefore) >= 75 && winChance(evalAfter) < 60) return { code: "wasted" };
  return { code: "position" };
}

let worker = null, ready = null, queue = Promise.resolve();
const listeners = new Set();

function spawn(file, threads) {
  return new Promise((resolve, reject) => {
    const w = new Worker(engineUrl(file));
    const t = setTimeout(() => { w.terminate(); reject(new Error("Silnik nie odpowiada.")); }, 30000);
    w.onerror = () => { clearTimeout(t); w.terminate(); reject(new Error("Nie udało się uruchomić silnika.")); };
    w.onmessage = (e) => {
      const line = String(e.data);
      if (line === "uciok") {
        if (threads > 1) w.postMessage(`setoption name Threads value ${threads}`);
        w.postMessage(`setoption name Hash value ${threads > 1 ? 64 : 32}`);
        w.postMessage("isready");
      } else if (line === "readyok") {
        clearTimeout(t);
        w.onmessage = (ev) => { const l = String(ev.data); listeners.forEach((fn) => fn(l)); };
        resolve(w);
      }
    };
    w.postMessage("uci");
  });
}

function start() {
  if (ready) return ready;
  ready = (async () => {
    const threads = pickThreads();
    if (threads > 1) {
      try { worker = await spawn("stockfish-18-lite.js", threads); engineThreads = threads; return; } catch { /* wracamy do jednego wątku */ }
    }
    worker = await spawn("stockfish-18-lite-single.js", 1);
    engineThreads = 1;
  })();
  ready.catch(() => { ready = null; worker?.terminate(); worker = null; });
  return ready;
}

// Ocena pozycji z perspektywy strony na ruchu: {cp | mate, pv, best (UCI), second: {cp | mate} | null}.
let multipvSet = 1;
function evaluate(fen, depth, multipv = 1) {
  const run = () => new Promise((resolve) => {
    if (multipv !== multipvSet) { worker.postMessage(`setoption name MultiPV value ${multipv}`); multipvSet = multipv; }
    const lines = {};
    const on = (line) => {
      if (line.startsWith("info") && line.includes(" score ")) {
        const m = line.match(/score (cp|mate) (-?\d+)/);
        if (m && !line.includes("lowerbound") && !line.includes("upperbound")) {
          const k = Number((line.match(/ multipv (\d+)/) || [, 1])[1]);
          const pv = (line.match(/ pv (.+)$/) || [, ""])[1].split(" ").filter(Boolean).slice(0, 6);
          lines[k] = m[1] === "cp" ? { cp: Number(m[2]), mate: null, pv } : { cp: null, mate: Number(m[2]), pv };
        }
      } else if (line.startsWith("bestmove")) {
        listeners.delete(on);
        resolve({ ...(lines[1] || { cp: 0, mate: null, pv: [] }), best: line.split(" ")[1], second: lines[2] || null });
      }
    };
    listeners.add(on);
    worker.postMessage(`position fen ${fen}`);
    worker.postMessage(`go depth ${depth}`);
  });
  const p = queue.then(run);
  queue = p.catch(() => {});
  return p;
}

// Przerwanie: nowa analiza (albo cancelAnalysis) unieważnia poprzednią.
let current = null;
export const cancelAnalysis = () => { if (current) current.cancelled = true; };
const newToken = () => { cancelAnalysis(); current = { cancelled: false }; return current; };

// Głębokość 16 to ok. 12 s na partię z 30 ruchów (desktop), 20 to ok. minuta. Seria partii liczy się szybciej (12).
export const ANALYSIS_DEPTH = 16; // przy wielu wątkach: defaultDepth() = 18
export const DEEP_DEPTH = 20; // przy wielu wątkach: deepDepth() = 22
export const BATCH_DEPTH = 12;
const CACHE_PREFIX = "sf|v3|";

// Faza partii w pozycji: debiut do 12. ruchu, końcówka gdy zostało ≤ 6 figur (bez pionów i królów).
export function phaseOf(fen, moveNo) {
  const pieces = (fen.split(" ")[0].match(/[nbrqNBRQ]/g) || []).length;
  if (pieces <= 6) return "end";
  return moveNo <= 12 ? "open" : "middle";
}

function uciToSan(fen, uciMoves) {
  const c = new Chess(fen), out = [];
  for (const u of uciMoves) {
    try { out.push(c.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u[4] }).san); } catch { break; }
  }
  return out;
}

// Zapisana analiza liczy się tylko, gdy była wykonana co najmniej na żądanej głębokości.
export async function cachedAnalysis(game, depth = 0) {
  if (!game.link || !cacheGet) return null;
  try {
    const r = await cacheGet(CACHE_PREFIX + game.link);
    return r && (r.depth || 0) >= depth ? r : null;
  } catch { return null; }
}

let cacheGet = null, cacheSet = null;
export function useCache(get, set) { cacheGet = get; cacheSet = set; }

// Analiza całej partii. onProgress(done, total). Zwraca null, gdy przerwano.
export async function analyzeGame(game, { depth = defaultDepth(), onProgress, token, multipv = 2 } = {}) {
  const cached = await cachedAnalysis(game, depth);
  if (cached) return cached;
  const my = token || newToken();
  await start();
  const chess = new Chess();
  const sans = sanMoves(game.pgn, 1000);
  const fens = [chess.fen()], moves = [];
  for (const san of sans) {
    let mv;
    try { mv = chess.move(san); } catch { break; }
    moves.push(mv);
    fens.push(chess.fen());
  }
  if (!moves.length) throw new Error("Nie udało się odczytać ruchów tej partii.");

  // Ocena każdej pozycji z perspektywy białych (w centypionach) + najlepszy wariant.
  const evals = [], best = [], pv = [], second = [];
  for (let i = 0; i < fens.length; i++) {
    if (my.cancelled) return null;
    const probe = new Chess(fens[i]);
    let white, e = { pv: [] };
    if (probe.isCheckmate()) white = probe.turn() === "w" ? -MATE_CP : MATE_CP;
    else if (probe.isDraw() || probe.isStalemate()) white = 0;
    else {
      e = await evaluate(fens[i], depth, multipv);
      white = evalToCp(e) * (probe.turn() === "w" ? 1 : -1);
    }
    evals.push(white);
    second.push(e.second ? evalToCp(e.second) : null); // z perspektywy strony na ruchu
    best.push(e.best && e.best !== "(none)" ? e.best : null);
    pv.push(uciToSan(fens[i], e.pv?.length ? e.pv : e.best ? [e.best] : []));
    onProgress?.(i + 1, fens.length);
  }

  // Ruchy: utrata szansy wygranej względem oceny przed ruchem (perspektywa strony, która ruszała).
  const meWhite = game.color === "w";
  const plies = [];
  moves.forEach((mv, i) => {
    const white = i % 2 === 0, sign = white ? 1 : -1;
    const winBefore = winChance(sign * evals[i]), winAfter = winChance(sign * evals[i + 1]);
    const isBest = best[i] === mv.lan;
    // Najlepszy ruch silnika nie traci nic; różnice między głębokościami obliczeń to szum.
    const drop = isBest ? 0 : Math.max(0, winBefore - winAfter);
    const gap = isBest && second[i] !== null ? winBefore - winChance(second[i]) : null;
    const prev = plies[i - 1];
    const kind = classifyMove({
      drop, isBest, gap, winBefore, winAfter,
      sacrifice: isSacrifice(fens[i], fens[i + 1], pv[i + 1], white),
      prevOppError: !!prev && ERROR_KINDS.includes(prev.kind) && prev.kind !== "inaccuracy",
    });
    const why = ERROR_KINDS.includes(kind)
      ? explainMove({ fenBefore: fens[i], san: mv.san, bestLine: pv[i], afterLine: pv[i + 1] || [], evalBefore: sign * evals[i], evalAfter: sign * evals[i + 1], moverWhite: white })
      : null;
    plies.push({
      why, no: Math.floor(i / 2) + 1, san: mv.san, lan: mv.lan, from: mv.from, to: mv.to,
      mine: white === meWhite, drop: Math.round(drop * 10) / 10, kind,
      bestSan: isBest ? null : pv[i][0] || null, line: isBest ? [] : pv[i], phase: phaseOf(fens[i], Math.floor(i / 2) + 1),
    });
  });
  const sideStats = (mine) => {
    const list = plies.filter((p) => p.mine === mine);
    const counts = Object.fromEntries(KIND_ORDER.map((k) => [k, 0]));
    list.forEach((p) => counts[p.kind]++);
    const accuracy = gameAccuracy(evals, plies.map((p) => p.drop), (i) => plies[i].mine === mine);
    return { counts, accuracy };
  };
  const me = sideStats(true), opp = sideStats(false);
  const res = {
    fens, evals, best, plies, depth,
    accuracy: me.accuracy, accuracyOpp: opp.accuracy, counts: me.counts, countsOpp: opp.counts,
    blunders: me.counts.blunder, mistakes: me.counts.mistake + me.counts.miss, inaccuracies: me.counts.inaccuracy,
  };
  if (game.link && cacheSet) cacheSet(CACHE_PREFIX + game.link, res);
  return res;
}

// Analiza wielu partii po kolei. onProgress(gameIdx, total, posDone, posTotal). Zwraca wyniki (bez przerwanych).
export async function analyzeMany(games, { onProgress, onResult } = {}) {
  const token = newToken();
  const out = [];
  for (let i = 0; i < games.length; i++) {
    if (token.cancelled) break;
    let r = null;
    try {
      r = await analyzeGame(games[i], { token, depth: BATCH_DEPTH, onProgress: (d, t) => onProgress?.(i, games.length, d, t) });
    } catch { /* pomijamy partię, której nie da się odczytać */ }
    if (token.cancelled) break;
    if (r) { out.push({ game: games[i], res: r }); onResult?.(games[i], r); }
    onProgress?.(i + 1, games.length, 0, 0);
  }
  return { results: out, cancelled: token.cancelled };
}
