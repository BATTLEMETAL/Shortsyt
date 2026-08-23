const { contextBridge, ipcRenderer } = require('electron');

// Expose secure electronStore API
contextBridge.exposeInMainWorld('electronStore', {
  get: (key, defaultValue) => ipcRenderer.invoke('store-get', key, defaultValue),
  set: (key, value) => ipcRenderer.invoke('store-set', key, value),
  delete: (key) => ipcRenderer.invoke('store-delete', key),
  clear: () => ipcRenderer.invoke('store-clear'),
});

// Expose system / app info helpers
contextBridge.exposeInMainWorld('electronApp', {
  getVersion: () => ipcRenderer.invoke('app-version'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  showItemInFolder: (fullPath) => ipcRenderer.invoke('show-item-in-folder', fullPath),
  openPath: (fullPath) => ipcRenderer.invoke('open-path', fullPath),
});
