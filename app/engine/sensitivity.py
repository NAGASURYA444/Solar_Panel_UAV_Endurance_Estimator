"""
Sensitivity analysis — vary each parameter ±10% (one-at-a-time) and
report the delta in endurance / net power relative to the baseline.
"""
from typing import Dict, Any, List
import copy

from .solar import compute_point
from .power import compute_power_budget
from .wind_drag import compute_wind_drag

# Parameters to sweep and their display labels
SWEEP_PARAMS = [
    ("area",           "Panel Area (m²)"),
    ("efficiency",     "Cell Efficiency (%)"),
    ("temp_coeff",     "Temp Coefficient (%/°C)"),
    ("mppt",           "MPPT Efficiency (%)"),
    ("panel_temp",     "Panel Temperature (°C)"),
    ("num_motors",     "Number of Motors"),
    ("cruise_power",   "Cruise Power/Motor (W)"),
    ("batt_wh",        "Battery Capacity (Wh)"),
    ("airspeed",       "Airspeed (km/h)"),
    ("altitude",       "Altitude (m)"),
    ("wind_speed_ms",  "Headwind (m/s)"),
    ("panel_2_area",   "Panel 2 Area (m²)"),
]


def _run_one(params: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Run solar + power budget for params with given overrides."""
    p = {**params, **overrides}
    sol    = compute_point(p)
    wind   = compute_wind_drag(p)
    budget = compute_power_budget(p, sol["solar_power"], p_wind=wind["p_wind_w"])
    return {
        "solar_power": sol["solar_power"],
        "p_net":       budget["p_net"],
        "endurance":   budget["endurance"],  # None = sustainable
        "range_km":    budget["range_km"],
    }


def compute_sensitivity(params: Dict[str, Any], step_pct: float = 10.0) -> Dict[str, Any]:
    """
    One-at-a-time sensitivity analysis.

    For each parameter in SWEEP_PARAMS:
      - baseline: current value
      - low:  value * (1 - step_pct/100)
      - high: value * (1 + step_pct/100)

    Returns:
      baseline : dict (solar_power, p_net, endurance, range_km)
      rows     : list of dicts, one per swept parameter
      step_pct : the step percentage used
    """
    baseline = _run_one(params, {})

    rows: List[Dict[str, Any]] = []
    for key, label in SWEEP_PARAMS:
        if key not in params:
            continue
        base_val = params[key]
        if base_val == 0:
            continue  # skip zero-valued params to avoid division issues

        val_low  = base_val * (1.0 - step_pct / 100.0)
        val_high = base_val * (1.0 + step_pct / 100.0)

        # panel_temp: additive makes more sense than multiplicative for small values
        if key == "panel_temp":
            val_low  = base_val - step_pct
            val_high = base_val + step_pct

        res_low  = _run_one(params, {key: val_low})
        res_high = _run_one(params, {key: val_high})

        def _delta_end(res):
            """Change in effective endurance vs baseline (hours). None (sustainable) treated as 999."""
            b = baseline["endurance"] if baseline["endurance"] is not None else 999.0
            r = res["endurance"]      if res["endurance"]      is not None else 999.0
            return round(r - b, 2)

        def _delta_pnet(res):
            return round(res["p_net"] - baseline["p_net"], 2)

        rows.append({
            "param":         key,
            "label":         label,
            "base_val":      base_val,
            "low_val":       round(val_low, 4),
            "high_val":      round(val_high, 4),
            "pnet_low":      res_low["p_net"],
            "pnet_high":     res_high["p_net"],
            "delta_pnet_low":  _delta_pnet(res_low),
            "delta_pnet_high": _delta_pnet(res_high),
            "endurance_low":   res_low["endurance"],
            "endurance_high":  res_high["endurance"],
            "delta_end_low":   _delta_end(res_low),
            "delta_end_high":  _delta_end(res_high),
            # sensitivity magnitude: max |delta pnet| / (step% * base) → normalised
            "sensitivity_score": round(
                max(abs(_delta_pnet(res_low)), abs(_delta_pnet(res_high)))
                / (step_pct / 100.0 * abs(base_val) + 1e-9),
                3,
            ),
        })

    # Sort by sensitivity_score descending so most influential param is first
    rows.sort(key=lambda r: r["sensitivity_score"], reverse=True)

    return {
        "baseline": {
            "solar_power": baseline["solar_power"],
            "p_net":       baseline["p_net"],
            "endurance":   baseline["endurance"],
            "range_km":    baseline["range_km"],
        },
        "rows":     rows,
        "step_pct": step_pct,
    }
