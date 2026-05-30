'use client';

import { motion, Variants, AnimatePresence } from 'motion/react';
import { useEffect, useState } from 'react';
import { Send, X } from 'lucide-react';

export type Emotion = 'idle' | 'happy' | 'excited' | 'worried' | 'sad' | 'sleepy' | 'thinking' | 'angry' | 'hurt';
export type SessionState = 'idle' | 'running' | 'paused' | 'break';

const SoundFX = {
  playBlink: () => {
    try {
      const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gainNode = ctx.createGain();

      osc.type = 'square';
      osc.frequency.setValueAtTime(1200, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(2000, ctx.currentTime + 0.03);
      
      gainNode.gain.setValueAtTime(0.015, ctx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.03);

      osc.connect(gainNode);
      gainNode.connect(ctx.destination);

      osc.start();
      osc.stop(ctx.currentTime + 0.03);
    } catch(e) {}
  },
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
  emotion: Emotion;
  constraintsRef: React.RefObject<HTMLDivElement | null>;
  isSpeaking?: boolean;
  speechText?: string | null;
  isQuickChatOpen?: boolean;
  onQuickChatClose?: () => void;
  onSendMessage?: (msg: string) => void;
  onChatClick?: () => void;
  onTasksClick?: () => void;
  sessionState?: SessionState;
  timeLeft?: number;
  currentTaskName?: string;
  onPauseSession?: () => void;
  onResumeSession?: () => void;
  onCancelSession?: () => void;
}

export default function FloatingPet({ 
  emotion, 
  constraintsRef, 
  isSpeaking = false, 
  speechText,
  isQuickChatOpen,
  onQuickChatClose,
  onSendMessage,
  onChatClick, 
  onTasksClick,
  sessionState = 'idle',
  timeLeft = 0,
  currentTaskName,
  onPauseSession,
  onResumeSession,
  onCancelSession
}: FloatingPetProps) {
  const [isBlinking, setIsBlinking] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [chatInput, setChatInput] = useState('');

  useEffect(() => {
    // Random blink logic
    const blinkInterval = setInterval(() => {
      // Don't blink if eyes are closed/squinted tightly anyway
      if (emotion !== 'happy' && emotion !== 'excited' && emotion !== 'sad' && emotion !== 'sleepy') {
        if (Math.random() > 0.4) {
          setIsBlinking(true);
          SoundFX.playBlink();
          setTimeout(() => {
            setIsBlinking(false);
            // Occasional double blink
            if (Math.random() > 0.7) {
              setTimeout(() => {
                setIsBlinking(true);
                SoundFX.playBlink();
                setTimeout(() => setIsBlinking(false), 100);
              }, 150);
            }
          }, 100);
        }
      }
    }, 4000);
    return () => clearInterval(blinkInterval);
  }, [emotion]);

  useEffect(() => {
    SoundFX.playEmotionChange();
  }, [emotion]);

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
    sleepy: { y: [0, 4, 0], transition: { repeat: Infinity, duration: 5, ease: "easeInOut", delay: 0.5 } }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const displayEmotion = isDragging ? 'hurt' : emotion;

  return (
    <motion.div
      drag
      dragConstraints={constraintsRef}
      dragElastic={0.1}
      dragMomentum={false}
      onDragStart={() => {
        setIsDragging(true);
        if (typeof window !== 'undefined') {
          const win = window as any;
          if (win.electron && win.electron.setIgnoreMouseEvents) win.electron.setIgnoreMouseEvents(false);
          else if (win.ipcRenderer) win.ipcRenderer.send('set-ignore-mouse-events', false);
        }
      }}
      onDragEnd={() => {
        setIsDragging(false);
        if (typeof window !== 'undefined') {
          const win = window as any;
          if (win.electron && win.electron.setIgnoreMouseEvents) win.electron.setIgnoreMouseEvents(true, { forward: true });
          else if (win.ipcRenderer) win.ipcRenderer.send('set-ignore-mouse-events', true, { forward: true });
        }
      }}
      whileDrag={{ scale: 1.05, cursor: "grabbing" }}
      className="absolute z-40 flex flex-col items-center bottom-4 right-4"
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1, transition: { type: "spring", bounce: 0.5 } }}
      onHoverStart={() => {
        setIsHovered(true);
        if (typeof window !== 'undefined') {
          const win = window as any;
          if (win.electron && win.electron.setIgnoreMouseEvents) {
            win.electron.setIgnoreMouseEvents(false);
          } else if (win.ipcRenderer) {
            win.ipcRenderer.send('set-ignore-mouse-events', false);
          }
        }
      }}
      onHoverEnd={() => {
        setIsHovered(false);
        if (typeof window !== 'undefined') {
          const win = window as any;
          if (win.electron && win.electron.setIgnoreMouseEvents) {
            win.electron.setIgnoreMouseEvents(true, { forward: true });
          } else if (win.ipcRenderer) {
            win.ipcRenderer.send('set-ignore-mouse-events', true, { forward: true });
          }
        }
      }}
    >
      {/* Session Action Menu (Shows when running/paused) */}
      <AnimatePresence>
        {sessionState !== 'idle' && (
          <motion.div
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
        initial={{ opacity: 0, y: 10, scale: 0.9 }}
        animate={{ opacity: isHovered && !isQuickChatOpen && sessionState === 'idle' ? 1 : 0, y: isHovered && !isQuickChatOpen && sessionState === 'idle' ? -20 : 10, scale: isHovered && !isQuickChatOpen && sessionState === 'idle' ? 1 : 0.9 }}
        className="absolute -top-12 flex gap-2 bg-white border-[3px] border-black shadow-[4px_4px_0_#000] rounded-xl px-2 py-1 pointer-events-auto z-10"
      >
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
            initial={{ opacity: 0, scale: 0.8, rotate: -5, originX: 0, originY: 1 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="absolute -top-16 left-full ml-4 min-w-[140px] max-w-[220px] bg-white border-[4px] border-black shadow-[6px_6px_0_#000] rounded-2xl p-4 z-40 pointer-events-none"
          >
            {/* Triangle tip pointing left */}
            <div className="absolute top-1/2 -left-4 -translate-y-1/2 w-0 h-0 border-t-[10px] border-t-transparent border-b-[10px] border-b-transparent border-r-[12px] border-r-black" />
            <div className="absolute top-1/2 -left-2.5 -translate-y-1/2 w-0 h-0 border-t-[8px] border-t-transparent border-b-[8px] border-b-transparent border-r-[10px] border-r-white z-10" />
            
            <div className="text-black font-mono font-black text-[13px] tracking-tighter leading-tight break-words uppercase">
              {emotion === 'thinking' ? (
                <div className="flex gap-2 items-center justify-center py-2 h-6">
                  <motion.div className="w-2.5 h-2.5 bg-black" animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0 }} />
                  <motion.div className="w-2.5 h-2.5 bg-black" animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0.15 }} />
                  <motion.div className="w-2.5 h-2.5 bg-black" animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0.3 }} />
                </div>
              ) : (
                speechText
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Quick Chat Input */}
      <AnimatePresence>
        {isQuickChatOpen && (
          <motion.div
             initial={{ opacity: 0, y: -10 }}
             animate={{ opacity: 1, y: 0 }}
             exit={{ opacity: 0, y: -10 }}
             className="absolute -bottom-20 left-1/2 -translate-x-1/2 w-72 bg-white border-[4px] border-black shadow-[6px_6px_0_#000] p-1.5 rounded-xl z-50 pointer-events-auto"
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
        variants={faceVariants}
        animate={displayEmotion}
      >
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
                 animate={getEyeStyle('left', displayEmotion, isBlinking)}
                 transition={{ type: "spring", stiffness: 400, damping: 25 }}
                 className="bg-cyan-400 absolute ml-[-50px] mt-[-20px] shadow-[0_0_10px_rgba(34,211,238,0.5)]"
               />
               
               {/* Right Eye */}
               <motion.div
                 animate={getEyeStyle('right', displayEmotion, isBlinking)}
                 transition={{ type: "spring", stiffness: 400, damping: 25 }}
                 className="bg-cyan-400 absolute ml-[50px] mt-[-20px] shadow-[0_0_10px_rgba(34,211,238,0.5)]"
               />
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
