# Installation & Setup Guide

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 or higher |
| pip | Latest (comes with Python) |
| Browser | Chrome, Firefox, Edge, or Safari (modern version) |
| Internet | Optional — only needed for NASA POWER real data feature |

---

## Step-by-Step Installation

### Step 1 — Get the code

**Option A: Clone with Git**
```bash
git clone https://github.com/NAGASURYA444/Solar_Panel_UAV_Endurance_Estimator.git
cd Solar_Panel_UAV_Endurance_Estimator
```

**Option B: Download ZIP**
1. Go to the GitHub repository page
2. Click **Code → Download ZIP**
3. Extract the ZIP to a folder of your choice
4. Open a terminal in that folder

---

### Step 2 — Create a virtual environment

A virtual environment keeps the project's dependencies isolated from your system Python.

**Windows:**
```cmd
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` appear at the start of your terminal prompt — this confirms the environment is active.

---

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs: FastAPI, Uvicorn, pvlib, NumPy, Pandas, Pydantic, and httpx.

Expected install time: 1–3 minutes depending on internet speed.

---

### Step 4 — Start the server

**Option A: Command line**
```bash
python -m uvicorn app.main:app --host "::" --port 8000
```

**Option B: Windows batch file**
Double-click `run.bat` in the project folder.

You should see output like:
```
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://[::]:8000
```

---

### Step 5 — Open in browser

Open your browser and go to:
```
http://localhost:8000
```

The tool will load immediately. No login, no account, no further setup.

---

## Stopping the Server

Press `Ctrl + C` in the terminal window where the server is running.

---

## Restarting After Closing

Every time you want to use the tool again:

1. Open a terminal in the project folder
2. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - macOS/Linux: `source .venv/bin/activate`
3. Run: `python -m uvicorn app.main:app --host "::" --port 8000`
4. Open `http://localhost:8000`

---

## Troubleshooting

### "python is not recognized" or "command not found"

Python is not installed or not in your system PATH.
- Download Python from [python.org](https://www.python.org/downloads/)
- During installation on Windows, check **"Add Python to PATH"**

### Port 8000 is already in use

Another process is using port 8000. Use a different port:
```bash
python -m uvicorn app.main:app --host "::" --port 8001
```
Then open `http://localhost:8001` in your browser.

### "ModuleNotFoundError: No module named 'pvlib'" (or similar)

The virtual environment is not activated, or dependencies weren't installed.
```bash
# Activate the environment first, then install:
pip install -r requirements.txt
```

### The page loads but charts don't appear

Check your browser console (F12 → Console) for errors. Make sure you're using a modern browser. Internet Explorer is not supported.

### NASA GHI chart shows no data

This feature fetches data from the NASA POWER API and requires an internet connection. It works on the first online request and caches results. If you're offline, the chart will only show the tool's model line.

### Saved configurations disappeared after restart

Named configurations are stored in `app/db/configs.db` (SQLite). This file is excluded from Git (in `.gitignore`) so it will not persist if you re-clone the repo. The browser's automatic save (localStorage) works independently and persists across server restarts.

---

## Running the Test Suite

To verify everything is working correctly:

```bash
python validate_all.py
```

Expected output: `104 tests passed` with no failures.

---

## Accessing the API Documentation

The FastAPI backend includes interactive API documentation (Swagger UI):

```
http://localhost:8000/docs
```

This lets you explore and test all 20 API endpoints directly from the browser.

---

## Upgrading Dependencies

If you need to upgrade to the latest package versions:

```bash
pip install --upgrade -r requirements.txt
```
