# ☀ Solar UAV Endurance Estimator v3.0

A web-based engineering tool to estimate solar-powered UAV flight endurance. Enter your drone's solar panel, motors, battery, and location — get an instant answer on whether it can fly indefinitely or how long it lasts.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green?logo=fastapi)
![pvlib](https://img.shields.io/badge/pvlib-0.10+-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## What does it do?

Given a UAV's solar panel area, efficiency, motor power, battery, and geographic location, the tool calculates:

- How much solar power the panels generate at any time and location
- Whether that power covers the total drone consumption (SUSTAINABLE / MARGINAL / BATTERY ASSISTED / INSUFFICIENT)
- How long the battery lasts if solar is insufficient
- Battery state of charge through a full day–night cycle
- 12-month seasonal performance to find the worst-case design month
- Minimum panel area required to break even
- Sensitivity to parameter variation (Monte Carlo + tornado analysis)

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/NAGASURYA444/Solar_Panel_UAV_Endurance_Estimator.git
cd Solar_Panel_UAV_Endurance_Estimator
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

- **Windows:** `.venv\Scripts\activate`
- **macOS / Linux:** `source .venv/bin/activate`

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the server

```bash
python -m uvicorn app.main:app --host "::" --port 8000
```

Or on Windows, double-click `run.bat`.

### 5. Open in browser

```
http://localhost:8000
```

That's it. No build step, no database setup, no configuration files needed.

---

## Features

| Feature | Description |
|---|---|
| **Live Calculation** | All results update instantly as you type |
| **4-State Verdict** | SUSTAINABLE / MARGINAL / BATTERY ASSISTED / INSUFFICIENT |
| **12 Charts** | Solar profile, SOC simulation, power breakdown, degradation, thermal, Monte Carlo, and more |
| **12-Month Table** | Full year performance sweep — find your worst-case month |
| **Config Comparison** | Side-by-side comparison of two drone configurations |
| **Sensitivity Analysis** | Tornado chart showing which parameter matters most |
| **Monte Carlo** | 500-sample statistical reliability analysis |
| **Mission Window Planner** | Month × Hour grid showing safe flight windows |
| **Route Planner** | Draw a flight path on a map, get per-segment energy budget |
| **Panel Degradation** | Power output forecast over 10–25 years |
| **Thermal Analysis** | NOCT-based cell temperature and efficiency derating |
| **Annual Heatmap** | 365-day solar energy calendar |
| **Battery Cycle Life** | Woehler model — years before 80% capacity loss |
| **Cloud Survival** | Impact of cloud cover on battery SOC |
| **Save / Load / Share** | Named configs, URL sharing, PDF & CSV export |
| **Solar Cell Presets** | SunPower Maxeon, Mono c-Si, Thin-Film CIGS, PERC Bifacial, GaAs |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI, Pydantic v2 |
| Solar Engine | pvlib (NREL SPA + Ineichen clear-sky model) |
| Scientific | NumPy, Pandas |
| External Data | NASA POWER API (real monthly GHI data) |
| Frontend | Vanilla JS, Chart.js 4.4, Leaflet.js 1.9 |
| Database | SQLite (named config storage) |

---

## Project Structure

```
Solar_Panel_UAV_Endurance_Estimator/
├── app/
│   ├── main.py                  # FastAPI app — all 20 API endpoints
│   ├── engine/
│   │   ├── solar.py             # pvlib solar geometry engine
│   │   ├── power.py             # Power budget, verdict logic
│   │   ├── battery.py           # Multi-day SOC simulation
│   │   ├── monthly.py           # 12-month batch analysis
│   │   ├── sensitivity.py       # One-at-a-time parameter sweep
│   │   ├── monte_carlo.py       # 500-sample statistical analysis
│   │   ├── compare.py           # Side-by-side config comparison
│   │   ├── optimize.py          # Optimal launch window sweep
│   │   ├── mission.py           # Multi-segment mission planner
│   │   ├── nasa_power.py        # NASA POWER API integration
│   │   ├── degradation.py       # Panel degradation model
│   │   ├── thermal.py           # NOCT thermal model
│   │   ├── heatmap.py           # 365-day annual heatmap
│   │   ├── battery_life.py      # Woehler cycle-life model
│   │   ├── wind_drag.py         # Headwind propulsion drag
│   │   ├── altitude_profile.py  # Altitude vs irradiance
│   │   ├── batt_temp.py         # Battery temperature derating
│   │   └── route.py             # Route planner energy budget
│   ├── db/
│   │   └── database.py          # SQLite CRUD for saved configs
│   └── static/
│       └── index.html           # Full SPA frontend (JS + CSS inline)
├── validate_all.py              # 104-test validation suite
├── USER_DOCUMENTATION.html      # Complete user guide (open in browser)
├── requirements.txt             # Python dependencies
├── run.bat                      # Windows one-click launcher
└── README.md
```

---

## API Endpoints

All endpoints accept `POST` with a JSON body containing UAV parameters.

| Endpoint | Description |
|---|---|
| `POST /api/calculate` | Main calculation: solar + power budget + SOC + verdict |
| `POST /api/monthly` | 12-month performance table |
| `POST /api/sensitivity` | Parameter sensitivity (tornado chart) |
| `POST /api/monte_carlo` | Monte Carlo statistical analysis |
| `POST /api/compare` | Side-by-side config comparison |
| `POST /api/multiday` | Multi-day SOC simulation |
| `POST /api/optimize` | Optimal launch window |
| `POST /api/mission` | Multi-segment mission energy budget |
| `POST /api/nasa_power` | Fetch real GHI from NASA POWER API |
| `POST /api/degradation` | Panel degradation over years |
| `POST /api/thermal` | NOCT thermal profile |
| `POST /api/heatmap` | 365-day annual solar heatmap |
| `POST /api/battery_life` | Woehler battery cycle life |
| `GET /api/configs` | List saved configurations |
| `POST /api/configs` | Save a configuration |
| `GET /api/configs/{name}` | Load a configuration |
| `DELETE /api/configs/{name}` | Delete a configuration |
| `PATCH /api/configs/{name}/rename` | Rename a configuration |

Interactive API docs available at `http://localhost:8000/docs` after starting the server.

---

## Running the Test Suite

```bash
python validate_all.py
```

104 tests covering solar geometry, power budget formulas, verdict logic, edge cases, and all engine modules.

---

## Documentation

Open `USER_DOCUMENTATION.html` directly in any browser for the complete user guide — no server needed. It covers every input field, output metric, chart, and module with plain-English explanations and worked examples.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
