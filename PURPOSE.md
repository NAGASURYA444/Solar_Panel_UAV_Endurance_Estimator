# Project Purpose

## The Problem

Solar-powered UAVs operate at a delicate energy balance point. The solar panels must generate at least as much power as the drone consumes — otherwise the battery depletes, and the mission ends. Getting this balance right requires understanding:

- **Solar geometry**: how high the sun is at a given latitude, season, and time of day
- **Irradiance modelling**: how atmosphere, altitude, and sky conditions reduce available sunlight
- **Panel physics**: how efficiency is affected by temperature, tilt angle, and cell technology
- **Power systems**: motor propulsion draw, avionics consumption, battery capacity and chemistry
- **Seasonal variation**: whether a design that works in summer still works in winter

Traditionally, answering these questions required either expensive simulation software (MATLAB, SAM, OpenFOAM), writing custom scripts in Python or MATLAB, or relying on rough mental estimates. None of these options are accessible to most drone designers and students.

## The Solution

This tool packages all the necessary physics into a browser-based calculator that anyone can use without installing software or writing code. It uses:

- **pvlib** (the same solar library used by NREL's System Advisor Model) for accurate solar position and irradiance calculation
- **NASA POWER** historical data for real-world validation against satellite-measured GHI
- **FastAPI** for a lightweight, responsive backend
- **Chart.js and Leaflet** for interactive visualisation

Every input change triggers a full recalculation in under 300 ms, making parametric exploration fast and intuitive.

## Target Users

| User | Use Case |
|---|---|
| UAV Systems Engineer | Size solar panels and battery for an endurance mission |
| Research Engineer | Validate energy budget model against real flight data |
| Mission Planner | Determine safe launch windows and worst-case seasonal limits |
| Student / Academic | Learn solar UAV energy system design interactively |
| Drone Enthusiast | Explore "what if" scenarios without coding |

## What This Tool Does NOT Do

- Aerodynamic or structural analysis (lift, drag, wing loading)
- Motor selection or propeller matching
- Actual flight controller integration
- Weather forecasting (uses clear-sky model with optional NASA historical data)
- Financial or cost analysis

## Design Philosophy

1. **No installation barrier** — open a browser and go; no accounts, no build steps
2. **Real physics, not rules of thumb** — pvlib NREL SPA + Ineichen clear-sky gives industry-standard accuracy
3. **Immediate feedback** — every change recalculates instantly; exploration is encouraged
4. **Transparent results** — every output links to a formula; nothing is a black box
5. **Designed for iteration** — save, compare, share configurations; build up design knowledge incrementally

## Solar Model Details

The irradiance calculation uses the **Ineichen clear-sky model** with the **NREL Solar Position Algorithm (SPA)**. This combination is the industry standard for solar resource assessment, accurate to within 1% for direct beam irradiance under clear conditions.

For tilted panels (non-zero tilt angle), the tool uses pvlib's full plane-of-array (POA) irradiance decomposition, which correctly accounts for direct normal irradiance (DNI), diffuse horizontal irradiance (DHI), and ground-reflected irradiance separately — important when comparing horizontal (flat wing) vs tilted panel mounting configurations.

Sky clarity is parameterised through Linke turbidity:
- **Clear** (LT = 2.0): very clean, high-altitude air
- **Standard** (LT = 3.0): typical clear-day conditions
- **Hazy** (LT = 5.5): humid, urban, or dust-laden atmosphere

## Power Budget Model

```
P_solar  = area × eff_actual × POA × mppt_eff
eff_actual = eff_STC × (1 + temp_coeff/100 × (T_panel − 25))

P_wind   = P_prop × ((v_air + v_wind) / v_air)² − P_prop
P_total  = (N_motors × P_cruise) + P_wind + P_fc + P_tel + P_payload + P_other

P_net    = P_solar − P_total
```

If `P_net ≥ 0`: the drone is self-powered. Surplus goes to battery via MPPT.
If `P_net < 0`: battery supplies the deficit. Endurance = Usable_Wh / |P_net|.

## Verdict Logic

| State | Condition | Meaning |
|---|---|---|
| SUSTAINABLE | P_net > 0, margin ≥ 15% | Solar fully covers consumption with comfortable margin |
| MARGINAL | P_net > 0, margin < 15% | Barely sustainable — cloud or load increase could tip to deficit |
| BATTERY ASSISTED | P_net < 0, endurance ≥ 4 hrs | Drawing from battery but has meaningful flight time remaining |
| INSUFFICIENT | P_net < 0, endurance < 4 hrs | Mission not viable — significant design change needed |

## Version History

| Version | Description |
|---|---|
| v1.0 | Single HTML file with simplified JS solar model |
| v2.0 | FastAPI backend, pvlib solar engine, 9 charts, basic modules |
| v3.0 | Monte Carlo, Mission Window Planner, Route Planner, Thermal Model, Annual Heatmap, Battery Life, Altitude Profile, Battery Temp Derating — 20 API endpoints total |
