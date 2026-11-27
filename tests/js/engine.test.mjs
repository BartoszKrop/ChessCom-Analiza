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

import { cachedAnalysis, useCache, ANALYSIS_DEPTH, DEEP_DEPTH, BATCH_DEPTH } from "../../docs/js/engine.js";

test("cachedAnalysis zwraca zapis tylko gdy był wystarczająco głęboki", async () => {
  const store = new Map([["sf|v6|g1", { depth: 16 }], ["sf|v3|old", { accuracy: 90 }]]);
  useCache(async (k) => store.get(k), async (k, v) => store.set(k, v));
  assert.ok(BATCH_DEPTH < ANALYSIS_DEPTH && ANALYSIS_DEPTH < DEEP_DEPTH);
  assert.deepEqual(await cachedAnalysis({ link: "g1" }, 12), { depth: 16 });
  assert.deepEqual(await cachedAnalysis({ link: "g1" }, 16), { depth: 16 });
  assert.equal(await cachedAnalysis({ link: "g1" }, 20), null);
  assert.equal(await cachedAnalysis({ link: "old" }, 12), null); // stary zapis bez głębokości
  assert.equal(await cachedAnalysis({ link: "none" }, 12), undefined ?? null);
});

import { classifyMove, materialDiff, isSacrifice, KIND_ORDER } from "../../docs/js/engine.js";

test("classifyMove: kategorie jak na Chess.com", () => {
  const base = { drop: 0, isBest: true, gap: 3, winBefore: 50, winAfter: 50 };
  assert.equal(classifyMove(base), "best");
  assert.equal(classifyMove({ ...base, gap: 20 }), "great");
  assert.equal(classifyMove({ ...base, gap: 20, winBefore: 95 }), "best"); // już wygrane: nie „świetny”
  assert.equal(classifyMove({ ...base, sacrifice: true }), "brilliant");
  assert.equal(classifyMove({ ...base, sacrifice: true, winAfter: 20 }), "best"); // poświęcenie, po którym jest źle
  assert.equal(classifyMove({ ...base, isBest: false, drop: 1 }), "excellent");
  assert.equal(classifyMove({ ...base, isBest: false, drop: 4 }), "good");
  assert.equal(classifyMove({ ...base, isBest: false, drop: 7 }), "inaccuracy");
  assert.equal(classifyMove({ ...base, isBest: false, drop: 12 }), "mistake");
  assert.equal(classifyMove({ ...base, isBest: false, drop: 12, prevOppError: true }), "miss");
  assert.equal(classifyMove({ ...base, isBest: false, drop: 25, prevOppError: true }), "blunder");
  assert.equal(KIND_ORDER.length, 9);
});

test("materialDiff i isSacrifice", () => {
  assert.equal(materialDiff("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"), 0);
  assert.equal(materialDiff("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"), 9);
  // Légal: 5.Nxe5 poświęca hetmana (5...Bxd1 6.Bxf7+ Ke7 7.Nd5#)
  const before = "rn1qkbnr/ppp2ppp/3p4/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 2 5";
  const after = "rn1qkbnr/ppp2ppp/3p4/4N3/2B1P1b1/2N5/PPPP1PPP/R1BQK2R b KQkq - 0 5";
  assert.equal(isSacrifice(before, after, ["Bxd1", "Bxf7+", "Ke7", "Nd5#"], true), true);  // hetman poświęcony (mat nie jest „odzyskaniem”)
  assert.equal(isSacrifice(before, after, ["Bxd1", "Bxf7+"], true), true);
  assert.equal(isSacrifice("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2", ["Nc6", "Bb5"], true), false); // zwykły rozwój
  assert.equal(isSacrifice(before, after, ["Bxd1"], true), false);                        // za krótka linia
});
