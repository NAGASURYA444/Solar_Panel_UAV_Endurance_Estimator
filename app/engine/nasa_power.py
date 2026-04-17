"""
NASA POWER API client — fetches real monthly average GHI, temperature, and clearness index.

Endpoint: https://power.larc.nasa.gov/api/temporal/monthly/point
Parameters:
    ALLSKY_SFC_SW_DWN  – all-sky surface GHI, kWh/m²/day
    T2M                – 2m air temperature, °C
    ALLSKY_KT          – clearness index (0–1, ratio of surface to top-of-atmosphere irradiance)

Actual response format: flat dict with YYYYMM keys, float values.
  e.g. {"202001": 5.42, "202002": 6.29, ..., "202013": 6.06}  ← month 13 = annual avg
Monthly values are averaged across all requested years.

In-process cache keyed on (rounded lat, rounded lon) → dict with all fetched data.
"""
import httpx
from typing import Dict, Optional, Tuple

NASA_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
TIMEOUT  = 15.0   # seconds — NASA can be slow

# In-process cache: (lat_r, lon_r) → dict with monthly data
_cache: Dict[Tuple[float, float], dict] = {}

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

# KT → clarity mapping thresholds
_KT_CLEAR    = 0.65
_KT_STANDARD = 0.45


def _round_coords(lat: float, lon: float) -> Tuple[float, float]:
    """Round to 0.5° so nearby points share a cache entry."""
    return round(lat * 2) / 2, round(lon * 2) / 2


def _kt_to_clarity(kt: float) -> str:
    """Convert clearness index to clarity label."""
    if kt >= _KT_CLEAR:
        return "clear"
    if kt >= _KT_STANDARD:
        return "standard"
    return "hazy"


def _aggregate_monthly(raw: Dict[str, float]) -> Optional[list]:
    """Aggregate a YYYYMM-keyed dict into 12 monthly averages."""
    month_sum   = [0.0] * 12
    month_count = [0]   * 12

    for key_str, val in raw.items():
        if len(key_str) != 6:
            continue
        mm = int(key_str[4:6])
        if mm < 1 or mm > 12:
            continue
        if val is None or float(val) < -900:   # NASA uses -999 for missing
            continue
        idx = mm - 1
        month_sum[idx]   += float(val)
        month_count[idx] += 1

    if any(c == 0 for c in month_count):
        return None
    return [round(month_sum[i] / month_count[i], 3) for i in range(12)]


async def fetch_monthly_ghi(lat: float, lon: float = 0.0) -> Optional[Dict]:
    """
    Return monthly average GHI, temperature, and clearness index from NASA POWER.

    On success returns:
        monthly_ghi          : list[12] – Jan…Dec averages in kWh/m²/day
        monthly_t2m          : list[12] – Jan…Dec 2m air temperature °C
        monthly_kt           : list[12] – Jan…Dec clearness index
        monthly_clarity      : list[12] – clarity label per month
        monthly_panel_temp   : list[12] – suggested panel temp = T2M + 20°C
        annual_avg           : float (GHI)
        annual_avg_t2m       : float
        annual_avg_kt        : float
        source               : "nasa_power" | "cache"
        lat, lon             : actual coordinates used
        month_labels         : list[12] str labels
    """
    key = _round_coords(lat, lon)
    if key in _cache:
        data = _cache[key]
        return _build_result(data, key, source="cache")

    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,T2M,ALLSKY_KT",
        "community":  "RE",
        "longitude":  key[1],
        "latitude":   key[0],
        "start":      2018,
        "end":        2023,
        "format":     "JSON",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, verify=True) as client:
            resp = await client.get(NASA_URL, params=params)
            resp.raise_for_status()
            raw = resp.json()

        param_data = raw["properties"]["parameter"]

        ghi_raw = param_data.get("ALLSKY_SFC_SW_DWN", {})
        t2m_raw = param_data.get("T2M", {})
        kt_raw  = param_data.get("ALLSKY_KT", {})

        monthly_ghi = _aggregate_monthly(ghi_raw)
        monthly_t2m = _aggregate_monthly(t2m_raw)
        monthly_kt  = _aggregate_monthly(kt_raw)

        # GHI is required; others fall back gracefully
        if monthly_ghi is None:
            return None

        data = {
            "ghi": monthly_ghi,
            "t2m": monthly_t2m,
            "kt":  monthly_kt,
        }
        _cache[key] = data
        return _build_result(data, key, source="nasa_power")

    except Exception:
        return None


def _build_result(data: dict, key: Tuple[float, float], source: str) -> Dict:
    monthly_ghi = data["ghi"]
    monthly_t2m = data.get("t2m")
    monthly_kt  = data.get("kt")

    # Derived fields
    monthly_clarity    = None
    monthly_panel_temp = None
    annual_avg_t2m     = None
    annual_avg_kt      = None

    if monthly_kt:
        monthly_clarity = [_kt_to_clarity(kt) for kt in monthly_kt]
        annual_avg_kt   = round(sum(monthly_kt) / 12, 3)

    if monthly_t2m:
        monthly_panel_temp = [round(t + 20.0, 1) for t in monthly_t2m]
        annual_avg_t2m     = round(sum(monthly_t2m) / 12, 1)

    return {
        "monthly_ghi":        monthly_ghi,
        "monthly_t2m":        monthly_t2m,
        "monthly_kt":         monthly_kt,
        "monthly_clarity":    monthly_clarity,
        "monthly_panel_temp": monthly_panel_temp,
        "annual_avg":         round(sum(monthly_ghi) / 12, 3),
        "annual_avg_t2m":     annual_avg_t2m,
        "annual_avg_kt":      annual_avg_kt,
        "source":             source,
        "lat":                key[0],
        "lon":                key[1],
        "month_labels":       MONTH_NAMES,
    }


def ghi_to_clarity_factor(nasa_ghi_kwh: float) -> float:
    """
    Convert NASA monthly average GHI (kWh/m²/day) to a sky clarity
    scale factor [0.3, 1.0] for comparison against the Ineichen model.

    Reference: sea-level equatorial clear-sky daily GHI ≈ 8.0 kWh/m²/day.
    """
    CLEAR_SKY_REF = 8.0
    return round(max(0.3, min(1.0, nasa_ghi_kwh / CLEAR_SKY_REF)), 3)
