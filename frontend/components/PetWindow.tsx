'use client';

import { useEffect, useRef, useState } from 'react';
import FloatingPet from './FloatingPet';
import type { PetWindowAction, PetWindowState } from '@/lib/desktop-ipc';
import { useWindowRegions, type WindowRegionBridge } from '@/hooks/use-window-regions';

interface PetBridge extends WindowRegionBridge {
  getPetState?: () => Promise<PetWindowState | null>;
  onPetState?: (callback: (state: PetWindowState) => void) => () => void;
  onPetDragState?: (callback: (isDragging: boolean) => void) => () => void;
  setPetChaseSuspended?: (suspended: boolean, keepWindowVisible?: boolean) => void;
  onPetChaseState?: (callback: (isChasing: boolean) => void) => () => void;
  onPetChaseBump?: (callback: () => void) => () => void;
  pokePet?: () => void;
  sendPetAction?: (action: PetWindowAction) => void;
}

function getPetBridge(): PetBridge | undefined {
  if (typeof window === 'undefined') return undefined;
  return (window as Window & { electron?: PetBridge }).electron;
}

export default function PetWindow() {
  const constraintsRef = useRef<HTMLDivElement>(null);
  const bumpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [state, setState] = useState<PetWindowState | null>(null);
  const [isQuickChatOpen, setIsQuickChatOpen] = useState(false);
  const [isNativeDragging, setIsNativeDragging] = useState(false);
  const [isPetHovered, setIsPetHovered] = useState(false);
  const [isNativeChasing, setIsNativeChasing] = useState(false);
  const [isNativeBumping, setIsNativeBumping] = useState(false);
  const bridge = getPetBridge();

  useWindowRegions(bridge, true);

  useEffect(() => {
    if (!bridge) return;
    void bridge.getPetState?.().then(snapshot => {
      if (snapshot) setState(snapshot);
    });
    return bridge.onPetState?.(setState);
  }, [bridge]);

  useEffect(() => bridge?.onPetDragState?.(setIsNativeDragging), [bridge]);
  useEffect(() => bridge?.onPetChaseState?.(setIsNativeChasing), [bridge]);

  useEffect(() => bridge?.onPetChaseBump?.(() => {
    setIsNativeBumping(true);
    if (bumpTimerRef.current) clearTimeout(bumpTimerRef.current);
    bumpTimerRef.current = setTimeout(() => {
      bumpTimerRef.current = null;
      setIsNativeBumping(false);
    }, 650);
  }), [bridge]);

  useEffect(() => () => {
    if (bumpTimerRef.current) clearTimeout(bumpTimerRef.current);
  }, []);

  useEffect(() => {
    bridge?.setPetChaseSuspended?.(isQuickChatOpen || isPetHovered, isQuickChatOpen);
    return () => bridge?.setPetChaseSuspended?.(false);
  }, [bridge, isPetHovered, isQuickChatOpen]);

  const sendAction = (action: PetWindowAction) => bridge?.sendPetAction?.(action);

  return (
    <div ref={constraintsRef} className="relative h-screen w-full overflow-hidden bg-transparent">
      {state?.petName ? (
        <FloatingPet
          nativeWindow
          nativeDragging={isNativeDragging}
          nativeChasing={isNativeChasing}
          nativeBumping={isNativeBumping}
          emotion={state.emotion}
          constraintsRef={constraintsRef}
          isSpeaking={state.isSpeaking}
          speechText={state.speechText}
          proactiveAnimation={state.proactiveAnimation}
          isQuickChatOpen={isQuickChatOpen}
          onQuickChatClose={() => setIsQuickChatOpen(false)}
          onSendMessage={message => sendAction({ type: 'send-message', message })}
          onChatClick={() => setIsQuickChatOpen(true)}
          onTasksClick={() => sendAction({ type: 'open-main', tab: 'tasks' })}
          onHoverChange={setIsPetHovered}
          onPoke={() => bridge?.pokePet?.()}
          sessionState={state.sessionState}
          timeLeft={state.timeLeft}
          currentTaskName={state.currentTaskName}
          onPauseSession={() => sendAction({ type: 'pause-session' })}
          onResumeSession={() => sendAction({ type: 'resume-session' })}
          onExtendSession={minutes => sendAction({ type: 'extend-session', minutes })}
          onCancelSession={() => sendAction({ type: 'cancel-session' })}
        />
      ) : null}
    </div>
  );
}
