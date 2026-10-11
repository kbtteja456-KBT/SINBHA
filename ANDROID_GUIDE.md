# 🌸 SINBHA for Android — Complete Setup & Testing Guide

This guide walks you through building, installing, and testing the **SINBHA Android App (APK)** on your **OnePlus / Oppo / Realme** phone running **Android 15**.

---

## 📱 1. Architecture Overview

- **WebView Container**: The app loads `https://sinbha-backend.onrender.com` inside a secure Android WebView. All UI improvements and updates deploy instantly from Render without needing a new APK install.
- **Waking Up Screen**: If Render is cold-starting or the connection drops, a local pink-themed recovery screen automatically pings `/api/health` every few seconds and transitions seamlessly as soon as the server is awake.
- **Native Kotlin Plugin (`SinbhaPlugin` & `OverlayBirdService`)**:
  - **Floating Overlay Bird**: Uses Android's `SYSTEM_ALERT_WINDOW` permission with strict touch pass-through (`FLAG_NOT_TOUCH_MODAL | FLAG_NOT_FOCUSABLE`). It never blocks touches anywhere on your phone except directly on the bird and its note card.
  - **Sprite Animation**: Flaps with the 4 artwork frames (`bird_wings_up`, `bird_glide`, `bird_wings_down`, `bird_landed`) along a smooth curved Bezier swoop path across the screen.
  - **One-Tap Actions**: Done (completes task), Snooze (15m), Open Chat (brings SINBHA to the front), or Dismiss (X).
  - **Accessibility**: Automatically honors Android's system `reduce-motion` setting by fading the bird smoothly into position without rapid flapping or curved swoops.
  - **Exact Alarms**: Uses `AlarmManager.setExactAndAllowWhileIdle()` to wake the device at the exact scheduled minute, even in Doze mode.
  - **Boot Resilience**: Re-registers all scheduled alarms automatically after phone reboot (`BOOT_COMPLETED`) from Android's encrypted cache.
  - **Notification Fallback**: If the "Display over other apps" permission is not granted, shows a high-priority Heads-up Notification with direct `Done` and `Snooze` action buttons.
  - **Quiet Hours & DND**: Respects user Quiet Hours, Emergency STOP, and Android system Do Not Disturb filters.
- **Security & Keystore**:
  - No passwords or secrets are ever stored on the phone. When you log in, an authenticated session token is stored in Android's hardware-backed `EncryptedSharedPreferences`. Native actions authenticate directly via `Authorization: Bearer <device_token>`.
  - Cleartext traffic disabled (HTTPS only).
  - Remote WebView debugging disabled in release builds.
  - `android:allowBackup="false"` to prevent unauthorized device extraction.

---

## 🛠️ 2. Step-by-Step: Installing Android Studio & Running on Your Phone

### Step 2.1: Download & Install Android Studio
1. Go to [https://developer.android.com/studio](https://developer.android.com/studio) and download **Android Studio** (Ladybug or latest).
2. Run the installer with default options.
3. On first launch, follow the Setup Wizard:
   - Select **Standard Setup**.
   - Check **Android SDK**, **Android SDK Platform**, and **Android Virtual Device**.
   - Accept the licenses and let it finish downloading components.

### Step 2.2: Open SINBHA Android Project in Android Studio
1. Open Android Studio.
2. Click **Open** (or `File > Open`).
3. Browse to your SINBHA project folder and select the **`android`** subfolder:
   `c:\Users\kosur\OneDrive\Desktop\SINBHA\android`
4. Android Studio will open the project and automatically download Gradle and dependencies.
5. Wait for the bottom status bar to show **Gradle sync finished** (takes 1–2 minutes on first run).

---

## 📲 3. Enable USB Debugging on Your OnePlus / Oppo / Realme Phone (OxygenOS / ColorOS)

ColorOS and OxygenOS have a developer settings menu:

1. **Enable Developer Options**:
   - On your phone, open **Settings**.
   - Tap **About device** > **Version** (or **Software information**).
   - Tap **Version number** (or **Build number**) **7 times** quickly.
   - Enter your phone lock screen PIN/Pattern. You will see: *"You are now in Developer mode!"*
2. **Enable USB Debugging**:
   - Go back to **Settings** > **Additional settings** (or **System settings**).
   - Tap **Developer options**.
   - Turn ON **USB debugging**.
   - Turn ON **Install via USB** (if present on your OxygenOS/ColorOS version).
3. **Connect to Your PC**:
   - Connect your phone to your computer with a USB cable.
   - On your phone screen, a prompt will appear: *"Allow USB debugging from this computer?"*.
   - Check **"Always allow from this computer"** and tap **Allow**.

---

## 🚀 4. Run the App Directly on Your Phone

1. In Android Studio, look at the top toolbar device selector dropdown.
2. Select your OnePlus / Oppo / Realme device (it will show your model name, e.g., `OnePlus 12` / `CPH...`).
3. Click the green **Run (▶)** button (or press `Shift + F10`).
4. Android Studio will compile the app and install it directly onto your phone. The app will launch with the cute elephant splash screen!

---

## ⚙️ 5. Crucial OnePlus / ColorOS Background Settings (Prevent App Freezing)

OxygenOS and ColorOS have battery management that can freeze background apps unless exempted:

1. **Auto-Launch / Autostart**:
   - Go to **Settings** > **Apps** > **Auto-launch** (or **App battery management**).
   - Find **SINBHA** and enable:
     - ✅ **Allow auto-launch**
     - ✅ **Allow secondary launch**
     - ✅ **Allow background activity**
2. **Battery Optimization**:
   - Go to **Settings** > **Battery** > **More settings** > **Optimize battery use**.
   - Find **SINBHA** and set it to **Don't optimize**.
3. **In-App Permissions Setup**:
   - Inside SINBHA, tap the top gear icon (Settings) and scroll to **📱 Android Companion & Permissions**.
   - Tap each button to enable:
     - 🔔 **Notifications**: Tap *Grant Permission* > Allow.
     - 🕊️ **Display Over Other Apps**: Tap *Grant Permission* > Toggle ON for SINBHA.
     - ⏰ **Exact Alarms**: Tap *Grant Permission* > Toggle ON for SINBHA.
     - 🔋 **Battery Optimization**: Tap *Allow Background Running* > Tap Allow.
     - 🚀 **OxygenOS / ColorOS Auto-launch**: Tap *Open Auto-launch Settings* > Toggle ON.

---

## 🔐 6. Release Signing Key & Building the Signed APK

### Keystore Location & Safety
Your 2048-bit RSA release signing key has been generated at:
`c:\Users\kosur\OneDrive\Desktop\SINBHA\android\sinbha-release.keystore`
with configuration in:
`c:\Users\kosur\OneDrive\Desktop\SINBHA\android\signing.properties`

> [!CAUTION]
> **NEVER COMMIT YOUR KEYSTORE TO GIT.**
> Both files are already added to `.gitignore`.
> Back up `sinbha-release.keystore` and `signing.properties` to a safe personal location (e.g., your personal Google Drive or an encrypted USB drive).
> If you ever lose this key, you cannot release app updates with the same signature!

### Building the APKs
In Android Studio:
1. Go to the menu: **Build** > **Generate Signed Bundle / APK...**
2. Select **APK** and click **Next**.
3. Point to:
   - **Key store path**: Browse to `android/sinbha-release.keystore`
   - Enter your passwords from `android/signing.properties`.
4. Choose build variant **release** (or **debug** for quick testing).
5. Click **Finish**.
6. When done, click the **"locate"** notification in Android Studio. Your ready-to-share APK will be in:
   `android/app/build/outputs/apk/release/app-release.apk`
   Rename it to `SINBHA.apk`!

Or from the command line:
```bash
cd android
.\gradlew.bat assembleRelease
```
The signed APK will be at:
`android/app/build/outputs/apk/release/app-release.apk`

---

## 👥 7. How Friends Install & Receive Updates

### Installing Without the Google Play Store
1. Send them `SINBHA.apk` (via Google Drive link, Telegram, WhatsApp, or email).
2. When they tap the APK file on their phone:
   - Android will prompt: *"For your security, your phone is not allowed to install unknown apps from this source."*
   - They tap **Settings**, toggle **Allow from this source**, and go back.
   - Tap **Install**.

### Receiving Updates via Your Public `sinbha-releases` Repository
1. When you release a new version of SINBHA, create a release in your **public** repository:
   `https://github.com/kbtteja456-KBT/sinbha-releases`
2. Attach your compiled `SINBHA.apk` (and `SINBHA-Setup.exe` for Windows) as release assets and publish the release.
3. Update `MIN_APP_VERSION_ANDROID` and `LATEST_APP_VERSION_ANDROID` in your environment (or `app/main.py`).
4. **How the in-app update prompt finds it**:
   - The app periodically calls `/api/app/version-check` on your hosted backend.
   - If the installed app is below the minimum required version, the app displays the **"Update Required to Continue"** dialog with a button pointing directly to `https://github.com/kbtteja456-KBT/sinbha-releases/releases/latest`.
   - **Accidental Lockout Protection**: If a configuration typo sets `MIN_APP_VERSION` higher than `LATEST_APP_VERSION`, both the backend server and client apps automatically detect the discrepancy, ignore the invalid minimum version, log a warning, and prevent all users from being accidentally locked out!
5. Your friends tap **Download Update**, install the new APK, and all their logged-in data and settings remain completely intact without needing to uninstall!

### Publishing on Google Play Later: Pros & Cons
| Pros of Google Play | Cons of Google Play |
| :--- | :--- |
| • 1-tap installation with no "Unknown Sources" warnings | • $25 one-time developer fee |
| • Automatic silent background app updates | • Google Play requires 14–20 days of closed testing with 12 testers |
| • Google Play Protect verified badge | • Strict policies on `SYSTEM_ALERT_WINDOW` & exact alarms permissions |
| • Easy discovery via search | • App review delays (24–72 hours per update) |

*For you and your friends, distributing the APK via your GitHub Releases is faster, gives instant updates, and has zero approval delays!*

---

## 🧪 8. Complete Step-by-Step Testing Checklist

1. **Install & Login**:
   - Open SINBHA on your phone.
   - Log into your account (or create a new account).
   - Confirm you see your tasks and chat history.
2. **Instant Test of the Floating Bird**:
   - Open Settings in SINBHA > **Android Companion & Permissions**.
   - Tap **🕊️ Test Bird Flight**.
   - Go to your home screen or open YouTube / WhatsApp.
   - Within 2 seconds, watch the animated bird flap onto your screen along a smooth curved path, display a reminder note card, and perch.
   - Tap on the screen *outside* the bird: confirm outside touches pass straight through to whatever app you are using!
   - Tap **✓ Done**: confirm the bird swoops off the screen and dismisses gracefully.
3. **2-Minute Alarm with App Closed**:
   - In chat, send: `"Remind me to test coffee in 2 minutes"`
   - Tap **Confirm 🌸**.
   - Swipe away SINBHA from your recent apps list (force close it).
   - Lock your phone or use other apps.
   - After 2 minutes, verify that the exact alarm fires and the companion bird visits you right on cue!
4. **Phone Reboot Test**:
   - Set a reminder for 5 minutes in the future.
   - Completely restart your phone.
   - Do NOT open SINBHA after restarting.
   - Verify that when the minute arrives, the alarm fires right on time via `BootReceiver`!
5. **Update Gate Test**:
   - Temporarily set `MIN_APP_VERSION_ANDROID="2.0.0"` in `.env`.
   - Open SINBHA: confirm the pink Update Gate screen appears blocking older versions and offering the download link.
