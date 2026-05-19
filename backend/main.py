# =============================================================================
# Tunisia Surfcasting Analyzer - Backend API v1.0.0
# =============================================================================
# نظام تحليل ذكي لظروف صيد الشاطئ في السواحل التونسية
# مطابق 100% للمواصفات المطلوبة: منطق 24 ساعة، مصفوفة المخاطر، الضغط الديناميكي،
# التيارات، وزن الرصاص، جلب مزدوج متزامن، ودعم المواقع المخصصة.
# =============================================================================

import asyncio
import logging
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

# ---------------------------------------------
# إعدادات التسجيل (Logging)
# ---------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("surfcast-api")

# ---------------------------------------------
# تهيئة تطبيق FastAPI
# ---------------------------------------------
app = FastAPI(
    title="Tunisia Surfcasting Analyzer API",
    description="Smart marine weather analysis for Tunisian surfcasting anglers",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ---------------------------------------------
# إعدادات CORS الكاملة
# ---------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600)

# ---------------------------------------------
# 1. قاعدة بيانات الشواطئ التونسية المبرمجة مسبقاً
# ---------------------------------------------
TUNISIAN_SPOTS: List[Dict[str, Any]] = [
    {"name": "قلعة الأندلس (تونس العاصمة)", "lat": 36.9150, "lon": 10.1550, "facing": "N"},
    {"name": "شاطئ رواد (تونس العاصمة)", "lat": 36.9380, "lon": 10.2150, "facing": "NE"},
    {"name": "الهوارية (نابل)", "lat": 37.0500, "lon": 11.0150, "facing": "N"},
    {"name": "قليبية (نابل)", "lat": 36.8500, "lon": 11.1000, "facing": "E"},
    {"name": "حمام الغزاز (نابل)", "lat": 36.8850, "lon": 11.1150, "facing": "NE"},
    {"name": "كاب سيرات (بنزرت)", "lat": 37.2300, "lon": 9.2100, "facing": "NW"},
    {"name": "سيدي مشرق (بنزرت)", "lat": 37.1600, "lon": 9.1200, "facing": "N"},
    {"name": "الرمال (بنزرت)", "lat": 37.2750, "lon": 9.9150, "facing": "NW"},
    {"name": "شط مريم (سوسة)", "lat": 35.9350, "lon": 10.5600, "facing": "E"},
    {"name": "هرقلة (سوسة)", "lat": 36.0300, "lon": 10.5100, "facing": "NE"}
]

# ---------------------------------------------
# دوال مساعدة: الجغرافيا والأرصاد البحرية
# ---------------------------------------------
def dir_to_deg(d: str) -> float:
    """تحويل اتجاه البوصلة إلى درجات رقمية (0-360)"""
    direction_map = {
        "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5, "E": 90.0, "ESE": 112.5,
        "SE": 135.0, "SSE": 157.5, "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
        "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5
    }
    return direction_map.get(d.strip().upper(), 0.0)


def classify_wind(wind_deg: float, beach_dir: str) -> str:
    """
    تصنيف الرياح نسبة لاتجاه واجهة الشاطئ:
    - Onshore: رياح تهب من البحر نحو الشاطئ
    - Offshore: رياح تهب من الشاطئ نحو البحر
    - Side-shore: رياح جانبية
    """
    beach_deg = dir_to_deg(beach_dir)
    diff = abs(wind_deg - beach_deg)
    if diff > 180.0:
        diff = 360.0 - diff
    
    if diff <= 45.0:
        return "Onshore"
    elif diff >= 135.0:
        return "Offshore"
    else:
        return "Side-shore"

def is_low_tide_approx(utc_hour: int, lat: float) -> bool:
    """
    تقدير تقريبي لمرحلة المد المنخفض للساحل التونسي.
    يستخدم نموذجاً توافقياً مبسطاً لدورة شبه يومية (~12.42 ساعة).
    """
    phase_offset = 3.0 if lat < 37.0 else 2.0
    tidal_cycle = 12.42
    phase_angle = ((utc_hour - phase_offset) % tidal_cycle) / tidal_cycle * 360.0
    low_tide_window = 40.0
    return (phase_angle < low_tide_window) or (phase_angle > (360.0 - low_tide_window))


def get_current_utc_index(times_list: List[str]) -> int:
    """إيجاد الفهرس الأقرب للوقت الحالي UTC في مصفوفة البيانات الساعية"""
    if not times_list:
        return 0
    now = datetime.now(timezone.utc)
    closest_idx = 0
    min_diff = timedelta(hours=24)
    
    for i, t_str in enumerate(times_list):
        try:
            parsed_time = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
            diff = abs(now - parsed_time)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i
        except ValueError:
            continue
    return closest_idx


def safe_list_get(data_list: List[Any], index: int, default_value: Any = None) -> Any:
    """جلب آمن من القائمة مع قيمة افتراضية لتجنب IndexError"""
    try:
        return data_list[index] if 0 <= index < len(data_list) else default_value
    except (IndexError, TypeError):
        return default_value


# ---------------------------------------------
# 2. محرك التحليل الذكي ومصفوفة المخاطر (REVOLUTIONARY FISHING LOGIC)
# ---------------------------------------------
def analyze_single_spot(lat: float, lon: float, beach_dir: str, weather_data: Dict, marine_data: Dict) -> Dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    
    # استخراج المصفوفات من استجابات الـ API
    w_hourly = weather_data.get("hourly", {})
    m_hourly = marine_data.get("hourly", {})    
    w_times = w_hourly.get("time", [])
    current_idx = get_current_utc_index(w_times)
    
    # القيم الحالية
    wind_spd = safe_list_get(w_hourly.get("wind_speed_10m", []), current_idx, 15.0)
    wind_dir = safe_list_get(w_hourly.get("wind_direction_10m", []), current_idx, 270.0)
    current_pres = safe_list_get(w_hourly.get("surface_pressure", []), current_idx, 1015.0)
    
    swell_h = safe_list_get(m_hourly.get("swell_wave_height", []), current_idx, 0.8)
    swell_p = safe_list_get(m_hourly.get("swell_wave_period", []), current_idx, 8.0)
    swell_dir = safe_list_get(m_hourly.get("swell_wave_direction", []), current_idx, 0.0)
    
    # اتجاه الضغط الجوي قبل 3 ساعات (Dynamic Pressure Trend)
    idx_3h_ago = max(0, current_idx - 3)
    pres_3h_ago = safe_list_get(w_hourly.get("surface_pressure", []), idx_3h_ago, current_pres)
    pres_trend = current_pres - pres_3h_ago  # سالب = انخفاض، موجب = ارتفاع
    
    wind_type = classify_wind(wind_dir, beach_dir)
    
    # -----------------------------------------
    # منطق الطحالب والحطام البحري (Persistent 24H Logic)
    # -----------------------------------------
    persistent_seaweed = False
    start_idx_24h = max(0, current_idx - 24)
    
    for i in range(start_idx_24h, current_idx):
        if i >= len(m_hourly.get("swell_wave_height", [])):
            break
        hist_swell = m_hourly["swell_wave_height"][i]
        if hist_swell > 2.0:
            hist_wind_dir = safe_list_get(w_hourly.get("wind_direction_10m", []), i, 0.0)
            if classify_wind(hist_wind_dir, beach_dir) == "Onshore":
                persistent_seaweed = True
                break
    
    if persistent_seaweed:
        seaweed_risk = "Confirmed/Persistent"
    elif swell_h < 0.4 or wind_type == "Offshore":
        seaweed_risk = "None"
    elif 0.4 <= swell_h <= 1.0 and wind_type == "Side-shore":
        seaweed_risk = "Low"
    elif 1.0 < swell_h <= 1.8 and wind_type == "Onshore":
        seaweed_risk = "High"
    else:
        seaweed_risk = "Low"
    
    # -----------------------------------------
    # منطق تيارات السحب (Rip Currents Risk)
    # -----------------------------------------    is_low_tide = is_low_tide_approx(now_utc.hour, lat)
    if swell_p >= 14.0 and is_low_tide:
        rip_risk = "Confirmed"
    elif 10.0 <= swell_p < 14.0:
        rip_risk = "High"
    else:
        rip_risk = "Low"
    
    # -----------------------------------------
    # منطق خطر الرياح (Wind Danger)
    # -----------------------------------------
    if wind_spd < 10.0:
        wind_risk = "None"
    elif 10.0 <= wind_spd <= 25.0:
        wind_risk = "Low"
    elif 26.0 <= wind_spd <= 45.0:
        wind_risk = "High"
    else:
        wind_risk = "Confirmed"
    
    # -----------------------------------------
    # مصفوفة القرار النهائية (Ultimate Verdict Matrix)
    # -----------------------------------------
    score = 0
    risk_map = {"None": 10, "Low": 5, "High": 2, "Confirmed": -5, "Confirmed/Persistent": -5}
    score += risk_map.get(seaweed_risk, 0)
    score += risk_map.get(rip_risk, 0)
    score += risk_map.get(wind_risk, 0)
    
    if 0.5 <= swell_h <= 1.2:
        score += 10
    elif swell_h > 1.8:
        score -= 15
    
    if -2.0 <= pres_trend <= -1.0:
        score += 10
    elif pres_trend > 2.0:
        score -= 10
    
    score = max(0, min(45, score))
    
    if score >= 35 and seaweed_risk == "None" and wind_risk in ["None", "Low"] and rip_risk in ["Low"]:
        verdict = "ممتاز"
        explanation = "ظروف ممتازة: موج مناسب (0.5-1.2م)، رياح خفيفة، وانخفاض ضغط بطيء (1-2 hPa) ينشط الأسماك. التيارات والطحالب تحت السيطرة."
    elif score >= 20 and "Confirmed" not in [seaweed_risk, wind_risk]:
        verdict = "ممكن"
        explanation = "ظروف مقبولة للصيد مع بعض التحديات. استخدم معدات أثقل قليلاً وراقب التيارات الجانبية."
    elif score >= 5:
        verdict = "صعب جداً"
        explanation = "ظروف قاسية: أمواج عاتية أو رياح شديدة أو طحالب متراكمة. يتطلب خبرة عالية وتجهيزات ثقيلة."    else:
        verdict = "مستحيل"
        explanation = "الظروف خطرة: أمواج عاتية جداً مع رياح عاتية أو مخلفات طحالب مؤكدة. لا يُنصح بالنزول للشاطئ إطلاقاً."
    
    # -----------------------------------------
    # حساب وزن الرصاص المقترح (Sinker Weight Logic)
    # -----------------------------------------
    base_weight = 50.0
    weight = base_weight + (swell_h * 40.0) + (wind_spd * 0.8)
    if wind_type == "Onshore":
        weight += 20.0
    if rip_risk == "High":
        weight += 30.0
    sinker_g = int(min(300, max(30, weight)))
    
    return {
        "location": {"lat": round(lat, 4), "lon": round(lon, 4), "facing": beach_dir},
        "conditions": {
            "wind_speed_kmh": round(wind_spd, 1),
            "wind_type": wind_type,
            "swell_height_m": round(swell_h, 2),
            "swell_period_s": round(swell_p, 1),
            "pressure_trend_hpa": round(pres_trend, 2),
            "is_low_tide": is_low_tide
        },
        "risks": {
            "seaweed_debris": seaweed_risk,
            "rip_currents": rip_risk,
            "wind_danger": wind_risk
        },
        "verdict": {
            "status": verdict,
            "score": score,
            "explanation": explanation,
            "sinker_weight_g": sinker_g
        }
    }


# ---------------------------------------------
# 3. نماذج البيانات (Pydantic v2)
# ---------------------------------------------
class AnalyzeRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    beach_direction: str = Field(..., pattern=r"^(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)$")
    
    @field_validator('beach_direction')
    @classmethod
    def normalize_dir(cls, v: str) -> str:        return v.strip().upper()


class BatchSpot(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    facing: str = Field(..., pattern=r"^(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)$")
    
    @field_validator('facing')
    @classmethod
    def normalize_facing(cls, v: str) -> str:
        return v.strip().upper()


# ---------------------------------------------
# 4. نقاط النهاية (API Endpoints)
# ---------------------------------------------
@app.get("/", tags=["Info"])
async def root_info():
    return {
        "service": "Tunisia Surfcasting Analyzer API",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
async def health_check(req: Request):
    return JSONResponse({
        "healthy": True,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "request_id": req.headers.get("x-request-id", "unknown")
    })


@app.post("/analyze", tags=["Analysis"])
async def analyze_spot(req: AnalyzeRequest):
    """تحليل نقطة واحدة مع جلب متزامن للطقس والأمواج"""
    logger.info(f"Analyze request: lat={req.lat}, lon={req.lon}, dir={req.beach_direction}")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={req.lat}&longitude={req.lon}"
            f"&hourly=wind_speed_10m,wind_direction_10m,surface_pressure"
            f"&past_days=1&timezone=auto"
        )
        marine_url = (            f"https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={req.lat}&longitude={req.lon}"
            f"&hourly=swell_wave_height,swell_wave_period,swell_wave_direction"
            f"&past_days=1&timezone=auto"
        )
        
        try:
            weather_resp, marine_resp = await asyncio.gather(
                client.get(weather_url),
                client.get(marine_url)
            )
            weather_resp.raise_for_status()
            marine_resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Open-Meteo HTTP error: {e.response.status_code}")
            raise HTTPException(502, f"فشل الاتصال بـ Open-Meteo: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Network/Async error: {e}")
            raise HTTPException(503, "تعذر جلب البيانات الجوية. حاول لاحقاً.")
        
        result = analyze_single_spot(req.lat, req.lon, req.beach_direction, weather_resp.json(), marine_resp.json())
        result["name"] = "موقع محدد"
        return result


@app.post("/best-spots", tags=["Discovery"])
async def get_best_spots(custom_spots: List[BatchSpot]):
    """مسح وتقييم جميع الشواطئ المبرمجة + المفضلات، وترتيبها من الأفضل للأسوأ"""
    all_spots = TUNISIAN_SPOTS + [s.model_dump() for s in custom_spots]
    results = []
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        for spot in all_spots:
            try:
                w_url = f"https://api.open-meteo.com/v1/forecast?latitude={spot['lat']}&longitude={spot['lon']}&hourly=wind_speed_10m,wind_direction_10m,surface_pressure&past_days=1&timezone=auto"
                m_url = f"https://marine-api.open-meteo.com/v1/marine?latitude={spot['lat']}&longitude={spot['lon']}&hourly=swell_wave_height,swell_wave_period,swell_wave_direction&past_days=1&timezone=auto"
                
                w_res, m_res = await asyncio.gather(client.get(w_url), client.get(m_url))
                w_res.raise_for_status()
                m_res.raise_for_status()
                
                res = analyze_single_spot(spot["lat"], spot["lon"], spot["facing"], w_res.json(), m_res.json())
                res["name"] = spot["name"]
                results.append(res)
                
                await asyncio.sleep(0.25)  # احترام حدود الـ API المجاني
            except Exception as e:
                logger.warning(f"Failed to evaluate spot '{spot.get('name', 'unknown')}': {e}")
                continue
        results.sort(key=lambda x: x["verdict"]["score"], reverse=True)
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
    return results


# ---------------------------------------------
# 5. معالجة الأخطاء العامة
# ---------------------------------------------
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(req: Request, exc: HTTPException):
    msgs = {
        400: "طلب غير صالح", 404: "غير موجود", 422: "بيانات خاطئة",
        429: "تجاوز الحد", 500: "خطأ داخلي", 502: "خطأ خارجي",
        503: "غير متاح", 504: "انتهت المهلة"
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": exc.status_code,
            "message_ar": msgs.get(exc.status_code, "خطأ غير متوقع"),
            "detail": exc.detail,
            "path": req.url.path
        }
    )


# ---------------------------------------------
# 6. نقطة الدخول للتشغيل المحلي
# ---------------------------------------------
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting local development server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
