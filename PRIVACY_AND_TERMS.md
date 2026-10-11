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

### 2.2 How Your Data is Processed (AI Processing)
- **AI Processing**: When you send messages to SINBHA, your text is processed through our chosen AI provider (such as OpenRouter / Google Gemini) to generate conversational replies and parse natural language deadlines.
- **Field-Level Encryption at Rest**: Sensitive chat contents and memory facts are stored in our PostgreSQL database using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
- **No Plaintext Logging**: We do not store plaintext passwords, session cookies, or raw message text in our audit or system logs.

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
