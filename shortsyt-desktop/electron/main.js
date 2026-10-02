const { app, BrowserWindow, ipcMain, shell, Menu, dialog } = require('electron');
const path = require('path');
const http = require('http');
const fs = require('fs');
const { spawn } = require('child_process');

// File logger to diagnose startup
const logPath = path.join(path.resolve(__dirname, '../..'), 'electron_debug.log');
function logDebug(msg) {
  try {
    fs.appendFileSync(logPath, `[${new Date().toISOString()}] ${msg}\n`);
  } catch (_) {}
}
logDebug('--- Electron main process starting ---');

process.on('uncaughtException', (err) => {
  logDebug('CRITICAL uncaughtException: ' + (err.stack || err));
});
process.on('unhandledRejection', (reason) => {
  logDebug('CRITICAL unhandledRejection: ' + ((reason && reason.stack) || reason));
});

const Store = require('electron-store');

// Initialize electron store
const store = new Store({
  defaults: {
    api_url: 'http://localhost:8765',
    jwt_token: null,
  },
});

let mainWindow = null;

let backendProcess = null;
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

function isBackendRunning(port = 8765) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureBackendRunning() {
  const isUp = await isBackendRunning(8765);
  if (isUp) {
    console.log('✅ Backend API is already running on port 8765');
    return;
  }

  // Find python in venv across common dev and packaged locations
  const candidateVenvs = [
    path.join(process.cwd(), 'venv313', 'Scripts', 'python.exe'),
    path.resolve(__dirname, '../../venv313/Scripts/python.exe'),
    path.resolve(__dirname, '../../../venv313/Scripts/python.exe'),
    path.resolve(__dirname, '../../../../venv313/Scripts/python.exe'),
    path.join(process.env.USERPROFILE || '', 'PycharmProjects', 'shortsyt', 'venv313', 'Scripts', 'python.exe'),
  ];

  let pythonCmd = 'python';
  let projectRoot = path.resolve(__dirname, '../..');
  for (const candidate of candidateVenvs) {
    if (fs.existsSync(candidate)) {
      pythonCmd = candidate;
      projectRoot = path.dirname(path.dirname(path.dirname(candidate)));
      break;
    }
  }

  console.log('🚀 Starting Shortsyt Backend API via:', pythonCmd, 'in cwd:', projectRoot);
  try {
    backendProcess = spawn(pythonCmd, ['-m', 'uvicorn', 'lol_agent.api.main:app', '--host', '127.0.0.1', '--port', '8765'], {
      cwd: projectRoot,
      stdio: 'ignore',
      detached: false,
      windowsHide: true,
    });

    backendProcess.on('error', (err) => {
      console.warn('Backend process spawn error:', err);
    });

    // Wait briefly for backend to initialize
    for (let i = 0; i < 10; i++) {
      await new Promise((r) => setTimeout(r, 600));
      if (await isBackendRunning(8765)) {
        console.log('✅ Backend API started successfully');
        break;
      }
    }
  } catch (err) {
    console.warn('Could not auto-start backend:', err);
  }
}

async function createWindow() {
  logDebug('createWindow() called');
  await ensureBackendRunning();
  logDebug('ensureBackendRunning finished');

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

  // Graceful show + safety timeout fallback
  mainWindow.once('ready-to-show', () => {
    logDebug('mainWindow ready-to-show event fired');
    mainWindow.show();
  });
  setTimeout(() => {
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible()) {
      logDebug('Safety timeout: forcing mainWindow.show()');
      mainWindow.show();
    }
  }, 1200);

  const viteUp = await isViteRunning(5173);
  logDebug(`isViteRunning: ${viteUp}, isDev: ${isDev}`);

  if (isDev && viteUp) {
    logDebug('Loading http://localhost:5173');
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    const indexPath = path.join(__dirname, '../dist/index.html');
    logDebug(`Loading local file: ${indexPath}, exists: ${fs.existsSync(indexPath)}`);
    mainWindow.loadFile(indexPath).catch((err) => {
      logDebug('Fallback loading error: ' + (err.stack || err));
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

ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Wybierz folder z nagraniami / klipami (np. Outplayed / Medal)',
  });
  if (result.canceled || !result.filePaths || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
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

app.on('before-quit', () => {
  if (backendProcess && backendProcess.pid) {
    try {
      if (process.platform === 'win32') {
        const { execSync } = require('child_process');
        execSync(`taskkill /pid ${backendProcess.pid} /T /F`, { stdio: 'ignore' });
      } else {
        backendProcess.kill();
      }
    } catch (_) {
      try { backendProcess.kill(); } catch (__) {}
    }
  }
});
