import { test } from "node:test";
import assert from "node:assert/strict";
import { patterns } from "../../docs/js/insights.js";
import { gameAccuracy } from "../../docs/js/engine.js";

const ply = (san, kind, phase = "open", why = null, no = 5) => ({ san, kind, phase, why, mine: true, no });
const game = (result, plies, evals = [0, 0], accuracy = 80, color = "w") => ({ game: { result, color }, res: { plies, evals, accuracy } });

test("patterns: za mało partii", () => assert.deepEqual(patterns([game("L", [])]), []));

test("patterns: faza pierwszego błędu, figura, zmarnowane przewagi, maty", () => {
  const lostEarly = () => game("L", [ply("Qh5", "blunder", "open", { code: "material", pts: 9 }, 3), ply("e4", "best")], [0, -300]);
  const rs = [lostEarly(), lostEarly(), lostEarly(), game("L", [ply("Rf1", "mistake", "end")], [0, 400]), game("W", [ply("e4", "best")], [0, 500]), game("D", [ply("Nf3", "good")], [0, 450]),
    game("L", [ply("Qxe5", "miss", "open", { code: "missedMate", n: 2 }), ply("Qh4", "blunder", "open", { code: "allowedMate", n: 1 })], [0, 600])];
  const texts = patterns(rs).map((x) => x.text).join("\n");
  assert.match(texts, /pierwszy poważny błąd robisz w debiucie/);
  assert.match(texts, /hetmanem/);
  assert.match(texts, /miałeś wyraźną przewagę/);
  assert.match(texts, /Przeoczone maty: 1, dopuszczone maty rywala: 1/);
  assert.match(texts, /oddałeś figurę lub więcej/);
  assert.match(texts, /błąd rażący już w pierwszych 15 ruchach/);
});

test("gameAccuracy: partie z błędem dostają mniej niż średnia ruchów, czyste ~100", () => {
  const evals = Array.from({ length: 21 }, (_, i) => (i < 10 ? 20 : -400));
  const drops = Array.from({ length: 20 }, (_, i) => (i === 8 ? 35 : 0));
  const acc = gameAccuracy(evals, drops, (i) => i % 2 === 0);
  assert.ok(acc < 100 && acc > 50);
  assert.equal(gameAccuracy(Array(21).fill(10), Array(20).fill(0), (i) => i % 2 === 0), 100);
  const blunder = gameAccuracy(evals, drops.map((d, i) => (i === 8 ? 35 : d)), (i) => i % 2 === 0);
  assert.ok(blunder < 95, `${blunder} < 95`);
});

import { calibrateAccuracy } from "../../docs/js/engine.js";
test("calibrateAccuracy: lekko ściska wyniki do środka, zachowuje kolejność", () => {
  assert.equal(calibrateAccuracy(100), 94.5);
  assert.ok(calibrateAccuracy(92.1) < 92.1 && calibrateAccuracy(60) > 60);
  assert.ok(calibrateAccuracy(80) < calibrateAccuracy(81));
});
