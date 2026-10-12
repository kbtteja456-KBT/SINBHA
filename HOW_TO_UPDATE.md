# 🚀 SINBHA Update & Upgrade Guide

This guide explains how updates reach your phones and PCs, and gives you the exact step-by-step process whenever you make changes.

---

## ⚡ 1. The Two Types of Updates in SINBHA

### Type A: Web & AI Updates (Instant, No Download Needed!)
Because both Android and Windows load your hosted app from **`https://sinbha-backend.onrender.com`**:
* Any changes to chat, AI features, task UI, buttons, styles, or backend Python code **update instantly**.
* **Zero download required**: Whenever you deploy to Render, every phone and PC gets the update the second they open the app.

---

### Type B: Native App Updates (Requires New APK / EXE)
You only need to publish a new APK or Windows installer when you change **native system features**:
* Android background alarms or notification channels
* Flying bird overlay native window permissions
* Offline caching or new Capacitor native plugins
* App icon, splash screen, or app name

---

## 📱 2. How Phones and PCs Detect New Updates

1. **Automatic Detection**: Every time SINBHA opens on your phone or PC, it automatically checks your public repository:
   `https://github.com/kbtteja456-KBT/sinbha-releases/releases`
2. **Update Notification**: If the cloud version is newer than the installed version (e.g., `1.0.2` > `1.0.1`), a banner appears:
   > *"🌸 New version of SINBHA is available! Tap to update."*
3. **One-Tap Upgrade**:
   - On **Android**: Tapping download gets `SINBHA.apk`. Opening it upgrades the app **in-place**. All logins, tasks, and settings stay completely intact because both APKs are signed with your secret release key.
   - On **Windows**: The updater downloads in the background and prompts to restart.

---

## 🛠️ 3. Step-by-Step: How to Publish an Upgrade

Whenever you want to release a new version for Android and Windows, follow these 4 simple steps:

### Step 1: Update the Version Numbers on your PC

1. In **`package.json`**:
   Change `"version": "1.0.1"` to `"version": "1.0.2"`.
2. In **`android/app/build.gradle`**:
   * Change `versionCode 2` to `versionCode 3` *(must always go up by 1)*.
   * Change `versionName "1.0.1"` to `versionName "1.0.2"`.

*(Tip: Our automated script `npm run android:check-version` will ensure your version numbers are correct before building).*

---

### Step 2: Commit and Push your Changes

In VS Code terminal (or PowerShell), run:

```powershell
git add .
git commit -m "Release v1.0.2 with new features"
git push origin main
```

---

### Step 3: Trigger the Cloud Build

You have two easy ways:

#### Option A: One-Click in your Browser (Easiest)
1. Go to your **SINBHA** repository on GitHub.
2. Click **Actions** ➔ **Build and Release Android APK**.
3. Click **Run workflow** ➔ **Run workflow**.

#### Option B: Push a Git Tag from Terminal
```powershell
git tag android-v1.0.2
git push origin android-v1.0.2
```

---

### Step 4: What Happens Automatically
1. GitHub Actions spins up an Ubuntu cloud server with JDK 21 and Node 22.
2. It verifies all security checks and confirms `versionCode` increased.
3. It signs the APK using your secret keystore.
4. It attaches `SINBHA.apk` and `SINBHA.apk.sha256` to your public `sinbha-releases` repo.
5. All phones running SINBHA detect the new release and show the update button!

---

## 🔒 Important Security Rules

1. **Never delete or regenerate your keystore file**:
   Android will **only** update an installed app if the new APK is signed with the exact same keystore key. Keep your `android/sinbha-release.keystore` backed up safely.
2. **Always increment `versionCode`**:
   Android ignores or rejects APKs if the `versionCode` is the same as or lower than the currently installed version.
