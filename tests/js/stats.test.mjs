import { test } from "node:test";
import assert from "node:assert/strict";
import { monthGrid } from "../../docs/js/stats.js";

test("monthGrid sumuje partie po miesiącach", () => {
  const g = monthGrid(["2024-11-03", "2024-11-20", "2025-02-01"].map((day) => ({ month: day.slice(0, 7) })));
  assert.deepEqual(g.years, [2024, 2025]);
  assert.equal(g.z[0][9], null);
  assert.equal(g.z[0][10], 2);
  assert.equal(g.z[0][11], 0);
  assert.equal(g.z[1][1], 1);
  assert.equal(g.z[1][2], null);
});

import { sessionIndexWin, ratingDiffWin, timeResults, opponents, monthSummary, prevMonth, openingTree } from "../../docs/js/stats.js";

test("sessionIndexWin numeruje partie w sesji", () => {
  const games = [0, 600, 1200, 20000, 20600].map((endTs, i) => ({ endTs, result: i % 2 ? "L" : "W" }));
  const m = sessionIndexWin(games);
  assert.equal(m.get("1").n, 2);
  assert.equal(m.get("2").n, 2);
  assert.equal(m.get("3").n, 1);
});

test("ratingDiffWin grupuje po różnicy rankingu", () => {
  const m = ratingDiffWin([{ elo: 1000, oppElo: 1250, result: "L" }, { elo: 1000, oppElo: 950, result: "W" }, { elo: 0, oppElo: 900, result: "W" }]);
  assert.equal(m.get("≥ 200").n, 1);
  assert.equal(m.get("−100…−1").winPct, 100);
  assert.equal([...m.values()].reduce((s, e) => s + e.n, 0), 2);
});

test("timeResults liczy porażki na czas", () => {
  const r = timeResults([{ mode: "Blitz", result: "L", reason: "timeout" }, { mode: "Blitz", result: "L", reason: "resigned" }, { mode: "Bullet", result: "W", reason: "outoftime" }]);
  assert.deepEqual(r[0], { mode: "Wszystkie", losses: 2, lostOnTime: 1, lossPct: 50, wins: 1, wonOnTime: 1, winPct: 100 });
  assert.equal(r.find((x) => x.mode === "Rapid"), undefined);
});

test("opponents zwraca rywali z min. 3 partiami", () => {
  const g = (opp, result) => ({ opp, platform: "Lichess", result, day: "2025-01-01" });
  const r = opponents([g("a", "W"), g("a", "L"), g("a", "L"), g("b", "W"), g("Anonim", "W"), g("Anonim", "W"), g("Anonim", "W")]);
  assert.equal(r.length, 1);
  assert.deepEqual([r[0].opp, r[0].n, r[0].score, r[0].winPct, r[0].lossPct], ["a", 3, -1, 33, 67]);
});

test("monthSummary i prevMonth", () => {
  assert.equal(prevMonth("2025-01"), "2024-12");
  const g = (month, elo, result, group = "X") => ({ month, elo, result, group, mode: "Blitz", account: "u (C)" });
  const s = monthSummary([g("2024-12", 1000, "W"), g("2025-01", 1010, "W"), g("2025-01", 1030, "L"), g("2025-01", 1020, "W")], "2025-01");
  assert.equal(s.n, 3);
  assert.equal(s.winPct, 67);
  assert.deepEqual(s.elo.Blitz, { end: 1020, change: 20, n: 3 });
  assert.equal(s.best.name, "X");
  assert.equal(s.worst, null);
});

test("openingTree liczy kolejne ruchy po ścieżce", () => {
  const games = [["e4", "e5"], ["e4", "c5"], ["e4", "c5"], ["d4"]].map((m, i) => ({ m, result: i ? "W" : "L" }));
  const r = openingTree(games, ["e4"], (g) => g.m);
  assert.deepEqual(r.map((x) => [x.move, x.n, x.winPct]), [["c5", 2, 100], ["e5", 1, 0]]);
});

import { quickResigns } from "../../docs/js/stats.js";

test("quickResigns liczy poddania przed 20. ruchem", () => {
  const g = (reason, moves, result = "L", group = "Sicilian Defense", mode = "Blitz") => ({ reason, moves, result, group, mode });
  const r = quickResigns([g("resigned", 12), g("resign", 15, "L", "French Defense"), g("resigned", 30), g("timeout", 10), g("resigned", 10, "W")]);
  assert.equal(r.n, 2);
  assert.equal(r.losses, 4);
  assert.equal(r.pct, 50);
  assert.deepEqual(r.byMode, [{ mode: "Blitz", n: 2, losses: 4, pct: 50 }]);
});
