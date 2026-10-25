const { contextBridge, ipcRenderer } = require('electron');

const roleArgument = process.argv.find(argument => argument.startsWith('--pomopet-window-role='));
const windowRole = roleArgument?.split('=', 2)[1] === 'pet' ? 'pet' : 'main';

contextBridge.exposeInMainWorld('electron', {
  windowRole,
  getRuntimeConfig: () => ipcRenderer.invoke('runtime:get-config'),
  supportsWindowRegions: process.platform === 'win32' || process.platform === 'linux',
  setWindowRegions: regions => {
    ipcRenderer.send('set-window-regions', regions);
  },
  setIgnoreMouseEvents: (ignore, options) => {
    ipcRenderer.send('set-ignore-mouse-events', ignore, options);
  },
  getPetState: () => ipcRenderer.invoke('pet-state:get'),
  publishPetState: state => ipcRenderer.send('pet-state:publish', state),
  onPetState: callback => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('pet-state:update', listener);
    return () => ipcRenderer.removeListener('pet-state:update', listener);
  },
  onPetDragState: callback => {
    const listener = (_event, isDragging) => callback(isDragging === true);
    ipcRenderer.on('pet-window:drag-state', listener);
    return () => ipcRenderer.removeListener('pet-window:drag-state', listener);
  },
  setPetChaseSuspended: (suspended, keepWindowVisible = false) => {
    ipcRenderer.send('pet-cursor-chase:set-suspended', suspended, keepWindowVisible);
  },
  onPetChaseState: callback => {
    const listener = (_event, isChasing) => callback(isChasing === true);
    ipcRenderer.on('pet-cursor-chase:state', listener);
    return () => ipcRenderer.removeListener('pet-cursor-chase:state', listener);
  },
  onPetChaseBump: callback => {
    const listener = () => callback();
    ipcRenderer.on('pet-cursor-chase:bump', listener);
    return () => ipcRenderer.removeListener('pet-cursor-chase:bump', listener);
  },
  pokePet: () => ipcRenderer.send('pet-cursor-chase:poke'),
  sendPetAction: action => ipcRenderer.send('pet-action:send', action),
  onPetAction: callback => {
    const listener = (_event, action) => callback(action);
    ipcRenderer.on('pet-action:receive', listener);
    return () => ipcRenderer.removeListener('pet-action:receive', listener);
  },
  setMainWindowVisible: visible => ipcRenderer.send('main-window:set-visible', visible),
  restoreApiKeys: () => ipcRenderer.invoke('api-key:restore'),
  setApiKey: (provider, apiKey) => ipcRenderer.invoke('api-key:set', provider, apiKey),
  onBackendStatus: callback => {
    const listener = (_event, status) => callback(status);
    ipcRenderer.on('backend:status', listener);
    return () => ipcRenderer.removeListener('backend:status', listener);
  },
  onGoodbyeRequested: callback => {
    const listener = () => callback();
    ipcRenderer.on('app:goodbye-request', listener);
    return () => ipcRenderer.removeListener('app:goodbye-request', listener);
  },
  notifyGoodbyeComplete: () => ipcRenderer.send('app:goodbye-complete'),
  configureDistractionTracking: settings => {
    ipcRenderer.send('distraction-tracking:configure', settings);
  },
  onAutoDistraction: callback => {
    const listener = (_event, distraction) => callback(distraction);
    ipcRenderer.on('distraction:recorded', listener);
    return () => ipcRenderer.removeListener('distraction:recorded', listener);
  },
});
