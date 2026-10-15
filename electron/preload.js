const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Mouse click-through control
  setIgnoreMouseEvents: (ignore, options) => {
    ipcRenderer.send('set-ignore-mouse-events', ignore, options);
  },

  // Bird reminder events
  onShowBird: (callback) => {
    ipcRenderer.on('show-bird', (_event, data) => callback(data));
  },
  onHideBird: (callback) => {
    ipcRenderer.on('hide-bird', () => callback());
  },

  // Actions from overlay
  markTaskDone: (taskId) => ipcRenderer.invoke('mark-task-done', taskId),
  snoozeReminder: (taskId, minutes, taskTitle) => ipcRenderer.invoke('snooze-reminder', taskId, minutes, taskTitle),
  openChatWindow: () => ipcRenderer.send('open-chat-window'),
  dismissBird: () => ipcRenderer.send('dismiss-bird'),
  birdDeparted: () => ipcRenderer.send('bird-departed'),

  // Settings & Status
  getAppStatus: () => ipcRenderer.invoke('get-app-status'),
  setDnd: (enabled) => ipcRenderer.invoke('set-dnd', enabled),
  setStartWithWindows: (enabled) => ipcRenderer.invoke('set-start-with-windows', enabled),

  // Step 16b: Native Device Commands
  showNotification: (title, body) => ipcRenderer.send('show-device-notification', { title, body }),
  showConfirmDialog: (options) => ipcRenderer.invoke('show-confirm-dialog', options),
  startAlarmRing: (sender) => ipcRenderer.send('start-alarm-ring', sender),
  stopAlarmRing: () => ipcRenderer.send('stop-alarm-ring')
});
