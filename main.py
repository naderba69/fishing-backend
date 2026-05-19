# =============================================================================
# Tunisia Surfcasting Analyzer - Backend API
# =============================================================================
# وصف: نظام ذكي لتحليل ظروف صيد الشاطئ في السواحل التونسية
# الميزات:
#   - قاعدة بيانات مدمجة للشواطئ التونسية مع إحداثيات واتجاهات الواجهات
#   - دمج مزدوج لـ Open-Meteo APIs (Weather + Marine) مع جلب متزامن
#   - منطق صيد ثوري: تصنيف الرياح، مخاطر الطحالب، تيارات السحب، خطر الرياح
#   - مصفوفة قرار نهائية مع شرح نصي واقتراح وزن الرصاص
#   - مكتشف أفضل الشواطئ تلقائياً مع دعم المواقع المخصصة المحفوظة
#   - دعم CORS كامل للتشغيل على منصات Free Tier (Render, Vercel, GitHub Pages)
#   - متوافق مع Pydantic v2 و FastAPI الحديث
# =============================================================================

# ---------------------------------------------
# 1. الاستيرادات والمكتبات
# ---------------------------------------------
import asyncio
import math
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone, timedelta
import logging

# ---------------------------------------------
# 2. إعدادات التسجيل (Logging) للتشخيص
# ---------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("surfcast-api")

# ---------------------------------------------
# 3. تهيئة تطبيق FastAPI
# ---------------------------------------------
app = FastAPI(
    title="Tunisia Surfcasting Analyzer API",
    description="""
    نظام تحليل ذكي لظروف صيد الشاطئ في تونس.
    
    ## الميزات:
    - **تحليل نقطة واحدة**: جلب بيانات الطقس والأمواج وتقييم المخاطر
    - **مكتشف أفضل الشواطئ**: مسح جميع المواقع المبرمجة + المفضلات وترتيبها
    - **منطق صيد متقدم**: تصنيف الرياح، مخاطر الطحالب، تيارات السحب، ضغط جوي    - **توصيات عملية**: وزن الرصاص المقترح بناءً على طاقة الأمواج
    
    ## النهايات المتاحة:
    - `POST /analyze`: تحليل موقع محدد
    - `POST /best-spots`: الحصول على أفضل الشواطئ حالياً
    - `GET /health`: فحص صحة الخدمة
    - `GET /`: معلومات الـ API
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# ---------------------------------------------
# 4. إعدادات CORS (السماح بالاتصال من أي نطاق)
# ---------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # يسمح لـ Vercel، GitHub Pages، localhost، وأي نطاق
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=["*"],  # يسمح بجميع العناوين بما فيها المخصصة
    expose_headers=["*"],
    max_age=3600,  # الاحتفاظ بإعدادات CORS لمدة ساعة لتقليل طلبات OPTIONS
)

# ---------------------------------------------
# 5. قاعدة بيانات الشواطئ التونسية المبرمجة مسبقاً
# ---------------------------------------------
TUNISIAN_SPOTS: List[Dict[str, Union[str, float]]] = [
    {
        "name": "قلعة الأندلس (تونس العاصمة)",
        "lat": 36.9150,
        "lon": 10.1550,
        "facing": "N",
        "region": "تونس",
        "description": "شاطئ رملي واسع، مناسب للصيد الليلي"
    },
    {
        "name": "شاطئ رواد (تونس العاصمة)",
        "lat": 36.9380,
        "lon": 10.2150,
        "facing": "NE",
        "region": "تونس",
        "description": "منطقة هادئة، تيارات معتدلة"
    },
    {
        "name": "الهوارية (نابل)",
        "lat": 37.0500,        "lon": 11.0150,
        "facing": "N",
        "region": "نابل",
        "description": "أحد أفضل مواقع الصيد في الشمال الشرقي"
    },
    {
        "name": "قليبية (نابل)",
        "lat": 36.8500,
        "lon": 11.1000,
        "facing": "E",
        "region": "نابل",
        "description": "شواطئ صخرية ورملية متنوعة"
    },
    {
        "name": "حمام الغزاز (نابل)",
        "lat": 36.8850,
        "lon": 11.1150,
        "facing": "NE",
        "region": "نابل",
        "description": "منطقة محمية، مياه صافية"
    },
    {
        "name": "كاب سيرات (بنزرت)",
        "lat": 37.2300,
        "lon": 9.2100,
        "facing": "NW",
        "region": "بنزرت",
        "description": "رأس صخري، تيارات قوية، للأسماك الكبيرة"
    },
    {
        "name": "سيدي مشرق (بنزرت)",
        "lat": 37.1600,
        "lon": 9.1200,
        "facing": "N",
        "region": "بنزرت",
        "description": "شاطئ رملي طويل، مناسب للمبتدئين"
    },
    {
        "name": "الرمال (بنزرت)",
        "lat": 37.2750,
        "lon": 9.9150,
        "facing": "NW",
        "region": "بنزرت",
        "description": "منطقة شعبية، سهولة الوصول"
    },
    {
        "name": "شط مريم (سوسة)",
        "lat": 35.9350,
        "lon": 10.5600,
        "facing": "E",        "region": "سوسة",
        "description": "منطقة سياحية، بنية تحتية جيدة"
    },
    {
        "name": "هرقلة (سوسة)",
        "lat": 36.0300,
        "lon": 10.5100,
        "facing": "NE",
        "region": "سوسة",
        "description": "شاطئ هادئ، مناسب للصيد العائلي"
    }
]

# ---------------------------------------------
# 6. دوال مساعدة: الجغرافيا والأرصاد البحرية
# ---------------------------------------------

def compass_direction_to_degrees(direction: str) -> float:
    """
    تحويل اتجاه البوصلة (نصّي) إلى درجات رقمية (0-360).
    
    Args:
        direction: نص الاتجاه (N, NE, E, SE, S, SW, W, NW)
    
    Returns:
        float: الدرجة المقابلة (0 للشمال، 90 للشرق، إلخ)
    """
    direction_map: Dict[str, float] = {
        "N": 0.0,
        "NNE": 22.5,
        "NE": 45.0,
        "ENE": 67.5,
        "E": 90.0,
        "ESE": 112.5,
        "SE": 135.0,
        "SSE": 157.5,
        "S": 180.0,
        "SSW": 202.5,
        "SW": 225.0,
        "WSW": 247.5,
        "W": 270.0,
        "WNW": 292.5,
        "NW": 315.0,
        "NNW": 337.5
    }
    return direction_map.get(direction.strip().upper(), 0.0)


def classify_wind_relative_to_beach(
    wind_direction_degrees: float,    beach_facing_direction: str
) -> str:
    """
    تصنيف الرياح نسبة لاتجاه واجهة الشاطئ: Onshore / Offshore / Side-shore.
    
    المنطق:
    - Onshore: رياح تهب من البحر نحو الشاطئ (تزيد الأمواج والطحالب)
    - Offshore: رياح تهب من الشاطئ نحو البحر (تسطح الأمواج، ظروف مثالية)
    - Side-shore: رياح جانبية (تأثير متوسط)
    
    Args:
        wind_direction_degrees: اتجاه الرياح بالدرجات (0-360، من أين تهب)
        beach_facing_direction: اتجاه واجهة الشاطئ (مثل "N", "NE", "E")
    
    Returns:
        str: "Onshore" أو "Offshore" أو "Side-shore"
    """
    beach_degrees: float = compass_direction_to_degrees(beach_facing_direction)
    
    # حساب الفرق الزاوي بين اتجاه الرياح وواجهة الشاطئ
    angle_difference: float = abs(wind_direction_degrees - beach_degrees)
    
    # التعامل مع الدائرية (360 درجة)
    if angle_difference > 180.0:
        angle_difference = 360.0 - angle_difference
    
    # تصنيف بناءً على الزاوية
    if angle_difference <= 45.0:
        return "Onshore"  # رياح مباشرة نحو الشاطئ
    elif angle_difference >= 135.0:
        return "Offshore"  # رياح مباشرة بعيداً عن الشاطئ
    else:
        return "Side-shore"  # رياح جانبية


def estimate_tide_phase_approximate(utc_hour: int, location_lat: float) -> bool:
    """
    تقدير تقريبي لمرحلة المد والجزر للساحل التونسي (بحر متوسطي شبه مغلق).
    
    ملاحظة: البحر المتوسط له مد وجزر ضعيف (30-50 سم)، لكن التيارات المرتبطة
    بالرياح والضغط الجوي تؤثر على حركة المياه القريبة من الشاطئ.
    
    هذه الدالة تستخدم نموذجاً توافقياً مبسطاً لتقدير "نافذة المد المنخفض"
    التي تزيد فيها مخاطر تيارات السحب (Rip Currents) مع الأمواج الطويلة.
    
    Args:
        utc_hour: الساعة الحالية بالتوقيت العالمي المنسق (0-23)
        location_lat: خط العرض للموقع (لتحسين الدقة الإقليمية)
    
    Returns:        bool: True إذا كان الوقت ضمن نافذة "مد منخفض تقريبي"
    """
    # معامل طور إقليمي للساحل التونسي (تعديل زمني بسيط)
    # الساحل الشرقي (تونس، نابل، سوسة): تأخير ~3 ساعات عن المرجع
    # الساحل الشمالي (بنزرت): تأخير ~2 ساعة
    phase_offset: float = 3.0 if location_lat < 37.0 else 2.0
    
    # دورة شبه يومية (Semi-diurnal): ~12.42 ساعة بين مدّين متتاليين
    tidal_cycle_hours: float = 12.42
    
    # حساب الطور الحالي ضمن الدورة
    phase_angle: float = ((utc_hour - phase_offset) % tidal_cycle_hours) / tidal_cycle_hours * 360.0
    
    # نافذة المد المنخفض: ±40 درجة حول 0° و 360° في النموذج التوافقي
    # هذا يعادل ~1.4 ساعة قبل وبعد ذروة المد المنخفض التقريبية
    low_tide_window: float = 40.0
    
    return (phase_angle < low_tide_window) or (phase_angle > (360.0 - low_tide_window))


def find_closest_hourly_index(
    target_datetime: datetime,
    hourly_times_list: List[str]
) -> int:
    """
    إيجاد فهرس العنصر الأقرب زمنياً في مصفوفة البيانات الساعية لـ Open-Meteo.
    
    Args:
        target_datetime: الوقت المستهدف (يفضل أن يكون UTC)
        hourly_times_list: قائمة سلاسل زمنية بصيغة ISO 8601 من Open-Meteo
    
    Returns:
        int: الفهرس (index) للعنصر الأقرب في المصفوفة
    """
    if not hourly_times_list:
        return 0
    
    closest_index: int = 0
    smallest_time_difference: timedelta = timedelta(hours=24)  # حد أقصى للفرق
    
    for idx, time_str in enumerate(hourly_times_list):
        # تحويل السلسلة الزمنية من Open-Meteo (تنتهي بـ "Z") إلى datetime
        try:
            parsed_time: datetime = datetime.fromisoformat(
                time_str.replace("Z", "+00:00")
            )
        except ValueError:
            continue  # تخطي أي تنسيق غير صالح
        
        # حساب الفرق المطلق        current_difference: timedelta = abs(target_datetime - parsed_time)
        
        if current_difference < smallest_time_difference:
            smallest_time_difference = current_difference
            closest_index = idx
    
    return closest_index


def safe_list_get(
    data_list: List[Any],
    index: int,
    default_value: Any = None
) -> Any:
    """
    دالة آمنة لجلب عنصر من قائمة مع قيمة افتراضية في حال تجاوز الفهرس.
    
    تمنع أخطاء IndexError في حال كانت البيانات غير مكتملة من الـ API.
    """
    try:
        return data_list[index] if 0 <= index < len(data_list) else default_value
    except (IndexError, TypeError):
        return default_value


# ---------------------------------------------
# 7. محرك التحليل الذكي: المنطق البحري ومصفوفة المخاطر
# ---------------------------------------------

def execute_fishing_logic_and_risk_matrix(
    latitude: float,
    longitude: float,
    beach_facing_direction: str,
    weather_api_response: Dict[str, Any],
    marine_api_response: Dict[str, Any]
) -> Dict[str, Any]:
    """
    النواة الذكية للتطبيق: تحليل البيانات الخام وإصدار تقييم شامل.
    
    يدمج:
    1. بيانات الرياح (السرعة، الاتجاه) من Weather API
    2. بيانات الأمواج (الارتفاع، الفترة، الاتجاه) من Marine API
    3. بيانات الضغط الجوي (الحالي وقبل 3 ساعات) لحساب الاتجاه الديناميكي
    4. البيانات التاريخية لـ 24 ساعة الماضية لتقييم استمرارية المخاطر
    
    ويعيد:
    - تصنيف المخاطر (طحالب، تيارات سحب، رياح)
    - الحكم النهائي (ممتاز / ممكن / صعب جداً / مستحيل)
    - شرح نصي مفصل للأسباب
    - توصية عملية بوزن الرصاص (سبيكة الرصاص)    
    Args:
        latitude: خط العرض للموقع (درجة عشرية)
        longitude: خط الطول للموقع (درجة عشرية)
        beach_facing_direction: اتجاه واجهة الشاطئ (N, NE, E, etc.)
        weather_api_response: JSON كامل من Open-Meteo Weather API
        marine_api_response: JSON كامل من Open-Meteo Marine API
    
    Returns:
        dict: قاموس يحتوي على جميع نتائج التحليل مُهيأة للواجهة الأمامية
    """
    
    # -----------------------------------------
    # أ. استخراج البيانات من استجابات الـ API
    # -----------------------------------------
    now_utc: datetime = datetime.now(timezone.utc)
    
    # بيانات الطقس (الساعية)
    weather_hourly: Dict[str, Any] = weather_api_response.get("hourly", {})
    weather_times: List[str] = weather_hourly.get("time", [])
    wind_speeds: List[float] = weather_hourly.get("wind_speed_10m", [])  # كم/ساعة
    wind_directions: List[float] = weather_hourly.get("wind_direction_10m", [])  # درجات
    surface_pressures: List[float] = weather_hourly.get("surface_pressure", [])  # هيكتوباسكال
    
    # بيانات الأمواج (الساعية)
    marine_hourly: Dict[str, Any] = marine_api_response.get("hourly", {})
    marine_times: List[str] = marine_hourly.get("time", [])
    swell_heights: List[float] = marine_hourly.get("swell_wave_height", [])  # أمتار
    swell_periods: List[float] = marine_hourly.get("swell_wave_period", [])  # ثوانٍ
    swell_directions: List[float] = marine_hourly.get("swell_wave_direction", [])  # درجات
    
    # -----------------------------------------
    # ب. تحديد الفهرس الزمني الحالي
    # -----------------------------------------
    current_data_index: int = find_closest_hourly_index(now_utc, weather_times)
    
    # -----------------------------------------
    ج. استخراج القيم الحالية (مع قيم افتراضية آمنة)
    # -----------------------------------------
    current_wind_speed_kmh: float = safe_list_get(wind_speeds, current_data_index, 15.0)
    current_wind_direction_deg: float = safe_list_get(wind_directions, current_data_index, 270.0)
    current_pressure_hpa: float = safe_list_get(surface_pressures, current_data_index, 1015.0)
    
    current_swell_height_m: float = safe_list_get(swell_heights, current_data_index, 0.8)
    current_swell_period_s: float = safe_list_get(swell_periods, current_data_index, 8.0)
    current_swell_direction_deg: float = safe_list_get(swell_directions, current_data_index, 0.0)
    
    # -----------------------------------------
    # د. حساب اتجاه الضغط الجوي (3 ساعات ماضية)
    # -----------------------------------------    three_hours_ago_index: int = max(0, current_data_index - 3)
    pressure_3h_ago_hpa: float = safe_list_get(surface_pressures, three_hours_ago_index, current_pressure_hpa)
    pressure_trend_hpa: float = current_pressure_hpa - pressure_3h_ago_hpa
    # موجب = ارتفاع في الضغط (استقرار/هدوء)، سالب = انخفاض (نشاط جوي/زيادة الصيد)
    
    # -----------------------------------------
    # هـ. تصنيف الرياح نسبة للشاطئ
    # -----------------------------------------
    wind_relative_classification: str = classify_wind_relative_to_beach(
        current_wind_direction_deg,
        beach_facing_direction
    )
    
    # -----------------------------------------
    # و. منطق مخاطر الطحالب والحطام البحري (مع استمرارية 24 ساعة)
    # -----------------------------------------
    seaweed_debris_risk: str = "None"
    persistent_seaweed_confirmed: bool = False
    
    # فحص البيانات التاريخية لـ 24 ساعة الماضية
    start_index_24h: int = max(0, current_data_index - 24)
    
    for historical_index in range(start_index_24h, current_data_index):
        # التأكد من وجود بيانات كافية
        if historical_index >= len(swell_heights):
            break
        
        historical_swell_height: float = swell_heights[historical_index]
        
        # شرط التلوث: موجة عالية (>2.0م) مع رياح Onshore تدفع الحطام للشاطئ
        if historical_swell_height > 2.0:
            historical_wind_dir: float = safe_list_get(wind_directions, historical_index, 0.0)
            historical_wind_type: str = classify_wind_relative_to_beach(
                historical_wind_dir,
                beach_facing_direction
            )
            
            if historical_wind_type == "Onshore":
                persistent_seaweed_confirmed = True
                logger.info(
                    f"Persistent seaweed detected at {latitude},{longitude}: "
                    f"swell {historical_swell_height}m + onshore wind at index {historical_index}"
                )
                break  # خروج مبكر عند التأكيد
    
    # تحديد مستوى الخطر النهائي للطحالب
    if persistent_seaweed_confirmed:
        seaweed_debris_risk = "Confirmed/Persistent"
    elif current_swell_height_m < 0.4 or wind_relative_classification == "Offshore":
        seaweed_debris_risk = "None"    elif (0.4 <= current_swell_height_m <= 1.0) and (wind_relative_classification == "Side-shore"):
        seaweed_debris_risk = "Low"
    elif (1.0 < current_swell_height_m <= 1.8) and (wind_relative_classification == "Onshore"):
        seaweed_debris_risk = "High"
    else:
        # الحالة الافتراضية الآمنة
        seaweed_debris_risk = "Low"
    
    # -----------------------------------------
    # ز. منطق مخاطر تيارات السحب (Rip Currents)
    # -----------------------------------------
    is_approximate_low_tide: bool = estimate_tide_phase_approximate(
        now_utc.hour,
        latitude
    )
    
    if current_swell_period_s >= 14.0 and is_approximate_low_tide:
        rip_currents_risk: str = "Confirmed"
    elif 10.0 <= current_swell_period_s < 14.0:
        rip_currents_risk: str = "High"
    else:
        rip_currents_risk: str = "Low"
    
    # -----------------------------------------
    # ح. منطق خطر الرياح (للسلامة الشخصية)
    # -----------------------------------------
    if current_wind_speed_kmh < 10.0:
        wind_danger_risk: str = "None"
    elif 10.0 <= current_wind_speed_kmh <= 25.0:
        wind_danger_risk: str = "Low"
    elif 26.0 <= current_wind_speed_kmh <= 45.0:
        wind_danger_risk: str = "High"
    else:  # > 45 km/h
        wind_danger_risk: str = "Confirmed"
    
    # -----------------------------------------
    # ط. مصفوفة القرار النهائية (Ultimate Verdict Matrix)
    # -----------------------------------------
    # نظام النقاط: كل خطر يُضيف أو يُخصم من الدرجة الكلية (0-45)
    total_score: int = 0
    
    # نقاط المخاطر الثلاثة الرئيسية
    risk_score_map: Dict[str, int] = {
        "None": 10,
        "Low": 5,
        "High": 2,
        "Confirmed": -5,
        "Confirmed/Persistent": -5
    }
        total_score += risk_score_map.get(seaweed_debris_risk, 0)
    total_score += risk_score_map.get(rip_currents_risk, 0)
    total_score += risk_score_map.get(wind_danger_risk, 0)
    
    # مكافأة/عقوبة ارتفاع الأمواج
    if 0.5 <= current_swell_height_m <= 1.2:
        total_score += 10  # النطاق المثالي للصيد الشاطئي
    elif current_swell_height_m > 1.8:
        total_score -= 15  # أمواج عاتية تعيق الصيد وتزيد الخطر
    
    # مكافأة/عقوبة اتجاه الضغط الجوي
    if -2.0 <= pressure_trend_hpa <= -1.0:
        total_score += 10  # انخفاض بطيء = نشاط الأسماك (تغذية)
    elif pressure_trend_hpa > 2.0:
        total_score -= 10  # ارتفاع سريع = استقرار مفرط / خمول
    
    # ضمان أن النتيجة ضمن النطاق المحدد
    total_score = max(0, min(45, total_score))
    
    # -----------------------------------------
    # ي. تحديد الحكم النهائي والشرح
    # -----------------------------------------
    final_verdict: str
    verdict_explanation: str
    
    if (
        total_score >= 35 and
        seaweed_debris_risk == "None" and
        wind_danger_risk in ["None", "Low"] and
        rip_currents_risk in ["Low"]
    ):
        final_verdict = "ممتاز"
        verdict_explanation = (
            f"ظروف ممتازة للصيد: ارتفاع موج مثالي ({current_swell_height_m:.1f}م)، "
            f"رياح {wind_relative_classification.lower()} خفيفة، "
            f"وانخفاض ضغط جوي بطيء ({pressure_trend_hpa:+.1f} هكتوباسكال) "
            f"ينشط حركة الأسماك القريبة من الشاطئ. "
            f"المخاطر البحرية تحت السيطرة التامة."
        )
    elif (
        total_score >= 20 and
        "Confirmed" not in [seaweed_debris_risk, wind_danger_risk]
    ):
        final_verdict = "ممكن"
        verdict_explanation = (
            f"ظروف مقبولة للصيد مع بعض التحديات: "
            f"موجة {current_swell_height_m:.1f}م ورياح {wind_relative_classification}. "
            f"يُنصح باستخدام معدات أثقل قليلاً، والانتباه للتيارات الجانبية. "
            f"الوقت المناسب: الصباح الباكر أو المساء."
        )    elif total_score >= 5:
        final_verdict = "صعب جداً"
        verdict_explanation = (
            f"ظروف قاسية تتطلب خبرة عالية: "
            f"{'أمواج عاتية' if current_swell_height_m > 1.5 else 'رياح شديدة' if current_wind_speed_kmh > 30 else 'تراكم طحالب'} "
            f"مع {wind_relative_classification} winds. "
            f"استخدم تجهيزات ثقيلة (رصاص +80غ)، وابقَ قريباً من الشاطئ. "
            f"المبتدئون: يُفضل تأجيل الرحلة."
        )
    else:
        final_verdict = "مستحيل"
        verdict_explanation = (
            f"الظروف خطرة وغير مناسبة للصيد إطلاقاً: "
            f"{'أمواج عاتية جداً' if current_swell_height_m > 2.0 else 'عاصفة رياح' if current_wind_speed_kmh > 45 else 'تلوث بحري مؤكد'} "
            f"مع مخاطر عالية للتيارات. "
            f"سلامتك أولاً: لا تنزل للشاطئ تحت أي ظرف. "
            f"انتظر تحسن الأحوال لمدة 6-12 ساعة قادمة."
        )
    
    # -----------------------------------------
    # ك. حساب وزن الرصاص المقترح (Sinker Weight Logic)
    # -----------------------------------------
    # المعادلة: وزن أساسي + تعديلات حسب طاقة الموج والرياح والتيارات
    base_sinker_weight_grams: int = 50
    
    # زيادة الوزن مع ارتفاع الموج (كل 1م موج = +40غ رصاص)
    wave_energy_adjustment: float = current_swell_height_m * 40.0
    
    # زيادة الوزن مع سرعة الرياح (كل 1 كم/س = +0.8غ)
    wind_drag_adjustment: float = current_wind_speed_kmh * 0.8
    
    # زيادة إضافية للرياح Onshore (تدفع الطعم بعيداً)
    onshore_penalty: int = 20 if wind_relative_classification == "Onshore" else 0
    
    # زيادة إضافية لتيارات السحب العالية (تتطلب تثبيتاً أقوى)
    rip_current_penalty: int = 30 if rip_currents_risk == "High" else 0
    
    # الحساب النهائي مع حدود دنيا وعليا آمنة
    calculated_sinker_weight: float = (
        base_sinker_weight_grams +
        wave_energy_adjustment +
        wind_drag_adjustment +
        onshore_penalty +
        rip_current_penalty
    )
    
    recommended_sinker_weight_grams: int = int(
        min(300, max(30, calculated_sinker_weight))  # حدود 30-300 غرام
    )
        # -----------------------------------------
    # ل. تجميع نتيجة التحليل النهائية
    # -----------------------------------------
    analysis_result: Dict[str, Any] = {
        "location": {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "beach_facing_direction": beach_facing_direction
        },
        "current_conditions": {
            "wind_speed_kmh": round(current_wind_speed_kmh, 1),
            "wind_direction_degrees": round(current_wind_direction_deg, 1),
            "wind_relative_to_beach": wind_relative_classification,
            "swell_height_meters": round(current_swell_height_m, 2),
            "swell_period_seconds": round(current_swell_period_s, 1),
            "swell_direction_degrees": round(current_swell_direction_deg, 1),
            "surface_pressure_hpa": round(current_pressure_hpa, 2),
            "pressure_trend_3h_hpa": round(pressure_trend_hpa, 2),
            "pressure_trend_description": "dropping" if pressure_trend_hpa < 0 else "rising",
            "approximate_low_tide_window": is_approximate_low_tide,
            "analysis_timestamp_utc": now_utc.isoformat()
        },
        "risk_assessment": {
            "seaweed_and_debris": {
                "level": seaweed_debris_risk,
                "persistent_24h_detected": persistent_seaweed_confirmed,
                "message_ar": (
                    "البحر مخربض بسبب مخلفات الـ 24 ساعة الماضية"
                    if persistent_seaweed_confirmed else ""
                )
            },
            "rip_currents": {
                "level": rip_currents_risk,
                "contributing_factors": {
                    "long_period_swell": current_swell_period_s >= 10.0,
                    "low_tide_phase": is_approximate_low_tide
                }
            },
            "wind_danger": {
                "level": wind_danger_risk,
                "safety_note": (
                    "ارتدِ سترة نجاة وابقَ ضمن منطقة آمنة"
                    if wind_danger_risk in ["High", "Confirmed"] else ""
                )
            }
        },
        "ultimate_verdict": {
            "status": final_verdict,
            "score": total_score,
            "score_max": 45,            "explanation_ar": verdict_explanation,
            "recommended_sinker_weight_grams": recommended_sinker_weight_grams,
            "sinker_weight_note": (
                f"استخدم رصاص {recommended_sinker_weight_grams}غ لتثبيت الطعم في الظروف الحالية"
            )
        },
        "metadata": {
            "api_version": "1.0.0",
            "data_sources": ["Open-Meteo Weather API", "Open-Meteo Marine API"],
            "historical_window_hours": 24,
            "update_frequency": "hourly"
        }
    }
    
    return analysis_result


# ---------------------------------------------
# 8. نماذج طلبات الـ API (Pydantic v2)
# ---------------------------------------------

class AnalyzeLocationRequest(BaseModel):
    """
    نموذج طلب تحليل موقع محدد.
    
    يستخدم في نقطة النهاية /analyze
    """
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="خط العرض بالدرجات العشرية (مثال: 36.8500)"
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="خط الطول بالدرجات العشرية (مثال: 11.1000)"
    )
    beach_direction: str = Field(
        ...,
        pattern=r"^(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)$",
        description="اتجاه واجهة الشاطئ (مثال: 'N' للشمال، 'NE' للشمال الشرقي)"
    )
    
    @field_validator('beach_direction')
    @classmethod
    def normalize_direction(cls, v: str) -> str:
        """تطبيع اتجاه البوصلة لأحرف كبيرة"""
        return v.strip().upper()

class CustomSpotRequest(BaseModel):
    """
    نموذج موقع مخصص (للمفضلات التي يحفظها المستخدم).
    
    يستخدم في نقطة النهاية /best-spots
    """
    name: str = Field(..., min_length=1, max_length=100, description="اسم الموقع المفضل")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="خط العرض")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="خط الطول")
    facing_direction: str = Field(
        ...,
        pattern=r"^(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)$",
        description="اتجاه واجهة الشاطئ"
    )
    
    @field_validator('facing_direction')
    @classmethod
    def normalize_facing(cls, v: str) -> str:
        return v.strip().upper()


# ---------------------------------------------
# 9. نقاط النهاية للـ API (Endpoints)
# ---------------------------------------------

@app.get("/", tags=["معلومات"])
async def api_root_information() -> Dict[str, str]:
    """
    نقطة بداية الـ API: تعرض حالة الخدمة ومعلومات أساسية.
    
    مفيدة لفحص الاتصال والتكامل مع الواجهة الأمامية.
    """
    return {
        "service": "Tunisia Surfcasting Analyzer API",
        "version": "1.0.0",
        "status": "online",
        "documentation": "/docs",
        "health_check": "/health",
        "endpoints": {
            "analyze_single_location": "POST /analyze",
            "find_best_spots": "POST /best-spots"
        }
    }


@app.get("/health", tags=["صحة النظام"])
async def health_check_endpoint(request: Request) -> JSONResponse:
    """    فحص صحة الخدمة: يعود بـ 200 إذا كان كل شيء يعمل.
    
    تستخدمها منصات الاستضافة (Render, Vercel) لمراقبة توفر الخدمة.
    """
    return JSONResponse(
        status_code=200,
        content={
            "healthy": True,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "server_time_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "request_id": request.headers.get("x-request-id", "unknown")
        }
    )


@app.post("/analyze", tags=["تحليل"], response_model=Dict[str, Any])
async def analyze_single_location_endpoint(
    request: AnalyzeLocationRequest
) -> Dict[str, Any]:
    """
    تحليل ظروف الصيد لموقع محدد بناءً على إحداثياته واتجاه شاطئه.
    
    ## العملية:
    1. جلب بيانات الطقس من Open-Meteo Weather API
    2. جلب بيانات الأمواج من Open-Meteo Marine API (بالتوازي)
    3. تطبيق منطق التحليل الذكي (المخاطر + مصفوفة القرار)
    4. إعادة النتيجة مُهيأة للعرض في الواجهة الأمامية
    
    ## مثال طلب:
```json
    {
        "latitude": 36.8500,
        "longitude": 11.1000,
        "beach_direction": "E"
    }
```
    """
    logger.info(f"Analyze request received: lat={request.latitude}, lon={request.longitude}, dir={request.beach_direction}")
    
    # إنشاء عميل HTTP غير متزامن مع مهلة زمنية مناسبة للباقة المجانية
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http_client:
        
        # بناء روابط الـ API مع المعلمات المطلوبة
        weather_api_url: str = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={request.latitude}"
            f"&longitude={request.longitude}"
            f"&hourly=wind_speed_10m,wind_direction_10m,surface_pressure"
            f"&past_days=1"  # بيانات 24 ساعة ماضية للمخاطر المستمرة
            f"&timezone=auto"  # ضبط تلقائي للمنطقة الزمنية        )
        
        marine_api_url: str = (
            "https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={request.latitude}"
            f"&longitude={request.longitude}"
            f"&hourly=swell_wave_height,swell_wave_period,swell_wave_direction"
            f"&past_days=1"
            f"&timezone=auto"
        )
        
        try:
            # جلب البيانات من المصدرين **بالتوازي** لتقليل زمن الاستجابة
            weather_response_task = http_client.get(weather_api_url)
            marine_response_task = http_client.get(marine_api_url)
            
            weather_response, marine_response = await asyncio.gather(
                weather_response_task,
                marine_response_task
            )
            
            # التحقق من نجاح الطلبات
            weather_response.raise_for_status()
            marine_response.raise_for_status()
            
            # تحويل الاستجابات إلى قاموس (JSON)
            weather_data: Dict[str, Any] = weather_response.json()
            marine_data: Dict[str, Any] = marine_response.json()
            
        except httpx.TimeoutException as timeout_err:
            logger.error(f"Timeout fetching Open-Meteo data: {timeout_err}")
            raise HTTPException(
                status_code=504,
                detail="مهلة الاتصال بخدمات الأرصاد انتهت. حاول مرة أخرى خلال دقيقة."
            )
        except httpx.HTTPStatusError as http_err:
            logger.error(f"HTTP error from Open-Meteo: {http_err.response.status_code}")
            raise HTTPException(
                status_code=502,
                detail=f"خطأ في الخادم الخارجي: {http_err.response.status_code}"
            )
        except httpx.RequestError as req_err:
            logger.error(f"Network error: {req_err}")
            raise HTTPException(
                status_code=503,
                detail="تعذر الاتصال بخدمة الأرصاد. تحقق من اتصالك بالإنترنت."
            )
        except Exception as unexpected_err:
            logger.error(f"Unexpected error: {unexpected_err}", exc_info=True)
            raise HTTPException(                status_code=500,
                detail="حدث خطأ غير متوقع أثناء معالجة الطلب."
            )
    
    # تنفيذ محرك التحليل الذكي
    analysis_result: Dict[str, Any] = execute_fishing_logic_and_risk_matrix(
        latitude=request.latitude,
        longitude=request.longitude,
        beach_facing_direction=request.beach_direction,
        weather_api_response=weather_data,
        marine_api_response=marine_data
    )
    
    # إضافة اسم الموقع للنتيجة (للعرض في الواجهة)
    analysis_result["location_name"] = "موقع مخصص"
    
    logger.info(f"Analysis completed successfully for {request.latitude},{request.longitude}")
    return analysis_result


@app.post("/best-spots", tags=["اكتشاف"], response_model=List[Dict[str, Any]])
async def find_best_fishing_spots_endpoint(
    custom_user_spots: List[CustomSpotRequest]
) -> List[Dict[str, Any]]:
    """
    مسح وتقييم جميع الشواطئ المتاحة (المبرمجة + المفضلات الشخصية)
    وإرجاعها مرتبة من الأفضل للأسوأ حسب ظروف الصيد الحالية.
    
    ## العملية:
    1. دمج قائمة الشواطئ المبرمجة مع القائمة المرسلة من المستخدم
    2. جلب وتحليل بيانات كل موقع (بالتسلسل لتجنب إجهاد الـ API المجاني)
    3. حساب "درجة الجاذبية" لكل موقع بناءً على مصفوفة القرار
    4. ترتيب النتائج تنازلياً حسب الدرجة
    
    ## مثال طلب (مصفوفة المواقع المخصصة):
```json
    [
        {
            "name": "موقعي السري",
            "latitude": 36.9000,
            "longitude": 10.2000,
            "facing_direction": "NE"
        }
    ]
```
    """
    logger.info(f"Best-spots request: {len(custom_user_spots)} custom spots provided")
    
    # دمج الشواطئ المبرمجة مع المفضلات الشخصية
    all_spots_to_evaluate: List[Dict[str, Any]] = []    
    # إضافة الشواطئ المبرمجة مسبقاً
    for spot in TUNISIAN_SPOTS:
        all_spots_to_evaluate.append({
            "name": spot["name"],
            "latitude": spot["lat"],
            "longitude": spot["lon"],
            "facing_direction": spot["facing"],
            "region": spot.get("region", "غير محدد"),
            "is_preset": True
        })
    
    # إضافة المواقع المخصصة من المستخدم (المفضلات)
    for custom_spot in custom_user_spots:
        all_spots_to_evaluate.append({
            "name": custom_spot.name,
            "latitude": custom_spot.latitude,
            "longitude": custom_spot.longitude,
            "facing_direction": custom_spot.facing_direction,
            "region": "مفضل شخصي",
            "is_preset": False
        })
    
    logger.info(f"Total spots to evaluate: {len(all_spots_to_evaluate)}")
    
    # قائمة لتخزين النتائج
    evaluation_results: List[Dict[str, Any]] = []
    
    # عميل HTTP مشترك لجميع الطلبات (كفاءة في الموارد)
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http_client:
        
        for spot in all_spots_to_evaluate:
            try:
                # بناء روابط الـ API لهذا الموقع
                w_url = (
                    f"https://api.open-meteo.com/v1/forecast"
                    f"?latitude={spot['latitude']}"
                    f"&longitude={spot['longitude']}"
                    f"&hourly=wind_speed_10m,wind_direction_10m,surface_pressure"
                    f"&past_days=1&timezone=auto"
                )
                m_url = (
                    f"https://marine-api.open-meteo.com/v1/marine"
                    f"?latitude={spot['latitude']}"
                    f"&longitude={spot['longitude']}"
                    f"&hourly=swell_wave_height,swell_wave_period,swell_wave_direction"
                    f"&past_days=1&timezone=auto"
                )
                
                # جلب البيانات (بالتسلسل لتجنب Rate Limiting في الباقة المجانية)                w_resp = await http_client.get(w_url)
                m_resp = await http_client.get(m_url)
                
                w_resp.raise_for_status()
                m_resp.raise_for_status()
                
                # تحليل الموقع
                spot_analysis = execute_fishing_logic_and_risk_matrix(
                    latitude=spot["latitude"],
                    longitude=spot["longitude"],
                    beach_facing_direction=spot["facing_direction"],
                    weather_api_response=w_resp.json(),
                    marine_api_response=m_resp.json()
                )
                
                # إثراء النتيجة بمعلومات الموقع
                spot_analysis["location_name"] = spot["name"]
                spot_analysis["region"] = spot["region"]
                spot_analysis["is_preset_spot"] = spot["is_preset"]
                
                evaluation_results.append(spot_analysis)
                
                # تأخير بسيط بين الطلبات لتجنب الحظر (احتراماً لـ Free Tier)
                await asyncio.sleep(0.3)
                
            except Exception as spot_error:
                logger.warning(f"Failed to evaluate spot '{spot['name']}': {spot_error}")
                # تخطي الموقع الفاشل والاستمرار في البقية
                continue
    
    # -----------------------------------------
    # ترتيب النتائج: الأفضل (أعلى درجة) أولاً
    # -----------------------------------------
    evaluation_results.sort(
        key=lambda result: result["ultimate_verdict"]["score"],
        reverse=True  # تنازلي: 45 (ممتاز) → 0 (مستحيل)
    )
    
    # إضافة ترتيب رقمي للعرض
    for rank, result in enumerate(evaluation_results, start=1):
        result["ranking"] = rank
        result["total_evaluated"] = len(evaluation_results)
    
    logger.info(f"Best-spots evaluation completed: {len(evaluation_results)} spots ranked")
    return evaluation_results


# ---------------------------------------------
# 10. معالجة الأخطاء العامة (Global Exception Handler)
# ---------------------------------------------@app.exception_handler(HTTPException)
async def custom_http_exception_handler(
    request: Request,
    exc: HTTPException
) -> JSONResponse:
    """
    معالجة موحدة لأخطاء HTTP مع رسائل واضحة بالعربية.
    """
    error_messages_ar: Dict[int, str] = {
        400: "طلب غير صالح: تحقق من البيانات المرسلة.",
        404: "الموقع أو الخدمة غير موجودة.",
        422: "بيانات غير مكتملة أو بتنسيق خاطئ.",
        429: "تجاوزت حد الطلبات المسموح. انتظر دقيقة وحاول مجدداً.",
        500: "خطأ داخلي في الخادم. جرب مرة أخرى لاحقاً.",
        502: "مشكلة في الاتصال بخدمة الأرصاد الخارجية.",
        503: "الخدمة غير متاحة مؤقتاً للصيانة.",
        504: "انتهت مهلة الاتصال. الشبكة بطيئة أو الخادم مشغول."
    }
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": exc.status_code,
            "message_ar": error_messages_ar.get(exc.status_code, "حدث خطأ غير متوقع."),
            "message_en": exc.detail,
            "request_path": request.url.path,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


# ---------------------------------------------
# 11. نقطة الدخول للتشغيل المحلي (للتطوير فقط)
# ---------------------------------------------
# ملاحظة: منصات الاستضافة السحابية (Render, Vercel) تتجاهل هذا الجزء
# وتعتمد على متغير Start Command في إعدادات المشروع.

if __name__ == "__main__":
    import uvicorn
    
    # إعدادات التشغيل المحلي
    # --reload: لإعادة التحميل التلقائي عند تعديل الكود (للتطوير فقط)
    # --host 0.0.0.0: للسماح بالاتصال من أي جهاز على الشبكة المحلية
    # --port 8000: المنفذ الافتراضي (يمكن تغييره عبر متغير البيئة PORT)
    
    import os
    server_port: int = int(os.getenv("PORT", 8000))
    
    logger.info(f"Starting local server on port {server_port}...")    
    uvicorn.run(
        "main:app",  # "اسم_الملف:اسم_التطبيق"
        host="0.0.0.0",
        port=server_port,
        reload=False,  # عطله في الإنتاج لتوفير الموارد
        log_level="info",
        access_log=True
)
