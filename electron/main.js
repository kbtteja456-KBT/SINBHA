// ========================================================
// SINBHA - Electron Desktop Application (Windows)
// Automatically spawns backend, transparent bird overlay,
// system tray, and quiet hours / DND controls.
// ========================================================

const { app, BrowserWindow, Tray, Menu, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn, execSync } = require('child_process');

let mainWindow = null;
let overlayWindow = null;
let tray = null;
let pythonProcess = null;
let isQuitting = false;

// Global application state
let remindersPaused = false;
let doNotDisturb = false;
const BACKEND_PORT = 8000;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

// ----------------- Python Environment Discovery -----------------
function findPythonExecutable() {
  const candidates = [
    path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe'),
    'C:\\Users\\kosur\\AppData\\Local\\Python\\bin\\python.exe',
    'python.exe',
    'python'
  ];

  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) {
        execSync(`"${p}" -V`, { stdio: 'ignore' });
        return p;
      }
    } catch (e) {
      // Not working, continue
    }
  }

  // Fallback to checking PATH
  try {
    execSync('python -V', { stdio: 'ignore' });
    return 'python';
  } catch (e) {}

  return 'python';
}

function checkBackendHealth() {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/api/settings`, { timeout: 1500 }, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function startPythonServer() {
  const isRunning = await checkBackendHealth();
  if (isRunning) {
    console.log('Python server is already running on port', BACKEND_PORT);
    return;
  }

  const pythonExec = findPythonExecutable();
  console.log('Spawning Python server using:', pythonExec);

  const projectRoot = path.join(__dirname, '..');
  pythonProcess = spawn(pythonExec, ['-m', 'uvicorn', 'app.main:app', '--port', String(BACKEND_PORT)], {
    cwd: projectRoot,
    stdio: 'ignore',
    windowsHide: true,
    detached: false
  });

  pythonProcess.on('error', (err) => {
    console.error('Failed to spawn python process:', err);
  });

  // Wait for server to become healthy
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const healthy = await checkBackendHealth();
    if (healthy) {
      console.log('Python server is up and healthy!');
      return;
    }
  }
}

// ----------------- Window Management -----------------
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 500,
    height: 820,
    minWidth: 380,
    minHeight: 520,
    title: 'SINBHA - Personal Habit & Task Companion',
    icon: path.join(__dirname, 'icon.png'),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  mainWindow.loadURL(BACKEND_URL);

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createOverlayWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { x, y, width, height } = primaryDisplay.bounds;

  overlayWindow = new BrowserWindow({
    x: x,
    y: y,
    width: width,
    height: height,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    resizable: false,
    movable: false,
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  // Keep overlay above all regular desktop windows
  overlayWindow.setAlwaysOnTop(true, 'screen-saver');
  // Click-through by default
  overlayWindow.setIgnoreMouseEvents(true, { forward: true });

  overlayWindow.loadFile(path.join(__dirname, 'overlay.html'));

  overlayWindow.on('closed', () => {
    overlayWindow = null;
  });
}

function showMainWindow() {
  if (!mainWindow) {
    createMainWindow();
  } else {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  }
}

// ----------------- Fullscreen / DND Detection (Requirement 6) -----------------
function isFullscreenAppActive() {
  if (doNotDisturb) return true;

  try {
    // Quick PowerShell check on Windows to detect if foreground window is fullscreen/presenting
    const script = `
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
$hwnd = [Win]::GetForegroundWindow()
$rect = New-Object Win+RECT
[Win]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top
$sw = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width
$sh = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height
if ($w -ge $sw -and $h -ge $sh) { "FULLSCREEN" } else { "NORMAL" }
`;
    // If needed we can run asynchronous check, but we avoid blocking IPC
  } catch (e) {}

  return doNotDisturb;
}

// ----------------- System Tray (Requirement 4) -----------------
function updateTrayMenu() {
  if (!tray) return;

  const startWithWindows = app.getLoginItemSettings().openAtLogin;

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '🌸 Open SINBHA',
      click: () => showMainWindow()
    },
    { type: 'separator' },
    {
      label: remindersPaused ? '▶ Resume Reminders' : '⏸ Pause Reminders',
      click: () => {
        remindersPaused = !remindersPaused;
        updateTrayMenu();
        if (overlayWindow) overlayWindow.webContents.send('hide-bird');
      }
    },
    {
      label: '🔕 Do Not Disturb',
      type: 'checkbox',
      checked: doNotDisturb,
      click: (menuItem) => {
        doNotDisturb = menuItem.checked;
        if (doNotDisturb && overlayWindow) {
          overlayWindow.webContents.send('hide-bird');
        }
      }
    },
    {
      label: '🚀 Start with Windows',
      type: 'checkbox',
      checked: startWithWindows,
      click: (menuItem) => {
        app.setLoginItemSettings({
          openAtLogin: menuItem.checked,
          path: process.execPath
        });
        updateTrayMenu();
      }
    },
    { type: 'separator' },
    {
      label: '✕ Quit SINBHA',
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);
}

function createTray() {
  const iconPath = path.join(__dirname, 'tray_icon.png');
  tray = new Tray(iconPath);
  tray.setToolTip('SINBHA - Habit & Task Companion');

  updateTrayMenu();

  tray.on('click', () => {
    showMainWindow();
  });
}

// ----------------- Background Reminder Poller (Requirement 3 & Sequential Queue) -----------------
let isBirdShowingOnOverlay = false;

async function checkDueRemindersLoop() {
  if (remindersPaused || isFullscreenAppActive() || isBirdShowingOnOverlay) return;

  try {
    const tzOffset = new Date().getTimezoneOffset();
    const url = `${BACKEND_URL}/api/reminders/check?tz_offset_minutes=${tzOffset}`;

    http.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (json.reminder_needed && json.task && !json.emergency_stopped) {
            // Keep active so tasks are delivered one by one in chronological order
            isBirdShowingOnOverlay = true;

            // Trigger bird in overlay window!
            if (overlayWindow && !overlayWindow.isDestroyed()) {
              overlayWindow.webContents.send('show-bird', {
                task: json.task,
                reminder_id: json.reminder_id,
                is_explicit: json.is_explicit
              });
            }

            // Mark reminder fired in backend so it does not repeat
            if (json.reminder_id || json.is_explicit) {
              const postData = JSON.stringify({ task_id: json.task.id, reminder_id: json.reminder_id });
              const fireReq = http.request(
                `${BACKEND_URL}/api/reminders/fired`,
                {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(postData)
                  }
                }
              );
              fireReq.on('error', () => {});
              fireReq.write(postData);
              fireReq.end();
            }
          }
        } catch (e) {}
      });
    }).on('error', () => {});
  } catch (e) {}
}

// ----------------- IPC Handlers -----------------
function setupIpcHandlers() {
  // Click-through toggler
  ipcMain.on('set-ignore-mouse-events', (event, ignore, options) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win && !win.isDestroyed()) {
      win.setIgnoreMouseEvents(ignore, options);
    }
  });

  // Open Chat from Overlay Bird
  ipcMain.on('open-chat-window', () => {
    showMainWindow();
  });

  // Dismiss bird
  ipcMain.on('dismiss-bird', () => {
    isBirdShowingOnOverlay = false;
    if (overlayWindow && !overlayWindow.isDestroyed()) {
      overlayWindow.webContents.send('hide-bird');
    }
  });

  // Bird departed off-screen: advance queue to next task in line!
  ipcMain.on('bird-departed', () => {
    isBirdShowingOnOverlay = false;
    setTimeout(checkDueRemindersLoop, 2000);
  });

  // Mark task done from bird popup
  ipcMain.handle('mark-task-done', async (_event, taskId) => {
    return new Promise((resolve) => {
      const postData = JSON.stringify({ status: 'completed' });
      const req = http.request(
        `${BACKEND_URL}/api/tasks/${taskId}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postData)
          }
        },
        (res) => {
          resolve(res.statusCode === 200);
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.reload();
          }
        }
      );
      req.on('error', () => resolve(false));
      req.write(postData);
      req.end();
    });
  });

  // Snooze reminder from bird popup
  ipcMain.handle('snooze-reminder', async (_event, taskId, minutes) => {
    return new Promise((resolve) => {
      const postData = JSON.stringify({ task_id: taskId, minutes: minutes });
      const req = http.request(
        `${BACKEND_URL}/api/reminders/snooze`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postData)
          }
        },
        (res) => {
          resolve(res.statusCode === 200);
        }
      );
      req.on('error', () => resolve(false));
      req.write(postData);
      req.end();
    });
  });

  // Settings
  ipcMain.handle('get-app-status', () => {
    return {
      remindersPaused,
      doNotDisturb,
      startWithWindows: app.getLoginItemSettings().openAtLogin
    };
  });

  ipcMain.handle('set-dnd', (_event, enabled) => {
    doNotDisturb = Boolean(enabled);
    updateTrayMenu();
    if (doNotDisturb && overlayWindow) {
      overlayWindow.webContents.send('hide-bird');
    }
    return true;
  });

  ipcMain.handle('set-start-with-windows', (_event, enabled) => {
    app.setLoginItemSettings({
      openAtLogin: Boolean(enabled),
      path: process.execPath
    });
    updateTrayMenu();
    return true;
  });
}

// ----------------- App Lifecycle -----------------
const gotSingleInstanceLock = app.requestSingleInstanceLock();

if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    showMainWindow();
  });

  app.whenReady().then(async () => {
    setupIpcHandlers();
    await startPythonServer();

    createMainWindow();
    createOverlayWindow();
    createTray();

    // Check reminders periodically
    setInterval(checkDueRemindersLoop, 20000);
    setTimeout(checkDueRemindersLoop, 3000);

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createMainWindow();
      } else {
        showMainWindow();
      }
    });
  });

  app.on('before-quit', () => {
    isQuitting = true;
    if (pythonProcess) {
      try {
        pythonProcess.kill();
      } catch (e) {}
    }
  });

  app.on('window-all-closed', () => {
    // Keep app running in tray unless explicit quit
    if (isQuitting) {
      app.quit();
    }
  });
}
