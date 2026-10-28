// ========================================================
// SINBHA - Security & Command Injection Protection Tests
// Verifies removal of child_process.exec() and validates
// rejection of attack inputs like: "x\" & calc & \"", quotes,
// ampersands, pipes, and shell metacharacters.
// ========================================================

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const {
  DANGEROUS_SHELL_CHARS,
  ALLOWED_APP_NAME_REGEX,
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
} = require('../electron/command_security');

test('Security Test Suite: Command Injection Protection & Input Validation', async (t) => {

  await t.test('1. App Name Validation: Blocks attack vectors with quotes, ampersands, pipes', () => {
    // Attack payloads that must be rejected
    const attackPayloads = [
      'x" & calc & "',
      'x" && calc && "',
      'x\' & calc & \'',
      'x` & calc & `',
      'notepad & calc',
      'notepad && calc',
      'notepad | calc',
      'notepad || calc',
      'notepad; calc',
      'app > output.txt',
      'app < input.txt',
      'calc | whoami',
      'app $(calc)',
      'app %COMSPEC%',
      'app `calc`',
      'calc\r\ndir',
      'calc\ncalc',
      'calc\0',
      'calc\\..\\calc',
      '../../calc',
      'C:\\Windows\\calc.exe'
    ];

    for (const payload of attackPayloads) {
      const res = validateAppName(payload);
      assert.strictEqual(res.valid, false, `Expected payload "${payload}" to be rejected`);
      assert.ok(res.error, `Expected error message for "${payload}"`);
    }

    // Allowlisted, benign app names
    const validNames = [
      'calc',
      'notepad',
      'Google Chrome',
      'visual-studio_code',
      'code.exe',
      'App 123',
      'spotify'
    ];

    for (const name of validNames) {
      const res = validateAppName(name);
      assert.strictEqual(res.valid, true, `Expected valid name "${name}" to pass`);
      assert.strictEqual(res.sanitized, name);
    }

    // Non-string / empty / oversized inputs
    assert.strictEqual(validateAppName('').valid, false);
    assert.strictEqual(validateAppName('   ').valid, false);
    assert.strictEqual(validateAppName(null).valid, false);
    assert.strictEqual(validateAppName(undefined).valid, false);
    assert.strictEqual(validateAppName(12345).valid, false);
    assert.strictEqual(validateAppName({}).valid, false);
    assert.strictEqual(validateAppName('a'.repeat(65)).valid, false);
  });

  await t.test('2. URL Validation: Rejects dangerous protocols and injection strings', () => {
    const maliciousUrls = [
      'javascript:alert(1)',
      'JAVASCRIPT:fetch("http://evil.com")',
      'file:///C:/Windows/System32/calc.exe',
      'data:text/html,<script>alert(1)</script>',
      'vbscript:MsgBox("pwned")',
      'ms-msdt:/id DevDiagnostic',
      'x" & calc & "',
      'http://example.com/test\x00evil',
      'http://example.com/test\reval'
    ];

    for (const url of maliciousUrls) {
      const res = validateUrl(url);
      assert.strictEqual(res.valid, false, `Expected URL "${url}" to be rejected`);
    }

    const validUrls = [
      'https://google.com',
      'http://localhost:3000/dashboard',
      'https://youtube.com/results?search_query=lofi+music',
      'https://github.com/kbtteja456-KBT/SINBHA'
    ];

    for (const url of validUrls) {
      const res = validateUrl(url);
      assert.strictEqual(res.valid, true, `Expected valid URL "${url}" to pass`);
      assert.ok(res.sanitizedUrl.startsWith('http'));
    }
  });

  await t.test('3. Search Query Validation: Bounded and sanitizes control characters', () => {
    assert.strictEqual(validateSearchQuery('').valid, false);
    assert.strictEqual(validateSearchQuery('   ').valid, false);
    assert.strictEqual(validateSearchQuery(null).valid, false);
    assert.strictEqual(validateSearchQuery('a'.repeat(501)).valid, false);
    assert.strictEqual(validateSearchQuery('test\x00query').valid, false);

    const valid = validateSearchQuery('C++ & Python programming | tips "2026"');
    assert.strictEqual(valid.valid, true);
    assert.strictEqual(valid.sanitizedQuery, 'C++ & Python programming | tips "2026"');
  });

  await t.test('4. Type Input Payload & SendKeys Script: Safe keystroke guarantees', () => {
    // Attack payloads in type-input text
    const attackText = 'x" & calc & "';
    const payload = { text: attackText, press_enter: true };

    let writtenToClipboard = '';
    const mockClipboard = {
      writeText: (t) => { writtenToClipboard = t; }
    };

    let spawnedCommand = '';
    let spawnedArgs = [];
    let spawnedOptions = null;
    const mockSpawn = (cmd, args, opts) => {
      spawnedCommand = cmd;
      spawnedArgs = args;
      spawnedOptions = opts;
      return { unref: () => {} };
    };

    executeTypeInput(payload, { clipboard: mockClipboard, spawn: mockSpawn });

    // 1. Text is safely transferred via clipboard ONLY
    assert.strictEqual(writtenToClipboard, attackText);

    // 2. Command spawned is powershell.exe with shell: false
    assert.strictEqual(spawnedCommand, 'powershell.exe');
    assert.strictEqual(spawnedOptions.shell, false);
    assert.ok(Array.isArray(spawnedArgs));

    // 3. User text is NEVER in the PowerShell command arguments
    const cmdArg = spawnedArgs[spawnedArgs.indexOf('-Command') + 1];
    assert.ok(!cmdArg.includes('calc'), 'PowerShell script must NOT contain injected text');
    assert.ok(!cmdArg.includes('&'), 'PowerShell script must NOT contain ampersand');
    assert.ok(cmdArg.includes("SendKeys('^v~')"), 'PowerShell script must ONLY contain safe keystrokes ^v~');

    // 4. Test script builder throws on invalid keystroke combinations
    assert.throws(() => buildSendKeysScript(false, false));
    const validScript = buildSendKeysScript(true, true);
    assert.ok(validScript.includes("SendKeys('^v~')"));
  });

  await t.test('5. executeLaunchApp: Attack inputs rejected, never spawn shell commands', async () => {
    let spawnCalled = false;
    let spawnTarget = '';
    let spawnOptions = null;
    const mockSpawn = (cmd, args, opts) => {
      spawnCalled = true;
      spawnTarget = cmd;
      spawnOptions = opts;
      return { unref: () => {}, on: () => {} };
    };

    let openedExternalUrl = '';
    const mockShell = {
      openExternal: async (url) => { openedExternalUrl = url; },
      openPath: async () => ''
    };

    // Attack 1: App string injection: 'x" & calc & "'
    const res1 = await executeLaunchApp('x" & calc & "', { shell: mockShell, spawn: mockSpawn });
    assert.strictEqual(res1.success, false);
    assert.strictEqual(spawnCalled, false, 'Spawn must NEVER be called for injection string');

    // Attack 2: App object with ampersand: { app: 'notepad & calc' }
    const res2 = await executeLaunchApp({ app: 'notepad & calc' }, { shell: mockShell, spawn: mockSpawn });
    assert.strictEqual(res2.success, false);
    assert.strictEqual(spawnCalled, false);

    // Attack 3: App object with pipes: { app: 'calc | notepad' }
    const res3 = await executeLaunchApp({ app: 'calc | notepad' }, { shell: mockShell, spawn: mockSpawn });
    assert.strictEqual(res3.success, false);
    assert.strictEqual(spawnCalled, false);

    // Attack 4: App object with quotes: { app: 'calc"calc"' }
    const res4 = await executeLaunchApp({ app: 'calc"calc"' }, { shell: mockShell, spawn: mockSpawn });
    assert.strictEqual(res4.success, false);
    assert.strictEqual(spawnCalled, false);

    // Attack 5: Malicious URL protocol: { url: 'javascript:alert(document.cookie)' }
    const res5 = await executeLaunchApp({ url: 'javascript:alert(document.cookie)' }, { shell: mockShell, spawn: mockSpawn });
    assert.strictEqual(res5.success, false);
    assert.strictEqual(spawnCalled, false);

    // Benign 1: Search query with characters like quotes & ampersands
    // Must be safely URL-encoded into Google search and opened via Electron shell.openExternal
    openedExternalUrl = '';
    const res6 = await executeLaunchApp({ search_query: 'x" & calc & "' }, { shell: mockShell, spawn: mockSpawn });
    assert.strictEqual(res6.success, true);
    assert.strictEqual(res6.method, 'search');
    assert.ok(openedExternalUrl.includes('x%22%20%26%20calc%20%26%20%22'));
    assert.strictEqual(spawnCalled, false, 'No shell or exec must be used for search queries');

    // Benign 2: Known app launch (calc)
    spawnCalled = false;
    const res7 = await executeLaunchApp('calc', { shell: mockShell, spawn: mockSpawn });
    assert.strictEqual(res7.success, true);
    assert.strictEqual(res7.method, 'spawn_exe');
    assert.strictEqual(spawnCalled, true);
    assert.strictEqual(spawnTarget, 'calc.exe');
    assert.strictEqual(spawnOptions.shell, false, 'Spawn must explicitly set shell: false');

    // Benign 3: Notepad note creation with text containing quotes & ampersands
    spawnCalled = false;
    let writtenFilePath = '';
    let writtenFileContent = '';
    const mockFs = {
      writeFileSync: (p, c) => { writtenFilePath = p; writtenFileContent = c; },
      existsSync: () => false
    };
    const mockOs = {
      tmpdir: () => 'C:\\temp'
    };
    const res8 = await executeLaunchApp({ app: 'notepad', text: 'Important note with "quotes" & ampersands' }, {
      shell: mockShell,
      spawn: mockSpawn,
      fs: mockFs,
      os: mockOs
    });
    assert.strictEqual(res8.success, true);
    assert.strictEqual(res8.method, 'notepad_file');
    assert.strictEqual(writtenFileContent, 'Important note with "quotes" & ampersands');
    assert.strictEqual(spawnCalled, true);
    assert.strictEqual(spawnTarget, 'notepad.exe');
    assert.strictEqual(spawnOptions.shell, false);
  });

  await t.test('6. Codebase Audit: Zero occurrences of child_process.exec in electron/main.js', () => {
    const mainJsPath = path.resolve(__dirname, '../electron/main.js');
    const mainJsContent = fs.readFileSync(mainJsPath, 'utf8');

    // Ensure exec is not imported from child_process
    assert.ok(!/require\(['"]child_process['"]\)\.exec\b/.test(mainJsContent), 'Must not use child_process.exec');
    assert.ok(!/\{\s*exec\s*\}\s*=\s*require\(['"]child_process['"]\)/.test(mainJsContent), 'Must not import exec from child_process');

    // Ensure exec(...) is not called
    const execCallMatches = mainJsContent.match(/\bexec\s*\(/g);
    assert.strictEqual(execCallMatches, null, 'electron/main.js must contain 0 calls to exec()');

    // Ensure command_security.js contains 0 calls to exec()
    const cmdSecPath = path.resolve(__dirname, '../electron/command_security.js');
    const cmdSecContent = fs.readFileSync(cmdSecPath, 'utf8');
    const secExecMatches = cmdSecContent.match(/\bexec\s*\(/g);
    assert.strictEqual(secExecMatches, null, 'electron/command_security.js must contain 0 calls to exec()');
  });
});
