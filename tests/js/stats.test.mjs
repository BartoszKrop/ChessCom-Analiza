import { test } from "node:test";
import assert from "node:assert/strict";
import { weekGrid } from "../../docs/js/stats.js";

test("weekGrid sumuje partie po tygodniach i lata w wierszach", () => {
  const games = ["2024-12-30", "2025-01-01", "2025-01-05", "2025-01-06", "2025-01-20"].map((day) => ({ day }));
  const g = weekGrid(games);
  assert.deepEqual(g.years, [2024, 2025]);
  assert.equal(g.z[0][52], 3);           // pon 30.12.2024 – nd 05.01.2025
  assert.equal(g.text[0][52], "30.12.2024");
  assert.equal(g.z[1][0], 1);            // 06.01.2025
  assert.equal(g.z[1][1], 0);            // tydzień bez partii
  assert.equal(g.z[1][2], 1);            // 20.01.2025
  assert.equal(g.z[1][3], null);         // po ostatniej partii
  assert.equal(g.z[0][0], null);         // przed pierwszą partią
});

test("weekGrid bez partii", () => assert.deepEqual(weekGrid([]).years, []));
