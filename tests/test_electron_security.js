// ========================================================
// Unit tests for Electron Command & Process Execution Security
// Tests injection payloads: quotes, ampersands, pipes, semicolons,
// backticks, malicious protocols, path traversals.
// ========================================================

const test = require('node:test');
const assert = require('node:assert');
const {
  validateAppTarget,
  validateUrl,
  validateSearchQuery,
  validateTypeInputPayload,
  FORBIDDEN_SHELL_CHARS_REGEX,
  ALLOWED_APP_TARGETS,
  ALLOWED_BROWSERS,
  ALLOWED_KEY_COMBINATIONS,
  findInstalledApp,
  openUrlWithBrowser,
  safePressKeys
} = require('../electron/command_security');

test('Validation: Rejects shell injection patterns in app identifiers', () => {
  const maliciousInputs = [
    'x" & calc & "',
    'notepad & calc',
    'calc | dir',
    'notepad; whoami',
    'calc `calc`',
    '$(calc)',
    'notepad > test.txt',
    'notepad < test.txt',
    'notepad\ncalc',
    'notepad\r\ncalc',
    'app\' OR \'1\'=\'1',
    'notepad\tcalc',
    'calc^',
    'calc&'
  ];

  for (const input of maliciousInputs) {
    const res = validateAppTarget(input);
    assert.strictEqual(
      res.valid,
      false,
      `Input should have been rejected for shell injection: ${JSON.stringify(input)}`
    );
    assert.match(
      res.error,
      /forbidden shell characters/i,
      `Expected error about shell characters for ${JSON.stringify(input)}`
    );
  }
});

test('Validation: Accepts valid app targets and trims whitespace', () => {
  const validInputs = [
    'notepad',
    'calc',
    'CALCULATOR',
    ' chrome ',
    'whatsapp',
    'spotify',
    'vscode',
    'terminal'
  ];

  for (const input of validInputs) {
    const res = validateAppTarget(input);
    assert.strictEqual(res.valid, true, `Input should be valid: ${input}`);
    assert.strictEqual(res.app, input.toLowerCase().trim());
  }
});

test('Validation: Rejects non-string and empty app inputs', () => {
  assert.strictEqual(validateAppTarget('').valid, false);
  assert.strictEqual(validateAppTarget('   ').valid, false);
  assert.strictEqual(validateAppTarget(null).valid, false);
  assert.strictEqual(validateAppTarget(undefined).valid, false);
  assert.strictEqual(validateAppTarget(12345).valid, false);
  assert.strictEqual(validateAppTarget({}).valid, false);
});

test('Validation: Enforces maximum length for app identifiers', () => {
  const longInput = 'a'.repeat(81);
  const res = validateAppTarget(longInput);
  assert.strictEqual(res.valid, false);
  assert.match(res.error, /maximum length/i);
});

test('URL Validation: Only allows http, https, whatsapp, and spotify schemes', () => {
  // Allowed
  assert.strictEqual(validateUrl('https://example.com').valid, true);
  assert.strictEqual(validateUrl('http://example.com/test?q=1').valid, true);
  assert.strictEqual(validateUrl('whatsapp:').valid, true);
  assert.strictEqual(validateUrl('spotify:').valid, true);

  // Malicious / Disallowed
  const badUrls = [
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'file:///C:/Windows/System32/cmd.exe',
    'vbscript:msgbox',
    'powershell:Start-Process',
    'ms-settings:privacy'
  ];

  for (const bad of badUrls) {
    const res = validateUrl(bad);
    assert.strictEqual(res.valid, false, `Should reject disallowed protocol: ${bad}`);
  }
});

test('Search Query Validation: Rejects null bytes and excessive length', () => {
  assert.strictEqual(validateSearchQuery('Valid search query 123').valid, true);
  assert.strictEqual(validateSearchQuery('query with "quotes" and & ampersand').valid, true); // Search queries are URI encoded, but check length/nulls
  assert.strictEqual(validateSearchQuery('query\0with null').valid, false);
  assert.strictEqual(validateSearchQuery('a'.repeat(501)).valid, false);
  assert.strictEqual(validateSearchQuery('').valid, false);
  assert.strictEqual(validateSearchQuery('   ').valid, false);
});

test('Type Input Validation: Validates payload schema safely', () => {
  // String payload
  const resStr = validateTypeInputPayload('Hello World');
  assert.strictEqual(resStr.valid, true);
  assert.strictEqual(resStr.text, 'Hello World');
  assert.strictEqual(resStr.pressEnter, false);

  // Object payload with enter
  const resObj = validateTypeInputPayload({ text: 'Hello', press_enter: true });
  assert.strictEqual(resObj.valid, true);
  assert.strictEqual(resObj.text, 'Hello');
  assert.strictEqual(resObj.pressEnter, true);

  // Object with enter alternate key
  const resObj2 = validateTypeInputPayload({ text: 'Enter only', enter: true });
  assert.strictEqual(resObj2.valid, true);
  assert.strictEqual(resObj2.pressEnter, true);

  // Rejects null bytes
  assert.strictEqual(validateTypeInputPayload('malicious\0text').valid, false);

  // Rejects excessive text
  assert.strictEqual(validateTypeInputPayload('x'.repeat(10001)).valid, false);

  // Rejects invalid types
  assert.strictEqual(validateTypeInputPayload(12345).valid, false);
  assert.strictEqual(validateTypeInputPayload(null).valid, false);
});

test('Type Input Validation (C2): Strictly blocks passwords, secrets, OTP codes, and payments', () => {
  // Passwords
  assert.strictEqual(validateTypeInputPayload('password: SuperSecret123').valid, false);
  assert.strictEqual(validateTypeInputPayload('My password is Pass123').valid, false);
  assert.strictEqual(validateTypeInputPayload({ text: 'secret = abcdef' }).valid, false);

  // OTP codes
  assert.strictEqual(validateTypeInputPayload('Your verification OTP is 492819').valid, false);
  assert.strictEqual(validateTypeInputPayload('Here is the 6-digit code: 123456').valid, false);
  assert.strictEqual(validateTypeInputPayload({ text: 'Enter auth code 987654' }).valid, false);

  // Credit card & Payments
  assert.strictEqual(validateTypeInputPayload('Visa card 4532 0152 8392 1029 CVV 123').valid, false);
  assert.strictEqual(validateTypeInputPayload('make payment for $500').valid, false);
  assert.strictEqual(validateTypeInputPayload('checkout now and send money').valid, false);

  // Normal safe text passes
  assert.strictEqual(validateTypeInputPayload('Hello, how are you doing today?').valid, true);
  assert.strictEqual(validateTypeInputPayload('Can you open Google Docs for me?').valid, true);
});

test('App Index Search (C2): findInstalledApp returns matches without shell execution', () => {
  const res = findInstalledApp('calc');
  assert.strictEqual(res.success, true);
  assert.ok(res.matches.length > 0);
  assert.strictEqual(res.matches[0].name, 'calc');

  // Search chrome
  const chromeRes = findInstalledApp('chrome');
  assert.strictEqual(chromeRes.success, true);
  assert.ok(chromeRes.matches.some(m => m.name.includes('chrome')));

  // Search non-existent app
  const missingRes = findInstalledApp('non_existent_app_xyz_123');
  assert.strictEqual(missingRes.success, true);
  assert.strictEqual(missingRes.count, 0);

  // Rejects malicious query
  const badRes = findInstalledApp('calc & dir');
  assert.strictEqual(badRes.success, false);
  assert.match(badRes.error, /forbidden shell characters/i);
});

test('Browser Launch (C2): Rejects unsupported browsers', async () => {
  // Disallowed browser
  const badBrowser = await openUrlWithBrowser('https://example.com', 'safari');
  assert.strictEqual(badBrowser.success, false);
  assert.match(badBrowser.error, /not supported/i);

  // Allowed browsers set
  assert.ok(ALLOWED_BROWSERS.has('default'));
  assert.ok(ALLOWED_BROWSERS.has('chrome'));
  assert.ok(ALLOWED_BROWSERS.has('edge'));
  assert.ok(ALLOWED_BROWSERS.has('firefox'));
});

test('Key Press Validation (C2): Only allows safe allowlisted keys', async () => {
  // Allowed combinations
  const validKeys = ['enter', 'tab', 'esc', 'ctrl+c', 'ctrl+v', 'alt+tab', 'f5'];
  for (const k of validKeys) {
    assert.ok(ALLOWED_KEY_COMBINATIONS.has(k), `Expected ${k} in ALLOWED_KEY_COMBINATIONS`);
  }

  // Disallowed keys
  const badKeyRes = await safePressKeys('ctrl+alt+del');
  assert.strictEqual(badKeyRes.success, false);
  assert.match(badKeyRes.error, /not allowlisted/i);

  const emptyKeyRes = await safePressKeys('');
  assert.strictEqual(emptyKeyRes.success, false);
});
