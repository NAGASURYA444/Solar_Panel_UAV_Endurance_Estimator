"""12-month batch analysis — compute key metrics for every month at a given location."""
import numpy as np
from typing import Dict, Any, List

from .solar import (
    get_poa, panel_power, compute_sunrise_sunset,
    _make_time_series, CLARITY_TURBIDITY, _combined_powers,
)
from .power import compute_power_budget, compute_min_area
from .wind_drag import compute_wind_drag

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def compute_monthly_table(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Run a full 12-month analysis for the given parameter set.

    For each month computes at the user's selected time_hrs:
      - Peak solar power (single point at time_hrs)
      - Daily energy (Wh) — rectangular sum over 05:00–19:00
      - Solar window (hrs/day above total consumption)
      - Endurance (hrs) or None if sustainable
      - Verdict
      - Sunrise / sunset

    Returns a list of 12 dicts, one per month.
    """
    results = []

    wind      = compute_wind_drag(params)
    p_wind    = wind["p_wind_w"]
    p_prop    = params["num_motors"] * params["cruise_power"]
    p_avion   = params["power_fc"] + params["power_tel"]
    p_payload = params["power_payload"]
    p_other   = params["power_other"]
    ptotal    = p_prop + p_wind + p_avion + p_payload + p_other

    from .solar import BATT_DISCHARGE_EFF
    d_eff   = BATT_DISCHARGE_EFF.get(params["batt_chem"], 0.95)
    usable  = params["batt_wh"] * (1.0 - params["min_soc"] / 100.0) * d_eff

    for month in range(1, 13):
        monthly_params = {**params, "month": month}

        # 29-point profile (05:00–19:00 in 30-min steps)
        times  = _make_time_series(month, 5.0, 29, 30)
        powers = _combined_powers({**params, "month": month}, times)
        poa    = get_poa(params["lat"], params["altitude"], times,
                         params["clarity"], params["tilt"])

        daily_energy  = float(np.sum(powers) * 0.5)   # Wh
        solar_window  = float(np.sum(powers > ptotal) * 0.5)  # hrs
        peak_solar    = float(np.max(powers))

        # Solar power at the user's selected time_hrs (for verdict / endurance)
        # Profile covers 05:00–19:00 in 30-min steps (indices 0–28)
        t = params["time_hrs"]
        if 5.0 <= t <= 19.0:
            t_idx = min(28, int(round((t - 5.0) / 0.5)))
            solar_at_time = float(powers[t_idx])
        else:
            solar_at_time = 0.0

        sun = compute_sunrise_sunset(params["lat"], month, params["altitude"])

        # Verdict at user's selected time_hrs (not peak)
        p_net = solar_at_time - ptotal
        if p_net >= 0:
            margin = p_net / ptotal if ptotal > 0 else 1.0
            if margin >= 0.15:
                verdict = "sustainable"
            else:
                verdict = "marginal"
            endurance = None
        else:
            endurance = round(usable / abs(p_net), 2) if abs(p_net) > 0 else None
            verdict = "battery_assisted" if (endurance and endurance >= 4.0) else "insufficient"

        # Min area at noon (step index 14 = 12:00)
        poa_noon  = float(poa[14]) if len(poa) > 14 else 0.0
        p2_tilt   = float(params.get("panel_2_tilt", 0.0))
        p2_area   = float(params.get("panel_2_area", 0.0))
        poa2_noon = 0.0
        if p2_area > 0.0:
            poa2_series = get_poa(params["lat"], params["altitude"], times,
                                  params["clarity"], p2_tilt)
            poa2_noon = float(poa2_series[14]) if len(poa2_series) > 14 else 0.0
        min_area = compute_min_area(params, poa_noon, poa2=poa2_noon)

        results.append({
            "month":          month,
            "month_name":     MONTH_NAMES[month - 1],
            "peak_solar_w":   round(peak_solar, 1),
            "solar_at_time_w": round(solar_at_time, 1),
            "daily_energy_wh": round(daily_energy, 1),
            "solar_window_hrs": round(solar_window, 1),
            "endurance_hrs":  endurance,
            "verdict":        verdict,
            "sunrise":        sun["sunrise"],
            "sunset":         sun["sunset"],
            "day_length_hrs": sun["day_length"],
            "min_area_m2":    round(min_area, 2) if min_area != float("inf") else None,
        })

    return results
