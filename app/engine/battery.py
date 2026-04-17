"""Multi-day battery SOC simulation — N-day battery drift across day/night cycles."""
import numpy as np
from typing import Dict, Any, List

from .solar import _combined_powers, _make_time_series, BATT_DISCHARGE_EFF


def compute_multiday_soc(params: Dict[str, Any], ptotal: float, days: int = 3) -> Dict[str, Any]:
    """
    Simulate battery SOC over N consecutive days (48 half-hour steps per day).

    Returns:
        soc_series   : list of floats, length = days*48 + 1 (one per half-hour + initial)
        hour_labels  : list of str labels "Day 1 00:00", ...
        day_summary  : per-day dict {min_soc, max_soc, end_soc, survived}
        survived     : True if SOC never dropped below min_soc on any day
        night_survived: True if every night period ends above min_soc
    """
    d_eff = BATT_DISCHARGE_EFF.get(params["batt_chem"], 0.95)
    c_eff = params["charge_eff"] / 100.0
    batt  = float(params["batt_wh"])
    min_s = float(params["min_soc"])  # keep as float so max(min_s, soc) never returns int
    month = params["month"]

    # Build full time series for all days at once (vectorised pvlib call)
    n_steps = days * 48
    times  = _make_time_series(month, 0.0, n_steps, 30)
    powers = _combined_powers(params, times)

    soc = 100.0
    soc_series = [round(soc, 2)]
    hour_labels = []
    day_summaries = []

    for day in range(days):
        day_soc_min = soc
        day_soc_max = soc
        night_at_floor = False   # did SOC hit reserve floor during a night step?
        start = day * 48

        for step in range(48):
            idx = start + step
            h = step * 0.5
            label_h = int(h)
            label_m = "30" if (h % 1 == 0.5) else "00"
            hour_labels.append(f"Day {day+1} {label_h:02d}:{label_m}")

            pw   = float(powers[idx]) if idx < len(powers) else 0.0
            pnet = pw - ptotal
            if pnet >= 0:
                soc += (pnet * 0.5 * c_eff) / batt * 100.0
            else:
                soc += (pnet * 0.5) / (batt * d_eff) * 100.0
            soc = max(min_s, min(100.0, soc))
            soc_series.append(round(soc, 2))

            if soc < day_soc_min:
                day_soc_min = soc
            if soc > day_soc_max:
                day_soc_max = soc

            # Night step: solar power is negligible (< 1 W)
            # If SOC is at the reserve floor during night, battery has no overnight margin
            if pw < 1.0 and soc <= min_s + 0.01:
                night_at_floor = True

        day_summaries.append({
            "day":             day + 1,
            "min_soc":         round(day_soc_min, 1),
            "max_soc":         round(day_soc_max, 1),
            "end_soc":         round(soc, 1),
            "survived":        day_soc_min >= min_s,
            "night_margin_ok": not night_at_floor,
        })

    # night_survived: True only if battery never hit the reserve floor during night hours
    night_survived = all(s["night_margin_ok"] for s in day_summaries)
    survived = all(s["survived"] for s in day_summaries)

    return {
        "soc_series":     soc_series,
        "hour_labels":    hour_labels,
        "day_summaries":  day_summaries,
        "survived":       survived,
        "night_survived": night_survived,
        "final_soc":      round(soc, 1),
    }
