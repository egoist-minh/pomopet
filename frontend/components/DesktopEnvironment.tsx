'use client';

import { useRef, useState, useEffect, useCallback } from 'react';
import FloatingPet, { Emotion, SessionState } from './FloatingPet';
import MainWindow, { AIService } from './MainWindow';
import SetupModal from './SetupModal';
import { motion, AnimatePresence } from 'motion/react';
import { api, Task, Statistics, setErrorCallback, APIError } from '@/lib/api';
import { initializeLogger } from '@/lib/logger';

function Clock() {
  const [time, setTime] = useState<string>('');
  
  useEffect(() => {
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
  const [aiService, setAiService] = useState<AIService>('openai');
  const [backendConnected, setBackendConnected] = useState(false);

  // Task & Session State
  const [tasks, setTasks] = useState<Task[]>([]);
  const tasksRef = useRef<Task[]>([]);
  const [sessionState, setSessionState] = useState<SessionState>('idle');
  const [timeLeft, setTimeLeft] = useState<number>(0);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [focusHoursToday, setFocusHoursToday] = useState(0);
  const [focusHoursWeek, setFocusHoursWeek] = useState(0);
  const [sessionsCompleted, setSessionsCompleted] = useState(0);
  const [distractionChain, setDistractionChain] = useState(0);
  const [apiError, setApiError] = useState<string | null>(null);
  
  const initialDistractionData = Array.from({ length: 12 }, (_, i) => ({
    time: `${(i * 2).toString().padStart(2, '0')}:00`,
    distractions: 0
  }));
  const [distractionData, setDistractionData] = useState<{time: string, distractions: number}[]>(initialDistractionData);
  
  const originalDurationRef = useRef<number>(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

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
          originalDurationRef.current = session.duration;
        }
      }
    }
  }, []);

  // Initial data load
  useEffect(() => {
    const storedName = localStorage.getItem('petName');
    if (storedName) {
      setPetName(storedName);
      setMessages([{ role: 'pet', text: `Welcome back! I'm ${storedName}.` }]);
    }
    const storedAIService = localStorage.getItem('ai_service') as AIService;
    if (storedAIService) {
      setAiService(storedAIService);
    }

    initializeLogger();

    // Check backend connection and load data
    const initBackend = async (retryCount = 0) => {
      const maxRetries = 3;
      try {
        console.log(`[Init] Checking backend health via api.getTasks()...`);
        const tasks = await api.getTasks();
        console.log(`[Init] Backend responded successfully. Tasks count: ${tasks?.length ?? 0}`);
        setApiError(null);
        setBackendConnected(true);

        try {
          await loadTasks();
          console.log(`[Init] loadTasks() completed`);
        } catch (e) {
          console.error(`[Init] loadTasks() failed:`, e);
        }

        try {
          await loadStatistics();
          console.log(`[Init] loadStatistics() completed`);
        } catch (e) {
          console.error(`[Init] loadStatistics() failed:`, e);
        }

        try {
          await restoreSession();
          console.log(`[Init] restoreSession() completed`);
        } catch (e) {
          console.error(`[Init] restoreSession() failed:`, e);
        }

        console.log(`[Init] Initialization complete. backendConnected = true`);
      } catch (e) {
        const err = e as any;
        const isNetworkError = !err?.response && (
          err?.message?.toLowerCase().includes('network error') ||
          err?.message?.toLowerCase().includes('failed to fetch') ||
          err?.message?.includes('ECONNREFUSED') ||
          err?.message?.includes('ENOTFOUND') ||
          err?.message?.includes('ETIMEDOUT')
        );

        if (!isNetworkError) {
          if (err?.response) {
            console.error(`[Init] Backend responded with HTTP ${err.response.status}. Not a network failure. Keeping backendConnected = true.`);
            console.error(`[Init] Response data:`, err.response.data);
          } else {
            console.error(`[Init] Unexpected error (not network-related). Keeping backendConnected = true.`);
            console.error(`[Init] Error:`, err);
          }
          return;
        }

        if (retryCount < maxRetries) {
          console.log(`[Init] Network error detected. Retry attempt ${retryCount + 1}/${maxRetries}...`);
          await new Promise(r => setTimeout(r, 1000));
          return initBackend(retryCount + 1);
        }
        console.error(`[Init] Backend unreachable after ${maxRetries} retries. Activating Fallback Local State.`);
        setBackendConnected(false);
        setTasks([
          { id: '1', name: 'Design PomoPet MVP', priority: 'high' as const, completed: false, subtasks: [] },
          { id: '2', name: 'Write backend service', priority: 'medium' as const, completed: false, subtasks: [] }
        ]);
      }
    };

    initBackend();

    setErrorCallback((error: APIError) => {
      setApiError(error.message);
      const isNetworkError = error.message?.toLowerCase().includes('network error') ||
                           error.message?.toLowerCase().includes('failed to fetch') ||
                           error.message?.includes('ECONNREFUSED') ||
                           error.message?.includes('ENOTFOUND') ||
                           error.message?.includes('ETIMEDOUT');
      if (isNetworkError) {
        setBackendConnected(false);
      }
    });

    return () => setErrorCallback(null);
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
          reply = "Oh no, I'm sorry to hear that.";
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
       
       setTimeout(() => setIsSpeaking(false), Math.min(reply.length * 50, 2500));
       setTimeout(() => setSpeechText(null), Math.max(Math.min(reply.length * 100, 5000), 3000));

       setTimeout(() => {
          setEmotion(prev => prev === nextEmotion ? 'idle' : prev);
       }, 2000);
    }, 2000);
  };

  // Timer Effect
  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (sessionState === 'running' || sessionState === 'break') {
      timerRef.current = setInterval(() => {
        setTimeLeft(prev => {
          if (prev <= 1) {
            return 0;
          }
          // Sync with backend periodically
          if (backendConnected && prev % 10 === 0) {
            api.updateTimeLeft(prev - 1);
          }
          return prev - 1;
        });
      }, 1000);
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [sessionState, backendConnected]);

  useEffect(() => {
    if (timeLeft === 0 && sessionState !== 'idle') {
       handleSessionComplete();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeft, sessionState]);

  const handleSessionComplete = async () => {
    if (sessionState === 'running') {
      if (!backendConnected) {
        console.error(`[handleSessionComplete] Backend NOT connected - cannot complete session!`);
        throw new Error('Backend not connected');
      }
      
      await api.completeSession();
      
      setEmotion('excited');
      setSpeechText('SESSION COMPLETE! GREAT JOB!');
      setSessionsCompleted(prev => prev + 1);
      setFocusHoursToday(prev => prev + (originalDurationRef.current / 3600));
      setFocusHoursWeek(prev => prev + (originalDurationRef.current / 3600));
      
      setTimeout(() => {
        setSessionState('break');
        setTimeLeft(5 * 60);
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

  const handleStartSession = async (task: Task, durationMinutes: number) => {
    const durationSeconds = durationMinutes * 60;
    originalDurationRef.current = durationSeconds;
    
    if (!backendConnected) {
      console.error(`[handleStartSession] Backend NOT connected - cannot start session!`);
      throw new Error('Backend not connected');
    }
    
    await api.startSession(task.id, durationSeconds);
    
    setCurrentTask(task);
    setTimeLeft(durationSeconds);
    setSessionState('running');
    setEmotion('happy');
    setSpeechText(`FOCUSING ON: ${task.name.toUpperCase()}`);
    setIsMainWindowOpen(false);
    setTimeout(() => setSpeechText(null), 4000);
  };

  const handlePauseSession = async () => {
    if (!backendConnected) {
      console.error(`[handlePauseSession] Backend NOT connected - cannot pause session!`);
      throw new Error('Backend not connected');
    }
    
    await api.pauseSession();
    setSessionState('paused');
    setEmotion('idle');
  };

  const handleResumeSession = async () => {
    if (!backendConnected) {
      console.error(`[handleResumeSession] Backend NOT connected - cannot resume session!`);
      throw new Error('Backend not connected');
    }
    
    await api.resumeSession();
    setSessionState('running');
    setEmotion('happy');
  };

  const handleCancelSession = async () => {
    if (!backendConnected) {
      console.error(`[handleCancelSession] Backend NOT connected - cannot cancel session!`);
      throw new Error('Backend not connected');
    }
    
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
  };

  const handleSimulateDistraction = async () => {
    if (sessionState === 'running') {
      if (!backendConnected) {
        console.error(`[handleSimulateDistraction] Backend NOT connected - cannot add distraction!`);
        throw new Error('Backend not connected');
      }
      
      const result = await api.addDistraction();
      if (result) {
        setDistractionChain(result.distraction_count);
        setTimeLeft(result.time_left);
      }

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

  const addTaskWithApi = async (name: string, priority: 'high' | 'medium' | 'low', deadline: string) => {
    console.log(`[addTaskWithApi] Attempting to add task: "${name}" | backendConnected: ${backendConnected}`);
    
    if (!backendConnected) {
      console.error(`[addTaskWithApi] Backend NOT connected - cannot create task!`);
      throw new Error('Backend not connected');
    }
    
    console.log(`[addTaskWithApi] Backend connected - sending POST request to API`);
    try {
      const result = await api.createTask({ name, priority, deadline });
      if (result) {
        console.log(`[addTaskWithApi] API call successful, reloading tasks from database`);
      } else {
        console.error(`[addTaskWithApi] API call returned null/undefined - attempting to reload tasks to verify database state`);
      }
      await loadTasks();
    } catch (error: any) {
      console.error(`[addTaskWithApi] API call failed!`);
      console.error(`[addTaskWithApi] Error message:`, error?.message);
      console.error(`[addTaskWithApi] HTTP status:`, error?.response?.status);
      console.error(`[addTaskWithApi] Response data:`, error?.response?.data);
      await loadTasks();
      throw error;
    }
  };

  const deleteTaskWithApi = async (taskId: string) => {
    if (!backendConnected) {
      console.error(`[deleteTaskWithApi] Backend NOT connected - cannot delete task!`);
      throw new Error('Backend not connected');
    }
    
    try {
      await api.deleteTask(taskId);
    } catch (error) {
      console.error(`[deleteTaskWithApi] Failed to delete task:`, error);
      await loadTasks();
      throw error;
    }
    setTasks(prev => prev.filter(t => t.id !== taskId));
  };

  const toggleTaskWithApi = async (taskId: string) => {
    if (!backendConnected) {
      console.error(`[toggleTaskWithApi] Backend NOT connected - cannot complete task!`);
      throw new Error('Backend not connected');
    }
    
    try {
      await api.completeTask(taskId);
    } catch (error) {
      console.error(`[toggleTaskWithApi] Failed to complete task:`, error);
      await loadTasks();
      throw error;
    }
    setTasks(prev => prev.filter(t => t.id !== taskId));
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
                onAddTask={addTaskWithApi}
                onDeleteTask={deleteTaskWithApi}
                onToggleTask={toggleTaskWithApi}
                focusHoursToday={focusHoursToday}
                focusHoursWeek={focusHoursWeek}
                sessionsCompleted={sessionsCompleted}
                onStartSession={handleStartSession}
                sessionState={sessionState}
                distractionChain={distractionChain}
                distractionData={distractionData}
                onSimulateDistraction={handleSimulateDistraction}
                aiService={aiService}
                setAiService={setAiService}
                apiError={apiError}
                backendConnected={backendConnected}
               />
         </>
      )}
    </div>
  );
}
