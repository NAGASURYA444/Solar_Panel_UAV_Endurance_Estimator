"""
Optimal launch time finder.

Sweeps time_hrs from 05:00 to 19:00 in 30-min steps and reports:
  - best_time       : time of peak solar power
  - peak_power_w    : maximum solar power reached
  - window_start    : earliest time where p_net > 0 (solar > consumption)
  - window_end      : latest  time where p_net > 0
  - window_hrs      : total hours where p_net > 0
  - optimal_launch  : recommended take-off time (window_start - 0.5hr buffer)
  - profile         : full 29-point sweep [{time_hrs, solar_w, p_net}]
"""
from typing import Dict, Any, List, Optional

from .solar import _combined_powers, _make_time_series
from .power import compute_min_area
from .wind_drag import compute_wind_drag

STEP = 0.5          # hours
START_HR = 5.0
END_HR = 19.0


def find_optimal_launch(params: Dict[str, Any]) -> Dict[str, Any]:
    wind   = compute_wind_drag(params)
    p_wind = wind["p_wind_w"]
    p_prop = params["num_motors"] * params["cruise_power"]
    p_avion   = params["power_fc"] + params["power_tel"]
    p_payload = params["power_payload"]
    p_other   = params["power_other"]
    ptotal    = p_prop + p_wind + p_avion + p_payload + p_other

    n = int((END_HR - START_HR) / STEP) + 1          # 29 steps
    times  = _make_time_series(params["month"], START_HR, n, int(STEP * 60))
    powers = _combined_powers(params, times)

    profile: List[Dict[str, Any]] = []
    best_time: Optional[float]  = None
    peak_power: float = 0.0
    window_start: Optional[float] = None
    window_end:   Optional[float] = None

    for i, pw in enumerate(powers):
        t    = START_HR + i * STEP
        pnet = float(pw) - ptotal

        profile.append({
            "time_hrs":  t,
            "time_label": f"{int(t):02d}:{'30' if t % 1 else '00'}",
            "solar_w":   round(float(pw), 1),
            "p_net":     round(pnet, 1),
            "surplus":   pnet > 0,
        })

        if float(pw) > peak_power:
            peak_power = float(pw)
            best_time  = t

        if pnet > 0:
            if window_start is None:
                window_start = t
            window_end = t

    window_hrs = 0.0
    if window_start is not None and window_end is not None:
        window_hrs = window_end - window_start + STEP

    # Recommended launch: 0.5 hr before surplus window opens so UAV is at
    # altitude when solar power ramps up; clamp to 05:00 minimum
    optimal_launch: Optional[float] = None
    if window_start is not None:
        optimal_launch = max(START_HR, window_start - STEP)

    return {
        "ptotal":          round(ptotal, 1),
        "best_time":       best_time,
        "best_time_label": f"{int(best_time):02d}:{'30' if best_time and best_time % 1 else '00'}" if best_time else None,
        "peak_power_w":    round(peak_power, 1),
        "window_start":    window_start,
        "window_end":      window_end,
        "window_hrs":      round(window_hrs, 1),
        "optimal_launch":  optimal_launch,
        "optimal_launch_label": (
            f"{int(optimal_launch):02d}:{'30' if optimal_launch % 1 else '00'}"
            if optimal_launch is not None else None
        ),
        "profile":         profile,
        "sustainable":     window_start is not None,
    }
