# =============================================================================
#  SURFCAST TUNISIA — PRODUCTION BACKEND
#  FastAPI | Python 3.11+
#  Deploy: Render.com (Free Tier)
#  APIs: Open-Meteo Marine + Weather (100% Free, No Key Required)
#
#  Architecture:
#   - /forecast?lat=&lon=&name= → Full 48h history + 3-day future analysis
#   - /best-spots               → Scans all spots, finds best windows
#   - /spots                    → Returns predefined spot list
# =============================================================================

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
import math

# ─────────────────────────────────────────────────────────────────────────────
# APP INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SurfCast Tunisia API",
    description="Advanced Surfcasting Forecast Engine for Tunisian Coasts",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# PREDEFINED SPOTS — Tunisia's Best Surfcasting Locations
# beach_angle: The compass bearing (degrees) that the beach FACES (toward the sea).
# A wind/swell coming FROM the same direction as beach_angle is ONSHORE.
# ─────────────────────────────────────────────────────────────────────────────
PREDEFINED_SPOTS = [
    {
        "id": "tunis_carthage",
        "name": "قرطاج - تونس",
        "name_en": "Carthage Beach - Tunis",
        "lat": 36.858,
        "lon": 10.328,
        "beach_angle": 60,   # Beach faces NE (toward Gulf of Tunis)
        "region": "تونس الكبرى"
    },
    {
        "id": "nabeul_kelibia",
        "name": "قليبية - نابل",
        "name_en": "Kelibia - Nabeul",
        "lat": 36.847,
        "lon": 11.106,
        "beach_angle": 90,   # Beach faces E (toward open Mediterranean)
        "region": "نابل"
    },
    {
        "id": "nabeul_hammamet",
        "name": "الحمامات - نابل",
        "name_en": "Hammamet - Nabeul",
        "lat": 36.398,
        "lon": 10.617,
        "beach_angle": 45,   # Beach faces NE
        "region": "نابل"
    },
    {
        "id": "bizerte_cap_blanc",
        "name": "كاب بيان - بنزرت",
        "name_en": "Cap Blanc - Bizerte",
        "lat": 37.290,
        "lon": 9.869,
        "beach_angle": 330,  # Beach faces NNW (toward open Mediterranean)
        "region": "بنزرت"
    },
    {
        "id": "bizerte_sidi_ali_mekki",
        "name": "سيدي علي المكي - بنزرت",
        "name_en": "Sidi Ali Mekki - Bizerte",
        "lat": 37.194,
        "lon": 10.004,
        "beach_angle": 10,   # Beach faces N
        "region": "بنزرت"
    },
    {
        "id": "sousse_port_kantaoui",
        "name": "بورت الكنتاوي - سوسة",
        "name_en": "Port El Kantaoui - Sousse",
        "lat": 35.898,
        "lon": 10.598,
        "beach_angle": 80,   # Beach faces ENE
        "region": "سوسة"
    },
    {
        "id": "sousse_chott_meriem",
        "name": "شط مريم - سوسة",
        "name_en": "Chott Meriem - Sousse",
        "lat": 35.969,
        "lon": 10.617,
        "beach_angle": 75,   # Beach faces ENE
        "region": "سوسة"
    },
    {
        "id": "monastir_ksibet",
        "name": "كصيبة المديوني - المنستير",
        "name_en": "Ksibet - Monastir",
        "lat": 35.723,
        "lon": 10.812,
        "beach_angle": 85,   # Beach faces E
        "region": "المنستير"
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# PHYSICS ENGINE — Core Analysis Functions
# ─────────────────────────────────────────────────────────────────────────────

def angular_difference(angle1: float, angle2: float) -> float:
    """Calculate the smallest angular difference between two compass bearings."""
    diff = abs(angle1 - angle2) % 360
    return diff if diff <= 180 else 360 - diff


def classify_wind_direction(wind_dir: float, beach_angle: float) -> dict:
    """
    Classify wind relative to beach orientation.
    Wind direction in meteorology = direction FROM which wind blows.
    Onshore = wind blowing FROM the sea toward the beach.
    beach_angle = direction beach faces (toward sea).
    Wind is onshore when it comes from the same direction the beach faces.
    """
    diff = angular_difference(wind_dir, beach_angle)
    if diff <= 45:
        return {"type": "onshore", "label": "بحري (Onshore)", "emoji": "🌊"}
    elif diff <= 90:
        return {"type": "side_onshore", "label": "جانبي بحري (Side-Onshore)", "emoji": "↗️"}
    elif diff <= 135:
        return {"type": "side_offshore", "label": "جانبي بري (Side-Offshore)", "emoji": "↙️"}
    else:
        return {"type": "offshore", "label": "بري (Offshore)", "emoji": "🏔️"}


def classify_swell_direction(swell_dir: float, beach_angle: float) -> dict:
    """Classify swell approach relative to beach."""
    diff = angular_difference(swell_dir, beach_angle)
    if diff <= 30:
        return {"type": "direct", "label": "مباشر", "perpendicular": True}
    elif diff <= 60:
        return {"type": "angled", "label": "مائل", "perpendicular": False}
    else:
        return {"type": "oblique", "label": "منحرف", "perpendicular": False}


def estimate_tide_phase(hour: int) -> dict:
    """
    Estimate tidal phase using a simplified 12.4-hour sinusoidal cycle.
    Tunisia (Mediterranean) has a microtidal range of ~0.2-0.4m.
    Low tide hours (approximate) around 06:00 and 18:00 local time.
    """
    # Simplified semidiurnal model
    cycle_hours = 12.4
    phase_offset = 6  # Low tide at ~06:00 and ~18:20
    angle = ((hour - phase_offset) / cycle_hours) * 2 * math.pi
    tide_level = math.sin(angle)  # -1 = low, +1 = high
    if tide_level < -0.5:
        return {"phase": "low", "label": "جزر (Low Tide)", "level": tide_level}
    elif tide_level > 0.5:
        return {"phase": "high", "label": "مد (High Tide)", "level": tide_level}
    else:
        return {"phase": "mid", "label": "متوسط (Mid Tide)", "level": tide_level}


def calculate_seaweed_risk(
    swell_height: float,
    wind_classification: dict,
    historical_breach: bool,
    hours_since_breach: int
) -> dict:
    """
    Seaweed/Debris Risk Engine using 48h persistent logic.
    - If historical_breach=True (swell > 1.8m AND onshore wind in last 48h),
      risk stays elevated for at least 12 hours even after conditions improve.
    - Risk also calculates current-hour direct risk.
    """
    direct_risk = "low"
    risk_score = 0

    # Current hour direct risk
    if wind_classification["type"] == "onshore":
        if swell_height > 1.8:
            direct_risk = "critical"
            risk_score = 4
        elif swell_height > 1.2:
            direct_risk = "high"
            risk_score = 3
        elif swell_height > 0.6:
            direct_risk = "moderate"
            risk_score = 2
        else:
            direct_risk = "low"
            risk_score = 1
    elif wind_classification["type"] == "side_onshore":
        if swell_height > 2.0:
            direct_risk = "high"
            risk_score = 3
        elif swell_height > 1.0:
            direct_risk = "moderate"
            risk_score = 2
        else:
            direct_risk = "low"
            risk_score = 1
    else:
        if swell_height > 2.5:
            direct_risk = "moderate"
            risk_score = 2
        else:
            direct_risk = "low"
            risk_score = 1

    # Apply persistent 48h historical contamination
    if historical_breach and hours_since_breach < 12:
        persistent_score = max(3, risk_score)
        labels = {1: "low", 2: "moderate", 3: "high", 4: "critical"}
        final_risk = labels.get(persistent_score, "high")
        persistence_active = True
    else:
        final_risk = direct_risk
        persistence_active = False

    risk_display = {
        "low": {"label": "منخفض", "color": "#22c55e", "emoji": "✅", "score": 1},
        "moderate": {"label": "متوسط", "color": "#f59e0b", "emoji": "⚠️", "score": 2},
        "high": {"label": "مرتفع", "color": "#ef4444", "emoji": "🚫", "score": 3},
        "critical": {"label": "حرج", "color": "#7c3aed", "emoji": "☠️", "score": 4},
    }

    return {
        "level": final_risk,
        "persistence_active": persistence_active,
        **risk_display.get(final_risk, risk_display["low"])
    }


def calculate_rip_current_risk(
    swell_period: float,
    swell_height: float,
    swell_classification: dict,
    tide_phase: dict
) -> dict:
    """
    Rip Current Risk Engine.
    High risk when: swell period >= 12s AND swell is perpendicular to beach
    AND during low tide (when water channels are most pronounced).
    """
    risk_score = 0

    # Period factor
    if swell_period >= 14:
        risk_score += 3
    elif swell_period >= 12:
        risk_score += 2
    elif swell_period >= 10:
        risk_score += 1

    # Height factor
    if swell_height > 2.0:
        risk_score += 2
    elif swell_height > 1.2:
        risk_score += 1

    # Direction factor (perpendicular = most dangerous)
    if swell_classification["perpendicular"]:
        risk_score += 2

    # Tide multiplier
    if tide_phase["phase"] == "low":
        risk_score = int(risk_score * 1.5)

    if risk_score >= 6:
        return {"level": "critical", "label": "تيار خطير جداً", "color": "#7c3aed", "emoji": "🌀", "score": 4}
    elif risk_score >= 4:
        return {"level": "high", "label": "خطر تيار مرتفع", "color": "#ef4444", "emoji": "⚠️", "score": 3}
    elif risk_score >= 2:
        return {"level": "moderate", "label": "تيار معتدل", "color": "#f59e0b", "emoji": "〰️", "score": 2}
    else:
        return {"level": "low", "label": "منخفض", "color": "#22c55e", "emoji": "✅", "score": 1}


def calculate_wind_casting_danger(wind_speed: float, wind_gust: float) -> dict:
    """
    Wind and Casting Danger Assessment.
    Wind speed in km/h for surfcasting context.
    """
    # Convert m/s to km/h
    speed_kmh = wind_speed * 3.6
    gust_kmh = wind_gust * 3.6

    if gust_kmh > 60 or speed_kmh > 45:
        return {
            "level": "impossible",
            "label": "مستحيل الصيد",
            "detail": f"ريح {speed_kmh:.0f} كم/س | هبّة {gust_kmh:.0f} كم/س",
            "color": "#7c3aed",
            "emoji": "🌪️",
            "score": 4
        }
    elif gust_kmh > 40 or speed_kmh > 28:
        return {
            "level": "dangerous",
            "label": "صعب جداً",
            "detail": f"ريح {speed_kmh:.0f} كم/س | هبّة {gust_kmh:.0f} كم/س",
            "color": "#ef4444",
            "emoji": "💨",
            "score": 3
        }
    elif gust_kmh > 25 or speed_kmh > 18:
        return {
            "level": "difficult",
            "label": "متعذّر",
            "detail": f"ريح {speed_kmh:.0f} كم/س | هبّة {gust_kmh:.0f} كم/س",
            "color": "#f59e0b",
            "emoji": "🌬️",
            "score": 2
        }
    else:
        return {
            "level": "good",
            "label": "ملائم للرمي",
            "detail": f"ريح {speed_kmh:.0f} كم/س | هبّة {gust_kmh:.0f} كم/س",
            "color": "#22c55e",
            "emoji": "🎣",
            "score": 1
        }


def recommend_sinker(
    swell_height: float,
    swell_period: float,
    rip_risk: dict,
    wind_danger: dict
) -> dict:
    """
    Dynamic Sinker Weight Advisor.
    Recommends specific sinker types based on sea conditions.
    """
    # Rip current scenario — needs anchoring sinker
    if rip_risk["score"] >= 3:
        return {
            "type": "Grapple / Spider",
            "type_ar": "مرساة / عنكبوت",
            "weight": "130-180g",
            "reason": "تيار رجعي قوي — المرساة ضرورية لتثبيت الطعم",
            "emoji": "⚓",
            "color": "#ef4444"
        }
    # Heavy swell scenario
    elif swell_height > 1.5 or swell_period > 10:
        return {
            "type": "Pyramid",
            "type_ar": "هرمي",
            "weight": "110-130g",
            "reason": f"موج {swell_height:.1f}م / دورة {swell_period:.0f}ث — الهرمي يثبت في القاع",
            "emoji": "🔺",
            "color": "#f59e0b"
        }
    # Moderate swell
    elif swell_height > 0.8:
        return {
            "type": "Breakaway / Grip",
            "type_ar": "مخلب / قابض",
            "weight": "90-110g",
            "reason": f"موج معتدل {swell_height:.1f}م — القابض يمنع الانزياح",
            "emoji": "🪝",
            "color": "#3b82f6"
        }
    # Calm / flat sea
    else:
        return {
            "type": "Roll / Sphere / Bomb",
            "type_ar": "كروي / قنبلة",
            "weight": "60-90g",
            "reason": "بحر هادئ — الوزن الخفيف يتيح رمياً أبعد",
            "emoji": "⚫",
            "color": "#22c55e"
        }


def calculate_pressure_trend(pressures: list, current_idx: int) -> dict:
    """
    Calculate barometric pressure trend over 3 hours.
    Falling pressure = fish are more active.
    """
    if current_idx < 3 or not pressures:
        return {"trend": "stable", "label": "مستقر", "delta": 0}

    valid = [p for p in pressures[max(0, current_idx-3):current_idx+1] if p is not None]
    if len(valid) < 2:
        return {"trend": "stable", "label": "مستقر", "delta": 0}

    delta = valid[-1] - valid[0]

    if delta < -2:
        return {"trend": "falling_fast", "label": "هابط بسرعة 📉", "delta": round(delta, 1), "fishing_bonus": True}
    elif delta < -0.5:
        return {"trend": "falling", "label": "هابط تدريجياً 📉", "delta": round(delta, 1), "fishing_bonus": True}
    elif delta > 2:
        return {"trend": "rising_fast", "label": "صاعد بسرعة 📈", "delta": round(delta, 1), "fishing_bonus": False}
    elif delta > 0.5:
        return {"trend": "rising", "label": "صاعد 📈", "delta": round(delta, 1), "fishing_bonus": False}
    else:
        return {"trend": "stable", "label": "مستقر", "delta": round(delta, 1), "fishing_bonus": False}


def calculate_ultimate_verdict(
    swell_height: float,
    swell_period: float,
    seaweed_risk: dict,
    rip_risk: dict,
    wind_danger: dict,
    pressure_trend: dict,
    wind_classification: dict
) -> dict:
    """
    The Master Verdict Matrix — الحكم النهائي.
    Combines all risk factors into a single actionable verdict.
    """
    risk_total = seaweed_risk["score"] + rip_risk["score"] + wind_danger["score"]

    # IMPOSSIBLE conditions
    if wind_danger["level"] == "impossible" or rip_risk["level"] == "critical":
        return {
            "verdict": "مستحيل",
            "verdict_en": "IMPOSSIBLE",
            "color": "#7c3aed",
            "bg_color": "rgba(124,58,237,0.15)",
            "emoji": "⛔",
            "score": 4,
            "stars": 0
        }

    # EXCELLENT conditions — the golden window
    excellent = (
        0.5 <= swell_height <= 1.2
        and seaweed_risk["score"] <= 1
        and rip_risk["score"] <= 1
        and wind_danger["score"] <= 1
        and (pressure_trend.get("fishing_bonus", False) or pressure_trend["trend"] == "stable")
        and wind_classification["type"] in ("offshore", "side_offshore")
    )
    if excellent:
        return {
            "verdict": "ممتاز 🏆",
            "verdict_en": "EXCELLENT",
            "color": "#22c55e",
            "bg_color": "rgba(34,197,94,0.15)",
            "emoji": "🏆",
            "score": 1,
            "stars": 5
        }

    # GOOD conditions
    good = (
        0.3 <= swell_height <= 1.5
        and seaweed_risk["score"] <= 2
        and rip_risk["score"] <= 2
        and wind_danger["score"] <= 2
    )
    if good:
        return {
            "verdict": "ممكن ✅",
            "verdict_en": "POSSIBLE",
            "color": "#3b82f6",
            "bg_color": "rgba(59,130,246,0.15)",
            "emoji": "✅",
            "score": 2,
            "stars": 3
        }

    # VERY DIFFICULT
    if risk_total <= 9:
        return {
            "verdict": "صعب جداً ⚠️",
            "verdict_en": "VERY DIFFICULT",
            "color": "#f59e0b",
            "bg_color": "rgba(245,158,11,0.15)",
            "emoji": "⚠️",
            "score": 3,
            "stars": 1
        }

    return {
        "verdict": "مستحيل ⛔",
        "verdict_en": "IMPOSSIBLE",
        "color": "#ef4444",
        "bg_color": "rgba(239,68,68,0.15)",
        "emoji": "⛔",
        "score": 4,
        "stars": 0
    }


def generate_arabic_explanation(
    hour_data: dict,
    spot_name: str,
    historical_breach: bool
) -> str:
    """
    Generate a detailed Arabic paragraph explaining the AI's verdict.
    """
    verdict = hour_data["verdict"]["verdict_en"]
    swell_h = hour_data["swell_height"]
    swell_p = hour_data["swell_period"]
    wind_c = hour_data["wind_classification"]
    seaweed = hour_data["seaweed_risk"]
    rip = hour_data["rip_current_risk"]
    wind_d = hour_data["wind_danger"]
    tide = hour_data["tide_phase"]
    pressure = hour_data["pressure_trend"]

    parts = [f"📍 {spot_name} |"]

    # Swell assessment
    if swell_h < 0.3:
        parts.append(f"البحر هادئ جداً (ارتفاع الأمواج {swell_h:.1f}م)")
    elif swell_h <= 1.2:
        parts.append(f"الأمواج مثالية بارتفاع {swell_h:.1f}م ودورة {swell_p:.0f} ثانية")
    elif swell_h <= 2.0:
        parts.append(f"الأمواج متوسطة إلى مرتفعة ({swell_h:.1f}م / {swell_p:.0f}ث)")
    else:
        parts.append(f"تحذير: أمواج عالية جداً تبلغ {swell_h:.1f}م")

    # Wind assessment
    parts.append(f"الريح {wind_c['label']} — {wind_d['detail']}")

    # Historical contamination
    if historical_breach:
        if seaweed["persistence_active"]:
            parts.append("⚠️ تحذير: سُجّل موج فوق 1.8م مع ريح بحرية خلال الـ48 ساعة الماضية، ومن المرجح وجود عشب بحري وحطام في المنطقة")
        else:
            parts.append("البحر بدأ يهدأ تدريجياً بعد اضطراب سابق")

    # Rip current assessment
    if rip["score"] >= 3:
        parts.append(f"🌀 خطر تيارات رجعية شديدة: دورة الأمواج {swell_p:.0f}ث عمودية على الشاطئ مع {tide['label']}")
    elif rip["score"] == 2:
        parts.append(f"احتمال تيارات متوسطة — توخَّ الحذر")

    # Pressure trend
    if pressure.get("fishing_bonus"):
        parts.append(f"📉 الضغط الجوي هابط ({pressure['delta']} هكتوباسكال) — شرط ممتاز لنشاط الأسماك")
    elif pressure["trend"] == "rising_fast":
        parts.append(f"📈 الضغط الجوي صاعد — الأسماك أقل نشاطاً")

    # Final verdict explanation
    if verdict == "EXCELLENT":
        parts.append("✅ الحكم النهائي: ظروف مثالية نادرة — استغل هذه الفرصة الذهبية!")
    elif verdict == "POSSIBLE":
        parts.append("✅ الحكم: ظروف مقبولة — الصيد ممكن مع الأخذ بعين الاعتبار للمخاطر المذكورة")
    elif verdict == "VERY DIFFICULT":
        parts.append("⚠️ الحكم: ظروف صعبة — لا يُنصح إلا لذوي الخبرة العالية")
    else:
        parts.append("⛔ الحكم: ظروف خطيرة — لا يُنصح بالصيد مطلقاً في هذه الأحوال")

    return " | ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# API DATA FETCHING — Concurrent calls to Open-Meteo
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_marine_data(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """
    Fetch from Open-Meteo Marine API.
    past_days=2 gives us the 48h historical window seamlessly.
    forecast_days=4 gives us today + 3 full future days.
    """
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "wave_height",
            "wave_direction",
            "wave_period",
            "swell_wave_height",
            "swell_wave_direction",
            "swell_wave_period",
            "swell_wave_peak_period",
            "wind_wave_height",
            "wind_wave_direction",
            "wind_wave_period",
        ]),
        "past_days": 2,
        "forecast_days": 4,
        "timezone": "Africa/Tunis"
    }
    resp = await client.get(url, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


async def fetch_weather_data(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """
    Fetch from Open-Meteo Weather API.
    Includes surface pressure for barometric trend analysis.
    past_days=2 for historical wind data needed for seaweed persistence.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "surface_pressure",
            "temperature_2m",
            "precipitation_probability",
            "cloud_cover",
            "visibility",
        ]),
        "past_days": 2,
        "forecast_days": 4,
        "timezone": "Africa/Tunis",
        "wind_speed_unit": "ms"
    }
    resp = await client.get(url, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# CORE ANALYSIS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def analyze_spot_data(marine: dict, weather: dict, spot: dict) -> dict:
    """
    Main analysis function — processes raw API data and returns
    a structured hourly forecast with all risk assessments.
    """
    beach_angle = spot["beach_angle"]
    times = marine["hourly"]["time"]
    n = len(times)

    # Extract all arrays (with safe fallback)
    def safe_get(data, key, default=None):
        arr = data["hourly"].get(key, [])
        return [v if v is not None else default for v in arr]

    # Marine arrays
    wave_heights = safe_get(marine, "wave_height", 0.0)
    swell_heights = safe_get(marine, "swell_wave_height", 0.0)
    swell_dirs = safe_get(marine, "swell_wave_direction", 0.0)
    swell_periods = safe_get(marine, "swell_wave_period", 6.0)
    swell_peak_periods = safe_get(marine, "swell_wave_peak_period", 6.0)
    wind_wave_heights = safe_get(marine, "wind_wave_height", 0.0)

    # Weather arrays
    wind_speeds = safe_get(weather, "wind_speed_10m", 0.0)
    wind_dirs = safe_get(weather, "wind_direction_10m", 0.0)
    wind_gusts = safe_get(weather, "wind_gusts_10m", 0.0)
    pressures = safe_get(weather, "surface_pressure", 1013.0)
    temperatures = safe_get(weather, "temperature_2m", 20.0)
    precip_probs = safe_get(weather, "precipitation_probability", 0)
    cloud_covers = safe_get(weather, "cloud_cover", 0)

    # ── STEP 1: Analyze 48h history for persistent debris risk ────────────────
    now_utc = datetime.now(timezone.utc)
    # Tunisia is UTC+1
    now_local_hour_str = (now_utc + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00")

    # Find current index
    current_idx = 0
    for i, t in enumerate(times):
        if t >= now_local_hour_str:
            current_idx = i
            break

    historical_breach = False
    breach_hour_idx = -1

    # Scan past 48 hours (current_idx - 48 to current_idx)
    hist_start = max(0, current_idx - 48)
    for i in range(hist_start, current_idx):
        if i < len(swell_heights) and i < len(wind_dirs):
            h_swell = swell_heights[i]
            h_wind_dir = wind_dirs[i]
            h_wind_class = classify_wind_direction(h_wind_dir, beach_angle)
            if h_swell > 1.8 and h_wind_class["type"] == "onshore":
                historical_breach = True
                breach_hour_idx = i

    hours_since_breach = (current_idx - breach_hour_idx) if breach_hour_idx >= 0 else 999

    # ── STEP 2: Build hourly analysis for the next 3 days (72 hours) ──────────
    # Only process from current_idx onwards, for 72 hours
    forecast_hours = []
    future_start = current_idx
    future_end = min(n, current_idx + 73)

    for i in range(future_start, future_end):
        if i >= n:
            break

        t_str = times[i]
        try:
            t_dt = datetime.fromisoformat(t_str)
        except Exception:
            continue

        hour = t_dt.hour

        # Safe value extraction
        s_height = swell_heights[i] if i < len(swell_heights) else 0.0
        s_dir = swell_dirs[i] if i < len(swell_dirs) else 0.0
        s_period = swell_periods[i] if i < len(swell_periods) else 6.0
        s_peak_period = swell_peak_periods[i] if i < len(swell_peak_periods) else 6.0
        w_height = wave_heights[i] if i < len(wave_heights) else s_height
        ww_height = wind_wave_heights[i] if i < len(wind_wave_heights) else 0.0
        w_speed = wind_speeds[i] if i < len(wind_speeds) else 0.0
        w_dir = wind_dirs[i] if i < len(wind_dirs) else 0.0
        w_gust = wind_gusts[i] if i < len(wind_gusts) else w_speed * 1.3
        pressure = pressures[i] if i < len(pressures) else 1013.0
        temp = temperatures[i] if i < len(temperatures) else 20.0
        precip_p = precip_probs[i] if i < len(precip_probs) else 0
        cloud = cloud_covers[i] if i < len(cloud_covers) else 0

        # Hours since breach for this forecast hour
        hrs_since = (i - breach_hour_idx) if breach_hour_idx >= 0 else 999

        # Run all analysis modules
        wind_class = classify_wind_direction(w_dir, beach_angle)
        swell_class = classify_swell_direction(s_dir, beach_angle)
        tide_phase = estimate_tide_phase(hour)
        seaweed_risk = calculate_seaweed_risk(s_height, wind_class, historical_breach, hrs_since)
        rip_risk = calculate_rip_current_risk(s_period, s_height, swell_class, tide_phase)
        wind_danger = calculate_wind_casting_danger(w_speed, w_gust)
        pressure_trend = calculate_pressure_trend(pressures, i)
        sinker = recommend_sinker(s_height, s_period, rip_risk, wind_danger)
        verdict = calculate_ultimate_verdict(
            s_height, s_period, seaweed_risk, rip_risk,
            wind_danger, pressure_trend, wind_class
        )

        # Day number (0=today, 1=tomorrow, 2=day after)
        days_offset = (t_dt.date() - (now_utc + timedelta(hours=1)).date()).days

        hour_record = {
            "time": t_str,
            "hour": hour,
            "day_offset": days_offset,
            "day_label": ["اليوم", "غداً", "بعد غد", "اليوم الثالث"].get(days_offset, f"يوم +{days_offset}"),
            "swell_height": round(s_height, 2),
            "swell_period": round(s_period, 1),
            "swell_peak_period": round(s_peak_period, 1),
            "swell_direction": round(s_dir, 0),
            "wave_height": round(w_height, 2),
            "wind_wave_height": round(ww_height, 2),
            "wind_speed_ms": round(w_speed, 1),
            "wind_speed_kmh": round(w_speed * 3.6, 1),
            "wind_direction": round(w_dir, 0),
            "wind_gust_ms": round(w_gust, 1),
            "wind_gust_kmh": round(w_gust * 3.6, 1),
            "pressure_hpa": round(pressure, 1),
            "temperature_c": round(temp, 1),
            "precipitation_probability": precip_p,
            "cloud_cover": cloud,
            "wind_classification": wind_class,
            "swell_classification": swell_class,
            "tide_phase": tide_phase,
            "seaweed_risk": seaweed_risk,
            "rip_current_risk": rip_risk,
            "wind_danger": wind_danger,
            "pressure_trend": pressure_trend,
            "sinker_recommendation": sinker,
            "verdict": verdict,
        }

        # Generate Arabic explanation
        hour_record["arabic_explanation"] = generate_arabic_explanation(
            hour_record, spot.get("name", "الموقع"), historical_breach
        )

        forecast_hours.append(hour_record)

    # ── STEP 3: Group by day ──────────────────────────────────────────────────
    days = {}
    for h in forecast_hours:
        d = h["day_offset"]
        if d not in days:
            days[d] = []
        days[d].append(h)

    # ── STEP 4: Per-day summary ───────────────────────────────────────────────
    day_summaries = []
    for d_offset in sorted(days.keys()):
        day_hours = days[d_offset]
        if not day_hours:
            continue

        verdicts = [h["verdict"]["score"] for h in day_hours]
        best_verdict_score = min(verdicts)
        best_hour = min(day_hours, key=lambda h: h["verdict"]["score"])

        # Count excellent windows
        excellent_windows = [h for h in day_hours if h["verdict"]["verdict_en"] == "EXCELLENT"]
        good_windows = [h for h in day_hours if h["verdict"]["verdict_en"] in ("EXCELLENT", "POSSIBLE")]

        # Best 3-hour fishing window
        best_window = None
        if len(day_hours) >= 3:
            best_window_score = float('inf')
            for j in range(len(day_hours) - 2):
                window = day_hours[j:j+3]
                avg_score = sum(h["verdict"]["score"] for h in window) / 3
                if avg_score < best_window_score:
                    best_window_score = avg_score
                    start_t = window[0]["time"]
                    end_t = window[-1]["time"]
                    best_window = {
                        "start": start_t,
                        "end": end_t,
                        "avg_score": round(best_window_score, 2),
                        "label": f'{window[0]["hour"]:02d}:00 → {window[-1]["hour"]:02d}:00',
                        "verdict_score": best_window_score
                    }

        day_summaries.append({
            "day_offset": d_offset,
            "day_label": day_hours[0]["day_label"],
            "date": day_hours[0]["time"][:10],
            "best_hour": best_hour,
            "best_window": best_window,
            "avg_verdict_score": round(sum(verdicts) / len(verdicts), 2),
            "best_verdict_score": best_verdict_score,
            "excellent_count": len(excellent_windows),
            "good_count": len(good_windows),
            "hours": day_hours
        })

    # ── STEP 5: Current conditions snapshot ──────────────────────────────────
    current_hour_data = forecast_hours[0] if forecast_hours else None

    return {
        "spot": spot,
        "historical_breach": historical_breach,
        "hours_since_breach": hours_since_breach if breach_hour_idx >= 0 else None,
        "current": current_hour_data,
        "days": day_summaries,
        "all_hours": forecast_hours
    }


# ─────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/spots")
async def get_spots():
    """Return all predefined spots."""
    return {"spots": PREDEFINED_SPOTS}


@app.get("/forecast")
async def get_forecast(
    lat: float = Query(..., description="Latitude", ge=-90, le=90),
    lon: float = Query(..., description="Longitude", ge=-180, le=180),
    name: Optional[str] = Query(None, description="Spot name"),
    beach_angle: Optional[float] = Query(None, description="Beach facing angle (degrees)")
):
    """
    Full 3-day forecast analysis for a single coordinate.
    Includes 48h historical breach detection + 72h future forecast.
    """
    # Try to match against predefined spots first
    matched_spot = None
    for s in PREDEFINED_SPOTS:
        if abs(s["lat"] - lat) < 0.05 and abs(s["lon"] - lon) < 0.05:
            matched_spot = s
            break

    if matched_spot is None:
        # Custom spot
        matched_spot = {
            "id": f"custom_{lat}_{lon}",
            "name": name or f"موقع مخصص ({lat:.3f}, {lon:.3f})",
            "name_en": name or f"Custom Spot ({lat:.3f}, {lon:.3f})",
            "lat": lat,
            "lon": lon,
            "beach_angle": beach_angle if beach_angle is not None else 90,
            "region": "مخصص"
        }

    async with httpx.AsyncClient() as client:
        try:
            marine_data, weather_data = await asyncio.gather(
                fetch_marine_data(client, lat, lon),
                fetch_weather_data(client, lat, lon)
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Open-Meteo API error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Network error contacting Open-Meteo: {str(e)}")

    result = analyze_spot_data(marine_data, weather_data, matched_spot)
    return result


@app.get("/best-spots")
async def get_best_spots(
    custom_spots: Optional[str] = Query(None, description="JSON string of custom spots array")
):
    """
    Scan ALL spots (predefined + custom), evaluate 3-day forecast,
    and return the ultimate best spot + golden windows table.
    """
    import json

    all_spots = list(PREDEFINED_SPOTS)

    # Parse any custom spots passed from frontend
    if custom_spots:
        try:
            parsed_custom = json.loads(custom_spots)
            if isinstance(parsed_custom, list):
                for cs in parsed_custom:
                    if all(k in cs for k in ("lat", "lon")):
                        all_spots.append({
                            "id": f"custom_{cs['lat']}_{cs['lon']}",
                            "name": cs.get("name", f"مخصص ({cs['lat']:.3f}, {cs['lon']:.3f})"),
                            "name_en": cs.get("name_en", "Custom"),
                            "lat": float(cs["lat"]),
                            "lon": float(cs["lon"]),
                            "beach_angle": float(cs.get("beach_angle", 90)),
                            "region": cs.get("region", "مخصص")
                        })
        except Exception:
            pass

    # Fetch all spots concurrently
    async with httpx.AsyncClient() as client:
        tasks = []
        for spot in all_spots:
            tasks.append(asyncio.gather(
                fetch_marine_data(client, spot["lat"], spot["lon"]),
                fetch_weather_data(client, spot["lat"], spot["lon"])
            ))

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to fetch data: {str(e)}")

    # Analyze all spots
    analyses = []
    for i, spot in enumerate(all_spots):
        if isinstance(results[i], Exception):
            continue
        marine_data, weather_data = results[i]
        try:
            analysis = analyze_spot_data(marine_data, weather_data, spot)
            analyses.append(analysis)
        except Exception:
            continue

    if not analyses:
        raise HTTPException(status_code=503, detail="No spot data available")

    # ── Find best spot RIGHT NOW ──────────────────────────────────────────────
    now_analyses = [a for a in analyses if a.get("current")]
    now_analyses.sort(key=lambda a: a["current"]["verdict"]["score"])
    best_now = now_analyses[0] if now_analyses else None

    # ── Build Golden Windows Table ────────────────────────────────────────────
    golden_windows = []
    for analysis in analyses:
        spot_info = analysis["spot"]
        for day_summary in analysis.get("days", []):
            bw = day_summary.get("best_window")
            if bw and bw["avg_score"] <= 2.0:  # Only excellent/good windows
                golden_windows.append({
                    "spot_name": spot_info["name"],
                    "spot_id": spot_info["id"],
                    "day_label": day_summary["day_label"],
                    "date": day_summary["date"],
                    "window_label": bw["label"],
                    "start_time": bw["start"],
                    "end_time": bw["end"],
                    "avg_score": bw["avg_score"],
                    "verdict_score": bw["verdict_score"],
                    "lat": spot_info["lat"],
                    "lon": spot_info["lon"],
                    "region": spot_info.get("region", ""),
                    "excellent_count": day_summary["excellent_count"],
                })

    # Sort golden windows by quality
    golden_windows.sort(key=lambda w: w["avg_score"])

    # Assign ratings to windows
    for w in golden_windows:
        if w["avg_score"] <= 1.2:
            w["rating"] = "ممتاز 🏆"
            w["rating_color"] = "#22c55e"
        elif w["avg_score"] <= 1.8:
            w["rating"] = "جيد جداً ⭐"
            w["rating_color"] = "#3b82f6"
        else:
            w["rating"] = "مقبول ✅"
            w["rating_color"] = "#f59e0b"

    # Spot rankings
    spot_rankings = []
    for analysis in analyses:
        spot_info = analysis["spot"]
        days = analysis.get("days", [])
        if not days:
            continue
        avg_score = sum(d["avg_verdict_score"] for d in days) / len(days)
        best_day = min(days, key=lambda d: d["avg_verdict_score"])
        spot_rankings.append({
            "spot": spot_info,
            "avg_score": round(avg_score, 2),
            "best_day": best_day.get("day_label"),
            "best_day_score": best_day.get("avg_verdict_score"),
            "excellent_total": sum(d["excellent_count"] for d in days),
            "historical_breach": analysis.get("historical_breach", False),
            "current_verdict": analysis["current"]["verdict"]["verdict"] if analysis.get("current") else "—"
        })

    spot_rankings.sort(key=lambda s: s["avg_score"])

    return {
        "best_spot_now": {
            "spot": best_now["spot"] if best_now else None,
            "current": best_now["current"] if best_now else None,
            "arabic_explanation": best_now["current"]["arabic_explanation"] if best_now and best_now.get("current") else ""
        },
        "golden_windows": golden_windows[:20],  # Top 20 windows
        "spot_rankings": spot_rankings,
        "total_spots_analyzed": len(analyses)
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Render."""
    return {
        "status": "healthy",
        "service": "SurfCast Tunisia API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0"
    }


@app.get("/")
async def root():
    return {
        "message": "🎣 SurfCast Tunisia API — صيد السرف في تونس",
        "docs": "/docs",
        "endpoints": ["/forecast", "/best-spots", "/spots", "/health"]
        }
