# GrowHive Media — Project Management Platform

A web-based project management platform for **GrowHive Media** (Technology & Marketing company). Track client contracts, expenses, payments, subcontractors, and generate monthly reports per project.

## Features

- **Role-based login**: Admin and Project Manager accounts
- **Projects dashboard**: View all projects with status (Pending, Ongoing, Completed)
- **Financial tracking** per project:
  - Contract amount & payment terms
  - Expenses & payments received
  - Remaining contract balance
  - Company bank balance
- **Subcontractors** assigned per contract
- **Monthly maintenance** flag and amount
- **Project duration** in weeks
- **Monthly Report** per project with client company details (view, print, download PDF)
- **Admin settings** for company info and bank balance

## Quick Start

### 1. Install dependencies

```powershell
cd "d:\MY PROJECTS\Project Mnagement"
pip install -r requirements.txt
```

### 2. Run the application

```powershell
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

### Demo Login Accounts

| Role | Email | Password |
|------|-------|----------|
| Admin | astone.mwamba@growhivemedea.com | admin123 |
| Sales Manager | sales@growthhivemedia.com | sales123 |
| Project Manager | pm@growthhivemedia.com | pm123 |

## Deploy on Render (cloud hosting)

See **[RENDER.md](RENDER.md)** for a full step-by-step guide (GitHub → Render → live HTTPS URL).

Quick summary:

1. Push this project to GitHub
2. Create a **Web Service** on [render.com](https://render.com) (free tier)
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
5. Add env vars: `SECRET_KEY` (generate), `PYTHON_VERSION` = `3.12.5`, `DATABASE_PATH` = `/tmp/growthhive.db`

Or use the included **`render.yaml`** blueprint for one-click setup.

## Usage

1. **Sign in** with Admin or Project Manager credentials
2. **Dashboard** shows all projects, bank balance, and summary stats
3. **Click a project** to view details, add expenses, payments, and subcontractors
4. **Monthly Report** — select month/year, view on screen, print, or download PDF
5. **Admin → Settings** — update company details and bank balance

## Tech Stack

- Python 3 + Flask
- SQLite database (local file: `growthhive.db`)
- Tailwind CSS (CDN)
- ReportLab for PDF generation

## Reset Demo Data

Delete `growthhive.db` and restart the app to re-seed sample projects.

## Start fresh with your own data (no demo projects)

Stop the app if it is running, then:

```powershell
cd "D:\MY PROJECTS\Project Mnagement"
python reset_db.py
python app.py
```

This **deletes everything** and creates an empty database with:
- Your **admin login** only (`astone.mwamba@growhivemedea.com` / `admin123`)
- **No** demo projects, clients, expenses, or investments
- Bank balance and reserves at **K 0.00**

Add `--team` to also create empty sales & project manager accounts:

```powershell
python reset_db.py --team
```

Change your password in **Settings** after logging in.
