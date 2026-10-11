// ========================================================
// SINBHA - Android Keystore Generator (Requirement 7)
// Safely creates a 2048-bit RSA release signing key
// and writes local signing.properties (git-ignored).
// ========================================================

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ANDROID_DIR = path.resolve(__dirname, '..', 'android');
const KEYSTORE_PATH = path.join(ANDROID_DIR, 'sinbha-release.keystore');
const SIGNING_PROPERTIES_PATH = path.join(ANDROID_DIR, 'signing.properties');

console.log('🌸 SINBHA Release Key Setup...\n');

function findKeytool() {
  if (process.env.JAVA_HOME) {
    const candidate = path.join(process.env.JAVA_HOME, 'bin', 'keytool.exe');
    if (fs.existsSync(candidate)) return candidate;
  }
  const javaDir = 'C:\\Program Files\\Java';
  if (fs.existsSync(javaDir)) {
    const entries = fs.readdirSync(javaDir);
    for (const entry of entries) {
      const candidate = path.join(javaDir, entry, 'bin', 'keytool.exe');
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  return 'keytool';
}

if (fs.existsSync(KEYSTORE_PATH)) {
  console.log(`ℹ️ Release keystore already exists at: ${KEYSTORE_PATH}`);
} else {
  const keytoolBin = findKeytool();
  // Generate random secure passwords for the keystore
  const storePassword = crypto.randomBytes(16).toString('hex');
  const keyPassword = crypto.randomBytes(16).toString('hex');
  const alias = 'sinbha_release';

  const dname = 'CN=SINBHA, OU=Mobile, O=SINBHA Companion, L=City, ST=State, C=IN';
  const keytoolCmd = `"${keytoolBin}" -genkeypair -v -keystore "${KEYSTORE_PATH}" -alias "${alias}" -keyalg RSA -keysize 2048 -validity 10000 -storepass "${storePassword}" -keypass "${keyPassword}" -dname "${dname}"`;

  try {
    execSync(keytoolCmd, { stdio: 'inherit' });
    console.log('\n✅ Successfully generated release keystore!');

    // Write local signing.properties (git-ignored)
    const signingProps = [
      '# Local release signing configuration for SINBHA APK',
      '# This file is ignored by Git and must NEVER be committed.',
      `RELEASE_STORE_FILE=sinbha-release.keystore`,
      `RELEASE_KEY_ALIAS=${alias}`,
      `RELEASE_STORE_PASSWORD=${storePassword}`,
      `RELEASE_KEY_PASSWORD=${keyPassword}`
    ].join('\n');

    fs.writeFileSync(SIGNING_PROPERTIES_PATH, signingProps, 'utf8');
    console.log(`✅ Created ${SIGNING_PROPERTIES_PATH} (automatically ignored by Git).`);

  } catch (err) {
    console.error('❌ Failed to run keytool:', err.message);
    process.exit(1);
  }
}

console.log('\n' + '='.repeat(60));
console.log('🔐 SAFE BACKUP INSTRUCTIONS (NEVER COMMIT TO GIT):');
console.log('1. Keep your "sinbha-release.keystore" and "signing.properties" backed up');
console.log('   in a secure private folder (e.g., Google Drive, USB drive, or 1Password).');
console.log('2. If you lose this key, you cannot update your installed app without');
console.log('   uninstalling first!');
console.log('='.repeat(60) + '\n');
