'use client';

import { useCallback, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import {
  createProactiveScheduler,
  ProactiveDecision,
  ProactiveSessionState,
  transitionTrigger,
} from '@/lib/proactive-agent';
import { getOrCreateChatThreadId } from '@/lib/chat-memory';

interface UseProactiveAgentOptions {
  ready: boolean;
  sessionState: ProactiveSessionState;
  provider: 'openai' | 'gemini';
  onDecision: (decision: ProactiveDecision) => void | Promise<void>;
}

export function useProactiveAgent({
  ready,
  sessionState,
  provider,
  onDecision,
}: UseProactiveAgentOptions) {
  const sessionRef = useRef(sessionState);
  const providerRef = useRef(provider);
  const previousSessionRef = useRef(sessionState);
  const decisionHandlerRef = useRef(onDecision);
  const schedulerRef = useRef<ReturnType<typeof createProactiveScheduler> | null>(null);
  const welcomeSentRef = useRef(false);

  sessionRef.current = sessionState;
  providerRef.current = provider;
  decisionHandlerRef.current = onDecision;

  useEffect(() => {
    if (!ready) return;
    const scheduler = createProactiveScheduler({
      evaluate: input => api.evaluateProactive(input),
      getSessionState: () => sessionRef.current,
      getProvider: () => providerRef.current,
      getThreadId: () => getOrCreateChatThreadId(localStorage),
      onDecision: decision => decisionHandlerRef.current(decision),
    });
    schedulerRef.current = scheduler;
    scheduler.start(welcomeSentRef.current ? 'periodic' : 'welcome');
    welcomeSentRef.current = true;
    return () => {
      scheduler.stop();
      schedulerRef.current = null;
    };
  }, [ready]);

  useEffect(() => {
    const trigger = transitionTrigger(previousSessionRef.current, sessionState);
    previousSessionRef.current = sessionState;
    if (ready && trigger) void schedulerRef.current?.trigger(trigger);
  }, [ready, sessionState]);

  return useCallback(async (reason = 'manual') => {
    if (!ready || !schedulerRef.current) return false;
    return schedulerRef.current.trigger(reason);
  }, [ready]);
}
