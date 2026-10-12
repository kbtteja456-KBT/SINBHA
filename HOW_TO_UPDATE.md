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

### Step 1: Bump Version with One Command

You don't need to manually edit files! Just run this single command in your terminal:

```powershell
npm run bump
```

This single command automatically:
* Increments the version in `package.json` (e.g. `1.0.1` ➔ `1.0.2`)
* Increments `versionCode` by +1 in `android/app/build.gradle` (e.g. `2` ➔ `3`)
* Synchronizes `versionName` in `android/app/build.gradle`

*(Or if making a bigger update, you can run `npm run bump minor` for `1.1.0`)*

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

You can build **Android (`.apk`)**, **Windows (`.exe`)**, or both!

#### 📱 For Android APK (`SINBHA.apk`):
1. In your **SINBHA** repo on GitHub, click **Actions**.
2. Click **Build and Release Android APK** on the left menu.
3. Click **Run workflow** ➔ **Run workflow**.
*(Or via tag: `git tag android-v1.0.2; git push origin android-v1.0.2`)*

#### 💻 For Windows Installer (`SINBHA-Setup.exe`):
1. In your **SINBHA** repo on GitHub, click **Actions**.
2. Click **Build and Release Windows Desktop App** on the left menu.
3. Click **Run workflow** ➔ **Run workflow**.
*(Or via tag: `git tag windows-v1.0.2; git push origin windows-v1.0.2`)*

---

### Step 4: What Happens Automatically
* **Android**: GitHub Actions compiles the signed `SINBHA.apk` and publishes it with `SINBHA.apk.sha256`.
* **Windows**: GitHub Actions compiles the Windows NSIS installer `SINBHA-Setup.exe` and publishes it with `SINBHA-Setup.exe.sha256`.
* Both files appear in your public **`sinbha-releases`** repository!

---

## 🔗 4. How to Share the Apps Every Time

GitHub provides **permanent direct download links** that never change. They always point to the newest version automatically:

👉 **Android APK Permanent Download:**
```text
https://github.com/kbtteja456-KBT/sinbha-releases/releases/latest/download/SINBHA.apk
```

👉 **Windows .EXE Permanent Download:**
```text
https://github.com/kbtteja456-KBT/sinbha-releases/releases/latest/download/SINBHA-Setup.exe
```

* Send either link to anyone or bookmark them.
* Whenever you release an update, anyone who opens those links downloads the newest version immediately!
* Public Releases Webpage:
  `https://github.com/kbtteja456-KBT/sinbha-releases/releases`

---

## 🔒 Important Security Rules

1. **Never delete or regenerate your keystore file**:
   Android will **only** update an installed app if the new APK is signed with the exact same keystore key. Keep your `android/sinbha-release.keystore` backed up safely.
2. **Always increment `versionCode`**:
   Android ignores or rejects APKs if the `versionCode` is the same as or lower than the currently installed version (`npm run bump` does this automatically).

