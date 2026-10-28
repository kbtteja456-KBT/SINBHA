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
  'whatsapp': { type: 'protocol', target: 'whatsapp:' },
  'spotify': { type: 'protocol', target: 'spotify:' },
  'youtube': { type: 'url', target: 'https://youtube.com' },
  'snapchat': { type: 'url', target: 'https://web.snapchat.com' },
  'instagram': { type: 'url', target: 'https://www.instagram.com' },
  'notepad': { type: 'binary', binary: 'notepad.exe', args: [] },
  'calculator': { type: 'binary', binary: 'calc.exe', args: [] },
  'calc': { type: 'binary', binary: 'calc.exe', args: [] },
  'explorer': { type: 'binary', binary: 'explorer.exe', args: [] },
  'files': { type: 'binary', binary: 'explorer.exe', args: [] },
  'file manager': { type: 'binary', binary: 'explorer.exe', args: [] },
  'terminal': { type: 'binary', binary: 'wt.exe', args: [] },
  'cmd': { type: 'binary', binary: 'cmd.exe', args: [] },
  'chrome': { type: 'binary', binary: 'chrome.exe', fallbackUrl: 'https://google.com' },
  'google chrome': { type: 'binary', binary: 'chrome.exe', fallbackUrl: 'https://google.com' },
  'code': { type: 'binary', binary: 'code.cmd', fallbackBinary: 'code.exe' },
  'vscode': { type: 'binary', binary: 'code.cmd', fallbackBinary: 'code.exe' },
  'claude': { type: 'special', app: 'claude' },
  'chatgpt': { type: 'special', app: 'chatgpt' },
  'antigravity': { type: 'special', app: 'antigravity' }
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
 * Safely launches a desktop app, search, URL, or typing text.
 * NEVER uses shell string interpolation or cmd.exe /c start.
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

    // 3. Typing text into Notepad using safe spawn and argument array
    if (target === 'notepad' && typeText) {
      const tempPath = path.join(os.tmpdir(), 'sinbha_note.txt');
      fs.writeFileSync(tempPath, typeText, 'utf8');
      
      const child = spawn('notepad.exe', [tempPath], {
        shell: false,
        detached: true,
        stdio: 'ignore'
      });
      const pid = child.pid;
      child.unref();
      return { success: true, app: 'notepad', method: 'notepad_file', text: typeText, pid };
    }

    // 4. Known desktop app mappings
    const mapping = ALLOWED_APP_TARGETS[target];
    if (mapping) {
      if (mapping.type === 'protocol' || mapping.type === 'url') {
        await shell.openExternal(mapping.target);
        return { success: true, app: target, method: mapping.type };
      }

      if (mapping.type === 'binary') {
        const child = spawn(mapping.binary, mapping.args || [], {
          shell: false,
          detached: true,
          stdio: 'ignore'
        });
        const pid = child.pid;
        child.on('error', () => {
          if (mapping.fallbackUrl) {
            shell.openExternal(mapping.fallbackUrl);
          } else if (mapping.fallbackBinary) {
            const fallbackChild = spawn(mapping.fallbackBinary, mapping.args || [], {
              shell: false,
              detached: true,
              stdio: 'ignore'
            });
            fallbackChild.unref();
          }
        });
        child.unref();
        return { success: true, app: target, method: 'spawn_binary', pid };
      }

      if (mapping.type === 'special' && target === 'claude') {
        const localClaude = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Claude', 'Claude.exe');
        if (fs.existsSync(localClaude)) {
          const child = spawn(localClaude, [], { shell: false, detached: true, stdio: 'ignore' });
          const pid = child.pid;
          child.unref();
          return { success: true, app: 'claude', method: 'desktop_exe', pid };
        }
        await shell.openExternal('https://claude.ai');
        return { success: true, app: 'claude', method: 'web_fallback' };
      }

      if (mapping.type === 'special' && target === 'chatgpt') {
        const localGpt = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'ChatGPT', 'ChatGPT.exe');
        if (fs.existsSync(localGpt)) {
          const child = spawn(localGpt, [], { shell: false, detached: true, stdio: 'ignore' });
          const pid = child.pid;
          child.unref();
          return { success: true, app: 'chatgpt', method: 'desktop_exe', pid };
        }
        await shell.openExternal('https://chatgpt.com');
        return { success: true, app: 'chatgpt', method: 'web_fallback' };
      }

      if (mapping.type === 'special' && target === 'antigravity') {
        const localAg = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Antigravity', 'Antigravity.exe');
        if (fs.existsSync(localAg)) {
          const child = spawn(localAg, [], { shell: false, detached: true, stdio: 'ignore' });
          const pid = child.pid;
          child.unref();
          return { success: true, app: 'antigravity', method: 'desktop_exe', pid };
        }
        // Fallback to start menu search
      }
    }

    // 5. Dynamic Start Menu shortcut search using shell.openPath (zero shell execution)
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
      await shell.openPath(foundLnk);
      return { success: true, app: target, method: 'start_menu_shortcut', path: foundLnk };
    }

    return { success: false, error: `App '${target}' not found in allowlist or Start Menu` };
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

  if (text) {
    clipboard.writeText(text);
  }

  // Pre-determined, safe character sequences for WScript.Shell SendKeys
  // Fixed literal constants ONLY — no user input is ever placed in SendKeys string
  const pasteToken = text ? '^v' : '';
  const enterToken = pressEnter ? '~' : '';
  const sendKeysKeys = `${pasteToken}${enterToken}`;

  if (!sendKeysKeys) {
    return { success: true, text, enter: pressEnter };
  }

  const psScript = `$ws = New-Object -ComObject WScript.Shell; Start-Sleep -Milliseconds 300; $ws.SendKeys('${sendKeysKeys}')`;

  return new Promise((resolve) => {
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

  // 2. Scan Windows Start Menu folders (User & All Users)
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
    // If it has a shortcut path
    if (topCandidate.path && topCandidate.type === 'start_menu_shortcut') {
      try {
        await shell.openPath(topCandidate.path);
        return {
          success: true,
          method: 'start_menu_shortcut',
          app: topCandidate.name,
          displayName: topCandidate.displayName,
          path: topCandidate.path
        };
      } catch (e) {}
    }

    // Direct registered exe
    if (topCandidate.path && topCandidate.type === 'registered_exe') {
      try {
        const child = spawn(topCandidate.path, [], { shell: false, detached: true, stdio: 'ignore' });
        const pid = child.pid;
        child.unref();
        return {
          success: true,
          method: 'registered_exe',
          app: topCandidate.name,
          displayName: topCandidate.displayName,
          path: topCandidate.path,
          pid
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
    const candidateNames = candidates.map(c => `'${c.displayName}'`).join(', ');
    return {
      success: false,
      needs_clarification: true,
      confidence,
      candidates,
      message: `Did you mean ${candidateNames}?`
    };
  }

  // 4. No app found: If user explicitly confirmed website opening, open it; otherwise ask first!
  if (userConfirmedWebsite) {
    const browserRes = await openUrlWithBrowser(fallbackUrl, preferredBrowser);
    return {
      success: true,
      method: 'website_fallback',
      app: target,
      url: fallbackUrl,
      browser: preferredBrowser,
      detail: browserRes
    };
  }

  // Never silently fall back to a website without asking first!
  return {
    success: false,
    app_not_found: true,
    offer_website: true,
    fallback_url: fallbackUrl,
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

  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psScript],
      { shell: false, windowsHide: true },
      (err) => {
        if (err) {
          resolve({ success: false, error: err.message });
        } else {
          resolve({ success: true, key: cleanKey });
        }
      }
    );
  });
}

module.exports = {
  FORBIDDEN_SHELL_CHARS_REGEX,
  ALLOWED_APP_TARGETS,
  ALLOWED_BROWSERS,
  ALLOWED_KEY_COMBINATIONS,
  validateUrl,
  validateSearchQuery,
  validateAppTarget,
  validateTypeInputPayload,
  safeLaunchDesktopApp,
  safeTypeInput,
  safeLockWorkstation,
  safeGetDesktopBattery,
  buildInstalledAppsIndex,
  findInstalledApp,
  openUrlWithBrowser,
  openAppWithFallback,
  safePressKeys,
  levenshteinDistance,
  computeSimilarity
};
