import React, { useState, useEffect } from 'react'
import './TaskList.css'

interface Task {
  id: string
  name: string
  priority: 'high' | 'medium' | 'low'
  deadline: string
}

const TaskList: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([])
  const [showForm, setShowForm] = useState(false)
  const [newTask, setNewTask] = useState({
    name: '',
    priority: 'medium' as 'high' | 'medium' | 'low',
    deadline: ''
  })

  useEffect(() => {
    loadTasks()
  }, [])

  const loadTasks = async () => {
    const data = await window.electronAPI?.getTasks()
    if (data) setTasks(data)
  }

  const handleCreateTask = async () => {
    await window.electronAPI?.createTask(newTask)
    setNewTask({ name: '', priority: 'medium', deadline: '' })
    setShowForm(false)
    loadTasks()
  }

  const handleDeleteTask = async (id: string) => {
    await window.electronAPI?.deleteTask(id)
    loadTasks()
  }

  const handleStartSession = async (taskId: string) => {
    const duration = prompt('Enter session duration (minutes):', '25')
    if (duration) {
      await window.electronAPI?.startSession(taskId, parseInt(duration) * 60)
    }
  }

  return (
    <div className="task-list">
      <div className="task-header">
        <h2>Tasks</h2>
        <button onClick={() => setShowForm(!showForm)}>+ New Task</button>
      </div>

      {showForm && (
        <div className="task-form">
          <input
            type="text"
            placeholder="Task name"
            value={newTask.name}
            onChange={(e) => setNewTask({ ...newTask, name: e.target.value })}
          />
          <select
            value={newTask.priority}
            onChange={(e) => setNewTask({ ...newTask, priority: e.target.value as any })}
          >
            <option value="high">High Priority</option>
            <option value="medium">Medium Priority</option>
            <option value="low">Low Priority</option>
          </select>
          <input
            type="date"
            value={newTask.deadline}
            onChange={(e) => setNewTask({ ...newTask, deadline: e.target.value })}
          />
          <button onClick={handleCreateTask}>Create</button>
          <button onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      )}

      <div className="tasks">
        {tasks.map((task) => (
          <div key={task.id} className={`task-item priority-${task.priority}`}>
            <div className="task-info">
              <h3>{task.name}</h3>
              <p>Deadline: {task.deadline}</p>
            </div>
            <div className="task-actions">
              <button onClick={() => handleStartSession(task.id)}>Start</button>
              <button onClick={() => handleDeleteTask(task.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default TaskList
