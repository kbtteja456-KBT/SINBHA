// ========================================================
// SINBHA - Electron Desktop Application (Windows)
// Connects to hosted cloud backend (https://sinbha-backend.onrender.com)
// Provides transparent click-through bird overlay, system tray,
// waking-up recovery screen, and background reminder notifications.
// ========================================================

const { app, BrowserWindow, Tray, Menu, ipcMain, screen, session, shell, dialog, Notification } = require('electron');
const path = require('path');
const fs = require('fs');
const config = require('./config');

let mainWindow = null;
let overlayWindow = null;
let tray = null;
let isQuitting = false;

// Global application state
let remindersPaused = false;
let doNotDisturb = false;
let isBirdShowingOnOverlay = false;
let authNotificationShown = false;

// Auto-updater (only active in packaged app or when configured)
let autoUpdater = null;
try {
  autoUpdater = require('electron-updater').autoUpdater;
} catch (e) {
  console.log('electron-updater not loaded in dev mode');
}

// Helper to get active session cookie for authenticated background requests
async function getSessionCookieHeader() {
  try {
    const cookies = await session.defaultSession.cookies.get({ url: config.BACKEND_URL, name: 'sinbha_session' });
    if (cookies && cookies.length > 0) {
      return `sinbha_session=${cookies[0].value}`;
    }
  } catch (e) {}
  return null;
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

  // Load the hosted cloud backend
  mainWindow.loadURL(config.BACKEND_URL);

  // Requirement 1: Reset notification flag as soon as the user logs in again
  session.defaultSession.cookies.on('changed', (_event, cookie, cause, removed) => {
    if (cookie.name === 'sinbha_session' && !removed) {
      authNotificationShown = false;
    }
  });

  // Requirement 3: If server is sleeping or connection fails, show waking screen
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    console.log(`Failed to load ${config.BACKEND_URL} (${errorCode}: ${errorDescription}). Showing waking recovery screen.`);
    mainWindow.loadFile(path.join(__dirname, 'waking.html'));
  });

  // Requirement 7: Electron Security Hardening
  // 1. Block navigation outside trusted domain
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(config.BACKEND_URL) && !url.startsWith('file://')) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  // 2. Open any external links in the default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // 3. Disable DevTools in production release
  if (app.isPackaged) {
    mainWindow.webContents.on('devtools-opened', () => {
      mainWindow.webContents.closeDevTools();
    });
  }

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

// ----------------- System Tray (Requirement 4) -----------------
function updateTrayMenu() {
  if (!tray) return;

  const startWithWindows = app.getLoginItemSettings().openAtLogin;

  const contextMenu = Menu.buildFromTemplate([
    {
      label: `🌸 Open SINBHA (v${app.getVersion()})`,
      click: () => showMainWindow()
    },
    { type: 'separator' },
    {
      label: remindersPaused ? '▶ Resume Reminders' : '⏸ Pause Reminders',
      click: () => {
        remindersPaused = !remindersPaused;
        updateTrayMenu();
        if (overlayWindow && !overlayWindow.isDestroyed()) overlayWindow.webContents.send('hide-bird');
      }
    },
    {
      label: '🌙 Do Not Disturb',
      type: 'checkbox',
      checked: doNotDisturb,
      click: (menuItem) => {
        doNotDisturb = menuItem.checked;
        if (doNotDisturb && overlayWindow && !overlayWindow.isDestroyed()) {
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
      label: '✨ What\'s New',
      click: () => showWhatsNewWindow(app.getVersion())
    },
    {
      label: '❌ Quit SINBHA',
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
  tray.setToolTip(`SINBHA - Habit & Task Companion (v${app.getVersion()})`);

  updateTrayMenu();

  tray.on('click', () => {
    showMainWindow();
  });
}

// ----------------- Background Reminder Poller (Requirement 2) -----------------
async function checkDueRemindersLoop() {
  if (remindersPaused || doNotDisturb || isBirdShowingOnOverlay) return;

  try {
    const cookieHeader = await getSessionCookieHeader();
    if (!cookieHeader) {
      // User is not logged in: overlay bird stays idle
      return;
    }

    const tzOffset = new Date().getTimezoneOffset();
    const url = `${config.BACKEND_URL}/api/reminders/check?tz_offset_minutes=${tzOffset}`;

    const res = await fetch(url, {
      headers: {
        'Cookie': cookieHeader,
        'X-Requested-With': 'XMLHttpRequest'
      }
    });

    if (res.ok) {
      authNotificationShown = false;
      const json = await res.json();
      if (json.reminder_needed && json.task && !json.emergency_stopped) {
        isBirdShowingOnOverlay = true;

        if (overlayWindow && !overlayWindow.isDestroyed()) {
          overlayWindow.webContents.send('show-bird', {
            task: json.task,
            reminder_id: json.reminder_id,
            is_explicit: json.is_explicit
          });
        }

        // Mark fired on backend
        if (json.reminder_id || json.is_explicit) {
          await fetch(`${config.BACKEND_URL}/api/reminders/fired`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Cookie': cookieHeader,
              'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ task_id: json.task.id, reminder_id: json.reminder_id })
          }).catch(() => {});
        }
      }
    } else if (res.status === 401) {
      // Requirement 3: 401 notification on Windows
      if (!authNotificationShown) {
        authNotificationShown = true;
        if (Notification.isSupported()) {
          const authNotif = new Notification({
            title: 'SINBHA Reminders',
            body: 'SINBHA reminders are paused, please open the app and log in again.',
            icon: path.join(__dirname, 'icon.png'),
            urgency: 'critical'
          });
          authNotif.on('click', () => {
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.show();
              mainWindow.focus();
            }
          });
          authNotif.show();
        }
      }
    }
  } catch (e) {
    // Server waking up or network unavailable
  }
}

// ----------------- What's New Window (Requirement 6) -----------------
function checkWhatsNew() {
  try {
    const configPath = path.join(app.getPath('userData'), 'sinbha_state.json');
    let state = {};
    if (fs.existsSync(configPath)) {
      try {
        state = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      } catch (err) {}
    }

    const currentVersion = app.getVersion();
    if (state.lastSeenVersion !== currentVersion) {
      state.lastSeenVersion = currentVersion;
      fs.writeFileSync(configPath, JSON.stringify(state, null, 2));

      // Show What's New card after a short delay
      setTimeout(() => {
        showWhatsNewWindow(currentVersion);
      }, 1800);
    }
  } catch (e) {
    console.error('Error in checkWhatsNew:', e);
  }
}

function showWhatsNewWindow(version) {
  const whatsNewWin = new BrowserWindow({
    width: 460,
    height: 520,
    resizable: false,
    minimizable: false,
    maximizable: false,
    title: `What's New in SINBHA v${version}`,
    icon: path.join(__dirname, 'icon.png'),
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  whatsNewWin.loadFile(path.join(__dirname, 'whats_new.html'));
  whatsNewWin.webContents.on('did-finish-load', () => {
    const features = config.WHATS_NEW[version] || [
      '🌸 Improvements to habit memory & task intelligence',
      '⚡ Faster cloud synchronization & automated reminders'
    ];
    whatsNewWin.webContents.send('whats-new-data', { version, features });
  });
}

// ----------------- Auto-Updater (Requirement 5) -----------------
function setupAutoUpdater() {
  if (!autoUpdater) return;

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on('update-available', (info) => {
    console.log('Update available:', info.version);
  });

  autoUpdater.on('update-downloaded', (info) => {
    dialog.showMessageBox({
      type: 'info',
      title: 'Update Ready 🌸',
      message: `SINBHA v${info.version} is downloaded and ready!`,
      detail: 'Restart the app now to apply the update and see what\'s new.',
      buttons: ['Restart Now', 'Later'],
      defaultId: 0,
      cancelId: 1
    }).then((res) => {
      if (res.response === 0) {
        autoUpdater.quitAndInstall();
      }
    });
  });

  // Check on startup after 5 seconds
  setTimeout(() => {
    autoUpdater.checkForUpdatesAndNotify().catch(() => {});
  }, 5000);

  // Check periodically (every 4 hours)
  setInterval(() => {
    autoUpdater.checkForUpdatesAndNotify().catch(() => {});
  }, config.UPDATE_CHECK_INTERVAL_MS);
}

// ----------------- Minimum Version Gate (Requirement 5) -----------------
function isOlderVersion(current, minimum) {
  if (!current || !minimum) return false;
  const cParts = current.split('.').map(n => parseInt(n, 10) || 0);
  const mParts = minimum.split('.').map(n => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(cParts.length, mParts.length); i++) {
    const c = cParts[i] || 0;
    const m = mParts[i] || 0;
    if (c < m) return true;
    if (c > m) return false;
  }
  return false;
}

async function checkMinimumSupportedVersion() {
  try {
    const res = await fetch(`${config.BACKEND_URL}/api/app/version-check`, { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();

    // Requirement 4: Safety guard against accidental lockout
    if (data.min_version_desktop && data.latest_version_desktop) {
      if (isOlderVersion(data.latest_version_desktop, data.min_version_desktop)) {
        console.warn(`⚠️ [SAFETY LOCKOUT PREVENTED] min_version_desktop (${data.min_version_desktop}) exceeds latest_version_desktop (${data.latest_version_desktop}). Ignoring to prevent accidental user lockout.`);
        return;
      }
    }

    const currentVersion = app.getVersion();
    const minRequired = data.min_version_desktop || '1.0.0';
    const latestAvail = data.latest_version_desktop || minRequired;
    const isMandatory = isOlderVersion(currentVersion, minRequired);
    const isUpdateAvailable = isOlderVersion(currentVersion, latestAvail);

    if (isMandatory || isUpdateAvailable) {
      const downloadLink = data.download_url_desktop || 'https://github.com/kbtteja456-KBT/sinbha-releases/releases/latest/download/SINBHA-Setup.exe';
      const choice = await dialog.showMessageBox({
        type: isMandatory ? 'warning' : 'info',
        title: isMandatory ? 'Update Required 🌸' : 'New Version Available! 🌸',
        message: isMandatory ? 'Please update SINBHA to continue.' : `A newer version of SINBHA (v${latestAvail}) is available!`,
        detail: isMandatory
          ? `Your version (${currentVersion}) is no longer supported. Minimum required version is ${minRequired}.`
          : `You are currently using v${currentVersion}. Click "Download Update" to install the newest update.`,
        buttons: isMandatory ? ['Download Update ⚡', 'Close SINBHA'] : ['Download Update ⚡', 'Maybe Later'],
        defaultId: 0,
        cancelId: 1
      });
      if (choice.response === 0) {
        shell.openExternal(downloadLink);
      }
      if (isMandatory) {
        app.exit(0);
      }
    }
  } catch (e) {
    // Graceful network timeout fallback
  }
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

  // Bird departed off-screen: check for next task in line!
  ipcMain.on('bird-departed', () => {
    isBirdShowingOnOverlay = false;
    setTimeout(checkDueRemindersLoop, 2000);
  });

  // Mark task done from bird popup
  ipcMain.handle('mark-task-done', async (_event, taskId) => {
    const cookieHeader = await getSessionCookieHeader();
    try {
      const res = await fetch(`${config.BACKEND_URL}/api/tasks/${taskId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Cookie': cookieHeader || '',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ status: 'completed' })
      });
      return { success: res.ok };
    } catch (e) {
      return { success: false };
    }
  });

  // Snooze reminder from bird popup
  ipcMain.handle('snooze-reminder', async (_event, taskId, minutes) => {
    const cookieHeader = await getSessionCookieHeader();
    try {
      const res = await fetch(`${config.BACKEND_URL}/api/reminders/snooze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Cookie': cookieHeader || '',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ task_id: taskId, minutes: minutes || 15 })
      });
      return { success: res.ok };
    } catch (e) {
      return { success: false };
    }
  });

  // Status & Settings for UI
  ipcMain.handle('get-app-status', () => {
    return {
      version: app.getVersion(),
      backendUrl: config.BACKEND_URL,
      dnd: doNotDisturb,
      paused: remindersPaused,
      startWithWindows: app.getLoginItemSettings().openAtLogin
    };
  });

  ipcMain.handle('set-dnd', (_event, enabled) => {
    doNotDisturb = enabled;
    updateTrayMenu();
    return { dnd: doNotDisturb };
  });

  ipcMain.handle('set-start-with-windows', (_event, enabled) => {
    app.setLoginItemSettings({
      openAtLogin: enabled,
      path: process.execPath
    });
    updateTrayMenu();
    return { startWithWindows: enabled };
  });

  // Step 16b: Native Device Commands
  ipcMain.on('show-device-notification', (_event, data) => {
    if (Notification.isSupported()) {
      new Notification({
        title: data.title || 'SINBHA Note',
        body: data.body || '',
        icon: path.join(__dirname, 'icon.png')
      }).show();
    }
  });

  ipcMain.handle('show-confirm-dialog', async (_event, options) => {
    const parent = mainWindow && !mainWindow.isDestroyed() ? mainWindow : null;
    const res = await dialog.showMessageBox(parent, {
      type: 'question',
      buttons: ['Allow', 'Deny'],
      defaultId: 0,
      cancelId: 1,
      title: options.title || 'Incoming Remote Action',
      message: options.message || 'A paired device requested an action:',
      detail: options.detail || ''
    });
    return res.response === 0;
  });

  let activeDesktopRingNotification = null;
  ipcMain.on('start-alarm-ring', (_event, sender) => {
    if (Notification.isSupported()) {
      activeDesktopRingNotification = new Notification({
        title: '🔔 Ringing Desktop Alert',
        body: `Remote ring triggered by ${sender || 'Paired Companion'}. Open SINBHA to stop.`,
        icon: path.join(__dirname, 'icon.png'),
        urgency: 'critical'
      });
      activeDesktopRingNotification.on('click', () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.show();
          mainWindow.focus();
        }
      });
      activeDesktopRingNotification.show();
    }
  });

  ipcMain.on('stop-alarm-ring', () => {
    if (activeDesktopRingNotification) {
      try { activeDesktopRingNotification.close(); } catch (e) {}
      activeDesktopRingNotification = null;
    }
  });
}

// ----------------- App Lifecycle -----------------
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    showMainWindow();
  });

  app.whenReady().then(() => {
    setupIpcHandlers();
    createMainWindow();
    createOverlayWindow();
    createTray();

    // Catch-up check on startup & periodic polling (Requirement 2)
    setTimeout(checkDueRemindersLoop, 3000);
    setInterval(checkDueRemindersLoop, config.REMINDER_POLL_INTERVAL_SECONDS * 1000);

    // Auto-update & What's New checks
    setupAutoUpdater();
    checkWhatsNew();
    checkMinimumSupportedVersion();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createMainWindow();
        createOverlayWindow();
      }
    });
  });

  app.on('before-quit', () => {
    isQuitting = true;
  });
}
