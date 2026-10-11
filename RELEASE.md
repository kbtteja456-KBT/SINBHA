# 📦 SINBHA Desktop Release & Distribution Guide

This guide explains how to build the Windows installer (`SINBHA-Setup.exe`), distribute it to your friends, and publish automatic over-the-air updates.

---

## 1. How to Build the Windows Installer (`SINBHA-Setup.exe`)

Building the installer is 100% automated:

```powershell
# 1. Open your terminal in the SINBHA folder
cd "C:\Users\kosur\OneDrive\Desktop\SINBHA"

# 2. Run the build command
npm run build:win
```

### What Happens Behind the Scenes:
1. **Pre-Build Security Scan (`scripts/check_secrets.js`)**: Automatically scans the package. If any `.env`, database URL, or private API key is found, the build **immediately stops** to prevent leaking secrets.
2. **Bundling**: Only packages the lightweight desktop client, elephant icon, and transparent bird overlay.
3. **Packaging**: Creates an NSIS setup installer in the `dist/` folder:
   📁 **`dist/SINBHA-Setup.exe`**

---

## 2. Installing on Your Own PC (Or Sending to Friends)

1. Open the `dist` folder:
   ```powershell
   explorer dist
   ```
2. Double-click **`SINBHA-Setup.exe`**.
3. **Key Benefits**:
   - **No Admin Needed**: Installs into your user profile (`%LocalAppData%\Programs\SINBHA`). It will never ask for Windows Administrator permissions.
   - **Elephant Icon**: Places an official elephant icon on your Desktop and in your Start menu.
   - **Clean Uninstall**: Appears in Windows **Settings > Apps > Installed apps**, where it can be cleanly uninstalled anytime with 1 click.
   - **Connected to Cloud**: Instantly connects to your live server at `https://sinbha-backend.onrender.com`.

---

## 3. How Auto-Updates Work (In Simple Words)

SINBHA uses **`electron-updater`** to update itself automatically without friends needing to re-download an installer.

### Where Update Files Are Hosted:
We recommend creating a **separate, public GitHub repository** called:
👉 **`kbtteja456-KBT/sinbha-releases`**

- **Why separate?** Your main source code and project repository stay completely **private**, while only the built `.exe` and update metadata (`latest.yml`) are posted publicly for downloads!
- **How friends receive updates**:
  1. The app automatically checks for updates when opened, and every 4 hours in the background.
  2. When a new version is detected, it downloads silently.
  3. A friendly prompt appears:
     > *"Update Ready 🌸 SINBHA v1.0.1 is downloaded. Restart to apply and see what's new!"*
  4. On restart, the app opens with a cute **"What's New in v1.0.1"** card!

---

## 4. How to Test an Update (v1.0.0 to v1.0.1)

Follow these simple steps to test an update workflow:

### Step 1: Bump the Version Number
1. Open `package.json` and change:
   ```json
   "version": "1.0.1"
   ```
2. In `electron/config.js`, add what's new in `WHATS_NEW`:
   ```javascript
   WHATS_NEW: {
     '1.0.1': [
       '✨ Faster bird arrival animations',
       '🌸 Enhanced quiet hours scheduling'
     ]
   }
   ```

### Step 2: Build the New Release
Run:
```powershell
npm run build:win
```
This generates:
- `dist/SINBHA-Setup.exe` (v1.0.1)
- `dist/latest.yml` (the update manifest that tells existing apps a new version is available)
- `dist/SINBHA-Setup.exe.blockmap`

### Step 3: Publish to GitHub Releases
1. Create a public GitHub repo named `sinbha-releases` under your GitHub account (`kbtteja456-KBT`).
2. Go to **Releases** > **Draft a new release**.
3. Set the tag to `v1.0.1`.
4. Drag and drop these 3 files from your `dist/` folder:
   - `SINBHA-Setup.exe`
   - `latest.yml`
   - `SINBHA-Setup.exe.blockmap`
5. Click **Publish release**.

Any computer running `v1.0.0` will automatically detect `v1.0.1`, download it quietly, and show the update notification! 🌸
