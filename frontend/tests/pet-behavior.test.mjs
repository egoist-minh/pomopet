import assert from 'node:assert/strict';
import test from 'node:test';

import {
  advancePetBehavior,
  createPetBehaviorState,
  emotionForBehavior,
  resolvePetVisualState,
  startPetBehaviorScheduler,
  temperamentFromSeed,
} from '../lib/pet-behavior.ts';

const baseInput = (now, overrides = {}) => ({
  now,
  sessionState: 'idle',
  explicitEmotion: 'idle',
  cursorNear: false,
  reducedMotion: false,
  hour: 14,
  ...overrides,
});

test('temperament and ambient transitions are deterministic for a stable seed', () => {
  assert.deepEqual(temperamentFromSeed('pomo-42'), temperamentFromSeed('pomo-42'));

  let first = createPetBehaviorState('pomo-42', 0);
  let second = createPetBehaviorState('pomo-42', 0);
  for (const now of [2_001, 7_000, 15_000, 30_000, 60_000]) {
    first = advancePetBehavior(first, baseInput(now));
    second = advancePetBehavior(second, baseInput(now));
    assert.deepEqual(first, second);
  }
});

test('behavior priority is user interaction, session, explicit emotion, then ambient', () => {
  const initial = createPetBehaviorState('priority', 0);

  const explicit = advancePetBehavior(initial, baseInput(3_000, {
    explicitEmotion: 'thinking',
  }));
  assert.equal(explicit.source, 'explicit');
  assert.equal(explicit.activity, 'explicit');
  assert.equal(emotionForBehavior(explicit, 'thinking'), 'thinking');

  const session = advancePetBehavior(explicit, baseInput(4_000, {
    sessionState: 'running',
    explicitEmotion: 'excited',
  }));
  assert.equal(session.source, 'session');
  assert.equal(session.activity, 'focus-still');

  const user = advancePetBehavior(session, baseInput(4_100, {
    sessionState: 'running',
    explicitEmotion: 'excited',
    interaction: 'click',
  }));
  assert.equal(user.source, 'user');
  assert.equal(user.activity, 'wake');

  const userStillWins = advancePetBehavior(user, baseInput(4_500, {
    sessionState: 'running',
    explicitEmotion: 'excited',
  }));
  assert.equal(userStillWins.source, 'user');
  assert.equal(userStillWins.activity, 'wake');

  const breakEvent = advancePetBehavior(session, baseInput(6_000, {
    sessionState: 'break',
    explicitEmotion: 'excited',
  }));
  assert.equal(breakEvent.source, 'session');
  assert.equal(breakEvent.activity, 'break-stretch');
});

test('a yawn transition sequence can settle into a timed doze', () => {
  const initial = createPetBehaviorState('sleepy', 0);
  const yawning = {
    ...initial,
    activity: 'yawn',
    source: 'ambient',
    activityUntil: 1_000,
    ambientCooldownUntil: 1_000,
    sequence: ['doze'],
    needs: { ...initial.needs, energy: 0.2 },
  };

  const dozing = advancePetBehavior(yawning, baseInput(1_001, { hour: 23 }));
  assert.equal(dozing.activity, 'doze');
  assert.equal(dozing.source, 'ambient');
  assert.equal(dozing.activityUntil > 1_001, true);

  const awake = advancePetBehavior(dozing, baseInput(1_100, {
    hour: 23,
    interaction: 'hover',
  }));
  assert.equal(awake.activity, 'wake');
  assert.equal(awake.source, 'user');
});

test('long idle progresses through sleepy, sleep, wake, and rest', () => {
  const initial = {
    ...createPetBehaviorState('long-idle', 0),
    activityUntil: 0,
    ambientCooldownUntil: 0,
  };

  const sleepy = advancePetBehavior(initial, baseInput(90_001));
  assert.equal(sleepy.activity, 'yawn');
  assert.deepEqual(sleepy.sequence, ['resting']);
  assert.equal(emotionForBehavior(sleepy, 'idle'), 'sleepy');

  const readyToSleep = {
    ...initial,
    lastUpdatedAt: 240_000,
    needs: { ...initial.needs, energy: 0.35 },
  };
  const yawning = advancePetBehavior(readyToSleep, baseInput(300_001));
  assert.equal(yawning.activity, 'yawn');
  assert.deepEqual(yawning.sequence, ['doze', 'wake', 'resting']);

  const dozing = advancePetBehavior(yawning, baseInput(yawning.activityUntil + 1));
  assert.equal(dozing.activity, 'doze');
  const waking = advancePetBehavior(dozing, baseInput(dozing.activityUntil + 1));
  assert.equal(waking.activity, 'wake');
  const resting = advancePetBehavior(waking, baseInput(waking.activityUntil + 1));
  assert.equal(resting.activity, 'resting');
});

test('passive cursor chasing only runs while no session is active', () => {
  const initial = createPetBehaviorState('cursor-session', 0);
  const idleChase = advancePetBehavior(initial, baseInput(3_000, {
    interaction: 'cursor',
    cursorNear: true,
  }));
  assert.equal(idleChase.activity, 'follow-cursor');
  assert.equal(idleChase.source, 'user');

  const focus = advancePetBehavior(initial, baseInput(3_000, {
    sessionState: 'running',
    interaction: 'cursor',
    cursorNear: true,
  }));
  assert.equal(focus.activity, 'focus-still');
  assert.equal(focus.source, 'session');

  const breakState = advancePetBehavior(initial, baseInput(3_000, {
    sessionState: 'break',
    interaction: 'cursor',
    cursorNear: true,
  }));
  assert.equal(breakState.activity, 'break-stretch');
  assert.equal(breakState.source, 'session');
});

test('ambient free actions complete their configured chains', () => {
  const initial = createPetBehaviorState('free-actions', 0);
  const stretching = {
    ...initial,
    activity: 'idle-stretch',
    source: 'ambient',
    activityUntil: 1_000,
    ambientCooldownUntil: 1_000,
    sequence: ['shake', 'resting'],
  };

  const shaking = advancePetBehavior(stretching, baseInput(1_001));
  assert.equal(shaking.activity, 'shake');
  assert.deepEqual(shaking.sequence, ['resting']);
  const resting = advancePetBehavior(shaking, baseInput(shaking.activityUntil + 1));
  assert.equal(resting.activity, 'resting');
  assert.deepEqual(resting.sequence, []);
});

test('ambient cooldown prevents the same glance from immediately repeating', () => {
  const initial = createPetBehaviorState('cooldown', 0);
  const expiredGlance = {
    ...initial,
    activity: 'glance-left',
    source: 'ambient',
    activityUntil: 3_000,
    ambientCooldownUntil: 3_000,
    cooldowns: { 'glance-left': 20_000 },
  };

  const next = advancePetBehavior(expiredGlance, baseInput(3_001));
  assert.notEqual(next.activity, 'glance-left');
});

test('reduced motion suppresses ambient animation while preserving focus state', () => {
  const initial = createPetBehaviorState('reduced', 0);
  const idle = advancePetBehavior(initial, baseInput(3_000, { reducedMotion: true }));
  assert.equal(idle.activity, 'resting');

  const focus = advancePetBehavior(idle, baseInput(4_000, {
    reducedMotion: true,
    sessionState: 'running',
  }));
  assert.equal(focus.activity, 'focus-still');
  assert.equal(focus.source, 'session');
});

test('drag and head pet expressions override autonomous activity in priority order', () => {
  const base = {
    activity: 'follow-cursor',
    emotion: 'idle',
    reducedMotion: false,
  };
  assert.deepEqual(resolvePetVisualState({
    ...base,
    dragging: false,
    petted: true,
  }), { emotion: 'happy', animation: 'happy' });
  assert.deepEqual(resolvePetVisualState({
    ...base,
    dragging: true,
    petted: true,
  }), { emotion: 'hurt', animation: 'hurt' });
});

test('behavior scheduler cleanup clears its timer exactly once', () => {
  const calls = [];
  const handle = { id: 7 };
  const cleanup = startPetBehaviorScheduler(() => calls.push('tick'), 250, {
    setInterval(callback, intervalMs) {
      calls.push(['start', intervalMs]);
      callback();
      return handle;
    },
    clearInterval(value) {
      calls.push(['clear', value]);
    },
  });

  cleanup();
  assert.deepEqual(calls, [
    ['start', 250],
    'tick',
    ['clear', handle],
  ]);
});
