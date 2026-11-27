// Analiza partii Stockfishem (wersja lite, jeden wątek) w Web Workerze, bez serwera.
// Pliki silnika leżą w docs/vendor/stockfish (GPLv3, https://github.com/nmrugg/stockfish.js).

import { Chess } from "../vendor/chess.js";
import { sanMoves } from "./parse.js?v=36";

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
        if (m && !line.includes("lowerbound") && !line.includes("upperbound")) last = m[1] === "cp" ? { cp: Number(m[2]), mate: null } : { cp: null, mate: Number(m[2]) };
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

let generation = 0;
export const cancelAnalysis = () => { generation++; };

// Analiza całej partii. onProgress(done, total). Zwraca null, gdy przerwano.
export async function analyzeGame(game, { depth = 12, onProgress } = {}) {
  const my = ++generation;
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

  // Ocena każdej pozycji z perspektywy białych (w centypionach).
  const evals = [];
  for (let i = 0; i < fens.length; i++) {
    if (my !== generation) return null;
    const probe = new Chess(fens[i]);
    let white;
    if (probe.isCheckmate()) white = probe.turn() === "w" ? -MATE_CP : MATE_CP;
    else if (probe.isDraw() || probe.isStalemate()) white = 0;
    const e = white === undefined ? await evaluate(fens[i], depth) : { best: null };
    if (white === undefined) white = evalToCp(e) * (probe.turn() === "w" ? 1 : -1);
    evals.push({ white, best: e.best });
    onProgress?.(i + 1, fens.length);
  }

  // Ruchy gracza: utrata szansy wygranej względem najlepszej kontynuacji.
  const meWhite = game.color === "w";
  const plies = moves.map((mv, i) => {
    const before = evals[i].white, after = evals[i + 1].white;
    const mine = (i % 2 === 0) === meWhite;
    const sign = i % 2 === 0 ? 1 : -1; // perspektywa strony, która ruszała
    const drop = Math.max(0, winChance(sign * before) - winChance(sign * after));
    let bestSan = null;
    const best = evals[i].best;
    if (best && best !== mv.lan) {
      try { bestSan = new Chess(fens[i]).move({ from: best.slice(0, 2), to: best.slice(2, 4), promotion: best[4] }).san; } catch { /* pomijamy */ }
    }
    return { ply: i, no: Math.floor(i / 2) + 1, san: mv.san, mine, drop, kind: classify(drop), bestSan: mv.lan === best ? null : bestSan, after };
  });
  const minePlies = plies.filter((p) => p.mine);
  const acc = minePlies.length ? minePlies.reduce((s, p) => s + moveAccuracy(p.drop), 0) / minePlies.length : 0;
  const count = (k) => minePlies.filter((p) => p.kind === k).length;
  return {
    evals: evals.map((e) => e.white), plies,
    accuracy: Math.round(acc * 10) / 10,
    blunders: count("blunder"), mistakes: count("mistake"), inaccuracies: count("inaccuracy"),
  };
}
