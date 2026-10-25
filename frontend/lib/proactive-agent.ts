export type ProactiveAction =
  | 'STAY_SILENT'
  | 'TELL_JOKE'
  | 'TELL_DRY_HUMOR'
  | 'GIVE_HYDRATION_TIP'
  | 'GIVE_FOCUS_TIP'
  | 'WELCOME'
  | 'GOODBYE'
  | 'SUGGEST_PLAN';
export type ProactiveSessionState = 'idle' | 'running' | 'paused' | 'break';

export interface ProactiveDecision {
  decision_id: string;
  action: ProactiveAction;
  message: string | null;
  target: string | null;
  reason_codes: string[];
  status: 'SELECTED' | 'EXECUTED' | 'SILENT';
  created_at: string | null;
  executed_at: string | null;
}

export interface ProactiveEvaluateInput {
  request_id: string;
  trigger: string;
  session_state: ProactiveSessionState;
  timezone_offset: number;
  provider: 'openai' | 'gemini';
  thread_id?: string;
}

export interface ProactiveTraceEvent {
  sequence: number;
  stage: string;
  details: Record<string, unknown>;
  created_at: string | null;
}

export interface ProactiveRun extends ProactiveDecision {
  state_snapshot: Record<string, unknown>;
  candidate_actions: ProactiveAction[];
  trace: ProactiveTraceEvent[];
}

export const PROACTIVE_POLL_INTERVAL_MS = 5 * 60 * 1000;

export function shouldPresentProactiveDecision(decision: ProactiveDecision): boolean {
  return decision.action !== 'STAY_SILENT' && Boolean(decision.message);
}

export function transitionTrigger(
  previous: ProactiveSessionState,
  current: ProactiveSessionState,
): 'focus_ended' | 'break_ended' | null {
  if (previous === 'running' && current === 'break') return 'focus_ended';
  if (previous === 'break' && current === 'idle') return 'break_ended';
  return null;
}

export function createExecutionAcknowledger(
  markExecuted: (decisionId: string) => Promise<unknown>,
) {
  const acknowledged = new Set<string>();
  return async (decision: ProactiveDecision): Promise<boolean> => {
    if (!shouldPresentProactiveDecision(decision) || acknowledged.has(decision.decision_id)) {
      return false;
    }
    acknowledged.add(decision.decision_id);
    await markExecuted(decision.decision_id);
    return true;
  };
}

interface SchedulerOptions {
  evaluate: (input: ProactiveEvaluateInput) => Promise<ProactiveDecision>;
  getSessionState: () => ProactiveSessionState;
  getProvider: () => 'openai' | 'gemini';
  getThreadId?: () => string | undefined;
  onDecision: (decision: ProactiveDecision) => void | Promise<void>;
  createRequestId?: () => string;
  intervalMs?: number;
  setIntervalFn?: typeof setInterval;
  clearIntervalFn?: typeof clearInterval;
}

export function createProactiveScheduler(options: SchedulerOptions) {
  const intervalMs = options.intervalMs ?? PROACTIVE_POLL_INTERVAL_MS;
  const setIntervalFn = options.setIntervalFn ?? setInterval;
  const clearIntervalFn = options.clearIntervalFn ?? clearInterval;
  const createRequestId = options.createRequestId ?? (() => crypto.randomUUID());
  let timer: ReturnType<typeof setInterval> | null = null;
  let inFlight = false;
  let stopped = false;

  const trigger = async (reason: string): Promise<boolean> => {
    if (stopped || inFlight) return false;
    inFlight = true;
    try {
      const decision = await options.evaluate({
        request_id: createRequestId(),
        trigger: reason,
        session_state: options.getSessionState(),
        timezone_offset: -new Date().getTimezoneOffset(),
        provider: options.getProvider(),
        thread_id: options.getThreadId?.(),
      });
      await options.onDecision(decision);
      return true;
    } finally {
      inFlight = false;
    }
  };

  return {
    start(initialReason = 'periodic') {
      if (timer !== null || stopped) return;
      void trigger(initialReason).catch(() => {});
      timer = setIntervalFn(() => void trigger('periodic').catch(() => {}), intervalMs);
    },
    trigger,
    stop() {
      stopped = true;
      if (timer !== null) clearIntervalFn(timer);
      timer = null;
    },
    isInFlight: () => inFlight,
  };
}
