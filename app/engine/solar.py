"""
Solar calculation engine using pvlib (NREL SPA algorithm + Ineichen clear-sky model).
Replaces the simplified Spencer/Hottel JS model with industry-standard solar math.
"""
import numpy as np
import pandas as pd
import pvlib
from pvlib import clearsky, atmosphere, irradiance as pvl_irr
from typing import Dict, Any, List, Optional

# Mid-month day of year (Jan=15, Feb=46, ... Dec=344)
MID_MONTH_DAYS = [15, 46, 74, 105, 135, 162, 198, 228, 258, 288, 318, 344]

# Linke turbidity for Ineichen model
# Clear sky: very clean high-altitude air (~2.0)
# Standard:  typical clear day (~3.0)
# Hazy:      humid/urban/polluted (~5.5)
CLARITY_TURBIDITY = {
    "clear":    2.0,
    "standard": 3.0,
    "hazy":     5.5,
}

BATT_DISCHARGE_EFF = {"lipo": 0.95, "liion": 0.97, "lifepo4": 0.96}


def _make_times(month: int, time_hrs: float) -> pd.DatetimeIndex:
    """
    Build a UTC DatetimeIndex treating input as local solar time (longitude=0).
    UAV endurance calcs use solar time, so lon=0 + UTC = solar time.
    """
    day = MID_MONTH_DAYS[month - 1]
    h = int(time_hrs)
    m = int(round((time_hrs - h) * 60))
    if m == 60:
        h += 1
        m = 0
    base = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=day - 1)
    ts = base + pd.Timedelta(hours=h, minutes=m)
    return pd.DatetimeIndex([ts])


def _make_time_series(month: int, start_hrs: float, n: int, freq_min: int = 30) -> pd.DatetimeIndex:
    """Build a series of UTC times for vectorised pvlib calls."""
    day = MID_MONTH_DAYS[month - 1]
    base = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=day - 1)
    start = base + pd.Timedelta(hours=start_hrs)
    return pd.date_range(start=start, periods=n, freq=f"{freq_min}min")


def _location(lat: float, altitude: float) -> pvlib.location.Location:
    return pvlib.location.Location(lat, 0.0, altitude=altitude, tz="UTC")


def get_poa(
    lat: float,
    altitude: float,
    times: pd.DatetimeIndex,
    clarity: str,
    tilt: float,
) -> np.ndarray:
    """
    Return plane-of-array irradiance (W/m²) for each timestamp.
    tilt=0 → horizontal flat wing → POA = GHI.
    tilt>0 → south-facing fixed tilt → full POA decomposition.
    """
    lt = CLARITY_TURBIDITY.get(clarity, 3.0)
    loc = _location(lat, altitude)

    solpos = loc.get_solarposition(times)
    elev = solpos["elevation"].values
    zen  = solpos["apparent_zenith"].values
    az   = solpos["azimuth"].values

    # Clear-sky irradiance (vectorised)
    cs = loc.get_clearsky(times, model="ineichen", linke_turbidity=lt)
    ghi = np.maximum(0.0, cs["ghi"].values)
    dni = np.maximum(0.0, cs["dni"].values)
    dhi = np.maximum(0.0, cs["dhi"].values)

    night_mask = elev <= 0.0

    if tilt == 0:
        poa = np.where(night_mask, 0.0, ghi)
    else:
        poa_df = pvl_irr.get_total_irradiance(
            surface_tilt=tilt,
            surface_azimuth=180.0,
            solar_zenith=zen,
            solar_azimuth=az,
            dni=dni,
            ghi=ghi,
            dhi=dhi,
        )
        # poa_df["poa_global"] may be a pandas Series or a numpy array depending
        # on pvlib version; np.asarray() handles both without needing .values
        poa = np.where(night_mask, 0.0, np.maximum(0.0, np.asarray(poa_df["poa_global"])))

    return poa


def panel_power(poa: np.ndarray, area: float, efficiency: float,
                temp_coeff: float, panel_temp: float, mppt: float) -> np.ndarray:
    """Convert POA irradiance array → panel power (W) array."""
    eff_actual = efficiency * (1.0 + (temp_coeff / 100.0) * (panel_temp - 25.0))
    return np.maximum(0.0, area * (eff_actual / 100.0) * poa * (mppt / 100.0))


# ─── Public API ──────────────────────────────────────────────────────────────

def _panel2_poa_point(params: Dict[str, Any], ghi: float, dni: float, dhi: float,
                       zen: float, az: float) -> float:
    """Compute POA for the optional second panel at a single point."""
    p2_area = float(params.get("panel_2_area", 0.0))
    if p2_area <= 0.0:
        return 0.0
    p2_tilt = float(params.get("panel_2_tilt", 0.0))
    if p2_tilt == 0.0:
        return ghi
    poa_df = pvl_irr.get_total_irradiance(
        surface_tilt=p2_tilt, surface_azimuth=180.0,
        solar_zenith=zen, solar_azimuth=az,
        dni=dni, ghi=ghi, dhi=dhi,
    )
    return max(0.0, float(poa_df["poa_global"]))


def compute_point(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full single-point solar calculation.
    Returns irradiance, solar position, panel power, and derived metrics.
    Supports optional second panel (panel_2_area, panel_2_tilt).
    """
    lat       = params["lat"]
    altitude  = params["altitude"]
    month     = params["month"]
    time_hrs  = params["time_hrs"]
    clarity   = params["clarity"]
    tilt      = params["tilt"]
    area      = params["area"]
    efficiency= params["efficiency"]
    temp_coeff= params["temp_coeff"]
    panel_temp= params["panel_temp"]
    mppt      = params["mppt"]
    p2_area   = float(params.get("panel_2_area", 0.0))
    p2_tilt   = float(params.get("panel_2_tilt", 0.0))

    times = _make_times(month, time_hrs)
    lt    = CLARITY_TURBIDITY.get(clarity, 3.0)
    loc   = _location(lat, altitude)

    solpos = loc.get_solarposition(times)
    elevation = float(solpos["elevation"].iloc[0])

    if elevation <= 0.0:
        return {
            "elevation":   elevation,
            "ghi":         0.0,
            "poa":         0.0,
            "poa2":        0.0,
            "solar_power": 0.0,
            "eff_actual":  efficiency * (1 + (temp_coeff / 100) * (panel_temp - 25)),
        }

    cs  = loc.get_clearsky(times, model="ineichen", linke_turbidity=lt)
    ghi = max(0.0, float(cs["ghi"].iloc[0]))
    dni = max(0.0, float(cs["dni"].iloc[0]))
    dhi = max(0.0, float(cs["dhi"].iloc[0]))
    zen = float(solpos["apparent_zenith"].iloc[0])
    az  = float(solpos["azimuth"].iloc[0])

    if tilt == 0:
        poa = ghi
    else:
        poa_df = pvl_irr.get_total_irradiance(
            surface_tilt=tilt, surface_azimuth=180.0,
            solar_zenith=zen, solar_azimuth=az,
            dni=dni, ghi=ghi, dhi=dhi,
        )
        poa = max(0.0, float(poa_df["poa_global"]))

    eff_actual = efficiency * (1.0 + (temp_coeff / 100.0) * (panel_temp - 25.0))
    p_solar    = max(0.0, area * (eff_actual / 100.0) * poa * (mppt / 100.0))

    # Panel 2 contribution (if configured)
    poa2 = 0.0
    if p2_area > 0.0:
        poa2    = _panel2_poa_point(params, ghi, dni, dhi, zen, az)
        p_solar += max(0.0, p2_area * (eff_actual / 100.0) * poa2 * (mppt / 100.0))

    return {
        "elevation":   elevation,
        "ghi":         round(ghi, 1),
        "poa":         round(poa, 1),   # panel-1 POA at params["tilt"]
        "poa2":        round(poa2, 1),  # panel-2 POA at params["panel_2_tilt"]
        "solar_power": round(p_solar, 2),
        "eff_actual":  round(eff_actual, 3),
    }


def _combined_powers(params: Dict[str, Any], times: pd.DatetimeIndex) -> np.ndarray:
    """Panel 1 + optional Panel 2 power array for a time series."""
    poa = get_poa(params["lat"], params["altitude"], times,
                  params["clarity"], params["tilt"])
    pw  = panel_power(poa, params["area"], params["efficiency"],
                      params["temp_coeff"], params["panel_temp"], params["mppt"])

    p2_area = float(params.get("panel_2_area", 0.0))
    if p2_area > 0.0:
        p2_tilt = float(params.get("panel_2_tilt", 0.0))
        poa2 = get_poa(params["lat"], params["altitude"], times,
                       params["clarity"], p2_tilt)
        pw2  = panel_power(poa2, p2_area, params["efficiency"],
                           params["temp_coeff"], params["panel_temp"], params["mppt"])
        pw = pw + pw2

    return pw


def compute_daily_profile(params: Dict[str, Any], ptotal: float) -> Dict[str, Any]:
    """
    29-point profile: 05:00 → 19:00 in 30-min steps.
    Also computes Dec comparison profile for season toggle.
    Returns chart arrays + daily_energy + solar_window.
    Supports optional second panel (panel_2_area, panel_2_tilt).
    """
    times  = _make_time_series(params["month"], 5.0, 29, 30)
    powers = _combined_powers(params, times)

    times_dec  = _make_time_series(12, 5.0, 29, 30)
    powers_dec = _combined_powers({**params, "month": 12}, times_dec)

    daily_energy = float(np.sum(powers) * 0.5)
    solar_window = float(np.sum(powers > ptotal) * 0.5)

    return {
        "chart1_profile": [round(float(v), 2) for v in powers],
        "chart1_season":  [round(float(v), 2) for v in powers_dec],
        "daily_energy_wh": round(daily_energy, 1),
        "solar_window_hrs": round(solar_window, 1),
    }


def compute_sunrise_sunset(lat: float, month: int, altitude: float) -> Dict[str, Any]:
    """
    Find sunrise and sunset (decimal hours) for given lat/month.
    Uses pvlib solar elevation sweep across the full day.
    """
    times = _make_time_series(month, 0.0, 48, 30)  # 0:00 → 23:30
    loc   = _location(lat, altitude)
    solpos = loc.get_solarposition(times)
    elev   = solpos["elevation"].values

    sunrise: Optional[float] = None
    sunset:  Optional[float] = None

    for i, e in enumerate(elev):
        t = i * 0.5
        if e > 0.0:
            if sunrise is None:
                sunrise = t
            sunset = t + 0.5

    day_len   = (sunset - sunrise) if (sunrise is not None and sunset is not None) else 0.0
    night_hrs = 24.0 - day_len

    return {
        "sunrise":   round(sunrise, 2) if sunrise is not None else None,
        "sunset":    round(sunset, 2) if sunset is not None else None,
        "day_length": round(day_len, 2),
        "night_hrs":  round(night_hrs, 2),
    }


def compute_soc_24h(params: Dict[str, Any], ptotal: float) -> List[float]:
    """
    48-step (0:00–23:30) SOC simulation.
    Returns 49-element list (index 0 = midnight start, index 48 = midnight end).
    Supports optional second panel (panel_2_area, panel_2_tilt).
    """
    d_eff = BATT_DISCHARGE_EFF.get(params["batt_chem"], 0.95)
    c_eff = params["charge_eff"] / 100.0
    batt  = float(params["batt_wh"])
    min_s = float(params["min_soc"])

    times  = _make_time_series(params["month"], 0.0, 48, 30)
    powers = _combined_powers(params, times)

    soc = 100.0
    arr = [soc]
    for pw in powers:
        pnet = float(pw) - ptotal
        if pnet >= 0:
            soc += (pnet * 0.5 * c_eff) / batt * 100.0
        else:
            soc += (pnet * 0.5) / (batt * d_eff) * 100.0
        soc = max(min_s, min(100.0, soc))
        arr.append(round(soc, 2))

    return arr
