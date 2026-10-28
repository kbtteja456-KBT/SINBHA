// ========================================================
// SINBHA - Secure Command Execution & Input Sanitization
// ========================================================
// Replaces legacy command string execution with
// strict schema validation, character allowlists, spawn/execFile
// argument arrays (shell: false), and native Electron APIs.
// ========================================================

const path = require('path');
const os = require('os');
const fs = require('fs');
const { spawn: defaultSpawn, execFile: defaultExecFile } = require('child_process');

// Regex for disallowed shell injection metacharacters
// Blocks quotes, ampersands, pipes, semicolons, redirection, backticks, newlines, null bytes, variables
const DANGEROUS_SHELL_CHARS = /["'&|;`$<>\r\n\0\\]/;

// Allowlist for app names: alphanumeric, spaces, hyphens, underscores, dots (1-64 chars)
const ALLOWED_APP_NAME_REGEX = /^[a-zA-Z0-9_\-\. ]{1,64}$/;

// Known protocol handlers allowed for shell.openExternal
const ALLOWED_PROTOCOLS = new Set([
  'whatsapp:',
  'spotify:'
]);

// Known web URLs for apps
const KNOWN_APP_URLS = {
  'youtube': 'https://youtube.com',
  'snapchat': 'https://web.snapchat.com',
  'instagram': 'https://www.instagram.com'
};

// Known direct Windows executables (safe to launch via spawn without shell)
const KNOWN_EXECUTABLES = {
  'calc': 'calc.exe',
  'calculator': 'calc.exe',
  'notepad': 'notepad.exe',
  'explorer': 'explorer.exe',
  'files': 'explorer.exe',
  'file manager': 'explorer.exe',
  'cmd': 'cmd.exe',
  'terminal': 'wt.exe',
  'wt': 'wt.exe',
  'chrome': 'chrome.exe',
  'google chrome': 'chrome.exe'
};

/**
 * Validates target application name against strict allowlist.
 * Rejects command injection characters (quotes, ampersands, pipes, etc.).
 */
function validateAppName(appName) {
  if (typeof appName !== 'string') {
    return { valid: false, error: 'App name must be a string' };
  }
  const trimmed = appName.trim();
  if (trimmed.length === 0) {
    return { valid: false, error: 'App name cannot be empty' };
  }
  if (trimmed.length > 64) {
    return { valid: false, error: 'App name exceeds maximum length of 64 characters' };
  }
  if (DANGEROUS_SHELL_CHARS.test(trimmed)) {
    return { valid: false, error: 'Disallowed characters in app name' };
  }
  if (!ALLOWED_APP_NAME_REGEX.test(trimmed)) {
    return { valid: false, error: 'App name contains invalid characters' };
  }
  return { valid: true, sanitized: trimmed };
}

/**
 * Validates and sanitizes URLs.
 * Rejects dangerous protocols (javascript:, file:, data:, ms-msdt:) and control characters.
 */
function validateUrl(urlStr) {
  if (typeof urlStr !== 'string') {
    return { valid: false, error: 'URL must be a string' };
  }
  const trimmed = urlStr.trim();
  if (trimmed.length === 0) {
    return { valid: false, error: 'URL cannot be empty' };
  }
  if (trimmed.length > 2048) {
    return { valid: false, error: 'URL exceeds maximum length of 2048 characters' };
  }
  if (/[\x00-\x1F\x7F]/.test(trimmed)) {
    return { valid: false, error: 'URL contains control characters' };
  }

  let urlToParse = trimmed;
  if (!/^https?:\/\//i.test(trimmed)) {
    // If a scheme like file:, javascript:, data: is present, reject immediately
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(trimmed)) {
      return { valid: false, error: 'Disallowed URL scheme. Only http and https are allowed.' };
    }
    urlToParse = `https://${trimmed}`;
  }

  try {
    const parsed = new URL(urlToParse);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return { valid: false, error: `Invalid URL protocol: ${parsed.protocol}. Only http and https are allowed.` };
    }
    return { valid: true, sanitizedUrl: parsed.toString() };
  } catch (err) {
    return { valid: false, error: 'Malformed URL: ' + err.message };
  }
}

/**
 * Validates search query string.
 * Strips/rejects control characters; length bounded to 500 characters.
 */
function validateSearchQuery(query) {
  if (typeof query !== 'string') {
    return { valid: false, error: 'Search query must be a string' };
  }
  const trimmed = query.trim();
  if (trimmed.length === 0) {
    return { valid: false, error: 'Search query cannot be empty' };
  }
  if (trimmed.length > 500) {
    return { valid: false, error: 'Search query exceeds maximum length of 500 characters' };
  }
  if (/[\x00-\x1F\x7F]/.test(trimmed)) {
    return { valid: false, error: 'Search query contains control characters' };
  }
  return { valid: true, sanitizedQuery: trimmed };
}

/**
 * Validates typing text content.
 */
function validateTypeText(text) {
  if (typeof text !== 'string') {
    return { valid: false, error: 'Type text must be a string' };
  }
  if (text.length > 50000) {
    return { valid: false, error: 'Type text exceeds maximum length of 50000 characters' };
  }
  return { valid: true, text };
}

/**
 * Validates payload for type-input IPC call.
 */
function validateTypeInputPayload(payload) {
  if (typeof payload === 'string') {
    const textVal = validateTypeText(payload);
    if (!textVal.valid) return textVal;
    return { valid: true, text: textVal.text, pressEnter: false };
  }

  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
    return { valid: false, error: 'Payload must be a string or object' };
  }

  const rawText = payload.text !== undefined ? payload.text : (payload.type_text !== undefined ? payload.type_text : '');
  if (typeof rawText !== 'string') {
    return { valid: false, error: 'Payload text must be a string' };
  }
  const textVal = validateTypeText(rawText);
  if (!textVal.valid) return textVal;

  const pressEnter = Boolean(payload.press_enter || payload.enter);
  return { valid: true, text: textVal.text, pressEnter };
}

/**
 * Generates the PowerShell SendKeys script.
 * Crucially, user text is NEVER concatenated into this script.
 * Only static safe keystrokes ('^v' and '~') are allowed.
 */
function buildSendKeysScript(pressEnter, hasText) {
  const pasteAction = hasText ? '^v' : '';
  const enterKey = pressEnter ? '~' : '';
  const keysToSend = `${pasteAction}${enterKey}`;

  // Strict allowlist: must be non-empty and only consist of '^v' and '~'
  if (!keysToSend || !/^(?:\^v)?(?:~)?$/.test(keysToSend)) {
    throw new Error('Invalid keystroke sequence: at least one key must be sent');
  }

  return `$ws = New-Object -ComObject WScript.Shell; Start-Sleep -Milliseconds 300; $ws.SendKeys('${keysToSend}')`;
}

/**
 * Safely executes typing input automation.
 * Copies text to system clipboard and triggers paste / enter using spawn without shell.
 */
async function executeTypeInput(payload, deps = {}) {
  const clipboard = deps.clipboard;
  const spawn = deps.spawn || defaultSpawn;

  const validation = validateTypeInputPayload(payload);
  if (!validation.valid) {
    return { success: false, error: validation.error };
  }

  const { text, pressEnter } = validation;

  if (text && clipboard && typeof clipboard.writeText === 'function') {
    clipboard.writeText(text);
  }

  if (!text && !pressEnter) {
    return { success: true, text: '', enter: false };
  }

  const script = buildSendKeysScript(pressEnter, Boolean(text));
  const psArgs = [
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy', 'Bypass',
    '-Command',
    script
  ];

  const child = spawn('powershell.exe', psArgs, {
    shell: false,
    windowsHide: true,
    stdio: 'ignore'
  });
  if (child && typeof child.unref === 'function') {
    child.unref();
  }

  return { success: true, text, enter: pressEnter };
}

/**
 * Safely executes desktop application launch or web action.
 * Uses Electron shell APIs and spawn with argument arrays (no shell).
 */
async function executeLaunchApp(appNameOrTarget, deps = {}) {
  const shell = deps.shell;
  const spawn = deps.spawn || defaultSpawn;
  const fsModule = deps.fs || fs;
  const osModule = deps.os || os;
  const env = deps.processEnv || process.env;

  let target = '';
  let searchQuery = null;
  let targetUrl = null;
  let typeText = null;

  if (typeof appNameOrTarget === 'object' && appNameOrTarget !== null) {
    if (Array.isArray(appNameOrTarget)) {
      return { success: false, error: 'Invalid payload: array not permitted' };
    }
    target = typeof appNameOrTarget.app === 'string' ? appNameOrTarget.app.trim().toLowerCase() : '';
    searchQuery = appNameOrTarget.search_query !== undefined ? appNameOrTarget.search_query : (appNameOrTarget.query !== undefined ? appNameOrTarget.query : null);
    targetUrl = appNameOrTarget.url !== undefined ? appNameOrTarget.url : null;
    typeText = appNameOrTarget.type_text !== undefined ? appNameOrTarget.type_text : (appNameOrTarget.text !== undefined ? appNameOrTarget.text : null);
  } else if (typeof appNameOrTarget === 'string') {
    target = appNameOrTarget.trim().toLowerCase();
  } else {
    return { success: false, error: 'Invalid payload: expected string or object' };
  }

  // 1. Direct URL opening
  if (targetUrl !== null) {
    const urlVal = validateUrl(targetUrl);
    if (!urlVal.valid) {
      return { success: false, error: urlVal.error };
    }
    if (shell && typeof shell.openExternal === 'function') {
      await shell.openExternal(urlVal.sanitizedUrl);
    }
    return { success: true, app: target, method: 'url', url: urlVal.sanitizedUrl };
  }

  // 2. Search query with browser or YouTube
  if (searchQuery !== null) {
    const searchVal = validateSearchQuery(searchQuery);
    if (!searchVal.valid) {
      return { success: false, error: searchVal.error };
    }
    if (target === 'youtube') {
      const ytUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(searchVal.sanitizedQuery)}`;
      if (shell && typeof shell.openExternal === 'function') {
        await shell.openExternal(ytUrl);
      }
      return { success: true, app: 'youtube', method: 'search', query: searchVal.sanitizedQuery };
    }
    const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(searchVal.sanitizedQuery)}`;
    if (shell && typeof shell.openExternal === 'function') {
      await shell.openExternal(searchUrl);
    }
    return { success: true, app: target || 'chrome', method: 'search', query: searchVal.sanitizedQuery };
  }

  // 3. Typing text into Notepad
  if (target === 'notepad' && typeText !== null) {
    const textVal = validateTypeText(typeText);
    if (!textVal.valid) {
      return { success: false, error: textVal.error };
    }
    const tempDir = osModule.tmpdir();
    const tempPath = path.join(tempDir, 'sinbha_note.txt');
    fsModule.writeFileSync(tempPath, textVal.text, 'utf8');

    const child = spawn('notepad.exe', [tempPath], {
      detached: true,
      stdio: 'ignore',
      shell: false
    });
    if (child && typeof child.unref === 'function') {
      child.unref();
    }
    return { success: true, app: 'notepad', method: 'notepad_file', text: textVal.text };
  }

  // If target is given, validate app name against allowlist / metacharacters
  if (!target) {
    return { success: false, error: 'No target application specified' };
  }

  const appVal = validateAppName(target);
  if (!appVal.valid) {
    return { success: false, error: appVal.error };
  }
  const cleanTarget = appVal.sanitized.toLowerCase();

  // 4. Known protocols
  if (ALLOWED_PROTOCOLS.has(cleanTarget + ':')) {
    if (shell && typeof shell.openExternal === 'function') {
      await shell.openExternal(cleanTarget + ':');
    }
    return { success: true, app: cleanTarget, method: 'protocol' };
  }

  // Known URLs
  if (KNOWN_APP_URLS[cleanTarget]) {
    const webUrl = KNOWN_APP_URLS[cleanTarget];
    if (shell && typeof shell.openExternal === 'function') {
      await shell.openExternal(webUrl);
    }
    return { success: true, app: cleanTarget, method: 'url' };
  }

  // Known direct executables
  if (KNOWN_EXECUTABLES[cleanTarget]) {
    const exe = KNOWN_EXECUTABLES[cleanTarget];
    const child = spawn(exe, [], {
      detached: true,
      stdio: 'ignore',
      shell: false
    });
    if (child && typeof child.unref === 'function') {
      child.unref();
    }
    return { success: true, app: cleanTarget, method: 'spawn_exe' };
  }

  // 5. Special handlers: Claude and ChatGPT
  if (cleanTarget === 'claude') {
    const localClaude = path.join(env.LOCALAPPDATA || '', 'Programs', 'Claude', 'Claude.exe');
    if (fsModule.existsSync(localClaude)) {
      const child = spawn(localClaude, [], {
        detached: true,
        stdio: 'ignore',
        shell: false
      });
      if (child && typeof child.unref === 'function') {
        child.unref();
      }
      return { success: true, app: 'claude', method: 'desktop_exe' };
    }
    if (shell && typeof shell.openExternal === 'function') {
      await shell.openExternal('https://claude.ai');
    }
    return { success: true, app: 'claude', method: 'web_fallback' };
  }

  if (cleanTarget === 'chatgpt') {
    const localGpt = path.join(env.LOCALAPPDATA || '', 'Programs', 'ChatGPT', 'ChatGPT.exe');
    if (fsModule.existsSync(localGpt)) {
      const child = spawn(localGpt, [], {
        detached: true,
        stdio: 'ignore',
        shell: false
      });
      if (child && typeof child.unref === 'function') {
        child.unref();
      }
      return { success: true, app: 'chatgpt', method: 'desktop_exe' };
    }
    if (shell && typeof shell.openExternal === 'function') {
      await shell.openExternal('https://chatgpt.com');
    }
    return { success: true, app: 'chatgpt', method: 'web_fallback' };
  }

  if (cleanTarget === 'code' || cleanTarget === 'vscode') {
    const codeCandidates = [
      path.join(env.LOCALAPPDATA || '', 'Programs', 'Microsoft VS Code', 'Code.exe'),
      path.join(env.PROGRAMFILES || 'C:\\Program Files', 'Microsoft VS Code', 'Code.exe')
    ];
    for (const codeExe of codeCandidates) {
      if (fsModule.existsSync(codeExe)) {
        const child = spawn(codeExe, [], {
          detached: true,
          stdio: 'ignore',
          shell: false
        });
        if (child && typeof child.unref === 'function') {
          child.unref();
        }
        return { success: true, app: cleanTarget, method: 'desktop_exe' };
      }
    }
  }

  // 6. Generic Start Menu shortcuts (.lnk files)
  const userStartMenu = path.join(env.APPDATA || '', 'Microsoft', 'Windows', 'Start Menu', 'Programs');
  const allStartMenu = path.join(env.PROGRAMDATA || 'C:\\ProgramData', 'Microsoft', 'Windows', 'Start Menu', 'Programs');

  const searchShortcuts = (dir) => {
    if (!fsModule.existsSync(dir)) return null;
    try {
      const files = fsModule.readdirSync(dir, { recursive: true });
      for (const f of files) {
        const fStr = String(f);
        if (fStr.toLowerCase().endsWith('.lnk') && fStr.toLowerCase().includes(cleanTarget)) {
          return path.join(dir, fStr);
        }
      }
    } catch (e) {}
    return null;
  };

  const foundLnk = searchShortcuts(userStartMenu) || searchShortcuts(allStartMenu);
  if (foundLnk) {
    if (shell && typeof shell.openPath === 'function') {
      const openErr = await shell.openPath(foundLnk);
      if (openErr) {
        return { success: false, error: openErr, app: cleanTarget };
      }
    }
    return { success: true, app: cleanTarget, method: 'start_menu_shortcut', path: foundLnk };
  }

  // 7. General fallback: spawn cleanly without shell, fallback to Google search on error
  try {
    const child = spawn(`${cleanTarget}.exe`, [], {
      detached: true,
      stdio: 'ignore',
      shell: false
    });
    if (child) {
      child.on('error', () => {
        if (shell && typeof shell.openExternal === 'function') {
          shell.openExternal(`https://www.google.com/search?q=${encodeURIComponent(cleanTarget)}`);
        }
      });
      if (typeof child.unref === 'function') {
        child.unref();
      }
    }
    return { success: true, app: cleanTarget, method: 'fallback_spawn' };
  } catch (err) {
    if (shell && typeof shell.openExternal === 'function') {
      shell.openExternal(`https://www.google.com/search?q=${encodeURIComponent(cleanTarget)}`);
    }
    return { success: true, app: cleanTarget, method: 'fallback_search' };
  }
}

/**
 * Safely locks workstation using spawn with argument array and shell: false.
 */
function executeLockWorkstation(deps = {}) {
  const spawn = deps.spawn || defaultSpawn;
  try {
    const child = spawn('rundll32.exe', ['user32.dll,LockWorkStation'], {
      shell: false,
      detached: true,
      stdio: 'ignore'
    });
    if (child && typeof child.unref === 'function') {
      child.unref();
    }
    return { success: true };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * Safely gets desktop battery remaining percentage using execFile with argument array and shell: false.
 */
function executeGetBattery(deps = {}) {
  const execFile = deps.execFile || defaultExecFile;
  return new Promise((resolve) => {
    try {
      execFile('powershell.exe', [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        '(Get-WmiObject -Class Win32_Battery).EstimatedChargeRemaining'
      ], {
        shell: false,
        windowsHide: true
      }, (err, stdout) => {
        if (err || !stdout || !stdout.trim()) {
          resolve({ hasBattery: false, percentage: 100, isPlugged: true });
        } else {
          const pct = parseInt(stdout.trim(), 10);
          resolve({ hasBattery: true, percentage: isNaN(pct) ? 100 : pct });
        }
      });
    } catch (e) {
      resolve({ hasBattery: false, percentage: 100 });
    }
  });
}

module.exports = {
  DANGEROUS_SHELL_CHARS,
  ALLOWED_APP_NAME_REGEX,
  ALLOWED_PROTOCOLS,
  KNOWN_APP_URLS,
  KNOWN_EXECUTABLES,
  validateAppName,
  validateUrl,
  validateSearchQuery,
  validateTypeText,
  validateTypeInputPayload,
  buildSendKeysScript,
  executeLaunchApp,
  executeTypeInput,
  executeLockWorkstation,
  executeGetBattery
};
