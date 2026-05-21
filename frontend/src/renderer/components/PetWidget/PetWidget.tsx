import React, { useState, useEffect } from 'react'
import './PetWidget.css'

interface PetWidgetProps {}

const PetWidget: React.FC<PetWidgetProps> = () => {
  const [emotion, setEmotion] = useState('happy')
  const [timeLeft, setTimeLeft] = useState(0)
  const [isRunning, setIsRunning] = useState(false)

  useEffect(() => {
    // Listen for pet emotion changes
    window.electronAPI?.onPetEmotion((newEmotion: string) => {
      setEmotion(newEmotion)
    })

    // Listen for session updates
    window.electronAPI?.onSessionUpdate((data: any) => {
      setTimeLeft(data.timeLeft)
      setIsRunning(data.isRunning)
    })
  }, [])

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="pet-widget">
      <div className="pet-face">
        {/* TODO: Add Lottie animation based on emotion */}
        <div className="pet-emotion">{emotion}</div>
      </div>
      <div className="timer">
        {isRunning ? formatTime(timeLeft) : '--:--'}
      </div>
    </div>
  )
}

export default PetWidget
