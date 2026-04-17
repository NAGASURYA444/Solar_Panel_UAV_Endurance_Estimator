"""
Config comparison engine — run two parameter sets and produce a
side-by-side diff of all key metrics.
"""
from typing import Dict, Any, Tuple

from .solar import compute_point, compute_daily_profile, compute_sunrise_sunset
from .power import compute_power_budget, compute_min_area, get_verdict
from .wind_drag import compute_wind_drag


def _run(params: Dict[str, Any]) -> Dict[str, Any]:
    sol    = compute_point(params)
    wind   = compute_wind_drag(params)
    p_wind = wind["p_wind_w"]
    budget = compute_power_budget(params, sol["solar_power"], p_wind=p_wind)
    verd   = get_verdict(budget["p_net"], budget["p_total"], budget["endurance"])
    prof   = compute_daily_profile(params, budget["p_total"])
    sr     = compute_sunrise_sunset(params["lat"], params["month"], params["altitude"])
    mina   = compute_min_area(params, sol["poa"], p_wind=p_wind, poa2=sol.get("poa2", 0.0))
    return {
        "solar_power_w":    sol["solar_power"],
        "elevation_deg":    round(sol["elevation"], 1),
        "ghi_wm2":          sol["ghi"],
        "eff_actual_pct":   round(sol["eff_actual"], 2),
        "p_prop_w":         budget["p_prop"],
        "p_wind_w":         budget["p_wind"],
        "p_avion_w":        budget["p_avion"],
        "p_payload_w":      budget["p_payload"],
        "p_total_w":        budget["p_total"],
        "p_net_w":          budget["p_net"],
        "endurance_hrs":    budget["endurance"],
        "range_km":         budget["range_km"],
        "charge_time_hrs":  budget["charge_time_hrs"],
        "usable_wh":        budget["usable_wh"],
        "daily_energy_wh":  prof["daily_energy_wh"],
        "solar_window_hrs": prof["solar_window_hrs"],
        "sunrise":          sr["sunrise"],
        "sunset":           sr["sunset"],
        "night_hrs":        sr["night_hrs"],
        "min_area_m2":      round(mina, 2) if mina != float("inf") else None,
        "verdict":          verd["verdict"],
        "verdict_label":    verd["verdict_label"],
        "verdict_icon":     verd["verdict_icon"],
    }


# Metric display config: (label, unit, higher_is_better)
METRICS = [
    ("solar_power_w",    "Solar Power",       "W",     True),
    ("p_total_w",        "Consumption",       "W",     False),
    ("p_net_w",          "Net Balance",       "W",     True),
    ("endurance_hrs",    "Endurance",         "hrs",   True),
    ("range_km",         "Range",             "km",    True),
    ("daily_energy_wh",  "Daily Energy",      "Wh",    True),
    ("solar_window_hrs", "Solar Window",      "hrs",   True),
    ("usable_wh",        "Usable Capacity",   "Wh",    True),
    ("charge_time_hrs",  "Charge Time",       "hrs",   False),
    ("min_area_m2",      "Min Panel Area",    "m²",    False),
    ("eff_actual_pct",   "Actual Efficiency", "%",     True),
    ("night_hrs",        "Night Duration",    "hrs",   False),
    ("verdict_label",    "Verdict",           "",      None),
]


def compare_configs(params_a: Dict[str, Any],
                    params_b: Dict[str, Any],
                    label_a: str = "Config A",
                    label_b: str = "Config B") -> Dict[str, Any]:
    """
    Run both configs and return a comparison table.

    Each row in `rows` has:
        metric, label, unit,
        value_a, value_b,
        delta (b - a for numerics),
        winner: "a" | "b" | "tie" | None
    """
    res_a = _run(params_a)
    res_b = _run(params_b)

    rows = []
    for key, label, unit, higher_better in METRICS:
        va = res_a.get(key)
        vb = res_b.get(key)

        # Delta only for numeric fields
        delta = None
        winner = None
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            delta = round(vb - va, 3)
            if abs(delta) < 1e-6:
                winner = "tie"
            elif higher_better is True:
                winner = "b" if delta > 0 else "a"
            elif higher_better is False:
                winner = "a" if delta > 0 else "b"

        rows.append({
            "metric":  key,
            "label":   label,
            "unit":    unit,
            "value_a": va,
            "value_b": vb,
            "delta":   delta,
            "winner":  winner,
        })

    wins_a = sum(1 for r in rows if r["winner"] == "a")
    wins_b = sum(1 for r in rows if r["winner"] == "b")

    return {
        "label_a":  label_a,
        "label_b":  label_b,
        "result_a": res_a,
        "result_b": res_b,
        "rows":     rows,
        "wins_a":   wins_a,
        "wins_b":   wins_b,
        "overall_winner": "a" if wins_a > wins_b else ("b" if wins_b > wins_a else "tie"),
    }
