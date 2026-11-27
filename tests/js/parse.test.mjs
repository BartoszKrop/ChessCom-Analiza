import test from "node:test";
import assert from "node:assert/strict";
import { movesCount, moveTimesFromPgn, parseChesscomGame, parseLichessGame, openingGroup, extractOpening } from "../../docs/js/parse.js";
import { streakEffect, eloSummary, filterGames } from "../../docs/js/stats.js";

const PGN = `[Event "Live Chess"]
[Date "2024.01.05"]

1. e4 {[%clk 0:02:59.9]} 1... e5 {[%clk 0:02:58.1]} 2. Qh5 {[%clk 0:02:55.3]} 2... Nc6 {[%clk 0:02:50.7]} 3. Bc4 {[%clk 0:02:50]} 3... Nf6 {[%clk 0:02:45.2]} 4. Qxf7# {[%clk 0:02:48.4]} 1-0`;

test("liczba ruchów ignoruje zegar i datę", () => {
  assert.equal(movesCount(PGN), 4);
  assert.equal(movesCount("1. e4 e5 2. Nf3"), 2);
  assert.equal(movesCount(""), 0);
});

test("czasy ruchów białych", () => assert.deepEqual(moveTimesFromPgn(PGN, true), [4.6, 5.3, 1.6]));

test("debiuty", () => {
  assert.equal(openingGroup("Sicilian Defense: Najdorf"), "Sicilian Defense");
  assert.equal(extractOpening('[ECOUrl "https://www.chess.com/openings/Kings-Pawn-Opening-2.Nf3"]'), "Kings Pawn Opening 2.Nf3");
});

const cc = (rules = "chess", wr = "win", br = "checkmated") => ({
  end_time: 1704470400, rules, time_class: "blitz", pgn: PGN, url: "u",
  white: { username: "Me", result: wr, rating: 1500 }, black: { username: "you", result: br, rating: 1480 },
});

test("Chess.com: parsowanie, warianty pomijane, remis", () => {
  const r = parseChesscomGame(cc(), "me", "me (C)");
  assert.equal(r.result, "W"); assert.equal(r.moves, 4); assert.equal(r.color, "w");
  assert.equal(parseChesscomGame(cc("chess960"), "me", "x"), null);
  assert.equal(parseChesscomGame(cc("chess", "repetition", "repetition"), "me", "x").result, "D");
});

test("Lichess: przerwane pomijane, czas końca partii", () => {
  const g = { id: "a", status: "mate", winner: "black", variant: "standard", speed: "rapid", createdAt: 1e12, lastMoveAt: 1e12 + 60000,
    moves: "e4 e5 Qh5", players: { white: { user: { name: "Me" }, rating: 1 }, black: { user: { name: "x" }, rating: 2 } } };
  const r = parseLichessGame(g, "me", "me (L)");
  assert.equal(r.result, "L"); assert.equal(r.endTs, 1e9 + 60); assert.equal(r.moves, 2);
  assert.equal(parseLichessGame({ ...g, status: "aborted", winner: undefined }, "me", "x"), null);
});

const mk = (endTs, result, elo = 1500, account = "a") => ({ endTs, result, elo, account, mode: "Blitz", day: "2024-01-01", color: "w", hour: 10 });

test("aktualne ELO = najnowsza partia", () => {
  const games = [mk(1, "W", 1400), mk(2, "W", 1600), mk(3, "L", 1550)];
  assert.deepEqual(eloSummary(games, "Blitz"), { peak: 1600, current: 1550 });
});

test("serie w sesji", () => {
  const r = streakEffect([mk(0, "W"), mk(100, "W"), mk(200, "L"), mk(20000, "W")]);
  assert.deepEqual(r.map((x) => [x.type, x.streak, x.winPct]), [["Po serii wygranych", "1 z rzędu", 100], ["Po serii wygranych", "2 z rzędu", 0]]);
});

test("filtry", () => {
  const f = { from: "", to: "", mode: "", colors: ["b"], hourMin: 0, hourMax: 23 };
  assert.equal(filterGames([mk(1, "W")], f).length, 0);
});

import { sanMoves } from "../../docs/js/parse.js";

test("sanMoves czyta ruchy z PGN Chess.com i z listy Lichess", () => {
  const pgn = '[Event "x"]\n\n1. e4 {[%clk 0:02:59.9]} 1... c5 {[%clk 0:02:58]} 2. Nf3 2... d6?! 3. d4 1-0';
  assert.deepEqual(sanMoves(pgn), ["e4", "c5", "Nf3", "d6", "d4"]);
  assert.deepEqual(sanMoves("e4 e5 Nf3 Nc6 Bb5", 3), ["e4", "e5", "Nf3"]);
});
