'use client';

import { motion, AnimatePresence, useDragControls } from 'motion/react';
import { X, Minus, MessageSquare, CheckSquare, BarChart2, Settings, Send, Play, Trash2 } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { Emotion, SessionState } from './FloatingPet';
import { Task } from './DesktopEnvironment';
import dynamic from 'next/dynamic';

const AreaChart = dynamic(() => import('recharts').then((mod) => mod.AreaChart), { ssr: false });
const Area = dynamic(() => import('recharts').then((mod) => mod.Area), { ssr: false });
const XAxis = dynamic(() => import('recharts').then((mod) => mod.XAxis), { ssr: false });
const YAxis = dynamic(() => import('recharts').then((mod) => mod.YAxis), { ssr: false });
const CartesianGrid = dynamic(() => import('recharts').then((mod) => mod.CartesianGrid), { ssr: false });
const ResponsiveContainer = dynamic(() => import('recharts').then((mod) => mod.ResponsiveContainer), { ssr: false });
const Tooltip = dynamic(() => import('recharts').then((mod) => mod.Tooltip), { ssr: false });

interface MainWindowProps {
  isOpen: boolean;
  onClose: () => void;
  onMinimize: () => void;
  petName: string;
  setPetName: (name: string) => void;
  emotion: Emotion;
  setEmotion: (emotion: Emotion) => void;
  chatMessages: { role: 'user' | 'pet'; text: string }[];
  onSendMessage: (msg: string) => void;
  activeTab: 'chat' | 'tasks' | 'stats' | 'settings';
  setActiveTab: (tab: 'chat' | 'tasks' | 'stats' | 'settings') => void;
  isDesktopMode: boolean;
  setIsDesktopMode: (mode: boolean) => void;
  tasks: Task[];
  setTasks: (tasks: Task[]) => void;
  focusHoursToday: number;
  focusHoursWeek: number;
  sessionsCompleted: number;
  onStartSession: (task: Task, durationMinutes: number) => void;
  sessionState: SessionState;
  distractionChain: number;
  distractionData: { time: string, distractions: number }[];
  onSimulateDistraction: () => void;
}

export default function MainWindow({
  isOpen,
  onClose,
  onMinimize,
  petName,
  setPetName,
  emotion,
  setEmotion,
  chatMessages,
  onSendMessage,
  activeTab,
  setActiveTab,
  isDesktopMode,
  setIsDesktopMode,
  tasks,
  setTasks,
  focusHoursToday,
  focusHoursWeek,
  sessionsCompleted,
  onStartSession,
  sessionState,
  distractionChain,
  distractionData,
  onSimulateDistraction,
}: MainWindowProps) {
  const dragControls = useDragControls();
  const [chatInput, setChatInput] = useState('');
  
  // New Task Form States
  const [newTaskName, setNewTaskName] = useState('');
  const [newTaskPriority, setNewTaskPriority] = useState<'high' | 'medium' | 'low'>('medium');
  const [newTaskDeadline, setNewTaskDeadline] = useState('');

  const lastMessageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activeTab === 'chat' && lastMessageRef.current) {
      lastMessageRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, activeTab]);

  const handleChatSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    onSendMessage(chatInput.trim());
    setChatInput('');
  };

  const addTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskName.trim()) return;
    setTasks([...tasks, { 
      id: Date.now().toString(), 
      name: newTaskName.trim(), 
      priority: newTaskPriority,
      deadline: newTaskDeadline,
      completed: false 
    }]);
    setNewTaskName('');
    setNewTaskDeadline('');
  };

  const toggleTask = (id: string) => {
    setTasks(tasks.map((t) => (t.id === id ? { ...t, completed: !t.completed } : t)).filter(t => !t.completed)); // auto delete completed for MVP
  };

  const deleteTask = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setTasks(tasks.filter(t => t.id !== id));
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'bg-red-400';
      case 'medium': return 'bg-orange-400';
      case 'low': return 'bg-green-400';
      default: return 'bg-gray-400';
    }
  };

  if (!isOpen) return null;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: 20 }}
      className="absolute top-24 left-8 sm:left-24 w-full max-w-sm sm:max-w-md bg-white border-[4px] border-black shadow-[8px_8px_0_#000] flex flex-col z-30 pointer-events-auto rounded-xl overflow-hidden"
      drag
      dragControls={dragControls}
      dragListener={false}
      dragMomentum={false}
    >
      {/* Title Bar - Classic Mac OS style */}
      <div 
        className="bg-black p-2 px-3 flex items-center justify-between cursor-move select-none"
        onPointerDown={(e) => dragControls.start(e)}
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
          <button onClick={onMinimize} className="p-1 bg-white border-2 border-black hover:bg-cyan-400 transition-colors">
            <Minus className="w-3 h-3 text-black" strokeWidth={3} />
          </button>
          <button onClick={onClose} className="p-1 bg-white border-2 border-black hover:bg-cyan-400 transition-colors">
            <X className="w-3 h-3 text-black" strokeWidth={3} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b-[4px] border-black bg-white">
        {[
          { id: 'chat', icon: MessageSquare, label: 'Chat' },
          { id: 'tasks', icon: CheckSquare, label: 'Tasks' },
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

      {/* Content Area */}
      <div className="h-80 relative bg-gray-100">
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
                  <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
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
                  className="flex-1 bg-white border-[3px] border-black px-3 py-2 text-black font-mono text-xs font-bold outline-none focus:bg-cyan-50 placeholder:text-gray-400"
                />
                <button
                  type="submit"
                  disabled={!chatInput.trim()}
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
              className="absolute inset-0 flex flex-col p-4"
            >
              <div className="flex-1 overflow-y-auto flex flex-col gap-3 pr-1 scrollbar-thin scrollbar-thumb-black">
                {tasks.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-gray-500 text-sm font-mono text-center font-bold px-4">
                    NO TASKS FOUND. ADD SOME GOALS TO FEED {petName.toUpperCase()}.
                  </div>
                ) : (
                  tasks.map((task) => (
                    <div
                      key={task.id}
                      onClick={() => toggleTask(task.id)}
                      className="group flex flex-col gap-1 p-3 bg-white border-[3px] border-black shadow-[2px_2px_0_#000] hover:bg-cyan-50 cursor-pointer transition-colors relative"
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-5 h-5 border-[3px] border-black flex items-center justify-center transition-colors ${task.completed ? 'bg-cyan-400' : 'bg-white'}`}>
                          {task.completed && <CheckSquare className="w-4 h-4 text-black" strokeWidth={3} />}
                        </div>
                        <span className={`text-sm flex-1 font-mono font-bold transition-all ${task.completed ? 'text-gray-400 line-through' : 'text-black'}`}>
                          {task.name}
                        </span>
                        
                        {/* Task Actions */}
                        <div className="flex items-center gap-1">
                           <button 
                             onClick={(e) => { e.stopPropagation(); onStartSession(task, 25); }} 
                             disabled={sessionState !== 'idle' || task.completed}
                             className="p-1 border-[2px] border-black bg-cyan-400 hover:bg-cyan-300 disabled:opacity-50"
                             title="Start 25m Session"
                           >
                              <Play className="w-3 h-3 text-black" />
                           </button>
                           <button 
                             onClick={(e) => deleteTask(task.id, e)} 
                             className="p-1 border-[2px] border-black bg-red-400 hover:bg-red-500"
                             title="Delete"
                           >
                              <Trash2 className="w-3 h-3 text-black" />
                           </button>
                        </div>
                      </div>
                      
                      {/* Priority & Deadline Badges */}
                      <div className="pl-8 flex gap-2">
                        <div className={`px-1.5 py-0.5 text-[10px] font-mono font-black uppercase text-black border-2 border-black ${getPriorityColor(task.priority)}`}>
                          {task.priority}
                        </div>
                        {task.deadline && (
                           <div className="px-1.5 py-0.5 text-[10px] font-mono font-black text-black border-2 border-black bg-yellow-200">
                             {task.deadline}
                           </div>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
              
              {/* Add Task Form */}
              <form onSubmit={addTask} className="mt-4 flex flex-col gap-2 bg-white border-[3px] border-black p-2 shadow-[2px_2px_0_#000]">
                <input
                  type="text"
                  value={newTaskName}
                  onChange={(e) => setNewTaskName(e.target.value)}
                  placeholder="NEW TASK NAME..."
                  className="w-full bg-gray-100 border-2 border-black px-2 py-1 text-black font-mono font-bold text-xs outline-none focus:bg-cyan-50 uppercase placeholder:text-gray-400"
                />
                <div className="flex gap-2">
                  <select 
                    value={newTaskPriority} 
                    onChange={(e) => setNewTaskPriority(e.target.value as any)}
                    className="flex-1 bg-gray-100 border-2 border-black px-1 py-1 text-black font-mono font-bold text-[10px] uppercase outline-none"
                  >
                    <option value="high">HIGH PRIORITY</option>
                    <option value="medium">MEDIUM PRIORITY</option>
                    <option value="low">LOW PRIORITY</option>
                  </select>
                  <input
                    type="date"
                    value={newTaskDeadline}
                    onChange={(e) => setNewTaskDeadline(e.target.value)}
                    className="flex-1 bg-gray-100 border-2 border-black px-1 py-1 text-black font-mono font-bold text-[10px] outline-none"
                  />
                  <button
                    type="submit"
                    disabled={!newTaskName.trim()}
                    className="bg-black hover:bg-gray-800 disabled:opacity-50 text-white px-3 py-1 border-2 border-black font-mono text-[10px] font-bold transition-colors"
                  >
                    ADD
                  </button>
                </div>
              </form>
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
                        onChange={(e) => setPetName(e.target.value)}
                        className="flex-1 bg-white border-[3px] border-black px-3 py-2 text-black font-mono font-bold text-sm outline-none focus:bg-cyan-50 uppercase"
                      />
                  </div>
                </div>
                
                <div className="space-y-2">
                  <label className="text-black text-xs font-mono font-bold uppercase flex items-center justify-between cursor-pointer border-[3px] border-black p-2 hover:bg-cyan-50" onClick={() => setIsDesktopMode(!isDesktopMode)}>
                     <span>Pure Transparent Mode (For Electron/Real Desktop)</span>
                     <div className={`w-8 h-4 border-2 border-black flex items-center px-0.5 ${isDesktopMode ? 'bg-cyan-400' : 'bg-gray-300'}`}>
                        <motion.div animate={{ x: isDesktopMode ? 14 : 0 }} className="w-3 h-3 bg-white border-2 border-black shadow-sm" />
                     </div>
                  </label>
                  <p className="text-[10px] text-gray-500 font-mono">Turn this on when exporting as an Electron app to remove the mock UI background.</p>
                </div>
                
                <div className="space-y-2">
                  <label className="text-black text-xs font-mono font-bold uppercase block">Simulate Distraction</label>
                  <button 
                     onClick={onSimulateDistraction}
                     className="w-full bg-red-400 hover:bg-red-500 text-white font-mono font-bold border-[3px] border-black py-2 shadow-[2px_2px_0_#000] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all"
                  >
                     TEST DISTRACTION PENALTY (+5 MINS)
                  </button>
                  <p className="text-[10px] text-gray-500 font-mono">Simulates app detection feature for Phase 2. Gets pet angry if session is running.</p>
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
