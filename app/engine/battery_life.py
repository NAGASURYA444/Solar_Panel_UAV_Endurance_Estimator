"""
Battery Cycle Life Model.

Estimates remaining battery capacity and cycle life based on:
  1. Chemistry-specific cycle-to-80%-capacity counts
  2. Daily depth-of-discharge (DoD) from the 24h SOC simulation
  3. DoD-adjusted cycle life (Woehler/power-law model)

Reference cycle counts (to 80% capacity):
  LiPo:    ~400 cycles at 80% DoD, ~800 at 50% DoD
  Li-Ion:  ~800 cycles at 80% DoD, ~1500 at 50% DoD
  LiFePO4: ~2000 cycles at 80% DoD, ~4000 at 50% DoD

Woehler exponent β ≈ 1.2–1.4 for Li-chemistries (conservative: 1.3)
  N(DoD) = N_ref × (DoD_ref / DoD) ^ β
"""
from typing import Dict, Any, List

# Reference cycle counts at reference DoD
CYCLE_REF = {
    "lipo":    {"n_ref": 400,  "dod_ref": 0.80, "beta": 1.3},
    "liion":   {"n_ref": 800,  "dod_ref": 0.80, "beta": 1.3},
    "lifepo4": {"n_ref": 2000, "dod_ref": 0.80, "beta": 1.3},
}

# Capacity fade model: linear fade from 100% to 80% over N_ref cycles,
# then faster fade (accelerated) below 80%
def _capacity_at_cycle(n_cycles: int, n_ref: int) -> float:
    """Remaining capacity fraction at n_cycles."""
    if n_cycles <= 0:
        return 1.0
    if n_cycles <= n_ref:
        # Linear fade 100% → 80% over n_ref cycles
        return 1.0 - 0.20 * (n_cycles / n_ref)
    else:
        # Accelerated fade below 80%: additional 1% per 10% of n_ref
        extra = (n_cycles - n_ref) / n_ref
        return max(0.0, 0.80 - 0.10 * extra)


def compute_battery_life(
    params: Dict[str, Any],
    soc_24h: List[float],              # 49-element SOC array from compute_soc_24h
    missions_per_day: float = 1.0,
    projection_years: int = 5,
) -> Dict[str, Any]:
    """
    Estimate battery cycle life based on daily DoD from the SOC simulation.

    Returns:
        daily_dod_pct      : daily depth-of-discharge (%)
        cycles_to_80pct    : estimated cycles before capacity drops to 80%
        days_to_80pct      : days of operation until 80% capacity
        years_to_80pct     : years until 80% capacity (at missions_per_day)
        yearly_projection  : list of {year, cycles, capacity_pct, usable_wh}
        current_usable_wh  : usable Wh at current state
        chemistry          : battery chemistry used
        recommendation     : usage advice string
    """
    chem    = params["batt_chem"]
    batt_wh = params["batt_wh"]
    min_soc = params["min_soc"]

    ref = CYCLE_REF.get(chem, CYCLE_REF["lipo"])
    n_ref   = ref["n_ref"]
    dod_ref = ref["dod_ref"]
    beta    = ref["beta"]

    # Daily DoD from SOC simulation: peak - trough across the day
    soc_max = max(soc_24h)
    soc_min = min(soc_24h)
    daily_dod_pct = max(0.0, soc_max - soc_min)
    daily_dod     = daily_dod_pct / 100.0

    # Woehler-adjusted cycle life
    if daily_dod > 0:
        cycles_to_80 = max(1, int(n_ref * (dod_ref / daily_dod) ** beta))
    else:
        cycles_to_80 = n_ref * 10   # barely cycled → very long life

    days_to_80   = int(cycles_to_80 / max(missions_per_day, 0.1))
    years_to_80  = round(days_to_80 / 365.25, 1)

    # Initial usable capacity
    from .solar import BATT_DISCHARGE_EFF
    d_eff        = BATT_DISCHARGE_EFF.get(chem, 0.95)
    usable_now   = batt_wh * (1.0 - min_soc / 100.0) * d_eff

    # Yearly projection
    yearly = []
    cycles_per_year = int(missions_per_day * 365.25)
    for yr in range(0, projection_years + 1):
        n_cyc   = yr * cycles_per_year
        cap_frac = _capacity_at_cycle(n_cyc, cycles_to_80)
        uw       = round(usable_now * cap_frac, 1)
        yearly.append({
            "year":         yr,
            "cycles":       n_cyc,
            "capacity_pct": round(cap_frac * 100, 1),
            "usable_wh":    uw,
        })

    # Recommendation
    if daily_dod_pct > 70:
        rec = f"High DoD ({daily_dod_pct:.0f}%). Consider larger battery to reduce daily cycling."
    elif daily_dod_pct > 40:
        rec = f"Moderate DoD ({daily_dod_pct:.0f}%). Battery life is acceptable."
    else:
        rec = f"Low DoD ({daily_dod_pct:.0f}%). Excellent cycle life — battery well-sized."

    return {
        "daily_dod_pct":    round(daily_dod_pct, 1),
        "cycles_to_80pct":  cycles_to_80,
        "days_to_80pct":    days_to_80,
        "years_to_80pct":   years_to_80,
        "yearly_projection": yearly,
        "current_usable_wh": round(usable_now, 1),
        "chemistry":        chem,
        "n_ref":            n_ref,
        "recommendation":   rec,
        "missions_per_day": missions_per_day,
    }
