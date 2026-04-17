"""
Monte Carlo Sensitivity Analysis.

Simultaneously randomises all solar + power parameters within ±uncertainty_pct
and reports the probability distribution of net-power outcomes.

Performance: pvlib is called ONCE for the baseline POA. All N samples are
evaluated with pure NumPy array operations (no per-sample pvlib calls),
so 500 samples completes in < 100 ms regardless of machine speed.

Parameters varied (multiplicative ±frac, except noted):
    area, efficiency, temp_coeff (*), mppt, panel_temp (additive ±°C),
    cruise_power, power_payload, power_other, batt_wh, wind_speed_ms

(*) temp_coeff stays negative; clamped to [-1.0, 0.0].
"""
import numpy as np
from typing import Dict, Any, List

from .solar import compute_point, BATT_DISCHARGE_EFF

# Parameters to vary and their variation type
# "mult"  → new_val = base * Uniform(1-frac, 1+frac)
# "add"   → new_val = base + Uniform(-pct, +pct)   (used for °C)
_MC_PARAMS: List[tuple] = [
    ("area",           "mult"),
    ("efficiency",     "mult"),
    ("temp_coeff",     "mult"),   # kept ≤ 0 after sampling
    ("mppt",           "mult"),
    ("panel_temp",     "add"),    # ±uncertainty_pct degrees
    ("cruise_power",   "mult"),
    ("power_payload",  "mult"),
    ("power_other",    "mult"),
    ("batt_wh",        "mult"),
    ("wind_speed_ms",  "mult"),   # wind variation adds drag uncertainty
]


def compute_monte_carlo(
    params: Dict[str, Any],
    n_samples: int = 500,
    uncertainty_pct: float = 10.0,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Run Monte Carlo sensitivity analysis.

    Returns
    -------
    dict with keys:
        n_samples, n_valid
        n_sustainable, n_marginal, n_battery_assisted, n_insufficient
        prob_* (four floats 0–1)
        pnet_p5 … pnet_p95 (seven percentiles of net power)
        endurance_p10/p50/p90  (only when battery-limited runs exist)
        histogram  : list of {bin_label, bin_min, bin_max, count}
        params_varied : list of param names
        uncertainty_pct, baseline_pnet, baseline_verdict
    """
    # ── Step 1: single pvlib call for baseline POA ───────────────────────────
    sol_base = compute_point(params)
    poa_base = float(sol_base["poa"])          # scalar W/m²

    p_prop_base = params["num_motors"] * params["cruise_power"]
    p_avion_base = float(params.get("power_fc", 5.0)) + float(params.get("power_tel", 3.0))
    p_total_base = p_prop_base + p_avion_base + params["power_payload"] + params["power_other"]
    pnet_base = sol_base["solar_power"] - p_total_base

    d_eff = BATT_DISCHARGE_EFF.get(params["batt_chem"], 0.95)
    min_soc = float(params["min_soc"])

    if pnet_base > 0:
        margin_base = pnet_base / p_total_base if p_total_base > 0 else 1.0
        verdict_base = "sustainable" if margin_base >= 0.15 else "marginal"
    else:
        usable_base = params["batt_wh"] * (1 - min_soc / 100.0) * d_eff
        end_base = usable_base / max(-pnet_base, 1e-9)
        verdict_base = "battery_assisted" if end_base >= 4.0 else "insufficient"

    # ── Step 2: generate all samples as NumPy arrays (no loop over pvlib) ───
    rng = np.random.default_rng(seed)
    n = n_samples
    frac = uncertainty_pct / 100.0

    def _sample(key: str, vtype: str) -> np.ndarray:
        base = float(params.get(key, 0.0))
        if vtype == "add":
            arr = base + rng.uniform(-uncertainty_pct, uncertainty_pct, n)
        else:
            arr = base * rng.uniform(1.0 - frac, 1.0 + frac, n)
        return arr

    area_s    = np.maximum(0.01, _sample("area",           "mult"))
    eff_s     = np.clip(_sample("efficiency",     "mult"), 0.5,  50.0)
    tc_s      = np.clip(_sample("temp_coeff",     "mult"), -1.0,  0.0)
    mppt_s    = np.clip(_sample("mppt",           "mult"), 50.0, 100.0)
    pt_s      = np.clip(_sample("panel_temp",     "add"),  -20.0, 100.0)
    cp_s      = np.maximum(0.1, _sample("cruise_power",   "mult"))
    pp_s      = np.maximum(0.0, _sample("power_payload",  "mult"))
    po_s      = np.maximum(0.0, _sample("power_other",    "mult"))
    bw_s      = np.maximum(1.0, _sample("batt_wh",        "mult"))
    wind_s    = np.maximum(0.0, _sample("wind_speed_ms",  "mult"))

    # ── Step 3: vectorised power budget ──────────────────────────────────────
    eff_actual = eff_s * (1.0 + (tc_s / 100.0) * (pt_s - 25.0))
    eff_actual = np.maximum(eff_actual, 0.01)
    solar_w    = np.maximum(0.0, area_s * (eff_actual / 100.0) * poa_base * (mppt_s / 100.0))

    p_prop      = params["num_motors"] * cp_s
    airspeed_ms = float(params["airspeed"]) / 3.6
    # Wind drag: extra propulsive power due to headwind
    p_wind      = np.where(
        (wind_s > 0) & (airspeed_ms > 0),
        p_prop * ((airspeed_ms + wind_s) / airspeed_ms) ** 2 - p_prop,
        0.0,
    )
    p_wind      = np.maximum(0.0, p_wind)
    p_avion     = float(params.get("power_fc", 5.0)) + float(params.get("power_tel", 3.0))
    p_total     = p_prop + p_wind + p_avion + pp_s + po_s
    p_net       = solar_w - p_total

    usable_wh  = bw_s * (1.0 - min_soc / 100.0) * d_eff
    endurance  = np.where(p_net < 0, usable_wh / np.maximum(-p_net, 1e-9), np.inf)

    # ── Step 4: classify verdicts ─────────────────────────────────────────────
    margin = np.where(p_total > 0, p_net / p_total, 1.0)
    is_sust = (p_net > 0) & (margin >= 0.15)
    is_marg = (p_net > 0) & (margin < 0.15)
    is_batt = (p_net < 0) & (endurance >= 4.0)
    is_insuf = (p_net < 0) & (endurance < 4.0)

    n_sust  = int(np.sum(is_sust))
    n_marg  = int(np.sum(is_marg))
    n_batt  = int(np.sum(is_batt))
    n_insuf = int(np.sum(is_insuf))
    n_valid = n_sust + n_marg + n_batt + n_insuf

    # ── Step 5: percentiles ───────────────────────────────────────────────────
    def _pct(arr, q):
        return round(float(np.percentile(arr, q)), 1)

    pnet_stats = {
        "pnet_p5":  _pct(p_net, 5),
        "pnet_p10": _pct(p_net, 10),
        "pnet_p25": _pct(p_net, 25),
        "pnet_p50": _pct(p_net, 50),
        "pnet_p75": _pct(p_net, 75),
        "pnet_p90": _pct(p_net, 90),
        "pnet_p95": _pct(p_net, 95),
    }

    end_stats = {}
    batt_end = endurance[p_net < 0]
    if len(batt_end) > 0:
        end_stats = {
            "endurance_p10": round(float(np.percentile(batt_end, 10)), 2),
            "endurance_p50": round(float(np.percentile(batt_end, 50)), 2),
            "endurance_p90": round(float(np.percentile(batt_end, 90)), 2),
        }

    # ── Step 6: histogram (20 bins over p_net range) ─────────────────────────
    hist_counts, hist_edges = np.histogram(p_net, bins=20)
    histogram = [
        {
            "bin_label": f"{hist_edges[i]:.0f}",
            "bin_min":   round(float(hist_edges[i]),   1),
            "bin_max":   round(float(hist_edges[i+1]), 1),
            "count":     int(hist_counts[i]),
        }
        for i in range(len(hist_counts))
    ]

    return {
        "n_samples":           n_samples,
        "n_valid":             n_valid,
        "n_sustainable":       n_sust,
        "n_marginal":          n_marg,
        "n_battery_assisted":  n_batt,
        "n_insufficient":      n_insuf,
        "prob_sustainable":    round(n_sust  / n_valid, 3) if n_valid else 0.0,
        "prob_marginal":       round(n_marg  / n_valid, 3) if n_valid else 0.0,
        "prob_battery_assisted": round(n_batt  / n_valid, 3) if n_valid else 0.0,
        "prob_insufficient":   round(n_insuf / n_valid, 3) if n_valid else 0.0,
        **pnet_stats,
        **end_stats,
        "histogram":           histogram,
        "params_varied":       [k for k, _ in _MC_PARAMS],
        "uncertainty_pct":     uncertainty_pct,
        "baseline_pnet":       round(pnet_base, 1),
        "baseline_verdict":    verdict_base,
    }
