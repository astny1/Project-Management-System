# Deploy GrowthHive Media on Render

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
git commit -m "Prepare GrowthHive for Render deployment"

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

## Security checklist

- [ ] Change default passwords
- [ ] Strong `SECRET_KEY` in Render env
- [ ] Do not share admin URL without strong auth

---

## Links

- [Render Flask docs](https://render.com/docs/deploy-flask)
- [Render free tier](https://render.com/docs/free)
