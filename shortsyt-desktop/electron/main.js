const { app, BrowserWindow, ipcMain, shell, Menu } = require('electron');
const path = require('path');
const http = require('http');
const Store = require('electron-store');

// Initialize electron store
const store = new Store({
  defaults: {
    api_url: 'http://localhost:8765',
    jwt_token: null,
  },
});

let mainWindow = null;
const isDev = process.env.NODE_ENV === 'development';

function isViteRunning(port = 5173) {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${port}`, (res) => {
      resolve(res.statusCode === 200 || res.statusCode === 304);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(800, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 1080,
    minHeight: 720,
    title: 'Shortsyt Desktop — LoL Shorts Studio',
    backgroundColor: '#0A0E1A',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
    },
  });

  // Remove default menu in production or customize
  if (!isDev) {
    Menu.setApplicationMenu(null);
  }

  // Graceful show
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  const viteUp = await isViteRunning(5173);

  if (isDev && viteUp) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    const indexPath = path.join(__dirname, '../dist/index.html');
    mainWindow.loadFile(indexPath).catch((err) => {
      console.warn('Fallback loading error:', err);
    });
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── IPC Handlers for Store ─────────────────────────────────────────────────
ipcMain.handle('store-get', (event, key, defaultValue) => {
  return store.get(key, defaultValue);
});

ipcMain.handle('store-set', (event, key, value) => {
  store.set(key, value);
  return true;
});

ipcMain.handle('store-delete', (event, key) => {
  store.delete(key);
  return true;
});

ipcMain.handle('store-clear', () => {
  store.clear();
  return true;
});

ipcMain.handle('app-version', () => {
  return app.getVersion();
});

ipcMain.handle('open-external', (event, url) => {
  return shell.openExternal(url);
});

ipcMain.handle('show-item-in-folder', (event, fullPath) => {
  if (fullPath) {
    shell.showItemInFolder(fullPath);
  }
  return true;
});

ipcMain.handle('open-path', (event, fullPath) => {
  if (fullPath) {
    shell.openPath(fullPath);
  }
  return true;
});

// ── App Lifecycle ──────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
