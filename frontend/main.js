const { app, BrowserWindow, dialog, ipcMain, powerMonitor, protocol, safeStorage, screen } = require('electron');
const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const { findAvailablePort, waitForHealth } = require('./electron/runtime');
const { isTrustedRendererUrl, resolveAppAsset } = require('./electron/security');
const { normalizeWindowRegions } = require('./electron/window-regions');
const { createWindowDragTracker } = require('./electron/window-drag');
const {
  calculateCursorChaseStep,
  hasCursorLeftPokeArea,
  registerPetPoke,
} = require('./electron/cursor-chase');
const {
  DEFAULT_DISTRACTION_SETTINGS,
  DistractionTracker,
  classifyDistractionObservation,
  sanitizeDistractionSettings,
} = require('./electron/distraction-detector');

const isDev = !app.isPackaged && process.argv.includes('--dev');
const supportedProviders = new Set(['openai', 'gemini']);
const MAX_BACKEND_RESTARTS = 3;

if (process.env.POMOPET_USER_DATA_DIR) {
  const userDataDirectory = path.resolve(process.env.POMOPET_USER_DATA_DIR);
  fs.mkdirSync(userDataDirectory, { recursive: true });
  app.setPath('userData', userDataDirectory);
}

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { secure: true, standard: true, supportFetchAPI: true } },
]);

let backendProcess = null;
let backendRestartCount = 0;
let mainWindow = null;
let petWindow = null;
let latestPetState = null;
let runtimeConfig = null;
let shuttingDown = false;
let goodbyeInProgress = false;
let goodbyeTimeout = null;
let petChaseTimer = null;
let petChaseSuspendedByRenderer = false;
let petChaseSuspendedByDrag = false;
let petChaseMoving = false;
let ignorePetMoveUntil = 0;
let petChaseRequested = false;
let petChaseStarted = false;
let petChaseArmCursor = null;
let petPokeCount = 0;
let petLastPokeAt = 0;
let distractionTimer = null;
let distractionPollInFlight = false;
let distractionSettings = sanitizeDistractionSettings(DEFAULT_DISTRACTION_SETTINGS);
let activeWindowProvider = null;
let activeWindowLoadFailed = false;
let distractionActionQueue = Promise.resolve();

const distractionTracker = new DistractionTracker({
  thresholdMs: distractionSettings.detectionThresholdSeconds * 1000,
  createId: () => crypto.randomUUID(),
});

const PET_CHASE_INTERVAL_MS = 32;
const DISTRACTION_POLL_INTERVAL_MS = 2000;

function ownWindowProcessIds() {
  const processIds = new Set([process.pid]);
  for (const targetWindow of [mainWindow, petWindow]) {
    if (!targetWindow || targetWindow.isDestroyed() || targetWindow.webContents.isDestroyed()) continue;
    processIds.add(targetWindow.webContents.getOSProcessId());
  }
  return processIds;
}

async function getActiveWindow() {
  if (activeWindowLoadFailed) return undefined;
  try {
    if (!activeWindowProvider) {
      const getWindowsModule = await import('get-windows');
      activeWindowProvider = getWindowsModule.activeWindow;
    }
    return await activeWindowProvider({
      accessibilityPermission: false,
      screenRecordingPermission: false,
    });
  } catch (error) {
    activeWindowLoadFailed = true;
    console.warn('[distraction-tracking] Foreground app detection is unavailable:', error?.message || error);
    return undefined;
  }
}

function sendAutoDistractionUpdate(payload) {
  for (const targetWindow of [mainWindow, petWindow]) {
    if (targetWindow && !targetWindow.isDestroyed() && !targetWindow.webContents.isDestroyed()) {
      targetWindow.webContents.send('distraction:recorded', payload);
    }
  }
}

async function requestBackend(endpoint, options) {
  if (!runtimeConfig) throw new Error('Backend is not ready');
  const response = await fetch(`${runtimeConfig.apiBaseUrl}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(runtimeConfig.token ? { 'X-PomoPet-Token': runtimeConfig.token } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `Backend request failed (${response.status})`);
  }
  return response.json();
}

async function processDistractionAction(action) {
  if (action.type === 'start') {
    const result = await requestBackend('/sessions/distraction/automatic', {
      method: 'POST',
      body: JSON.stringify({
        event_id: action.eventId,
        source: action.source,
        application: action.application,
        confidence: action.confidence,
        started_at: action.startedAt,
      }),
    });
    sendAutoDistractionUpdate({
      eventId: action.eventId,
      source: action.source,
      application: action.application,
      distractionCount: result.distraction_count,
    });
    return;
  }

  await requestBackend(`/sessions/distraction/${encodeURIComponent(action.eventId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ ended_at: action.endedAt }),
  });
}

function enqueueDistractionActions(actions) {
  for (const action of actions) {
    distractionActionQueue = distractionActionQueue
      .then(() => processDistractionAction(action))
      .catch(error => {
        console.warn('[distraction-tracking] Failed to persist event:', error?.message || error);
      });
  }
}

function resetDistractionTracker(nowMs = Date.now()) {
  enqueueDistractionActions(distractionTracker.reset(nowMs));
}

async function pollForDistraction() {
  if (distractionPollInFlight) return;
  distractionPollInFlight = true;
  try {
    if (!distractionSettings.enabled || latestPetState?.sessionState !== 'running') {
      resetDistractionTracker();
      return;
    }

    const nowMs = Date.now();
    const idleSeconds = powerMonitor.getSystemIdleTime();
    let activeWindow;
    if (idleSeconds < distractionSettings.idleThresholdSeconds) {
      activeWindow = await getActiveWindow();
    }
    const signal = classifyDistractionObservation({
      appName: activeWindow?.owner?.name,
      processId: activeWindow?.owner?.processId,
      windowTitle: activeWindow?.title,
      idleSeconds,
      nowMs,
    }, distractionSettings, ownWindowProcessIds());
    enqueueDistractionActions(distractionTracker.observe(signal, nowMs));
  } finally {
    distractionPollInFlight = false;
  }
}

function startDistractionTracking() {
  if (distractionTimer) return;
  distractionTimer = setInterval(() => void pollForDistraction(), DISTRACTION_POLL_INTERVAL_MS);
  distractionTimer.unref?.();
}

function stopDistractionTracking() {
  if (distractionTimer) clearInterval(distractionTimer);
  distractionTimer = null;
  resetDistractionTracker();
}

function publishPetChaseState(moving) {
  if (petChaseMoving === moving) return;
  petChaseMoving = moving;
  if (petWindow && !petWindow.isDestroyed() && !petWindow.webContents.isDestroyed()) {
    petWindow.webContents.send('pet-cursor-chase:state', moving);
  }
}

function publishPetChaseBump() {
  if (petWindow && !petWindow.isDestroyed() && !petWindow.webContents.isDestroyed()) {
    petWindow.webContents.send('pet-cursor-chase:bump');
  }
}

function hasIdleChaseContext() {
  return latestPetState?.sessionState === 'idle'
    && !latestPetState?.speechText;
}

function updatePetCursorChase() {
  if (!petWindow || petWindow.isDestroyed()) {
    publishPetChaseState(false);
    return;
  }

  const cursor = screen.getCursorScreenPoint();
  if (!hasIdleChaseContext()) {
    petChaseRequested = false;
    petChaseStarted = false;
    petChaseArmCursor = null;
    petPokeCount = 0;
    petLastPokeAt = 0;
    publishPetChaseState(false);
    return;
  }
  if (!petChaseRequested || petChaseSuspendedByRenderer || petChaseSuspendedByDrag) {
    publishPetChaseState(false);
    return;
  }
  if (!petChaseStarted) {
    if (!hasCursorLeftPokeArea(petChaseArmCursor, cursor)) {
      publishPetChaseState(false);
      return;
    }
    petChaseStarted = true;
  }

  const workArea = screen.getDisplayNearestPoint(cursor).workArea;
  const step = calculateCursorChaseStep({
    windowBounds: petWindow.getBounds(),
    cursor,
    workArea,
  });
  publishPetChaseState(step.moving);
  if (!step.moving) {
    petChaseRequested = false;
    petChaseStarted = false;
    petChaseArmCursor = null;
    publishPetChaseBump();
    return;
  }

  ignorePetMoveUntil = Date.now() + (PET_CHASE_INTERVAL_MS * 3);
  petWindow.setPosition(step.x, step.y, false);
}

function startPetCursorChase() {
  if (petChaseTimer) return;
  petChaseTimer = setInterval(updatePetCursorChase, PET_CHASE_INTERVAL_MS);
  petChaseTimer.unref?.();
}

function stopPetCursorChase() {
  if (petChaseTimer) clearInterval(petChaseTimer);
  petChaseTimer = null;
  petChaseRequested = false;
  petChaseStarted = false;
  petChaseArmCursor = null;
  petPokeCount = 0;
  petLastPokeAt = 0;
  publishPetChaseState(false);
}

function ensurePetWindowVisible() {
  if (!petWindow || petWindow.isDestroyed()) return;
  const bounds = petWindow.getBounds();
  const center = {
    x: bounds.x + Math.round(bounds.width / 2),
    y: bounds.y + Math.round(bounds.height / 2),
  };
  const workArea = screen.getDisplayNearestPoint(center).workArea;
  const maximumX = workArea.x + Math.max(0, workArea.width - bounds.width);
  const maximumY = workArea.y + Math.max(0, workArea.height - bounds.height);
  const x = Math.max(workArea.x, Math.min(maximumX, bounds.x));
  const y = Math.max(workArea.y, Math.min(maximumY, bounds.y));
  if (x === bounds.x && y === bounds.y) return;
  ignorePetMoveUntil = Date.now() + (PET_CHASE_INTERVAL_MS * 3);
  petWindow.setPosition(x, y, false);
}

function getApiKeyStorePath() {
  return path.join(app.getPath('userData'), 'api-keys.json');
}

function readApiKeyStore() {
  const storePath = getApiKeyStorePath();
  if (!fs.existsSync(storePath)) return {};
  try {
    const parsed = JSON.parse(fs.readFileSync(storePath, 'utf8'));
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function assertProvider(provider) {
  if (typeof provider !== 'string' || !supportedProviders.has(provider)) {
    throw new Error('Unsupported AI provider');
  }
}

function assertTrustedSender(event) {
  const senderUrl = event.senderFrame?.url || event.sender.getURL();
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  if (
    !senderWindow
    || ![mainWindow, petWindow].includes(senderWindow)
    || !isTrustedRendererUrl(senderUrl, isDev)
  ) {
    throw new Error('Request rejected');
  }
  return senderWindow;
}

function assertWindowSender(event, expectedWindow) {
  const senderWindow = assertTrustedSender(event);
  if (!expectedWindow || senderWindow !== expectedWindow) throw new Error('Request rejected');
  return senderWindow;
}

function getDevelopmentRuntimeConfig() {
  const backendUrl = process.env.POMOPET_BACKEND_URL || 'http://127.0.0.1:8000';
  const parsed = new URL(backendUrl);
  if (parsed.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(parsed.hostname)) {
    throw new Error('POMOPET_BACKEND_URL must use a loopback HTTP address');
  }
  return {
    apiBaseUrl: `${backendUrl.replace(/\/$/, '')}/api`,
    token: process.env.POMOPET_RUNTIME_TOKEN || '',
  };
}

function sendBackendStatus(state, message) {
  for (const targetWindow of [mainWindow, petWindow]) {
    if (targetWindow && !targetWindow.isDestroyed()) {
      targetWindow.webContents.send('backend:status', { state, message });
    }
  }
}

function backendExecutablePath() {
  return path.join(process.resourcesPath, 'backend', 'pomopet-backend.exe');
}

async function startManagedBackend() {
  if (!runtimeConfig) {
    const port = await findAvailablePort();
    runtimeConfig = {
      apiBaseUrl: `http://127.0.0.1:${port}/api`,
      token: crypto.randomBytes(32).toString('base64url'),
    };
  }

  const executable = backendExecutablePath();
  if (!fs.existsSync(executable)) {
    throw new Error('Packaged backend executable is missing');
  }

  const port = new URL(runtimeConfig.apiBaseUrl).port;
  const args = [
    '--host', '127.0.0.1',
    '--port', port,
    '--data-dir', app.getPath('userData'),
    '--parent-pid', String(process.pid),
  ];
  const child = spawn(executable, args, {
    env: { ...process.env, POMOPET_RUNTIME_TOKEN: runtimeConfig.token },
    stdio: 'ignore',
    windowsHide: true,
  });
  backendProcess = child;
  const spawnFailure = new Promise((_, reject) => child.once('error', reject));

  child.once('exit', () => {
    if (backendProcess === child) backendProcess = null;
    if (shuttingDown) return;

    backendRestartCount += 1;
    if (backendRestartCount > MAX_BACKEND_RESTARTS) {
      sendBackendStatus('failed', 'The local backend stopped repeatedly. Restart PomoPet.');
      return;
    }

    sendBackendStatus('starting', 'Restarting the local backend…');
    setTimeout(() => {
      startManagedBackend()
        .then(() => sendBackendStatus('ready'))
        .catch(error => sendBackendStatus('failed', error.message));
    }, Math.min(backendRestartCount * 1000, 3000));
  });

  await Promise.race([
    waitForHealth({ apiBaseUrl: runtimeConfig.apiBaseUrl, token: runtimeConfig.token }),
    spawnFailure,
  ]);
}

function stopManagedBackend() {
  const child = backendProcess;
  backendProcess = null;
  if (!child || child.killed) return;
  if (process.platform === 'win32') {
    spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    });
  } else {
    child.kill();
  }
}

function registerStaticProtocol() {
  const outDirectory = path.join(__dirname, 'out');
  protocol.registerFileProtocol('app', (request, callback) => {
    const assetPath = resolveAppAsset(outDirectory, request.url, fs.existsSync);
    if (!assetPath) {
      callback({ error: -6 });
      return;
    }
    callback({ path: assetPath });
  });
}

function loadRenderer(targetWindow, role) {
  const target = isDev
    ? `http://localhost:3000/?window=${role}`
    : `app://-/index.html?window=${role}`;
  void targetWindow.loadURL(target);
}

function createWindows() {
  const display = screen.getPrimaryDisplay();
  const petWidth = 520;
  const petHeight = 420;
  petChaseSuspendedByRenderer = false;
  petChaseSuspendedByDrag = false;
  ignorePetMoveUntil = 0;
  mainWindow = new BrowserWindow({
    width: 560,
    height: 620,
    minWidth: 460,
    minHeight: 540,
    show: false,
    backgroundColor: '#f3f4f6',
    frame: false,
    skipTaskbar: false,
    resizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      backgroundThrottling: false,
      preload: path.join(__dirname, 'preload.js'),
      additionalArguments: ['--pomopet-window-role=main'],
    },
  });

  petWindow = new BrowserWindow({
    width: petWidth,
    height: petHeight,
    x: display.workArea.x + display.workArea.width - petWidth - 16,
    y: display.workArea.y + display.workArea.height - petHeight - 16,
    transparent: true,
    frame: false,
    hasShadow: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
      additionalArguments: ['--pomopet-window-role=pet'],
    },
  });

  petWindow.setIgnoreMouseEvents(true, { forward: true });

  const petDragTracker = createWindowDragTracker(isDragging => {
    petChaseSuspendedByDrag = isDragging;
    if (petWindow && !petWindow.isDestroyed() && !petWindow.webContents.isDestroyed()) {
      petWindow.webContents.send('pet-window:drag-state', isDragging);
    }
  });
  petWindow.on('will-move', petDragTracker.start);
  petWindow.on('move', () => {
    if (!petChaseMoving && Date.now() >= ignorePetMoveUntil) petDragTracker.move();
  });

  for (const targetWindow of [mainWindow, petWindow]) {
    targetWindow.webContents.on('will-navigate', (event, url) => {
      if (!isTrustedRendererUrl(url, isDev)) event.preventDefault();
    });
    targetWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  }

  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
  loadRenderer(mainWindow, 'main');
  loadRenderer(petWindow, 'pet');
  startPetCursorChase();

  mainWindow.on('close', event => {
    if (shuttingDown) return;
    event.preventDefault();
    mainWindow.hide();
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  petWindow.on('close', event => {
    if (shuttingDown) return;
    event.preventDefault();
    if (goodbyeInProgress) return;
    goodbyeInProgress = true;

    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.webContents.isDestroyed()) {
      mainWindow.webContents.send('app:goodbye-request');
      goodbyeTimeout = setTimeout(() => {
        goodbyeTimeout = null;
        shuttingDown = true;
        app.quit();
      }, 8000);
      return;
    }
    shuttingDown = true;
    app.quit();
  });
  petWindow.on('closed', () => {
    petDragTracker.dispose();
    stopPetCursorChase();
    petWindow = null;
    if (!shuttingDown) app.quit();
  });
}

ipcMain.handle('runtime:get-config', event => {
  assertTrustedSender(event);
  if (!runtimeConfig) throw new Error('Backend is not ready');
  if (process.env.POMOPET_SMOKE_MARKER) {
    fs.writeFileSync(path.resolve(process.env.POMOPET_SMOKE_MARKER), 'ready', 'utf8');
  }
  return runtimeConfig;
});

ipcMain.on('set-ignore-mouse-events', (event, ignore, options) => {
  try {
    const senderWindow = assertTrustedSender(event);
    if (typeof ignore !== 'boolean') return;
    const safeOptions = options?.forward === true ? { forward: true } : undefined;
    senderWindow.setIgnoreMouseEvents(ignore, safeOptions);
  } catch {
    // Ignore messages from untrusted or already-closed renderers.
  }
});

ipcMain.on('set-window-regions', (event, regions) => {
  try {
    const senderWindow = assertWindowSender(event, petWindow);
    if (typeof senderWindow.setShape !== 'function') return;

    const bounds = senderWindow.getContentBounds();
    const safeRegions = normalizeWindowRegions(regions, bounds);
    if (safeRegions.length === 0) {
      senderWindow.setIgnoreMouseEvents(true, { forward: true });
      return;
    }

    senderWindow.setShape(safeRegions);
    senderWindow.setIgnoreMouseEvents(false);
  } catch {
    // Ignore malformed messages or messages sent while the window is closing.
  }
});

ipcMain.handle('pet-state:get', event => {
  assertWindowSender(event, petWindow);
  return latestPetState;
});

ipcMain.on('pet-state:publish', (event, state) => {
  try {
    assertWindowSender(event, mainWindow);
    if (!state || typeof state !== 'object') return;
    const wasRunning = latestPetState?.sessionState === 'running';
    latestPetState = state;
    if (wasRunning && state.sessionState !== 'running') resetDistractionTracker();
    if (state.speechText) ensurePetWindowVisible();
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send('pet-state:update', state);
    }
  } catch {
    // Ignore invalid state publishers.
  }
});

ipcMain.on('distraction-tracking:configure', (event, settings) => {
  try {
    assertWindowSender(event, mainWindow);
    distractionSettings = sanitizeDistractionSettings(settings);
    distractionTracker.setThresholdMs(distractionSettings.detectionThresholdSeconds * 1000);
    if (!distractionSettings.enabled) resetDistractionTracker();
  } catch {
    // Ignore malformed settings or messages from an untrusted renderer.
  }
});

ipcMain.on('pet-action:send', (event, action) => {
  try {
    assertWindowSender(event, petWindow);
    if (!action || typeof action.type !== 'string') return;
    if (action.type === 'open-main' && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('pet-action:receive', action);
    }
  } catch {
    // Ignore invalid pet actions.
  }
});

ipcMain.on('pet-cursor-chase:set-suspended', (event, suspended, keepWindowVisible) => {
  try {
    assertWindowSender(event, petWindow);
    if (typeof suspended !== 'boolean') return;
    petChaseSuspendedByRenderer = suspended;
    if (suspended) {
      publishPetChaseState(false);
    }
    if (keepWindowVisible === true) {
      petChaseRequested = false;
      petChaseStarted = false;
      petChaseArmCursor = null;
    }
    if (suspended && keepWindowVisible === true) ensurePetWindowVisible();
  } catch {
    // Ignore malformed messages or messages sent while the pet window is closing.
  }
});

ipcMain.on('pet-cursor-chase:poke', event => {
  try {
    assertWindowSender(event, petWindow);
    if (!hasIdleChaseContext()) return;
    const sequence = registerPetPoke({
      count: petPokeCount,
      lastPokeAt: petLastPokeAt,
      now: Date.now(),
    });
    petPokeCount = sequence.count;
    petLastPokeAt = sequence.lastPokeAt;
    if (sequence.triggered) {
      petChaseRequested = true;
      petChaseStarted = false;
      petChaseArmCursor = screen.getCursorScreenPoint();
    }
  } catch {
    // Ignore malformed messages or messages sent while the pet window is closing.
  }
});

ipcMain.on('main-window:set-visible', (event, visible) => {
  try {
    assertWindowSender(event, mainWindow);
    if (typeof visible !== 'boolean') return;
    if (visible) {
      mainWindow.show();
      mainWindow.focus();
    } else {
      mainWindow.hide();
    }
  } catch {
    // Ignore messages sent while the main window is closing.
  }
});

ipcMain.on('app:goodbye-complete', event => {
  assertTrustedSender(event);
  if (!goodbyeInProgress || shuttingDown) return;
  if (goodbyeTimeout) clearTimeout(goodbyeTimeout);
  goodbyeTimeout = null;
  shuttingDown = true;
  app.quit();
});

ipcMain.handle('api-key:restore', async event => {
  assertTrustedSender(event);
  if (!safeStorage.isEncryptionAvailable()) return false;
  if (!runtimeConfig) throw new Error('Backend is not ready');

  const store = readApiKeyStore();
  for (const provider of supportedProviders) {
    const encryptedKey = store[provider];
    if (typeof encryptedKey !== 'string') continue;

    const apiKey = safeStorage.decryptString(Buffer.from(encryptedKey, 'base64'));
    await configureBackendApiKey(provider, apiKey);
  }
  return true;
});

async function configureBackendApiKey(provider, apiKey) {
  if (!runtimeConfig) throw new Error('Backend is not ready');
  const response = await fetch(`${runtimeConfig.apiBaseUrl}/chat/providers/${provider}/key`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-PomoPet-Token': runtimeConfig.token,
    },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!response.ok) throw new Error(`Failed to configure ${provider} API key`);
}

ipcMain.handle('api-key:set', async (event, provider, apiKey) => {
  assertTrustedSender(event);
  assertProvider(provider);
  if (typeof apiKey !== 'string' || apiKey.length < 8 || apiKey.length > 500) {
    throw new Error('Invalid API key');
  }
  await configureBackendApiKey(provider, apiKey);
  if (!safeStorage.isEncryptionAvailable()) return false;

  const storePath = getApiKeyStorePath();
  const store = readApiKeyStore();
  store[provider] = safeStorage.encryptString(apiKey).toString('base64');
  fs.writeFileSync(storePath, JSON.stringify(store), { encoding: 'utf8', mode: 0o600 });
  return true;
});

app.whenReady().then(async () => {
  try {
    registerStaticProtocol();
    if (isDev) {
      runtimeConfig = getDevelopmentRuntimeConfig();
      await waitForHealth({ ...runtimeConfig, timeoutMs: 15000 });
    } else {
      await startManagedBackend();
    }
    createWindows();
    startDistractionTracking();
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown startup error';
    try {
      fs.writeFileSync(path.join(app.getPath('userData'), 'startup-error.log'), message, 'utf8');
    } catch {
      // The dialog below remains the recovery path when the log cannot be written.
    }
    await dialog.showMessageBox({
      type: 'error',
      title: 'PomoPet could not start',
      message: 'The local PomoPet service could not be started.',
      detail: message,
    });
    app.quit();
  }
});

app.on('before-quit', () => {
  shuttingDown = true;
  if (goodbyeTimeout) clearTimeout(goodbyeTimeout);
  goodbyeTimeout = null;
  stopPetCursorChase();
  stopDistractionTracking();
  stopManagedBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && runtimeConfig) createWindows();
  else if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show();
});
