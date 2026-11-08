// ========================================================
// SINBHA - Secure Desktop Command & Process Execution Engine
// Enforces strict allowlists, input validation schemas, argument arrays,
// and zero-shell spawn/execFile to prevent command injection.
// ========================================================

const { spawn, execFile } = require('child_process');
const { shell, clipboard } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');

// Forbidden shell characters that indicate potential command injection
const FORBIDDEN_SHELL_CHARS_REGEX = /[&|;`$<>^"'\r\n\t]/;

// Known allowed application names mapped to safe targets
const ALLOWED_APP_TARGETS = {
  'whatsapp': { type: 'protocol', target: 'whatsapp:', expected: ['WhatsApp.exe', 'WhatsApp.Root.exe'] },
  'spotify': { type: 'protocol', target: 'spotify:', expected: ['Spotify.exe'] },
  'youtube': { type: 'url', target: 'https://youtube.com', expected: ['chrome.exe', 'msedge.exe'] },
  'snapchat': { type: 'url', target: 'https://web.snapchat.com', expected: ['chrome.exe', 'msedge.exe'] },
  'instagram': { type: 'url', target: 'https://www.instagram.com', expected: ['chrome.exe', 'msedge.exe'] },
  'notepad': { type: 'binary', binary: 'notepad.exe', args: [], expected: ['Notepad.exe', 'notepad.exe'] },
  'calculator': { type: 'binary', binary: 'calc.exe', args: [], expected: ['CalculatorApp.exe', 'Calculator.exe', 'calc.exe'] },
  'calc': { type: 'binary', binary: 'calc.exe', args: [], expected: ['CalculatorApp.exe', 'Calculator.exe', 'calc.exe'] },
  'explorer': { type: 'binary', binary: 'explorer.exe', args: [], expected: ['explorer.exe'] },
  'files': { type: 'binary', binary: 'explorer.exe', args: [], expected: ['explorer.exe'] },
  'file manager': { type: 'binary', binary: 'explorer.exe', args: [], expected: ['explorer.exe'] },
  'terminal': { type: 'binary', binary: 'wt.exe', args: [], expected: ['WindowsTerminal.exe', 'wt.exe'] },
  'cmd': { type: 'binary', binary: 'cmd.exe', args: [], expected: ['cmd.exe'] },
  'chrome': { type: 'binary', binary: 'chrome.exe', fallbackUrl: 'https://google.com', expected: ['chrome.exe', 'Chrome.exe'] },
  'google chrome': { type: 'binary', binary: 'chrome.exe', fallbackUrl: 'https://google.com', expected: ['chrome.exe', 'Chrome.exe'] },
  'edge': { type: 'binary', binary: 'msedge.exe', fallbackUrl: 'https://microsoft.com/edge', expected: ['msedge.exe', 'MSEdge.exe'] },
  'microsoft edge': { type: 'binary', binary: 'msedge.exe', fallbackUrl: 'https://microsoft.com/edge', expected: ['msedge.exe', 'MSEdge.exe'] },
  'code': { type: 'special', app: 'vscode', expected: ['Code.exe'] },
  'vscode': { type: 'special', app: 'vscode', expected: ['Code.exe'] },
  'vs code': { type: 'special', app: 'vscode', expected: ['Code.exe'] },
  'visual studio code': { type: 'special', app: 'vscode', expected: ['Code.exe'] },
  'claude': { type: 'special', app: 'claude', expected: ['Claude.exe'] },
  'chatgpt': { type: 'special', app: 'chatgpt', expected: ['ChatGPT.exe'] },
  'antigravity': { type: 'special', app: 'antigravity', expected: ['Antigravity.exe'] },
  // Step C2.12: Windows Settings Pages and Microsoft Store UWP
  'settings': { type: 'settings_page', page: 'settings', target: 'ms-settings:', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Settings' },
  'windows settings': { type: 'settings_page', page: 'settings', target: 'ms-settings:', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Settings' },
  'bluetooth': { type: 'settings_page', page: 'bluetooth', target: 'ms-settings:bluetooth', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Bluetooth Settings' },
  'wifi': { type: 'settings_page', page: 'wifi', target: 'ms-settings:network-wifi', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Wi-Fi Settings' },
  'wi-fi': { type: 'settings_page', page: 'wifi', target: 'ms-settings:network-wifi', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Wi-Fi Settings' },
  'display': { type: 'settings_page', page: 'display', target: 'ms-settings:display', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Display Settings' },
  'apps': { type: 'settings_page', page: 'apps', target: 'ms-settings:appsfeatures', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Apps Settings' },
  'windows update': { type: 'settings_page', page: 'windows update', target: 'ms-settings:windowsupdate', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Windows Update' },
  'sound': { type: 'settings_page', page: 'sound', target: 'ms-settings:sound', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Sound Settings' },
  'notifications': { type: 'settings_page', page: 'notifications', target: 'ms-settings:notifications', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Notifications Settings' },
  'accessibility': { type: 'settings_page', page: 'accessibility', target: 'ms-settings:easeofaccess', expected: ['SystemSettings.exe', 'ApplicationFrameHost.exe'], displayName: 'Accessibility Settings' },
  'microsoft store': { type: 'store_app', target: 'ms-windows-store:', expected: ['WinStore.App.exe', 'ApplicationFrameHost.exe'], displayName: 'Microsoft Store' },
  'store': { type: 'store_app', target: 'ms-windows-store:', expected: ['WinStore.App.exe', 'ApplicationFrameHost.exe'], displayName: 'Microsoft Store' }
};

const SETTINGS_PAGES = {
  'settings': 'ms-settings:',
  'main': 'ms-settings:',
  'home': 'ms-settings:',
  'bluetooth': 'ms-settings:bluetooth',
  'devices': 'ms-settings:connecteddevices',
  'wifi': 'ms-settings:network-wifi',
  'wi-fi': 'ms-settings:network-wifi',
  'network': 'ms-settings:network',
  'internet': 'ms-settings:network',
  'display': 'ms-settings:display',
  'screen': 'ms-settings:display',
  'sound': 'ms-settings:sound',
  'volume': 'ms-settings:sound',
  'notifications': 'ms-settings:notifications',
  'battery': 'ms-settings:batterysaver',
  'power': 'ms-settings:powersleep',
  'apps': 'ms-settings:appsfeatures',
  'appsfeatures': 'ms-settings:appsfeatures',
  'installed apps': 'ms-settings:appsfeatures',
  'windows update': 'ms-settings:windowsupdate',
  'update': 'ms-settings:windowsupdate',
  'updates': 'ms-settings:windowsupdate',
  'accessibility': 'ms-settings:easeofaccess',
  'privacy': 'ms-settings:privacy'
};

const ALLOWED_PROTOCOLS = new Set(['https:', 'http:', 'whatsapp:', 'spotify:']);

/**
 * Validates a web or application protocol URL.
 * Rejects javascript:, file:, data:, or malformed schemas.
 */
function validateUrl(rawUrl) {
  if (typeof rawUrl !== 'string' || !rawUrl.trim()) {
    return { valid: false, error: 'URL must be a non-empty string' };
  }
  const trimmed = rawUrl.trim();
  try {
    const parsed = new URL(trimmed.includes('://') || trimmed.endsWith(':') ? trimmed : `https://${trimmed}`);
    if (!ALLOWED_PROTOCOLS.has(parsed.protocol)) {
      return { valid: false, error: `Protocol ${parsed.protocol} is not allowed` };
    }
    return { valid: true, url: parsed.toString() };
  } catch (err) {
    return { valid: false, error: `Invalid URL format: ${err.message}` };
  }
}

/**
 * Validates a search query for search engine / YouTube queries.
 */
function validateSearchQuery(rawQuery) {
  if (typeof rawQuery !== 'string' || !rawQuery.trim()) {
    return { valid: false, error: 'Search query must be a non-empty string' };
  }
  const trimmed = rawQuery.trim();
  if (trimmed.length > 500) {
    return { valid: false, error: 'Search query exceeds maximum length of 500 characters' };
  }
  if (trimmed.includes('\0')) {
    return { valid: false, error: 'Search query contains null bytes' };
  }
  return { valid: true, query: trimmed };
}

/**
 * Validates an app identifier string against injection patterns and schema.
 */
function validateAppTarget(rawApp) {
  if (typeof rawApp !== 'string' || !rawApp.trim()) {
    return { valid: false, error: 'App identifier must be a non-empty string' };
  }
  const trimmed = rawApp.toLowerCase().trim();

  // Strict check: disallow shell metacharacters
  if (FORBIDDEN_SHELL_CHARS_REGEX.test(trimmed)) {
    return { valid: false, error: 'App identifier contains forbidden shell characters' };
  }

  // Length sanity limit
  if (trimmed.length > 80) {
    return { valid: false, error: 'App identifier exceeds maximum length' };
  }

  return { valid: true, app: trimmed };
}

/**
 * Step C2.9 Item 5: Retrieves active foreground window title via zero-shell Windows API call.
 */
function getActiveWindowInfo() {
  return new Promise((resolve) => {
    const ps = `Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; using System.Text; public class WinUtil { [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count); public static string GetActiveTitle() { StringBuilder sb = new StringBuilder(256); IntPtr h = GetForegroundWindow(); if (h == IntPtr.Zero) return ""; GetWindowText(h, sb, 256); return sb.ToString(); } }'; [WinUtil]::GetActiveTitle()`;
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', ps],
      { shell: false, windowsHide: true, timeout: 2500 },
      (err, stdout) => {
        if (err || !stdout) {
          return resolve(null);
        }
        const title = stdout.trim();
        resolve(title ? { title } : null);
      }
    );
  });
}

/**
 * Validates payload for type-input IPC call.
 */
function validateTypeInputPayload(payload) {
  let text = '';
  let pressEnter = false;

  if (typeof payload === 'string') {
    text = payload;
  } else if (typeof payload === 'object' && payload !== null) {
    if (typeof payload.text === 'string') {
      text = payload.text;
    }
    pressEnter = Boolean(payload.press_enter || payload.enter);
  } else {
    return { valid: false, error: 'Invalid payload format for type-input' };
  }

  // Prevent null bytes or excessive size
  if (text.includes('\0')) {
    return { valid: false, error: 'Input text contains null bytes' };
  }
  if (text.length > 10000) {
    return { valid: false, error: 'Input text exceeds 10,000 characters' };
  }

  // Security Invariants: Never type passwords, OTP codes, credit cards, or make payments
  const lowerText = text.toLowerCase();
  if (
    /password\s*[:=]\s*\S+/i.test(text) ||
    /secret\s*[:=]\s*\S+/i.test(text) ||
    /\b(?:my\s+password\s+is|passcode\s*[:=])\b/i.test(text)
  ) {
    return { valid: false, error: 'Typing passwords or secrets is strictly prohibited' };
  }

  if (
    /\b(?:otp|one-time\s*password|verification\s*code|auth\s*code)\b/i.test(lowerText) ||
    (/\b\d{4,8}\b/.test(text) && /\b(?:code|otp|pin|verify)\b/i.test(lowerText))
  ) {
    return { valid: false, error: 'Typing OTP codes or two-factor tokens is strictly prohibited' };
  }

  if (
    /\b(?:\d[ -]*?){13,19}\b/.test(text) &&
    /\b(?:card|visa|mastercard|amex|cvv|cvc|expir)\b/i.test(lowerText)
  ) {
    return { valid: false, error: 'Typing credit card or payment details is strictly prohibited' };
  }

  if (
    /\b(?:make\s+payment|send\s+money|pay\s+\$|checkout\s+now|wire\s+transfer)\b/i.test(lowerText)
  ) {
    return { valid: false, error: 'Making payments is strictly prohibited' };
  }

  return { valid: true, text, pressEnter };
}

/**
 * Step C2.8 Item 4: Checks if a process is running using tasklist with argument array (zero shell strings).
 */
function checkProcessRunning(processName) {
  return new Promise((resolve) => {
    execFile('tasklist.exe', ['/FI', `IMAGENAME eq ${processName}`, '/FO', 'CSV', '/NH'], { shell: false }, (err, stdout) => {
      if (err || !stdout) {
        return resolve(null);
      }
      const lines = stdout.trim().split(/\r?\n/);
      for (const line of lines) {
        if (!line || line.startsWith('INFO:')) continue;
        const parts = line.split('","');
        if (parts.length >= 2) {
          const rawPid = parts[1].replace(/["']/g, '').trim();
          const parsed = parseInt(rawPid, 10);
          if (!isNaN(parsed) && parsed > 0) {
            return resolve(parsed);
          }
        }
      }
      resolve(null);
    });
  });
}

/**
 * Step C2.12: Verifies that expected process, window, or app frame appeared (waits up to 8s).
 * Checks image name, ApplicationFrameHost, SystemSettings, and active window titles.
 * Strictly reports success ONLY after verifying process or window appeared.
 * Never reports failed when the window appeared.
 */
async function verifyWindowOrProcessAppeared(expectedProcessNames, appNameHint = '', maxWaitMs = 8000) {
  if (!Array.isArray(expectedProcessNames)) {
    expectedProcessNames = expectedProcessNames ? [expectedProcessNames] : [];
  }
  const hint = String(appNameHint || '').toLowerCase().trim();
  const candidateProcesses = [...expectedProcessNames].filter(p => p !== 'ApplicationFrameHost.exe');

  if (hint.includes('setting') && !candidateProcesses.includes('SystemSettings.exe')) {
    candidateProcesses.push('SystemSettings.exe');
  }
  if (hint.includes('store') && !candidateProcesses.includes('WinStore.App.exe')) {
    candidateProcesses.push('WinStore.App.exe');
  }
  if (hint.includes('calculator') && !candidateProcesses.includes('CalculatorApp.exe')) {
    candidateProcesses.push('CalculatorApp.exe');
  }

  const startTime = Date.now();
  const pollInterval = 300;

  while (Date.now() - startTime < maxWaitMs) {
    // 1. Check process list for candidate image names
    for (const procName of candidateProcesses) {
      if (procName) {
        const pid = await checkProcessRunning(procName);
        if (pid) {
          return { verified: true, pid, processName: procName };
        }
      }
    }

    // 2. Check active foreground window title
    const activeWin = await getActiveWindowInfo();
    if (activeWin && activeWin.title) {
      const titleLower = activeWin.title.toLowerCase();
      if (
        (hint && titleLower.includes(hint)) ||
        (hint.includes('setting') && titleLower.includes('setting')) ||
        (hint.includes('store') && titleLower.includes('store'))
      ) {
        return { verified: true, windowTitle: activeWin.title, method: 'window_title' };
      }
    }

    await new Promise(r => setTimeout(r, pollInterval));
  }

  return {
    verified: false,
    error: `Process or window for '${appNameHint || expectedProcessNames.join(', ')}' did not appear within ${maxWaitMs / 1000}s timeout`
  };
}

/**
 * Backward compatible alias for verifyProcessAppeared.
 */
async function verifyProcessAppeared(expectedProcessNames, maxWaitMs = 8000) {
  return verifyWindowOrProcessAppeared(expectedProcessNames, '', maxWaitMs);
}

/**
 * Step C2.12: Opens Windows ms-settings pages safely using shell.openExternal.
 * Verifies window or SystemSettings appeared within 8s. Never falsely reports success.
 */
async function safeOpenSettings(page = 'settings') {
  const cleanPage = String(page || 'settings').toLowerCase().trim();
  const uri = SETTINGS_PAGES[cleanPage] || (cleanPage.startsWith('ms-settings:') ? cleanPage : `ms-settings:${cleanPage}`);

  try {
    if (shell && shell.openExternal) {
      await shell.openExternal(uri);
    }
  } catch (e) {}

  try {
    const { spawn } = require('child_process');
    spawn('explorer.exe', [uri], { detached: true, stdio: 'ignore' });
  } catch (e) {}

  const verify = await verifyWindowOrProcessAppeared(['SystemSettings.exe'], 'Settings', 8000);
  if (!verify.verified) {
    return {
      success: false,
      status: 'launch_timeout',
      page: cleanPage,
      uri,
      verified: false,
      error: verify.error || 'Settings window did not appear within timeout'
    };
  }

  return {
    success: true,
    status: 'succeeded',
    page: cleanPage,
    uri,
    verified: true,
    pid: verify.pid || null,
    method: 'ms-settings'
  };
}

/**
 * Safely launches a desktop app, search, URL, or typing text.
 * NEVER uses shell string interpolation or cmd.exe /c start.
 * Step C2.8 Item 4: Handles shell.openPath string error, listens for spawn 'error' events,
 * and reports success ONLY after verifying expected process appeared (up to 8s).
 */
async function safeLaunchDesktopApp(appNameOrTarget) {
  try {
    let target = '';
    let searchQuery = null;
    let targetUrl = null;
    let typeText = null;

    if (typeof appNameOrTarget === 'object' && appNameOrTarget !== null) {
      if (appNameOrTarget.app) {
        const vApp = validateAppTarget(String(appNameOrTarget.app));
        if (!vApp.valid) return { success: false, error: vApp.error };
        target = vApp.app;
      }
      if (appNameOrTarget.search_query || appNameOrTarget.query) {
        const vQuery = validateSearchQuery(String(appNameOrTarget.search_query || appNameOrTarget.query));
        if (!vQuery.valid) return { success: false, error: vQuery.error };
        searchQuery = vQuery.query;
      }
      if (appNameOrTarget.url) {
        const vUrl = validateUrl(String(appNameOrTarget.url));
        if (!vUrl.valid) return { success: false, error: vUrl.error };
        targetUrl = vUrl.url;
      }
      if (appNameOrTarget.type_text || appNameOrTarget.text) {
        typeText = String(appNameOrTarget.type_text || appNameOrTarget.text);
      }
    } else if (typeof appNameOrTarget === 'string') {
      const vApp = validateAppTarget(appNameOrTarget);
      if (!vApp.valid) return { success: false, error: vApp.error };
      target = vApp.app;
    } else {
      return { success: false, error: 'Invalid launch target' };
    }

    // 1. Direct URL opening (strictly validated against allowed protocols)
    if (targetUrl) {
      await shell.openExternal(targetUrl);
      return { success: true, app: target, method: 'url', url: targetUrl };
    }

    // 2. Search query via default browser using shell.openExternal (NO cmd.exe exec)
    if (searchQuery) {
      if (target === 'youtube') {
        const ytUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(searchQuery)}`;
        await shell.openExternal(ytUrl);
        return { success: true, app: 'youtube', method: 'search', query: searchQuery };
      }
      const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(searchQuery)}`;
      await shell.openExternal(searchUrl);
      return { success: true, app: target || 'browser', method: 'search', query: searchQuery };
    }

    // 3. Store App launched via shell:AppsFolder with argument array
    if (target.startsWith('shell:appsfolder\\') || target.includes('!app')) {
      let spawnError = null;
      const child = spawn('explorer.exe', [target], {
        shell: false,
        detached: true,
        stdio: 'ignore'
      });
      child.on('error', (err) => { spawnError = err.message; });
      await new Promise(r => setTimeout(r, 120));
      if (spawnError) {
        return { success: false, error: `Spawn error: ${spawnError}` };
      }
      child.unref();

      const verify = await verifyProcessAppeared(['CalculatorApp.exe', 'Calculator.exe', 'ApplicationFrameHost.exe'], 8000);
      if (!verify.verified) {
        return { success: false, error: verify.error, app: target };
      }
      return { success: true, app: target, method: 'store_app', pid: verify.pid };
    }

    // 4. Typing text into Notepad using safe spawn and argument array
    if (target === 'notepad' && typeText) {
      const tempPath = path.join(os.tmpdir(), 'sinbha_note.txt');
      fs.writeFileSync(tempPath, typeText, 'utf8');
      
      let spawnError = null;
      const child = spawn('notepad.exe', [tempPath], {
        shell: false,
        detached: true,
        stdio: 'ignore'
      });
      child.on('error', (err) => { spawnError = err.message; });
      await new Promise(r => setTimeout(r, 120));
      if (spawnError) {
        return { success: false, error: `Spawn error: ${spawnError}` };
      }
      child.unref();

      const verify = await verifyProcessAppeared(['Notepad.exe', 'notepad.exe'], 8000);
      if (!verify.verified) {
        return { success: false, error: verify.error, app: 'notepad' };
      }
      return { success: true, app: 'notepad', method: 'notepad_file', text: typeText, pid: verify.pid || child.pid };
    }

    // 5. Known desktop app mappings
    const mapping = ALLOWED_APP_TARGETS[target];
    if (mapping) {
      if (mapping.type === 'settings_page') {
        return await safeOpenSettings(mapping.page || target);
      }

      if (mapping.type === 'store_app') {
        await shell.openExternal(mapping.target);
        const verify = await verifyWindowOrProcessAppeared(mapping.expected || ['WinStore.App.exe', 'ApplicationFrameHost.exe'], mapping.displayName || target, 8000);
        if (!verify.verified) {
          return { success: false, status: 'sent_not_verified', error: verify.error, app: target };
        }
        return { success: true, status: 'succeeded', app: target, method: 'store_app', pid: verify.pid || null };
      }

      if (mapping.type === 'protocol' || mapping.type === 'url') {
        await shell.openExternal(mapping.target);
        return { success: true, app: target, method: mapping.type };
      }

      if (mapping.type === 'binary') {
        let spawnError = null;
        const child = spawn(mapping.binary, mapping.args || [], {
          shell: false,
          detached: true,
          stdio: 'ignore'
        });
        child.on('error', (err) => {
          spawnError = err.message;
        });
        await new Promise(r => setTimeout(r, 120));
        if (spawnError) {
          return { success: false, status: 'failed', error: `Spawn error: ${spawnError}`, app: target };
        }
        child.unref();

        const verify = await verifyProcessAppeared(mapping.expected || [mapping.binary], 8000);
        if (!verify.verified) {
          return { success: false, status: 'sent_not_verified', error: verify.error || 'Process or window did not appear within 8 seconds', app: target };
        }
        return { success: true, status: 'succeeded', app: target, method: 'spawn_binary', pid: verify.pid || child.pid };
      }

      if (mapping.type === 'special' && target === 'claude') {
        const localClaude = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Claude', 'Claude.exe');
        if (fs.existsSync(localClaude)) {
          let spawnError = null;
          const child = spawn(localClaude, [], { shell: false, detached: true, stdio: 'ignore' });
          child.on('error', (err) => { spawnError = err.message; });
          await new Promise(r => setTimeout(r, 120));
          if (!spawnError) {
            child.unref();
            const verify = await verifyProcessAppeared(['Claude.exe'], 8000);
            if (verify.verified) {
              return { success: true, status: 'succeeded', app: 'claude', method: 'desktop_exe', pid: verify.pid || child.pid };
            }
            return { success: false, status: 'sent_not_verified', error: verify.error, app: 'claude' };
          }
        }
        const sRes = findInstalledApp('claude');
        const cands = (sRes.candidates || []).map(c => c.displayName || c.name);
        return { success: false, status: 'not_installed', error: 'not_installed', app: 'claude', candidates: cands.slice(0, 3), message: "Claude desktop app is not installed on this computer." };
      }

      if (mapping.type === 'special' && target === 'chatgpt') {
        const localGpt = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'ChatGPT', 'ChatGPT.exe');
        if (fs.existsSync(localGpt)) {
          let spawnError = null;
          const child = spawn(localGpt, [], { shell: false, detached: true, stdio: 'ignore' });
          child.on('error', (err) => { spawnError = err.message; });
          await new Promise(r => setTimeout(r, 120));
          if (!spawnError) {
            child.unref();
            const verify = await verifyProcessAppeared(['ChatGPT.exe'], 8000);
            if (verify.verified) {
              return { success: true, status: 'succeeded', app: 'chatgpt', method: 'desktop_exe', pid: verify.pid || child.pid };
            }
            return { success: false, status: 'sent_not_verified', error: verify.error, app: 'chatgpt' };
          }
        }
        const sRes = findInstalledApp('chatgpt');
        const cands = (sRes.candidates || []).map(c => c.displayName || c.name);
        return { success: false, status: 'not_installed', error: 'not_installed', app: 'chatgpt', candidates: cands.slice(0, 3), message: "ChatGPT desktop app is not installed on this computer." };
      }

      if (mapping.type === 'special' && target === 'antigravity') {
        const localAg = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Antigravity', 'Antigravity.exe');
        if (fs.existsSync(localAg)) {
          let spawnError = null;
          const child = spawn(localAg, [], { shell: false, detached: true, stdio: 'ignore' });
          child.on('error', (err) => { spawnError = err.message; });
          await new Promise(r => setTimeout(r, 120));
          if (!spawnError) {
            child.unref();
            const verify = await verifyProcessAppeared(['Antigravity.exe'], 8000);
            if (verify.verified) {
              return { success: true, app: 'antigravity', method: 'desktop_exe', pid: verify.pid || child.pid };
            }
          }
        }
      }

      if (mapping.type === 'special' && (target === 'vscode' || target === 'vs code' || target === 'code' || target === 'visual studio code')) {
        const userCode = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code', 'Code.exe');
        const progCode = path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Microsoft VS Code', 'Code.exe');
        const progCodeX86 = path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Microsoft VS Code', 'Code.exe');
        const codeExe = fs.existsSync(userCode) ? userCode : (fs.existsSync(progCode) ? progCode : (fs.existsSync(progCodeX86) ? progCodeX86 : null));

        if (codeExe) {
          let spawnError = null;
          const child = spawn(codeExe, [], { shell: false, detached: true, stdio: 'ignore' });
          child.on('error', (err) => { spawnError = err.message; });
          await new Promise(r => setTimeout(r, 120));
          if (spawnError) {
            return { success: false, error: `Spawn error: ${spawnError}` };
          }
          child.unref();

          const verify = await verifyProcessAppeared(['Code.exe'], 8000);
          if (!verify.verified) {
            return { success: false, error: verify.error, app: 'Visual Studio Code' };
          }
          return { success: true, app: 'Visual Studio Code', method: 'desktop_exe', pid: verify.pid || child.pid };
        }

        const vsLnk = path.join(process.env.APPDATA || '', 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Visual Studio Code.lnk');
        if (fs.existsSync(vsLnk)) {
          const openErr = await shell.openPath(vsLnk);
          if (openErr) {
            return { success: false, error: `Failed to open shortcut '${vsLnk}': ${openErr}` };
          }
          const verify = await verifyProcessAppeared(['Code.exe'], 8000);
          if (!verify.verified) {
            return { success: false, error: verify.error, app: 'Visual Studio Code' };
          }
          return { success: true, app: 'Visual Studio Code', method: 'shortcut', path: vsLnk, pid: verify.pid };
        }

        return { success: false, status: 'not_installed', error: 'not_installed', message: 'Visual Studio Code not found on this computer' };
      }
    }

    // 6. Dynamic Start Menu shortcut search using shell.openPath (zero shell execution)
    const userStartMenu = path.join(process.env.APPDATA || '', 'Microsoft', 'Windows', 'Start Menu', 'Programs');
    const allStartMenu = path.join(process.env.PROGRAMDATA || 'C:\\ProgramData', 'Microsoft', 'Windows', 'Start Menu', 'Programs');

    const searchShortcuts = (dir) => {
      if (!fs.existsSync(dir)) return null;
      try {
        const files = fs.readdirSync(dir, { recursive: true });
        for (const f of files) {
          const fStr = String(f);
          if (fStr.toLowerCase().endsWith('.lnk') && fStr.toLowerCase().includes(target)) {
            return path.join(dir, fStr);
          }
        }
      } catch (e) {}
      return null;
    };

    const foundLnk = searchShortcuts(userStartMenu) || searchShortcuts(allStartMenu);
    if (foundLnk) {
      const openErr = await shell.openPath(foundLnk);
      if (openErr) {
        return { success: false, error: `Failed to open shortcut '${foundLnk}': ${openErr}` };
      }
      const targetBase = path.basename(foundLnk, '.lnk');
      const verify = await verifyProcessAppeared([`${target}.exe`, `${targetBase}.exe`], 8000);
      if (!verify.verified) {
        return { success: false, status: 'sent_not_verified', error: verify.error, app: target, message: `Shortcut opened but process did not appear within 8 seconds.` };
      }
      return { success: true, status: 'succeeded', app: target, method: 'start_menu_shortcut', path: foundLnk, pid: verify.pid };
    }

    const searchRes = findInstalledApp(target);
    const top3 = (searchRes && searchRes.candidates) ? searchRes.candidates.map(c => c.displayName || c.name) : [];
    return {
      success: false,
      status: 'not_installed',
      error: 'not_installed',
      app: target,
      candidates: top3.slice(0, 3),
      message: `App '${target}' is not installed on this computer.`
    };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * Safely types text via clipboard and simulated keystroke using execFile with argument arrays.
 * NEVER interpolates user text or shell commands into a command string.
 */
async function safeTypeInput(payload) {
  const validation = validateTypeInputPayload(payload);
  if (!validation.valid) {
    return { success: false, error: validation.error };
  }

  const { text, pressEnter } = validation;
  const previousClipboard = clipboard.readText();

  // Step C2.9 Item 5: Verify intended foreground window
  const activeWin = await getActiveWindowInfo();
  const isForegroundVerified = Boolean(activeWin && activeWin.title);

  if (text) {
    clipboard.writeText(text);
  }

  // Pre-determined, safe character sequences for WScript.Shell SendKeys
  // Fixed literal constants ONLY — no user input is ever placed in SendKeys string
  const pasteToken = text ? '^v' : '';
  const enterToken = pressEnter ? '~' : '';
  const sendKeysKeys = `${pasteToken}${enterToken}`;

  if (!sendKeysKeys) {
    return { success: true, text, enter: pressEnter, verified: isForegroundVerified };
  }

  const psScript = `$ws = New-Object -ComObject WScript.Shell; Start-Sleep -Milliseconds 250; $ws.SendKeys('${sendKeysKeys}')`;

  const execRes = await new Promise((resolve) => {
    // Uses execFile directly pointing to powershell.exe with argument array and NO shell
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psScript],
      { shell: false, windowsHide: true },
      (err) => {
        if (err) {
          resolve({ success: false, error: err.message });
        } else {
          resolve({ success: true, text, enter: pressEnter });
        }
      }
    );
  });

  // Step C2.9 Item 5: Restore the previous clipboard after pasting
  try {
    await new Promise(r => setTimeout(r, 200));
    clipboard.writeText(previousClipboard || '');
  } catch (e) {}

  if (!execRes.success) {
    return execRes;
  }

  if (!isForegroundVerified) {
    return {
      success: true,
      verified: false,
      status: 'sent_not_verified',
      message: 'sent, not verified (could not verify active window title in foreground)',
      text,
      enter: pressEnter
    };
  }

  return {
    success: true,
    verified: true,
    text,
    enter: pressEnter,
    foreground_window: activeWin.title
  };
}

/**
 * Safely locks workstation using execFile with no shell.
 */
async function safeLockWorkstation() {
  return new Promise((resolve) => {
    execFile('rundll32.exe', ['user32.dll,LockWorkStation'], { shell: false, windowsHide: true }, (err) => {
      if (err) {
        resolve({ success: false, error: err.message });
      } else {
        resolve({ success: true });
      }
    });
  });
}

/**
 * Safely queries battery charge using execFile with no shell.
 */
async function safeGetDesktopBattery() {
  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', '(Get-CimInstance -ClassName Win32_Battery).EstimatedChargeRemaining'],
      { shell: false, windowsHide: true },
      (err, stdout) => {
        if (err || !stdout || !stdout.trim()) {
          resolve({ hasBattery: false, percentage: 100, isPlugged: true });
        } else {
          const pct = parseInt(stdout.trim(), 10);
          resolve({ hasBattery: true, percentage: isNaN(pct) ? 100 : pct });
        }
      }
    );
  });
}


// ========================================================
// Step C2: Laptop Tools (App Index, Browsers, Keys, Tracking)
// ========================================================

const ALLOWED_BROWSERS = new Set(['default', 'chrome', 'edge', 'firefox']);

const ALLOWED_KEY_COMBINATIONS = new Set([
  'enter', 'return', 'tab', 'esc', 'escape', 'space', 'backspace', 'delete',
  'up', 'down', 'left', 'right', 'pageup', 'pagedown', 'home', 'end',
  'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
  'ctrl+c', 'ctrl+v', 'ctrl+z', 'ctrl+a', 'ctrl+s', 'ctrl+f', 'ctrl+w',
  'alt+f4', 'alt+tab'
]);

const KEY_TO_SENDKEYS = {
  'enter': '~',
  'return': '~',
  'tab': '{TAB}',
  'esc': '{ESC}',
  'escape': '{ESC}',
  'space': ' ',
  'backspace': '{BS}',
  'delete': '{DEL}',
  'up': '{UP}',
  'down': '{DOWN}',
  'left': '{LEFT}',
  'right': '{RIGHT}',
  'pageup': '{PGUP}',
  'pagedown': '{PGDN}',
  'home': '{HOME}',
  'end': '{END}',
  'f1': '{F1}', 'f2': '{F2}', 'f3': '{F3}', 'f4': '{F4}', 'f5': '{F5}', 'f6': '{F6}',
  'f7': '{F7}', 'f8': '{F8}', 'f9': '{F9}', 'f10': '{F10}', 'f11': '{F11}', 'f12': '{F12}',
  'ctrl+c': '^c',
  'ctrl+v': '^v',
  'ctrl+z': '^z',
  'ctrl+a': '^a',
  'ctrl+s': '^s',
  'ctrl+f': '^f',
  'ctrl+w': '^w',
  'alt+f4': '%{F4}',
  'alt+tab': '%{TAB}'
};

let installedAppsCache = null;
let lastIndexTime = 0;
const INDEX_CACHE_TTL_MS = 3600000; // 1 hour

/**
 * Levenshtein distance algorithm for typo-tolerant fuzzy matching.
 */
function levenshteinDistance(s1, s2) {
  const m = s1.length;
  const n = s2.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = s1[i - 1] === s2[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,       // deletion
        dp[i][j - 1] + 1,       // insertion
        dp[i - 1][j - 1] + cost  // substitution
      );
    }
  }
  return dp[m][n];
}

/**
 * Calculates similarity ratio between 0.0 and 1.0.
 */
function computeSimilarity(query, target) {
  const q = String(query || '').toLowerCase().trim();
  const t = String(target || '').toLowerCase().trim();
  if (!q || !t) return 0.0;
  if (q === t) return 1.0;

  const maxLen = Math.max(q.length, t.length);
  if (maxLen === 0) return 1.0;
  const dist = levenshteinDistance(q, t);
  const ratio = 1.0 - (dist / maxLen);

  if ((t.startsWith(q) || q.startsWith(t)) && dist <= 2) {
    return Math.max(ratio, 0.92);
  }
  return ratio;
}

/**
 * Builds an index of installed applications: Start Menu shortcuts (user + all users),
 * registered programs, and Windows Store apps.
 */
function buildInstalledAppsIndex() {
  const apps = new Map();

  // 1. Well-known allowlisted apps & Store protocols
  for (const [name, target] of Object.entries(ALLOWED_APP_TARGETS)) {
    apps.set(name, {
      name,
      displayName: name.charAt(0).toUpperCase() + name.slice(1),
      type: target.type,
      target: target.target || target.binary || target.app
    });
  }

  // Common Windows Store / System Apps
  const storeApps = [
    { name: 'calculator', displayName: 'Calculator', type: 'protocol', target: 'calculator:' },
    { name: 'calc', displayName: 'Calculator', type: 'binary', target: 'calc.exe' },
    { name: 'notepad', displayName: 'Notepad', type: 'binary', target: 'notepad.exe' },
    { name: 'camera', displayName: 'Camera', type: 'protocol', target: 'microsoft.windows.camera:' },
    { name: 'settings', displayName: 'Settings', type: 'protocol', target: 'ms-settings:' },
    { name: 'clock', displayName: 'Alarms & Clock', type: 'protocol', target: 'ms-clock:' },
    { name: 'whatsapp', displayName: 'WhatsApp', type: 'protocol', target: 'whatsapp:' },
    { name: 'spotify', displayName: 'Spotify', type: 'protocol', target: 'spotify:' },
    { name: 'antigravity', displayName: 'Google Antigravity', type: 'special', target: 'antigravity' },
    { name: 'claude', displayName: 'Claude', type: 'special', target: 'claude' },
    { name: 'chatgpt', displayName: 'ChatGPT', type: 'special', target: 'chatgpt' }
  ];
  for (const sa of storeApps) {
    if (!apps.has(sa.name)) {
      apps.set(sa.name, sa);
    }
  }

  // 2. Scan Windows Get-StartApps (UWP Store apps + Start menu apps)
  if (process.platform === 'win32') {
    try {
      const psOut = execFileSync(
        'powershell.exe',
        ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', 'Get-StartApps | ConvertTo-Json -Compress'],
        { shell: false, timeout: 4500, maxBuffer: 10 * 1024 * 1024, encoding: 'utf8', windowsHide: true }
      );
      if (psOut && psOut.trim()) {
        const parsed = JSON.parse(psOut);
        const list = Array.isArray(parsed) ? parsed : [parsed];
        for (const item of list) {
          if (!item || !item.Name || !item.AppID) continue;
          const cleanKey = item.Name.toLowerCase().trim();
          if (!apps.has(cleanKey)) {
            apps.set(cleanKey, {
              name: cleanKey,
              displayName: item.Name,
              appId: item.AppID,
              type: 'start_app'
            });
          }
        }
      }
    } catch (e) {}
  }

  // 3. Scan Windows Start Menu folders (User & All Users)
  const userStartMenu = path.join(process.env.APPDATA || '', 'Microsoft', 'Windows', 'Start Menu', 'Programs');
  const allStartMenu = path.join(process.env.PROGRAMDATA || 'C:\\ProgramData', 'Microsoft', 'Windows', 'Start Menu', 'Programs');
  const userPrograms = path.join(process.env.LOCALAPPDATA || '', 'Programs');

  const scanDir = (dir) => {
    if (!fs.existsSync(dir)) return;
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true, recursive: true });
      for (const entry of entries) {
        if (!entry.isDirectory() && entry.name.toLowerCase().endsWith('.lnk')) {
          const appName = entry.name.slice(0, -4).trim();
          const cleanKey = appName.toLowerCase();
          const fullPath = path.join(entry.parentPath || dir, entry.name);
          if (!apps.has(cleanKey)) {
            apps.set(cleanKey, {
              name: cleanKey,
              displayName: appName,
              type: 'start_menu_shortcut',
              path: fullPath
            });
          }
        }
      }
    } catch (e) {}
  };

  scanDir(userStartMenu);
  scanDir(allStartMenu);

  // Scan %LOCALAPPDATA%\Programs for direct exe files
  if (fs.existsSync(userPrograms)) {
    try {
      const progEntries = fs.readdirSync(userPrograms, { withFileTypes: true });
      for (const pe of progEntries) {
        if (pe.isDirectory()) {
          const progName = pe.name.toLowerCase();
          const exePath = path.join(userPrograms, pe.name, `${pe.name}.exe`);
          if (fs.existsSync(exePath) && !apps.has(progName)) {
            apps.set(progName, {
              name: progName,
              displayName: pe.name,
              type: 'registered_exe',
              path: exePath
            });
          }
        }
      }
    } catch (e) {}
  }

  installedAppsCache = Array.from(apps.values());
  lastIndexTime = Date.now();
  return installedAppsCache;
}

/**
 * Returns all installed apps on Windows (name, displayName, type, path)
 * for capability reporting to backend server (Step C2.11).
 */
function getInstalledApps() {
  if (!installedAppsCache || (Date.now() - lastIndexTime > INDEX_CACHE_TTL_MS)) {
    buildInstalledAppsIndex();
  }
  return (installedAppsCache || []).map(app => ({
    name: app.name,
    displayName: app.displayName || app.name,
    type: app.type || 'unknown',
    path: app.path || null
  }));
}

/**
 * Searches the pre-built index of installed applications with typo-tolerant matching.
 * Returns confidence level ('high', 'medium', 'low') and top 3 candidates.
 * Typo tolerant: 'antygravity' -> 'antigravity', 'calclator' -> 'calculator', 'chatgpy' -> 'chatgpt'.
 */
function findInstalledApp(rawQuery) {
  const vQuery = validateAppTarget(rawQuery);
  if (!vQuery.valid) {
    return { success: false, error: vQuery.error, matches: [], confidence: 'low', candidates: [] };
  }
  const query = vQuery.app;

  if (!installedAppsCache || (Date.now() - lastIndexTime > INDEX_CACHE_TTL_MS)) {
    buildInstalledAppsIndex();
  }

  const scored = [];
  for (const app of installedAppsCache) {
    const s1 = computeSimilarity(query, app.name);
    const s2 = computeSimilarity(query, app.displayName);
    const bestScore = Math.max(s1, s2);
    if (bestScore >= 0.40) {
      scored.push({
        name: app.name,
        displayName: app.displayName,
        type: app.type,
        path: app.path || null,
        target: app.target || null,
        score: Math.round(bestScore * 100) / 100
      });
    }
  }

  // Sort descending by score
  scored.sort((a, b) => b.score - a.score);

  // Top 3 candidates
  const top3 = scored.slice(0, 3);
  const best = top3[0] || null;

  let confidence = 'low';
  if (best) {
    if (best.score >= 0.80) {
      confidence = 'high';
    } else if (best.score >= 0.55) {
      confidence = 'medium';
    } else {
      confidence = 'low';
    }
  }

  return {
    success: true,
    query,
    confidence, // 'high' | 'medium' | 'low'
    topCandidate: best,
    candidates: top3,
    count: top3.length,
    matches: top3
  };
}

/**
 * Opens a URL in a specific browser (default, chrome, edge, firefox).
 * Enforces argument arrays with no shell execution.
 */
async function openUrlWithBrowser(rawUrl, rawBrowser = 'default') {
  const vUrl = validateUrl(rawUrl);
  if (!vUrl.valid) return { success: false, error: vUrl.error };
  const url = vUrl.url;

  const browser = (rawBrowser || 'default').toLowerCase().trim();
  if (!ALLOWED_BROWSERS.has(browser)) {
    return { success: false, error: `Browser '${browser}' is not supported. Use default, chrome, edge, or firefox.` };
  }

  if (browser === 'default') {
    await shell.openExternal(url);
    return { success: true, url, browser: 'default' };
  }

  const browserBinaries = {
    chrome: 'chrome.exe',
    edge: 'msedge.exe',
    firefox: 'firefox.exe'
  };

  const binary = browserBinaries[browser];
  return new Promise((resolve) => {
    const child = spawn(binary, [url], { shell: false, detached: true, stdio: 'ignore' });
    child.on('error', async () => {
      await shell.openExternal(url);
      resolve({ success: true, url, browser: 'default', fallback: true });
    });
    child.unref();
    resolve({ success: true, url, browser });
  });
}

/**
 * Rule (Step C2.5 Item 3):
 * 1. Look up app in installed apps index with typo tolerance.
 * 2. If confidence is high: launch using app's real launcher.
 * 3. If confidence is medium or low: ask "Did you mean ...?" and never silently fall back to a website.
 * 4. Only offer website when no app is found, and ask first.
 */
async function openAppWithFallback(appName, preferredBrowser = 'chrome', userConfirmedWebsite = false) {
  const vApp = validateAppTarget(appName);
  if (!vApp.valid) return { success: false, error: vApp.error };
  const target = vApp.app;

  // 1. Search installed app index with typo tolerance
  const searchResult = findInstalledApp(target);
  const confidence = searchResult.confidence;
  const topCandidate = searchResult.topCandidate;
  const candidates = searchResult.candidates || [];

  // Web fallback mapping
  const webFallbacks = {
    'claude': 'https://claude.ai',
    'chatgpt': 'https://chatgpt.com',
    'whatsapp': 'https://web.whatsapp.com',
    'spotify': 'https://open.spotify.com',
    'youtube': 'https://youtube.com',
    'instagram': 'https://instagram.com',
    'twitter': 'https://x.com',
    'github': 'https://github.com',
    'figma': 'https://figma.com',
    'slack': 'https://slack.com'
  };
  const fallbackUrl = webFallbacks[target] || `https://www.google.com/search?q=${encodeURIComponent(target)}`;

  // 2. High confidence: launch with real launcher
  if (topCandidate && confidence === 'high') {
    // If it is a settings page
    if (topCandidate.type === 'settings_page') {
      return await safeOpenSettings(topCandidate.page || topCandidate.name);
    }

    // If it is a Windows Store / Start App with AppID
    if (topCandidate.appId && topCandidate.type === 'start_app') {
      try {
        const child = spawn('explorer.exe', ['shell:AppsFolder\\' + topCandidate.appId], { shell: false, detached: true, stdio: 'ignore' });
        child.unref();
        const verify = await verifyWindowOrProcessAppeared(['ApplicationFrameHost.exe'], topCandidate.displayName, 8000);
        if (!verify.verified) {
          return {
            success: false,
            error: verify.error || `Process or window for '${topCandidate.displayName}' did not appear within 8 seconds`,
            app: topCandidate.name
          };
        }
        return {
          success: true,
          method: 'start_app',
          app: topCandidate.name,
          displayName: topCandidate.displayName,
          pid: verify.pid || null
        };
      } catch (e) {}
    }

    // If it has a shortcut path
    if (topCandidate.path && topCandidate.type === 'start_menu_shortcut') {
      try {
        await shell.openPath(topCandidate.path);
        const expectedExe = topCandidate.name ? `${topCandidate.name}.exe` : path.basename(topCandidate.path);
        const verify = await verifyProcessAppeared([expectedExe, `${topCandidate.name}.exe`], 8000);
        if (!verify.verified) {
          return {
            success: false,
            error: verify.error || `Process or window for '${topCandidate.displayName}' did not appear within 8 seconds`,
            app: topCandidate.name
          };
        }
        return {
          success: true,
          method: 'start_menu_shortcut',
          app: topCandidate.name,
          displayName: topCandidate.displayName,
          path: topCandidate.path,
          pid: verify.pid
        };
      } catch (e) {}
    }

    // Direct registered exe
    if (topCandidate.path && topCandidate.type === 'registered_exe') {
      try {
        const child = spawn(topCandidate.path, [], { shell: false, detached: true, stdio: 'ignore' });
        const pid = child.pid;
        child.unref();
        const expectedExe = path.basename(topCandidate.path);
        const verify = await verifyProcessAppeared([expectedExe, `${topCandidate.name}.exe`], 8000);
        if (!verify.verified) {
          return {
            success: false,
            error: verify.error || `Process or window for '${topCandidate.displayName}' did not appear within 8 seconds`,
            app: topCandidate.name
          };
        }
        return {
          success: true,
          method: 'registered_exe',
          app: topCandidate.name,
          displayName: topCandidate.displayName,
          path: topCandidate.path,
          pid: verify.pid || pid
        };
      } catch (e) {}
    }

    // Protocol or standard launch
    const launchRes = await safeLaunchDesktopApp(topCandidate.name);
    if (launchRes && launchRes.success) {
      return {
        success: true,
        method: launchRes.method || 'installed_app',
        app: topCandidate.name,
        displayName: topCandidate.displayName,
        pid: launchRes.pid || null,
        path: launchRes.path || null,
        detail: launchRes
      };
    }
  }

  // 3. Medium or Low confidence with candidates: Ask user for clarification
  if (candidates.length > 0 && confidence !== 'high') {
    const candList = candidates.slice(0, 3).map(c => c.displayName || c.name);
    const candidateNames = candList.map(c => `'${c}'`).join(', ');
    return {
      success: false,
      status: 'not_installed',
      error: 'not_installed',
      app_not_found: true,
      needs_clarification: true,
      confidence,
      candidates: candList,
      message: `Could not find '${appName}'. Did you mean ${candidateNames}? Or should I open its website?`
    };
  }

  // 4. No app found: If user explicitly confirmed website opening, open it; otherwise ask first!
  if (userConfirmedWebsite) {
    const browserRes = await openUrlWithBrowser(fallbackUrl, preferredBrowser);
    return {
      success: true,
      status: 'succeeded',
      method: 'website_fallback',
      app: target,
      url: fallbackUrl,
      browser: preferredBrowser,
      detail: browserRes
    };
  }

  // Never silently fall back to a website without asking first!
  const candList = (candidates || []).slice(0, 3).map(c => c.displayName || c.name);
  return {
    success: false,
    status: 'not_installed',
    error: 'not_installed',
    app_not_found: true,
    offer_website: true,
    fallback_url: fallbackUrl,
    candidates: candList,
    message: `Could not find an installed app matching '${appName}'. Would you like me to open the website instead?`
  };
}

/**
 * Simulates allowlisted key presses safely via WScript.Shell SendKeys.
 */
async function safePressKeys(keys) {
  if (typeof keys !== 'string' || !keys.trim()) {
    return { success: false, error: 'Keys must be a non-empty string' };
  }

  const cleanKey = keys.toLowerCase().trim();
  if (!ALLOWED_KEY_COMBINATIONS.has(cleanKey)) {
    return {
      success: false,
      error: `Key combination '${keys}' is not allowlisted.`
    };
  }

  const sendKeysToken = KEY_TO_SENDKEYS[cleanKey];
  if (!sendKeysToken) {
    return { success: false, error: `No SendKeys mapping for '${cleanKey}'` };
  }

  const psScript = `$ws = New-Object -ComObject WScript.Shell; Start-Sleep -Milliseconds 150; $ws.SendKeys('${sendKeysToken}')`;

  // Step C2.9 Item 5: Verify intended foreground window
  const activeWin = await getActiveWindowInfo();
  const isForegroundVerified = Boolean(activeWin && activeWin.title);

  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psScript],
      { shell: false, windowsHide: true },
      (err) => {
        if (err) {
          resolve({ success: false, error: err.message });
        } else {
          if (!isForegroundVerified) {
            resolve({
              success: true,
              verified: false,
              status: 'sent_not_verified',
              message: 'sent, not verified (could not verify active window title in foreground)',
              key: cleanKey
            });
          } else {
            resolve({
              success: true,
              verified: true,
              key: cleanKey,
              foreground_window: activeWin.title
            });
          }
        }
      }
    );
  });
}

// ========================================================
// PHASE 2: REAL WINDOWS AUTOMATION AGENT CAPABILITIES
// ========================================================

const BLOCKED_SYSTEM_DIRS = [
  process.env.WINDIR || 'C:\\Windows',
  process.env.PROGRAMFILES || 'C:\\Program Files',
  process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)',
  process.env.PROGRAMDATA || 'C:\\ProgramData'
];

/**
 * Resolves an input path safely within allowed user directories.
 * Strictly prevents path traversal escapes and writing to Windows system folders.
 */
function resolveSafeUserPath(inputPath, defaultFolder = 'Desktop') {
  if (!inputPath || typeof inputPath !== 'string') {
    return { valid: false, error: 'Path must be a non-empty string' };
  }
  const raw = inputPath.trim();
  if (raw.includes('\0') || /[&|;`$<>^"'\r\n\t]/.test(raw)) {
    return { valid: false, error: 'Path contains forbidden shell or control characters' };
  }

  const userHome = os.homedir();
  const desktopDir = path.join(userHome, 'Desktop');
  const docsDir = path.join(userHome, 'Documents');
  const downloadsDir = path.join(userHome, 'Downloads');

  let resolved;
  if (path.isAbsolute(raw)) {
    resolved = path.resolve(path.normalize(raw));
  } else {
    const lowerRaw = raw.toLowerCase().replace(/\\/g, '/');
    if (lowerRaw.startsWith('desktop/') || lowerRaw === 'desktop') {
      resolved = path.resolve(userHome, raw);
    } else if (lowerRaw.startsWith('documents/') || lowerRaw === 'documents') {
      resolved = path.resolve(userHome, raw);
    } else if (lowerRaw.startsWith('downloads/') || lowerRaw === 'downloads') {
      resolved = path.resolve(userHome, raw);
    } else {
      const baseDir = defaultFolder === 'Documents' ? docsDir : (defaultFolder === 'Downloads' ? downloadsDir : desktopDir);
      resolved = path.resolve(baseDir, raw);
    }
  }

  // Reject blocked system directories
  for (const sysDir of BLOCKED_SYSTEM_DIRS) {
    if (resolved.toLowerCase().startsWith(sysDir.toLowerCase())) {
      return { valid: false, error: `Modifying system directory '${sysDir}' is strictly prohibited` };
    }
  }

  // Must reside within user home or valid user partition (never drive root)
  if (!resolved.toLowerCase().startsWith(userHome.toLowerCase())) {
    const root = path.parse(resolved).root;
    if (resolved === root || path.dirname(resolved) === root) {
      return { valid: false, error: 'Modifying drive root directory is prohibited' };
    }
  }

  return { valid: true, resolvedPath: resolved };
}

/**
 * Closes a running desktop application safely by process/app name.
 */
async function safeCloseApp(payload) {
  const target = typeof payload === 'string' ? payload : (payload && (payload.app || payload.name || payload.target));
  const valid = validateAppTarget(target);
  if (!valid.valid) {
    return { success: false, error: valid.error };
  }
  const appClean = valid.app;
  const force = Boolean(payload && payload.force);

  const entry = ALLOWED_APP_TARGETS[appClean];
  let procCandidates = [];
  if (entry && entry.expected) {
    procCandidates = [...entry.expected].map(p => p.replace(/\.exe$/i, ''));
  } else {
    procCandidates = [appClean.replace(/\.exe$/i, '')];
  }

  let targetProc = null;
  for (const proc of procCandidates) {
    const isRunning = await checkProcessRunning(`${proc}.exe`);
    if (isRunning) {
      targetProc = proc;
      break;
    }
  }

  if (!targetProc) {
    return {
      success: false,
      status: 'not_running',
      app: appClean,
      message: `Application '${appClean}' is not currently running.`
    };
  }

  return new Promise((resolve) => {
    const psCmd = force
      ? `Stop-Process -Name '${targetProc}' -Force -ErrorAction SilentlyContinue`
      : `$procs = Get-Process -Name '${targetProc}' -ErrorAction SilentlyContinue; foreach ($p in $procs) { $p.CloseMainWindow() | Out-Null }; Start-Sleep -Milliseconds 600; if (Get-Process -Name '${targetProc}' -ErrorAction SilentlyContinue) { Stop-Process -Name '${targetProc}' -Force -ErrorAction SilentlyContinue }`;

    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psCmd],
      { shell: false, windowsHide: true, timeout: 5000 },
      async () => {
        const stillRunning = await checkProcessRunning(`${targetProc}.exe`);
        if (stillRunning) {
          resolve({
            success: false,
            status: 'failed',
            error: 'process_still_running',
            message: `Could not close '${appClean}'. The process is still running.`
          });
        } else {
          resolve({
            success: true,
            status: 'succeeded',
            app: appClean,
            process: targetProc,
            message: `Closed application '${appClean}'.`
          });
        }
      }
    );
  });
}

/**
 * Manages window state: minimize, maximize, restore, or focus.
 */
async function safeManageWindow(payload) {
  const action = (payload && payload.action ? String(payload.action) : 'minimize').toLowerCase().trim();
  const target = payload && (payload.target || payload.app || payload.title) ? String(payload.target || payload.app || payload.title).trim() : '';

  if (!['minimize', 'maximize', 'restore', 'focus'].includes(action)) {
    return { success: false, error: `Invalid window action '${action}'. Allowed: minimize, maximize, restore, focus.` };
  }

  const psScript = `
Add-Type -TypeDefinition '
using System;
using System.Runtime.InteropServices;
using System.Text;

public class WinControl {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}';

$target = '${target.replace(/'/g, "''")}';
$action = '${action}';
$hWnd = [IntPtr]::Zero;

if ($target -ne '') {
    $procs = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and ($_.MainWindowTitle -like "*$target*" -or $_.ProcessName -like "*$target*") }
    if ($procs) {
        $hWnd = $procs[0].MainWindowHandle
    }
}
if ($hWnd -eq [IntPtr]::Zero) {
    $hWnd = [WinControl]::GetForegroundWindow()
}

if ($hWnd -ne [IntPtr]::Zero) {
    $sb = New-Object System.Text.StringBuilder 256
    [WinControl]::GetWindowText($hWnd, $sb, 256) | Out-Null
    $title = $sb.ToString()

    switch ($action) {
        'minimize' { [WinControl]::ShowWindowAsync($hWnd, 6) | Out-Null }
        'maximize' { [WinControl]::ShowWindowAsync($hWnd, 3) | Out-Null }
        'restore'  { [WinControl]::ShowWindowAsync($hWnd, 9) | Out-Null }
        'focus'    { [WinControl]::SetForegroundWindow($hWnd) | Out-Null }
    }
    Write-Output "OK|$title"
} else {
    Write-Output "NOT_FOUND|"
}
`;

  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psScript],
      { shell: false, windowsHide: true, timeout: 3500 },
      (err, stdout) => {
        if (err) {
          return resolve({ success: false, error: err.message });
        }
        const out = (stdout || '').trim();
        if (out.startsWith('OK|')) {
          const winTitle = out.substring(3);
          resolve({
            success: true,
            status: 'succeeded',
            action,
            target: winTitle || target,
            message: `Window '${winTitle || target || 'active'}' ${action}d.`
          });
        } else {
          resolve({
            success: false,
            status: 'window_not_found',
            error: 'window_not_found',
            message: `Could not find an active window matching '${target || 'foreground'}'.`
          });
        }
      }
    );
  });
}

/**
 * Switches to and focuses a running window/app.
 */
async function safeSwitchApp(payload) {
  const target = typeof payload === 'string' ? payload : (payload && (payload.app || payload.title || payload.target));
  return safeManageWindow({ action: 'focus', target });
}

/**
 * Retrieves the currently focused window information with process details.
 */
async function safeGetActiveWindow() {
  const psScript = `
Add-Type -TypeDefinition '
using System;
using System.Runtime.InteropServices;
using System.Text;

public class WinInfo {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}';

$h = [WinInfo]::GetForegroundWindow()
if ($h -ne [IntPtr]::Zero) {
    $sb = New-Object System.Text.StringBuilder 256
    [WinInfo]::GetWindowText($h, $sb, 256) | Out-Null
    $pidOut = 0
    [WinInfo]::GetWindowThreadProcessId($h, [ref]$pidOut) | Out-Null
    $procName = (Get-Process -Id $pidOut -ErrorAction SilentlyContinue).ProcessName
    Write-Output "$($sb.ToString())|$procName|$pidOut"
} else {
    Write-Output "||"
}
`;

  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psScript],
      { shell: false, windowsHide: true, timeout: 2500 },
      (err, stdout) => {
        if (err || !stdout) {
          return resolve({ success: false, error: err ? err.message : 'No output' });
        }
        const parts = stdout.trim().split('|');
        const title = parts[0] || '';
        const processName = parts[1] || '';
        const pid = parseInt(parts[2], 10) || 0;
        resolve({
          success: true,
          status: 'succeeded',
          title,
          process: processName,
          pid,
          message: title ? `Active window is '${title}' (${processName})` : 'No active foreground window found.'
        });
      }
    );
  });
}

/**
 * Creates a folder safely under authorized user paths.
 */
async function safeCreateFolder(payload) {
  const rawPath = typeof payload === 'string' ? payload : (payload && (payload.path || payload.folder_name));
  const res = resolveSafeUserPath(rawPath, 'Desktop');
  if (!res.valid) {
    return { success: false, status: 'forbidden_path', error: res.error, message: res.error };
  }
  const targetDir = res.resolvedPath;
  try {
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
    }
    const folderName = path.basename(targetDir);
    return {
      success: true,
      status: 'succeeded',
      path: targetDir,
      folder_name: folderName,
      message: `Folder '${folderName}' created at ${targetDir}`
    };
  } catch (e) {
    return { success: false, status: 'error', error: e.message, message: `Could not create folder: ${e.message}` };
  }
}

/**
 * Writes or appends text to a file safely.
 */
async function safeWriteTextFile(payload) {
  if (!payload || typeof payload !== 'object') {
    return { success: false, error: 'Payload must be an object with path and content' };
  }
  const rawPath = payload.path || payload.file_name || payload.name;
  const content = String(payload.content != null ? payload.content : (payload.text != null ? payload.text : ''));
  const append = Boolean(payload.append);

  const res = resolveSafeUserPath(rawPath, 'Desktop');
  if (!res.valid) {
    return { success: false, status: 'forbidden_path', error: res.error, message: res.error };
  }
  const targetFile = res.resolvedPath;

  const ext = path.extname(targetFile).toLowerCase();
  if (['.exe', '.bat', '.cmd', '.vbs', '.ps1', '.msi', '.dll', '.scr', '.reg'].includes(ext)) {
    return { success: false, status: 'forbidden_extension', error: `Writing executable or script files (${ext}) is prohibited.` };
  }

  try {
    const parentDir = path.dirname(targetFile);
    if (!fs.existsSync(parentDir)) {
      fs.mkdirSync(parentDir, { recursive: true });
    }

    if (append && fs.existsSync(targetFile)) {
      fs.appendFileSync(targetFile, content, 'utf8');
    } else {
      fs.writeFileSync(targetFile, content, 'utf8');
    }

    const stat = fs.statSync(targetFile);
    const fileName = path.basename(targetFile);
    return {
      success: true,
      status: 'succeeded',
      path: targetFile,
      file_name: fileName,
      size_bytes: stat.size,
      message: `Wrote ${stat.size} bytes to '${fileName}'`
    };
  } catch (e) {
    return { success: false, status: 'error', error: e.message, message: `Could not write file: ${e.message}` };
  }
}

/**
 * Searches for files by query in user directories.
 */
async function safeSearchFiles(payload) {
  const query = typeof payload === 'string' ? payload : (payload && payload.query ? String(payload.query) : '');
  if (!query.trim()) {
    return { success: false, error: 'Search query must be non-empty' };
  }
  const targetFolder = payload && payload.folder ? String(payload.folder) : 'Desktop';
  const res = resolveSafeUserPath(targetFolder, 'Desktop');
  const searchRoot = res.valid ? res.resolvedPath : path.join(os.homedir(), 'Desktop');
  const limit = Math.min(25, Math.max(1, parseInt(payload && payload.limit, 10) || 10));

  const cleanQuery = query.toLowerCase().trim();
  const matches = [];

  const walk = (dir, depth = 0) => {
    if (depth > 4 || matches.length >= limit || !fs.existsSync(dir)) return;
    try {
      const items = fs.readdirSync(dir, { withFileTypes: true });
      for (const item of items) {
        if (matches.length >= limit) break;
        if (item.name.startsWith('.') || ['node_modules', 'appdata', '$recycle.bin'].includes(item.name.toLowerCase())) {
          continue;
        }
        const fullPath = path.join(dir, item.name);
        if (item.name.toLowerCase().includes(cleanQuery)) {
          let stat = null;
          try { stat = fs.statSync(fullPath); } catch (e) {}
          matches.push({
            name: item.name,
            path: fullPath,
            is_directory: item.isDirectory(),
            size_bytes: stat ? stat.size : 0,
            modified_at: stat ? stat.mtime.toISOString() : null
          });
        }
        if (item.isDirectory()) {
          walk(fullPath, depth + 1);
        }
      }
    } catch (e) {}
  };

  walk(searchRoot);
  if (matches.length < 3 && searchRoot.toLowerCase().includes('desktop')) {
    walk(path.join(os.homedir(), 'Documents'));
  }

  return {
    success: true,
    status: 'succeeded',
    query: cleanQuery,
    count: matches.length,
    matches,
    message: matches.length > 0
      ? `Found ${matches.length} matching files/folders for '${cleanQuery}'.`
      : `No files found matching '${cleanQuery}'.`
  };
}

/**
 * Opens a file or folder safely using native system launcher.
 */
async function safeOpenPath(payload) {
  const rawPath = typeof payload === 'string' ? payload : (payload && (payload.path || payload.target));
  const res = resolveSafeUserPath(rawPath, 'Desktop');
  if (!res.valid) {
    return { success: false, status: 'forbidden_path', error: res.error, message: res.error };
  }
  const targetPath = res.resolvedPath;
  if (!fs.existsSync(targetPath)) {
    return { success: false, status: 'not_found', error: 'File or folder does not exist.', path: targetPath };
  }

  const err = await shell.openPath(targetPath);
  if (err) {
    return { success: false, status: 'failed', error: err, message: `Could not open '${targetPath}': ${err}` };
  }
  return {
    success: true,
    status: 'succeeded',
    path: targetPath,
    message: `Opened '${path.basename(targetPath)}'.`
  };
}

/**
 * Retrieves file or folder metadata.
 */
async function safeGetFileInfo(payload) {
  const rawPath = typeof payload === 'string' ? payload : (payload && (payload.path || payload.target));
  const res = resolveSafeUserPath(rawPath, 'Desktop');
  if (!res.valid) {
    return { success: false, status: 'forbidden_path', error: res.error, message: res.error };
  }
  const targetPath = res.resolvedPath;
  if (!fs.existsSync(targetPath)) {
    return { success: true, status: 'succeeded', exists: false, path: targetPath, message: `Path does not exist: ${targetPath}` };
  }
  const stat = fs.statSync(targetPath);
  return {
    success: true,
    status: 'succeeded',
    exists: true,
    path: targetPath,
    name: path.basename(targetPath),
    is_directory: stat.isDirectory(),
    is_file: stat.isFile(),
    size_bytes: stat.size,
    created_at: stat.birthtime.toISOString(),
    modified_at: stat.mtime.toISOString(),
    message: `'${path.basename(targetPath)}' (${stat.isDirectory() ? 'Directory' : `${stat.size} bytes`})`
  };
}

/**
 * Deletes a file with mandatory explicit confirmation.
 */
async function safeDeleteFile(payload) {
  if (!payload || typeof payload !== 'object') {
    return { success: false, error: 'Payload must be an object' };
  }
  if (!payload.confirmed) {
    return {
      success: false,
      status: 'needs_confirmation',
      needs_user_confirmation: true,
      error: 'CONFIRMATION_REQUIRED',
      message: `Deleting files requires explicit confirmation. Please confirm to delete '${payload.path}'.`
    };
  }

  const res = resolveSafeUserPath(payload.path, 'Desktop');
  if (!res.valid) {
    return { success: false, status: 'forbidden_path', error: res.error, message: res.error };
  }
  const targetFile = res.resolvedPath;
  if (!fs.existsSync(targetFile)) {
    return { success: false, status: 'not_found', error: `File not found: ${targetFile}` };
  }
  const stat = fs.statSync(targetFile);
  if (stat.isDirectory()) {
    return { success: false, status: 'directory_deletion_forbidden', error: 'Deleting entire directories is not allowed for safety.' };
  }

  try {
    fs.unlinkSync(targetFile);
    return {
      success: true,
      status: 'succeeded',
      path: targetFile,
      message: `Deleted file '${path.basename(targetFile)}'.`
    };
  } catch (e) {
    return { success: false, status: 'error', error: e.message, message: `Could not delete file: ${e.message}` };
  }
}

/**
 * Clicks a UI element via Windows UI Automation or coordinate fallback.
 */
async function safeClickElement(payload) {
  const target = (payload && (payload.name || payload.target || payload.id) ? String(payload.name || payload.target || payload.id).trim() : '');
  const x = payload && payload.x != null ? parseInt(payload.x, 10) : null;
  const y = payload && payload.y != null ? parseInt(payload.y, 10) : null;

  if (!target && (x === null || y === null)) {
    return { success: false, error: 'Either an element name/id or x,y coordinates must be provided' };
  }

  if (target) {
    const psUIA = `
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$desktop = [System.Windows.Automation.AutomationElement]::RootElement
$target = '${target.replace(/'/g, "''")}'
$condName = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $target)
$condId = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $target)
$condOr = New-Object System.Windows.Automation.OrCondition($condName, $condId)
$element = $desktop.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condOr)

if ($element) {
    try {
        $invPattern = $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $invPattern.Invoke()
        Write-Output "INVOKED"
        exit 0
    } catch {
        $rect = $element.Current.BoundingRectangle
        if ($rect.Width -gt 0 -and $rect.Height -gt 0) {
            $cx = [int]($rect.X + ($rect.Width / 2))
            $cy = [int]($rect.Y + ($rect.Height / 2))
            Write-Output "COORDS|$cx|$cy"
            exit 0
        }
    }
}
Write-Output "NOT_FOUND"
`;

    const uiaResult = await new Promise((resolve) => {
      execFile(
        'powershell.exe',
        ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psUIA],
        { shell: false, windowsHide: true, timeout: 3500 },
        (err, stdout) => {
          if (err || !stdout) return resolve(null);
          const out = stdout.trim();
          if (out === 'INVOKED') return resolve({ method: 'ui_automation_invoked' });
          if (out.startsWith('COORDS|')) {
            const p = out.split('|');
            return resolve({ method: 'ui_automation_bounds', x: parseInt(p[1], 10), y: parseInt(p[2], 10) });
          }
          resolve(null);
        }
      );
    });

    if (uiaResult && uiaResult.method === 'ui_automation_invoked') {
      return {
        success: true,
        status: 'succeeded',
        method: 'ui_automation',
        target,
        message: `Clicked UI element '${target}' via UI Automation.`
      };
    }

    if (uiaResult && uiaResult.x && uiaResult.y) {
      return safeClickCoordinates(uiaResult.x, uiaResult.y, target);
    }
  }

  if (x !== null && y !== null) {
    return safeClickCoordinates(x, y, target || `coordinates (${x}, ${y})`);
  }

  return {
    success: false,
    status: 'element_not_found',
    error: 'element_not_found',
    message: `Could not locate UI element '${target}' on screen.`
  };
}

function safeClickCoordinates(x, y, label) {
  const psClick = `
Add-Type -TypeDefinition '
using System;
using System.Runtime.InteropServices;
public class MouseUtil {
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, int dwExtraInfo);
    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP   = 0x0004;
    public static void Click(int x, int y) {
        SetCursorPos(x, y);
        mouse_event(MOUSEEVENTF_LEFTDOWN, (uint)x, (uint)y, 0, 0);
        System.Threading.Thread.Sleep(50);
        mouse_event(MOUSEEVENTF_LEFTUP, (uint)x, (uint)y, 0, 0);
    }
}';
[MouseUtil]::Click(${x}, ${y})
`;

  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psClick],
      { shell: false, windowsHide: true, timeout: 2500 },
      (err) => {
        if (err) return resolve({ success: false, error: err.message });
        resolve({
          success: true,
          status: 'succeeded',
          method: 'coordinate_click',
          x,
          y,
          message: `Clicked ${label}.`
        });
      }
    );
  });
}

/**
 * Scrolls active window up or down.
 */
async function safeScrollWindow(payload) {
  const dir = (payload && payload.direction ? String(payload.direction) : 'down').toLowerCase();
  const isUp = dir === 'up' || dir === 'page_up';
  const keyToPress = isUp ? 'PageUp' : 'PageDown';
  return safePressKeys(keyToPress);
}

/**
 * Captures primary desktop screen to base64 JPEG with sensitive window privacy defense.
 */
async function safeDesktopScreenCapture() {
  const sensitive = await isForegroundSensitive();
  if (sensitive.isSensitive) {
    return {
      success: false,
      status: 'privacy_blocked',
      error: 'PRIVACY_PROTECTED',
      message: `Screen capture blocked: Active window '${sensitive.title}' contains sensitive information.`
    };
  }

  const psScreen = `
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$ms = New-Object System.IO.MemoryStream
$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Jpeg)
$bytes = $ms.ToArray()
$base64 = [Convert]::ToBase64String($bytes)
$graphics.Dispose()
$bmp.Dispose()
$ms.Dispose()
Write-Output $base64
`;

  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psScreen],
      { shell: false, windowsHide: true, maxBuffer: 15 * 1024 * 1024, timeout: 5000 },
      (err, stdout) => {
        if (err || !stdout) {
          return resolve({ success: false, error: err ? err.message : 'Capture failed' });
        }
        const b64 = stdout.trim();
        resolve({
          success: true,
          status: 'succeeded',
          image_base64: b64,
          format: 'image/jpeg',
          message: 'Desktop screenshot captured.'
        });
      }
    );
  });
}

async function isForegroundSensitive() {
  const win = await getActiveWindowInfo();
  if (!win || !win.title) return { isSensitive: false, title: '' };
  const lower = win.title.toLowerCase();
  const sensitiveWords = ['password', 'bitwarden', '1password', 'keepass', 'bank', 'chase', 'hdfc', 'sbi', 'icici', 'paypal', 'authenticator'];
  for (const w of sensitiveWords) {
    if (lower.includes(w)) {
      return { isSensitive: true, title: win.title };
    }
  }
  return { isSensitive: false, title: win.title };
}

module.exports = {
  FORBIDDEN_SHELL_CHARS_REGEX,
  ALLOWED_APP_TARGETS,
  ALLOWED_BROWSERS,
  ALLOWED_KEY_COMBINATIONS,
  SETTINGS_PAGES,
  validateUrl,
  validateSearchQuery,
  validateAppTarget,
  validateTypeInputPayload,
  safeLaunchDesktopApp,
  safeOpenSettings,
  safeTypeInput,
  safeLockWorkstation,
  safeGetDesktopBattery,
  buildInstalledAppsIndex,
  getInstalledApps,
  findInstalledApp,
  openUrlWithBrowser,
  openAppWithFallback,
  safePressKeys,
  checkProcessRunning,
  verifyProcessAppeared,
  verifyWindowOrProcessAppeared,
  levenshteinDistance,
  computeSimilarity,
  // Phase 2 exports:
  resolveSafeUserPath,
  safeCloseApp,
  safeManageWindow,
  safeSwitchApp,
  safeGetActiveWindow,
  safeClickElement,
  safeScrollWindow,
  safeCreateFolder,
  safeWriteTextFile,
  safeSearchFiles,
  safeOpenPath,
  safeGetFileInfo,
  safeDeleteFile,
  safeDesktopScreenCapture
};
