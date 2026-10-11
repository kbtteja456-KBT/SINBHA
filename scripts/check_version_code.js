/**
 * Verification script:
 * 1. Verifies Android versionCode has increased compared to the previous git commit/release.
 * 2. Syncs versionName with package.json version.
 * 3. Fails the build immediately if versionCode did not increase.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const rootDir = path.resolve(__dirname, '..');
const packageJsonPath = path.join(rootDir, 'package.json');
const gradlePath = path.join(rootDir, 'android', 'app', 'build.gradle');

function main() {
  console.log('🔍 Checking Android version and versionCode...');

  // 1. Read package.json
  if (!fs.existsSync(packageJsonPath)) {
    console.error('❌ package.json not found!');
    process.exit(1);
  }
  const pkg = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
  const targetVersion = pkg.version;

  // 2. Read build.gradle
  if (!fs.existsSync(gradlePath)) {
    console.error('❌ android/app/build.gradle not found!');
    process.exit(1);
  }
  let gradleContent = fs.readFileSync(gradlePath, 'utf8');

  const codeMatch = gradleContent.match(/versionCode\s+(\d+)/);
  if (!codeMatch) {
    console.error('❌ Could not parse versionCode from android/app/build.gradle');
    process.exit(1);
  }
  const currentVersionCode = parseInt(codeMatch[1], 10);

  const nameMatch = gradleContent.match(/versionName\s+["']([^"']+)["']/);
  const currentVersionName = nameMatch ? nameMatch[1] : '';

  console.log(`ℹ️  Current build.gradle: versionCode = ${currentVersionCode}, versionName = "${currentVersionName}"`);
  console.log(`ℹ️  package.json version: "${targetVersion}"`);

  // Sync versionName with package.json if mismatched
  if (currentVersionName !== targetVersion) {
    console.log(`🔄 Syncing versionName in build.gradle to "${targetVersion}"...`);
    gradleContent = gradleContent.replace(/versionName\s+["'][^"']+["']/, `versionName "${targetVersion}"`);
    fs.writeFileSync(gradlePath, gradleContent, 'utf8');
  }

  // 3. Compare with previous git commit (HEAD~1)
  try {
    const prevGradle = execSync('git show HEAD~1:android/app/build.gradle', {
      cwd: rootDir,
      stdio: ['pipe', 'pipe', 'ignore'],
      encoding: 'utf8'
    });

    const prevMatch = prevGradle.match(/versionCode\s+(\d+)/);
    if (prevMatch) {
      const prevVersionCode = parseInt(prevMatch[1], 10);
      console.log(`ℹ️  Previous commit build.gradle: versionCode = ${prevVersionCode}`);

      if (currentVersionCode <= prevVersionCode) {
        console.error('\n======================================================');
        console.error('❌ BUILD ERROR: Android versionCode did NOT increase!');
        console.error(`   Previous: ${prevVersionCode}`);
        console.error(`   Current:  ${currentVersionCode}`);
        console.error('   Each Android release must have a strictly higher versionCode');
        console.error('   to prevent install errors and upgrade rejection on Android.');
        console.error('   Please increment versionCode in android/app/build.gradle.');
        console.error('======================================================\n');
        process.exit(1);
      }
    }
  } catch (e) {
    // Single commit repository or tag checkout where HEAD~1 is not available
    console.log('ℹ️  No previous commit to compare against; versionCode check skipped for initial history.');
  }

  console.log(`✅ Android version check passed: versionCode ${currentVersionCode}, version ${targetVersion}`);
}

main();
