import React, { useState, useEffect } from 'react'
import TaskList from '../TaskList/TaskList'
import ChatInterface from '../ChatInterface/ChatInterface'
import './MainWindow.css'

const MainWindow: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'tasks' | 'stats' | 'chat'>('tasks')
  const [stats, setStats] = useState({ focusHoursToday: 0 })

  useEffect(() => {
    loadStatistics()
  }, [])

  const loadStatistics = async () => {
    const data = await window.electronAPI?.getStatistics()
    if (data) setStats(data)
  }

  return (
    <div className="main-window">
      <header className="header">
        <h1>PomoPet</h1>
        <div className="tabs">
          <button 
            className={activeTab === 'tasks' ? 'active' : ''} 
            onClick={() => setActiveTab('tasks')}
          >
            Tasks
          </button>
          <button 
            className={activeTab === 'stats' ? 'active' : ''} 
            onClick={() => setActiveTab('stats')}
          >
            Statistics
          </button>
          <button 
            className={activeTab === 'chat' ? 'active' : ''} 
            onClick={() => setActiveTab('chat')}
          >
            Chat
          </button>
        </div>
      </header>

      <main className="content">
        {activeTab === 'tasks' && <TaskList />}
        {activeTab === 'stats' && (
          <div className="stats">
            <h2>Today's Focus Time</h2>
            <div className="stat-value">{stats.focusHoursToday.toFixed(1)} hours</div>
          </div>
        )}
        {activeTab === 'chat' && <ChatInterface />}
      </main>
    </div>
  )
}

export default MainWindow
