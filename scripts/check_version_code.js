/**
 * Verification script:
 * 1. Verifies Android versionCode has increased compared to previous release tags.
 * 2. Syncs versionName in build.gradle with package.json version.
 * 3. Fails the build immediately if versionCode did not increase over previous releases.
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

  // 3. Compare versionCode with previous release tags
  let previousMaxVersionCode = 0;
  let comparisonSource = null;

  try {
    const rawTags = execSync('git tag -l "android-v*" "v*"', {
      cwd: rootDir,
      stdio: ['pipe', 'pipe', 'ignore'],
      encoding: 'utf8'
    }).trim();

    const currentRef = process.env.GITHUB_REF_NAME || '';
    const tags = rawTags
      ? rawTags.split('\n').map(t => t.trim()).filter(t => t && t !== currentRef)
      : [];

    for (const tag of tags) {
      try {
        const tagGradle = execSync(`git show "${tag}:android/app/build.gradle"`, {
          cwd: rootDir,
          stdio: ['pipe', 'pipe', 'ignore'],
          encoding: 'utf8'
        });
        const match = tagGradle.match(/versionCode\s+(\d+)/);
        if (match) {
          const vc = parseInt(match[1], 10);
          if (vc > previousMaxVersionCode) {
            previousMaxVersionCode = vc;
            comparisonSource = `tag ${tag}`;
          }
        }
      } catch (err) {
        // Tag doesn't have build.gradle
      }
    }
  } catch (err) {
    console.log('ℹ️  Could not fetch git tags.');
  }

  if (previousMaxVersionCode > 0) {
    console.log(`ℹ️  Highest previous release versionCode: ${previousMaxVersionCode} (from ${comparisonSource})`);
    if (currentVersionCode <= previousMaxVersionCode) {
      console.error('\n======================================================');
      console.error('❌ BUILD ERROR: Android versionCode did NOT increase!');
      console.error(`   Previous release: ${previousMaxVersionCode} (${comparisonSource})`);
      console.error(`   Current build:    ${currentVersionCode}`);
      console.error('   Each Android release must have a strictly higher versionCode');
      console.error('   to prevent install errors and upgrade rejection on Android.');
      console.error('   Please increment versionCode in android/app/build.gradle.');
      console.error('======================================================\n');
      process.exit(1);
    }
  } else {
    console.log(`ℹ️  No previous release tags found. Proceeding with initial release versionCode ${currentVersionCode}.`);
  }

  console.log(`✅ Android version check passed: versionCode ${currentVersionCode}, version ${targetVersion}`);
}

main();
