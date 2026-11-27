// Prosta szachownica (bez zależności): pozycja z FEN, podświetlenie ostatniego ruchu i strzałki.

const FILES = "abcdefgh";

function parseFen(fen) {
  const rows = fen.split(" ")[0].split("/");
  const out = {};
  rows.forEach((row, r) => {
    let f = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) { f += Number(ch); continue; }
      out[`${FILES[f]}${8 - r}`] = (ch === ch.toUpperCase() ? "w" : "b") + ch.toUpperCase();
      f++;
    }
  });
  return out;
}

// Współrzędne środka pola w układzie 0–8 (z uwzględnieniem orientacji).
function center(sq, flip) {
  const f = FILES.indexOf(sq[0]), r = Number(sq[1]) - 1;
  return flip ? [7 - f + 0.5, r + 0.5] : [f + 0.5, 7 - r + 0.5];
}

function arrowSvg({ from, to, color }, flip, i) {
  const [x1, y1] = center(from, flip), [x2, y2] = center(to, flip);
  const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy);
  const ux = dx / len, uy = dy / len, head = 0.42;
  const ex = x2 - ux * head, ey = y2 - uy * head;
  const px = -uy * 0.25, py = ux * 0.25;
  return `<g opacity=".82" fill="${color}" stroke="${color}">
    <line x1="${x1}" y1="${y1}" x2="${ex}" y2="${ey}" stroke-width=".17" stroke-linecap="round"/>
    <polygon points="${x2},${y2} ${ex + px},${ey + py} ${ex - px},${ey - py}" stroke="none"/></g>`;
}

// opts: { fen, flip, last: [from, to], lastClass, arrows: [{from, to, color}] }
export function renderBoard(el, { fen, flip = false, last = null, lastClass = "", arrows = [] }) {
  const pos = parseFen(fen);
  let squares = "";
  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const f = flip ? 7 - col : col, r = flip ? row : 7 - row;
      const sq = `${FILES[f]}${r + 1}`;
      const dark = (f + r) % 2 === 0;
      const hl = last && (sq === last[0] || sq === last[1]) ? ` hl ${lastClass}` : "";
      const coordFile = row === 7 ? `<span class="cf">${FILES[f]}</span>` : "";
      const coordRank = col === 0 ? `<span class="cr">${r + 1}</span>` : "";
      squares += `<div class="sq ${dark ? "d" : "l"}${hl}">${coordRank}${coordFile}${pos[sq] ? `<div class="pc ${pos[sq]}"></div>` : ""}</div>`;
    }
  }
  el.innerHTML = `<div class="bd">${squares}<svg class="arrows" viewBox="0 0 8 8">${arrows.map((a, i) => arrowSvg(a, flip, i)).join("")}</svg></div>`;
}
