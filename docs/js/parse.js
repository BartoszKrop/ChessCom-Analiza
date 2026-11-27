// Parsowanie partii z Chess.com i Lichess do wspólnego formatu.
// Czyste funkcje bez DOM, testowane w tests/js/parse.test.mjs.

export const MAX_MOVE_TIME_SECONDS = 300;
export const MODES = ["Bullet", "Blitz", "Rapid"];
const DRAW_RESULTS = new Set(["agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"]);
const LICHESS_SKIP_STATUS = new Set(["aborted", "noStart", "created", "started", "unknownFinish"]);
export const DAYS = ["Pn", "Wt", "Śr", "Czw", "Pt", "Sb", "Nd"];

const GROUPS = [
  [["sicilian"], "Sicilian Defense"],
  [["french"], "French Defense"],
  [["caro-kann", "caro kann"], "Caro-Kann Defense"],
  [["ruy lopez", "spanish"], "Ruy Lopez"],
  [["italian", "giuoco piano"], "Italian Game"],
  [["scotch"], "Scotch Game"],
  [["vienna"], "Vienna Game"],
  [["four knights"], "Four Knights Game"],
  [["two knights"], "Two Knights Defense"],
  [["petrov", "russian"], "Petrov's Defense"],
  [["philidor"], "Philidor Defense"],
  [["bishop's opening", "bishops opening"], "Bishop's Opening"],
  [["scandinavian"], "Scandinavian Defense"],
  [["alekhine"], "Alekhine's Defense"],
  [["pirc"], "Pirc Defense"],
  [["modern defense"], "Modern Defense"],
  [["queens gambit", "queen's gambit"], "Queen's Gambit"],
  [["kings gambit", "king's gambit"], "King's Gambit"],
  [["kings indian", "king's indian"], "King's Indian Defense"],
  [["queens indian", "queen's indian"], "Queen's Indian Defense"],
  [["nimzo"], "Nimzo-Indian Defense"],
  [["bogo-indian", "bogo indian"], "Bogo-Indian Defense"],
  [["grunfeld", "grünfeld", "gruenfeld"], "Grünfeld Defense"],
  [["slav"], "Slav Defense"],
  [["catalan"], "Catalan Opening"],
  [["london"], "London System"],
  [["trompowsky"], "Trompowsky Attack"],
  [["benoni"], "Benoni Defense"],
  [["benko", "volga"], "Benko Gambit"],
  [["dutch"], "Dutch Defense"],
  [["english"], "English Opening"],
  [["reti", "réti"], "Réti Opening"],
  [["bird"], "Bird's Opening"],
  [["king's pawn", "kings pawn"], "King's Pawn Opening"],
  [["queen's pawn", "queens pawn"], "Queen's Pawn Opening"],
];

const titleCase = (s) => s.toLowerCase().replace(/(^|[^\p{L}])(\p{L})/gu, (m, p, c) => p + c.toUpperCase());

export function openingGroup(name) {
  const n = String(name || "").toLowerCase();
  for (const [keys, group] of GROUPS) if (keys.some((k) => n.includes(k))) return group;
  const fallback = String(name || "").split(":")[0].trim();
  for (const kw of [" Defense", " Opening", " Game", " Gambit", " System", " Attack"]) {
    const idx = fallback.toLowerCase().indexOf(kw.toLowerCase());
    if (idx !== -1) return titleCase(fallback.slice(0, idx + kw.length));
  }
  return titleCase(fallback) || "Nieznany";
}

export function extractOpening(pgn) {
  if (!pgn) return "Nieznany";
  const tag = pgn.match(/\[Opening "(.*?)"\]/);
  if (tag) return tag[1].trim();
  const m = pgn.match(/openings\/(.*?)"/);
  if (!m) return "Inny";
  const slug = m[1].replace(/([A-Za-z])-s(?=-[A-Z]|-$|$)/g, "$1's");
  return titleCase(slug.replace(/-/g, " ")).replace(/([A-Za-z])'S\b/g, "$1's");
}

export function openingForUser(name, isWhite) {
  if (!name) return "Nieznany";
  const parts = String(name).split(":").map((p) => p.trim()).filter(Boolean);
  if (!parts.length) return "Nieznany";
  if (isWhite || parts.length === 1) return parts[0];
  const role = /\b(defen[sc]e|counter(?:gambit)?|gambit|system|attack)\b/i;
  for (const p of [...parts.slice(1), parts[0]]) if (role.test(p)) return p;
  return parts[1];
}

// Sam zapis ruchów: bez nagłówków i komentarzy {...} (zegar [%clk ...] nie psuje liczenia ruchów).
export function pgnMovetext(pgn) {
  if (!pgn) return "";
  return pgn.replace(/^\s*\[[^\]]*\]\s*$/gm, "").replace(/\{[^}]*\}/g, " ");
}

export function movesCount(pgn) {
  let max = 0;
  // Bez lookbehind: starsze Safari (iOS < 16.4) go nie obsługują i cały moduł by nie ruszył.
  for (const m of pgnMovetext(pgn).matchAll(/(^|[^\d.])(\d+)\./g)) max = Math.max(max, Number(m[2]));
  return max;
}

function clockToSeconds(text) {
  const p = String(text).split(":").map(Number);
  if (p.some(Number.isNaN)) return 0;
  if (p.length === 3) return p[0] * 3600 + p[1] * 60 + p[2];
  if (p.length === 2) return p[0] * 60 + p[1];
  return 0;
}

function clockDeltas(clocks) {
  const out = [];
  for (let i = 1; i < clocks.length; i++) {
    const d = clocks[i - 1] - clocks[i];
    if (d >= 0 && d <= MAX_MOVE_TIME_SECONDS) out.push(Math.round(d * 100) / 100);
  }
  return out;
}

const every2 = (arr, start) => arr.filter((_, i) => i % 2 === start);

export function moveTimesFromPgn(pgn, isWhite) {
  const clocks = [...String(pgn || "").matchAll(/\[%clk ([0-9:.]+)\]/g)].map((m) => clockToSeconds(m[1]));
  const mine = every2(clocks, isWhite ? 0 : 1);
  return mine.length < 2 ? [] : clockDeltas(mine);
}

export function moveTimesFromLichess(clocks, isWhite) {
  if (!clocks || clocks.length < 4) return [];
  return clockDeltas(every2(clocks, isWhite ? 0 : 1).map((c) => c / 100));
}

const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "Inne");

export function parseChesscomGame(g, user, account) {
  if (!g.end_time || (g.rules || "chess") !== "chess") return null;
  const isW = g.white.username.toLowerCase() === user.toLowerCase();
  const me = isW ? g.white : g.black;
  const opp = isW ? g.black : g.white;
  const result = me.result === "win" ? "W" : DRAW_RESULTS.has(me.result) ? "D" : "L";
  const pgn = g.pgn || "";
  const opening = openingForUser(extractOpening(pgn), isW);
  return {
    account, platform: "Chess.com", endTs: g.end_time,
    mode: cap(g.time_class), result,
    elo: me.rating || 0, oppElo: opp.rating || 0,
    moves: movesCount(pgn), opening, group: openingGroup(opening),
    opp: opp.username, color: isW ? "w" : "b",
    reason: result === "L" ? me.result : opp.result,
    pgn, link: g.url || "", moveTimes: moveTimesFromPgn(pgn, isW),
  };
}

export function parseLichessGame(g, user, account) {
  if (LICHESS_SKIP_STATUS.has(g.status) || (g.variant || "standard") !== "standard") return null;
  const whiteName = g.players?.white?.user?.name || "";
  const my = whiteName.toLowerCase() === user.toLowerCase() ? "white" : "black";
  const op = my === "white" ? "black" : "white";
  const result = g.winner === my ? "W" : g.winner === op ? "L" : "D";
  const moves = (g.moves || "").split(" ").filter(Boolean);
  const opening = openingForUser(g.opening?.name || "Nieznany", my === "white");
  return {
    account, platform: "Lichess", endTs: Math.floor((g.lastMoveAt || g.createdAt) / 1000),
    mode: cap(g.speed), result,
    elo: g.players[my].rating || 0, oppElo: g.players[op].rating || 0,
    moves: Math.ceil(moves.length / 2), opening, group: openingGroup(opening),
    opp: g.players[op]?.user?.name || "Anonim", color: my === "white" ? "w" : "b",
    reason: g.status, pgn: g.moves || "", link: `https://lichess.org/${g.id}`,
    moveTimes: moveTimesFromLichess(g.clocks, my === "white"),
  };
}

// Pola czasowe w strefie przeglądarki użytkownika.
export function addLocalTime(game) {
  const d = new Date(game.endTs * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  game.date = d;
  game.hour = d.getHours();
  game.dow = (d.getDay() + 6) % 7; // 0 = poniedziałek
  game.day = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  game.month = game.day.slice(0, 7);
  return game;
}
