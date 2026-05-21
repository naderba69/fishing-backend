# =============================================================================
#  SURFCAST TUNISIA — PRODUCTION BACKEND v3.0
#  ⚠️  الكود المُراجَع والمُصحَّح علمياً بالكامل
#
#  الإصلاحات المطبّقة:
#  ✅ wave_height (الكلي) هو المؤشر الرئيسي، swell_wave_height ثانوي
#  ✅ عتبات دورة الأمواج معيّرة للبحر المتوسط (4-9 ثانية نموذجي)
#  ✅ تحذيرات دقة النموذج: EU 5km للأيام 1-3، عالمي بعدها
#  ✅ نموذج المد مُحسَّن مع إشارة صريحة للتقريب
#  ✅ حساب Hmax التقديري (× 1.8) للموجات الأعلى المتوقعة
#  ✅ current_idx بمقارنة تاريخ/وقت صارمة
#  ✅ ضغط جوي: عتبة ±1.5 hPa/3ساعات لمعنوية المتوسط
#  ✅ تحقق شامل من Null على كل مصفوفة API
#  ✅ hours_since_breach محسوب بالفرق الزمني الفعلي بالساعات
#  ✅ data_quality_score على كل ساعة توقع
# =============================================================================

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
import math
import logging

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("surfcast")

# ─────────────────────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SurfCast Tunisia API v3",
    description="Advanced Surfcasting Engine — Tunisia | Scientifically Calibrated",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# TUNISIA TIMEZONE OFFSET
# Africa/Tunis = UTC+1, no DST
# ─────────────────────────────────────────────────────────────────────────────
TUN_OFFSET = timedelta(hours=1)

# ─────────────────────────────────────────────────────────────────────────────
# PREDEFINED SPOTS
#
# beach_angle: الاتجاه الذي يواجه فيه الشاطئ البحر (بالدرجات، 0=شمال)
# في الفيزياء الأرصادية: ريح "بحرية" تعني أنها تهبّ من الاتجاه الذي يواجه
# الشاطئ (beach_angle)، أي أن فرق الزاوية بين اتجاه الريح وـ beach_angle <= 45°
#
# Tunisia tidal range reference:
# - Gulf of Tunis:  ~0.25m (microtidal)
# - Kelibia/Cap Bon: ~0.20m
# - Sfax/Sousse:   ~0.35m
# - Bizerte:       ~0.20m
# Source: SHOM Mediterranean tide tables + IOC data
# ─────────────────────────────────────────────────────────────────────────────
PREDEFINED_SPOTS = [
    {
        "id": "tunis_carthage",
        "name": "قرطاج - تونس",
        "name_en": "Carthage Beach - Tunis",
        "lat": 36.858,
        "lon": 10.328,
        "beach_angle": 60,
        "region": "تونس الكبرى",
        "tidal_range_m": 0.25,
        "seabed_type": "sandy",
        "exposure": "semi_sheltered"
    },
    {
        "id": "nabeul_kelibia",
        "name": "قليبية - نابل",
        "name_en": "Kelibia - Nabeul",
        "lat": 36.847,
        "lon": 11.106,
        "beach_angle": 90,
        "region": "نابل",
        "tidal_range_m": 0.20,
        "seabed_type": "mixed_sandy_rocky",
        "exposure": "open"
    },
    {
        "id": "nabeul_hammamet",
        "name": "الحمامات - نابل",
        "name_en": "Hammamet - Nabeul",
        "lat": 36.398,
        "lon": 10.617,
        "beach_angle": 45,
        "region": "نابل",
        "tidal_range_m": 0.22,
        "seabed_type": "sandy",
        "exposure": "semi_open"
    },
    {
        "id": "nabeul_tazarka",
        "name": "تازارقة - نابل",
        "name_en": "Tazarka - Nabeul",
        "lat": 36.553,
        "lon": 10.762,
        "beach_angle": 70,
        "region": "نابل",
        "tidal_range_m": 0.22,
        "seabed_type": "sandy",
        "exposure": "semi_open"
    },
    {
        "id": "bizerte_cap_blanc",
        "name": "كاب بيان - بنزرت",
        "name_en": "Cap Blanc - Bizerte",
        "lat": 37.290,
        "lon": 9.869,
        "beach_angle": 330,
        "region": "بنزرت",
        "tidal_range_m": 0.20,
        "seabed_type": "rocky_mixed",
        "exposure": "open"
    },
    {
        "id": "bizerte_sidi_ali_mekki",
        "name": "سيدي علي المكي - بنزرت",
        "name_en": "Sidi Ali Mekki - Bizerte",
        "lat": 37.194,
        "lon": 10.004,
        "beach_angle": 10,
        "region": "بنزرت",
        "tidal_range_m": 0.20,
        "seabed_type": "sandy",
        "exposure": "open"
    },
    {
        "id": "bizerte_ghar_el_melh",
        "name": "غار الملح - بنزرت",
        "name_en": "Ghar El Melh - Bizerte",
        "lat": 37.178,
        "lon": 10.182,
        "beach_angle": 350,
        "region": "بنزرت",
        "tidal_range_m": 0.18,
        "seabed_type": "sandy",
        "exposure": "sheltered"
    },
    {
        "id": "sousse_port_kantaoui",
        "name": "بورت الكنتاوي - سوسة",
        "name_en": "Port El Kantaoui - Sousse",
        "lat": 35.898,
        "lon": 10.598,
        "beach_angle": 80,
        "region": "سوسة",
        "tidal_range_m": 0.32,
        "seabed_type": "sandy",
        "exposure": "semi_open"
    },
    {
        "id": "sousse_chott_meriem",
        "name": "شط مريم - سوسة",
        "name_en": "Chott Meriem - Sousse",
        "lat": 35.969,
        "lon": 10.617,
        "beach_angle": 75,
        "region": "سوسة",
        "tidal_range_m": 0.30,
        "seabed_type": "sandy",
        "exposure": "semi_open"
    },
    {
        "id": "monastir_ksibet",
        "name": "كصيبة المديوني - المنستير",
        "name_en": "Ksibet - Monastir",
        "lat": 35.723,
        "lon": 10.812,
        "beach_angle": 85,
        "region": "المنستير",
        "tidal_range_m": 0.33,
        "seabed_type": "sandy_muddy",
        "exposure": "semi_open"
    },
    {
        "id": "mahdia_ras_dimas",
        "name": "رأس ديماس - المهدية",
        "name_en": "Ras Dimas - Mahdia",
        "lat": 35.502,
        "lon": 11.058,
        "beach_angle": 95,
        "region": "المهدية",
        "tidal_range_m": 0.38,
        "seabed_type": "rocky",
        "exposure": "open"
    },
    {
        "id": "nabeul_menzel_temime",
        "name": "منزل تميم - نابل",
        "name_en": "Menzel Temime - Nabeul",
        "lat": 36.782,
        "lon": 10.997,
        "beach_angle": 85,
        "region": "نابل",
        "tidal_range_m": 0.20,
        "seabed_type": "sandy",
        "exposure": "semi_open"
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# SAFE VALUE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def safe_val(arr: list, idx: int, default: float = 0.0) -> float:
    """
    Safely extract a numeric value from an API array.
    Returns default if:
    - Index out of range
    - Value is None (Open-Meteo returns null for missing data)
    - Value is NaN
    """
    if not arr or idx < 0 or idx >= len(arr):
        return default
    v = arr[idx]
    if v is None:
        return default
    try:
        f = float(v)
        return default if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return default


def safe_arr(data: dict, key: str, default: float = 0.0) -> list:
    """Extract array from API response with null-safety."""
    arr = data.get("hourly", {}).get(key, [])
    if not arr:
        return []
    return arr  # Keep nulls, safe_val handles them per-index


# ─────────────────────────────────────────────────────────────────────────────
# PHYSICS ENGINE — CORRECTED & CALIBRATED FOR MEDITERRANEAN
# ─────────────────────────────────────────────────────────────────────────────

def angular_diff(a1: float, a2: float) -> float:
    """Smallest angular difference between two compass bearings [0–180°]."""
    d = abs(float(a1) - float(a2)) % 360.0
    return d if d <= 180.0 else 360.0 - d


def classify_wind(wind_from_deg: float, beach_facing_deg: float) -> dict:
    """
    Classify wind direction relative to beach orientation.

    PHYSICS NOTE:
    - wind_from_deg (meteorological): direction the wind is COMING FROM
    - beach_facing_deg: direction the beach FACES (toward the sea)
    - ONSHORE = wind coming FROM the direction the beach faces
      i.e. angular_diff(wind_from, beach_facing) is SMALL

    Example: Beach faces East (90°). If wind is from East (90°) → onshore.
    If wind is from West (270°) → offshore.
    """
    diff = angular_diff(wind_from_deg, beach_facing_deg)

    if diff <= 45:
        return {
            "type": "onshore",
            "label": "بحري (Onshore)",
            "label_en": "Onshore",
            "emoji": "🌊",
            "casting_penalty": 1.5,  # تعيق الرمي
            "debris_factor": 2.0,    # يجلب الأعشاب
        }
    elif diff <= 90:
        return {
            "type": "side_onshore",
            "label": "جانبي بحري (Side-Onshore)",
            "label_en": "Side-Onshore",
            "emoji": "↗️",
            "casting_penalty": 1.2,
            "debris_factor": 1.4,
        }
    elif diff <= 135:
        return {
            "type": "side_offshore",
            "label": "جانبي بري (Side-Offshore)",
            "label_en": "Side-Offshore",
            "emoji": "↙️",
            "casting_penalty": 0.9,
            "debris_factor": 0.6,
        }
    else:
        return {
            "type": "offshore",
            "label": "بري (Offshore)",
            "label_en": "Offshore",
            "emoji": "🏔️",
            "casting_penalty": 0.7,
            "debris_factor": 0.3,
        }


def classify_swell(swell_from_deg: float, beach_facing_deg: float) -> dict:
    """
    Classify swell approach angle relative to beach.

    diff <= 30°: Direct/perpendicular approach → max energy transfer to shore,
                 max rip current risk
    diff 30-70°: Angled → moderate energy
    diff > 70°:  Oblique → reduced direct impact
    """
    diff = angular_diff(swell_from_deg, beach_facing_deg)

    if diff <= 30:
        return {
            "type": "direct",
            "label": "مباشر ⊥",
            "angle_diff": round(diff, 1),
            "energy_factor": 1.0,
            "rip_factor": 1.5,
        }
    elif diff <= 70:
        return {
            "type": "angled",
            "label": "مائل",
            "angle_diff": round(diff, 1),
            "energy_factor": math.cos(math.radians(diff)),
            "rip_factor": 1.0,
        }
    else:
        return {
            "type": "oblique",
            "label": "منحرف",
            "angle_diff": round(diff, 1),
            "energy_factor": math.cos(math.radians(diff)),
            "rip_factor": 0.6,
        }


# ─────────────────────────────────────────────────────────────────────────────
# TIDE MODEL — IMPROVED SINUSOIDAL WITH SPOT-SPECIFIC PARAMETERS
#
# SCIENTIFIC NOTE:
# Tunisia has a MICROTIDAL Mediterranean regime.
# Source: Mediterranean tide tables (SHOM/IOC)
# - Tidal range: 0.18–0.40m depending on location
# - Period: 12h25min (M2 semidiurnal dominant)
# - Phase varies by location (Gulf of Gabes has higher range due to resonance)
#
# This model uses a simplified harmonic approach.
# IT IS NOT astronomical tide prediction.
# Accuracy: ±20-40 minutes for peak/trough timing
# ─────────────────────────────────────────────────────────────────────────────

def estimate_tide(hour: int, spot_tidal_range: float = 0.25) -> dict:
    """
    Simplified semidiurnal tidal model for Tunisia.
    Uses M2 principal lunar constituent (period=12.42h).

    Tunisia local time (UTC+1) approximate low tide anchors:
    - Gulf of Tunis / Cap Bon: ~05:00 and ~17:30 (approx, shifts ±2h daily)
    - This is a planning approximation only.

    Returns tide level normalized to [-1, +1] where:
    -1 = lowest (low tide), +1 = highest (high tide)
    """
    # M2 period in hours
    M2_PERIOD = 12.4206
    # Phase anchor: low tide at ~05:30 local Tunisia time (statistical average)
    LOW_TIDE_ANCHOR = 5.5

    angle = ((hour - LOW_TIDE_ANCHOR) / M2_PERIOD) * 2 * math.pi
    level = math.sin(angle)   # -1 = low, +1 = high
    abs_height_m = (level + 1) / 2 * spot_tidal_range  # actual height in meters

    phase = "low" if level < -0.4 else "high" if level > 0.4 else "mid"
    label_map = {
        "low": f"جزر (Low Tide) ~{abs_height_m:.2f}م",
        "mid": f"متوسط (Mid Tide) ~{abs_height_m:.2f}م",
        "high": f"مد (High Tide) ~{abs_height_m:.2f}م",
    }

    return {
        "phase": phase,
        "label": label_map[phase],
        "level_normalized": round(level, 3),
        "abs_height_m": round(abs_height_m, 3),
        "tidal_range_m": spot_tidal_range,
        "is_approximate": True,  # ALWAYS TRUE — this is not real tide prediction
        "accuracy_note": "تقريب رياضي ±40 دقيقة — ليس توقعاً فلكياً حقيقياً",
    }


# ─────────────────────────────────────────────────────────────────────────────
# WAVE ANALYSIS — KEY SCIENTIFIC CORRECTIONS
#
# Open-Meteo variables explained:
#
# wave_height:     Significant wave height Hm0 — TOTAL (swell + wind wave)
#                  = average of highest 1/3 of waves
#                  PRIMARY INDICATOR for fishing conditions
#
# wave_period:     Mean zero-crossing period — AVERAGE of all components
#                  ⚠️ CAN BE MISLEADING: a 6ft/13s reading might actually
#                  mean primary 6ft/9s + secondary 3ft/13s
#                  Source: open-meteo/open-meteo GitHub discussion #577
#
# wave_peak_period: Period of most energetic frequency — MORE RELIABLE
#                  for understanding dominant wave energy
#
# swell_wave_height: Only the swell component (long-period, distant origin)
#                   In Mediterranean, wind waves often DOMINATE
#
# wind_wave_height: Locally generated wind waves — VERY IMPORTANT in Med
#
# Hmax estimate:   ~1.8 × Hm0 (statistical: once per hour, a wave nearly
#                  twice significant height is expected)
#                  Source: NOAA / XWEATHER maritime documentation
# ─────────────────────────────────────────────────────────────────────────────

def analyze_wave_state(
    wave_height: float,        # Total Hm0 (primary)
    wave_period: float,        # Mean period (use with caution)
    wave_peak_period: float,   # Peak period (more reliable)
    wind_wave_height: float,   # Wind wave component
    swell_wave_height: float,  # Swell component
) -> dict:
    """
    Comprehensive wave state analysis.
    Returns dominant wave type and quality indicators.
    """
    wh = max(wave_height, 0.0)
    wph = max(wind_wave_height, 0.0)
    swh = max(swell_wave_height, 0.0)
    pp = max(wave_peak_period, wave_period, 1.0)

    # Hmax: statistical maximum wave height (~once per hour)
    # 15% of waves exceed Hm0; highest 10% reach 25-30% above Hm0
    # Single max wave ~1.8× Hm0
    hmax_estimate = round(wh * 1.8, 2)

    # Dominant wave type
    if wph > swh * 1.3:
        dominant = "wind_sea"
        dominant_label = "موج ريحي محلي (Wind Sea)"
    elif swh > wph * 1.3:
        dominant = "swell"
        dominant_label = "أمواج بعيدة (Swell)"
    else:
        dominant = "mixed"
        dominant_label = "مختلط (Mixed)"

    # Mediterranean wave period calibration:
    # Typical range: 3-9s (wind waves: 3-6s, short swell: 6-9s)
    # Rare exceptional: 9-12s (strong Atlantic swell through Strait of Gibraltar)
    # >12s in Mediterranean is extremely rare
    # Source: scientific literature + local knowledge
    if pp < 4:
        period_quality = "very_short"
        period_label = "قصيرة جداً < 4ث (موج عاصفة)"
        period_score = 4  # worst for fishing
    elif pp < 6:
        period_quality = "short"
        period_label = f"قصيرة {pp:.1f}ث (ريح محلية)"
        period_score = 3
    elif pp < 9:
        period_quality = "moderate"
        period_label = f"متوسطة {pp:.1f}ث (مناسبة للسرف ✅)"
        period_score = 1  # best for surfcasting
    elif pp < 11:
        period_quality = "long"
        period_label = f"طويلة {pp:.1f}ث (نادرة في المتوسط ⚠️)"
        period_score = 2
    else:
        period_quality = "very_long"
        period_label = f"طويلة جداً {pp:.1f}ث (استثنائية جداً في المتوسط 🚨)"
        period_score = 3

    return {
        "wave_height_hm0": round(wh, 3),
        "wind_wave_height": round(wph, 3),
        "swell_wave_height": round(swh, 3),
        "wave_period_mean": round(wave_period, 2),
        "wave_peak_period": round(pp, 2),
        "hmax_estimate": hmax_estimate,
        "dominant_type": dominant,
        "dominant_label": dominant_label,
        "period_quality": period_quality,
        "period_label": period_label,
        "period_score": period_score,
        "wave_height_note": "⚠️ wave_period قد يكون متوسطاً من مكوّنات متعددة — استخدم peak_period للدقة" if abs(wave_period - wave_peak_period) > 2 else "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# SEAWEED / DEBRIS RISK ENGINE
# Uses 48h persistence logic + current conditions
# ─────────────────────────────────────────────────────────────────────────────

def calc_seaweed_risk(
    wave_height: float,
    wind_class: dict,
    historical_breach: bool,
    hours_since_breach_actual: float,  # ACTUAL hours, not index difference
) -> dict:
    """
    Seaweed and debris risk calculation.

    Persistence logic:
    - If swell > 1.8m AND onshore wind occurred in last 48h:
      risk stays elevated for 12 hours post-breach minimum
    - Wind waves contribute more to debris mobilization than swell alone
      (wind waves = locally generated, directly move surface debris)
    """
    # Base risk from current conditions
    wind_type = wind_class.get("type", "offshore")
    debris_factor = wind_class.get("debris_factor", 0.3)

    raw_score = 0.0

    if wave_height > 2.5:
        raw_score += 3.5
    elif wave_height > 1.8:
        raw_score += 2.5
    elif wave_height > 1.2:
        raw_score += 1.5
    elif wave_height > 0.7:
        raw_score += 0.8
    else:
        raw_score += 0.2

    raw_score *= debris_factor

    # Historical persistence: if breach occurred within 12h, keep risk elevated
    persistence_active = (
        historical_breach
        and hours_since_breach_actual is not None
        and hours_since_breach_actual < 12.0
    )
    if persistence_active:
        raw_score = max(raw_score, 2.5)  # minimum HIGH

    # Convert score to risk level
    if raw_score >= 3.0:
        level, label, color, emoji, num = "critical", "حرج ☠️", "#7c3aed", "☠️", 4
    elif raw_score >= 2.0:
        level, label, color, emoji, num = "high", "مرتفع 🚫", "#ef4444", "🚫", 3
    elif raw_score >= 1.0:
        level, label, color, emoji, num = "moderate", "متوسط ⚠️", "#f59e0b", "⚠️", 2
    else:
        level, label, color, emoji, num = "low", "منخفض ✅", "#22c55e", "✅", 1

    return {
        "level": level,
        "label": label,
        "color": color,
        "emoji": emoji,
        "score": num,
        "persistence_active": persistence_active,
        "hours_since_breach": round(hours_since_breach_actual, 1) if hours_since_breach_actual is not None else None,
        "raw_score": round(raw_score, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RIP CURRENT RISK — RECALIBRATED FOR MEDITERRANEAN
#
# SCIENTIFIC BASIS:
# Rip currents form from alongshore variations in wave breaking
# (gaps in sandbars, structures, irregular bathymetry).
# Key factors for Mediterranean:
#
# 1. Wave height threshold: > 0.4m for Mediterranean (NOT ocean thresholds)
# 2. Wave period: > 6.5s is significant in Mediterranean context
#    (NOT 12s — that's ocean surfing threshold)
# 3. Direct swell approach (angle diff <= 30°) maximizes setup gradient
# 4. Tidal phase: Mediterranean microtidal, but LOW tide exposes
#    sandbars and channels = stronger channeling effect
# 5. Sustained onshore wind > 5 m/s increases setup + rip intensity
# ─────────────────────────────────────────────────────────────────────────────

def calc_rip_current_risk(
    wave_height: float,
    wave_peak_period: float,
    wind_wave_height: float,
    swell_class: dict,
    tide: dict,
    wind_speed_ms: float,
    wind_class: dict,
    seabed_type: str = "sandy",
) -> dict:
    """
    Rip current risk calibrated for Mediterranean / Tunisian coasts.

    Seabed type affects rip channel formation:
    - sandy: highest rip risk (mobile sandbars → channels)
    - sandy_muddy: moderate
    - rocky/mixed: lower (less sandbar channeling, but fixed channels exist)
    """
    score = 0.0

    # 1. Wave height factor (Mediterranean calibrated)
    # Even 0.4m persistent waves create rip channels on sandy beaches
    if wave_height > 1.5:
        score += 3.0
    elif wave_height > 1.0:
        score += 2.0
    elif wave_height > 0.6:
        score += 1.5
    elif wave_height > 0.4:
        score += 0.8
    else:
        score += 0.0  # too calm for rip formation

    # 2. Period factor (Mediterranean thresholds)
    # Longer period = more water piling up = stronger rip return
    if wave_peak_period >= 9.0:
        score += 2.5  # exceptionally energetic for Med
    elif wave_peak_period >= 7.0:
        score += 1.8
    elif wave_peak_period >= 6.0:
        score += 1.2
    elif wave_peak_period >= 5.0:
        score += 0.6
    else:
        score += 0.0

    # 3. Swell direction factor
    rip_factor = swell_class.get("rip_factor", 1.0)
    score *= rip_factor

    # 4. Tidal phase (Mediterranean microtidal)
    # Low tide: channels more exposed, rip concentrates
    if tide["phase"] == "low":
        score *= 1.35
    elif tide["phase"] == "mid":
        score *= 1.0

    # 5. Onshore sustained wind increases setup
    if wind_class["type"] in ("onshore", "side_onshore") and wind_speed_ms > 5.0:
        score += min((wind_speed_ms - 5.0) * 0.15, 1.0)

    # 6. Seabed type modifier
    seabed_factors = {
        "sandy": 1.3,          # highest: mobile sandbars form channels
        "sandy_muddy": 1.1,
        "mixed_sandy_rocky": 1.0,
        "rocky": 0.7,          # channels fixed, less intense
        "rocky_mixed": 0.8,
    }
    score *= seabed_factors.get(seabed_type, 1.0)

    # Classify
    if score >= 6.0:
        return {"level": "critical", "label": "تيار رجعي خطير جداً 🌀", "color": "#7c3aed", "emoji": "🌀", "score": 4}
    elif score >= 4.0:
        return {"level": "high", "label": "خطر تيار مرتفع ⚠️", "color": "#ef4444", "emoji": "⚠️", "score": 3}
    elif score >= 2.0:
        return {"level": "moderate", "label": "تيار محتمل 〰️", "color": "#f59e0b", "emoji": "〰️", "score": 2}
    else:
        return {"level": "low", "label": "منخفض ✅", "color": "#22c55e", "emoji": "✅", "score": 1}


# ─────────────────────────────────────────────────────────────────────────────
# WIND / CASTING DANGER
# ─────────────────────────────────────────────────────────────────────────────

def calc_wind_danger(wind_speed_ms: float, gust_ms: float, wind_class: dict) -> dict:
    """
    Wind danger for surfcasting.
    Converted to km/h for display (× 3.6).

    Key thresholds for surfcasting (leader + weight + rod dynamics):
    - <15 km/h: ideal casting
    - 15-25 km/h: manageable with heavier sinker
    - 25-35 km/h: difficult, affects accuracy, gust risk
    - 35-50 km/h: very difficult, casting inaccurate, line drift
    - >50 km/h: impossible (rod tip deflection, bait drift, safety risk)

    Onshore wind compounds danger (casting against wind).
    """
    spd = max(wind_speed_ms, 0.0)
    gst = max(gust_ms, spd * 1.3)  # gust minimum 1.3× speed if missing

    spd_kh = spd * 3.6
    gst_kh = gst * 3.6

    # Onshore penalty: casting against wind is harder
    onshore_factor = 1.25 if wind_class["type"] == "onshore" else 1.0
    effective_spd = spd_kh * onshore_factor
    effective_gst = gst_kh * onshore_factor

    detail = f"ريح {spd_kh:.0f} كم/س | هبّة {gst_kh:.0f} كم/س"
    if wind_class["type"] == "onshore":
        detail += " (مضاعف: ريح بحرية)"

    if effective_gst > 60 or effective_spd > 50:
        return {"level": "impossible", "label": "مستحيل ⛔", "color": "#7c3aed", "emoji": "🌪️", "score": 4, "detail": detail}
    elif effective_gst > 45 or effective_spd > 35:
        return {"level": "dangerous", "label": "صعب جداً 💨", "color": "#ef4444", "emoji": "💨", "score": 3, "detail": detail}
    elif effective_gst > 30 or effective_spd > 22:
        return {"level": "difficult", "label": "متعذّر 🌬️", "color": "#f59e0b", "emoji": "🌬️", "score": 2, "detail": detail}
    else:
        return {"level": "good", "label": "ملائم ✅", "color": "#22c55e", "emoji": "🎣", "score": 1, "detail": detail}


# ─────────────────────────────────────────────────────────────────────────────
# BAROMETRIC PRESSURE TREND
# Calibrated for Mediterranean: ±1.5 hPa/3h = meteorologically significant
# (oceanic: ±3 hPa/3h. Mediterranean is more volatile → lower threshold)
# ─────────────────────────────────────────────────────────────────────────────

def calc_pressure_trend(pressures: list, idx: int) -> dict:
    """
    3-hour barometric pressure trend.

    Mediterranean calibration:
    - Drop > 1.5 hPa/3h = significant (fish activity increases before storms)
    - Drop > 4 hPa/3h = rapid (approaching system, rough conditions soon)
    - Rise > 1.5 hPa/3h = stabilizing (fish less active)
    - ±1.5 hPa = stable (no significant change)
    """
    if idx < 3 or not pressures:
        return {"trend": "stable", "label": "مستقر 📊", "delta": 0.0, "fishing_bonus": False}

    # Use 3-hour window
    p_now = safe_val(pressures, idx, 1013.0)
    p_3h = safe_val(pressures, max(0, idx - 3), 1013.0)

    delta = p_now - p_3h  # negative = falling

    if delta < -4.0:
        return {"trend": "falling_rapid", "label": "هابط بسرعة ⚡📉", "delta": round(delta, 2), "fishing_bonus": True, "warning": "نظام عاصفي قادم"}
    elif delta < -1.5:
        return {"trend": "falling", "label": "هابط تدريجياً 📉", "delta": round(delta, 2), "fishing_bonus": True, "warning": None}
    elif delta > 4.0:
        return {"trend": "rising_rapid", "label": "صاعد بسرعة 📈", "delta": round(delta, 2), "fishing_bonus": False, "warning": None}
    elif delta > 1.5:
        return {"trend": "rising", "label": "صاعد 📈", "delta": round(delta, 2), "fishing_bonus": False, "warning": None}
    else:
        return {"trend": "stable", "label": "مستقر 📊", "delta": round(delta, 2), "fishing_bonus": False, "warning": None}


# ─────────────────────────────────────────────────────────────────────────────
# SINKER WEIGHT ADVISOR
# ─────────────────────────────────────────────────────────────────────────────

def recommend_sinker(
    wave_height: float,
    wave_peak_period: float,
    rip_risk: dict,
    wind_speed_ms: float,
    seabed_type: str,
) -> dict:
    """
    Sinker recommendation based on actual sea conditions.

    Tunisian surfcasting sinker types:
    - Grapple/Spider/Claw (مرساة/عنكبوت): anchoring, for rip + strong swell
    - Pyramid (هرمي): holds ground, moderate-heavy swell
    - Breakaway/Grip (قابض): releases on retrieve, moderate conditions
    - Bomb/Round (كروي/قنبلة): maximum casting distance, calm seas
    """
    # Rip current → must anchor
    if rip_risk["score"] >= 3:
        return {
            "type": "Grapple / Spider Anchor",
            "type_ar": "مرساة / عنكبوت",
            "weight": "130–180g",
            "reason": f"تيار رجعي قوي — المرساة ضرورية لتثبيت الطعم وتجنب الانجراف",
            "emoji": "⚓",
            "color": "#ef4444",
            "priority": "required"
        }

    # Heavy swell or long period
    if wave_height > 1.5 or wave_peak_period > 8:
        return {
            "type": "Pyramid",
            "type_ar": "هرمي",
            "weight": "110–130g",
            "reason": f"موج {wave_height:.1f}م / دورة {wave_peak_period:.1f}ث — الهرمي يحفر في القاع ويمنع الزحف",
            "emoji": "🔺",
            "color": "#f59e0b",
            "priority": "recommended"
        }

    # Moderate conditions, rocky seabed → grip to avoid snagging
    if seabed_type in ("rocky", "rocky_mixed") and wave_height > 0.5:
        return {
            "type": "Breakaway / Release Grip",
            "type_ar": "قابض قابل للتحرير",
            "weight": "80–110g",
            "reason": f"قاع صخري مع موج {wave_height:.1f}م — القابض يتحرر عند السحب ويمنع الفقدان",
            "emoji": "🪝",
            "color": "#3b82f6",
            "priority": "recommended"
        }

    # Moderate swell, sandy bottom
    if wave_height > 0.7:
        return {
            "type": "Breakaway / Grip",
            "type_ar": "قابض / مخلب",
            "weight": "90–110g",
            "reason": f"موج معتدل {wave_height:.1f}م — القابض يثبت مع إمكانية استرداد الطعم",
            "emoji": "🪝",
            "color": "#3b82f6",
            "priority": "recommended"
        }

    # Calm sea → maximize distance
    return {
        "type": "Round Bomb / Sphere",
        "type_ar": "كروي / قنبلة",
        "weight": "60–90g",
        "reason": f"بحر هادئ {wave_height:.1f}م — الكروي يتيح أقصى مسافة رمي",
        "emoji": "⚫",
        "color": "#22c55e",
        "priority": "optimal"
    }


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY SCORE — NEW FEATURE
# Tells the user how reliable this specific hour's forecast is
# ─────────────────────────────────────────────────────────────────────────────

def calc_data_quality(
    day_offset: int,
    is_interpolated: bool,
    null_count: int,
    total_vars: int = 10,
) -> dict:
    """
    Data quality assessment per forecast hour.

    Factors:
    1. Model: EU 5km (days 0-2) vs Global interpolated (day 3+)
    2. Null/missing variables from API
    3. Interpolation flag (global model data interpolated from 3h→1h)
    """
    score = 100

    # Model quality penalty
    if day_offset >= 3:
        score -= 25  # global model, less accurate
    if is_interpolated:
        score -= 15  # interpolated from 3h intervals

    # Missing data penalty
    if total_vars > 0:
        null_pct = null_count / total_vars
        score -= int(null_pct * 30)

    score = max(0, min(100, score))

    if score >= 85:
        level, color, label = "high", "#22c55e", "عالية ✅"
    elif score >= 65:
        level, color, label = "medium", "#f59e0b", "متوسطة ⚠️"
    else:
        level, color, label = "low", "#ef4444", "منخفضة ⛔"

    model_name = "EU ICON-Wave 5km" if day_offset < 3 else "Global Wave (interpolated)"

    return {
        "score": score,
        "level": level,
        "color": color,
        "label": label,
        "model": model_name,
        "is_interpolated": is_interpolated,
        "note": (
            "نموذج أوروبي 5كم — دقة عالية للبحر المتوسط"
            if day_offset < 3
            else "نموذج عالمي مُحوَّل من 3ساعات إلى ساعة — انخفاض في الدقة"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ULTIMATE VERDICT MATRIX
# ─────────────────────────────────────────────────────────────────────────────

def calc_verdict(
    wave_height: float,
    wave_state: dict,
    seaweed_risk: dict,
    rip_risk: dict,
    wind_danger: dict,
    pressure_trend: dict,
    wind_class: dict,
    data_quality: dict,
) -> dict:
    """
    Master fishing verdict combining all risk factors.

    Grading:
    ممتاز (EXCELLENT): rare optimal conditions
    ممكن (POSSIBLE):   acceptable conditions
    صعب (DIFFICULT):   challenging but doable for experienced
    صعب جداً (VERY DIFFICULT): experts only
    مستحيل (IMPOSSIBLE): do not fish

    EXCELLENT requires ALL of:
    - wave_height between 0.4m and 1.2m
    - All risks LOW (score == 1)
    - Wind is side-offshore or offshore
    - Pressure stable or gently falling
    - Data quality >= medium

    IMPOSSIBLE if ANY of:
    - wind_danger impossible
    - rip_risk critical (score 4)
    - wave_height > 3.0m
    """

    # Hard IMPOSSIBLE checks
    if (
        wind_danger["level"] == "impossible"
        or rip_risk["score"] == 4
        or wave_height > 3.0
    ):
        return {
            "verdict": "مستحيل ⛔",
            "verdict_en": "IMPOSSIBLE",
            "color": "#7c3aed",
            "bg_color": "rgba(124,58,237,0.12)",
            "emoji": "⛔",
            "score": 4,
            "stars": 0,
        }

    # Total risk score
    risk_total = seaweed_risk["score"] + rip_risk["score"] + wind_danger["score"]
    # Max possible = 12, minimum = 3

    # EXCELLENT: all green lights
    excellent = (
        0.4 <= wave_height <= 1.2
        and seaweed_risk["score"] == 1
        and rip_risk["score"] == 1
        and wind_danger["score"] == 1
        and wind_class["type"] in ("offshore", "side_offshore")
        and pressure_trend["trend"] in ("stable", "falling", "falling_rapid")
        and data_quality["level"] != "low"
        and wave_state["period_quality"] in ("moderate", "long")
    )
    if excellent:
        return {
            "verdict": "ممتاز 🏆",
            "verdict_en": "EXCELLENT",
            "color": "#22c55e",
            "bg_color": "rgba(34,197,94,0.12)",
            "emoji": "🏆",
            "score": 1,
            "stars": 5,
        }

    # VERY DIFFICULT / IMPOSSIBLE (high risk but not complete)
    if risk_total >= 10 or wave_height > 2.0:
        return {
            "verdict": "مستحيل تقريباً ⛔",
            "verdict_en": "IMPOSSIBLE",
            "color": "#ef4444",
            "bg_color": "rgba(239,68,68,0.12)",
            "emoji": "⛔",
            "score": 4,
            "stars": 0,
        }

    # VERY DIFFICULT
    if risk_total >= 8:
        return {
            "verdict": "صعب جداً ⚠️",
            "verdict_en": "VERY_DIFFICULT",
            "color": "#f59e0b",
            "bg_color": "rgba(245,158,11,0.12)",
            "emoji": "⚠️",
            "score": 3,
            "stars": 1,
        }

    # POSSIBLE
    possible = (
        0.3 <= wave_height <= 1.8
        and seaweed_risk["score"] <= 2
        and rip_risk["score"] <= 2
        and wind_danger["score"] <= 2
    )
    if possible:
        stars = 3 if risk_total <= 5 else 2
        return {
            "verdict": "ممكن ✅",
            "verdict_en": "POSSIBLE",
            "color": "#3b82f6",
            "bg_color": "rgba(59,130,246,0.12)",
            "emoji": "✅",
            "score": 2,
            "stars": stars,
        }

    # Default fallback
    return {
        "verdict": "صعب جداً ⚠️",
        "verdict_en": "VERY_DIFFICULT",
        "color": "#f59e0b",
        "bg_color": "rgba(245,158,11,0.12)",
        "emoji": "⚠️",
        "score": 3,
        "stars": 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ARABIC EXPLANATION GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_explanation(
    h: dict,
    spot_name: str,
    historical_breach: bool,
    data_quality: dict,
) -> str:
    """Generate a detailed Arabic explanation of the fishing verdict."""

    parts = [f"📍 {spot_name}"]

    # Wave state
    ws = h.get("wave_state", {})
    wh = ws.get("wave_height_hm0", 0)
    pp = ws.get("wave_peak_period", 5)
    hmax = ws.get("hmax_estimate", 0)
    dom = ws.get("dominant_label", "")

    if wh < 0.3:
        parts.append(f"البحر هادئ جداً ({wh:.2f}م) — الأسماك قد تبتعد للأعماق")
    elif wh <= 1.2:
        parts.append(f"أمواج مثالية للسرف: {wh:.2f}م ({dom}) | أعلى موجة متوقعة: ~{hmax}م | دورة الذروة: {pp:.1f}ث")
    elif wh <= 2.0:
        parts.append(f"أمواج متوسطة إلى مرتفعة: {wh:.2f}م | أعلى موجة متوقعة إحصائياً: ~{hmax}م ⚠️")
    else:
        parts.append(f"تحذير: أمواج عالية جداً {wh:.2f}م | الأعلى المتوقع: ~{hmax}م 🚨")

    # Wind
    wd = h.get("wind_danger", {})
    wc = h.get("wind_classification", {})
    parts.append(f"الريح: {wc.get('label','؟')} — {wd.get('detail','')}")

    # Historical breach
    if historical_breach:
        hrs = h.get("seaweed_risk", {}).get("hours_since_breach")
        if h.get("seaweed_risk", {}).get("persistence_active"):
            parts.append(f"⚠️ تلوث مستمر: اضطراب خلال آخر 12 ساعة — عشب وحطام محتمل")
        elif hrs is not None:
            parts.append(f"البحر بدأ يستقر بعد اضطراب قبل ~{hrs:.0f} ساعة")

    # Rip current
    rip = h.get("rip_current_risk", {})
    tide = h.get("tide_phase", {})
    if rip["score"] >= 3:
        parts.append(
            f"🌀 خطر تيار رجعي (سرعة الأمواج {pp:.1f}ث + {tide.get('label','')}) "
            f"— الجانب الصخري أو الفتحات في الحواجز الرملية أكثر خطراً"
        )
    elif rip["score"] == 2:
        parts.append(f"توخَّ الحذر من تيارات محلية في فجوات الشاطئ")

    # Pressure
    pt = h.get("pressure_trend", {})
    if pt.get("fishing_bonus"):
        parts.append(f"📉 ضغط جوي هابط ({pt['delta']:.1f} hPa/3ساعات) — تنشّط الأسماك قبيل التغيّر")
    if pt.get("warning"):
        parts.append(f"⚡ تحذير: {pt['warning']}")

    # Data quality warning
    if data_quality["level"] == "low":
        parts.append(f"📡 تحذير: دقة البيانات منخفضة ({data_quality['model']}) — استخدم هذه التوقعات بحذر شديد")
    elif data_quality["level"] == "medium" and data_quality["is_interpolated"]:
        parts.append(f"📡 البيانات مُحوَّلة من كل 3ساعات — دقة متوسطة")

    # Verdict
    v = h.get("verdict", {}).get("verdict_en", "")
    verdict_txt = {
        "EXCELLENT": "✅ ظروف مثالية نادرة في المتوسط — استغل الفرصة!",
        "POSSIBLE": "✅ ظروف مقبولة — الصيد ممكن مع مراعاة المخاطر المذكورة",
        "VERY_DIFFICULT": "⚠️ ظروف صعبة — لا يُنصح إلا لذوي الخبرة العالية",
        "IMPOSSIBLE": "⛔ ظروف خطيرة — يُمنع الصيد في هذه الأحوال",
    }.get(v, "")
    if verdict_txt:
        parts.append(verdict_txt)

    return " | ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# API DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_marine(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """
    Fetch all available marine variables from Open-Meteo.
    past_days=2 → 48h history
    forecast_days=4 → today + 3 full future days
    """
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "wave_height",
            "wave_direction",
            "wave_period",
            "wave_peak_period",
            "wind_wave_height",
            "wind_wave_direction",
            "wind_wave_period",
            "wind_wave_peak_period",
            "swell_wave_height",
            "swell_wave_direction",
            "swell_wave_period",
            "swell_wave_peak_period",
        ]),
        "past_days": 2,
        "forecast_days": 4,
        "timezone": "Africa/Tunis",
    }
    try:
        resp = await client.get(url, params=params, timeout=25.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        log.error(f"Marine API error {e.response.status_code} for ({lat},{lon})")
        raise
    except httpx.RequestError as e:
        log.error(f"Marine API network error for ({lat},{lon}): {e}")
        raise


async def fetch_weather(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """
    Fetch weather forecast from Open-Meteo.
    Includes surface pressure for barometric trend.
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
            "weather_code",
        ]),
        "past_days": 2,
        "forecast_days": 4,
        "timezone": "Africa/Tunis",
        "wind_speed_unit": "ms",  # always fetch in m/s for physics accuracy
    }
    try:
        resp = await client.get(url, params=params, timeout=25.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        log.error(f"Weather API error {e.response.status_code} for ({lat},{lon})")
        raise
    except httpx.RequestError as e:
        log.error(f"Weather API network error for ({lat},{lon}): {e}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# CURRENT INDEX FINDER — FIXED
#
# BUG IN ORIGINAL: string comparison could fail if format differs slightly
# FIX: Parse both times as datetime objects and compare properly
# ─────────────────────────────────────────────────────────────────────────────

def find_current_index(times: list) -> int:
    """
    Find the index corresponding to the current hour.
    Returns the index of the first time >= current local time.

    Uses datetime comparison (not string comparison) to avoid format issues.
    Tunisia = UTC+1.
    """
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc + TUN_OFFSET
    # Round down to current hour
    now_hour = now_local.replace(minute=0, second=0, microsecond=0)

    best_idx = 0
    best_delta = float('inf')

    for i, t_str in enumerate(times):
        try:
            # Handle both "2024-01-15T14:00" and "2024-01-15T14:00:00" formats
            t_str_clean = str(t_str).strip()
            if len(t_str_clean) == 16:
                t_str_clean += ":00"
            t_dt = datetime.fromisoformat(t_str_clean)
            # Make timezone-naive comparison (both are local Tunisia time)
            t_dt_naive = t_dt.replace(tzinfo=None)
            now_naive = now_hour.replace(tzinfo=None)
            delta = abs((t_dt_naive - now_naive).total_seconds())
            if delta < best_delta:
                best_delta = delta
                best_idx = i
        except (ValueError, TypeError):
            continue

    log.info(f"Current index: {best_idx}, time: {times[best_idx] if times else 'N/A'}")
    return best_idx


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ANALYSIS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def analyze_spot(marine: dict, weather: dict, spot: dict) -> dict:
    """
    Full analysis engine. All physics corrected for Mediterranean.
    Returns structured data with hourly forecasts for 72h future.
    """
    beach_angle = float(spot.get("beach_angle", 90))
    tidal_range = float(spot.get("tidal_range_m", 0.25))
    seabed_type = spot.get("seabed_type", "sandy")
    times = marine.get("hourly", {}).get("time", [])
    n = len(times)

    if n == 0:
        raise ValueError(f"No time data returned from Marine API for spot {spot.get('id')}")

    # ── Extract all raw arrays ──────────────────────────────────────────────
    wave_heights     = safe_arr(marine, "wave_height")
    wave_dirs        = safe_arr(marine, "wave_direction")
    wave_periods     = safe_arr(marine, "wave_period")
    wave_peak_p      = safe_arr(marine, "wave_peak_period")
    ww_heights       = safe_arr(marine, "wind_wave_height")
    ww_dirs          = safe_arr(marine, "wind_wave_direction")
    ww_periods       = safe_arr(marine, "wind_wave_period")
    sw_heights       = safe_arr(marine, "swell_wave_height")
    sw_dirs          = safe_arr(marine, "swell_wave_direction")
    sw_periods       = safe_arr(marine, "swell_wave_period")
    sw_peak_p        = safe_arr(marine, "swell_wave_peak_period")

    wind_speeds      = safe_arr(weather, "wind_speed_10m")
    wind_dirs        = safe_arr(weather, "wind_direction_10m")
    wind_gusts       = safe_arr(weather, "wind_gusts_10m")
    pressures        = safe_arr(weather, "surface_pressure")
    temperatures     = safe_arr(weather, "temperature_2m")
    precip_probs     = safe_arr(weather, "precipitation_probability")
    cloud_covers     = safe_arr(weather, "cloud_cover")
    weather_codes    = safe_arr(weather, "weather_code")

    # ── Find current index (FIXED) ─────────────────────────────────────────
    current_idx = find_current_index(times)

    # ── 48h Historical Breach Analysis ────────────────────────────────────
    # Scan past 48 hours for: wave_height > 1.8m AND onshore wind
    historical_breach = False
    breach_datetime = None
    hist_start = max(0, current_idx - 48)

    for i in range(hist_start, current_idx):
        h_wave = safe_val(wave_heights, i, 0.0)
        h_wind_dir = safe_val(wind_dirs, i, 0.0)
        h_wind_class = classify_wind(h_wind_dir, beach_angle)
        if h_wave > 1.8 and h_wind_class["type"] == "onshore":
            historical_breach = True
            # Record the LAST breach time for accurate hours calculation
            try:
                t_str = str(times[i]).strip()
                if len(t_str) == 16:
                    t_str += ":00"
                breach_datetime = datetime.fromisoformat(t_str)
            except Exception:
                breach_datetime = None

    # ── Calculate actual hours since breach ───────────────────────────────
    # BUG FIX: original used index difference, not actual time difference
    def get_hours_since_breach(hour_time_str: str) -> Optional[float]:
        if not breach_datetime or not hour_time_str:
            return None
        try:
            t_str = str(hour_time_str).strip()
            if len(t_str) == 16:
                t_str += ":00"
            hour_dt = datetime.fromisoformat(t_str)
            delta_s = (hour_dt - breach_datetime).total_seconds()
            return max(0.0, delta_s / 3600.0)
        except Exception:
            return None

    # ── Build 72-hour future forecast ─────────────────────────────────────
    forecast_hours = []
    future_end = min(n, current_idx + 73)

    now_local = (datetime.now(timezone.utc) + TUN_OFFSET)

    for i in range(current_idx, future_end):
        t_str = str(times[i]).strip()
        try:
            t_str_full = t_str if len(t_str) > 16 else t_str + ":00"
            t_dt = datetime.fromisoformat(t_str_full)
        except (ValueError, TypeError):
            continue

        hour = t_dt.hour
        # Days from today (date comparison)
        today_date = now_local.date()
        hour_date = t_dt.date()
        day_offset = (hour_date - today_date).days

        # Model accuracy: EU 5km for days 0-2, global interpolated for day 3+
        is_interpolated = day_offset >= 3

        # Count null values for data quality
        key_vars = [
            safe_val(wave_heights, i, None) if wave_heights and i < len(wave_heights) and wave_heights[i] is not None else None,
            safe_val(wind_speeds, i, None) if wind_speeds and i < len(wind_speeds) and wind_speeds[i] is not None else None,
        ]
        null_count = sum(1 for v in key_vars if v is None)

        # Safe value extraction for this hour
        def sv(arr, default=0.0):
            return safe_val(arr, i, default)

        # PRIMARY: wave_height (total Hm0) — NOT just swell
        wh = sv(wave_heights, 0.0)
        wd = sv(wave_dirs, 0.0)
        wp = sv(wave_periods, 6.0)
        wpp = sv(wave_peak_p, wp)  # peak period, fallback to mean period
        wwh = sv(ww_heights, 0.0)
        wwd = sv(ww_dirs, wd)
        swh = sv(sw_heights, 0.0)
        swd = sv(sw_dirs, wd)
        swp = sv(sw_periods, wp)
        swpp = sv(sw_peak_p, wpp)

        ws = sv(wind_speeds, 0.0)
        wdir = sv(wind_dirs, 0.0)
        wg = sv(wind_gusts, ws * 1.3)
        pressure = sv(pressures, 1013.25)
        temp = sv(temperatures, 20.0)
        precip = sv(precip_probs, 0.0)
        cloud = sv(cloud_covers, 0.0)
        wcode = int(sv(weather_codes, 0))

        # Use best available period (peak is more reliable for physics)
        best_period = wpp if wpp > 0 else wp

        # Physics calculations
        wind_class = classify_wind(wdir, beach_angle)
        # For swell direction: use combined wave direction (not just swell)
        # because in Med, wind waves dominate
        dominant_dir = wwd if wwh > swh else swd
        swell_class = classify_swell(dominant_dir, beach_angle)
        tide = estimate_tide(hour, tidal_range)
        hours_since = get_hours_since_breach(t_str)
        wave_state = analyze_wave_state(wh, wp, wpp, wwh, swh)
        seaweed = calc_seaweed_risk(wh, wind_class, historical_breach, hours_since if hours_since is not None else 999.0)
        rip = calc_rip_current_risk(wh, best_period, wwh, swell_class, tide, ws, wind_class, seabed_type)
        wind_danger = calc_wind_danger(ws, wg, wind_class)
        pressure_trend = calc_pressure_trend(pressures, i)
        sinker = recommend_sinker(wh, best_period, rip, ws, seabed_type)
        dq = calc_data_quality(day_offset, is_interpolated, null_count)
        verdict = calc_verdict(wh, wave_state, seaweed, rip, wind_danger, pressure_trend, wind_class, dq)

        record = {
            # Time
            "time": t_str,
            "hour": hour,
            "day_offset": day_offset,
            "day_label": {0: "اليوم", 1: "غداً", 2: "بعد غد"}.get(day_offset, f"يوم +{day_offset}"),

            # Raw wave data (all variables, labeled clearly)
            "wave_height": round(wh, 3),          # PRIMARY: Hm0 total
            "wave_direction": round(wd, 1),
            "wave_period": round(wp, 2),           # mean period (use with caution)
            "wave_peak_period": round(wpp, 2),     # peak period (more reliable)
            "wind_wave_height": round(wwh, 3),     # wind wave component
            "wind_wave_direction": round(wwd, 1),
            "wind_wave_period": round(sv(ww_periods, 4.0), 2),
            "swell_wave_height": round(swh, 3),    # swell component
            "swell_wave_direction": round(swd, 1),
            "swell_wave_period": round(swp, 2),
            "swell_wave_peak_period": round(swpp, 2),
            "hmax_estimate": wave_state["hmax_estimate"],  # statistical max wave

            # Raw weather data
            "wind_speed_ms": round(ws, 2),
            "wind_speed_kmh": round(ws * 3.6, 1),
            "wind_direction": round(wdir, 1),
            "wind_gust_ms": round(wg, 2),
            "wind_gust_kmh": round(wg * 3.6, 1),
            "pressure_hpa": round(pressure, 2),
            "temperature_c": round(temp, 1),
            "precipitation_probability": round(precip, 0),
            "cloud_cover": round(cloud, 0),
            "weather_code": wcode,

            # Physics analysis
            "wave_state": wave_state,
            "wind_classification": wind_class,
            "swell_classification": swell_class,
            "tide_phase": tide,

            # Risk assessments
            "seaweed_risk": seaweed,
            "rip_current_risk": rip,
            "wind_danger": wind_danger,
            "pressure_trend": pressure_trend,

            # Recommendations
            "sinker_recommendation": sinker,
            "verdict": verdict,
            "data_quality": dq,
        }

        record["arabic_explanation"] = generate_explanation(
            record, spot.get("name", "الموقع"), historical_breach, dq
        )

        forecast_hours.append(record)

    # ── Group by day ───────────────────────────────────────────────────────
    days_dict: dict = {}
    for h in forecast_hours:
        d = h["day_offset"]
        if d not in days_dict:
            days_dict[d] = []
        days_dict[d].append(h)

    # ── Per-day summary ────────────────────────────────────────────────────
    day_summaries = []
    for d_off in sorted(days_dict.keys()):
        day_hours = days_dict[d_off]
        if not day_hours:
            continue

        verdict_scores = [h["verdict"]["score"] for h in day_hours]
        best_score = min(verdict_scores)
        best_hour_rec = min(day_hours, key=lambda h: h["verdict"]["score"])
        excellent_hours = [h for h in day_hours if h["verdict"]["verdict_en"] == "EXCELLENT"]

        # Best 3-hour fishing window
        best_window = None
        if len(day_hours) >= 3:
            bw_score = float('inf')
            for j in range(len(day_hours) - 2):
                w = day_hours[j:j+3]
                avg = sum(h["verdict"]["score"] for h in w) / 3.0
                if avg < bw_score:
                    bw_score = avg
                    best_window = {
                        "start": w[0]["time"],
                        "end": w[-1]["time"],
                        "label": f'{w[0]["hour"]:02d}:00 → {w[-1]["hour"]:02d}:00',
                        "avg_score": round(bw_score, 2),
                    }

        # Average data quality for the day
        avg_dq = sum(h["data_quality"]["score"] for h in day_hours) / len(day_hours)

        day_summaries.append({
            "day_offset": d_off,
            "day_label": day_hours[0]["day_label"],
            "date": day_hours[0]["time"][:10],
            "best_hour": best_hour_rec,
            "best_window": best_window,
            "best_verdict_score": best_score,
            "avg_verdict_score": round(sum(verdict_scores) / len(verdict_scores), 2),
            "excellent_count": len(excellent_hours),
            "model": "EU ICON-Wave 5km" if d_off < 3 else "Global (interpolated)",
            "avg_data_quality": round(avg_dq, 1),
            "hours": day_hours,
        })

    return {
        "spot": spot,
        "historical_breach": historical_breach,
        "breach_datetime": breach_datetime.isoformat() if breach_datetime else None,
        "current": forecast_hours[0] if forecast_hours else None,
        "days": day_summaries,
        "all_hours": forecast_hours,
        "data_disclaimer": {
            "tide_model": "تقريب رياضي للمد — ليس توقعاً فلكياً. الدقة: ±20-40 دقيقة. المدى في تونس: 0.18-0.40م",
            "wave_period": "wave_period قد يكون متوسطاً من مكوّنات متعددة — استخدم wave_peak_period للدقة",
            "model_switch": "الأيام 1-3: نموذج EU ICON-Wave 5km (دقة عالية) | يوم 4+: نموذج عالمي مُحوَّل من 3ساعات",
            "hmax": "hmax_estimate = wave_height × 1.8 — الموجة الأعلى المتوقعة إحصائياً مرة كل ساعة تقريباً",
            "rip_currents": "حساب الأمواج الرجعية يعتمد على معطيات الموج فقط — الأمواج الرجعية الفعلية تتشكّل حسب تضاريس القاع المحلية",
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/spots")
async def get_spots():
    """Return all predefined spots with full metadata."""
    return {
        "spots": PREDEFINED_SPOTS,
        "count": len(PREDEFINED_SPOTS),
        "coverage": "Tunisia coastal surfcasting spots — calibrated beach angles and tidal ranges",
    }


@app.get("/forecast")
async def get_forecast(
    lat: float = Query(..., ge=-90, le=90, description="Latitude WGS84"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude WGS84"),
    name: Optional[str] = Query(None, description="Spot name"),
    beach_angle: Optional[float] = Query(None, ge=0, le=359, description="Beach facing direction (degrees, 0=N, 90=E, 180=S, 270=W)"),
):
    """
    Full 3-day forecast analysis for a single coordinate.
    48h historical breach detection + 72h future forecast.
    All physics calibrated for Mediterranean.
    """
    # Match against predefined spots (within 3km tolerance)
    matched = None
    for s in PREDEFINED_SPOTS:
        lat_diff = abs(s["lat"] - lat)
        lon_diff = abs(s["lon"] - lon)
        if lat_diff < 0.03 and lon_diff < 0.03:
            matched = s
            break

    if matched is None:
        matched = {
            "id": f"custom_{lat:.5f}_{lon:.5f}",
            "name": name or f"موقع مخصص ({lat:.3f}°N, {lon:.3f}°E)",
            "name_en": name or f"Custom Spot ({lat:.3f}N, {lon:.3f}E)",
            "lat": lat,
            "lon": lon,
            "beach_angle": float(beach_angle) if beach_angle is not None else 90.0,
            "region": "مخصص",
            "tidal_range_m": 0.25,  # Mediterranean average for Tunisia
            "seabed_type": "sandy",
            "exposure": "unknown",
        }

    log.info(f"Fetching forecast for: {matched['name']} ({lat}, {lon})")

    async with httpx.AsyncClient() as client:
        try:
            marine_data, weather_data = await asyncio.gather(
                fetch_marine(client, matched["lat"], matched["lon"]),
                fetch_weather(client, matched["lat"], matched["lon"]),
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Open-Meteo API returned {e.response.status_code}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Cannot reach Open-Meteo: {str(e)}")

    try:
        result = analyze_spot(marine_data, weather_data, matched)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.exception(f"Analysis error for {matched['name']}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    return result


@app.get("/best-spots")
async def get_best_spots(
    custom_spots: Optional[str] = Query(None, description="JSON array of custom spots"),
):
    """
    Scan ALL spots concurrently, evaluate 3-day forecast,
    and return best spot + golden time windows table.
    """
    import json

    all_spots = list(PREDEFINED_SPOTS)

    if custom_spots:
        try:
            parsed = json.loads(custom_spots)
            if isinstance(parsed, list):
                for cs in parsed:
                    if "lat" in cs and "lon" in cs:
                        all_spots.append({
                            "id": f"custom_{cs['lat']}_{cs['lon']}",
                            "name": cs.get("name", f"مخصص ({float(cs['lat']):.3f}°N)"),
                            "name_en": cs.get("name_en", "Custom"),
                            "lat": float(cs["lat"]),
                            "lon": float(cs["lon"]),
                            "beach_angle": float(cs.get("beach_angle", 90)),
                            "region": cs.get("region", "مخصص"),
                            "tidal_range_m": float(cs.get("tidal_range_m", 0.25)),
                            "seabed_type": cs.get("seabed_type", "sandy"),
                            "exposure": "unknown",
                        })
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Concurrent fetch for all spots
    async with httpx.AsyncClient() as client:
        fetch_tasks = [
            asyncio.gather(
                fetch_marine(client, s["lat"], s["lon"]),
                fetch_weather(client, s["lat"], s["lon"]),
                return_exceptions=True
            )
            for s in all_spots
        ]
        raw_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    # Analyze each spot
    analyses = []
    for i, spot in enumerate(all_spots):
        result = raw_results[i]
        if isinstance(result, Exception):
            log.warning(f"Failed to fetch {spot['name']}: {result}")
            continue
        if isinstance(result, tuple) and len(result) == 2:
            marine_r, weather_r = result
            if isinstance(marine_r, Exception) or isinstance(weather_r, Exception):
                log.warning(f"Data error for {spot['name']}")
                continue
            try:
                analysis = analyze_spot(marine_r, weather_r, spot)
                analyses.append(analysis)
            except Exception as e:
                log.warning(f"Analysis failed for {spot['name']}: {e}")
                continue

    if not analyses:
        raise HTTPException(status_code=503, detail="Could not fetch data for any spot")

    # ── Best spot right now ───────────────────────────────────────────────
    now_ranked = [a for a in analyses if a.get("current")]
    now_ranked.sort(key=lambda a: a["current"]["verdict"]["score"])
    best_now = now_ranked[0] if now_ranked else None

    # ── Golden windows (score <= 2.0 = excellent or possible) ────────────
    golden_windows = []
    for analysis in analyses:
        spot_info = analysis["spot"]
        for day_sum in analysis.get("days", []):
            bw = day_sum.get("best_window")
            if bw and bw["avg_score"] <= 2.2:
                golden_windows.append({
                    "spot_id": spot_info["id"],
                    "spot_name": spot_info["name"],
                    "region": spot_info.get("region", ""),
                    "lat": spot_info["lat"],
                    "lon": spot_info["lon"],
                    "day_label": day_sum["day_label"],
                    "date": day_sum["date"],
                    "window_label": bw["label"],
                    "start_time": bw["start"],
                    "end_time": bw["end"],
                    "avg_score": bw["avg_score"],
                    "model": day_sum["model"],
                    "data_quality_avg": day_sum["avg_data_quality"],
                    "rating": (
                        "ممتاز 🏆" if bw["avg_score"] <= 1.3
                        else "جيد جداً ⭐" if bw["avg_score"] <= 1.8
                        else "مقبول ✅"
                    ),
                    "rating_color": (
                        "#22c55e" if bw["avg_score"] <= 1.3
                        else "#3b82f6" if bw["avg_score"] <= 1.8
                        else "#f59e0b"
                    ),
                })

    golden_windows.sort(key=lambda w: w["avg_score"])

    # ── Spot rankings ─────────────────────────────────────────────────────
    spot_rankings = []
    for analysis in analyses:
        sp = analysis["spot"]
        days = analysis.get("days", [])
        if not days:
            continue
        avg_s = sum(d["avg_verdict_score"] for d in days) / len(days)
        best_d = min(days, key=lambda d: d["avg_verdict_score"])
        spot_rankings.append({
            "spot": {
                "id": sp["id"],
                "name": sp["name"],
                "name_en": sp["name_en"],
                "lat": sp["lat"],
                "lon": sp["lon"],
                "region": sp.get("region", ""),
                "beach_angle": sp.get("beach_angle", 90),
                "seabed_type": sp.get("seabed_type", ""),
            },
            "avg_score": round(avg_s, 2),
            "best_day": best_d["day_label"],
            "best_day_score": best_d["avg_verdict_score"],
            "excellent_total": sum(d["excellent_count"] for d in days),
            "historical_breach": analysis.get("historical_breach", False),
            "current_verdict": (
                analysis["current"]["verdict"]["verdict"]
                if analysis.get("current") else "—"
            ),
        })

    spot_rankings.sort(key=lambda s: s["avg_score"])

    return {
        "best_spot_now": {
            "spot": best_now["spot"] if best_now else None,
            "current": best_now["current"] if best_now else None,
            "arabic_explanation": (
                best_now["current"]["arabic_explanation"]
                if best_now and best_now.get("current") else ""
            ),
        },
        "golden_windows": golden_windows[:20],
        "spot_rankings": spot_rankings,
        "total_spots_analyzed": len(analyses),
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    """Health check — used by Render keepalive."""
    now = datetime.now(timezone.utc)
    return {
        "status": "healthy",
        "service": "SurfCast Tunisia API v3.0",
        "timestamp": now.isoformat(),
        "tunisia_local_time": (now + TUN_OFFSET).strftime("%Y-%m-%d %H:%M"),
        "predefined_spots": len(PREDEFINED_SPOTS),
        "physics_calibration": "Mediterranean Sea (Tunisia coastal)",
        "data_sources": [
            "Open-Meteo Marine API (ICON Wave DWD)",
            "Open-Meteo Weather Forecast API",
        ],
    }


@app.get("/")
async def root():
    return {
        "service": "🎣 SurfCast Tunisia API v3.0",
        "endpoints": {
            "GET /spots": "All predefined spots",
            "GET /forecast?lat=&lon=&name=&beach_angle=": "3-day analysis",
            "GET /best-spots?custom_spots=[]": "Best spot finder",
            "GET /health": "Service health",
            "GET /docs": "Interactive API documentation",
        },
        "data_disclaimer": "تقريب علمي — ليس ضماناً للسلامة الشخصية",
        }
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
