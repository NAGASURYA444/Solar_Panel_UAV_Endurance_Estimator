"""
Multi-segment mission planner.

A mission is a sequence of flight segments, each with its own duration,
altitude, speed, and power draw. The engine computes per-segment and
cumulative energy budget, mapping each segment onto actual solar time
so irradiance is correct for that part of the day.
"""
from typing import Dict, Any, List

from .solar import get_poa, panel_power, _make_time_series, BATT_DISCHARGE_EFF, _combined_powers
from .wind_drag import compute_wind_drag


def compute_mission(base_params: Dict[str, Any],
                    segments: List[Dict[str, Any]],
                    start_time_hrs: float = 7.0) -> Dict[str, Any]:
    """
    Evaluate a multi-segment mission.

    Each segment dict must contain:
        name            : str
        duration_hrs    : float   — how long this phase lasts
        altitude_m      : float   — cruise altitude (overrides base_params)
        speed_kmh       : float   — airspeed (used for range)
        num_motors      : int
        cruise_power_w  : float   — per-motor cruise power
        power_payload_w : float   — payload power this leg
        power_other_w   : float   — other loads this leg

    base_params are inherited for solar array properties (area, efficiency,
    temp_coeff, panel_temp, mppt, tilt, lat, month, clarity, batt_*).
    """
    d_eff    = BATT_DISCHARGE_EFF.get(base_params["batt_chem"], 0.95)
    c_eff    = base_params["charge_eff"] / 100.0
    batt_wh  = float(base_params["batt_wh"])
    min_soc  = float(base_params["min_soc"])

    usable_wh = batt_wh * (1.0 - min_soc / 100.0) * d_eff

    seg_results: List[Dict[str, Any]] = []
    current_time = start_time_hrs
    soc          = 100.0           # start fully charged
    cumulative_range_km = 0.0

    for seg in segments:
        def _v(key, fallback):
            """Return seg[key] if present and not None, else fallback."""
            v = seg.get(key)
            return v if v is not None else fallback

        dur    = float(seg["duration_hrs"])
        alt    = float(_v("altitude_m",     base_params["altitude"]))
        speed  = float(_v("speed_kmh",      base_params["airspeed"]))
        nm     = int(_v("num_motors",       base_params["num_motors"]))
        cp     = float(_v("cruise_power_w", base_params["cruise_power"]))
        pp     = float(_v("power_payload_w",base_params["power_payload"]))
        po     = float(_v("power_other_w",  base_params["power_other"]))
        pfc    = float(base_params.get("power_fc",  5.0))
        ptel   = float(base_params.get("power_tel", 3.0))

        # Wind drag per segment (uses segment speed if provided, else base airspeed)
        seg_wind_params = {**base_params,
                           "num_motors": nm, "cruise_power": cp,
                           "airspeed": _v("speed_kmh", base_params["airspeed"])}
        seg_wind  = compute_wind_drag(seg_wind_params)
        p_consume = nm * cp + seg_wind["p_wind_w"] + pfc + ptel + pp + po

        # Build time series for this segment (30-min resolution)
        n_steps = max(1, int(dur / 0.5))
        seg_times = _make_time_series(
            base_params["month"], current_time, n_steps, 30
        )
        seg_params = {**base_params, "altitude": alt}
        pow_arr = _combined_powers({**base_params, "altitude": alt}, seg_times)

        # Each step represents dur/n_steps hours; scale sum accordingly
        solar_wh   = float(sum(pow_arr)) * (dur / n_steps)
        consume_wh = p_consume * dur
        net_wh     = solar_wh - consume_wh

        # Update SOC over segment
        if net_wh >= 0:
            soc += (net_wh * c_eff) / batt_wh * 100.0
        else:
            soc += net_wh / (batt_wh * d_eff) * 100.0
        soc = max(min_soc, min(100.0, soc))

        range_km = speed * dur
        cumulative_range_km += range_km

        seg_results.append({
            "name":         seg.get("name", f"Seg {len(seg_results)+1}"),
            "duration_hrs": round(dur, 2),
            "start_time":   round(current_time, 2),
            "end_time":     round(current_time + dur, 2),
            "p_consume_w":  round(p_consume, 1),
            "solar_wh":     round(solar_wh, 1),
            "consume_wh":   round(consume_wh, 1),
            "net_wh":       round(net_wh, 1),
            "soc_end":      round(soc, 1),
            "range_km":     round(range_km, 1),
            "verdict":      "surplus" if net_wh >= 0 else "deficit",
        })

        current_time += dur

    total_solar   = sum(s["solar_wh"]   for s in seg_results)
    total_consume = sum(s["consume_wh"] for s in seg_results)
    total_net     = total_solar - total_consume
    mission_ok    = soc > min_soc

    return {
        "segments":            seg_results,
        "total_solar_wh":      round(total_solar, 1),
        "total_consume_wh":    round(total_consume, 1),
        "total_net_wh":        round(total_net, 1),
        "final_soc":           round(soc, 1),
        "total_range_km":      round(cumulative_range_km, 1),
        "total_duration_hrs":  round(current_time - start_time_hrs, 2),
        "mission_feasible":    mission_ok,
        "usable_wh":           round(usable_wh, 1),
    }
