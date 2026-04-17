"""
Panel Degradation Model.

Models how solar panel efficiency and power output decline over N years.

Degradation sources modelled:
  1. LID  — Light Induced Degradation: ~1.5% power loss in year 1
  2. Annual degradation: typically 0.3–0.8 %/year for modern panels
  3. Cumulative efficiency after N years

Reference: IEC 61215, NREL degradation study (Jordan & Kurtz, 2013).
Typical rates:
  Monocrystalline (SunPower Maxeon): 0.25 %/yr
  Standard mono c-Si:                0.50 %/yr
  PERC / bifacial:                   0.45 %/yr
  Thin-film CIGS:                    0.50 %/yr
  GaAs:                              0.30 %/yr
"""
from typing import Dict, Any, List

# Preset degradation rates (%/year after LID)
DEGRADATION_RATES = {
    "sunpower":  0.25,   # SunPower Maxeon — best-in-class
    "monocsi":   0.50,
    "perc":      0.45,
    "thinfilm":  0.50,
    "gaas":      0.30,
    "custom":    0.50,
}

LID_LOSS_PCT = 1.5      # % loss in year 1 from LID (applied once)
WARRANTY_YEARS = 25     # standard linear power warranty duration


def compute_degradation(
    params: Dict[str, Any],
    solar_power_w: float,
    years: int = 15,
    annual_rate_pct: float = 0.50,
    lid_pct: float = LID_LOSS_PCT,
) -> Dict[str, Any]:
    """
    Project panel power and efficiency over `years` years.

    Returns:
        yearly       : list of yearly dicts (year, eff, power_w, pct_of_new)
        year_80pct   : year at which output drops below 80% (warranty threshold)
        power_new    : initial solar power (W)
        power_y25    : projected power at year 25 (W)
        annual_rate  : rate used (%/yr)
    """
    initial_eff = params["efficiency"]   # % STC
    yearly: List[Dict[str, Any]] = []

    power_new = solar_power_w
    year_80pct = None

    for y in range(0, years + 1):
        if y == 0:
            eff   = initial_eff
            power = power_new
            retention = 100.0
        elif y == 1:
            # Year 1: LID + first year annual degradation
            retention = 100.0 - lid_pct - annual_rate_pct
            eff   = initial_eff * retention / 100.0
            power = power_new  * retention / 100.0
        else:
            # Subsequent years: compound annual degradation from year-1 baseline
            year_1_retention = 100.0 - lid_pct - annual_rate_pct
            retention = year_1_retention * ((1 - annual_rate_pct / 100) ** (y - 1))
            eff   = initial_eff * retention / 100.0
            power = power_new  * retention / 100.0

        pct_of_new = round(power / power_new * 100, 2) if power_new > 0 else 0.0

        if year_80pct is None and pct_of_new < 80.0 and y > 0:
            year_80pct = y

        yearly.append({
            "year":       y,
            "efficiency": round(eff, 3),
            "power_w":    round(power, 2),
            "pct_of_new": pct_of_new,
            "retention":  round(retention, 2),
        })

    # Power at year 25 (extrapolate if years < 25)
    year_1_ret = 100.0 - lid_pct - annual_rate_pct
    ret_25     = year_1_ret * ((1 - annual_rate_pct / 100) ** 24)
    power_y25 = round(power_new * ret_25 / 100, 2)

    return {
        "yearly":       yearly,
        "year_80pct":   year_80pct if year_80pct else f">{years}",
        "power_new":    round(power_new, 2),
        "power_y25":    power_y25,
        "pct_y25":      round(ret_25, 2),
        "annual_rate":  annual_rate_pct,
        "lid_pct":      lid_pct,
        "years":        years,
    }
