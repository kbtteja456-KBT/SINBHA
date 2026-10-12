// ========================================================
// SINBHA - Automated Version Bumper
// Automatically increments version in package.json and
// android/app/build.gradle (versionCode and versionName).
// Usage:
//   npm run bump          -> increments patch (e.g. 1.0.1 -> 1.0.2, versionCode 2 -> 3)
//   npm run bump minor    -> increments minor (e.g. 1.0.1 -> 1.1.0, versionCode 2 -> 3)
// ========================================================

const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const packageJsonPath = path.join(rootDir, 'package.json');
const gradlePath = path.join(rootDir, 'android', 'app', 'build.gradle');

function bump() {
  const type = process.argv[2] || 'patch'; // 'patch', 'minor', or 'major'

  if (!fs.existsSync(packageJsonPath) || !fs.existsSync(gradlePath)) {
    console.error('❌ Missing package.json or android/app/build.gradle');
    process.exit(1);
  }

  // 1. Read package.json
  const pkg = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
  const oldVersion = pkg.version;
  const parts = oldVersion.split('.').map(n => parseInt(n, 10));

  if (type === 'major') {
    parts[0] += 1;
    parts[1] = 0;
    parts[2] = 0;
  } else if (type === 'minor') {
    parts[1] += 1;
    parts[2] = 0;
  } else {
    // default: patch
    parts[2] += 1;
  }

  const newVersion = parts.join('.');
  pkg.version = newVersion;
  fs.writeFileSync(packageJsonPath, JSON.stringify(pkg, null, 2) + '\n', 'utf8');

  // 2. Read and update build.gradle
  let gradleContent = fs.readFileSync(gradlePath, 'utf8');

  const codeMatch = gradleContent.match(/versionCode\s+(\d+)/);
  if (!codeMatch) {
    console.error('❌ Could not parse versionCode from build.gradle');
    process.exit(1);
  }
  const oldCode = parseInt(codeMatch[1], 10);
  const newCode = oldCode + 1;

  gradleContent = gradleContent.replace(/versionCode\s+\d+/, `versionCode ${newCode}`);
  gradleContent = gradleContent.replace(/versionName\s+["'][^"']+["']/, `versionName "${newVersion}"`);
  fs.writeFileSync(gradlePath, gradleContent, 'utf8');

  console.log('\n🎉 VERSION BUMPED SUCCESSFULLY!');
  console.log(`📦 Version:     ${oldVersion} ➔ ${newVersion}`);
  console.log(`🔢 versionCode: ${oldCode} ➔ ${newCode}`);
  console.log('\n👉 Next steps to publish and share:');
  console.log(`   1. git add .`);
  console.log(`   2. git commit -m "Release v${newVersion}"`);
  console.log(`   3. git push origin main`);
  console.log(`   4. Go to GitHub Actions and click "Run workflow" (or run: git tag android-v${newVersion}; git push origin android-v${newVersion})`);
  console.log('\n🔗 Permanent download link to share with anyone:');
  console.log('   https://github.com/kbtteja456-KBT/sinbha-releases/releases/latest/download/SINBHA.apk\n');
}

bump();
