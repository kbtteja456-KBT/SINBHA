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
  ALLOWED_APP_TARGETS
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
