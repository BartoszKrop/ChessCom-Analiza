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
