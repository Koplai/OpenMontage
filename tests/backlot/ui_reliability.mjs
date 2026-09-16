import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../../backlot/ui/lib.js", import.meta.url), "utf8");
const { subscribe, getJSON, capturePlayback, restorePlayback } =
  await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

const timers = new Map();
let timerId = 0;
globalThis.setTimeout = (fn) => { timers.set(++timerId, fn); return timerId; };
globalThis.clearTimeout = (id) => timers.delete(id);
globalThis.EventSource = class { constructor(url) { this.url = url; } };
let refreshes = 0;
const events = subscribe("/api/project/synthetic/events", () => refreshes++);
const flush = () => { for (const fn of timers.values()) fn(); timers.clear(); };
const message = (type) => events.onmessage({ data: JSON.stringify({ type }) });
message("hello"); flush();
assert.equal(refreshes, 1, "initial connection must reconcile");
message("change"); message("change"); flush();
assert.equal(refreshes, 2, "burst is coalesced");
events.onerror();
message("hello"); flush();
assert.equal(refreshes, 3, "reconnect must reconcile missed changes");
message("heartbeat"); flush();
assert.equal(refreshes, 4, "elapsed time refreshes even without writes");
events.onmessage({ data: "broken JSON" }); message("irrelevant"); flush();
assert.equal(refreshes, 4);

globalThis.fetch = async (_url, options) => {
  assert.equal(options.cache, "no-store");
  return { ok: false, status: 503 };
};
await assert.rejects(getJSON("/state"), (error) => error.status === 503);

function video(src, overrides = {}) {
  const listeners = {};
  return {
    currentTime: 0, duration: 20, paused: true, ended: false, readyState: 0,
    volume: 1, muted: false, playbackRate: 1, isConnected: true, playCalls: 0,
    getAttribute: () => src,
    addEventListener: (type, fn) => { listeners[type] = fn; },
    loaded: () => listeners.loadedmetadata(),
    play() { this.playCalls++; this.paused = false; return Promise.resolve(); },
    ...overrides,
  };
}
const previous = video("/media/synthetic/final.mp4", {
  currentTime: 8.25, paused: false, muted: true, volume: 0.4, playbackRate: 1.5,
});
const oldContainer = { querySelectorAll: () => [previous] };
const snapshots = capturePlayback(oldContainer);
// The old DOM is gone before restoration, as it is in the actual board.
previous.isConnected = false;
const next = video("/media/synthetic/final.mp4");
restorePlayback({ querySelectorAll: () => [next] }, snapshots);
next.loaded();
assert.equal(next.currentTime, 8.25);
assert.equal(next.playCalls, 1);
assert.equal(next.volume, 0.4);
assert.equal(next.muted, true);
assert.equal(next.playbackRate, 1.5);
const paused = video("/media/synthetic/final.mp4", { readyState: 1, duration: 5 });
restorePlayback({ querySelectorAll: () => [paused] }, [{ ...snapshots[0], playing: false }]);
assert.equal(paused.currentTime, 5, "shorter replacement is clamped");
assert.equal(paused.playCalls, 0);
const different = video("/media/synthetic/other.mp4", { readyState: 1 });
restorePlayback({ querySelectorAll: () => [different] }, snapshots);
assert.equal(different.currentTime, 0);
assert.equal(different.playCalls, 0);
console.log("Backlot JS reliability: reconnect, heartbeat, HTTP errors and playback passed");
