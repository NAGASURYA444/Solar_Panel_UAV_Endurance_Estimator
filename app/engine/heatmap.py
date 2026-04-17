"""
Annual solar energy heatmap — daily solar energy for all 365 days.

Computes daily_energy_wh for every day of the year by iterating
over all 365 day-of-year values using mid-day POA as a proxy,
then integrating the 05:00–19:00 profile.

For performance, uses vectorised pvlib calls in monthly batches.
Returns a 365-element array suitable for a calendar heatmap.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, List

from .solar import get_poa, panel_power

# Day-of-year for each calendar date (non-leap year)
# We compute this dynamically per day using pvlib directly
_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_MONTH_NAMES   = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"]


def _doy_for_day(month: int, day: int) -> int:
    """Day-of-year (1-indexed) for a given month/day (non-leap year)."""
    return sum(_DAYS_IN_MONTH[:month - 1]) + day


def compute_annual_heatmap(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute daily solar energy (Wh) for every day of the year.

    Strategy: for each calendar day, build a 29-point (05:00–19:00)
    time series and integrate panel power.

    Returns:
        days         : list of 365 dicts {doy, month, day, month_name,
                       date_label, energy_wh, pct_of_max}
        max_energy   : peak daily energy across the year (Wh)
        min_energy   : minimum non-zero daily energy (Wh)
        annual_total : sum of all daily energies (Wh)
        best_month   : month with highest average daily energy
        worst_month  : month with lowest average daily energy
        monthly_avg  : list of 12 monthly average daily energies
    """
    import pvlib

    lat      = params["lat"]
    altitude = params["altitude"]
    clarity  = params["clarity"]
    tilt     = params["tilt"]
    area     = params["area"]
    eff      = params["efficiency"]
    tc       = params["temp_coeff"]
    pt       = params["panel_temp"]
    mppt_e   = params["mppt"]

    days_out  = []
    doy       = 0
    month_totals = [0.0] * 12
    month_counts = [0]   * 12

    for m in range(1, 13):
        n_days = _DAYS_IN_MONTH[m - 1]
        for d in range(1, n_days + 1):
            doy += 1
            day_of_year = _doy_for_day(m, d)

            # Build 29-step time series for this specific day
            base = pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=day_of_year - 1)
            times = pd.date_range(
                start=base + pd.Timedelta(hours=5),
                periods=29,
                freq="30min",
            )

            poa_arr  = get_poa(lat, altitude, times, clarity, tilt)
            pow_arr  = panel_power(poa_arr, area, eff, tc, pt, mppt_e)
            energy   = float(np.sum(pow_arr) * 0.5)   # Wh (30-min steps)

            days_out.append({
                "doy":        doy,
                "month":      m,
                "day":        d,
                "month_name": _MONTH_NAMES[m - 1],
                "date_label": f"{_MONTH_NAMES[m-1]} {d}",
                "energy_wh":  round(energy, 1),
                "pct_of_max": 0.0,   # filled in below
            })
            month_totals[m - 1] += energy
            month_counts[m - 1] += 1

    # Normalise pct_of_max
    max_e = max(d["energy_wh"] for d in days_out) if days_out else 1.0
    min_e = min(d["energy_wh"] for d in days_out if d["energy_wh"] > 0) if days_out else 0.0

    for d in days_out:
        d["pct_of_max"] = round(d["energy_wh"] / max_e * 100, 1) if max_e > 0 else 0.0

    annual_total = sum(d["energy_wh"] for d in days_out)
    monthly_avg  = [
        round(month_totals[i] / month_counts[i], 1) if month_counts[i] > 0 else 0.0
        for i in range(12)
    ]

    best_month  = monthly_avg.index(max(monthly_avg)) + 1
    worst_month = monthly_avg.index(min(monthly_avg)) + 1

    return {
        "days":         days_out,
        "max_energy":   round(max_e, 1),
        "min_energy":   round(min_e, 1),
        "annual_total": round(annual_total, 0),
        "monthly_avg":  monthly_avg,
        "best_month":   best_month,
        "best_month_name":  _MONTH_NAMES[best_month - 1],
        "worst_month":  worst_month,
        "worst_month_name": _MONTH_NAMES[worst_month - 1],
    }
