export type PetEmotion =
  | 'idle'
  | 'happy'
  | 'excited'
  | 'worried'
  | 'sad'
  | 'sleepy'
  | 'thinking'
  | 'angry'
  | 'hurt';

export type PetSessionState = 'idle' | 'running' | 'paused' | 'break';

export type PetActivity =
  | 'resting'
  | 'glance-left'
  | 'glance-right'
  | 'tilt-head'
  | 'idle-stretch'
  | 'shake'
  | 'eye-roll'
  | 'sigh'
  | 'follow-cursor'
  | 'yawn'
  | 'doze'
  | 'wake'
  | 'focus-still'
  | 'break-stretch'
  | 'explicit';

export type BehaviorSource = 'ambient' | 'explicit' | 'session' | 'user';
export type PetInteraction = 'cursor' | 'hover' | 'click' | 'drag' | 'return';

export interface PetNeeds {
  energy: number;
  curiosity: number;
  boredom: number;
}

export interface PetTemperament {
  energy: number;
  curiosity: number;
  sociability: number;
}

export interface PetBehaviorState {
  activity: PetActivity;
  source: BehaviorSource;
  activityUntil: number;
  ambientCooldownUntil: number;
  lastUpdatedAt: number;
  lastInteractionAt: number;
  needs: PetNeeds;
  temperament: PetTemperament;
  cooldowns: Partial<Record<PetActivity, number>>;
  sequence: PetActivity[];
  rngState: number;
}

export interface PetBehaviorInput {
  now: number;
  sessionState: PetSessionState;
  explicitEmotion: PetEmotion;
  interaction?: PetInteraction;
  cursorNear?: boolean;
  reducedMotion?: boolean;
  hour?: number;
}

export interface PetVisualStateInput {
  activity: PetActivity;
  emotion: PetEmotion;
  dragging: boolean;
  petted: boolean;
  reducedMotion: boolean;
}

interface WeightedActivity {
  activity: PetActivity;
  weight: number;
}

interface SchedulerTimers {
  setInterval: (callback: () => void, intervalMs: number) => ReturnType<typeof setInterval>;
  clearInterval: (handle: ReturnType<typeof setInterval>) => void;
}

export const PET_TEMPERAMENT_STORAGE_KEY = 'pomopet.temperament-seed.v1';
export const PET_BEHAVIOR_TICK_MS = 1_000;

const SLEEPY_AFTER_SECONDS = 90;
const SLEEP_AFTER_SECONDS = 5 * 60;

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

function hashSeed(seed: string): number {
  let hash = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0 || 1;
}

function nextRandom(rngState: number): { value: number; state: number } {
  const state = (Math.imul(rngState, 1664525) + 1013904223) >>> 0;
  return { value: state / 0x1_0000_0000, state };
}

function sampleRange(
  rngState: number,
  minimum: number,
  maximum: number,
): { value: number; state: number } {
  const random = nextRandom(rngState);
  return {
    value: minimum + ((maximum - minimum) * random.value),
    state: random.state,
  };
}

export function temperamentFromSeed(seed: string): PetTemperament {
  let state = hashSeed(seed);
  const energy = sampleRange(state, 0.35, 0.95);
  state = energy.state;
  const curiosity = sampleRange(state, 0.35, 0.95);
  state = curiosity.state;
  const sociability = sampleRange(state, 0.35, 0.95);
  return {
    energy: energy.value,
    curiosity: curiosity.value,
    sociability: sociability.value,
  };
}

export function createPetBehaviorState(seed: string, now = Date.now()): PetBehaviorState {
  const temperament = temperamentFromSeed(seed);
  return {
    activity: 'resting',
    source: 'ambient',
    activityUntil: now,
    ambientCooldownUntil: now + 2_000,
    lastUpdatedAt: now,
    lastInteractionAt: now,
    needs: {
      energy: 0.55 + (temperament.energy * 0.35),
      curiosity: 0.35 + (temperament.curiosity * 0.45),
      boredom: 0,
    },
    temperament,
    cooldowns: {},
    sequence: [],
    rngState: hashSeed(`${seed}:behavior`),
  };
}

function updateNeeds(state: PetBehaviorState, input: PetBehaviorInput): PetNeeds {
  const elapsedSeconds = Math.max(0, Math.min(60, input.now - state.lastUpdatedAt)) / 1_000;
  const inactiveSeconds = Math.max(0, input.now - state.lastInteractionAt) / 1_000;
  const hour = input.hour ?? new Date(input.now).getHours();
  const isQuietHour = hour >= 22 || hour < 7;
  const isFocus = input.sessionState === 'running';

  let energy = state.needs.energy;
  let curiosity = state.needs.curiosity;
  let boredom = state.needs.boredom;

  energy -= elapsedSeconds * (isQuietHour ? 0.0012 : 0.00035);
  curiosity += elapsedSeconds * (0.0005 + (state.temperament.curiosity * 0.00035));
  boredom += elapsedSeconds * (isFocus ? 0.00015 : 0.0007);

  if (state.activity === 'doze') energy += elapsedSeconds * 0.004;
  if (input.interaction) {
    energy += input.interaction === 'return' ? 0.08 : 0.035;
    curiosity += 0.12 * state.temperament.curiosity;
    boredom = Math.max(0, boredom - (0.3 + (state.temperament.sociability * 0.2)));
  } else if (inactiveSeconds > 120) {
    boredom += elapsedSeconds * 0.0005;
  }

  return {
    energy: clamp01(energy),
    curiosity: clamp01(curiosity),
    boredom: clamp01(boredom),
  };
}

function activityDuration(
  activity: PetActivity,
  temperament: PetTemperament,
  rngState: number,
): { value: number; state: number } {
  const ranges: Record<PetActivity, [number, number]> = {
    resting: [2_000, 4_500],
    'glance-left': [900, 1_600],
    'glance-right': [900, 1_600],
    'tilt-head': [1_200, 2_100],
    'idle-stretch': [1_500, 2_200],
    shake: [800, 1_300],
    'eye-roll': [1_100, 1_700],
    sigh: [1_400, 2_100],
    'follow-cursor': [700, 1_100],
    yawn: [1_700, 2_400],
    doze: [5_000, 10_000 + (5_000 * (1 - temperament.energy))],
    wake: [900, 1_400],
    'focus-still': [1_500, 1_500],
    'break-stretch': [1_400, 2_000],
    explicit: [1_000, 1_000],
  };
  const [minimum, maximum] = ranges[activity];
  return sampleRange(rngState, minimum, maximum);
}

function activityCooldown(activity: PetActivity): number {
  const cooldowns: Record<PetActivity, number> = {
    resting: 0,
    'glance-left': 5_000,
    'glance-right': 5_000,
    'tilt-head': 8_000,
    'idle-stretch': 18_000,
    shake: 12_000,
    'eye-roll': 22_000,
    sigh: 18_000,
    'follow-cursor': 500,
    yawn: 60_000,
    doze: 120_000,
    wake: 2_000,
    'focus-still': 0,
    'break-stretch': 12_000,
    explicit: 0,
  };
  return cooldowns[activity];
}

function enterActivity(
  state: PetBehaviorState,
  activity: PetActivity,
  source: BehaviorSource,
  now: number,
  sequence: PetActivity[] = [],
): PetBehaviorState {
  const sampledDuration = activityDuration(activity, state.temperament, state.rngState);
  return {
    ...state,
    activity,
    source,
    activityUntil: now + sampledDuration.value,
    ambientCooldownUntil: source === 'ambient'
      ? now + sampledDuration.value + (activity === 'resting' ? 0 : 900)
      : state.ambientCooldownUntil,
    cooldowns: source === 'ambient' && activity !== 'resting'
      ? { ...state.cooldowns, [activity]: now + activityCooldown(activity) }
      : state.cooldowns,
    sequence,
    rngState: sampledDuration.state,
  };
}

function chooseWeightedActivity(
  state: PetBehaviorState,
  input: PetBehaviorInput,
): { activity: PetActivity; state: number } {
  const hour = input.hour ?? new Date(input.now).getHours();
  const quietHourMultiplier = hour >= 22 || hour < 7 ? 2.2 : 0.75;
  const inactiveSeconds = Math.max(0, input.now - state.lastInteractionAt) / 1_000;
  const { energy, curiosity, boredom } = state.needs;
  const candidates: WeightedActivity[] = [
    { activity: 'resting', weight: 2.8 },
    { activity: 'glance-left', weight: 0.7 + (curiosity * 2.2) },
    { activity: 'glance-right', weight: 0.7 + (curiosity * 2.2) },
    { activity: 'tilt-head', weight: 0.3 + (curiosity * state.temperament.curiosity * 2.5) },
    { activity: 'idle-stretch', weight: 0.35 + (boredom * 1.8) },
    { activity: 'eye-roll', weight: boredom > 0.3 ? boredom * 1.6 : 0 },
    { activity: 'yawn', weight: Math.max(0, 1 - energy) * quietHourMultiplier * 2.4 },
    {
      activity: 'doze',
      weight: inactiveSeconds > 45
        ? Math.max(0, 0.62 - energy) * quietHourMultiplier * 3.2
        : 0,
    },
  ];
  const entries = candidates.map(entry => ({
    ...entry,
    weight: (state.cooldowns[entry.activity] ?? 0) > input.now ? 0 : entry.weight,
  }));

  entries[0].weight += Math.max(0, 0.35 - boredom);
  const totalWeight = entries.reduce((total, entry) => total + entry.weight, 0);
  const random = nextRandom(state.rngState);
  let threshold = random.value * totalWeight;
  for (const entry of entries) {
    threshold -= entry.weight;
    if (threshold <= 0) return { activity: entry.activity, state: random.state };
  }
  return { activity: 'resting', state: random.state };
}

function ambientSequenceFor(
  activity: PetActivity,
  state: PetBehaviorState,
): PetActivity[] {
  switch (activity) {
    case 'glance-left':
    case 'glance-right':
      return state.needs.curiosity > 0.55
        ? ['tilt-head', 'resting']
        : ['resting'];
    case 'idle-stretch':
      return ['shake', 'resting'];
    case 'eye-roll':
      return ['sigh', 'resting'];
    case 'yawn':
      return state.needs.energy < 0.45
        ? ['doze', 'wake', 'resting']
        : ['resting'];
    case 'doze':
      return ['wake', 'resting'];
    default:
      return [];
  }
}

export function advancePetBehavior(
  previous: PetBehaviorState,
  input: PetBehaviorInput,
): PetBehaviorState {
  let state: PetBehaviorState = {
    ...previous,
    needs: updateNeeds(previous, input),
    lastUpdatedAt: input.now,
    lastInteractionAt: input.interaction ? input.now : previous.lastInteractionAt,
  };

  if (input.reducedMotion) {
    return {
      ...state,
      activity: input.sessionState === 'running' ? 'focus-still' : 'resting',
      source: input.sessionState === 'running' ? 'session' : 'ambient',
      activityUntil: input.now + PET_BEHAVIOR_TICK_MS,
      sequence: [],
    };
  }

  const passiveCursorInteraction = input.interaction === 'cursor'
    && input.sessionState !== 'idle';
  if (input.interaction && !passiveCursorInteraction) {
    const shouldWake = previous.activity === 'doze'
      || previous.activity === 'yawn'
      || input.interaction === 'return';
    const activity = shouldWake
      ? 'wake'
      : input.sessionState === 'idle'
        && (input.interaction === 'cursor' || input.cursorNear)
        ? 'follow-cursor'
        : 'wake';
    return enterActivity(state, activity, 'user', input.now);
  }

  if (previous.source === 'user' && input.now < previous.activityUntil) {
    return { ...state, activity: previous.activity, source: 'user' };
  }

  if (input.sessionState === 'running') {
    return enterActivity(state, 'focus-still', 'session', input.now);
  }

  if (input.sessionState === 'break') {
    if (
      previous.source === 'session'
      && previous.activity === 'break-stretch'
      && input.now < previous.activityUntil
    ) {
      return { ...state, activity: 'break-stretch', source: 'session' };
    }
    const stretchCoolingDown = (state.cooldowns['break-stretch'] ?? 0) > input.now;
    if (!stretchCoolingDown && previous.activity !== 'break-stretch') {
      const stretched = enterActivity(state, 'break-stretch', 'session', input.now);
      return {
        ...stretched,
        cooldowns: {
          ...stretched.cooldowns,
          'break-stretch': input.now + activityCooldown('break-stretch'),
        },
      };
    }
    return {
      ...state,
      activity: 'resting',
      source: 'session',
      activityUntil: input.now + PET_BEHAVIOR_TICK_MS,
      sequence: [],
    };
  }

  if (input.sessionState === 'paused') {
    return {
      ...state,
      activity: 'resting',
      source: 'session',
      activityUntil: input.now + PET_BEHAVIOR_TICK_MS,
      sequence: [],
    };
  }

  if (input.explicitEmotion !== 'idle') {
    return enterActivity(state, 'explicit', 'explicit', input.now);
  }

  if (input.cursorNear) {
    return enterActivity(state, 'follow-cursor', 'user', input.now);
  }

  if (previous.source === 'ambient' && input.now < previous.activityUntil) {
    return { ...state, activity: previous.activity, source: 'ambient' };
  }

  if (previous.source === 'ambient' && previous.sequence.length > 0) {
    const [nextActivity, ...remainingSequence] = previous.sequence;
    return enterActivity(state, nextActivity, 'ambient', input.now, remainingSequence);
  }

  if (input.now < state.ambientCooldownUntil) {
    return {
      ...state,
      activity: 'resting',
      source: 'ambient',
      activityUntil: state.ambientCooldownUntil,
    };
  }


  const inactiveSeconds = Math.max(0, input.now - state.lastInteractionAt) / 1_000;
  const dozeCoolingDown = (state.cooldowns.doze ?? 0) > input.now;
  const yawnCoolingDown = (state.cooldowns.yawn ?? 0) > input.now;
  if (inactiveSeconds >= SLEEP_AFTER_SECONDS && !dozeCoolingDown && !yawnCoolingDown) {
    return enterActivity(
      state,
      'yawn',
      'ambient',
      input.now,
      ['doze', 'wake', 'resting'],
    );
  }
  if (
    inactiveSeconds >= SLEEPY_AFTER_SECONDS
    && inactiveSeconds < SLEEP_AFTER_SECONDS
    && !yawnCoolingDown
  ) {
    return enterActivity(state, 'yawn', 'ambient', input.now, ['resting']);
  }

  const selected = chooseWeightedActivity(state, input);
  state = { ...state, rngState: selected.state };
  const sequence = ambientSequenceFor(selected.activity, state);
  return enterActivity(state, selected.activity, 'ambient', input.now, sequence);
}

export function emotionForBehavior(
  state: PetBehaviorState,
  explicitEmotion: PetEmotion,
): PetEmotion {
  if (state.source === 'explicit') return explicitEmotion;
  if (state.activity === 'doze' || state.activity === 'yawn') return 'sleepy';
  if (state.activity === 'wake' || state.activity === 'break-stretch') return 'happy';
  return 'idle';
}

export function resolvePetVisualState({
  activity,
  emotion,
  dragging,
  petted,
  reducedMotion,
}: PetVisualStateInput): { emotion: PetEmotion; animation: PetActivity | PetEmotion | 'reduced' } {
  const resolvedEmotion: PetEmotion = dragging
    ? 'hurt'
    : petted
      ? 'happy'
      : emotion;
  const animation = reducedMotion
    ? 'reduced'
    : dragging
      ? 'hurt'
      : petted
        ? 'happy'
        : activity === 'resting' || activity === 'explicit'
          ? resolvedEmotion
          : activity;
  return { emotion: resolvedEmotion, animation };
}

export function startPetBehaviorScheduler(
  callback: () => void,
  intervalMs = PET_BEHAVIOR_TICK_MS,
  timers: SchedulerTimers = {
    setInterval: globalThis.setInterval.bind(globalThis),
    clearInterval: globalThis.clearInterval.bind(globalThis),
  },
): () => void {
  const handle = timers.setInterval(callback, intervalMs);
  return () => timers.clearInterval(handle);
}
