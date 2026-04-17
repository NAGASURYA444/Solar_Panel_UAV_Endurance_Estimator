"""
Solar UAV Endurance Estimator — FastAPI backend.
Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .engine.solar import compute_point, compute_daily_profile, compute_sunrise_sunset, compute_soc_24h
from .engine.power import compute_power_budget, compute_min_area, get_verdict
from .engine.battery import compute_multiday_soc
from .engine.monthly import compute_monthly_table
from .engine.sensitivity import compute_sensitivity
from .engine.nasa_power import fetch_monthly_ghi
from .engine.optimize import find_optimal_launch
from .engine.mission import compute_mission
from .engine.compare import compare_configs
from .engine.degradation import compute_degradation
from .engine.monte_carlo import compute_monte_carlo
from .engine.thermal import compute_thermal_profile
from .engine.heatmap import compute_annual_heatmap
from .engine.battery_life import compute_battery_life
from .engine.wind_drag import compute_wind_drag
from .engine.altitude_profile import compute_altitude_profile
from .engine.batt_temp import compute_batt_temp
from .engine.route import compute_route
from .db.database import save_config, load_config, list_configs, delete_config, rename_config

# ── App & static files ──────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"
app = FastAPI(title="Solar UAV Endurance Estimator", version="1.0.0")

# Serve static files under /static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── Shared Pydantic model ───────────────────────────────────────────────────

class UAVParams(BaseModel):
    # Solar array
    area:        float = Field(2.5,  ge=0.1,  le=50.0)
    efficiency:  float = Field(22.0, ge=1.0,  le=50.0)
    temp_coeff:  float = Field(-0.35, ge=-1.0, le=0.0)
    panel_temp:  float = Field(45.0, ge=-20.0, le=100.0)
    mppt:        float = Field(95.0, ge=50.0,  le=100.0)
    tilt:        float = Field(0.0,  ge=0.0,   le=90.0)

    # Location & time
    lat:         float = Field(13.0,  ge=-90.0, le=90.0)
    altitude:    float = Field(500.0, ge=0.0,   le=8000.0)
    month:       int   = Field(6,     ge=1,     le=12)
    time_hrs:    float = Field(12.0,  ge=0.0,   le=24.0)
    clarity:     str   = Field("clear")

    # Multi-panel (optional second panel)
    panel_2_area: float = Field(0.0,  ge=0.0,  le=50.0)
    panel_2_tilt: float = Field(0.0,  ge=0.0,  le=90.0)

    # Propulsion
    num_motors:    int   = Field(4,    ge=1,   le=20)
    cruise_power:  float = Field(80.0, ge=1.0, le=5000.0)
    airspeed:      float = Field(60.0, ge=1.0, le=500.0)
    wind_speed_ms: float = Field(0.0,  ge=0.0, le=30.0)

    # Avionics & payload
    power_fc:      float = Field(5.0,  ge=0.0, le=500.0)
    power_tel:     float = Field(3.0,  ge=0.0, le=500.0)
    power_payload: float = Field(10.0, ge=0.0, le=2000.0)
    power_other:   float = Field(2.0,  ge=0.0, le=500.0)

    # Battery
    batt_wh:    float = Field(500.0, ge=1.0,   le=100000.0)
    batt_chem:  str   = Field("lipo")
    min_soc:    float = Field(20.0,  ge=0.0,   le=90.0)
    charge_eff: float = Field(95.0,  ge=50.0,  le=100.0)

    @field_validator("clarity")
    @classmethod
    def validate_clarity(cls, v: str) -> str:
        if v not in ("clear", "standard", "hazy"):
            raise ValueError("clarity must be 'clear', 'standard', or 'hazy'")
        return v

    @field_validator("batt_chem")
    @classmethod
    def validate_chem(cls, v: str) -> str:
        if v not in ("lipo", "liion", "lifepo4"):
            raise ValueError("batt_chem must be 'lipo', 'liion', or 'lifepo4'")
        return v

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# ── /api/calculate ──────────────────────────────────────────────────────────

@app.post("/api/calculate")
async def calculate(params: UAVParams):
    """Full single-point calculation: solar + power budget + charts + verdict."""
    p = params.to_dict()

    solar    = compute_point(p)
    wind     = compute_wind_drag(p)
    budget   = compute_power_budget(p, solar["solar_power"], p_wind=wind["p_wind_w"])
    verdict  = get_verdict(budget["p_net"], budget["p_total"], budget["endurance"])
    min_area = compute_min_area(p, solar["poa"], p_wind=wind["p_wind_w"], poa2=solar.get("poa2", 0.0))

    ptotal  = budget["p_total"]
    profile = compute_daily_profile(p, ptotal)
    sunrise = compute_sunrise_sunset(p["lat"], p["month"], p["altitude"])
    soc_24h = compute_soc_24h(p, ptotal)

    return {
        "solar":    solar,
        "wind":     wind,
        "budget":   budget,
        "verdict":  verdict,
        "min_area": round(min_area, 2) if min_area != float("inf") else None,
        "profile":  profile,
        "sunrise":  sunrise,
        "soc_24h":  soc_24h,
    }


# ── /api/multiday ───────────────────────────────────────────────────────────

class MultiDayRequest(BaseModel):
    params: UAVParams
    days:   int = Field(3, ge=1, le=30)


@app.post("/api/multiday")
async def multiday(req: MultiDayRequest):
    """Multi-day battery SOC simulation."""
    p = req.params.to_dict()
    wind = compute_wind_drag(p)
    ptotal = (p["num_motors"] * p["cruise_power"]
              + wind["p_wind_w"]
              + p["power_fc"] + p["power_tel"]
              + p["power_payload"] + p["power_other"])
    return compute_multiday_soc(p, ptotal, days=req.days)


# ── /api/monthly ────────────────────────────────────────────────────────────

@app.post("/api/monthly")
async def monthly(params: UAVParams):
    """12-month performance table."""
    return {"rows": compute_monthly_table(params.to_dict())}


# ── /api/sensitivity ────────────────────────────────────────────────────────

class SensitivityRequest(BaseModel):
    params:   UAVParams
    step_pct: float = Field(10.0, ge=1.0, le=50.0)


@app.post("/api/sensitivity")
async def sensitivity(req: SensitivityRequest):
    """One-at-a-time ±N% sensitivity sweep."""
    return compute_sensitivity(req.params.to_dict(), step_pct=req.step_pct)


# ── /api/configs (CRUD) ─────────────────────────────────────────────────────

class SaveConfigRequest(BaseModel):
    name:   str = Field(..., min_length=1, max_length=100)
    params: UAVParams
    note:   str = Field("", max_length=500)


class RenameConfigRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=100)


@app.get("/api/configs")
async def list_all_configs():
    return {"configs": list_configs()}


@app.post("/api/configs")
async def create_config(req: SaveConfigRequest):
    saved = save_config(req.name, req.params.to_dict(), req.note)
    return saved


@app.get("/api/configs/{name}")
async def get_config(name: str):
    cfg = load_config(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Config '{name}' not found")
    return cfg


@app.delete("/api/configs/{name}")
async def remove_config(name: str):
    deleted = delete_config(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Config '{name}' not found")
    return {"deleted": name}


@app.patch("/api/configs/{name}/rename")
async def rename(name: str, req: RenameConfigRequest):
    try:
        updated = rename_config(name, req.new_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Config '{name}' not found")
    return updated


# ── /api/nasa_power ──────────────────────────────────────────────────────────

class NASARequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(0.0, ge=-180.0, le=180.0)


@app.post("/api/nasa_power")
async def nasa_power(req: NASARequest):
    """Fetch real monthly GHI from NASA POWER API for a location."""
    result = await fetch_monthly_ghi(req.lat, req.lon)
    if result is None:
        raise HTTPException(
            status_code=503,
            detail="NASA POWER API unreachable. Check internet connection or try later."
        )
    return result


# ── /api/optimize ────────────────────────────────────────────────────────────

@app.post("/api/optimize")
async def optimize_launch(params: UAVParams):
    """Find optimal launch time — sweep 05:00–19:00 and identify best window."""
    return find_optimal_launch(params.to_dict())


# ── /api/mission ─────────────────────────────────────────────────────────────

class MissionSegment(BaseModel):
    name:            str   = Field("Segment", max_length=50)
    duration_hrs:    float = Field(..., gt=0.0, le=24.0)
    altitude_m:      Optional[float] = Field(None, ge=0.0,   le=8000.0)
    speed_kmh:       Optional[float] = Field(None, ge=1.0,   le=500.0)
    num_motors:      Optional[int]   = Field(None, ge=1,     le=20)
    cruise_power_w:  Optional[float] = Field(None, ge=1.0,   le=5000.0)
    power_payload_w: Optional[float] = Field(None, ge=0.0,   le=2000.0)
    power_other_w:   Optional[float] = Field(None, ge=0.0,   le=500.0)


class MissionRequest(BaseModel):
    params:         UAVParams
    segments:       List[MissionSegment] = Field(..., min_length=1, max_length=20)
    start_time_hrs: float = Field(7.0, ge=0.0, le=23.0)


@app.post("/api/mission")
async def mission(req: MissionRequest):
    """Multi-segment mission energy budget."""
    segs = [s.model_dump(exclude_none=False) for s in req.segments]
    # Rename fields to match engine signature
    segs_clean = []
    for s in segs:
        segs_clean.append({
            "name":            s["name"],
            "duration_hrs":    s["duration_hrs"],
            "altitude_m":      s["altitude_m"],
            "speed_kmh":       s["speed_kmh"],
            "num_motors":      s["num_motors"],
            "cruise_power_w":  s["cruise_power_w"],
            "power_payload_w": s["power_payload_w"],
            "power_other_w":   s["power_other_w"],
        })
    return compute_mission(req.params.to_dict(), segs_clean, req.start_time_hrs)


# ── /api/compare ─────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    params_a: UAVParams
    params_b: UAVParams
    label_a:  str = Field("Config A", max_length=50)
    label_b:  str = Field("Config B", max_length=50)


@app.post("/api/compare")
async def compare(req: CompareRequest):
    """Side-by-side comparison of two parameter sets."""
    return compare_configs(
        req.params_a.to_dict(),
        req.params_b.to_dict(),
        req.label_a,
        req.label_b,
    )


# ── /api/degradation ─────────────────────────────────────────────────────────

class DegradationRequest(BaseModel):
    params:          UAVParams
    solar_power_w:   float = Field(..., ge=0.0)
    years:           int   = Field(15, ge=1,  le=40)
    annual_rate_pct: float = Field(0.50, ge=0.1, le=5.0)
    lid_pct:         float = Field(1.5,  ge=0.0, le=5.0)


@app.post("/api/degradation")
async def degradation(req: DegradationRequest):
    """Project panel power decay over N years with LID + annual degradation."""
    return compute_degradation(
        req.params.to_dict(),
        req.solar_power_w,
        years=req.years,
        annual_rate_pct=req.annual_rate_pct,
        lid_pct=req.lid_pct,
    )


# ── /api/thermal ─────────────────────────────────────────────────────────────

class ThermalRequest(BaseModel):
    params:      UAVParams
    t_ambient:   float = Field(25.0, ge=-20.0, le=60.0)
    mount_type:  str   = Field("uav_flying")

    @field_validator("mount_type")
    @classmethod
    def valid_mount(cls, v: str) -> str:
        allowed = {"uav_flying", "uav_ground", "open_rack", "rooftop", "building"}
        if v not in allowed:
            raise ValueError(f"mount_type must be one of {allowed}")
        return v


@app.post("/api/thermal")
async def thermal(req: ThermalRequest):
    """Compute panel temperature profile and power derating across the day."""
    p = req.params.to_dict()
    # Get the daily POA profile first
    wind = compute_wind_drag(p)
    ptotal = (p["num_motors"] * p["cruise_power"]
              + wind["p_wind_w"]
              + p["power_fc"] + p["power_tel"]
              + p["power_payload"] + p["power_other"])
    from .engine.solar import get_poa, _make_time_series
    import numpy as np
    times   = _make_time_series(p["month"], 5.0, 29, 30)
    poa_arr = get_poa(p["lat"], p["altitude"], times, p["clarity"], p["tilt"])
    poa_list = [float(v) for v in poa_arr]

    return compute_thermal_profile(p, poa_list, req.t_ambient, req.mount_type)


# ── /api/heatmap ─────────────────────────────────────────────────────────────

@app.post("/api/heatmap")
async def heatmap(params: UAVParams):
    """Annual 365-day solar energy heatmap."""
    return compute_annual_heatmap(params.to_dict())


# ── /api/battery_life ────────────────────────────────────────────────────────

class BatteryLifeRequest(BaseModel):
    params:            UAVParams
    soc_24h:           List[float] = Field(..., min_length=49, max_length=49)
    missions_per_day:  float = Field(1.0, ge=0.1, le=10.0)
    projection_years:  int   = Field(5,   ge=1,   le=20)

    @field_validator("soc_24h")
    @classmethod
    def validate_soc_values(cls, v: List[float]) -> List[float]:
        for val in v:
            if not (0.0 <= val <= 100.0):
                raise ValueError("All soc_24h values must be in [0, 100]")
        return v


@app.post("/api/battery_life")
async def battery_life(req: BatteryLifeRequest):
    """Battery cycle life projection based on daily DoD."""
    return compute_battery_life(
        req.params.to_dict(),
        req.soc_24h,
        missions_per_day=req.missions_per_day,
        projection_years=req.projection_years,
    )


# ── /api/monte_carlo ──────────────────────────────────────────────────────────

class MonteCarloRequest(BaseModel):
    params:          UAVParams
    n_samples:       int   = Field(500,  ge=100, le=2000)
    uncertainty_pct: float = Field(10.0, ge=1.0, le=30.0)


@app.post("/api/monte_carlo")
async def monte_carlo(req: MonteCarloRequest):
    """Monte Carlo sensitivity: simultaneously randomise all parameters and
    report the probability distribution of net-power outcomes."""
    return compute_monte_carlo(
        req.params.to_dict(),
        n_samples=req.n_samples,
        uncertainty_pct=req.uncertainty_pct,
    )


# ── /api/altitude_profile ─────────────────────────────────────────────────────

class AltitudeProfileRequest(BaseModel):
    params:    UAVParams
    alt_max_m: float = Field(8000.0, ge=500.0,  le=12000.0)
    steps:     int   = Field(20,     ge=5,      le=50)


@app.post("/api/altitude_profile")
async def altitude_profile(req: AltitudeProfileRequest):
    """Flight profile vs altitude: solar power, adjusted cruise power, net balance at each altitude."""
    return compute_altitude_profile(
        req.params.to_dict(),
        alt_max_m=req.alt_max_m,
        steps=req.steps,
    )


# ── /api/batt_temp ────────────────────────────────────────────────────────────

class BattTempRequest(BaseModel):
    params:     UAVParams
    temp_min_c: float = Field(-20.0, ge=-40.0, le=25.0)
    temp_max_c: float = Field(60.0,  ge=25.0,  le=80.0)


@app.post("/api/batt_temp")
async def batt_temp(req: BattTempRequest):
    """Battery temperature derating: capacity and endurance table across temperature range."""
    return compute_batt_temp(
        req.params.to_dict(),
        temp_min_c=req.temp_min_c,
        temp_max_c=req.temp_max_c,
    )


# ── /api/route ────────────────────────────────────────────────────────────────

class Waypoint(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class RouteRequest(BaseModel):
    params:         UAVParams
    waypoints:      List[Waypoint] = Field(..., min_length=2, max_length=50)
    start_time_hrs: float = Field(7.0, ge=0.0, le=23.0)


@app.post("/api/route")
async def route(req: RouteRequest):
    """Route planner: evaluate a multi-waypoint flight path for energy budget and SOC."""
    wps = [{"lat": w.lat, "lon": w.lon} for w in req.waypoints]
    return compute_route(req.params.to_dict(), wps, req.start_time_hrs)


# ── /api/wind_drag ────────────────────────────────────────────────────────────

@app.post("/api/wind_drag")
async def wind_drag(params: UAVParams):
    """Compute wind drag power penalty and effective ground speed."""
    return compute_wind_drag(params.to_dict())
