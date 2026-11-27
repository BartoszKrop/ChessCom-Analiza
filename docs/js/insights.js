// Wzorce w grze na podstawie przeanalizowanych partii (wyniki z engine.analyzeGame). Czyste funkcje, bez DOM.

import { winChance } from "./engine.js?v=61";

const BIG = new Set(["blunder", "mistake", "miss"]);
const PHASE_NAME = { open: "debiucie (ruchy 1–12)", middle: "grze środkowej", end: "końcówce" };
const PIECE = { K: "królem", Q: "hetmanem", R: "wieżą", B: "gońcem", N: "skoczkiem", P: "pionkiem" };
const pieceOf = (san) => (/^O-O/.test(san) ? "K" : /^[KQRBN]/.test(san) ? san[0] : "P");
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const avg = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);

// results: [{ game: {result, color}, res: {plies, evals, accuracy} }]
export function patterns(results) {
  const out = [];
  const n = results.length;
  if (n < 3) return out;

  // 1. Gdzie pojawia się pierwszy poważny błąd w przegranych partiach.
  const lost = results.filter((x) => x.game.result === "L");
  const firstPhase = { open: 0, middle: 0, end: 0 };
  let withErr = 0;
  for (const { res } of lost) {
    const e = res.plies.find((p) => p.mine && BIG.has(p.kind));
    if (e) { firstPhase[e.phase]++; withErr++; }
  }
  if (withErr >= 3) {
    const [ph, c] = Object.entries(firstPhase).sort((a, b) => b[1] - a[1])[0];
    if (pct(c, withErr) >= 40) out.push({ icon: "🎯", text: `W ${pct(c, withErr)}% przegranych partii pierwszy poważny błąd robisz w ${PHASE_NAME[ph]}.` });
  }

  // 2. Zmarnowane wygrane pozycje.
  const led = results.filter(({ game, res }) => {
    const sign = game.color === "w" ? 1 : -1;
    return res.evals.some((v) => winChance(sign * v) >= 70);
  });
  if (led.length >= 3) {
    const won = led.filter((x) => x.game.result === "W").length;
    if (won < led.length) out.push({ icon: "💸", text: `W ${led.length} z ${n} partii miałeś wyraźną przewagę (ok. +2,4 i więcej), ale wygrałeś ${won} z nich.${won / led.length < 0.8 ? " Warto ćwiczyć zamykanie wygranych pozycji." : ""}` });
  }

  // 3. Którą figurą robisz najwięcej błędów (w stosunku do liczby jej ruchów).
  const moves = {}, errs = {};
  let allMoves = 0, allErrs = 0;
  for (const { res } of results) for (const p of res.plies) {
    if (!p.mine) continue;
    const k = pieceOf(p.san);
    moves[k] = (moves[k] || 0) + 1; allMoves++;
    if (BIG.has(p.kind)) { errs[k] = (errs[k] || 0) + 1; allErrs++; }
  }
  if (allErrs >= 6) {
    const worst = Object.keys(errs).map((k) => ({ k, share: pct(errs[k], allErrs), mshare: pct(moves[k], allMoves) }))
      .filter((x) => errs[x.k] >= 3 && x.share - x.mshare >= 8).sort((a, b) => b.share - b.mshare - (a.share - a.mshare))[0];
    if (worst) out.push({ icon: "♞", text: `Najwięcej błędów robisz ${PIECE[worst.k]}: ${worst.share}% błędów przy ${worst.mshare}% ruchów tą figurą.` });
  }

  // 4. Biały kontra czarny.
  const acc = (c) => avg(results.filter((x) => x.game.color === c).map((x) => x.res.accuracy));
  const w = results.filter((x) => x.game.color === "w").length, b = n - w;
  if (w >= 3 && b >= 3) {
    const d = Math.round((acc("w") - acc("b")) * 10) / 10;
    if (Math.abs(d) >= 4) out.push({ icon: d > 0 ? "⚪" : "⚫", text: `${d > 0 ? "Czarnymi" : "Białymi"} grasz o ${Math.abs(d)} pp mniej celnie (${Math.round(acc(d > 0 ? "b" : "w"))}% wobec ${Math.round(acc(d > 0 ? "w" : "b"))}%).` });
  }

  // 5. Maty: przeoczone i dopuszczone.
  let missed = 0, allowed = 0, gamesMate = 0;
  for (const { res } of results) {
    let any = false;
    for (const p of res.plies) {
      if (!p.mine || !p.why) continue;
      if (p.why.code === "missedMate") { missed++; any = true; }
      if (p.why.code === "allowedMate") { allowed++; any = true; }
    }
    if (any) gamesMate++;
  }
  if (missed + allowed >= 2) out.push({ icon: "♚", text: `Przeoczone maty: ${missed}, dopuszczone maty rywala: ${allowed} (w ${gamesMate} partiach). Przed każdym ruchem sprawdź szachy i grożące maty.` });

  // 6. Oddawanie materiału jednym ruchem.
  let hung = 0, hungGames = 0;
  for (const { res } of results) {
    const c = res.plies.filter((p) => p.mine && p.why?.code === "material" && p.why.pts >= 3).length;
    hung += c; if (c) hungGames++;
  }
  if (hung >= 3) out.push({ icon: "🎁", text: `${hung} razy oddałeś figurę lub więcej jednym ruchem (w ${hungGames} partiach). Przed ruchem zapytaj: co teraz atakuje rywal?` });

  // 7. Wczesne błędy rażące.
  const early = results.filter((x) => x.res.plies.some((p) => p.mine && p.kind === "blunder" && p.no <= 15)).length;
  if (early >= 3 && pct(early, n) >= 25) out.push({ icon: "⚡", text: `W ${pct(early, n)}% partii robisz błąd rażący już w pierwszych 15 ruchach.` });

  return out;
}
