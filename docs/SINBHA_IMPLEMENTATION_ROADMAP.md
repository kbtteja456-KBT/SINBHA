# SINBHA — Phased Implementation Roadmap
**Audit Date:** November 5, 2026  
**Target Codebase Version:** `v1.4.28` (Android `versionCode: 55`)  
**Status:** PHASE 0 Audit Specification  

---

## 1. Roadmap Architecture Principles

1. **Preserve What Works:** Never break existing working code (Argon2 auth, Fernet encryption, tool registry, LLM failover, alarm scheduler, flying bird overlay).
2. **Strict Phase Gateways:** Each phase ends with real device verification. Never proceed to the next phase based solely on mocked tests.
3. **No Unverified Claims:** If an action cannot be verified on the operating system, report `sent_not_verified` or `needs_tap`. Never fake success.
4. **Zero Secrets in Git:** Never commit `.env`, keystores, or API tokens.
5. **Human Approval Gate:** All code changes require explicit review and approval before execution.

---

## 2. Phased Execution Roadmap

### PHASE 0 — COMPLETE SOURCE AUDIT (Current Phase)
- **Goal:** Comprehensive repository inspection and delivery of 4 master audit documents without modifying source code.
- **Files Created:**
  - `docs/SINBHA_EXISTING_ARCHITECTURE.md`
  - `docs/SINBHA_GAP_ANALYSIS.md`
  - `docs/SINBHA_REAL_WORLD_TEST_PLAN.md`
  - `docs/SINBHA_IMPLEMENTATION_ROADMAP.md`
- **Output:** Exact file paths, architecture diagrams, security boundaries, gap analysis, physical test protocols.
- **Done When:** User reviews and approves the four audit documents.

---

### PHASE 1 — SECURE DEVICE PAIRING & COMMUNICATION HARDENING
- **Goal:** Unify device presence, eliminate silent WebSocket dropouts, ensure multi-worker DB relay consistency.
- **Files to Inspect:** `app/device_relay.py`, `app/models.py:Device`, `android/.../SinbhaCompanionService.kt`, `electron/main.js`.
- **Files to Modify:** `app/device_relay.py`, `android/.../SinbhaCompanionService.kt`, `electron/main.js`.
- **Functionality:**
  1. WebSocket keepalive ping every 15s beating Render 55s proxy timeout.
  2. Active token rotation for companion background data sync.
  3. Device telemetry handshake recording battery, charging state, OS version, and exact last-seen timestamp.
- **Tests to Execute:** `pytest tests/test_c2_8_multiworker.py`, `tests/test_c2_9_real_devices.py`.
- **Done When:** Laptop and Phone remain `🟢 Online` in Diagnostics for 2 hours continuously without dropping.

---

### PHASE 2 — WINDOWS AUTOMATION (APPLICATIONS, DESKTOP & FILE OPS)
- **Goal:** Move desktop screen execution from server ctypes into Electron desktop runner; add file management tools.
- **Files to Inspect:** `electron/main.js`, `electron/command_security.js`, `app/screen_agent.py`, `app/agent_tools.py`.
- **Files to Modify:** `electron/command_security.js`, `electron/main.js`, `app/agent_tools.py`.
- **Functionality:**
  1. Add Windows File Management tools: `create_folder`, `create_text_file`, `list_directory`, `search_files`.
  2. Implement local desktop screenshot capture via Electron native `desktopCapturer` (zero server GDI ctypes).
  3. Active window detection via PowerShell / native Windows APIs without shell injection.
  4. Confirmation card for file deletion or overwriting (Level 2).
- **Tests to Execute:** `node tests/test_electron_security.js`, `pytest tests/test_c2_5_device_actions.py`.
- **Done When:** Command `"Create a folder named SINBHA on my desktop and write my study notes in notes.txt"` succeeds on the Windows laptop with a verified file creation receipt.

---

### PHASE 3 — ANDROID AUTOMATION (ROUTE LADDER & ACCESSIBILITY SCREEN AGENT)
- **Goal:** Verify and harden 5-route ladder launching from background and live Accessibility gestures.
- **Files to Inspect:** `android/.../SinbhaAppLauncher.kt`, `SinbhaAccessibilityService.kt`, `SinbhaCompanionService.kt`.
- **Files to Modify:** `android/.../SinbhaAccessibilityService.kt`, `android/.../SinbhaCompanionService.kt`.
- **Functionality:**
  1. Validate Route 1 &rarr; Route 2 &rarr; Route 3 &rarr; Route 4 &rarr; Route 5 execution ladder.
  2. Accessibility gesture execution: `tapElement`, `typeText`, `scroll`, `pressBack`, `pressHome`.
  3. Sensitive package blocker (`NEVER_TOUCH_PACKAGES` covering UPI, banking, password managers).
  4. Real-time floating indicator showing: *"SINBHA is controlling your phone"* with a red **STOP** button.
- **Tests to Execute:** Physical Android 13-State Matrix (A01 through A13).
- **Done When:** Background launch test succeeds across App, Settings, URL, and Deep Link while phone screen is OFF.

---

### PHASE 4 — REMOTE CROSS-DEVICE CONTROL
- **Goal:** Seamless bi-directional task execution between phone and laptop.
- **Files to Inspect:** `app/device_relay.py`, `app/agent_loop.py`, `app/agent_tools.py`.
- **Files to Modify:** `app/agent_loop.py`, `app/agent_tools.py`.
- **Functionality:**
  1. Laptop chat triggering phone apps, settings, and camera.
  2. Phone chat triggering laptop Notepad, Chrome, VS Code, and locking workstation.
  3. Cross-device screenshot request: Phone captures screen and displays thumbnail in laptop chat with user confirmation.
- **Tests to Execute:** `pytest tests/test_cross_device_agent.py`, Protocol CD-1 & CD-2.
- **Done When:** Prompt `"Open YouTube on my phone from my laptop"` opens YouTube on the locked phone and reports verified receipt to the laptop.

---

### PHASE 5 — WHATSAPP & MESSAGING INTELLIGENCE
- **Goal:** Read accessible notifications, check unread chats, generate style-matched drafts in Telugu/Hinglish/English, and enforce explicit confirmation before sending.
- **Files to Inspect:** `android/.../SinbhaNotificationListener.kt`, `app/messages_assistant.py`, `app/agent_loop.py`.
- **Files to Modify:** `app/messages_assistant.py`, `android/.../SinbhaNotificationListener.kt`, `android/.../SinbhaAccessibilityService.kt`.
- **Functionality:**
  1. Notification inbox parsing: sender, app, message preview, timestamp.
  2. Prompt injection defense: untrusted text cannot override system instructions or request OTP forwarding.
  3. Style-matching draft generator supporting Telugu, Hinglish, casual and formal modes.
  4. Approval card in chat: **NEVER** sends a message without explicit click or confirmation.
  5. Accessibility-based message dispatcher: types approved text into WhatsApp input and taps send button.
- **Tests to Execute:** `pytest tests/test_d2_messages_assistant.py`, Protocols M-01, M-02, M-03.
- **Done When:** A real WhatsApp notification from a friend is summarized in chat, a casual reply is drafted, and after clicking [Send], the message is delivered via WhatsApp on the phone.

---

### PHASE 6 — BROWSER AUTOMATION & FORM FILLING ENGINE
- **Goal:** Autonomous website interaction, form field mapping to saved personal details, and CAPTCHA pausing.
- **Files to Inspect:** `app/browser_agent.py`, `app/models.py:Fact`, `app/database.py`.
- **Files to Modify:** `app/browser_agent.py`, `app/agent_tools.py`.
- **Functionality:**
  1. Playwright DOM inspector identifying input fields (Name, Email, Phone, College, Degree, Year).
  2. Semantic mapper matching form fields to verified user facts in `Fact` database.
  3. Preview card showing mapped values before entering them on the live webpage.
  4. Pause on CAPTCHA / 2FA / Login challenges asking user to complete manually.
- **Tests to Execute:** `pytest tests/test_c3b_browser_agent.py`.
- **Done When:** Given a test registration form URL, SINBHA fills the fields from saved user memory, presents a preview, and awaits approval before final submit.

---

### PHASE 7 — MULTI-STEP AUTONOMOUS WORKFLOW ENGINE
- **Goal:** End-to-end task planner executing complex cross-device pipelines with state checkpoints and failure recovery.
- **Files to Inspect:** `app/agent_loop.py`, `app/models.py`, `app/agent_tools.py`.
- **Files to Modify:** `app/models.py` (Add `WorkflowExecution`), `app/agent_loop.py`, `static/script.js`.
- **Functionality:**
  1. Decompose complex user goals (e.g. 18-step request) into an ordered step graph.
  2. Route each step to the appropriate agent (Phone, Laptop, Browser).
  3. Record workflow execution checkpoints in database; support step retries and alternative routes.
  4. Real-time step progress card in chat showing completed steps, active step, and elapsed time.
- **Tests to Execute:** `pytest tests/agent_evals/test_eval_suite.py` (Assert 100% pass across all 98 scenarios).
- **Done When:** User prompt: `"Open YouTube on my phone, search for Python tutorials, open Notepad on my laptop, type my name, open Claude, ask a question, read its answer, and open ChatGPT"` executes across both physical devices with a unified final report.

---

### PHASE 8 — PROACTIVE PERSONAL ASSISTANT & SHARED MEMORY
- **Goal:** Proactive reminders, event monitoring, battery alerts, and disconnection notices.
- **Files to Modify:** `app/main.py`, `app/database.py`, `android/.../SinbhaCompanionService.kt`.
- **Functionality:**
  1. Background monitor checking phone battery (<15%) and alerting on laptop.
  2. Disconnection detector notifying user when a trusted device goes offline unexpectedly.
  3. Daily check-in greeting and morning agenda summary.
- **Done When:** Phone battery dropping to 10% triggers a prompt notification on the Windows laptop without user intervention.

---

### PHASE 9 — REAL-WORLD HARDENING & SECURITY AUDIT
- **Goal:** Stress testing, battery consumption profiling, network failover resilience, and audit compliance.
- **Verification:**
  1. Ensure 0% battery drain spikes on Android during idle background operation.
  2. Replay protection and rate limiting stress test (50 concurrent commands).
  3. Verify all money safety invariants (Section 14A) hold with 0 false positives.
  4. Verify emergency STOP halts all active operations in <500ms.

---

### PHASE 10 — FINAL PHYSICAL VALIDATION REPORT
- **Goal:** Complete hardware-verified audit report across all devices and release tagging.
- **Deliverables:**
  - `docs/SINBHA_PHYSICAL_VERIFICATION_REPORT.md`
  - GitHub releases for `SINBHA.apk` and `sinbha-setup.exe`
  - Final video/evidence log of the 18-step master workflow executed on real hardware.

