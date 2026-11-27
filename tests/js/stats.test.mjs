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
