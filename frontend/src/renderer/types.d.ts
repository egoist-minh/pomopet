declare global {
  interface Window {
    electronAPI?: {
      // Session controls
      startSession: (taskId: string, duration: number) => Promise<any>
      pauseSession: () => Promise<any>
      resumeSession: () => Promise<any>
      cancelSession: () => Promise<any>
      extendSession: (minutes: number) => Promise<any>

      // Task management
      getTasks: () => Promise<any>
      createTask: (task: any) => Promise<any>
      deleteTask: (id: string) => Promise<any>
      completeTask: (id: string) => Promise<any>

      // Chat
      sendMessage: (message: string) => Promise<any>

      // Statistics
      getStatistics: () => Promise<any>

      // Event listeners
      onSessionUpdate: (callback: (data: any) => void) => void
      onPetEmotion: (callback: (emotion: string) => void) => void
    }
  }
}

export {}
