'use client';

import { motion, AnimatePresence, useDragControls } from 'motion/react';
import { X, Minus, MessageSquare, CheckSquare, BarChart2, Settings, Send } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { Emotion, SessionState } from './FloatingPet';
import { AIProvider, AIProviderStatus, BehaviorActionContext, ChatMessageItem, Task } from '@/lib/api';
import dynamic from 'next/dynamic';
import { downloadLogs } from '@/lib/logger';
import PlanPanel from './PlanPanel';
import RelationshipMemories from './RelationshipMemories';
import ProactiveTracePanel from './ProactiveTracePanel';

const AreaChart = dynamic(() => import('recharts').then((mod) => mod.AreaChart), { ssr: false });
const Area = dynamic(() => import('recharts').then((mod) => mod.Area), { ssr: false });
const XAxis = dynamic(() => import('recharts').then((mod) => mod.XAxis), { ssr: false });
const YAxis = dynamic(() => import('recharts').then((mod) => mod.YAxis), { ssr: false });
const CartesianGrid = dynamic(() => import('recharts').then((mod) => mod.CartesianGrid), { ssr: false });
const ResponsiveContainer = dynamic(() => import('recharts').then((mod) => mod.ResponsiveContainer), { ssr: false });
const Tooltip = dynamic(() => import('recharts').then((mod) => mod.Tooltip), { ssr: false });

interface MainWindowProps {
   embedded?: boolean;
   isOpen: boolean;
   onClose: () => void;
   onMinimize: () => void;
   petName: string;
   setPetName: (name: string) => void;
   emotion: Emotion;
   setEmotion: (emotion: Emotion) => void;
   chatMessages: ChatMessageItem[];
   onSendMessage: (msg: string) => void;
   onResolveChatAction: (actionId: string, decision: 'confirm' | 'cancel') => void;
   activeTab: 'chat' | 'tasks' | 'stats' | 'settings';
   setActiveTab: (tab: 'chat' | 'tasks' | 'stats' | 'settings') => void;
   isDesktopMode: boolean;
   setIsDesktopMode: (mode: boolean) => void;
   focusHoursToday: number;
   focusHoursWeek: number;
   sessionsCompleted: number;
   onStartSession: (task: Task, durationMinutes: number, context?: BehaviorActionContext) => void;
    onTasksChanged?: () => Promise<void> | void;
    planRefreshToken?: number;
   sessionState: SessionState;
   distractionChain: number;
   distractionData: { time: string, distractions: number }[];
   onSimulateDistraction: () => void;
   autoDistractionEnabled: boolean;
   onAutoDistractionEnabledChange: (enabled: boolean) => void;
   aiProvider: AIProvider;
   setAiProvider: (provider: AIProvider) => void;
   configuredProviders: AIProviderStatus;
   onSaveApiKey: (provider: AIProvider, apiKey: string) => Promise<boolean>;
   onEvaluateProactiveNow?: () => Promise<boolean>;
    apiError?: string | null;
    backendConnected?: boolean;
 }

export default function MainWindow({
   embedded = false,
   isOpen,
   onClose,
   onMinimize,
   petName,
   setPetName,
   emotion,
   setEmotion,
   chatMessages,
   onSendMessage,
   onResolveChatAction,
   activeTab,
   setActiveTab,
   isDesktopMode,
   setIsDesktopMode,
   focusHoursToday,
   focusHoursWeek,
   sessionsCompleted,
   onStartSession,
    onTasksChanged,
    planRefreshToken = 0,
   sessionState,
   distractionChain,
   distractionData,
   onSimulateDistraction,
   autoDistractionEnabled,
   onAutoDistractionEnabledChange,
   aiProvider,
   setAiProvider,
   configuredProviders,
   onSaveApiKey,
   onEvaluateProactiveNow,
    apiError,
    backendConnected = true,
  }: MainWindowProps) {
  const dragControls = useDragControls();
  const [chatInput, setChatInput] = useState('');

  const [apiKey, setApiKey] = useState('');
  const [isSavingApiKey, setIsSavingApiKey] = useState(false);
  const [apiKeyStatus, setApiKeyStatus] = useState<string | null>(null);

  const lastMessageRef = useRef<HTMLDivElement>(null);
  const hasPendingChatAction = chatMessages.some(
    message => message.actionStatus === 'pending' || message.actionStatus === 'processing',
  );

  useEffect(() => {
    if (activeTab === 'chat' && lastMessageRef.current) {
      lastMessageRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, activeTab]);

  const handleChatSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || hasPendingChatAction) return;
    onSendMessage(chatInput.trim());
    setChatInput('');
  };

  const handleUpdateName = (newName: string) => {
    const finalName = newName.trim();
    if (finalName === '') {
      alert('Tên thú cưng không được để trống!');
      return;
    }
    setPetName(finalName);
  };

  const handleResetApp = () => {
    if (window.confirm("Xóa thú cưng và cài đặt lại từ đầu?")) {
      localStorage.removeItem('petName');
      window.location.reload();
    }
  };

  const saveProviderKey = async () => {
    const value = apiKey.trim();
    if (value.length < 8) return;

    setIsSavingApiKey(true);
    setApiKeyStatus(null);
    try {
      const persisted = await onSaveApiKey(aiProvider, value);
      setApiKey('');
      setApiKeyStatus(
        persisted
          ? 'KEY SAVED SECURELY.'
          : 'KEY ACTIVE FOR THIS BACKEND SESSION.',
      );
    } catch (error) {
      console.error('[saveProviderKey] Failed to save API key', error);
      setApiKeyStatus('FAILED TO SAVE KEY.');
    } finally {
      setIsSavingApiKey(false);
    }
  };


  if (!isOpen) return null;

  return (
    <motion.div
      data-pomopet-window-region
      initial={{ opacity: 0, scale: 0.95, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: 20 }}
      className={`${
        embedded
          ? 'absolute inset-0'
          : 'absolute top-24 left-8 sm:left-24 w-full max-w-sm sm:max-w-md rounded-xl shadow-[8px_8px_0_#000]'
      } bg-white border-[4px] border-black flex flex-col z-30 pointer-events-auto overflow-hidden`}
      drag={!embedded}
      dragControls={dragControls}
      dragListener={false}
      dragMomentum={false}
    >
      {/* Title Bar - Classic Mac OS style */}
      <div
        className="bg-black p-2 px-3 flex items-center justify-between cursor-move select-none"
        style={embedded ? ({ WebkitAppRegion: 'drag' } as React.CSSProperties) : undefined}
        onPointerDown={(e) => {
          if (!embedded) dragControls.start(e);
        }}
      >
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 bg-cyan-400 border-2 border-black flex items-center justify-center">
            <span className="text-black font-bold text-[10px] font-space">{petName.charAt(0)}</span>
          </div>
          <h3 className="text-white font-mono text-sm font-bold uppercase tracking-widest">
            {petName} OS
          </h3>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onMinimize}
            style={embedded ? ({ WebkitAppRegion: 'no-drag' } as React.CSSProperties) : undefined}
            className="p-1 bg-white border-2 border-black hover:bg-cyan-400 transition-colors"
          >
            <Minus className="w-3 h-3 text-black" strokeWidth={3} />
          </button>
          <button
            onClick={onClose}
            style={embedded ? ({ WebkitAppRegion: 'no-drag' } as React.CSSProperties) : undefined}
            className="p-1 bg-white border-2 border-black hover:bg-cyan-400 transition-colors"
          >
            <X className="w-3 h-3 text-black" strokeWidth={3} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b-[4px] border-black bg-white">
        {[
          { id: 'chat', icon: MessageSquare, label: 'Chat' },
          { id: 'tasks', icon: CheckSquare, label: 'Plan' },
          { id: 'stats', icon: BarChart2, label: 'Stats' },
          { id: 'settings', icon: Settings, label: 'Config' },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex-1 py-3 border-r-[4px] last:border-r-0 border-black flex flex-col items-center gap-1 transition-colors ${
                isActive
                  ? 'bg-cyan-400 text-black'
                  : 'bg-white text-black hover:bg-gray-200'
              }`}
            >
              <Icon className="w-4 h-4" strokeWidth={isActive ? 3 : 2} />
              <span className="text-[10px] uppercase font-bold font-mono">
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

      {apiError && (
        <div className="bg-red-100 border-l-4 border-red-500 p-2 font-mono text-xs text-red-700">
          ⚠ {apiError}
        </div>
      )}

      <div className={`px-2 py-1 text-[10px] font-mono font-bold border-b-[2px] border-black flex items-center gap-1 ${
        backendConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}>
        <div className={`w-2 h-2 rounded-full ${backendConnected ? 'bg-green-500' : 'bg-red-500'}`} />
        {backendConnected ? 'DB CONNECTED' : 'DB DISCONNECTED'}
      </div>

      {/* Content Area */}
      <div className={`${embedded ? 'flex-1 min-h-0' : 'h-80'} relative bg-gray-100`}>
        <AnimatePresence mode="wait">
          {activeTab === 'chat' && (
            <motion.div
              key="chat"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 flex flex-col"
            >
              <div className="flex-1 p-4 overflow-y-auto flex flex-col gap-3 font-mono text-sm scrollbar-thin scrollbar-thumb-black">
                {chatMessages.map((m, i) => (
                  <div key={m.action?.id || m.proactiveSuggestion?.decisionId || i} className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
                    <div
                      className={`max-w-[85%] border-[3px] border-black px-3 py-2 font-bold shadow-[2px_2px_0_#000] ${
                        m.role === 'user'
                          ? 'bg-cyan-400 text-black'
                          : 'bg-white text-black'
                      }`}
                      ref={i === chatMessages.length - 1 ? lastMessageRef : null}
                    >
                      {m.text}
                    </div>
                    {m.proactiveSuggestion?.target === 'plan' && (
                      <button
                        type="button"
                        onClick={() => setActiveTab('tasks')}
                        className="mt-2 border-[2px] border-black bg-cyan-400 px-3 py-1 text-[10px] font-black uppercase shadow-[2px_2px_0_#000] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none"
                      >
                        Open Plan
                      </button>
                    )}
                    {m.action && (
                      <div className="mt-2 max-w-[85%] border-[3px] border-black bg-amber-50 px-3 py-2 shadow-[2px_2px_0_#000]">
                        <div className="text-[10px] uppercase text-amber-700">Confirmation required</div>
                        <div className="mt-1 whitespace-pre-line text-xs">{m.action.preview}</div>
                        {(m.actionStatus === 'pending' || m.actionStatus === 'processing') && (
                          <div className="mt-3 flex gap-2">
                            <button
                              type="button"
                              disabled={m.actionStatus === 'processing'}
                              onClick={() => onResolveChatAction(m.action!.id, 'confirm')}
                              className="border-[2px] border-black bg-cyan-400 px-3 py-1 text-[10px] uppercase disabled:opacity-50"
                            >
                              Confirm
                            </button>
                            <button
                              type="button"
                              disabled={m.actionStatus === 'processing'}
                              onClick={() => onResolveChatAction(m.action!.id, 'cancel')}
                              className="border-[2px] border-black bg-white px-3 py-1 text-[10px] uppercase disabled:opacity-50"
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                        {m.actionStatus === 'completed' && (
                          <div className="mt-2 text-[10px] uppercase text-green-700">Completed</div>
                        )}
                        {m.actionStatus === 'cancelled' && (
                          <div className="mt-2 text-[10px] uppercase text-gray-600">Cancelled</div>
                        )}
                        {m.actionStatus === 'error' && (
                          <div className="mt-2 text-[10px] uppercase text-red-700">Could not complete</div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
                {emotion === 'thinking' && (
                  <div className="flex justify-start">
                    <div className="bg-white border-[3px] border-black text-black px-4 py-3 flex gap-1 items-center shadow-[2px_2px_0_#000]" ref={lastMessageRef}>
                      <motion.div className="w-2 h-2 bg-black" animate={{ y: [0, -4, 0] }} transition={{ repeat: Infinity, delay: 0 }} />
                      <motion.div className="w-2 h-2 bg-black" animate={{ y: [0, -4, 0] }} transition={{ repeat: Infinity, delay: 0.15 }} />
                      <motion.div className="w-2 h-2 bg-black" animate={{ y: [0, -4, 0] }} transition={{ repeat: Infinity, delay: 0.3 }} />
                    </div>
                  </div>
                )}
              </div>
              <form onSubmit={handleChatSubmit} className="p-3 bg-white border-t-[4px] border-black flex gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder={`Chat with ${petName}...`}
                  disabled={hasPendingChatAction}
                  className="flex-1 bg-white border-[3px] border-black px-3 py-2 text-black font-mono text-xs font-bold outline-none focus:bg-cyan-50 placeholder:text-gray-400"
                />
                <button
                  type="submit"
                  disabled={!chatInput.trim() || hasPendingChatAction}
                  className="bg-cyan-400 hover:bg-cyan-300 disabled:opacity-50 disabled:hover:bg-cyan-400 text-black p-2 border-[3px] border-black shadow-[2px_2px_0_#000] active:shadow-none active:translate-y-[2px] active:translate-x-[2px] transition-all"
                >
                  <Send className="w-4 h-4" strokeWidth={3} />
                </button>
              </form>
            </motion.div>
          )}

          {activeTab === 'tasks' && (
            <motion.div
              key="tasks"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0"
            >
              <PlanPanel
                petName={petName}
                sessionState={sessionState}
                onStartSession={onStartSession}
                onTasksChanged={onTasksChanged}
                provider={aiProvider}
                refreshToken={planRefreshToken}
              />
            </motion.div>
          )}

          {activeTab === 'stats' && (
            <motion.div
              key="stats"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 p-6 bg-white overflow-y-auto scrollbar-thin scrollbar-thumb-black"
            >
              <div className="flex flex-col gap-6 min-h-max pb-4">
                <div className="grid grid-cols-2 gap-4">
                <div className="bg-white border-[4px] border-black shadow-[4px_4px_0_#000] p-4 text-center">
                  <div className="text-black text-xs font-mono font-bold uppercase mb-2">Today Focus</div>
                  <div className="text-3xl font-bold text-black font-mono mb-2">
                    {focusHoursToday.toFixed(1)} <span className="text-sm font-black">HR</span>
                  </div>
                  <div className="w-full bg-gray-200 h-3 border-2 border-black overflow-hidden relative">
                    <motion.div
                       className="h-full bg-cyan-400 border-r-2 border-black"
                       initial={{ width: 0 }}
                       animate={{ width: `${Math.min((focusHoursToday / 8) * 100, 100)}%` }} // Let's say 8 hours is 100%
                    />
                  </div>
                </div>
                <div className="bg-white border-[4px] border-black shadow-[4px_4px_0_#000] p-4 text-center">
                  <div className="text-black text-xs font-mono font-bold uppercase mb-2">Week Focus</div>
                  <div className="text-3xl font-bold text-black font-mono mb-2">
                    {focusHoursWeek.toFixed(1)} <span className="text-sm font-black">HR</span>
                  </div>
                  <div className="w-full bg-gray-200 h-3 border-2 border-black overflow-hidden relative">
                    <motion.div
                       className="h-full bg-cyan-400 border-r-2 border-black"
                       initial={{ width: 0 }}
                       animate={{ width: `${Math.min((focusHoursWeek / 40) * 100, 100)}%` }} // Say 40 hours is full bar
                    />
                  </div>
                </div>
                <div className="bg-white border-[4px] border-black shadow-[4px_4px_0_#000] p-4 text-center col-span-2">
                  <div className="text-black text-xs font-mono font-bold uppercase mb-2 text-red-500">Distraction Chain</div>
                  <div className="text-3xl font-bold text-red-500 font-mono mb-2">
                    {distractionChain} <span className="text-sm font-black">X COMBO</span>
                  </div>
                </div>
              </div>
              <div className="bg-white border-[4px] border-black shadow-[4px_4px_0_#000] p-4 flex flex-col items-center">
                 <div className="text-black text-xs font-mono font-bold uppercase mb-4 text-center w-full">Daily Distraction Trend</div>
                 <div className="w-full h-48 overflow-x-auto overflow-y-hidden scrollbar-thin scrollbar-thumb-black">
                   <div className="w-[600px] h-full pr-2 pb-2">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={distractionData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#ccc" />
                          <XAxis dataKey="time" stroke="#000" tick={{ fill: '#000', fontSize: 10, fontFamily: 'monospace' }} interval={0} />
                          <YAxis stroke="#000" tick={{ fill: '#000', fontSize: 10, fontFamily: 'monospace' }} allowDecimals={false} />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#fff', border: '3px solid #000', borderRadius: '8px', boxShadow: '4px 4px 0 #000', fontFamily: 'monospace', fontSize: '12px' }}
                            itemStyle={{ color: '#ef4444', fontWeight: 'bold' }}
                          />
                          <Area type="monotone" dataKey="distractions" stroke="#ef4444" fill="#fca5a5" strokeWidth={3} />
                        </AreaChart>
                      </ResponsiveContainer>
                   </div>
                 </div>
              </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'settings' && (
            <motion.div
              key="settings"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 p-6 bg-white overflow-y-auto scrollbar-thin scrollbar-thumb-black"
            >
              <div className="flex flex-col gap-6 min-h-max pb-4">
                <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-black text-xs font-mono font-bold uppercase">Pet Name</label>
                  <div className="flex gap-2">
                      <input
                        type="text"
                        value={petName}
                        onChange={(e) => {
                          setPetName(e.target.value);
                        }}
                        onBlur={(e) => {
                          const finalName = e.target.value.trim();
                          if (finalName === '') {
                            const oldName = localStorage.getItem('petName') || 'Pomo';
                            setPetName(oldName);
                            alert('Tên thú cưng không được để trống!');
                          } else {
                            handleUpdateName(finalName);
                          }
                        }}
                        className="flex-1 bg-white border-[3px] border-black px-3 py-2 text-black font-mono font-bold text-sm outline-none focus:bg-cyan-50 uppercase"
                      />
                  </div>
                </div>

                <div className="space-y-2">
                    <button onClick={handleResetApp} className="w-full bg-red-500 text-white font-mono font-bold py-2 border-[3px] border-black hover:bg-red-600">
                        RESET APP
                    </button>
                </div>

                <div className="space-y-2">
                  <label className="text-black text-xs font-mono font-bold uppercase">AI Service</label>
                  <div className="grid grid-cols-2 gap-2">
                    {([
                      { id: 'openai', label: '⚡ OpenAI' },
                      { id: 'gemini', label: '✦ Gemini' },
                    ] as const).map((provider) => (
                      <button
                        key={provider.id}
                        type="button"
                        onClick={() => {
                          setAiProvider(provider.id);
                          setApiKey('');
                          setApiKeyStatus(null);
                        }}
                        className={`border-[3px] border-black px-3 py-2 font-mono text-xs font-black uppercase shadow-[2px_2px_0_#000] transition-all active:translate-x-[2px] active:translate-y-[2px] active:shadow-none ${
                          aiProvider === provider.id ? 'bg-cyan-400' : 'bg-white hover:bg-cyan-50'
                        }`}
                      >
                        {provider.label}
                      </button>
                    ))}
                  </div>
                  <div className="border-[3px] border-black bg-cyan-50 p-3 font-mono">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="text-[10px] font-black uppercase">
                        {aiProvider === 'gemini' ? 'Gemini API Key' : 'OpenAI API Key'}
                      </span>
                      <span className={`text-[9px] font-black ${configuredProviders[aiProvider] ? 'text-green-700' : 'text-gray-500'}`}>
                        {configuredProviders[aiProvider] ? '● CONFIGURED' : '○ NOT SET'}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value={apiKey}
                        onChange={(event) => setApiKey(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            void saveProviderKey();
                          }
                        }}
                        minLength={8}
                        autoComplete="off"
                        placeholder="PASTE KEY..."
                        className="min-w-0 flex-1 border-2 border-black bg-white px-2 py-1.5 text-xs font-bold outline-none focus:bg-cyan-100"
                      />
                      <button
                        type="button"
                        onClick={() => void saveProviderKey()}
                        disabled={apiKey.trim().length < 8 || isSavingApiKey}
                        className="border-2 border-black bg-black px-3 py-1.5 text-[10px] font-black text-white disabled:opacity-40"
                      >
                        {isSavingApiKey ? 'SAVING' : 'SAVE'}
                      </button>
                    </div>
                    <p className="mt-2 text-[9px] text-gray-600">
                      Electron encrypts keys with the OS secure store. Browser dev keeps them in backend memory only.
                    </p>
                    {apiKeyStatus && (
                      <p className="mt-1 text-[9px] font-black text-cyan-700">{apiKeyStatus}</p>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-black text-xs font-mono font-bold uppercase block">Automatic Distraction Tracking</label>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={autoDistractionEnabled}
                    onClick={() => onAutoDistractionEnabledChange(!autoDistractionEnabled)}
                    className={`w-full border-[3px] border-black py-2 font-mono font-black shadow-[2px_2px_0_#000] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all ${
                      autoDistractionEnabled ? 'bg-green-400 text-black' : 'bg-gray-300 text-gray-700'
                    }`}
                  >
                    {autoDistractionEnabled ? 'AUTO TRACKING: ON' : 'AUTO TRACKING: OFF'}
                  </button>
                  <p className="text-[9px] font-mono text-gray-600">
                    Detects distracting apps after 10 seconds and idle time after 60 seconds. Window titles are never stored.
                  </p>
                </div>

                <RelationshipMemories />
                <ProactiveTracePanel onEvaluateNow={onEvaluateProactiveNow} />

                <div className="space-y-2">
                  <label className="text-black text-xs font-mono font-bold uppercase block">Simulate Distraction</label>
                  <button
                     onClick={onSimulateDistraction}
                     className="w-full bg-red-400 hover:bg-red-500 text-white font-mono font-bold border-[3px] border-black py-2 shadow-[2px_2px_0_#000] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all"
                   >
                      TEST DISTRACTION PENALTY (+5 MINS)
                  </button>
                </div>
              </div>
              <div className="space-y-2 flex-1">
                <label className="text-black text-xs font-mono font-bold uppercase">Test Emotions</label>
                <div className="grid grid-cols-4 gap-2">
                  {(['idle', 'happy', 'excited', 'worried', 'sad', 'sleepy', 'thinking', 'angry'] as Emotion[]).map((e) => (
                    <button
                      key={e}
                      onClick={() => setEmotion(e)}
                      className={`py-2 px-1 text-xs font-mono font-bold transition-all capitalize border-[2px] border-black shadow-[2px_2px_0_#000] active:shadow-none active:translate-x-[2px] active:translate-y-[2px] ${
                        emotion === e
                          ? 'bg-cyan-400 text-black'
                          : 'bg-white text-black hover:bg-gray-100'
                      }`}
                    >
                      {e}
                    </button>
                  ))}
                </div>
               </div>
               <button
                 type="button"
                 onClick={downloadLogs}
                 className="w-full mt-4 py-2 px-3 text-[10px] font-mono font-bold border-[2px] border-black shadow-[2px_2px_0_#000] active:shadow-none active:translate-x-[2px] active:translate-y-[2px] bg-amber-400 text-black hover:bg-amber-300 uppercase leading-tight"
               >
                 📥 Download System Logs (.TXT)
               </button>
               <p className="text-xs text-black font-mono font-bold mt-4 text-center pt-4 border-t-2 border-dashed border-gray-300 uppercase">
                  EMO.OS v1.0.5 <br/>
                  AI STUDIO SYSTEM
               </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
