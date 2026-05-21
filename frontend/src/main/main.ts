import { app, BrowserWindow, Tray, Menu } from 'electron'
import path from 'path'

let mainWindow: BrowserWindow | null = null
let petWidget: BrowserWindow | null = null
let tray: Tray | null = null

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:3000')
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
  }
}

function createPetWidget() {
  petWidget = new BrowserWindow({
    width: 200,
    height: 250,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  if (process.env.NODE_ENV === 'development') {
    petWidget.loadURL('http://localhost:3000/widget')
  } else {
    petWidget.loadFile(path.join(__dirname, '../renderer/widget.html'))
  }
}

function createTray() {
  // TODO: Add tray icon
  tray = new Tray(path.join(__dirname, '../../assets/icon.png'))
  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show Main Window', click: () => mainWindow?.show() },
    { label: 'Show Pet', click: () => petWidget?.show() },
    { label: 'Quit', click: () => app.quit() }
  ])
  tray.setContextMenu(contextMenu)
}

app.whenReady().then(() => {
  createMainWindow()
  createPetWidget()
  createTray()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
