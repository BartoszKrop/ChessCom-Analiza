// Tryb „ćwicz błędy”: pozycje sprzed Twoich błędów z partii, trzeba kliknąć właściwy ruch (ten, który wskazał silnik).
import { Chess } from "../vendor/chess.js";
import { renderBoard } from "./board.js?v=49";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const BAD = ["blunder", "mistake", "miss"];

// Pozycje do ćwiczenia: Twoje błędy, dla których znamy najlepszy ruch.
export function trainingItems(r) {
  return r.plies.map((p, i) => ({ p, i })).filter(({ p, i }) => p.mine && BAD.includes(p.kind) && r.best?.[i] && r.fens?.[i]);
}

export function startTrainer(panel, g, r, flip, onExit) {
  const items = trainingItems(r);
  const boardEl = panel.querySelector(".board"), info = panel.querySelector(".sf-info");
  if (!items.length) { info.innerHTML = `<div class="sf-move">Brak błędów do ćwiczenia w tej partii 🎉</div>`; return; }
  const ctl = new AbortController();
  panel.classList.add("training");
  let k = 0, sel = null, solved = 0, clean = 0, mistakes = 0, tries = 0, hinted = false, shown = false, done = false;

  const chessAt = () => new Chess(r.fens[items[k].i]);

  function draw() {
    const { p, i } = items[k];
    const best = r.best[i];
    const prev = i ? r.plies[i - 1] : null;
    const arrows = shown || done ? [{ from: best.slice(0, 2), to: best.slice(2, 4), color: "#4a90d9" }] : [];
    renderBoard(boardEl, { fen: r.fens[i], flip, last: prev ? [prev.from, prev.to] : null, arrows });
    if (hinted && !done && !shown) boardEl.querySelector(`[data-sq="${best.slice(0, 2)}"]`)?.classList.add("hint");
    if (sel) {
      boardEl.querySelector(`[data-sq="${sel}"]`)?.classList.add("sel");
      for (const m of chessAt().moves({ square: sel, verbose: true })) boardEl.querySelector(`[data-sq="${m.to}"]`)?.classList.add("tgt");
    }
    const head = `<div class="sf-move">🎯 Zadanie ${k + 1} z ${items.length}</div>`;
    let body;
    if (done) body = `<div class="sf-verdict ok"><b>Dobrze!</b> ${esc(p.bestSan)}</div><div class="muted">W partii zagrałeś <b>${esc(p.san)}</b>.</div>`;
    else if (shown) body = `<div class="sf-verdict bad">Rozwiązanie: <b>${esc(p.bestSan)}</b></div>${p.line?.length ? `<div class="muted">Dalej: ${esc(p.line.slice(0, 4).join(" "))}</div>` : ""}`;
    else body = `<div>Znajdź najlepszy ruch dla ${g.color === "b" ? "czarnych" : "białych"}. W partii tu popełniłeś błąd.</div>${tries ? `<div class="sf-verdict bad">To nie ten ruch, spróbuj jeszcze (próby: ${tries}).</div>` : ""}`;
    const btns = done || shown
      ? `<button class="primary" data-tr="next">${k === items.length - 1 ? "Podsumowanie" : "Dalej ▶"}</button>`
      : `<button data-tr="hint">💡 Podpowiedź</button><button data-tr="show">Pokaż rozwiązanie</button>`;
    info.innerHTML = `${head}${body}<div class="tr-btns">${btns}<button data-tr="exit" class="link-btn">Wyjdź</button></div>`;
  }

  function finish() {
    panel.classList.remove("training");
    boardEl.style.opacity = boardEl.style.pointerEvents = "";
    ctl.abort();
    onExit();
  }
  function summary() {
    boardEl.style.opacity = ".55"; boardEl.style.pointerEvents = "none";
    info.innerHTML = `<div class="sf-move">🎯 Koniec ćwiczeń</div><div class="sf-verdict ok">Znalezione ruchy: <b>${solved} z ${items.length}</b>${clean ? ` (${clean} bez podpowiedzi i pomyłek)` : ""}</div>
      <div class="tr-btns"><button class="primary" data-tr="again">Jeszcze raz</button><button data-tr="exit">Wróć do analizy</button></div>`;
  }
  const reset = () => { sel = null; hinted = shown = done = false; tries = mistakes = 0; };
  const solveOk = () => { done = true; solved++; if (!hinted && !mistakes) clean++; sel = null; draw(); };

  boardEl.addEventListener("click", (e) => {
    if (done || shown) return;
    const sq = e.target.closest(".sq")?.dataset.sq;
    if (!sq) return;
    const c = chessAt();
    if (sel && sel !== sq && c.moves({ square: sel, verbose: true }).some((m) => m.to === sq)) {
      if (r.best[items[k].i].slice(0, 4) === sel + sq) return solveOk();
      tries++; mistakes++; sel = null; return draw();
    }
    sel = c.get(sq)?.color === c.turn() && sel !== sq ? sq : null;
    draw();
  }, { signal: ctl.signal });

  panel.addEventListener("click", (e) => {
    const t = e.target.closest("[data-tr]")?.dataset.tr;
    if (!t) return;
    if (t === "hint") { hinted = true; draw(); }
    else if (t === "show") { shown = true; sel = null; draw(); }
    else if (t === "next") { if (k >= items.length - 1) summary(); else { k++; reset(); draw(); } }
    else if (t === "exit") finish();
    else if (t === "again") { boardEl.style.opacity = boardEl.style.pointerEvents = ""; k = 0; solved = clean = 0; reset(); draw(); }
  }, { signal: ctl.signal });

  draw();
}
