import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const page = readFileSync("a-crossing.html", "utf8");
const index = readFileSync("index.html", "utf8");

test("A Crossing arrives as a full-viewport playable world", () => {
  assert.match(page, /class="play-stage"/);
  assert.match(page, /id="crossing-stage"/);
  assert.match(page, /min-height:\s*100svh/);
  assert.match(page, /id="passage-hud"/);
  assert.match(page, /id="need-chooser"/);
  assert.match(page, /id="action-ribbon"/);
  assert.doesNotMatch(page, /class="panel"/);
  assert.doesNotMatch(page, /<pre[^>]+id="crossing-source"/);
  assert.doesNotMatch(page, /Opening I/);
});

test("the sparse controls expose pause sound archive seed and replay accessibly", () => {
  assert.match(page, /aria-label="Pause passage"/);
  assert.match(page, /aria-label="Sound off"/);
  assert.match(page, /aria-label="Open the archive"/);
  assert.match(page, /aria-label="Roll a new Passage seed"/);
  assert.match(page, /aria-label="Replay this crossing"/);
  assert.match(page, /aria-label="Passage seed"/);
  assert.match(page, /aria-live="polite"/);
  assert.match(page, /prefers-reduced-motion/);
  assert.match(page, /simulated/i);
});

test("the browser consumes Planes Scene IR rather than owning a crossing model", () => {
  assert.match(page, /paint\/a_crossing\.planes/);
  assert.match(page, /stepGraph/);
  assert.match(page, /BrowserModuleLoader/);
  assert.match(page, /parseSceneIntent/);
  assert.match(page, /createCrossingStage/);
  assert.match(page, /createCrossingAudio/);
  assert.match(page, /intent\.actions/);
  assert.doesNotMatch(page, /function\s+(chooseRoute|calculatePassage|advanceWorld|availableActions)/);
  assert.doesNotMatch(page, /\.(fillRect|arc|bezierCurveTo|moveTo|lineTo)\(/);
  assert.doesNotMatch(page, /createAudioPlayer/);
});

test("the archive is optional and hidden at arrival", () => {
  assert.match(page, /<dialog[^>]+id="crossing-archive"/);
  assert.match(page, /data-tab="revision"/);
  assert.match(page, /data-tab="atlas"/);
  assert.match(page, /data-tab="why"/);
  assert.match(page, /data-tab="source"/);
  assert.match(page, /data-tab="surface"/);
  assert.doesNotMatch(page, /<dialog[^>]+id="crossing-archive"[^>]+open/);
});

test("the Planes mark returns to the showcase index without adding a visual panel", () => {
  assert.match(page, /<a class="world-home" href="\.\/index\.html" aria-label="Back to Planes showcases">/);
  assert.match(page, /class="world-home"[\s\S]*planes-mark-on-dark\.svg[\s\S]*<\/a>/);
  assert.doesNotMatch(page, />\s*Back to (?:index|home|Planes showcases)\s*</i);
});

test("A Crossing joins the index showcase in the same card collection as Garden", () => {
  const cards = /<div class="cards">([\s\S]*?)<\/div>\s*<p class="foot">/.exec(index)?.[1];
  assert.ok(cards, "index.html no longer has its showcase card collection");
  assert.match(cards, /<a class="card" href="\.\/a-crossing\.html">[\s\S]*?<strong>a crossing<\/strong>/);
  assert.match(cards, /<a class="card" href="\.\/garden\.html">[\s\S]*?<strong>the garden<\/strong>/);
  assert.ok(cards.indexOf("./a-crossing.html") < cards.indexOf("./garden.html"), "A Crossing should lead the showcase collection");
});
