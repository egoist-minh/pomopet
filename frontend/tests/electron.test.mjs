import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { findAvailablePort, waitForHealth } from '../electron/runtime.js';
import { isTrustedRendererUrl, resolveAppAsset } from '../electron/security.js';
import { normalizeWindowRegions } from '../electron/window-regions.js';
import { createWindowDragTracker } from '../electron/window-drag.js';
import distractionDetector from '../electron/distraction-detector.js';
import {
  calculateCursorChaseStep,
  hasCursorLeftPokeArea,
  registerPetPoke,
} from '../electron/cursor-chase.js';
import { applyScriptHashes } from '../scripts/apply-csp.mjs';

const {
  DistractionTracker,
  classifyDistractionObservation,
  sanitizeDistractionSettings,
} = distractionDetector;

test('main renderer keeps background timers active while its window is hidden', () => {
  const mainSource = readFileSync(new URL('../main.js', import.meta.url), 'utf8');
  assert.match(mainSource, /backgroundThrottling:\s*false/);
});

test('desktop API keys are encrypted and configured by the trusted main process', () => {
  const mainSource = readFileSync(new URL('../main.js', import.meta.url), 'utf8');
  assert.match(mainSource, /assertTrustedSender\(event\)/);
  assert.match(mainSource, /safeStorage\.encryptString\(apiKey\)/);
  assert.match(mainSource, /X-PomoPet-Token/);
  assert.match(mainSource, /configureBackendApiKey\(provider, apiKey\)/);
});

test('pet close requests a bounded goodbye before quitting', () => {
  const mainSource = readFileSync(new URL('../main.js', import.meta.url), 'utf8');
  const preloadSource = readFileSync(new URL('../preload.js', import.meta.url), 'utf8');
  assert.match(mainSource, /app:goodbye-request/);
  assert.match(mainSource, /app:goodbye-complete/);
  assert.match(mainSource, /}, 8000\)/);
  assert.match(preloadSource, /onGoodbyeRequested/);
  assert.match(preloadSource, /notifyGoodbyeComplete/);
});


test('dynamic backend port is a valid loopback port', async () => {
  const port = await findAvailablePort();
  assert.equal(Number.isInteger(port), true);
  assert.equal(port > 0 && port <= 65535, true);
});

test('health wait sends the runtime token', async () => {
  let request;
  await waitForHealth({
    apiBaseUrl: 'http://127.0.0.1:43123/api',
    token: 'session-secret',
    fetchImpl: async (url, options) => {
      request = { url, options };
      return { ok: true, json: async () => ({ status: 'ok' }) };
    },
  });
  assert.equal(request.url, 'http://127.0.0.1:43123/health');
  assert.equal(request.options.headers['X-PomoPet-Token'], 'session-secret');
});

test('app protocol rejects traversal and missing assets', () => {
  const root = 'C:\\PomoPet\\out';
  const existing = new Set([
    'C:\\PomoPet\\out\\index.html',
    'C:\\PomoPet\\out\\settings.html',
  ]);
  const exists = candidate => existing.has(candidate);

  assert.equal(resolveAppAsset(root, 'app://-/index.html', exists), 'C:\\PomoPet\\out\\index.html');
  assert.equal(resolveAppAsset(root, 'app://-/settings', exists), 'C:\\PomoPet\\out\\settings.html');
  assert.equal(resolveAppAsset(root, 'app://-/%2e%2e/secrets.txt', exists), null);
  assert.equal(resolveAppAsset(root, 'app://-/missing.txt', exists), null);
});

test('renderer URL allowlist is limited to the expected app origin', () => {
  assert.equal(isTrustedRendererUrl('app://-/index.html', false), true);
  assert.equal(isTrustedRendererUrl('app://evil/index.html', false), false);
  assert.equal(isTrustedRendererUrl('https://example.com', false), false);
  assert.equal(isTrustedRendererUrl('http://localhost:3000/tasks', true), true);
  assert.equal(isTrustedRendererUrl('http://localhost:4000/tasks', true), false);
});

test('interactive window regions are rounded, clipped, and validated', () => {
  assert.deepEqual(normalizeWindowRegions([
    { x: -5.2, y: 10.8, width: 30.4, height: 20.2 },
    { x: 90, y: 90, width: 30, height: 30 },
    { x: 10, y: 10, width: -1, height: 10 },
    { x: Number.NaN, y: 0, width: 10, height: 10 },
  ], { width: 100, height: 100 }), [
    { x: 0, y: 10, width: 26, height: 21 },
    { x: 90, y: 90, width: 10, height: 10 },
  ]);
});

test('native window drag tracker emits start once and settles after movement stops', () => {
  const states = [];
  const timers = new Map();
  let nextTimer = 1;
  const tracker = createWindowDragTracker(value => states.push(value), {
    settleMs: 160,
    setTimer(callback) {
      const id = nextTimer++;
      timers.set(id, callback);
      return id;
    },
    clearTimer(id) {
      timers.delete(id);
    },
  });

  tracker.start();
  tracker.move();
  assert.deepEqual(states, [true]);
  assert.equal(timers.size, 1);
  [...timers.values()][0]();
  assert.deepEqual(states, [true, false]);
  tracker.dispose();
});

test('cursor chase moves toward an offset from the cursor without leaving the pet body offscreen', () => {
  const first = calculateCursorChaseStep({
    windowBounds: { x: 0, y: 0, width: 520, height: 420 },
    cursor: { x: 900, y: 700 },
    workArea: { x: 0, y: 0, width: 1000, height: 800 },
  });
  assert.deepEqual(first, { x: 5, y: 3, moving: true });

  const atRightEdge = calculateCursorChaseStep({
    windowBounds: { x: 788, y: 461, width: 520, height: 420 },
    cursor: { x: 999, y: 799 },
    workArea: { x: 0, y: 0, width: 1000, height: 800 },
  });
  assert.equal(atRightEdge.moving, false);
});

test('cursor chase triggers on the third poke inside the sequence window', () => {
  const first = registerPetPoke({ count: 0, lastPokeAt: 0, now: 1_000 });
  const second = registerPetPoke({ ...first, now: 1_500 });
  const third = registerPetPoke({ ...second, now: 2_000 });
  assert.equal(first.triggered, false);
  assert.equal(second.triggered, false);
  assert.deepEqual(third, { count: 0, lastPokeAt: 0, triggered: true });

  assert.deepEqual(
    registerPetPoke({ count: 2, lastPokeAt: 1_000, now: 3_100 }),
    { count: 1, lastPokeAt: 3_100, triggered: false },
  );
});

test('an armed chase waits until the cursor leaves the poke area', () => {
  const origin = { x: 300, y: 200 };
  assert.equal(hasCursorLeftPokeArea(origin, { x: 340, y: 220 }), false);
  assert.equal(hasCursorLeftPokeArea(origin, { x: 380, y: 200 }), true);
  assert.equal(hasCursorLeftPokeArea(null, { x: 500, y: 500 }), false);
});

test('automatic distraction tracking waits for the threshold and records once', () => {
  const tracker = new DistractionTracker({
    thresholdMs: 10_000,
    createId: () => 'event-1',
  });
  const signal = {
    key: 'app:discord',
    source: 'app_switch',
    application: 'Discord',
    confidence: 0.95,
    detectedSinceMs: 1_000,
  };

  assert.deepEqual(tracker.observe(signal, 1_000), []);
  assert.deepEqual(tracker.observe(signal, 10_999), []);
  assert.deepEqual(tracker.observe(signal, 11_000), [{
    type: 'start',
    eventId: 'event-1',
    source: 'app_switch',
    application: 'Discord',
    confidence: 0.95,
    startedAt: new Date(1_000).toISOString(),
  }]);
  assert.deepEqual(tracker.observe(signal, 20_000), []);
  assert.deepEqual(tracker.observe(null, 21_000), [{
    type: 'finish',
    eventId: 'event-1',
    endedAt: new Date(21_000).toISOString(),
  }]);
});

test('automatic distraction classification ignores private titles after local matching', () => {
  const settings = sanitizeDistractionSettings({
    distractingApps: ['Discord'],
    distractingTitleKeywords: ['YouTube'],
  });
  const signal = classifyDistractionObservation({
    appName: 'Google Chrome',
    processId: 42,
    windowTitle: 'Private video title - YouTube',
    idleSeconds: 0,
    nowMs: 20_000,
  }, settings, 7);

  assert.deepEqual(signal, {
    key: 'app:google chrome:youtube',
    source: 'app_switch',
    application: 'YouTube · Google Chrome',
    confidence: 0.8,
    detectedSinceMs: 20_000,
  });
  assert.equal(JSON.stringify(signal).includes('Private video title'), false);
});

test('idle detection uses the beginning of the idle period', () => {
  const settings = sanitizeDistractionSettings({ idleThresholdSeconds: 60 });
  const signal = classifyDistractionObservation({
    idleSeconds: 65,
    nowMs: 100_000,
  }, settings, 7);

  assert.equal(signal.source, 'idle');
  assert.equal(signal.detectedSinceMs, 35_000);
});

test('static export CSP permits only the generated inline script hashes', () => {
  const html = '<meta http-equiv="Content-Security-Policy" content="script-src &#x27;self&#x27;"/>'
    + '<script src="/app.js"></script><script>window.__BOOTSTRAP__ = true;</script>';
  const secured = applyScriptHashes(html);

  assert.match(secured, /script-src &#x27;self&#x27; &#x27;sha256-[A-Za-z0-9+/=]+&#x27;/);
  assert.equal(secured.includes('unsafe-inline'), false);
  assert.equal((secured.match(/sha256-/g) || []).length, 1);
});
