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
  'chatgpt': { type: 'special', app: 'chatgpt' }
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
      child.unref();
      return { success: true, app: 'notepad', method: 'notepad_file', text: typeText };
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
        return { success: true, app: target, method: 'spawn_binary' };
      }

      if (mapping.type === 'special' && target === 'claude') {
        const localClaude = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Claude', 'Claude.exe');
        if (fs.existsSync(localClaude)) {
          const child = spawn(localClaude, [], { shell: false, detached: true, stdio: 'ignore' });
          child.unref();
          return { success: true, app: 'claude', method: 'desktop_exe' };
        }
        await shell.openExternal('https://claude.ai');
        return { success: true, app: 'claude', method: 'web_fallback' };
      }

      if (mapping.type === 'special' && target === 'chatgpt') {
        const localGpt = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'ChatGPT', 'ChatGPT.exe');
        if (fs.existsSync(localGpt)) {
          const child = spawn(localGpt, [], { shell: false, detached: true, stdio: 'ignore' });
          child.unref();
          return { success: true, app: 'chatgpt', method: 'desktop_exe' };
        }
        await shell.openExternal('https://chatgpt.com');
        return { success: true, app: 'chatgpt', method: 'web_fallback' };
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

module.exports = {
  FORBIDDEN_SHELL_CHARS_REGEX,
  ALLOWED_APP_TARGETS,
  validateUrl,
  validateSearchQuery,
  validateAppTarget,
  validateTypeInputPayload,
  safeLaunchDesktopApp,
  safeTypeInput,
  safeLockWorkstation,
  safeGetDesktopBattery
};
