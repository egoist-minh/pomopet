'use client';

import { useRef, useState, useEffect } from 'react';
import FloatingPet, { Emotion, SessionState } from './FloatingPet';
import MainWindow from './MainWindow';
import SetupModal from './SetupModal';
import { motion, AnimatePresence } from 'motion/react';
import { Sparkles, MonitorSmartphone } from 'lucide-react';

export interface Task {
  id: string;
  name: string;
  priority: 'high' | 'medium' | 'low';
  deadline?: string;
  completed: boolean;
}

function Clock() {
  const [time, setTime] = useState<string>('');
  
  useEffect(() => {
    // Only access DOM / Date on mount
    setTime(new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
    const interval = setInterval(() => {
      setTime(new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
    }, 1000);
    return () => clearInterval(interval);
  }, []);
  
  return <span className="tabular-nums border-l-[3px] border-black pl-4">{time || '--:--'}</span>;
}

export default function DesktopEnvironment() {
  const constraintsRef = useRef<HTMLDivElement>(null);
  const [petName, setPetName] = useState<string | null>(null);
  const [emotion, setEmotion] = useState<Emotion>('idle');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMainWindowOpen, setIsMainWindowOpen] = useState(false);
  const [isQuickChatOpen, setIsQuickChatOpen] = useState(false);
  const [speechText, setSpeechText] = useState<string | null>(null);
  const [isDesktopMode, setIsDesktopMode] = useState(false);
  const [activeTab, setActiveTab] = useState<'chat' | 'tasks' | 'stats' | 'settings'>('chat');
  const [messages, setMessages] = useState<{role: 'user' | 'pet', text: string}[]>([]);

  // Task & Session State
  const [tasks, setTasks] = useState<Task[]>([
    { id: '1', name: 'Design PomoPet MVP', priority: 'high', completed: false },
    { id: '2', name: 'Write backend service', priority: 'medium', completed: false }
  ]);
  const [sessionState, setSessionState] = useState<SessionState>('idle');
  const [timeLeft, setTimeLeft] = useState<number>(0);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [focusHoursToday, setFocusHoursToday] = useState(0);
  const [focusHoursWeek, setFocusHoursWeek] = useState(12.5); // Mock data for week
  const [sessionsCompleted, setSessionsCompleted] = useState(0);
  const [distractionChain, setDistractionChain] = useState(0);
  
  const initialDistractionData = Array.from({ length: 12 }, (_, i) => ({
    time: `${(i * 2).toString().padStart(2, '0')}:00`,
    distractions: 0
  }));
  const [distractionData, setDistractionData] = useState<{time: string, distractions: number}[]>(initialDistractionData);
  
  const originalDurationRef = useRef<number>(0);

  useEffect(() => {
    // Check local storage for existing pet name
    const storedName = localStorage.getItem('petName');
    if (storedName) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPetName(storedName);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMessages([{ role: 'pet', text: `Welcome back! I'm ${storedName}.` }]);
    }
  }, []);

  const handleSetupComplete = (name: string) => {
    setPetName(name);
    localStorage.setItem('petName', name);
    setMessages([{ role: 'pet', text: `Hello! I am ${name}, your new desktop companion.` }]);
    setEmotion('happy');
    setIsSpeaking(true);
    setSpeechText(`BOOT SEQUENCE COMPLETE. GREETINGS, I AM ${name}.`);
    
    setTimeout(() => {
      setEmotion('idle');
      setIsSpeaking(false);
      setSpeechText(null);
    }, 4000);
  };

  const handleSendMessage = (msg: string) => {
    setMessages(prev => [...prev, { role: 'user', text: msg }]);
    
    // Simulate thinking and responding
    setSpeechText(null);
    setEmotion('thinking');
    
    setTimeout(() => {
       let reply = "That's interesting!";
       let nextEmotion: Emotion = 'happy';
       
       const lowerMsg = msg.toLowerCase();
       if (lowerMsg.includes('hello') || lowerMsg.includes('hi')) {
          reply = `Hi there! It's me, ${petName}!`;
          nextEmotion = 'happy';
       } else if (lowerMsg.includes('bad') || lowerMsg.includes('sad')) {
          reply = "Oh no, I'm sorry to hear that. 😢";
          nextEmotion = 'sad';
       } else if (lowerMsg.includes('mad') || lowerMsg.includes('angry') || lowerMsg.includes('hate')) {
          reply = "Whoa, calm down!";
          nextEmotion = 'worried';
       } else if (lowerMsg.includes('joke')) {
          reply = "Why did the computer show up at work late? It had a hard drive!";
          nextEmotion = 'happy';
       } else if (lowerMsg.includes('yay') || lowerMsg.includes('win') || lowerMsg.includes('awesome')) {
          reply = "Yay! That's awesome!";
          nextEmotion = 'excited';
       } else if (lowerMsg.includes('boo') || lowerMsg.includes('ghost')) {
          reply = "Ah! You scared me!";
          nextEmotion = 'worried';
       }

       setMessages(prev => [...prev, { role: 'pet', text: reply }]);
       setEmotion(nextEmotion);
       setIsSpeaking(true);
       setSpeechText(reply.toUpperCase());
       
       // Stop speaking animation based on message length approx
       setTimeout(() => setIsSpeaking(false), Math.min(reply.length * 50, 2500));
       setTimeout(() => setSpeechText(null), Math.max(Math.min(reply.length * 100, 5000), 3000));

       // Return to idle after a while
       setTimeout(() => {
          setEmotion(prev => prev === nextEmotion ? 'idle' : prev);
       }, 2000);
    }, 2000);
  };

  // Timer Effect
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (sessionState === 'running' || sessionState === 'break') {
      interval = setInterval(() => {
        setTimeLeft(prev => {
          if (prev <= 1) {
            clearInterval(interval);
            // Instead of dealing with stale closures or callbacks, 
            // trigger the natural effect below.
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [sessionState]);

  useEffect(() => {
    if (timeLeft === 0 && sessionState !== 'idle') {
       handleSessionComplete();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeft, sessionState]);

  const handleSessionComplete = () => {
    if (sessionState === 'running') {
      setEmotion('excited');
      setSpeechText('SESSION COMPLETE! GREAT JOB!');
      setSessionsCompleted(prev => prev + 1);
      setFocusHoursToday(prev => prev + (originalDurationRef.current / 3600)); // Convert seconds to hours
      setFocusHoursWeek(prev => prev + (originalDurationRef.current / 3600));
      
      setTimeout(() => {
        setSessionState('break');
        setTimeLeft(5 * 60); // 5 min break
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
  };

  const handleStartSession = (task: Task, durationMinutes: number) => {
    setCurrentTask(task);
    const durationSeconds = durationMinutes * 60;
    setTimeLeft(durationSeconds);
    originalDurationRef.current = durationSeconds;
    setSessionState('running');
    setEmotion('happy');
    setSpeechText(`FOCUSING ON: ${task.name.toUpperCase()}`);
    setIsMainWindowOpen(false); // Close window to focus
    setTimeout(() => setSpeechText(null), 4000);
  };

  const handlePauseSession = () => {
    setSessionState('paused');
    setEmotion('idle');
  };

  const handleResumeSession = () => {
    setSessionState('running');
    setEmotion('happy');
  };

  const handleCancelSession = () => {
    setSessionState('idle');
    setCurrentTask(null);
    setTimeLeft(0);
    setEmotion('sad');
    setSpeechText('SESSION CANCELLED...');
    setDistractionChain(0); // Reset distraction on cancel
    setTimeout(() => {
      setEmotion('idle');
      setSpeechText(null);
    }, 4000);
  };

  const handleSimulateDistraction = () => {
    if (sessionState === 'running') {
      const currentHour = new Date().getHours();
      const binIndex = Math.floor(currentHour / 2);
      setDistractionData(prev => {
        const newData = [...prev];
        newData[binIndex] = { ...newData[binIndex], distractions: newData[binIndex].distractions + 1 };
        return newData;
      });

      setDistractionChain(prev => prev + 1);
      setTimeLeft(prev => prev + 300); // add 5 minutes penalty
      setEmotion('angry');
      setSpeechText('HEY! GET BACK TO WORK! (+5 MIN PENALTY)');
      setTimeout(() => {
        if (sessionState === 'running') {
          setEmotion('happy');
          setSpeechText(null);
        }
      }, 5000);
    } else {
      setEmotion('idle');
      setSpeechText('NO SESSION TO DISTRACT FROM!');
      setTimeout(() => setSpeechText(null), 3000);
    }
  };

  return (
    <div 
      ref={constraintsRef}
      className={`relative w-full h-screen overflow-hidden font-sans selection:bg-cyan-400/50 bg-transparent`}
    >
      <AnimatePresence>
        {!petName && (
           <SetupModal onComplete={handleSetupComplete} />
        )}
      </AnimatePresence>

      {petName && (
         <>
            {/* Always-on System Tray Floating Hint removed for clean desktop pet */}


            {/* Floating Pet Widget - Always on top layer */}
            <FloatingPet 
               emotion={emotion} 
               constraintsRef={constraintsRef} 
               isSpeaking={isSpeaking}
               speechText={speechText}
               isQuickChatOpen={isQuickChatOpen}
               onQuickChatClose={() => setIsQuickChatOpen(false)}
               onSendMessage={handleSendMessage}
               onChatClick={() => {
                 setIsQuickChatOpen(true);
               }}
               onTasksClick={() => {
                 setIsMainWindowOpen(true);
                 setActiveTab('tasks');
               }}
               sessionState={sessionState}
               timeLeft={timeLeft}
               currentTaskName={currentTask?.name}
               onPauseSession={handlePauseSession}
               onResumeSession={handleResumeSession}
               onCancelSession={handleCancelSession}
            />

            {/* Main Interactive Window */}
            <MainWindow 
               isOpen={isMainWindowOpen}
               onClose={() => setIsMainWindowOpen(false)}
               onMinimize={() => setIsMainWindowOpen(false)}
               petName={petName}
               setPetName={(n) => { setPetName(n); localStorage.setItem('petName', n); }}
               emotion={emotion}
               setEmotion={setEmotion}
               chatMessages={messages}
               onSendMessage={handleSendMessage}
               activeTab={activeTab}
               setActiveTab={setActiveTab}
               isDesktopMode={isDesktopMode}
               setIsDesktopMode={setIsDesktopMode}
               tasks={tasks}
               setTasks={setTasks}
               focusHoursToday={focusHoursToday}
               focusHoursWeek={focusHoursWeek}
               sessionsCompleted={sessionsCompleted}
               onStartSession={handleStartSession}
               sessionState={sessionState}
               distractionChain={distractionChain}
               distractionData={distractionData}
               onSimulateDistraction={handleSimulateDistraction}
            />
         </>
      )}
    </div>
  );
}
