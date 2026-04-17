"""
Battery Temperature Derating engine.

Real Li-* batteries lose usable capacity at cold temperatures.
Derating curves by chemistry (empirically-derived approximations):

    LiPo    — most cold-sensitive: loses ~40% at −20°C vs 25°C
    Li-Ion  — moderately sensitive: loses ~25% at −20°C
    LiFePO4 — most resilient: loses only ~15% at −20°C

Formula:
    capacity_pct = 100 × (1 − max(0, (25 − T) / 25) × factor)
    clamped to [clamp_low, 100]

Above 25°C capacity stays at 100% (batteries don't gain capacity with heat
within safe operating range; heat accelerates degradation separately).
"""
from typing import Dict, Any, List

from .solar import BATT_DISCHARGE_EFF

DERATING: Dict[str, Dict] = {
    "lipo":    {"factor": 0.40, "clamp_low": 60},
    "liion":   {"factor": 0.25, "clamp_low": 70},
    "lifepo4": {"factor": 0.15, "clamp_low": 80},
}


def _capacity_pct(temp_c: float, chemistry: str) -> float:
    cfg    = DERATING.get(chemistry, DERATING["lipo"])
    factor = cfg["factor"]
    clamp  = cfg["clamp_low"]
    raw    = 100.0 * (1.0 - max(0.0, (25.0 - temp_c) / 25.0) * factor)
    return max(float(clamp), min(100.0, raw))


def compute_batt_temp(
    params: Dict[str, Any],
    temp_min_c: float = -20.0,
    temp_max_c: float = 60.0,
) -> Dict[str, Any]:
    """
    Return capacity derating table from temp_min_c to temp_max_c in 5°C steps.

    Returns
    -------
    dict with:
        table              : list of {temp_c, capacity_pct, usable_wh, endurance_hrs}
        chemistry          : batt_chem string
        nominal_usable_wh  : usable Wh at 25°C reference
        worst_case_usable_wh
        worst_case_temp_c
        optimal_range_note : human-readable note
    """
    batt_chem = params["batt_chem"]
    batt_wh   = float(params["batt_wh"])
    min_soc   = float(params["min_soc"])
    d_eff     = BATT_DISCHARGE_EFF.get(batt_chem, 0.95)

    # Compute p_total for endurance estimate (including wind)
    from .wind_drag import compute_wind_drag
    wind   = compute_wind_drag(params)
    p_wind = wind["p_wind_w"]

    p_prop    = params["num_motors"] * params["cruise_power"]
    p_avion   = params["power_fc"] + params["power_tel"]
    p_payload = params["power_payload"]
    p_other   = params["power_other"]
    p_total   = p_prop + p_wind + p_avion + p_payload + p_other

    table: List[Dict[str, Any]] = []
    temp = temp_min_c
    while temp <= temp_max_c + 0.1:
        cap_pct  = _capacity_pct(temp, batt_chem)
        usable   = batt_wh * (cap_pct / 100.0) * (1.0 - min_soc / 100.0) * d_eff
        end_hrs  = round(usable / p_total, 2) if p_total > 0 else None
        table.append({
            "temp_c":       round(temp, 1),
            "capacity_pct": round(cap_pct, 1),
            "usable_wh":    round(usable, 1),
            "endurance_hrs": end_hrs,
        })
        temp += 5.0

    nominal_usable = batt_wh * (1.0 - min_soc / 100.0) * d_eff
    worst_row = min(table, key=lambda r: r["usable_wh"])

    cfg = DERATING.get(batt_chem, DERATING["lipo"])
    loss_at_minus20 = round(100 - _capacity_pct(-20.0, batt_chem), 1)

    return {
        "table":                  table,
        "chemistry":              batt_chem,
        "nominal_usable_wh":      round(nominal_usable, 1),
        "worst_case_usable_wh":   worst_row["usable_wh"],
        "worst_case_temp_c":      worst_row["temp_c"],
        "loss_at_minus20_pct":    loss_at_minus20,
        "optimal_range_note":     f"{batt_chem.upper()} loses {loss_at_minus20}% capacity at −20°C vs 25°C reference.",
    }
