const DEFAULT_DISTRACTION_SETTINGS = Object.freeze({
  enabled: true,
  detectionThresholdSeconds: 10,
  idleThresholdSeconds: 60,
  distractingApps: [
    'discord',
    'steam',
    'tiktok',
    'instagram',
    'facebook',
    'netflix',
    'twitch',
  ],
  distractingTitleKeywords: [
    'youtube',
    'facebook',
    'tiktok',
    'instagram',
    'reddit',
    'netflix',
    'twitch',
  ],
});

function clampInteger(value, fallback, minimum, maximum) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.round(parsed)));
}

function normalizeMatchers(value, fallback) {
  if (!Array.isArray(value)) return [...fallback];
  return [...new Set(value
    .filter(item => typeof item === 'string')
    .map(item => item.trim().toLocaleLowerCase())
    .filter(Boolean)
    .slice(0, 50))];
}

function sanitizeDistractionSettings(value = {}) {
  const input = value && typeof value === 'object' ? value : {};
  return {
    enabled: input.enabled !== false,
    detectionThresholdSeconds: clampInteger(
      input.detectionThresholdSeconds,
      DEFAULT_DISTRACTION_SETTINGS.detectionThresholdSeconds,
      5,
      60,
    ),
    idleThresholdSeconds: clampInteger(
      input.idleThresholdSeconds,
      DEFAULT_DISTRACTION_SETTINGS.idleThresholdSeconds,
      30,
      15 * 60,
    ),
    distractingApps: normalizeMatchers(
      input.distractingApps,
      DEFAULT_DISTRACTION_SETTINGS.distractingApps,
    ),
    distractingTitleKeywords: normalizeMatchers(
      input.distractingTitleKeywords,
      DEFAULT_DISTRACTION_SETTINGS.distractingTitleKeywords,
    ),
  };
}

function findMatcher(value, matchers) {
  const normalized = value?.trim().toLocaleLowerCase();
  return normalized ? matchers.find(matcher => normalized.includes(matcher)) || null : null;
}

function formatMatcherLabel(matcher) {
  const specialLabels = {
    youtube: 'YouTube',
    tiktok: 'TikTok',
  };
  return specialLabels[matcher]
    || matcher.replace(/\b\w/g, character => character.toLocaleUpperCase());
}

function classifyDistractionObservation(observation, settings, ownProcessId) {
  if (!settings.enabled || !observation) return null;

  if (observation.idleSeconds >= settings.idleThresholdSeconds) {
    return {
      key: 'idle',
      source: 'idle',
      application: null,
      confidence: 1,
      detectedSinceMs: observation.nowMs - (observation.idleSeconds * 1000),
    };
  }

  const isOwnProcess = ownProcessId instanceof Set
    ? ownProcessId.has(observation.processId)
    : observation.processId === ownProcessId;
  if (!observation.appName || isOwnProcess) return null;

  const appMatched = findMatcher(observation.appName, settings.distractingApps);
  const titleMatched = findMatcher(observation.windowTitle, settings.distractingTitleKeywords);
  if (!appMatched && !titleMatched) return null;

  const appName = String(observation.appName).trim();
  const application = (titleMatched
    ? `${formatMatcherLabel(titleMatched)} · ${appName}`
    : appName).slice(0, 120);
  return {
    key: `app:${appName.toLocaleLowerCase()}:${titleMatched || ''}`,
    source: 'app_switch',
    application,
    confidence: appMatched ? 0.95 : 0.8,
    detectedSinceMs: observation.nowMs,
  };
}

class DistractionTracker {
  constructor({ thresholdMs = 10_000, createId } = {}) {
    this.thresholdMs = thresholdMs;
    this.createId = createId || (() => `${Date.now()}-${Math.random()}`);
    this.candidate = null;
  }

  setThresholdMs(thresholdMs) {
    this.thresholdMs = Math.max(0, Number(thresholdMs) || 0);
  }

  observe(signal, nowMs = Date.now()) {
    const actions = [];
    const nextKey = signal?.key || null;
    const currentKey = this.candidate?.signal.key || null;

    if (nextKey !== currentKey) {
      if (this.candidate?.recorded) {
        actions.push(this.#finishAction(this.candidate, nowMs));
      }
      this.candidate = signal ? {
        eventId: this.createId(),
        signal,
        startedAtMs: Math.min(nowMs, signal.detectedSinceMs ?? nowMs),
        recorded: false,
      } : null;
    }

    if (
      this.candidate
      && !this.candidate.recorded
      && nowMs - this.candidate.startedAtMs >= this.thresholdMs
    ) {
      this.candidate.recorded = true;
      actions.push({
        type: 'start',
        eventId: this.candidate.eventId,
        source: this.candidate.signal.source,
        application: this.candidate.signal.application,
        confidence: this.candidate.signal.confidence,
        startedAt: new Date(this.candidate.startedAtMs).toISOString(),
      });
    }

    return actions;
  }

  reset(nowMs = Date.now()) {
    return this.observe(null, nowMs);
  }

  #finishAction(candidate, nowMs) {
    return {
      type: 'finish',
      eventId: candidate.eventId,
      endedAt: new Date(nowMs).toISOString(),
    };
  }
}

module.exports = {
  DEFAULT_DISTRACTION_SETTINGS,
  DistractionTracker,
  classifyDistractionObservation,
  sanitizeDistractionSettings,
};
