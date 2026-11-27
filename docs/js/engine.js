// Analiza partii Stockfishem (wersja lite, jeden wątek) w Web Workerze, bez serwera.
// Pliki silnika leżą w docs/vendor/stockfish (GPLv3, https://github.com/nmrugg/stockfish.js).

import { Chess } from "../vendor/chess.js";
import { sanMoves } from "./parse.js?v=43";

const ENGINE_URL = new URL("../vendor/stockfish/stockfish-18-lite-single.js", import.meta.url).href;

// Szansa wygranej (0–100) z oceny w centypionach, wzór jak na Lichess.
export const winChance = (cp) => 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
// Celność ruchu z utraty szansy wygranej (wzór Lichess).
export const moveAccuracy = (drop) => Math.max(0, Math.min(100, 103.1668 * Math.exp(-0.04354 * Math.max(0, drop)) - 3.1669));
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

let worker = null, ready = null, queue = Promise.resolve();
const listeners = new Set();

function start() {
  if (ready) return ready;
  worker = new Worker(ENGINE_URL);
  worker.onmessage = (e) => { const line = String(e.data); listeners.forEach((fn) => fn(line)); };
  ready = new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("Silnik nie odpowiada.")), 30000);
    const on = (line) => {
      if (line === "uciok") worker.postMessage("isready");
      if (line === "readyok") { clearTimeout(t); listeners.delete(on); resolve(); }
    };
    listeners.add(on);
    worker.onerror = () => { clearTimeout(t); reject(new Error("Nie udało się uruchomić silnika.")); };
    worker.postMessage("uci");
  });
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
export const ANALYSIS_DEPTH = 16;
export const DEEP_DEPTH = 20;
export const BATCH_DEPTH = 12;
const CACHE_PREFIX = "sf|v2|";

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
export async function analyzeGame(game, { depth = ANALYSIS_DEPTH, onProgress, token, multipv = 2 } = {}) {
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
    plies.push({
      no: Math.floor(i / 2) + 1, san: mv.san, lan: mv.lan, from: mv.from, to: mv.to,
      mine: white === meWhite, drop: Math.round(drop * 10) / 10, kind,
      bestSan: isBest ? null : pv[i][0] || null, line: isBest ? [] : pv[i], phase: phaseOf(fens[i], Math.floor(i / 2) + 1),
    });
  });
  const sideStats = (mine) => {
    const list = plies.filter((p) => p.mine === mine);
    const counts = Object.fromEntries(KIND_ORDER.map((k) => [k, 0]));
    list.forEach((p) => counts[p.kind]++);
    const acc = list.length ? list.reduce((s, p) => s + moveAccuracy(p.drop), 0) / list.length : 0;
    return { counts, accuracy: Math.round(acc * 10) / 10 };
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
