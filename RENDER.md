# Deploy GrowHive Media on Render

Step-by-step guide to host this Flask app on [Render](https://render.com) (free tier).

---

## Before you start

You need:

1. A **GitHub** account
2. A **Render** account (sign up at [render.com](https://render.com) — no credit card for free tier)
3. This project pushed to a **GitHub repository**

> **Important — database on free tier:** Render’s free web service uses **temporary disk**. Your SQLite file **resets when the app redeploys or restarts**. Fine for testing; for real company data, upgrade to **Render Postgres** or use **PythonAnywhere** with SQLite.

---

## Step 1 — Push code to GitHub

Open PowerShell in the project folder:

```powershell
cd "d:\MY PROJECTS\Project Mnagement"

git init
git add .
git commit -m "Prepare GrowHive for Render deployment"

# Create a new empty repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/growthhive-media.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME/growthhive-media` with your repo URL.

**Do not commit** `growthhive.db` — it is in `.gitignore`. Render creates a fresh database on first deploy via `wsgi.py` + `seed.py`.

---

## Step 2 — Create a Render Web Service

1. Log in to [dashboard.render.com](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. Connect your **GitHub** account if prompted
4. Select the **growthhive-media** repository
5. Use these settings:

| Setting | Value |
|---------|--------|
| **Name** | `growthhive-media` |
| **Region** | Closest to you (e.g. Frankfurt) |
| **Branch** | `main` |
| **Runtime** | **Python 3** |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| **Instance Type** | **Free** |

6. **Advanced** → **Environment Variables**:

| Key | Value |
|-----|--------|
| `SECRET_KEY` | Click **Generate** |
| `PYTHON_VERSION` | `3.12.5` |
| `DATABASE_PATH` | `/tmp/growthhive.db` |

**Email notifications & weekly digest** (optional but recommended):

| Key | Value |
|-----|--------|
| `NOTIFY_EMAIL` | `info@growhivemedea.com` |
| `SMTP_HOST` | e.g. `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Your SMTP login email |
| `SMTP_PASSWORD` | App password (Gmail) or SMTP key |
| `CRON_SECRET` | Random secret string |
| `ENABLE_WEEKLY_DIGEST` | `1` to auto-send every Monday 8:00 AM |

Without SMTP, alerts are logged in Render logs and on **Tax & ZRA** → notification history.

7. Click **Create Web Service**

First deploy takes **3–8 minutes**.

---

## Step 3 — Open your live URL

When deploy succeeds:

`https://growthhive-media.onrender.com`

Log in:

| Role | Email | Password |
|------|-------|----------|
| Admin | `astone.mwamba@growhivemedea.com` | `admin123` |
| Sales Manager | `sales@growthhivemedia.com` | `sales123` |
| Project Manager | `pm@growthhivemedia.com` | `pm123` |

Change passwords in **Settings** after first login.

---

## Optional — Blueprint (`render.yaml`)

1. **New +** → **Blueprint**
2. Connect the repo — Render uses `render.yaml` automatically

---

## Free tier notes

| Topic | Detail |
|-------|--------|
| Sleep | After ~15 min idle |
| Cold start | 30–50 seconds after sleep |
| HTTPS | Included automatically |
| Data loss | SQLite in `/tmp` clears on redeploy |

---

## Troubleshooting

**Build failed** — check Logs; confirm `requirements.txt` is in repo root.

**502 / timeout** — confirm Start Command matches exactly; PDF reports need `--timeout 120`.

**Logo missing** — commit `static/images/` to Git.

**Data gone after deploy** — expected on free SQLite; use Render Postgres for persistence.

---

## Reset Render database (remove demo data)

After deploy, new installs use an **empty** database (no demo projects). To **wipe** an existing Render database:

1. Push the latest code to GitHub (includes `reset_db.py` + updated `wsgi.py`)
2. In Render → your service → **Environment**
3. Add variable: `RESET_DATABASE` = `1`
4. Click **Manual Deploy** → **Deploy latest commit**
5. Wait until live, log in — empty database, admin only
6. **Remove** `RESET_DATABASE` from Environment (or every restart wipes your data!)
7. Save and deploy once more

Optional: add `INCLUDE_TEAM` = `1` to also create sales & PM login accounts.

Login after reset: `astone.mwamba@growhivemedea.com` / `admin123` — change password in Settings.

---

## Email setup (Gmail example)

1. Enable 2FA on your Google account
2. Create an **App Password** (Google Account → Security → App passwords)
3. In Render Environment:

```
NOTIFY_EMAIL=info@growhivemedea.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-16-char-app-password
CRON_SECRET=pick-a-long-random-string
ENABLE_WEEKLY_DIGEST=1
```

4. **Settings** → **Send Weekly Digest Now** to test
5. Optional: Render **Cron Job** weekly hitting  
   `https://YOUR-APP.onrender.com/cron/weekly-digest?key=YOUR_CRON_SECRET`

**What sends email to info@growhivemedea.com:**
- New leads
- Project file uploads
- New tax / ZRA obligations
- Weekly digest (bank balance, collections, MRR, cash flow forecast, hours logged)

---

## Security checklist

- [ ] Change default passwords
- [ ] Strong `SECRET_KEY` in Render env
- [ ] Do not share admin URL without strong auth

---

## Links

- [Render Flask docs](https://render.com/docs/deploy-flask)
- [Render free tier](https://render.com/docs/free)
