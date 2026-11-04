# SINBHA Codebase Status & Honest Implementation Audit

**Current Version:** `v1.4.27` (Android `versionCode: 54`)  
**Date of Audit:** November 4, 2026  
**Test Suite Status:** 280 passed across all unit/integration suites (including 7 dedicated C2.13 LLM provider plan tests and 6 C2.12 reliability tests); 98/98 passed in Agent Evaluation Suite (C4); 14/14 passed in Electron Security Suite.  
**Build & CI Status:** GitHub Actions for both Android APK (`android-release.yml`) and Windows Installer (`windows-release.yml`) configured for `v1.4.27`.

---

## 1. Master Status Table

| Phase / Step | Built? | Version | What Automated Tests Cover & Parts Using Fakes | What Has NOT Been Checked on Real Devices | Known Bugs & Shortcuts |
|---|---|---|---|---|---|
| **C2.13: LLM Provider Plan & Honest Windows Settings Launch** | **Yes** | v1.4.27 | **Covered:** Honest Windows Settings verification (removed `ApplicationFrameHost.exe` background false-positive; verified real `SystemSettings.exe` / window appearance or fails with `launch_timeout`); dynamic provider chain configuration (`build_ordered_provider_chain`): Groq (`gpt-oss-20b`/`120b`) &rarr; Google AI Studio (Gemini Flash direct fallback) &rarr; OpenRouter (paid fallback) &rarr; Dev Local (strictly rejected in production environments); dynamic 1-hour cached model discovery from `/models` preventing 404s; DEV_MODE telemetry endpoint (`/api/diagnostics/llm-usage`) tracking tokens today per provider/model/user and errors by type; deterministic cost safety guards ($1.00 daily spend cap with 80% alert, 150k token per-user limit) written by code; provider toggling and data-use privacy disclosures in settings.<br>**Fakes:** Tests mock LLM API endpoints and simulate sequential provider failures. | Real Google AI Studio API key latency on cellular networks; physical token usage under large multi-user spikes. | When free Groq hit 200,000 TPD on 120b, automatic failover seamlessly routes to 20b or Gemini Flash. |
| **C2.12: Reliability Polish from Real Chat Tests** | **Yes** | v1.4.26 | **Covered:** Windows Store (UWP) apps indexed via `Get-StartApps` and launched via AppID with argument arrays; window/app frame (`ApplicationFrameHost`, `SystemSettings`) verification instead of exe name; `ms-settings:` subpages tool; Android settings intents (`ACTION_BLUETOOTH_SETTINGS`, `ACTION_WIFI_SETTINGS`, etc.); LLM 429 backoff and automatic provider/model fallback; token capping on OpenRouter to avoid 402; complete removal of server `pyautogui` imports; Android companion truthful accessibility status reporting (`enabled`, `blocked_by_restricted_settings`, `disabled`, `missing`) with exact Settings guidance; structured safety confirmation cards in chat UI; presence threshold relaxed to 90s with exact last-seen elapsed time reporting.<br>**Fakes:** Tests mock target hardware where device is offline or absent; LLM 429 and backoff mocked via unittest mocks. | Deep OEM Android 14+ specific accessibility restriction toggles across every manufacturer skin. | If physical Windows machine has completely disabled PowerShell or restricted execution policy, AppID indexing falls back to static dictionary. |
| **C2.11: Truthful "Not Installed" & Real Stage Tables** | **Yes** | v1.4.24 | **Covered:** Removed all silent website/browser/shell fallbacks for unknown apps; unknown apps return `not_installed` with top 3 fuzzy candidates; verified real app launches on phone (package foreground check) and laptop (process/window appearance check); stage table wired to real command IDs with exact timestamps; Windows client reports installed app catalog to server.<br>**Fakes:** Tests mock OS process lists and Android package manager. | Apps with non-standard launch splash screens taking >8s. | In some heavily-modified Android ROMs, `isPackageInForeground` can report false negative if the app uses multiple processes. |
| **C2.10: Real Device Path, Stage Tables & Version Safety** | **Yes** | v1.4.23 | **Covered:** Real device check executes via identical chat path (`relay_command`); strict verification (real apps pass ONLY on `succeeded`, nonexistent app passes ONLY on `not_installed`, timeouts ALWAYS fail); 6-stage lifecycle table tracking (`created`, `delivered`, `received`, `started`, `result_sent`, `result_stored`) with first missing stage detection; dropped-WebSocket recovery via poller (`ws_sent` &rarr; `delivered`); WebSocket keepalive ping every 15s (beating Render 55s idle timeout); version safety clamping (`min_version <= latest_published`); exact chat rejection format (`"Your phone/laptop app is version X, please update to Y."`); separate Local Launcher Test section; Gradle plugin repository redundancy (`gradlePluginPortal` + `repo1.maven.org`).<br>**Fakes:** Tests mock target hardware where device is offline or absent. | Long-term WebSocket connection stability on physical mobile networks when moving across cell towers. | If a physical device is powered off or battery dies, commands remain unexecuted until expiration (10s chat / 60s background). |
| **C2.9: Real Device Execution & Verification** | **Yes** | v1.4.21 | **Covered:** Identity alignment between native OS & WebView, local-only command trace in Diagnostics, 6-app Real Device Check endpoint (`/api/devices/real-device-check`), complete removal of unconditional fallbacks, active window verification for typing/keys, clipboard restore, Android package foreground detection, store catalog protection, client version gate (`CLIENT_OUTDATED`).<br>**Fakes:** Tests mock OS window handles & processes where hardware is absent. | Real-world non-standard Windows apps (e.g. customized shortcuts without target exes) and aggressive OEM Android battery killers. | If a Windows app has a slow splash screen (>8s), the launcher times out and reports `launch_timeout`. |
| **C1: Agent Loop & Tool Registry** | **Yes** | v1.4.5 (refined), v1.4.0 (initial) | **Covered:** Tool registry dispatch, JSON schema validation, permission levels (0-4), task memory persistence across turns, step log generation.<br>**Fakes:** All LLM calls mocked via `unittest.mock` / fake client responses; simulated conversation turns. | Live multi-turn conversations where the user interrupts via chat during active LLM generation; complex tool chains where an external network fails mid-plan. | If LLM outputs malformed JSON or markdown-wrapped JSON, recovery falls back to basic regex extraction; prompt token budgeting truncates history bluntly. |
| **C2: Laptop Tools (Local Execution)** | **Yes** | v1.4.5 | **Covered:** Safe typing validation, key combination allowlists, forbidden typing guards (passwords/OTPs/cards), app alias matching, URL sanitization.<br>**Fakes:** OS process execution (`subprocess.Popen`), active window detection (`win32gui`), and browser launching are mocked in Python unit tests. | Handling non-standard Windows app paths (e.g., portable apps, Microsoft Store apps with encrypted virtual paths); non-English Windows locales with translated app titles. | Windows focus switching can fail silently if another application runs with elevated Administrator privileges (UAC window isolation). |
| **C2.5: Observable & Truthful Device Actions** | **Yes** | v1.4.6 | **Covered:** Command packet schema validation, status progression (`queued` &rarr; `delivered` &rarr; `started` &rarr; `succeeded`/`failed`), capability handshake.<br>**Fakes:** Device WebSockets and responses are mocked via async queues. | Disconnections occurring precisely during packet transmission; mobile OS killing companion app immediately after receiving command before writing status. | If a device receives a command and crashes, timeout is 10s before server marks it timed out. |
| **C2.6: Android Command Channel & Scoped Tokens** | **Yes** | v1.4.7 | **Covered:** Token scoping, command dispatch, unified waiter resolution, channel error responses.<br>**Fakes:** Android OS intents and Android companion service are mocked using Python mock relays. | Aggressive OEM battery killers (Xiaomi MIUI/HyperOS, Samsung OneUI, OnePlus OxygenOS killing `CompanionService` after deep doze); boot restart on devices where "Autostart" is disabled by default. | If Android companion WebSocket drops, polling fallback occurs every ~30s, causing perceptible latency if socket dies silently. |
| **C2.7: Phone & Command Reliability** | **Yes** | v1.4.11 | **Covered:** Schema parity between platforms, late confirmations arriving after timeout, deduplication of commands, app name synonyms.<br>**Fakes:** Simulated network latency delays, simulated late WebSocket packets, simulated duplicate delivery. | Real cellular network switching (e.g., 4G/5G to Wi-Fi mid-command handover); packet arrival when phone has poor 2G/EDGE connectivity. | Chat messages update retroactively on late confirmation via UI DOM injection if the user hasn't refreshed or navigated away from the page. |
| **C2.8: Persistent DB Command Relay & Multi-Worker** | **Yes** | v1.4.13 | **Covered:** Multi-process/multi-worker SQLite sharing, commands sent by worker A polled and answered by worker B, late confirmation persistence, expiration cleanup, 50-command stress test.<br>**Fakes:** Simulated workers running in pytest against a local test database rather than full multi-node Gunicorn cluster. | Real high-concurrency production load across multiple Render instances with Neon Postgres connection pool limits. | SQLite database locks if two local workers write simultaneously in fast succession during testing (mitigated in Postgres, but SQLite WAL mode needed for tests). |
| **Step 17: Email Verification & Password Reset** | **Yes** | v1.4.14 | **Covered:** Token generation, expiration, rate limiting, hashing, password change with valid token, rejection of reused tokens, first-device trust.<br>**Fakes:** SMTP transport is mocked using `unittest.mock`; email delivery inbox is not real in tests. | Real SMTP deliverability into spam folders (Gmail/Outlook SPF/DKIM/DMARC headers); email links opened in external mobile browser vs in-app webview. | If SMTP credentials fail or quota is reached on Render, the user receives a generic error; retry queue for bounced emails is not built. |
| **Step 1C: Post-Step 17 & C3b Safety & Cleanup** | **Yes** | v1.4.16 | **Covered:** Production database URL guard refusal, strict device platform validation, rejection of undeclared/guess platforms, migration script for legacy accounts, relay plain rejection logging.<br>**Fakes:** Neon production strings simulated to assert refusal; simulated client device packets. | Old physical devices running v1.1.x that try to reconnect without sending the explicit platform string. | Legacy devices connecting with ambiguous platform strings are rejected with a 400 error rather than automatically negotiated. |
| **C3a: Windows Screen Agent** | **Yes** | v1.4.10 | **Covered:** Never-capture window titles (passwords, banks), safe typing validation, action gating (buy, pay, delete), LLM visual reasoning parsing, image cropping, mock screen task loop.<br>**Fakes:** Screenshots are synthetic PIL images with mock buttons; desktop click/type execution is mocked; active window handles are mocked. | Multi-monitor setups with mismatched DPI scalings (e.g. 150% 4K laptop + 100% 1080p monitor); Direct3D/Vulkan exclusive fullscreen games/apps that block GDI desktop capture; Windows UAC secure desktop prompts (which freeze GDI capture). | OCR/Vision bounding box drift when scaling coordinates from downscaled JPEG back to native screen resolution; does not detect non-English sensitive window titles. |
| **C3b: Managed Chrome with Playwright** | **Yes** | v1.4.15 | **Covered:** Profile isolation path check (`~/.sinbha/browser_profile`), clear data safety, 8 semantic tools against local HTML fixtures, hidden prompt injection rejection, action gating on form submission, dry-run mode, URL allowlist.<br>**Fakes:** Ran against local file URLs (`file:///.../test_page.html`) rather than live websites; mocked external network calls. | Live websites with Cloudflare turnstile, complex shadow DOMs, Canvas-rendered UI (e.g., Google Docs / Figma), or real Meesho checkout on live network with dynamic popups. | Playwright requires Chrome to be installed; headless is disabled (it runs visible), so if user clicks around or minimizes Chrome during execution, Playwright click focus can be affected. |
| **C4: Agent Evaluation Suite** | **Yes** | v1.4.16+ | **Covered:** 98 scenarios: app resolution, device disambiguation, multi-step tasks, follow-ups, misspellings, Hinglish, delayed results, injection in web/chat/notifications, STOP handling, secret typing refusal, Section 14A money invariants (COD only, margin 0, price change, duplicate order, tamper). All 98 pass.<br>**Fakes:** Completely built on `fake_devices.py` (FakeLaptop, FakePhone, FakeBrowser) simulating device responses and tool executions. | Live real-device evaluation run (`--live` flag implemented, but not executed against live paired phones/laptops for all 98 scenarios). | Evals test the orchestrator and decision logic against synthetic device contracts, not physical Android touch responsiveness or Windows OS event queues. |
| **D1: Android Screen Agent (Accessibility Service)** | **Yes** | v1.4.17 (broken CI) &rarr; v1.4.20 (fixed) | **Covered:** Parsing fake accessibility tree nodes, element roles, bounds, clickability; never-touch package detection; action gating verbs; secret typing rejection; emergency STOP; timeout enforcement.<br>**Fakes:** Synthetic JSON accessibility trees; mock device bridge. | Real Android OEMs (Samsung, Xiaomi, Vivo) with customized accessibility permissions; apps that mark their views as `FLAG_SECURE` or use non-standard Flutter/React Native custom canvas rendering without accessibility semantics; real floating window overlay permissions across Android 12, 13, 14. | On Android, if an app does not expose accessible nodes (e.g. game or pure Canvas), accessibility tree is empty, falling back to pure coordinate clicks which are fragile across different screen resolutions. |
| **D2: Messages Assistant** | **Yes** | v1.4.18 (broken CI) &rarr; v1.4.20 (fixed) | **Covered:** Volatile memory inbox (zero DB storage), banking/UPI notification filter, WhatsApp tree reader, prompt injection / untrusted instruction detection ("send your OTP"), style drafting, action gating before sending, approved reply dispatch.<br>**Fakes:** Simulated notification payloads, simulated WhatsApp accessibility tree snapshots. | Real incoming WhatsApp notifications on dual-SIM devices; WhatsApp UI variations across WhatsApp regular vs WhatsApp Business; Android notification access permission toggle on Android 13+ restricted settings. | WhatsApp chat reading depends on WhatsApp's current UI node structure (e.g. `conversation_text_row` or contact names in app header). If WhatsApp updates its layout, the accessibility parser may fail to locate the message bubbles. |
| **D3: Official Data Tools (YouTube & Gmail)** | **Yes** | v1.4.19 (broken CI) &rarr; v1.4.20 (fixed) | **Covered:** YouTube API response parsing, rounding disclaimer, missing API key handling; Gmail OAuth scope verification (`gmail.readonly`, `gmail.compose`), email drafting, phishing/injection detection, gated sending.<br>**Fakes:** Google OAuth exchange and Google HTTP API endpoints (YouTube Data API v3 and Gmail REST API) are mocked with synthetic JSON responses. | Real OAuth user consent flow through a browser popup; real token refresh when refresh_token expires; live YouTube API quota limits (10,000 daily units cap); live Gmail user with 1,000+ unread emails. | If Google OAuth credentials (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`) or YouTube API key are not set in environment variables, tools return error notices. Draft creation creates an actual Gmail draft via API, but requires the user to authenticate via Google OAuth first. |
| **Reminders & Alarms** | **Yes** | v1.1.2 - v1.4.4 | **Covered:** Native alarm scheduler, full-screen alarm window, lockscreen wake locks, snooze, text-to-speech voice, Windows chime.<br>**Fakes:** Timers are simulated in pytest. | Exact ring behavior on Android when device is in deep Doze mode without battery optimization whitelist. | Audio playback volume is tied to device stream volume; if phone or laptop is muted in hardware, the alarm triggers visually without sound. |
| **Device Pairing & WebSockets** | **Yes** | v1.0.7 - v1.4.13 | **Covered:** Pairing token authentication, QR code pairing, heartbeat latency calculation, WebSocket keep-alive, disconnect detection.<br>**Fakes:** Python test clients connecting over TestClient / mock sockets. | Simultaneous multi-device reconnection storms when server restarts on Render. | Render free-tier spins down after 15 minutes of inactivity; WebSocket disconnects when server spins down until external ping awakens it. |

---

## 2. Places Where the Code Reported Success Without Certainty (Resolved in v1.4.21 / C2.9)

In Step C2.9, all unconditional fallbacks were audited and replaced with truthful verification:

### 1. Fallback Returns in `app/agent_tools.py` (FIXED in v1.4.21)
All 6 tool fallback returns (`handle_open_url`, `handle_open_app`, `handle_type_text`, `handle_press_keys`, `handle_send_note`, `handle_ring_phone`) have been changed to:
```python
return {
    "success": False,
    "status": "unconfirmed",
    "message": "I sent it to your device, but could not confirm receipt.",
}
```
The server NEVER claims success unless the device explicitly confirms execution.

---

### 2. Windows Electron Client Process Spawning (`electron/command_security.js` - FIXED in v1.4.21)
`openAppWithFallback` now awaits `verifyProcessAppeared(exeName, 8000)` using PowerShell window & process checking. If the window/process does not appear within 8 seconds, it reports `launch_timeout` (`success: false`).
Typing and key presses verify that the intended target window is active in the foreground (`getActiveWindowInfo`), safely preserve and restore the user's prior clipboard, and report `"sent, not verified"` if foreground focus cannot be confirmed.

---

### 3. Android Screen Agent Verification (`SinbhaAccessibilityService.kt` - FIXED in v1.4.21)
`openAppByPackage` now waits for window-state transitions confirming the target package is in the foreground, or returns `"sent, not verified"`. Tap operations report `"tap sent"` (never `"worked"`). Scrolls verify bounding box movement and report `"no movement"` if unchanged.

- **`safeTypeInput` (Lines 529-545)**:
  Text is copied to the system clipboard via `clipboard.writeText(text)` and pasted via `WScript.Shell SendKeys('^v~')`:
  ```javascript
  const psScript = `$ws = New-Object -ComObject WScript.Shell; Start-Sleep -Milliseconds 300; $ws.SendKeys('${sendKeysKeys}')`;
  ```
  *Issue:* If PowerShell exits with status code 0, the function returns `{ success: true }`. However:
  1. It has no way of verifying which window actually had focus at that moment. If another window popped up (or Windows focus was on the desktop), the text was pasted there.
  2. It leaves sensitive typed text in the operating system clipboard without wiping it.
  3. If the application does not accept `Ctrl+V` (e.g. some command terminals or custom editors), the paste fails silently while reporting success.

- **`safePressKeys` (Lines 1025-1035)**:
  Sends keystrokes via `WScript.Shell SendKeys`:
  ```javascript
  const psScript = `$ws = New-Object -ComObject WScript.Shell; Start-Sleep -Milliseconds 150; $ws.SendKeys('${sendKeysToken}')`;
  ```
  *Issue:* Reports `{ success: true }` solely because PowerShell executed without throwing an error. It cannot verify whether the targeted application window was active or whether it processed the key.

---

### 3. Android Client Activity & Action Dispatch (`SinbhaAppLauncher.kt` & `SinbhaAccessibilityService.kt`)
- **`SinbhaAppLauncher.launchIntentSafely` (`SinbhaAppLauncher.kt` lines 364-375)**:
  ```kotlin
  context.startActivity(launchIntent)
  return LaunchResult(
      success = true,
      app = appName,
      packageName = packageName,
      method = if (canOverlay) "$method+overlay_exemption" else "$method+direct_start"
  )
  ```
  *Issue:* `context.startActivity()` in Android is an asynchronous, fire-and-forget intent dispatch. Once the Android framework accepts the intent without throwing a security exception, `success = true` is immediately reported. If the app crashes on startup (e.g., runtime crash in `Application.onCreate()`), or is immediately terminated by Android's low-memory killer, the server is already told that the app launched successfully.

- **`SinbhaAccessibilityService.openAppByPackage` (`SinbhaAccessibilityService.kt` lines 580-588)**:
  ```kotlin
  startActivity(launchIntent)
  return result.apply {
      put("success", true)
      put("action", "open_app")
      put("package", packageName)
      put("message", "Opened $packageName")
  }
  ```
  *Issue:* Reports success immediately upon intent dispatch without waiting for an accessibility window state event (`TYPE_WINDOW_STATE_CHANGED`) to confirm that the package actually rendered in the foreground.

- **`SinbhaAccessibilityService.tapCoordinates` (`SinbhaAccessibilityService.kt` lines 358-385)**:
  ```kotlin
  dispatchGesture(gesture, object : GestureResultCallback() {
      override fun onCompleted(gestureDescription: GestureDescription?) { ... }
  })
  ```
  *Issue:* `onCompleted` only confirms that the touch gesture was injected into the Android display digitizer. It does not verify whether any UI element responded to the touch, or whether the click was swallowed by an overlay.

- **`SinbhaAccessibilityService.scroll` (`SinbhaAccessibilityService.kt` lines 483-520)**:
  ```kotlin
  val ok = scrollableNode.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
  ```
  *Issue:* `performAction()` returning `true` only means the view received the action. If the view was already at the absolute bottom or top of the page, no actual scrolling occurred, but `success = true` is reported.

---

### 4. Web Intelligence / Price Searches (`app/search.py` & `app/web_intelligence.py`)
- When a user asks about local store prices (e.g., "Check the price of headphones on our local store"), if no specific local store URL is supplied, the agent searches public web indexes (DuckDuckGo / Tavily).
- It extracts generic web snippets from global or national tech sites (e.g., Yahoo Tech, Amazon US), and responds with specific dollar figures without verifying whether those prices apply to the user's specific local store or currency.
- *Issue:* It presents web-scraped generalities as answers to specific local queries without explicitly stating "I could not locate your specific local store's catalog".

---

## 3. What Has Been Proved on Real Devices vs What Remains

### What has been proved on real devices:
1. **Device Pairing**: Real Android Companion and real Windows PC pairing tokens and database registration.
2. **WebSocket & Heartbeat**: Real-time heartbeat detection (both Android and Windows devices show `Heartbeat: 0s ago, WebSocket: connected` in live server diagnostics).
3. **Truthful Timeout Reporting (Step C2.7 / C2.8)**: When commands to the Windows PC or Android phone fail to report back within 10 seconds, the agent does NOT report "Opened X". It reports:
   > *"I sent it to your Windows PC, but could not confirm (timed out after 10s) (Heartbeat: 0s ago, WebSocket: connected)."*
4. **Secrets Verification**: Zero secrets committed across the entire repository.
5. **CI Build Success**: Release artifacts `SINBHA.apk` (Android) and `SINBHA-Setup.exe` (Windows) compile cleanly and build in GitHub Actions for `v1.4.20`.

### What has NOT been checked on real physical devices:
1. **Physical touch verification on D1 (Android Screen Agent)**: The accessibility tree and tap actions were verified against unit mocks, not on a physical Android handset with diverse screen resolutions.
2. **WhatsApp accessibility reading on D2**: Tested against simulated WhatsApp node hierarchies; not tested against live WhatsApp chat updates on a physical phone.
3. **Gmail & YouTube live API calls on D3**: Tested against mock responses; real Google OAuth consent flow and live token refreshes have not been executed with a real Google account.
4. **Live Playwright execution on C3b against live e-commerce websites**: Tested against local fixture pages (`test_page.html`), not live meesho.com checkout flows.
5. **Windows Electron companion response to remote commands**: While the Windows PC maintains active WebSocket connection and heartbeat, remote `open_app` commands are currently timing out after 10s because the local Electron background event dispatcher is not processing or responding to incoming command payloads.

---

## 4. Pending Master Plan Phases

- **Phase 5 (E1, E2)**: Companion check-ins, study partner, daily check-in loop, voice assistant (Not yet built).
- **Phase 6 (F1)**: Firebase Cloud Messaging push fallback (Not yet built).
- **Phase 7 (M0 - M9)**: Meesho reselling pilot & automated order worker (Not yet built).
- **Phase S (S1 - S4)**: SINBHA Shop storefront & COD checkout (Not yet built).
- **Phase 8**: Friends beta and launch hardening (Not yet built).

