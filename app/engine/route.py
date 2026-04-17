"""
Route Map Planner engine.

Evaluates a multi-waypoint flight route by computing, for each leg:
  - Great-circle distance (Haversine)
  - Flight time based on ground speed (airspeed ± wind)
  - Solar energy harvested (pvlib at mid-leg lat, mid-leg time)
  - Energy consumed
  - Running battery SOC

Assumptions
-----------
- All waypoints share the same altitude (from base params)
- Solar time is based on pvlib lon=0 convention (solar time)
- Wind is modelled as a persistent headwind on every leg
- Single solar panel configuration (no mid-route changes)
"""
import math
from typing import Dict, Any, List

from .solar import compute_point, BATT_DISCHARGE_EFF
from .wind_drag import compute_wind_drag


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R   = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ  = math.radians(lat2 - lat1)
    Δλ  = math.radians(lon2 - lon1)
    a   = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return 2.0 * R * math.asin(math.sqrt(min(1.0, a)))


def compute_route(
    params: Dict[str, Any],
    waypoints: List[Dict[str, float]],   # [{lat, lon}, ...]
    start_time_hrs: float = 7.0,
) -> Dict[str, Any]:
    """
    Evaluate a multi-waypoint route.

    Parameters
    ----------
    params         : UAVParams dict
    waypoints      : list of at least 2 {lat, lon} dicts
    start_time_hrs : departure time (solar hours, 0–23)

    Returns
    -------
    dict with:
        legs              : list of per-leg dicts
        total_distance_km
        total_time_hrs
        final_soc
        mission_feasible  : bool (final SOC > min_soc and no leg forced SOC to floor)
        waypoints_echoed  : list echoed back
    """
    if len(waypoints) < 2:
        return {
            "legs": [], "total_distance_km": 0.0, "total_time_hrs": 0.0,
            "final_soc": 100.0, "mission_feasible": False,
            "waypoints_echoed": waypoints,
            "error": "Need at least 2 waypoints.",
        }

    d_eff  = BATT_DISCHARGE_EFF.get(params["batt_chem"], 0.95)
    c_eff  = params["charge_eff"] / 100.0
    batt   = float(params["batt_wh"])
    min_s  = float(params["min_soc"])

    wind         = compute_wind_drag(params)
    p_wind       = wind["p_wind_w"]
    ground_speed = max(1.0, wind["ground_speed_kmh"])   # km/h, never zero

    p_prop    = params["num_motors"] * params["cruise_power"]
    p_avion   = params["power_fc"] + params["power_tel"]
    p_payload = params["power_payload"]
    p_other   = params["power_other"]
    p_total   = p_prop + p_wind + p_avion + p_payload + p_other

    soc          = 100.0
    current_time = start_time_hrs
    legs: List[Dict[str, Any]] = []
    any_floor_hit = False

    for i in range(len(waypoints) - 1):
        wp1 = waypoints[i]
        wp2 = waypoints[i + 1]

        dist_km  = _haversine_km(wp1["lat"], wp1["lon"], wp2["lat"], wp2["lon"])
        fly_hrs  = dist_km / ground_speed
        mid_time = current_time + fly_hrs / 2.0
        mid_lat  = (wp1["lat"] + wp2["lat"]) / 2.0

        # Clamp time to 0–24 range for pvlib
        mid_time_clamped = mid_time % 24.0

        # Solar at mid-point
        leg_params = {**params, "lat": mid_lat, "time_hrs": mid_time_clamped}
        sol        = compute_point(leg_params)
        solar_w    = sol["solar_power"]

        solar_wh   = solar_w * fly_hrs
        consume_wh = p_total * fly_hrs
        net_wh     = solar_wh - consume_wh

        # Update SOC
        if net_wh >= 0:
            soc += (net_wh * c_eff) / batt * 100.0
        else:
            soc += net_wh / (batt * d_eff) * 100.0
        soc = max(min_s, min(100.0, soc))

        if soc <= min_s + 0.05:
            any_floor_hit = True

        legs.append({
            "leg":          i + 1,
            "from_wp":      i,
            "to_wp":        i + 1,
            "from_lat":     round(wp1["lat"], 4),
            "from_lon":     round(wp1["lon"], 4),
            "to_lat":       round(wp2["lat"], 4),
            "to_lon":       round(wp2["lon"], 4),
            "distance_km":  round(dist_km, 1),
            "flight_time_hrs": round(fly_hrs, 2),
            "start_time":   round(current_time, 2),
            "end_time":     round(current_time + fly_hrs, 2),
            "mid_lat":      round(mid_lat, 4),
            "solar_w":      round(solar_w, 1),
            "solar_wh":     round(solar_wh, 1),
            "consume_wh":   round(consume_wh, 1),
            "net_wh":       round(net_wh, 1),
            "soc_end":      round(soc, 1),
            "feasible":     soc > min_s,
        })

        current_time += fly_hrs

    total_dist = sum(leg["distance_km"]     for leg in legs)
    total_time = sum(leg["flight_time_hrs"] for leg in legs)

    return {
        "legs":               legs,
        "total_distance_km":  round(total_dist, 1),
        "total_time_hrs":     round(total_time, 2),
        "final_soc":          round(soc, 1),
        "mission_feasible":   (soc > min_s) and not any_floor_hit,
        "ground_speed_kmh":   round(ground_speed, 1),
        "p_total_w":          round(p_total, 1),
        "waypoints_echoed":   waypoints,
    }
