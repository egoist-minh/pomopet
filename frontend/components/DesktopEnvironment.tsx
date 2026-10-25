'use client';

import { useRef, useState, useEffect, useCallback } from 'react';
import type { Emotion, SessionState } from './FloatingPet';
import MainWindow from './MainWindow';
import SetupModal from './SetupModal';
import { AnimatePresence } from 'motion/react';
import { api, Task, AIProvider, AIProviderStatus, BehaviorActionContext, ChatMessageItem, setErrorCallback, APIError } from '@/lib/api';
import { initializeLogger } from '@/lib/logger';
import {
  remainingSecondsUntil,
  shouldHandleTimerEnd,
  shouldOfferSessionExtension,
} from '@/lib/session-timer';
import { getOrCreateChatThreadId } from '@/lib/chat-memory';
import {
  appendProactivePlanSuggestion,
  hasUnresolvedChatAction,
  resolveChatActionRequest,
  updateChatActionStatus,
} from '@/lib/chat-actions';
import type {
  AutoDistractionRecorded,
  DistractionTrackingSettings,
  PetProactiveAnimation,
  PetWindowAction,
  PetWindowState,
} from '@/lib/desktop-ipc';
import { getSpeechBubbleDisplayDuration } from '@/lib/speech-bubble';
import { useProactiveAgent } from '@/hooks/use-proactive-agent';
import {
  createExecutionAcknowledger,
  ProactiveDecision,
  shouldPresentProactiveDecision,
} from '@/lib/proactive-agent';

const readPetNameFromStorage = (): string | null => {
  if (typeof window === 'undefined') return null;

  const storedName = localStorage.getItem('petName');
  return storedName?.trim() ? storedName.trim() : null;
};

interface ElectronKeyStore {
  windowRole?: 'main' | 'pet';
  getRuntimeConfig?: () => Promise<{ apiBaseUrl: string; token: string }>;
  setIgnoreMouseEvents?: (ignore: boolean, options?: { forward?: boolean }) => void;
  publishPetState?: (state: PetWindowState) => void;
  onPetAction?: (callback: (action: PetWindowAction) => void) => () => void;
  setMainWindowVisible?: (visible: boolean) => void;
  restoreApiKeys?: () => Promise<boolean>;
  setApiKey?: (provider: AIProvider, apiKey: string) => Promise<boolean>;
  onBackendStatus?: (callback: (status: { state: 'starting' | 'ready' | 'failed'; message?: string }) => void) => () => void;
  onGoodbyeRequested?: (callback: () => void) => () => void;
  notifyGoodbyeComplete?: () => void;
  configureDistractionTracking?: (settings: DistractionTrackingSettings) => void;
  onAutoDistraction?: (callback: (event: AutoDistractionRecorded) => void) => () => void;
}

const getElectronKeyStore = (): ElectronKeyStore | undefined => {
  if (typeof window === 'undefined') return undefined;
  return (window as Window & { electron?: ElectronKeyStore }).electron;
};

export default function DesktopEnvironment() {
  const [isReady, setIsReady] = useState(false);
  const [petName, setPetName] = useState<string | null>(readPetNameFromStorage);
  const [showSetupModal, setShowSetupModal] = useState<boolean>(() => readPetNameFromStorage() === null);
  const [emotion, setEmotion] = useState<Emotion>('idle');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMainWindowOpen, setIsMainWindowOpen] = useState(false);
  const [speechText, setSpeechText] = useState<string | null>(null);
  const [isDesktopMode, setIsDesktopMode] = useState(false);
  const [activeTab, setActiveTab] = useState<'chat' | 'tasks' | 'stats' | 'settings'>('chat');
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const hasPendingChatAction = hasUnresolvedChatAction(messages);
  const [backendConnected, setBackendConnected] = useState(false);
  const [aiProvider, setAiProvider] = useState<AIProvider>(() => {
    if (typeof window === 'undefined') return 'gemini';
    const defaultVersion = 'gemini-default-v1';
    if (localStorage.getItem('ai_provider_default_version') !== defaultVersion) {
      localStorage.setItem('ai_provider', 'gemini');
      localStorage.setItem('ai_provider_default_version', defaultVersion);
      return 'gemini';
    }
    return localStorage.getItem('ai_provider') === 'openai' ? 'openai' : 'gemini';
  });
  const [configuredProviders, setConfiguredProviders] = useState<AIProviderStatus>({
    openai: false,
    gemini: false,
  });
  const [planRefreshToken, setPlanRefreshToken] = useState(0);
  const [proactiveDecision, setProactiveDecision] = useState<ProactiveDecision | null>(null);
  const [proactiveAnimation, setProactiveAnimation] = useState<PetProactiveAnimation>(null);

  // Task & Session State
  const [, setTasks] = useState<Task[]>([]);
  const tasksRef = useRef<Task[]>([]);
  const [sessionState, setSessionState] = useState<SessionState>('idle');
  const [timeLeft, setTimeLeft] = useState<number>(0);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [focusHoursToday, setFocusHoursToday] = useState(0);
  const [focusHoursWeek, setFocusHoursWeek] = useState(0);
  const [sessionsCompleted, setSessionsCompleted] = useState(0);
  const [distractionChain, setDistractionChain] = useState(0);
  const [apiError, setApiError] = useState<string | null>(null);
  const [autoDistractionEnabled, setAutoDistractionEnabled] = useState(() => {
    if (typeof window === 'undefined') return true;
    return localStorage.getItem('auto_distraction_tracking') !== 'false';
  });

  const initialDistractionData = Array.from({ length: 12 }, (_, i) => ({
    time: `${(i * 2).toString().padStart(2, '0')}:00`,
    distractions: 0
  }));
  const [distractionData, setDistractionData] = useState<{time: string, distractions: number}[]>(initialDistractionData);

  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const timerDeadlineRef = useRef<number | null>(null);
  const timeLeftRef = useRef(timeLeft);
  const chatSpeechTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const extensionSpeechTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const proactiveSpeechTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const goodbyeHandledRef = useRef(false);
  const proactiveAcknowledgerRef = useRef(
    createExecutionAcknowledger((decisionId) => api.markProactiveExecuted(decisionId)),
  );
  const zeroHandledRef = useRef(false);
  const sessionTransitionRef = useRef(false);
  const extensionPromptedRef = useRef(false);
  timeLeftRef.current = timeLeft;

  // Load data from backend
  const loadTasks = useCallback(async () => {
    const loadedTasks = await api.getTasks();
    if (loadedTasks) {
      const mappedTasks = loadedTasks.map(t => ({
        ...t,
        priority: t.priority as 'high' | 'medium' | 'low'
      }));
      setTasks(mappedTasks);
      tasksRef.current = mappedTasks;
    }
  }, []);

  const loadStatistics = useCallback(async () => {
    const stats = await api.getStatistics();
    if (stats) {
      setFocusHoursToday(stats.focusHoursToday);
      setFocusHoursWeek(stats.focusHoursWeek);
      setSessionsCompleted(stats.sessionsCompleted);
      setDistractionChain(stats.distractionChain);
      setDistractionData(stats.distractionData);
    }
  }, []);

  const restoreSession = useCallback(async () => {
    const session = await api.getCurrentSession();
    if (session) {
      const stateMap: Record<string, SessionState> = {
        'running': 'running',
        'paused': 'paused',
        'completed': 'break',
        'cancelled': 'idle'
      };
      setSessionState(stateMap[session.state] || 'idle');
      setTimeLeft(session.time_left);
      setDistractionChain(session.distraction_count);

      if (session.task_id) {
        const task = tasksRef.current.find(t => t.id === session.task_id);
        if (task) {
          setCurrentTask(task);
        }
      }
    }
  }, []);

  const restoreApiKeys = useCallback(async () => {
    const keyStore = getElectronKeyStore();
    if (keyStore?.restoreApiKeys) {
      try {
        await keyStore.restoreApiKeys();
      } catch (error) {
        console.error('[restoreApiKeys] Failed to restore API keys', error);
      }
    }
    setConfiguredProviders(await api.getAIProviders());
  }, []);

  const saveApiKey = useCallback(async (provider: AIProvider, apiKey: string) => {
    const keyStore = getElectronKeyStore();
    if (keyStore?.setApiKey) {
      try {
        const persisted = await keyStore.setApiKey(provider, apiKey);
        setConfiguredProviders(current => ({ ...current, [provider]: true }));
        return persisted;
      } catch (error) {
        console.error(`[saveApiKey] Failed to persist ${provider} key`, error);
        throw error;
      }
    }

    // Browser development has no OS secure storage. Keep the key only in the
    // backend process memory; never place it in localStorage or renderer state.
    await api.configureAIProvider(provider, apiKey);
    setConfiguredProviders(current => ({ ...current, [provider]: true }));
    return false;
  }, []);

  // Initial data load
  useEffect(() => {
    initializeLogger();
    localStorage.removeItem('ai_openai_key');
    localStorage.removeItem('ai_claude_key');
    localStorage.removeItem('ai_service');

    const initBackend = async () => {
      try {
        console.log(`[Init] Checking backend health via api.getTasks()...`);
        const loadedTasks = await api.getTasks();
        if (!Array.isArray(loadedTasks)) {
          throw new APIError('Invalid tasks response', undefined, '/tasks/');
        }
        const mappedTasks = loadedTasks.map(task => ({
          ...task,
          priority: task.priority as 'high' | 'medium' | 'low',
        }));
        setTasks(mappedTasks);
        tasksRef.current = mappedTasks;
        console.log(`[Init] Backend responded successfully. Tasks count: ${loadedTasks.length}`);
        setApiError(null);
        setBackendConnected(true);

        try { await restoreApiKeys(); } catch (e) { console.error(e); }
        try { await loadStatistics(); } catch (e) { console.error(e); }
        try { await restoreSession(); } catch (e) { console.error(e); }

      } catch (e) {
        setBackendConnected(false);
        const err = e instanceof APIError ? e : new APIError(String(e));
        setApiError(err.message);
      } finally {
        const finalCheckName = localStorage.getItem('petName');
        const targetPetName = finalCheckName?.trim() ? finalCheckName.trim() : null;

        if (targetPetName) {
          setPetName(targetPetName);
          setShowSetupModal(false);
        } else {
          setShowSetupModal(true);
        }

        setIsReady(true);
      }
    };

    void initBackend();

    setErrorCallback((error: APIError) => {
      setApiError(
        error.requestId
          ? `${error.message} (ref: ${error.requestId})`
          : error.message,
      );
      if (error.status === undefined) {
        setBackendConnected(false);
      }
    });

    return () => setErrorCallback(null);
  }, [loadStatistics, restoreApiKeys, restoreSession]);

  useEffect(() => {
    const keyStore = getElectronKeyStore();
    if (!keyStore?.onBackendStatus) return;
    return keyStore.onBackendStatus(status => {
      if (status.state === 'ready') {
        setBackendConnected(true);
        setApiError(null);
      } else {
        setBackendConnected(false);
        setApiError(status.message || 'Backend is starting…');
      }
    });
  }, []);

  useEffect(() => {
    if (!isReady) return;
    getElectronKeyStore()?.setMainWindowVisible?.(showSetupModal || isMainWindowOpen);
  }, [isMainWindowOpen, isReady, showSetupModal]);

  useEffect(() => {
    if (!isReady) return;
    getElectronKeyStore()?.publishPetState?.({
      petName,
      emotion,
      isSpeaking,
      speechText,
      proactiveAnimation,
      sessionState,
      timeLeft,
      currentTaskName: currentTask?.name,
    });
  }, [currentTask?.name, emotion, isReady, isSpeaking, petName, proactiveAnimation, sessionState, speechText, timeLeft]);

  useEffect(() => {
    if (!isReady) return;
    getElectronKeyStore()?.configureDistractionTracking?.({
      enabled: autoDistractionEnabled,
      detectionThresholdSeconds: 10,
      idleThresholdSeconds: 60,
    });
    localStorage.setItem('auto_distraction_tracking', String(autoDistractionEnabled));
  }, [autoDistractionEnabled, isReady]);

  useEffect(() => {
    const bridge = getElectronKeyStore();
    if (!bridge?.onAutoDistraction) return;
    return bridge.onAutoDistraction(distraction => {
      setDistractionChain(distraction.distractionCount);
      void loadStatistics().catch(error => {
        console.error('[autoDistraction] Failed to refresh distraction statistics', error);
      });
      setEmotion('worried');
      setSpeechText(
        distraction.source === 'idle'
          ? 'LOOKS LIKE YOU STEPPED AWAY. READY TO FOCUS AGAIN?'
          : `${distraction.application || 'ANOTHER APP'} PULLED YOU AWAY. LET'S COME BACK!`,
      );
      setTimeout(() => {
        setEmotion(current => current === 'worried' ? 'happy' : current);
        setSpeechText(null);
      }, 5000);
    });
  }, [loadStatistics]);

  const handleSetupComplete = useCallback((name: string) => {
    const finalName = name.trim();
    setPetName(finalName);
    setShowSetupModal(false);
    localStorage.setItem('petName', finalName);

    setMessages([{ role: 'pet', text: `Hello! I am ${finalName}, your new desktop companion.` }]);
    setEmotion('happy');
    setIsSpeaking(true);
    setSpeechText(`BOOT SEQUENCE COMPLETE. GREETINGS, I AM ${finalName}.`);

    setTimeout(() => {
      setEmotion('idle');
      setIsSpeaking(false);
      setSpeechText(null);
    }, 4000);
  }, []);

  const handleProactiveDecision = useCallback((decision: ProactiveDecision) => {
    if (!shouldPresentProactiveDecision(decision) || !decision.message) return;
    if (proactiveSpeechTimerRef.current) clearTimeout(proactiveSpeechTimerRef.current);
    setProactiveDecision(decision);
    if (decision.action === 'SUGGEST_PLAN') {
      setMessages(current => appendProactivePlanSuggestion(current, decision));
    }
    if (decision.action === 'WELCOME') {
      setMessages(current => [...current, { role: 'pet', text: decision.message! }]);
    }
    setProactiveAnimation(
      decision.action === 'GIVE_HYDRATION_TIP' ? 'drink-water' : null,
    );
    setEmotion(
      decision.action === 'TELL_JOKE' || decision.action === 'WELCOME' ? 'excited'
        : decision.action === 'TELL_DRY_HUMOR' || decision.action === 'GIVE_HYDRATION_TIP' ? 'happy'
          : decision.action === 'GOODBYE' ? 'sleepy'
          : 'thinking',
    );
    setIsSpeaking(true);
    setSpeechText(decision.message);
    const message = decision.message;
    proactiveSpeechTimerRef.current = setTimeout(() => {
      setSpeechText(current => current === message ? null : current);
      setIsSpeaking(false);
      setProactiveAnimation(null);
      setEmotion(current => ['excited', 'thinking', 'happy', 'sleepy'].includes(current) ? 'idle' : current);
      proactiveSpeechTimerRef.current = null;
    }, getSpeechBubbleDisplayDuration(message));
  }, []);

  const triggerProactiveNow = useProactiveAgent({
    ready: backendConnected && isReady && !showSetupModal && Boolean(petName),
    sessionState,
    provider: aiProvider,
    onDecision: handleProactiveDecision,
  });

  useEffect(() => {
    const bridge = getElectronKeyStore();
    if (!bridge?.onGoodbyeRequested) return;
    return bridge.onGoodbyeRequested(() => {
      if (goodbyeHandledRef.current) return;
      goodbyeHandledRef.current = true;
      void triggerProactiveNow('goodbye')
        .catch(error => console.error('[proactive] Goodbye failed', error))
        .finally(() => {
          setTimeout(() => bridge.notifyGoodbyeComplete?.(), 2400);
        });
    });
  }, [triggerProactiveNow]);

  // This effect runs after React commits the bubble text. Only then does the
  // backend starts cooldown only after the selected action was actually rendered.
  useEffect(() => {
    if (
      !proactiveDecision?.message
      || speechText !== proactiveDecision.message
    ) return;
    void proactiveAcknowledgerRef.current(proactiveDecision).catch(error => {
      console.error('[proactive] Failed to mark rendered decision', error);
    });
  }, [proactiveDecision, speechText]);

  const handleSendMessage = useCallback(async (msg: string) => {
    if (hasPendingChatAction) return;
    if (chatSpeechTimerRef.current) {
      clearTimeout(chatSpeechTimerRef.current);
      chatSpeechTimerRef.current = null;
    }
    setMessages(prev => [...prev, { role: 'user', text: msg }]);
    setSpeechText(null);
    setEmotion('thinking');

    try {
      const threadId = getOrCreateChatThreadId(localStorage);
      const timezoneOffset = -new Date().getTimezoneOffset();
      const response = await api.sendChat(
        msg,
        aiProvider,
        threadId,
        timezoneOffset,
      );
      if (response.plan_changed) {
        setPlanRefreshToken(current => current + 1);
        void loadTasks().catch(error => {
          console.error('[handleSendMessage] Failed to refresh plan tasks', error);
        });
      }
      const reply = response.message;
      setMessages(prev => [
        ...prev,
        {
          role: 'pet',
          text: reply,
          action: response.action,
          actionStatus: response.action ? 'pending' : undefined,
        },
      ]);
      if (response.action) {
        setIsMainWindowOpen(true);
        setActiveTab('chat');
      }
      setEmotion('happy');
      setIsSpeaking(true);
      setSpeechText(reply);
      setTimeout(() => setIsSpeaking(false), Math.min(reply.length * 50, 2500));
      chatSpeechTimerRef.current = setTimeout(() => {
        setSpeechText(current => current === reply ? null : current);
        chatSpeechTimerRef.current = null;
      }, getSpeechBubbleDisplayDuration(reply));
      setTimeout(() => setEmotion('idle'), 2000);
    } catch (error) {
      console.error('[handleSendMessage] Chat request failed', error);
      setEmotion('worried');
      setSpeechText(`CHAT IS UNAVAILABLE. CHECK ${aiProvider.toUpperCase()}_API_KEY.`);
    }
  }, [aiProvider, hasPendingChatAction, loadTasks]);

  useEffect(() => () => {
    if (chatSpeechTimerRef.current) {
      clearTimeout(chatSpeechTimerRef.current);
    }
    if (extensionSpeechTimerRef.current) {
      clearTimeout(extensionSpeechTimerRef.current);
    }
    if (proactiveSpeechTimerRef.current) {
      clearTimeout(proactiveSpeechTimerRef.current);
    }
  }, []);

  const handleChatAction = useCallback(async (
    actionId: string,
    decision: 'confirm' | 'cancel',
  ) => {
    setMessages(current => updateChatActionStatus(current, actionId, 'processing'));

    try {
      const pendingAction = messages.find(message => message.action?.id === actionId)?.action;
      if (
        decision === 'confirm'
        && pendingAction?.type === 'extend_focus_session'
        && sessionState === 'running'
      ) {
        await api.updateTimeLeft(timeLeft);
      }
      const threadId = getOrCreateChatThreadId(localStorage);
      const response = await resolveChatActionRequest(
        actionId,
        decision,
        threadId,
        async () => {
          const dataResults = await Promise.allSettled([loadTasks(), loadStatistics()]);
          const sessionResults = await Promise.allSettled([restoreSession()]);
          const failure = [...dataResults, ...sessionResults].find(
            result => result.status === 'rejected',
          );
          if (failure?.status === 'rejected') throw failure.reason;
        },
        api,
      );
      if (response.plan_changed) {
        setPlanRefreshToken(current => current + 1);
      }

      setMessages(current => [
        ...updateChatActionStatus(
          current,
          actionId,
          decision === 'confirm' ? 'completed' : 'cancelled',
        ),
        { role: 'pet', text: response.message },
      ]);
      setEmotion(decision === 'confirm' ? 'happy' : 'idle');
    } catch (error) {
      console.error('[handleChatAction] Action resolution failed', error);
      setMessages(current => updateChatActionStatus(current, actionId, 'error'));
      setEmotion('worried');
    }
  }, [loadStatistics, loadTasks, messages, restoreSession, sessionState, timeLeft]);

  // Timer Effect
  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (sessionState === 'running' || sessionState === 'break') {
      timerDeadlineRef.current = Date.now() + timeLeftRef.current * 1000;
      timerRef.current = setInterval(() => {
        setTimeLeft(prev => {
          const deadline = timerDeadlineRef.current;
          if (deadline === null) return prev;
          const next = remainingSecondsUntil(deadline);
          if (next === 0) {
            if (timerRef.current) {
              clearInterval(timerRef.current);
              timerRef.current = null;
            }
          }
          return next;
        });
      }, 250);
    } else {
      timerDeadlineRef.current = null;
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      timerRef.current = null;
    };
  }, [sessionState]);

  useEffect(() => {
    if (sessionState === 'running' && backendConnected && timeLeft > 0 && timeLeft % 10 === 0) {
      void api.updateTimeLeft(timeLeft).catch(() => {});
    }
  }, [sessionState, backendConnected, timeLeft]);

  useEffect(() => {
    if (!shouldOfferSessionExtension(sessionState, timeLeft)) {
      if (sessionState !== 'running' || timeLeft > 120) {
        extensionPromptedRef.current = false;
      }
      return;
    }
    if (extensionPromptedRef.current) return;

    extensionPromptedRef.current = true;
    setEmotion('thinking');
    setSpeechText('ONLY 2 MINUTES LEFT. ENTER HOW MANY MINUTES YOU NEED!');
    if (extensionSpeechTimerRef.current) clearTimeout(extensionSpeechTimerRef.current);
    extensionSpeechTimerRef.current = setTimeout(() => {
      extensionSpeechTimerRef.current = null;
      setSpeechText(current => current?.startsWith('ONLY 2 MINUTES LEFT') ? null : current);
      setEmotion(current => current === 'thinking' ? 'happy' : current);
    }, 8000);
  }, [sessionState, timeLeft]);

  const handleSessionComplete = useCallback(async () => {
    if (sessionState === 'running') {
      if (!backendConnected) {
        console.error(`[handleSessionComplete] Backend NOT connected - cannot complete session!`);
        throw new Error('Backend not connected');
      }

      await api.completeSession();
      await Promise.allSettled([loadTasks(), loadStatistics()]);
      setPlanRefreshToken(current => current + 1);

      setSessionState('break');
      setTimeLeft(5 * 60);
      setEmotion('excited');
      setSpeechText('SESSION COMPLETE! GREAT JOB!');

      setTimeout(() => {
        setEmotion('sleepy');
        setSpeechText('TIME FOR A QUICK BREAK...');
        setTimeout(() => setSpeechText(null), 4000);
      }, 4000);
    } else if (sessionState === 'break') {
      setEmotion('idle');
      setSpeechText('BREAK OVER! READY FOR NEXT TASK?');
      setSessionState('idle');
      setCurrentTask(null);
      setTimeout(() => setSpeechText(null), 4000);
    }
  }, [sessionState, backendConnected, loadStatistics, loadTasks]);

  useEffect(() => {
    if (timeLeft > 0) {
      zeroHandledRef.current = false;
      return;
    }

    if (!shouldHandleTimerEnd(sessionState, timeLeft) || zeroHandledRef.current) {
      return;
    }

    zeroHandledRef.current = true;
    void handleSessionComplete().catch((error) => {
      console.error('[handleSessionComplete] Failed to complete session', error);
      setEmotion('worried');
      setSpeechText('FAILED TO COMPLETE SESSION. CHECK THE BACKEND.');
    });
  }, [timeLeft, sessionState, handleSessionComplete]);

  const handleCancelSession = useCallback(async () => {
    if (!backendConnected) {
      console.error(`[handleCancelSession] Backend NOT connected - cannot cancel session!`);
      setApiError('Backend not connected');
      return;
    }

    try {
      await api.cancelSession();
      setSessionState('idle');
      setCurrentTask(null);
      setTimeLeft(0);
      setEmotion('sad');
      setSpeechText('SESSION CANCELLED...');
      setDistractionChain(0);
      setTimeout(() => {
        setEmotion('idle');
        setSpeechText(null);
      }, 4000);
    } catch (error) {
      console.error('[handleCancelSession] Failed to cancel session', error);
    }
  }, [backendConnected, setSessionState, setCurrentTask, setTimeLeft, setEmotion, setSpeechText, setDistractionChain]);

  const handlePauseSession = useCallback(async () => {
    if (sessionState !== 'running' || sessionTransitionRef.current) return;
    if (!backendConnected) {
      setApiError('Backend not connected');
      return;
    }

    sessionTransitionRef.current = true;
    try {
      await api.updateTimeLeft(timeLeft);
      const result = await api.pauseSession();
      setTimeLeft(result.time_left);
      setSessionState('paused');
    } catch (error) {
      console.error('[handlePauseSession] Failed to pause session', error);
    } finally {
      sessionTransitionRef.current = false;
    }
  }, [sessionState, backendConnected, timeLeft]);

  const handleResumeSession = useCallback(async () => {
    if (sessionState !== 'paused' || sessionTransitionRef.current) return;
    if (!backendConnected) {
      setApiError('Backend not connected');
      return;
    }

    sessionTransitionRef.current = true;
    try {
      const result = await api.resumeSession();
      setTimeLeft(result.time_left);
      setSessionState('running');
    } catch (error) {
      console.error('[handleResumeSession] Failed to resume session', error);
    } finally {
      sessionTransitionRef.current = false;
    }
  }, [sessionState, backendConnected]);

  const handleExtendSession = useCallback(async (minutes: number) => {
    if (
      sessionState !== 'running'
      || sessionTransitionRef.current
      || !Number.isInteger(minutes)
      || minutes < 1
      || minutes > 120
    ) return;
    if (!backendConnected) {
      setApiError('Backend not connected');
      return;
    }

    sessionTransitionRef.current = true;
    try {
      await api.updateTimeLeft(timeLeft);
      const result = await api.extendSession(minutes);
      setTimeLeft(result.time_left);
      timerDeadlineRef.current = Date.now() + result.time_left * 1000;
      extensionPromptedRef.current = false;
      if (extensionSpeechTimerRef.current) {
        clearTimeout(extensionSpeechTimerRef.current);
        extensionSpeechTimerRef.current = null;
      }
      setEmotion('happy');
      setSpeechText(`ADDED ${minutes} MINUTES. LET'S KEEP GOING!`);
      setTimeout(() => {
        setSpeechText(current => current?.startsWith('ADDED ') ? null : current);
      }, 5000);
    } catch (error) {
      console.error('[handleExtendSession] Failed to extend session', error);
      setEmotion('worried');
      setSpeechText('FAILED TO EXTEND THE SESSION.');
    } finally {
      sessionTransitionRef.current = false;
    }
  }, [backendConnected, sessionState, timeLeft]);

  const handleStartSession = useCallback(async (task: Task, durationMinutes: number, context?: BehaviorActionContext) => {
    try {
      if (!backendConnected) {
        console.error(`[handleStartSession] Backend NOT connected - cannot start session!`);
        throw new Error('Backend not connected');
      }

      const session = await api.startSession(task.id, durationMinutes * 60, context);

      setCurrentTask(task);
      setSessionState('running');
      setTimeLeft(session.time_left);
      timerDeadlineRef.current = Date.now() + session.time_left * 1000;
      setDistractionChain(0);
      zeroHandledRef.current = false;

      setEmotion('happy');
      setSpeechText(`SESSION STARTED! LET'S FOCUS FOR ${durationMinutes} MINUTES!`);
      setTimeout(() => {
        setSpeechText(null);
      }, 4000);
    } catch (error) {
      console.error(`[handleStartSession] Failed to start session`, error);
      setEmotion('worried');
      setSpeechText('FAILED TO START SESSION!');
      setTimeout(() => {
        setEmotion('idle');
        setSpeechText(null);
      }, 3000);
    }
  }, [backendConnected, setCurrentTask, setSessionState, setTimeLeft, setDistractionChain, setEmotion, setSpeechText]);

  const handleSimulateDistraction = useCallback(async () => {
    if (sessionState === 'running') {
      if (!backendConnected) {
        console.error(`[handleSimulateDistraction] Backend NOT connected - cannot add distraction!`);
        setApiError('Backend not connected');
        return;
      }

      try {
        const result = await api.addDistraction();
        setDistractionChain(result.distraction_count);
        setTimeLeft(result.time_left);
        timerDeadlineRef.current = Date.now() + result.time_left * 1000;

        setEmotion('angry');
        setSpeechText('HEY! GET BACK TO WORK! (+5 MIN PENALTY)');
        setTimeout(() => {
          if (sessionState === 'running') {
            setEmotion('happy');
            setSpeechText(null);
          }
        }, 5000);
      } catch (error) {
        console.error('[handleSimulateDistraction] Failed to record distraction', error);
      }
    } else {
      setEmotion('idle');
      setSpeechText('NO SESSION TO DISTRACT FROM!');
      setTimeout(() => setSpeechText(null), 3000);
    }
  }, [sessionState, backendConnected, setDistractionChain, setTimeLeft, setEmotion, setSpeechText]);

  useEffect(() => {
    const bridge = getElectronKeyStore();
    if (!bridge?.onPetAction) return;

    return bridge.onPetAction(action => {
      switch (action.type) {
        case 'open-main':
          setActiveTab(action.tab);
          setIsMainWindowOpen(true);
          break;
        case 'send-message':
          if (action.message.trim()) void handleSendMessage(action.message.trim());
          break;
        case 'pause-session':
          void handlePauseSession();
          break;
        case 'resume-session':
          void handleResumeSession();
          break;
        case 'extend-session':
          void handleExtendSession(action.minutes);
          break;
        case 'cancel-session':
          void handleCancelSession();
          break;
      }
    });
  }, [handleCancelSession, handleExtendSession, handlePauseSession, handleResumeSession, handleSendMessage]);

  if (!isReady) {
    return <div style={{ background: '#fff', height: '100vh', width: '100vw' }} />;
  }

  return (
    <div className="relative w-full h-screen overflow-hidden font-sans selection:bg-cyan-400/50 bg-gray-100">
      <AnimatePresence>
        {showSetupModal && (
           <SetupModal onComplete={handleSetupComplete} />
        )}
      </AnimatePresence>

    {petName ? (
       <MainWindow
                embedded
                isOpen={isMainWindowOpen}
                onClose={() => setIsMainWindowOpen(false)}
                onMinimize={() => setIsMainWindowOpen(false)}
                petName={petName}
                setPetName={(n) => {
                  if(n.trim() !== '') {
                    setPetName(n);
                    localStorage.setItem('petName', n);
                  }
                }}
                emotion={emotion}
                setEmotion={setEmotion}
                chatMessages={messages}
                onSendMessage={handleSendMessage}
                onResolveChatAction={handleChatAction}
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                isDesktopMode={isDesktopMode}
                setIsDesktopMode={setIsDesktopMode}
                focusHoursToday={focusHoursToday}
                focusHoursWeek={focusHoursWeek}
                sessionsCompleted={sessionsCompleted}
                onStartSession={handleStartSession}
                 onTasksChanged={loadTasks}
                planRefreshToken={planRefreshToken}
                sessionState={sessionState}
                distractionChain={distractionChain}
                distractionData={distractionData}
                onSimulateDistraction={handleSimulateDistraction}
                autoDistractionEnabled={autoDistractionEnabled}
                onAutoDistractionEnabledChange={setAutoDistractionEnabled}
                aiProvider={aiProvider}
                setAiProvider={(provider) => {
                  setAiProvider(provider);
                  localStorage.setItem('ai_provider', provider);
                }}
                configuredProviders={configuredProviders}
                onSaveApiKey={saveApiKey}
                 onEvaluateProactiveNow={triggerProactiveNow}
                apiError={apiError}
                backendConnected={backendConnected}
               />
    ) : null}
    </div>
  );
}
