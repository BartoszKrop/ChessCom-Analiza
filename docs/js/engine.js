// Analiza partii Stockfishem (wersja lite, jeden wątek) w Web Workerze, bez serwera.
// Pliki silnika leżą w docs/vendor/stockfish (GPLv3, https://github.com/nmrugg/stockfish.js).

import { Chess } from "../vendor/chess.js";
import { sanMoves } from "./parse.js?v=37";

const ENGINE_URL = new URL("../vendor/stockfish/stockfish-18-lite-single.js", import.meta.url).href;

// Szansa wygranej (0–100) z oceny w centypionach, wzór jak na Lichess.
export const winChance = (cp) => 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
// Celność ruchu z utraty szansy wygranej (wzór Lichess).
export const moveAccuracy = (drop) => Math.max(0, Math.min(100, 103.1668 * Math.exp(-0.04354 * Math.max(0, drop)) - 3.1669));
export function classify(drop) {
  if (drop >= 15) return "blunder";
  if (drop >= 10) return "mistake";
  if (drop >= 5) return "inaccuracy";
  return null;
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

// Ocena pozycji z perspektywy strony na ruchu: {cp | mate, best (UCI)}.
function evaluate(fen, depth) {
  const run = () => new Promise((resolve) => {
    let last = { cp: 0, mate: null };
    const on = (line) => {
      if (line.startsWith("info") && line.includes(" score ")) {
        const m = line.match(/score (cp|mate) (-?\d+)/);
        if (m && !line.includes("lowerbound") && !line.includes("upperbound")) {
          const pv = (line.match(/ pv (.+)$/) || [, ""])[1].split(" ").filter(Boolean).slice(0, 6);
          last = m[1] === "cp" ? { cp: Number(m[2]), mate: null, pv } : { cp: null, mate: Number(m[2]), pv };
        }
      } else if (line.startsWith("bestmove")) {
        listeners.delete(on);
        resolve({ ...last, best: line.split(" ")[1] });
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

export const ANALYSIS_DEPTH = 12;
const CACHE_PREFIX = "sf|v1|";

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

export async function cachedAnalysis(game) {
  if (!game.link || !cacheGet) return null;
  try { return (await cacheGet(CACHE_PREFIX + game.link)) || null; } catch { return null; }
}

let cacheGet = null, cacheSet = null;
export function useCache(get, set) { cacheGet = get; cacheSet = set; }

// Analiza całej partii. onProgress(done, total). Zwraca null, gdy przerwano.
export async function analyzeGame(game, { depth = ANALYSIS_DEPTH, onProgress, token } = {}) {
  const cached = await cachedAnalysis(game);
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
  const evals = [], best = [], pv = [];
  for (let i = 0; i < fens.length; i++) {
    if (my.cancelled) return null;
    const probe = new Chess(fens[i]);
    let white, e = { pv: [] };
    if (probe.isCheckmate()) white = probe.turn() === "w" ? -MATE_CP : MATE_CP;
    else if (probe.isDraw() || probe.isStalemate()) white = 0;
    else {
      e = await evaluate(fens[i], depth);
      white = evalToCp(e) * (probe.turn() === "w" ? 1 : -1);
    }
    evals.push(white);
    best.push(e.best && e.best !== "(none)" ? e.best : null);
    pv.push(uciToSan(fens[i], e.pv?.length ? e.pv : e.best ? [e.best] : []));
    onProgress?.(i + 1, fens.length);
  }

  // Ruchy: utrata szansy wygranej względem oceny przed ruchem (perspektywa strony, która ruszała).
  const meWhite = game.color === "w";
  const plies = moves.map((mv, i) => {
    const sign = i % 2 === 0 ? 1 : -1;
    const drop = Math.max(0, winChance(sign * evals[i]) - winChance(sign * evals[i + 1]));
    const isBest = best[i] === mv.lan;
    return {
      no: Math.floor(i / 2) + 1, san: mv.san, lan: mv.lan, from: mv.from, to: mv.to,
      mine: (i % 2 === 0) === meWhite, drop: Math.round(drop * 10) / 10, kind: isBest ? null : classify(drop),
      bestSan: isBest ? null : pv[i][0] || null, line: isBest ? [] : pv[i], phase: phaseOf(fens[i], Math.floor(i / 2) + 1),
    };
  });
  const minePlies = plies.filter((p) => p.mine);
  const acc = minePlies.length ? minePlies.reduce((s, p) => s + moveAccuracy(p.drop), 0) / minePlies.length : 0;
  const count = (k) => minePlies.filter((p) => p.kind === k).length;
  const res = {
    fens, evals, best, plies, depth,
    accuracy: Math.round(acc * 10) / 10,
    blunders: count("blunder"), mistakes: count("mistake"), inaccuracies: count("inaccuracy"),
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
      r = await analyzeGame(games[i], { token, onProgress: (d, t) => onProgress?.(i, games.length, d, t) });
    } catch { /* pomijamy partię, której nie da się odczytać */ }
    if (token.cancelled) break;
    if (r) { out.push({ game: games[i], res: r }); onResult?.(games[i], r); }
    onProgress?.(i + 1, games.length, 0, 0);
  }
  return { results: out, cancelled: token.cancelled };
}
