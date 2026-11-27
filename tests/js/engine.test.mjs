import { test } from "node:test";
import assert from "node:assert/strict";
import { winChance, moveAccuracy, classify, evalToCp } from "../../docs/js/engine.js";

test("winChance i klasyfikacja ruchów", () => {
  assert.equal(Math.round(winChance(0)), 50);
  assert.ok(winChance(300) > 70 && winChance(-300) < 30);
  assert.equal(Math.round(moveAccuracy(0)), 100);
  assert.equal(classify(20), "blunder");
  assert.equal(classify(12), "mistake");
  assert.equal(classify(6), "inaccuracy");
  assert.equal(classify(2), null);
  assert.ok(evalToCp({ mate: 3 }) > 9000 && evalToCp({ mate: -2 }) < -9000);
  assert.equal(evalToCp({ cp: 45, mate: null }), 45);
});

import { phaseOf } from "../../docs/js/engine.js";

test("phaseOf: debiut, gra środkowa, końcówka", () => {
  const start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
  assert.equal(phaseOf(start, 5), "open");
  assert.equal(phaseOf(start, 20), "middle");
  assert.equal(phaseOf("4k3/pp3r2/8/8/8/8/PP2R3/4K3 w - - 0 40", 40), "end");
});
