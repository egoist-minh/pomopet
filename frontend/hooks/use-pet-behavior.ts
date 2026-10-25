'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'motion/react';
import {
  advancePetBehavior,
  createPetBehaviorState,
  emotionForBehavior,
  PET_TEMPERAMENT_STORAGE_KEY,
  PetBehaviorInput,
  PetEmotion,
  PetInteraction,
  PetSessionState,
  startPetBehaviorScheduler,
} from '@/lib/pet-behavior';

interface UsePetBehaviorOptions {
  explicitEmotion: PetEmotion;
  sessionState: PetSessionState;
  cursorNear: boolean;
}

function getOrCreateTemperamentSeed(): string {
  if (typeof window === 'undefined') return 'pomopet-server-render';
  const existing = window.localStorage.getItem(PET_TEMPERAMENT_STORAGE_KEY);
  if (existing) return existing;

  const seed = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  window.localStorage.setItem(PET_TEMPERAMENT_STORAGE_KEY, seed);
  return seed;
}

export function usePetBehavior({
  explicitEmotion,
  sessionState,
  cursorNear,
}: UsePetBehaviorOptions) {
  const reducedMotion = useReducedMotion() ?? false;
  const contextRef = useRef({ explicitEmotion, sessionState, cursorNear, reducedMotion });
  contextRef.current = { explicitEmotion, sessionState, cursorNear, reducedMotion };

  const [behavior, setBehavior] = useState(() => (
    createPetBehaviorState(getOrCreateTemperamentSeed())
  ));

  const update = useCallback((interaction?: PetInteraction) => {
    setBehavior(current => {
      const context = contextRef.current;
      const input: PetBehaviorInput = {
        ...context,
        now: Date.now(),
        interaction,
        hour: new Date().getHours(),
      };
      return advancePetBehavior(current, input);
    });
  }, []);

  useEffect(() => startPetBehaviorScheduler(() => update()), [update]);

  useEffect(() => {
    update(cursorNear ? 'cursor' : undefined);
  }, [cursorNear, explicitEmotion, reducedMotion, sessionState, update]);

  useEffect(() => {
    const handleReturn = () => update('return');
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') handleReturn();
    };
    window.addEventListener('focus', handleReturn);
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      window.removeEventListener('focus', handleReturn);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [update]);

  return {
    activity: behavior.activity,
    emotion: emotionForBehavior(behavior, explicitEmotion),
    needs: behavior.needs,
    temperament: behavior.temperament,
    reducedMotion,
    notifyInteraction: update,
  };
}
