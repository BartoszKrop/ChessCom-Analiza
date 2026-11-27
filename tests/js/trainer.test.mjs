import { test } from "node:test";
import assert from "node:assert/strict";
import { trainingItems } from "../../docs/js/trainer.js";

test("trainingItems: tylko moje błędy z znanym najlepszym ruchem", () => {
  const r = {
    plies: [{ mine: true, kind: "best" }, { mine: false, kind: "blunder" }, { mine: true, kind: "blunder" }, { mine: true, kind: "miss" }, { mine: true, kind: "mistake" }, { mine: true, kind: "inaccuracy" }],
    best: ["e2e4", "e7e5", "d2d4", "g1f3", null, "a2a3"],
    fens: ["a", "b", "c", "d", "e", "f"],
  };
  assert.deepEqual(trainingItems(r).map((x) => x.i), [2, 3]);
});
