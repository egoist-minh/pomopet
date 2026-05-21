import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  // Session controls
  startSession: (taskId: string, duration: number) => 
    ipcRenderer.invoke('session:start', taskId, duration),
  pauseSession: () => ipcRenderer.invoke('session:pause'),
  resumeSession: () => ipcRenderer.invoke('session:resume'),
  cancelSession: () => ipcRenderer.invoke('session:cancel'),
  extendSession: (minutes: number) => 
    ipcRenderer.invoke('session:extend', minutes),

  // Task management
  getTasks: () => ipcRenderer.invoke('tasks:get'),
  createTask: (task: any) => ipcRenderer.invoke('tasks:create', task),
  deleteTask: (id: string) => ipcRenderer.invoke('tasks:delete', id),
  completeTask: (id: string) => ipcRenderer.invoke('tasks:complete', id),

  // Chat
  sendMessage: (message: string) => ipcRenderer.invoke('chat:send', message),

  // Statistics
  getStatistics: () => ipcRenderer.invoke('stats:get'),

  // Event listeners
  onSessionUpdate: (callback: (data: any) => void) => 
    ipcRenderer.on('session:update', (_event, data) => callback(data)),
  onPetEmotion: (callback: (emotion: string) => void) =>
    ipcRenderer.on('pet:emotion', (_event, emotion) => callback(emotion))
})
