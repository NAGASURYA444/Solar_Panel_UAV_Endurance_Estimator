"""
Thermal model — calculate actual panel operating temperature from conditions.

Replaces the fixed panel_temp input with a physics-based estimate using:
  1. NOCT model (IEC 61215):
       T_cell = T_amb + (NOCT - 20°C) / 800 W/m² × G_POA
  2. Wind cooling correction (Ross model):
       T_cell = T_amb + G_POA × k_ross
     where k_ross ≈ 0.02–0.04 °C·m²/W depending on mount / airflow

For a UAV in flight, forced convection from airspeed significantly lowers
panel temperature compared to a roof-mounted system.

UAV-specific correction:
  - Ground-based NOCT assumes ~1 m/s wind
  - UAV at 60 km/h (16.7 m/s) sees 16× more convective cooling
  - Effective NOCT for UAV ≈ 33–38°C (vs 45°C ground)
"""
import math
from typing import Dict, Any, List

# NOCT values (°C) by mounting type
NOCT_BY_MOUNT = {
    "uav_flying":  36.0,   # UAV at cruise speed — strong forced convection
    "uav_ground":  43.0,   # UAV on ground, idle
    "open_rack":   45.0,   # Standard open-rack ground mount (IEC reference)
    "rooftop":     48.0,   # Close-mount rooftop, limited airflow
    "building":    50.0,   # BIPV, worst-case airflow
}

# Ross coefficients (°C·m²/W) — alternative to NOCT for quick estimation
ROSS_K = {
    "uav_flying": 0.017,
    "uav_ground": 0.030,
    "open_rack":  0.032,
    "rooftop":    0.044,
    "building":   0.056,
}


def noct_temperature(
    t_ambient: float,
    poa: float,
    noct: float = 45.0,
) -> float:
    """
    NOCT model: T_cell = T_amb + (NOCT - 20) / 800 × G_POA
    Standard IEC 61215 formula. Valid for POA > 0.
    """
    if poa <= 0:
        return t_ambient
    return t_ambient + (noct - 20.0) / 800.0 * poa


def wind_corrected_temperature(
    t_ambient: float,
    poa: float,
    airspeed_ms: float,
    noct_ground: float = 45.0,
) -> float:
    """
    Wind-speed corrected cell temperature for a flying UAV.

    Uses a convective heat transfer correction:
      h ∝ v^0.8  (turbulent forced convection on flat plate)
    At reference NOCT wind (1 m/s) → at UAV cruise speed.
    """
    if poa <= 0:
        return t_ambient

    # Convective coefficient ratio relative to NOCT reference wind (1 m/s)
    v_ref  = 1.0
    v_uav  = max(v_ref, airspeed_ms)
    h_ratio = (v_ref / v_uav) ** 0.8   # higher speed → lower T rise

    delta_t_noct = (noct_ground - 20.0) / 800.0 * poa
    delta_t_uav  = delta_t_noct * h_ratio

    return round(t_ambient + delta_t_uav, 1)


def compute_thermal_profile(
    params: Dict[str, Any],
    poa_profile: List[float],          # 29-point profile (05:00–19:00)
    t_ambient: float = 25.0,
    mount_type: str = "uav_flying",
) -> Dict[str, Any]:
    """
    Compute panel temperature and derating for each time step.

    Returns:
        temp_profile   : list of cell temperatures (°C) per time step
        power_profile  : list of actual power (W) at each temp (vs fixed temp)
        peak_temp      : max cell temperature reached
        avg_temp       : average over daylight hours
        delta_vs_fixed : average power difference vs using fixed panel_temp
        recommendation : suggested panel_temp value to use in inputs
    """
    noct    = NOCT_BY_MOUNT.get(mount_type, 45.0)
    airspeed_ms = params.get("airspeed", 60) / 3.6   # km/h → m/s

    base_eff   = params["efficiency"]
    temp_coeff = params["temp_coeff"]   # %/°C (negative)
    fixed_temp = params["panel_temp"]
    area       = params["area"]
    mppt       = params["mppt"]

    temp_profile  = []
    power_actual  = []
    power_fixed   = []

    daylight_temps = []

    for poa in poa_profile:
        if poa > 0:
            t_cell = wind_corrected_temperature(t_ambient, poa, airspeed_ms, noct)
            daylight_temps.append(t_cell)
        else:
            t_cell = t_ambient

        # Power with calculated temperature
        eff_actual = base_eff * (1.0 + (temp_coeff / 100.0) * (t_cell - 25.0))
        p_actual   = max(0.0, area * (eff_actual / 100.0) * poa * (mppt / 100.0))

        # Power with user's fixed temp
        eff_fixed  = base_eff * (1.0 + (temp_coeff / 100.0) * (fixed_temp - 25.0))
        p_fixed    = max(0.0, area * (eff_fixed  / 100.0) * poa * (mppt / 100.0))

        temp_profile.append(round(t_cell, 1))
        power_actual.append(round(p_actual, 2))
        power_fixed.append(round(p_fixed, 2))

    peak_temp = max(temp_profile) if temp_profile else t_ambient
    avg_temp  = round(sum(daylight_temps) / len(daylight_temps), 1) if daylight_temps else t_ambient

    # Delta: positive = calculated gives more power than fixed temp assumption
    total_actual = sum(power_actual)
    total_fixed  = sum(power_fixed)
    daily_delta_wh = round((total_actual - total_fixed) * 0.5, 1)  # 30-min steps

    return {
        "temp_profile":    temp_profile,
        "power_actual":    power_actual,
        "power_fixed":     power_fixed,
        "peak_temp_c":     round(peak_temp, 1),
        "avg_temp_c":      avg_temp,
        "t_ambient":       t_ambient,
        "mount_type":      mount_type,
        "daily_delta_wh":  daily_delta_wh,
        "recommendation":  avg_temp,    # suggest using avg as fixed_temp
        "noct_used":       noct,
    }
