"""
Flight Profile vs Altitude engine.

Sweeps altitude from 0 → alt_max_m and at each step computes:
  - Solar power  (pvlib handles increased irradiance at altitude via turbidity)
  - Adjusted cruise power  (less dense air → less aerodynamic drag)
  - Net power balance and verdict

Air density model:  rho = 1.225 * exp(-alt / 8500)  kg/m³
Propulsion model:   P_cruise_adj = P_cruise_base * (rho / rho0)
  — valid for fixed-pitch prop UAVs where drag ∝ air density at constant TAS.

Note: pvlib's Ineichen model already accounts for altitude via the
      Location(altitude=…) parameter and the AM correction it applies,
      so solar_w naturally increases with altitude.
"""
import math
from typing import Dict, Any, List

from .solar import compute_point
from .wind_drag import compute_wind_drag

RHO0 = 1.225   # sea-level air density kg/m³


def compute_altitude_profile(
    params: Dict[str, Any],
    alt_max_m: float = 8000.0,
    steps: int = 20,
) -> Dict[str, Any]:
    """
    Return per-altitude performance profile.

    Returns
    -------
    dict with:
        profile : list of step dicts
        alt_max_m, steps
        crossover_alt_m : altitude where p_net first becomes >= 0 (or None)
        sea_level_solar_w, sea_level_p_total_w
    """
    results: List[Dict[str, Any]] = []
    crossover_alt: float | None = None
    prev_pnet = None

    for i in range(steps + 1):
        alt = round(alt_max_m * i / steps, 1)
        rho = 1.225 * math.exp(-alt / 8500.0)
        density_ratio = rho / RHO0

        # Solar at this altitude (pvlib turbidity-corrected)
        alt_params = {**params, "altitude": alt}
        sol = compute_point(alt_params)
        solar_w = sol["solar_power"]

        # Wind drag at this altitude (uses same wind_speed_ms)
        wind = compute_wind_drag(alt_params)
        p_wind = wind["p_wind_w"]

        # Cruise power scales with air density
        cruise_adj = params["cruise_power"] * density_ratio
        p_prop_adj = params["num_motors"] * cruise_adj + p_wind
        p_avion    = params["power_fc"] + params["power_tel"]
        p_payload  = params["power_payload"]
        p_other    = params["power_other"]
        p_total    = p_prop_adj + p_avion + p_payload + p_other
        p_net      = solar_w - p_total

        # Detect crossover (negative → positive p_net)
        if prev_pnet is not None and prev_pnet < 0 and p_net >= 0 and crossover_alt is None:
            crossover_alt = alt
        prev_pnet = p_net

        if p_net > 0:
            margin = p_net / p_total if p_total > 0 else 1.0
            verdict = "sustainable" if margin >= 0.15 else "marginal"
        else:
            verdict = "insufficient"

        results.append({
            "altitude_m":        alt,
            "air_density":       round(rho, 4),
            "density_ratio":     round(density_ratio, 4),
            "solar_w":           round(solar_w, 1),
            "cruise_power_adj_w": round(cruise_adj, 1),
            "p_total_w":         round(p_total, 1),
            "p_net_w":           round(p_net, 1),
            "verdict":           verdict,
        })

    return {
        "profile":            results,
        "alt_max_m":          alt_max_m,
        "steps":              steps,
        "crossover_alt_m":    crossover_alt,
        "sea_level_solar_w":  results[0]["solar_w"],
        "sea_level_p_total_w": results[0]["p_total_w"],
    }
