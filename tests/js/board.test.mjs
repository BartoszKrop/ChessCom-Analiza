import { test } from "node:test";
import assert from "node:assert/strict";
import { renderBoard } from "../../docs/js/board.js";

test("renderBoard rysuje 64 pola, bierki i strzałki", () => {
  const el = {};
  renderBoard(el, { fen: "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", last: ["e2", "e4"], arrows: [{ from: "e7", to: "e5", color: "#0f0" }] });
  assert.equal((el.innerHTML.match(/class="sq /g) || []).length, 64);
  assert.equal((el.innerHTML.match(/class="pc /g) || []).length, 32);
  assert.equal((el.innerHTML.match(/ hl /g) || []).length, 2);
  assert.equal((el.innerHTML.match(/<polygon/g) || []).length, 1);
});
