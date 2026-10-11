# 🚀 SINBHA Backend Deployment & Operations Guide (Render)

This guide walks you through deploying your SINBHA backend online to **Render** connected to your **Neon PostgreSQL** database.

---

## 1. Hosting Provider Comparison (Why Render + Cron Ping?)

| Provider | Free Tier | Server Sleep Behavior | Setup Ease | Monthly Cost |
| :--- | :--- | :--- | :--- | :--- |
| **Render** (Recommended) | **Yes** (750 free compute hrs/month) | Sleeps after 15 min of inactivity (wakes up in ~30s) | ⭐⭐⭐⭐⭐ Easiest for beginners, direct GitHub sync | **$0 / month** (or $7/mo for always-on Starter) |
| **Railway** | No free tier (Free trial has 30-day limit / $5 credit) | Never sleeps while credits exist | ⭐⭐⭐⭐ Good UI, fast | ~$5–$10 / month minimum |
| **Fly.io** | Limited free allowance, requires credit card | Micro-VM architecture, complex CLI | ⭐⭐⭐ Steeper learning curve | Free allowance or ~$5 / month |

### Why Render + 15-Minute Cron Ping is the Best Choice:
Render's free tier gives you a real cloud web server with automatic HTTPS and free PostgreSQL connection support. When paired with a **free keep-alive cron job** (e.g., [cron-job.org](https://cron-job.org) or UptimeRobot) pinging `https://your-service.onrender.com/api/health` every 10–14 minutes, the server **never goes to sleep and stays awake 24/7 for free**.

---

## 2. Production Secrets (Do NOT Paste in Chat)

Generate two completely new keys on your computer using Python:

```powershell
# 1. Generate Production Data Encryption Key (Fernet AES-128-CBC)
python -c "from cryptography.fernet import Fernet; print('DATA_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# 2. Generate Production Session Secret
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(48))"
```

> [!IMPORTANT]
> **Store these keys in your personal password manager (1Password, Bitwarden, or Apple Keychain).**
> Never share or commit these keys to GitHub. You will paste them directly into Render's Environment dashboard.

---

## 3. Neon Production Database Branch

To keep your local development data separate from your live users' data:
1. Log into your [Neon Console](https://console.neon.tech).
2. Go to your project (`polished-poetry-88188380`).
3. Click **Branches** > **New Branch**.
4. Name the branch `production` (parent: `main` or clean schema).
5. Copy the connection string for this branch:
   - Format: `postgresql+psycopg://username:password@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`

---

## 4. Deploying to Render (Step-by-Step)

### Step 4.1: Connect Your GitHub Repository
1. Log in to [Render](https://dashboard.render.com).
2. Click **New +** > **Web Service**.
3. Select **Build and deploy from a Git repository**.
4. Connect your GitHub account and select your repository:
   `https://github.com/kbtteja456-KBT/SINBHA`

### Step 4.2: Configure the Service
- **Name**: `sinbha-backend` (or your chosen name)
- **Region**: `Singapore` (closest to your ap-southeast-1 Neon database for ultra-low latency)
- **Branch**: `main` (or `master`)
- **Runtime**: `Python`
- **Build Command**: `./build.sh` (installs dependencies and automatically runs Alembic migrations)
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`
- **Instance Type**: `Free`

### Step 4.3: Add Environment Variables
Under the **Environment** section, add the following variables:

| Key | Value | Description |
| :--- | :--- | :--- |
| `ENV` | `production` | Enables production mode (turns off dev endpoints, marks cookies Secure) |
| `DEV_MODE` | `false` | Disables internal developer inspection |
| `OPENROUTER_API_KEY` | *(your real OpenRouter API key)* | LLM reasoning API key |
| `OPENROUTER_MODEL` | `google/gemini-2.5-flash` | Affordable, fast companion model |
| `DATABASE_URL` | *(your Neon production URL)* | Must end with `?sslmode=require` |
| `DATA_ENCRYPTION_KEY` | *(your generated Fernet key)* | Field encryption at rest |
| `SESSION_SECRET` | *(your generated session secret)* | Cookie session signing |
| `DAILY_USER_AI_LIMIT` | `100` | Per-user message cap |
| `DAILY_GLOBAL_AI_LIMIT`| `2000` | Global platform safety cap |

Click **Deploy Web Service**! Render will pull your repo, run `build.sh`, run `alembic upgrade head`, and start the server.

---

## 5. Keeping the Server Awake 24/7 (Free Cron Job)

Render's free tier spins down after 15 minutes without incoming web traffic. To make it 24/7:
1. Sign up for free at [cron-job.org](https://cron-job.org) or [UptimeRobot](https://uptimerobot.com).
2. Create a new monitor / cron job:
   - **URL**: `https://sinbha-backend.onrender.com/api/health`
   - **Schedule**: Every **10 minutes** (or 14 minutes)
   - **Method**: `GET`
3. Save the job.
4. Because the health endpoint receives a ping every 10 minutes, Render never sleeps, and the zero-downtime health check keeps your companion active 24/7!

---

## 6. How to Roll Back to a Previous Version

If a new code deployment introduces an error, you can roll back with 1 click:
1. Open the [Render Dashboard](https://dashboard.render.com).
2. Click your `sinbha-backend` service.
3. In the sidebar, click **Events** or **Deploys**.
4. Find the previous successful deploy in the list.
5. Click the three dots `...` next to that commit, and click **Rollback to this deploy**.
6. Render will instantly re-activate the previous working build.

---

## 7. How to Restore the Database from a Backup

Because SINBHA uses Neon PostgreSQL, you have continuous **Point-in-Time Recovery (PITR)**:
1. Open [Neon Console](https://console.neon.tech).
2. Navigate to your project > **Branches**.
3. Click **Create Branch**.
4. Under "Branch from", choose **Time** (Point in time).
5. Pick the date and exact minute before any issue occurred (e.g., 1 hour ago).
6. Neon instantly creates a restored database branch in seconds without data loss.
7. Update `DATABASE_URL` in Render's Environment settings to point to the restored branch URL, and click **Save Changes**.

---

## 8. Monthly Cost Estimate

- **Hosting (Render Free Tier)**: **$0.00 / month** (750 compute hours covered, kept alive via cron-job.org ping).
- **Database (Neon Free Tier)**: **$0.00 / month** (0.5 GB storage, instant branching included).
- **AI Token Usage (OpenRouter - Gemini 2.5 Flash)**: **~$0.10 – $0.50 / month** depending on daily conversation volume.
- **Optional Upgrade (Render Starter - Dedicated Always-On)**: **$7.00 / month** (if you prefer not to use a cron ping).

---

## 9. How to Test Your Live Deployment (In Simple Words)

Once your Render dashboard shows **"Live"**:
1. **Health Check**:
   - Open in your browser: `https://your-service.onrender.com/api/health`
   - You should see:
     ```json
     {
       "status": "healthy",
       "environment": "production",
       "database": "connected",
       "version": "1.0.0"
     }
     ```
2. **Open the Web UI**:
   - Visit `https://your-service.onrender.com/` in your browser or on your phone.
3. **Sign Up**:
   - Create a test account (e.g. `test@example.com`). Check the 18+ and Terms checkboxes.
4. **Chat & Task Confirmation**:
   - Say: *"Hi SINBHA! Remind me to review my goals tomorrow at 10am."*
   - Verify SINBHA understands and suggests the task proposal.
5. **Data Rights**:
   - Open **⚙ Settings**, click **📥 Download My Data**, and verify the JSON file downloads cleanly.
6. **Emergency STOP**:
   - Click the red **🛑 STOP** button in the header and verify all actions pause immediately.
