// ========================================================
// Pre-Build Security Check (Requirement 1)
// Fails the build immediately if any secret-looking file or
// credentials (.env, API keys, database URLs) are found in
// files packaged into the desktop installer.
// ========================================================

const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.resolve(__dirname, '..');

// Dangerous file patterns that must NEVER be inside installer package
const FORBIDDEN_FILES = [
  '.env',
  '.env.production',
  '.env.local',
  '.env.development',
  'sinbha.db',
  'sinbha.sqlite',
  'sinbha.sqlite3'
];

// Dangerous content patterns (secrets, private keys)
const SECRET_REGEXES = [
  /sk-or-v1-[a-zA-Z0-9]{32,}/i,               // OpenRouter API key
  /postgresql\+psycopg:\/\/[^@\s]+@[^\s]+/i, // Postgres connection string with password
  /postgres:\/\/[^@\s]+@[^\s]+/i,
  /DATA_ENCRYPTION_KEY\s*=\s*[a-zA-Z0-9_-]{30,}/i,
  /SESSION_SECRET\s*=\s*[a-zA-Z0-9_-]{30,}/i,
  /-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----/i
];

console.log('🔍 Running Pre-Build Secret Verification...');

let violations = [];

// 1. Check for presence of forbidden files in packaging roots
for (const file of FORBIDDEN_FILES) {
  const rootFile = path.join(ROOT_DIR, file);
  const electronFile = path.join(ROOT_DIR, 'electron', file);
  if (fs.existsSync(electronFile)) {
    violations.push(`Forbidden file found inside electron folder: ${electronFile}`);
  }
}

// 2. Scan bundled javascript and config files inside electron folder
const filesToScan = [
  path.join(ROOT_DIR, 'electron', 'config.js'),
  path.join(ROOT_DIR, 'electron', 'main.js'),
  path.join(ROOT_DIR, 'electron', 'preload.js'),
  path.join(ROOT_DIR, 'electron', 'overlay.js')
];

for (const filePath of filesToScan) {
  if (fs.existsSync(filePath)) {
    const content = fs.readFileSync(filePath, 'utf8');
    for (const regex of SECRET_REGEXES) {
      if (regex.test(content)) {
        violations.push(`Potential secret detected in ${path.relative(ROOT_DIR, filePath)} matching ${regex}`);
      }
    }
  }
}

if (violations.length > 0) {
  console.error('\n❌ BUILD FAILED: Security Violation Detected!');
  console.error('The installer cannot be built because sensitive secrets or secret files were found:');
  violations.forEach(v => console.error(`  - ${v}`));
  console.error('\nPlease remove these secrets or files before building.\n');
  process.exit(1);
}

console.log('✅ Security Check Passed: No secrets, .env files, or database credentials detected in installer payload.\n');
process.exit(0);
