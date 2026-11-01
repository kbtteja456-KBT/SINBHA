# SINBHA Privacy Policy & Terms of Service

> **NOTICE: Marked for Legal Review.**  
> *Last Updated: October 2026*  
> *This document provides an honest, transparent description of how SINBHA handles user data, security, AI processing, and service boundaries.*

---

## 1. Terms of Service

### 1.1 Nature of the Service
SINBHA is a personal task companion designed to help you organize daily tasks, deadlines, and reminders with warm conversational check-ins.

### 1.2 Not a Therapist or Emergency Healthcare Service
**SINBHA is an automated AI software assistant, NOT a licensed therapist, counselor, psychiatrist, medical professional, or emergency crisis service.**
- If you are experiencing a mental health emergency, severe distress, or thoughts of self-harm, please immediately contact emergency services or a dedicated 24/7 crisis hotline (such as dialing **988** in the United States and Canada, or your local emergency emergency number).
- SINBHA cannot provide medical advice, diagnosis, or crisis intervention.

### 1.3 Age Requirement (18+)
**You must be at least 18 years of age to register and use SINBHA.** By creating an account, you affirm that you are 18 or older and have the legal capacity to agree to these terms.

### 1.4 Account Security
You are responsible for safeguarding your login credentials. Use a strong, unique password of at least 8 characters. Do not share your password.

---

## 2. Privacy Policy

### 2.1 What Data We Collect
- **Account Information**: Your email address, encrypted password hash (Argon2), and preferred timezone.
- **Task and Schedule Data**: Titles, due dates, reminder times, and task completion statuses.
- **Conversations & Memory**: Messages you send in chat and personal facts you share with SINBHA (e.g. your preferences or daily routines).

### 2.2 How Your Data is Processed & External AI / Search Providers
SINBHA connects to approved external AI and search providers to provide companion capabilities, tool orchestration, and screen visual guidance. We maintain strict transparency regarding which providers receive data:

1. **Groq Inc.** (`api.groq.com`):
   - **What it receives**: User chat messages, tool definitions, and tool execution status when Groq is the active provider or used as primary/fallback LLM.
   - **Purpose**: Ultra-fast conversational text generation and tool routing.
2. **OpenRouter / Google** (`openrouter.ai` / Google Gemini):
   - **What it receives**: User chat messages, tool parameters, and desktop screenshot frames during autonomous screen tasks (`screen_task`).
   - **Purpose**: Multi-step reasoning and computer vision screen navigation (Google Gemini 2.5 Flash).
3. **Tavily Technologies** (`api.tavily.com`):
   - **What it receives**: Search queries formulated when real-time web search is explicitly needed.
   - **Purpose**: Real-time web search and current news grounding. Tavily never receives your passwords, account profile, or chat history.

### 2.2.1 Windows Screen Agent & Visual Privacy (Step C3a)
- **Ephemeral In-Memory Processing**: Screen capture frames taken by the Windows Screen Agent are held strictly in temporary RAM for vision model coordinate analysis. **Screenshots are NEVER stored on the server, NEVER written to disk, and NEVER logged in any database or file.**
- **Never-Capture List**: Windows belonging to password managers (such as 1Password, Bitwarden, KeePass, LastPass, Dashlane, RoboForm, Windows Security, Authenticator) and banking/financial services (Chase, Wells Fargo, Bank of America, Citi, PayPal, Binance, Coinbase, etc.) are strictly prohibited from capture. Screen capture is instantly blocked if a sensitive window is in focus.
- **Action Gating & Safety Invariants**: The agent gates ACTIONS, not apps: before sensitive operations (send, post, submit, buy, pay, delete, install, share), an explicit confirmation card is shown with the exact text and a cropped preview. The agent **never types passwords, OTP codes, PINs, or credit card numbers**, and pauses for human completion on CAPTCHAs and login screens.

### 2.2.2 Data Encryption & Protection
- **Field-Level Encryption at Rest**: Sensitive chat contents and memory facts are stored in our PostgreSQL database using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
- **No Plaintext Logging**: We do not store plaintext passwords, session cookies, prompt text, or raw message text in our audit or system logs. Failures are classified with zero external provider names leaked to users.

### 2.3 Strict Data Isolation
Every piece of data is isolated to your individual account ID. No other user can access or view your chat history, tasks, or memory facts. Even administrators cannot view other users' private chat contents or memories through the application.

### 2.4 Your Data Rights (Export and Deletion)
Under privacy principles (including GDPR and CCPA concepts), you have complete control over your data:
1. **Download My Data (Export)**: You can download a complete, readable JSON copy of all your messages, facts, tasks, and settings at any time in **Settings → Download My Data**.
2. **Delete My Account**: You can permanently erase your entire account and all associated data at any time in **Settings → Delete my account**. When confirmed, your user record, credentials, active sessions, messages, tasks, and memories are permanently purged from the database.

### 2.5 Security Measures
- **SSL / TLS**: All communication between your device and the server, and between the server and the database, is encrypted in transit using SSL.
- **Web Protections**: CSRF protection, strict Content Security Policy (CSP), HTTP Strict Transport Security (HSTS), and rate limiting are enforced to protect your account.

---

*For questions or concerns regarding privacy or data handling, please refer to the application repository or contact your administrator.*
