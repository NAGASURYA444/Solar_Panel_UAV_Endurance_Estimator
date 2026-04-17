"""Power budget calculations — propulsion, avionics, net balance, endurance."""
from typing import Dict, Any

BATT_DISCHARGE_EFF = {"lipo": 0.95, "liion": 0.97, "lifepo4": 0.96}


def compute_power_budget(params: Dict[str, Any], solar_power: float,
                         p_wind: float = 0.0) -> Dict[str, Any]:
    """
    Full power budget.  p_wind is the extra propulsive drag power from
    headwind (computed by wind_drag.compute_wind_drag).  Defaults to 0
    so all existing callers continue to work unchanged.
    """
    p_prop    = params["num_motors"] * params["cruise_power"]
    p_avion   = params["power_fc"] + params["power_tel"]
    p_payload = params["power_payload"]
    p_other   = params["power_other"]
    p_total   = p_prop + p_wind + p_avion + p_payload + p_other
    p_net     = solar_power - p_total

    d_eff     = BATT_DISCHARGE_EFF.get(params["batt_chem"], 0.95)
    c_eff     = params["charge_eff"] / 100.0
    usable_wh = params["batt_wh"] * (1.0 - params["min_soc"] / 100.0) * d_eff

    # Ground speed (reduced by headwind)
    wind_ms      = float(params.get("wind_speed_ms", 0.0))
    ground_speed = max(0.0, params["airspeed"] - wind_ms * 3.6)

    endurance = None  # None = sustainable
    range_km  = None
    if p_net < 0:
        endurance = usable_wh / abs(p_net)
        range_km  = ground_speed * endurance

    # Charging time from surplus to fill usable capacity
    charge_time = None
    if p_net > 0:
        fill_wh     = params["batt_wh"] * (1.0 - params["min_soc"] / 100.0)
        charge_time = fill_wh / (p_net * c_eff)

    return {
        "p_prop":          round(p_prop, 1),
        "p_wind":          round(p_wind, 1),
        "p_avion":         round(p_avion, 1),
        "p_payload":       round(p_payload, 1),
        "p_other":         round(p_other, 1),
        "p_total":         round(p_total, 1),
        "p_net":           round(p_net, 2),
        "usable_wh":       round(usable_wh, 1),
        "endurance":       round(endurance, 2) if endurance is not None else None,
        "range_km":        round(range_km, 1) if range_km is not None else None,
        "ground_speed_kmh": round(ground_speed, 1),
        "charge_time_hrs": round(charge_time, 2) if charge_time is not None else None,
    }


def compute_min_area(params: Dict[str, Any], poa: float,
                     p_wind: float = 0.0, poa2: float = 0.0) -> float:
    """Minimum panel-1 area needed to break even at current irradiance.

    poa  – plane-of-array irradiance for panel 1 (at params["tilt"]).
    poa2 – plane-of-array irradiance for panel 2 (at params["panel_2_tilt"]).
           Must be supplied separately; using panel-1 POA for panel 2 is wrong
           when the two tilts differ.
    p_wind – extra propulsive drag power from headwind (W).
    """
    if poa <= 0:
        return float("inf")
    p2_area = float(params.get("panel_2_area", 0.0))
    p_total = (params["num_motors"] * params["cruise_power"] + p_wind
               + params["power_fc"] + params["power_tel"]
               + params["power_payload"] + params["power_other"])
    eff_act = params["efficiency"] * (1 + (params["temp_coeff"] / 100) * (params["panel_temp"] - 25))
    if eff_act <= 0:
        return float("inf")
    # Subtract panel-2 contribution using panel-2 POA (not panel-1 POA)
    p_need = p_total
    if p2_area > 0.0 and poa2 > 0.0:
        p2_contrib = p2_area * (eff_act / 100.0) * poa2 * (params["mppt"] / 100.0)
        p_need = max(0.0, p_total - p2_contrib)
    if p_need <= 0.0:
        return 0.0
    return p_need / ((eff_act / 100.0) * poa * (params["mppt"] / 100.0))


def get_verdict(p_net: float, p_total: float, endurance) -> Dict[str, str]:
    if p_net > 0:
        margin = p_net / p_total if p_total > 0 else 1.0
        if margin >= 0.15:
            return {
                "verdict":       "sustainable",
                "verdict_label": "SUSTAINABLE",
                "verdict_icon":  "✅",
                "verdict_detail": f"+{p_net:.1f} W surplus · {margin*100:.0f}% margin",
            }
        return {
            "verdict":       "marginal",
            "verdict_label": "MARGINAL",
            "verdict_icon":  "⚠️",
            "verdict_detail": f"Thin +{p_net:.1f} W margin · {margin*100:.1f}% — cloud risk",
        }
    if endurance is not None and endurance >= 4.0:
        return {
            "verdict":       "battery_assisted",
            "verdict_label": "BATTERY ASSISTED",
            "verdict_icon":  "🔋",
            "verdict_detail": f"{endurance:.1f} hrs on battery",
        }
    e = endurance if endurance is not None else 0.0
    land_min = e * 60
    land_str = "immediately" if land_min < 1 else f"in {land_min:.0f} min"
    return {
        "verdict":       "insufficient",
        "verdict_label": "INSUFFICIENT",
        "verdict_icon":  "🚫",
        "verdict_detail": f"{e:.1f} hrs endurance · land {land_str}",
    }
