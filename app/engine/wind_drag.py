"""
Wind drag model for solar UAV propulsion.

Physical model: for a fixed-wing UAV at constant airspeed, a headwind
increases the effective drag on the airframe. Simplified power penalty:

    P_wind = P_prop * ((v_air_ms + v_wind_ms) / v_air_ms)^2 - P_prop

where P_prop = num_motors * cruise_power.  This is a first-order
aerodynamic drag approximation (power ∝ v²) widely used in UAV
energy estimation.  When wind_speed_ms == 0, P_wind == 0 exactly —
backward-compatible with any existing caller.

Ground speed (for range/mission purposes):
    ground_speed = max(0, airspeed_kmh - wind_speed_ms * 3.6)
"""
from typing import Dict, Any


def compute_wind_drag(params: Dict[str, Any]) -> Dict[str, float]:
    """
    Compute extra propulsive power and ground speed due to headwind.

    Parameters
    ----------
    params : UAVParams dict — uses airspeed, num_motors, cruise_power,
             wind_speed_ms (defaults to 0.0 if absent).

    Returns
    -------
    dict with:
        p_wind_w         : extra propulsive power (W), always >= 0
        ground_speed_kmh : effective ground speed (km/h), >= 0
        wind_speed_ms    : echo of input
    """
    wind_ms       = float(params.get("wind_speed_ms", 0.0))
    airspeed_kmh  = float(params["airspeed"])
    cruise_power  = float(params["cruise_power"])
    num_motors    = int(params["num_motors"])

    p_prop        = num_motors * cruise_power
    ground_speed  = max(0.0, airspeed_kmh - wind_ms * 3.6)

    if wind_ms <= 0.0 or airspeed_kmh <= 0.0:
        return {
            "p_wind_w":         0.0,
            "ground_speed_kmh": round(ground_speed, 1),
            "wind_speed_ms":    wind_ms,
        }

    airspeed_ms = airspeed_kmh / 3.6
    p_wind = p_prop * ((airspeed_ms + wind_ms) / airspeed_ms) ** 2 - p_prop

    return {
        "p_wind_w":         round(max(0.0, p_wind), 1),
        "ground_speed_kmh": round(ground_speed, 1),
        "wind_speed_ms":    wind_ms,
    }
