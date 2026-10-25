'use client';

import { motion, Variants, AnimatePresence } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { Send, X } from 'lucide-react';
import { usePetBehavior } from '@/hooks/use-pet-behavior';
import { PetEmotion, resolvePetVisualState } from '@/lib/pet-behavior';
import { shouldOfferSessionExtension } from '@/lib/session-timer';
import { wrapSpeechBubbleText } from '@/lib/speech-bubble';
import type { PetProactiveAnimation } from '@/lib/desktop-ipc';

export type Emotion = PetEmotion;
export type SessionState = 'idle' | 'running' | 'paused' | 'break';

const CURSOR_NEAR_TIMEOUT_MS = 1_500;

const SoundFX = {
  playEmotionChange: () => {
    try {
      const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gainNode = ctx.createGain();

      osc1.type = 'sawtooth';
      osc2.type = 'square';

      osc1.frequency.setValueAtTime(100, ctx.currentTime);
      osc1.frequency.exponentialRampToValueAtTime(300, ctx.currentTime + 0.1);
      osc1.frequency.exponentialRampToValueAtTime(150, ctx.currentTime + 0.25);

      osc2.frequency.setValueAtTime(150, ctx.currentTime);
      osc2.frequency.exponentialRampToValueAtTime(450, ctx.currentTime + 0.1);
      osc2.frequency.exponentialRampToValueAtTime(200, ctx.currentTime + 0.25);

      gainNode.gain.setValueAtTime(0, ctx.currentTime);
      gainNode.gain.linearRampToValueAtTime(0.03, ctx.currentTime + 0.03);
      gainNode.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.25);

      osc1.connect(gainNode);
      osc2.connect(gainNode);
      gainNode.connect(ctx.destination);

      osc1.start();
      osc2.start();
      osc1.stop(ctx.currentTime + 0.25);
      osc2.stop(ctx.currentTime + 0.25);
    } catch(e) {}
  }
};

interface FloatingPetProps {
  nativeWindow?: boolean;
  nativeDragging?: boolean;
  nativeChasing?: boolean;
  nativeBumping?: boolean;
  emotion: Emotion;
  constraintsRef: React.RefObject<HTMLDivElement | null>;
  isSpeaking?: boolean;
  speechText?: string | null;
  proactiveAnimation?: PetProactiveAnimation;
  isQuickChatOpen?: boolean;
  onQuickChatClose?: () => void;
  onSendMessage?: (msg: string) => void;
  onChatClick?: () => void;
  onTasksClick?: () => void;
  onHoverChange?: (hovered: boolean) => void;
  onPoke?: () => void;
  sessionState?: SessionState;
  timeLeft?: number;
  currentTaskName?: string;
  onPauseSession?: () => void;
  onResumeSession?: () => void;
  onExtendSession?: (minutes: number) => void;
  onCancelSession?: () => void;
}

export default function FloatingPet({
  nativeWindow = false,
  nativeDragging = false,
  nativeChasing = false,
  nativeBumping = false,
  emotion,
  constraintsRef,
  isSpeaking = false,
  speechText,
  proactiveAnimation = null,
  isQuickChatOpen,
  onQuickChatClose,
  onSendMessage,
  onChatClick,
  onTasksClick,
  onHoverChange,
  onPoke,
  sessionState = 'idle',
  timeLeft = 0,
  currentTaskName,
  onPauseSession,
  onResumeSession,
  onExtendSession,
  onCancelSession
}: FloatingPetProps) {
  const petRef = useRef<HTMLDivElement>(null);
  const pettingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cursorNearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pokeReactionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isBlinking, setIsBlinking] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isBeingPetted, setIsBeingPetted] = useState(false);
  const [isPokeAnnoyed, setIsPokeAnnoyed] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [extensionMinutes, setExtensionMinutes] = useState('10');
  const [cursorNear, setCursorNear] = useState(false);
  const [cursorPoint, setCursorPoint] = useState({ x: 0, y: 0 });
  const behavior = usePetBehavior({
    explicitEmotion: emotion,
    sessionState,
    cursorNear,
  });
  const notifyPetInteraction = behavior.notifyInteraction;
  const activelyDragging = nativeWindow ? nativeDragging : isDragging;
  const visualState = resolvePetVisualState({
    activity: behavior.activity,
    emotion: behavior.emotion,
    dragging: activelyDragging,
    petted: isBeingPetted,
    reducedMotion: behavior.reducedMotion,
  });
  const displayEmotion: PetEmotion = nativeChasing || nativeBumping || isPokeAnnoyed
    ? 'angry'
    : visualState.emotion;

  const handleHeadPet = () => {
    setIsBeingPetted(true);
    notifyPetInteraction('hover');
    if (pettingTimerRef.current) clearTimeout(pettingTimerRef.current);
    pettingTimerRef.current = setTimeout(() => {
      pettingTimerRef.current = null;
      setIsBeingPetted(false);
    }, 1_600);
  };

  const handlePoke = () => {
    onPoke?.();
    setIsPokeAnnoyed(true);
    if (pokeReactionTimerRef.current) clearTimeout(pokeReactionTimerRef.current);
    pokeReactionTimerRef.current = setTimeout(() => {
      pokeReactionTimerRef.current = null;
      setIsPokeAnnoyed(false);
    }, 1_200);
  };

  useEffect(() => {
    if (nativeDragging) notifyPetInteraction('drag');
  }, [nativeDragging, notifyPetInteraction]);

  useEffect(() => () => {
    if (pettingTimerRef.current) clearTimeout(pettingTimerRef.current);
    if (cursorNearTimerRef.current) clearTimeout(cursorNearTimerRef.current);
    if (pokeReactionTimerRef.current) clearTimeout(pokeReactionTimerRef.current);
  }, []);

  useEffect(() => {
    if (!nativeBumping) return;
    if (pokeReactionTimerRef.current) {
      clearTimeout(pokeReactionTimerRef.current);
      pokeReactionTimerRef.current = null;
    }
    setIsPokeAnnoyed(false);
  }, [nativeBumping]);

  useEffect(() => {
    if (behavior.reducedMotion) return;

    const blinkInterval = setInterval(() => {
      if (displayEmotion !== 'happy' && displayEmotion !== 'excited' && displayEmotion !== 'sad' && displayEmotion !== 'sleepy') {
        if (Math.random() > 0.4) {
          setIsBlinking(true);
          setTimeout(() => {
            setIsBlinking(false);
            if (Math.random() > 0.7) {
              setTimeout(() => {
                setIsBlinking(true);
                setTimeout(() => setIsBlinking(false), 100);
              }, 150);
            }
          }, 100);
        }
      }
    }, 4000);
    return () => clearInterval(blinkInterval);
  }, [behavior.reducedMotion, displayEmotion]);

  useEffect(() => {
    if (emotion !== 'idle') SoundFX.playEmotionChange();
  }, [emotion]);

  useEffect(() => {
    const clearCursorNearTimer = () => {
      if (!cursorNearTimerRef.current) return;
      clearTimeout(cursorNearTimerRef.current);
      cursorNearTimerRef.current = null;
    };

    const markCursorNear = () => {
      setCursorNear(true);
      clearCursorNearTimer();
      cursorNearTimerRef.current = setTimeout(() => {
        cursorNearTimerRef.current = null;
        setCursorNear(false);
      }, CURSOR_NEAR_TIMEOUT_MS);
    };

    const markCursorAway = () => {
      clearCursorNearTimer();
      setCursorNear(false);
    };

    const handlePointerMove = (event: PointerEvent) => {
      const bounds = petRef.current?.getBoundingClientRect();
      if (!bounds) return;
      const centerX = bounds.left + (bounds.width / 2);
      const centerY = bounds.top + (bounds.height / 2);
      const deltaX = event.clientX - centerX;
      const deltaY = event.clientY - centerY;
      const distance = Math.hypot(deltaX, deltaY);
      if (distance <= 240) {
        markCursorNear();
      } else {
        markCursorAway();
      }
      setCursorPoint({
        x: Math.max(-1, Math.min(1, deltaX / 240)),
        y: Math.max(-1, Math.min(1, deltaY / 240)),
      });
    };
    const handlePointerOut = (event: PointerEvent) => {
      if (event.relatedTarget) return;
      markCursorAway();
    };
    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    window.addEventListener('pointerout', handlePointerOut);
    window.addEventListener('blur', markCursorAway);
    return () => {
      clearCursorNearTimer();
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerout', handlePointerOut);
      window.removeEventListener('blur', markCursorAway);
    };
  }, []);

  useEffect(() => {
    let soundInterval: NodeJS.Timeout;
    if (isSpeaking) {
      soundInterval = setInterval(() => {
        try {
          const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
          if (!AudioContext) return;
          const ctx = new AudioContext();
          const osc1 = ctx.createOscillator();
          const osc2 = ctx.createOscillator();
          const gainNode = ctx.createGain();

          osc1.type = 'square';
          osc2.type = 'sawtooth';

          const freqs = [440, 554, 659, 880, 1108, 1318, 1760];
          const baseFreq = freqs[Math.floor(Math.random() * freqs.length)];

          osc1.frequency.setValueAtTime(baseFreq, ctx.currentTime);
          osc1.frequency.exponentialRampToValueAtTime(baseFreq * 0.5, ctx.currentTime + 0.06);

          osc2.frequency.setValueAtTime(baseFreq * 1.5, ctx.currentTime);
          osc2.frequency.exponentialRampToValueAtTime(baseFreq * 0.75, ctx.currentTime + 0.06);

          gainNode.gain.setValueAtTime(0.015, ctx.currentTime);
          gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.06);

          osc1.connect(gainNode);
          osc2.connect(gainNode);
          gainNode.connect(ctx.destination);

          osc1.start();
          osc2.start();
          osc1.stop(ctx.currentTime + 0.06);
          osc2.stop(ctx.currentTime + 0.06);
        } catch(e) {}
      }, 70);
    }
    return () => {
      if (soundInterval) clearInterval(soundInterval);
    };
  }, [isSpeaking]);

  const getEyeStyle = (side: 'left' | 'right', currentEmotion: Emotion, blinking: boolean) => {
    const base = { backgroundColor: "#22d3ee", borderWidth: 0, borderColor: "transparent", borderStyle: "solid" as any };
    if (blinking) {
      return { ...base, height: 8, width: 64, borderRadius: "8px", rotate: 0, y: 0, scale: 1 };
    }

    switch(currentEmotion) {
      case 'idle':
        return { ...base, height: 48, width: 48, borderRadius: "12px", rotate: 0, y: 0 };
      case 'happy':
        return { ...base, height: 40, width: 48, borderRadius: "24px 24px 8px 8px", rotate: side === 'left' ? -12 : 12, y: -8 };
      case 'excited':
        return { ...base, height: 46, width: 52, borderRadius: "24px 24px 8px 8px", rotate: side === 'left' ? -16 : 16, y: -10 };
      case 'worried':
        return { ...base, height: 46, width: 46, borderRadius: "18px 18px 8px 8px", rotate: side === 'left' ? 12 : -12, y: -4 };
      case 'sad':
        return { ...base, height: 36, width: 46, borderRadius: "18px 18px 8px 8px", rotate: side === 'left' ? 16 : -16, y: 10 };
      case 'angry':
        return { ...base, height: 36, width: 48, borderRadius: "8px 8px 18px 18px", rotate: side === 'left' ? 24 : -24, y: -6, scale: 1.05 };
      case 'thinking':
        return { ...base, height: side === 'left' ? 24 : 48, width: 48, borderRadius: "12px", rotate: side === 'left' ? 12 : 0, y: side === 'left' ? -10 : 0 };
      case 'sleepy':
        return { ...base, height: 8, width: 48, borderRadius: "12px", rotate: 0, y: 6 };
      case 'hurt':
        if (side === 'left') {
          return { ...base, backgroundColor: "transparent", borderTopWidth: 8, borderRightWidth: 8, borderColor: "#22d3ee", height: 32, width: 32, borderRadius: "6px", rotate: 45, y: -6 };
        } else {
          return { ...base, backgroundColor: "transparent", borderTopWidth: 8, borderLeftWidth: 8, borderColor: "#22d3ee", height: 32, width: 32, borderRadius: "6px", rotate: -45, y: -6 };
        }
      default:
        return { ...base, height: 48, width: 48, borderRadius: "12px", rotate: 0, y: 0 };
    }
  };

  const faceVariants: Variants = {
    idle: { y: [0, -2, 0], transition: { repeat: Infinity, duration: 3, ease: "easeInOut" } },
    happy: { y: [0, -12, 0], transition: { repeat: Infinity, duration: 0.8, ease: "easeOut" } },
    excited: { y: [0, -20, 0], transition: { repeat: Infinity, duration: 0.5, ease: "easeOut" } },
    worried: { x: [-2, 2, -2, 2, 0], transition: { repeat: Infinity, duration: 4, ease: "easeInOut" } },
    sad: { y: [0, 2, 0], transition: { repeat: Infinity, duration: 4, ease: "easeInOut" } },
    angry: { x: [-1, 1, -1, 1, 0], transition: { repeat: Infinity, duration: 0.4 } },
    hurt: { x: [-2, 2, -2, 2, 0], transition: { repeat: Infinity, duration: 0.2 } },
    thinking: { y: [0, -3, 0], transition: { repeat: Infinity, duration: 2.5, ease: "easeInOut" } },
    sleepy: { y: [0, 4, 0], transition: { repeat: Infinity, duration: 5, ease: "easeInOut", delay: 0.5 } },
    'glance-left': { x: [0, -5, -5, 0], transition: { duration: 1.2, ease: "easeInOut" } },
    'glance-right': { x: [0, 5, 5, 0], transition: { duration: 1.2, ease: "easeInOut" } },
    'tilt-head': { rotate: [0, -7, -7, 0], transition: { duration: 1.7, ease: "easeInOut" } },
    'idle-stretch': { scaleY: [1, 1.08, 1.08, 1], y: [0, -7, -7, 0], transition: { duration: 1.8, ease: "easeInOut" } },
    shake: { x: [0, -4, 4, -3, 3, 0], rotate: [0, -2, 2, -1, 1, 0], transition: { duration: 1, ease: "easeInOut" } },
    'eye-roll': { y: [0, -2, 0], transition: { duration: 1.4, ease: "easeInOut" } },
    sigh: { scaleY: [1, 0.97, 1], y: [0, 3, 0], transition: { duration: 1.8, ease: "easeInOut" } },
    'follow-cursor': { rotate: cursorPoint.x * 3, transition: { duration: 0.18 } },
    'chase-cursor': { y: [0, -4, 0], rotate: [0, -1, 1, 0], transition: { repeat: Infinity, duration: 0.65, ease: "easeInOut" } },
    'cursor-bump': { x: [0, 13, -5, 0], y: [0, 10, -4, 0], scale: [1, 1.04, 0.98, 1], transition: { duration: 0.6, ease: "easeOut" } },
    yawn: { scaleY: [1, 0.97, 1], y: [0, 3, 0], transition: { duration: 1.8, ease: "easeInOut" } },
    doze: { rotate: [0, -3, -3, 0], y: [0, 4, 5, 4], transition: { repeat: Infinity, duration: 4, ease: "easeInOut" } },
    wake: { y: [4, -10, 0], scale: [0.98, 1.04, 1], transition: { duration: 0.8, ease: "easeOut" } },
    'focus-still': { x: 0, y: 0, rotate: 0, transition: { duration: 0.25 } },
    'break-stretch': { scaleY: [1, 1.06, 1], y: [0, -5, 0], transition: { duration: 1.5, ease: "easeInOut" } },
    'drink-water': { rotate: [0, 3, 3, 0], y: [0, 2, 2, 0], transition: { repeat: Infinity, duration: 2.4, ease: "easeInOut" } },
    reduced: { x: 0, y: 0, rotate: 0, scale: 1, transition: { duration: 0 } },
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const animationKey = behavior.reducedMotion
    ? 'reduced'
    : proactiveAnimation === 'drink-water'
      ? 'drink-water'
    : nativeBumping
      ? 'cursor-bump'
      : nativeChasing
        ? 'chase-cursor'
        : visualState.animation;
  const gazeX = behavior.activity === 'glance-left'
    ? -10
    : behavior.activity === 'glance-right'
      ? 10
      : behavior.activity === 'follow-cursor'
        ? cursorPoint.x * 11
        : 0;
  const gazeY = behavior.activity === 'follow-cursor' ? cursorPoint.y * 7 : 0;
  const activityGazeY = behavior.activity === 'eye-roll' ? -12 : gazeY;

  return (
    <motion.div
      ref={petRef}
      data-pomopet-window-region
      data-pet-activity={behavior.activity}
      drag={!nativeWindow}
      dragConstraints={nativeWindow ? undefined : constraintsRef}
      dragElastic={0.1}
      dragMomentum={false}
      onDragStart={() => {
        setIsDragging(true);
        notifyPetInteraction('drag');
      }}
      onDragEnd={() => {
        setIsDragging(false);
      }}
      whileDrag={{ scale: 1.05, cursor: "grabbing" }}
      className={`absolute z-40 flex flex-col items-center ${nativeWindow ? 'bottom-24 left-4' : 'bottom-4 right-4'}`}
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1, transition: { type: "spring", bounce: 0.5 } }}
      onHoverStart={() => {
        setIsHovered(true);
        notifyPetInteraction('hover');
        onHoverChange?.(true);
      }}
      onHoverEnd={() => {
        setIsHovered(false);
        if (cursorNearTimerRef.current) {
          clearTimeout(cursorNearTimerRef.current);
          cursorNearTimerRef.current = null;
        }
        setCursorNear(false);
        onHoverChange?.(false);
      }}
      onPointerDown={() => notifyPetInteraction('click')}
    >
      {/* Session Action Menu (Shows when running/paused) */}
      <AnimatePresence>
        {sessionState !== 'idle' && (
          <motion.div
            data-pomopet-window-region
            initial={{ opacity: 0, y: 10, scale: 0.9 }}
            animate={{ opacity: 1, y: -25, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="absolute -top-16 flex gap-2 bg-white border-[3px] border-black shadow-[4px_4px_0_#000] rounded-xl px-2 py-1 pointer-events-auto z-10"
          >
            {sessionState === 'running' || sessionState === 'break' ? (
               <button
                onClick={onPauseSession}
                className="text-black hover:bg-yellow-300 px-3 py-1 rounded text-xs font-mono font-bold uppercase transition-colors"
                title="Pause"
              >
                Pause
              </button>
            ) : (
               <button
                onClick={onResumeSession}
                className="text-black hover:bg-green-400 px-3 py-1 rounded text-xs font-mono font-bold uppercase transition-colors"
                title="Resume"
              >
                Resume
              </button>
            )}
            {shouldOfferSessionExtension(sessionState, timeLeft) && (
              <div className="flex items-center gap-1 border-l-2 border-black pl-2">
                <input
                  type="number"
                  min={1}
                  max={120}
                  value={extensionMinutes}
                  onChange={event => setExtensionMinutes(event.target.value)}
                  onPointerDown={event => event.stopPropagation()}
                  aria-label="Extension duration in minutes"
                  className="w-12 rounded border-2 border-black bg-white px-1 py-0.5 text-center text-xs font-mono font-black text-black outline-none focus:bg-cyan-50"
                />
                <button
                  type="button"
                  onClick={() => {
                    const minutes = Number(extensionMinutes);
                    if (Number.isInteger(minutes) && minutes >= 1 && minutes <= 120) {
                      onExtendSession?.(minutes);
                    }
                  }}
                  className="rounded bg-cyan-300 px-2 py-1 text-xs font-mono font-black uppercase text-black transition-colors hover:bg-cyan-400 disabled:opacity-40"
                  disabled={
                    !Number.isInteger(Number(extensionMinutes))
                    || Number(extensionMinutes) < 1
                    || Number(extensionMinutes) > 120
                  }
                  title="Extend the focus session"
                >
                  Extend
                </button>
              </div>
            )}
            <button
              onClick={onCancelSession}
              className="text-black hover:bg-red-400 hover:text-white px-3 py-1 rounded text-xs font-mono font-bold uppercase transition-colors"
              title="Cancel"
            >
              Cancel
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Hover Action Menu */}
      <motion.div
        data-pomopet-window-region
        initial={{ opacity: 0, y: 10, scale: 0.9 }}
        animate={{ opacity: isHovered && !isQuickChatOpen && sessionState === 'idle' ? 1 : 0, y: isHovered && !isQuickChatOpen && sessionState === 'idle' ? -20 : 10, scale: isHovered && !isQuickChatOpen && sessionState === 'idle' ? 1 : 0.9 }}
        className="absolute -top-12 flex gap-2 bg-white border-[3px] border-black shadow-[4px_4px_0_#000] rounded-xl px-2 py-1 pointer-events-auto z-10"
      >
        <AnimatePresence>
          {proactiveAnimation === 'drink-water' && (
            <motion.div
              key="drink-water"
              role="img"
              aria-label="Pomo is drinking water"
              className="pointer-events-none absolute -right-9 bottom-8 z-40 h-20 w-16"
              initial={{ opacity: 0, y: 18, rotate: 0 }}
              animate={behavior.reducedMotion
                ? { opacity: 1, y: -18, rotate: -10 }
                : { opacity: 1, y: [18, -22, -22, 18], rotate: [0, -12, -12, 0] }}
              exit={{ opacity: 0, y: 18, rotate: 0 }}
              transition={behavior.reducedMotion
                ? { duration: 0 }
                : { repeat: Infinity, duration: 2.4, times: [0, 0.3, 0.72, 1], ease: 'easeInOut' }}
            >
              <div className="absolute left-1 top-0 h-12 w-1 origin-bottom rotate-[-12deg] border-l-[3px] border-black bg-cyan-300" />
              <div className="absolute bottom-0 left-0 h-12 w-11 overflow-hidden rounded-b-lg border-[3px] border-black bg-white shadow-[3px_3px_0_#000]">
                <motion.div
                  className="absolute inset-x-0 bottom-0 h-8 bg-cyan-300"
                  animate={behavior.reducedMotion ? undefined : { y: [0, 3, 0], rotate: [0, 3, 0] }}
                  transition={{ repeat: Infinity, duration: 0.8 }}
                />
                <div className="absolute right-1 top-1 h-6 w-1 bg-white/70" />
              </div>
              <motion.span
                aria-hidden="true"
                className="absolute right-0 top-5 font-mono text-lg font-black text-cyan-400"
                animate={behavior.reducedMotion ? undefined : { opacity: [0, 1, 0], y: [-4, 5, 10] }}
                transition={{ repeat: Infinity, duration: 1.1 }}
              >
                ◆
              </motion.span>
            </motion.div>
          )}
        </AnimatePresence>
        <button
          onClick={onChatClick}
          className="text-black hover:bg-cyan-300 px-3 py-1 rounded text-xs font-mono font-bold uppercase transition-colors"
        >
          Chat
        </button>
        <button
          onClick={onTasksClick}
          className="text-black hover:bg-cyan-300 px-3 py-1 rounded text-xs font-mono font-bold uppercase transition-colors"
        >
          Tasks
        </button>
      </motion.div>

      {/* Speech Bubble (Manga Style) */}
      <AnimatePresence>
        {(speechText || emotion === 'thinking') && (
          <motion.div
            data-pomopet-window-region
            initial={{ opacity: 0, scale: 0.8, rotate: -5, originX: 0, originY: 1 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="absolute -top-12 left-full ml-4 w-max min-w-[240px] max-w-[312px] bg-white border-[4px] border-black shadow-[6px_6px_0_#000] rounded-2xl px-4 py-3 z-40 pointer-events-none"
          >
            {/* Triangle tip pointing left */}
            <div className="absolute top-1/2 -left-4 -translate-y-1/2 w-0 h-0 border-t-[10px] border-t-transparent border-b-[10px] border-b-transparent border-r-[12px] border-r-black" />
            <div className="absolute top-1/2 -left-2.5 -translate-y-1/2 w-0 h-0 border-t-[8px] border-t-transparent border-b-[8px] border-b-transparent border-r-[10px] border-r-white z-10" />

            <div className="text-black font-mono font-bold text-sm tracking-normal leading-snug whitespace-pre-line break-words">
              {emotion === 'thinking' ? (
                <div className="flex gap-2 items-center justify-center py-2 h-6">
                  <motion.div className="w-2.5 h-2.5 bg-black" animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0 }} />
                  <motion.div className="w-2.5 h-2.5 bg-black" animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0.15 }} />
                  <motion.div className="w-2.5 h-2.5 bg-black" animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0.3 }} />
                </div>
              ) : (
                speechText ? wrapSpeechBubbleText(speechText) : null
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Quick Chat Input */}
      <AnimatePresence>
        {isQuickChatOpen && (
          <motion.div
             data-pomopet-window-region
             initial={{ opacity: 0, y: -10 }}
             animate={{ opacity: 1, y: 0 }}
             exit={{ opacity: 0, y: -10 }}
             className={`absolute -bottom-20 w-72 bg-white border-[4px] border-black shadow-[6px_6px_0_#000] p-1.5 rounded-xl z-50 pointer-events-auto ${
               nativeWindow ? 'left-0' : 'left-1/2 -translate-x-1/2'
             }`}
          >
             <form
               onSubmit={(e) => {
                 e.preventDefault();
                 if (chatInput.trim() && onSendMessage) {
                   onSendMessage(chatInput.trim());
                   setChatInput('');
                 }
               }}
               className="flex gap-2"
             >
               <input
                  autoFocus
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="TYPE MESSAGE..."
                  className="flex-1 min-w-0 bg-transparent text-black font-mono font-bold text-[13px] outline-none px-2 uppercase placeholder:text-gray-400"
               />
               <button
                 type="submit"
                 disabled={!chatInput.trim()}
                 className="bg-cyan-400 border-[3px] border-black text-black px-2.5 py-1.5 flex items-center justify-center shrink-0 active:translate-y-[2px] active:translate-x-[2px] disabled:opacity-50 transition-all hover:bg-cyan-300"
               >
                 <Send className="w-4 h-4" strokeWidth={3} />
               </button>
               <button
                 type="button"
                 onClick={onQuickChatClose}
                 className="bg-gray-200 border-[3px] border-black text-black px-2.5 py-1.5 flex items-center justify-center shrink-0 active:translate-y-[2px] active:translate-x-[2px] transition-all hover:bg-red-400 hover:text-white"
               >
                 <X className="w-4 h-4" strokeWidth={3} />
               </button>
             </form>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main Body/Face (Retro PC/Tamagotchi style) */}
      <motion.div
        className="w-40 h-48 bg-white rounded-2xl shadow-[6px_6px_0_#000] border-[4px] border-black flex flex-col items-center p-3 cursor-grab overflow-visible relative"
        style={nativeWindow ? ({ WebkitAppRegion: 'drag' } as React.CSSProperties) : undefined}
        variants={faceVariants}
        animate={animationKey}
        onPointerDown={event => {
          if (event.button === 0) handlePoke();
        }}
      >
        <button
          type="button"
          aria-label="Pet Pomo on the head"
          className="absolute left-5 right-5 top-0 z-30 h-8 cursor-pointer bg-transparent"
          style={nativeWindow ? ({ WebkitAppRegion: 'no-drag' } as React.CSSProperties) : undefined}
          onPointerEnter={handleHeadPet}
          onPointerMove={event => {
            if (event.buttons === 1) handleHeadPet();
          }}
          onClick={handleHeadPet}
        />
        {/* Screen */}
        <div className="w-full flex-1 bg-black rounded-lg border-[4px] border-black overflow-hidden relative shadow-[inset_0_4px_10px_rgba(0,0,0,0.8)]">
           {/* Scanlines / Pixel Grid */}
           <div className="absolute inset-0 bg-[linear-gradient(rgba(34,211,238,0.1)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.1)_1px,transparent_1px)] bg-[size:4px_4px] pointer-events-none z-10" />

           {/* Timer Overlay */}
           {sessionState !== 'idle' && (
              <div className="absolute top-1 left-1/2 -translate-x-1/2 flex flex-col items-center z-20">
                 <span className={`font-mono text-sm font-black ${sessionState === 'paused' ? 'text-yellow-400 animate-pulse' : 'text-cyan-400'} drop-shadow-[0_0_8px_rgba(34,211,238,0.8)]`}>
                   {formatTime(timeLeft)}
                 </span>
                 {currentTaskName && (
                    <span className="font-mono text-[8px] text-cyan-200 mt-0.5 truncate max-w-[100px] opacity-70">
                      {currentTaskName}
                    </span>
                 )}
              </div>
           )}

           <div className="relative flex items-center justify-center w-full h-full z-0 mt-3">
               {/* Left Eye */}
               <motion.div
                 animate={{
                   ...getEyeStyle('left', displayEmotion, isBlinking),
                   x: gazeX,
                   y: (getEyeStyle('left', displayEmotion, isBlinking).y ?? 0) + activityGazeY,
                 }}
                 transition={{ type: "spring", stiffness: 400, damping: 25 }}
                 className="bg-cyan-400 absolute ml-[-50px] mt-[-20px] shadow-[0_0_10px_rgba(34,211,238,0.5)]"
               />

               {/* Right Eye */}
               <motion.div
                 animate={{
                   ...getEyeStyle('right', displayEmotion, isBlinking),
                   x: gazeX,
                   y: (getEyeStyle('right', displayEmotion, isBlinking).y ?? 0) + activityGazeY,
                 }}
                 transition={{ type: "spring", stiffness: 400, damping: 25 }}
                 className="bg-cyan-400 absolute ml-[50px] mt-[-20px] shadow-[0_0_10px_rgba(34,211,238,0.5)]"
               />

               {behavior.activity === 'yawn' && (
                 <motion.div
                   aria-hidden="true"
                   className="absolute mt-14 h-7 w-6 rounded-full border-[3px] border-cyan-400"
                   animate={behavior.reducedMotion ? undefined : { scaleY: [0.6, 1.2, 0.6] }}
                   transition={{ duration: 1.6, ease: 'easeInOut' }}
                 />
               )}

               {behavior.activity === 'doze' && (
                 <motion.span
                   aria-label="Pomo is dozing"
                   className="absolute -right-1 -top-1 font-mono text-lg font-black text-cyan-300"
                   animate={behavior.reducedMotion ? undefined : { opacity: [0.35, 1, 0.35], y: [3, -3, 3] }}
                   transition={{ repeat: Infinity, duration: 2.2 }}
                 >
                   Z
                 </motion.span>
               )}

               {(nativeChasing || nativeBumping || isPokeAnnoyed) && (
                 <>
                   <motion.div
                     aria-hidden="true"
                     className="absolute ml-[-76px] mt-10 h-3 w-5 rounded-full bg-pink-400/80"
                     animate={{ opacity: [0.55, 1, 0.55] }}
                     transition={{ repeat: Infinity, duration: 0.7 }}
                   />
                   <motion.div
                     aria-hidden="true"
                     className="absolute ml-[76px] mt-10 h-3 w-5 rounded-full bg-pink-400/80"
                     animate={{ opacity: [0.55, 1, 0.55] }}
                     transition={{ repeat: Infinity, duration: 0.7 }}
                   />
                   <motion.span
                     aria-label="Pomo is playfully angry"
                     className="absolute -right-1 top-0 font-mono text-xl font-black text-pink-400"
                     animate={{ rotate: [-8, 8, -8], scale: [1, 1.15, 1] }}
                     transition={{ repeat: Infinity, duration: 0.45 }}
                   >
                     !
                   </motion.span>
                 </>
               )}
           </div>
        </div>

        {/* Physical Details (Speaker / Buttons) */}
        <div className="w-full flex justify-between items-end pt-3 pb-1 px-1">
            {/* Speaker grills */}
            <div className="flex flex-col gap-1 items-start">
                <motion.div animate={isSpeaking ? { scaleX: [1, 1.4, 0.8, 1.2, 1], transition: { repeat: Infinity, duration: 0.3 } } : { scaleX: 1 }} className="w-6 h-1 bg-black rounded-full origin-left" />
                <motion.div animate={isSpeaking ? { scaleX: [1, 0.5, 1.3, 0.7, 1], transition: { repeat: Infinity, duration: 0.4 } } : { scaleX: 1 }} className="w-4 h-1 bg-black rounded-full origin-left" />
                <motion.div animate={isSpeaking ? { scaleX: [1, 1.6, 0.9, 1.3, 1], transition: { repeat: Infinity, duration: 0.35 } } : { scaleX: 1 }} className="w-5 h-1 bg-black rounded-full origin-left" />
            </div>
            {/* LED */}
            <div className={`w-2.5 h-2.5 bg-cyan-400 border-[2px] border-black rounded-full ${isSpeaking ? 'animate-pulse' : ''}`} />
        </div>
      </motion.div>
    </motion.div>
  );
}
