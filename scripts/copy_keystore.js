const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const keystorePath = path.resolve(__dirname, '../android/sinbha-release.keystore');

if (!fs.existsSync(keystorePath)) {
  console.error('❌ Keystore file not found at:', keystorePath);
  process.exit(1);
}

const base64Content = fs.readFileSync(keystorePath).toString('base64');

// Pipe directly to Windows clip.exe so it never prints to terminal
const proc = spawnSync('clip', { input: base64Content, encoding: 'utf-8' });

if (proc.error) {
  console.error('❌ Failed to copy to clipboard:', proc.error.message);
  process.exit(1);
}

console.log('✅ Success! Base64 keystore copied to your clipboard.');
console.log('👉 Now open GitHub Secrets (ANDROID_KEYSTORE_BASE64) and press Ctrl + V.');
