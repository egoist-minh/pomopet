export type TimerSessionState = 'idle' | 'running' | 'paused' | 'break';

export const EXTENSION_PROMPT_SECONDS = 2 * 60;

export function nextTimerValue(timeLeft: number): number {
  return Math.max(0, timeLeft - 1);
}

export function remainingSecondsUntil(deadlineMs: number, nowMs = Date.now()): number {
  return Math.max(0, Math.ceil((deadlineMs - nowMs) / 1000));
}

export function shouldHandleTimerEnd(state: TimerSessionState, timeLeft: number): boolean {
  return timeLeft === 0 && (state === 'running' || state === 'break');
}

export function shouldOfferSessionExtension(
  state: TimerSessionState,
  timeLeft: number,
): boolean {
  return state === 'running' && timeLeft > 0 && timeLeft <= EXTENSION_PROMPT_SECONDS;
}
