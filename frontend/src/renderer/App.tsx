import React from 'react'
import MainWindow from './components/MainWindow/MainWindow'
import PetWidget from './components/PetWidget/PetWidget'

function App() {
  const isPetWidget = window.location.pathname === '/widget'

  return (
    <div className="App">
      {isPetWidget ? <PetWidget /> : <MainWindow />}
    </div>
  )
}

export default App
