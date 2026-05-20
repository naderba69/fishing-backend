import asyncio
import logging
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

# ==========================================
# إعدادات التسجيل
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("surfcast-api")

# ==========================================
# تهيئة التطبيق
# ==========================================
app = FastAPI(title="Tunisia Surfcasting Analyzer API", version="1.0.0", docs_url="/docs")

# ==========================================
# إعدادات CORS
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600
)

# ==========================================
# قاعدة بيانات الشواطئ التونسية
# ==========================================
TUNISIAN_SPOTS = [
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
# ==========================================
# الدوال المساعدة (مسطحة لتجنب أخطاء التنسيق)
# ==========================================
def dir_to_deg(d: str) -> float:
    m = {"N":0.0,"NNE":22.5,"NE":45.0,"ENE":67.5,"E":90.0,"ESE":112.5,"SE":135.0,"SSE":157.5,"S":180.0,"SSW":202.5,"SW":225.0,"WSW":247.5,"W":270.0,"WNW":292.5,"NW":315.0,"NNW":337.5}
    return m.get(d.strip().upper(), 0.0)

def classify_wind(wind_deg: float, beach_dir: str) -> str:
    diff = abs(wind_deg - dir_to_deg(beach_dir))
    if diff > 180.0: diff = 360.0 - diff
    if diff <= 45.0: return "Onshore"
    if diff >= 135.0: return "Offshore"
    return "Side-shore"

def is_low_tide_approx(utc_hour: int, lat: float) -> bool:
    offset = 3.0 if lat < 37.0 else 2.0
    phase = ((utc_hour - offset) % 12.42) / 12.42 * 360.0
    return phase < 40.0 or phase > 320.0

def get_utc_index(times_list: List[str]) -> int:
    if not times_list: return 0
    now = datetime.now(timezone.utc)
    idx, min_diff = 0, timedelta(hours=24)
    # تم تسطيح الحلقة لتجنب أخطاء المسافات
    for i, t_str in enumerate(times_list):
        try:
            dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
            d = abs(now - dt)
            if d < min_diff:
                min_diff = d
                idx = i
        except Exception:
            continue
    return idx

def safe_get(lst: List, i: int, default=None):
    try: return lst[i] if 0 <= i < len(lst) else default
    except Exception: return default

# ==========================================
# محرك التحليل الذكي
# ==========================================
def analyze_logic(lat: float, lon: float, beach_dir: str, w_data: Dict, m_data: Dict) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    w_h = w_data.get("hourly", {})
    m_h = m_data.get("hourly", {})
    idx = get_utc_index(w_h.get("time", []))

    ws = safe_get(w_h.get("wind_speed_10m", []), idx, 15.0)
    wd = safe_get(w_h.get("wind_direction_10m", []), idx, 270.0)    
    p_now = safe_get(w_h.get("surface_pressure", []), idx, 1015.0)
    p_prev = safe_get(w_h.get("surface_pressure", []), max(0, idx-3), p_now)
    trend = p_now - p_prev

    sh = safe_get(m_h.get("swell_wave_height", []), idx, 0.8)
    sp = safe_get(m_h.get("swell_wave_period", []), idx, 8.0)
    wt = classify_wind(wd, beach_dir)

    # منطق الطحالب (24 ساعة)
    persistent = False
    for i in range(max(0, idx-24), idx):
        if i >= len(m_h.get("swell_wave_height", [])): break
        if m_h["swell_wave_height"][i] > 2.0:
            h_wd = safe_get(w_h.get("wind_direction_10m", []), i, 0.0)
            if classify_wind(h_wd, beach_dir) == "Onshore":
                persistent = True
                break

    if persistent: sw = "Confirmed/Persistent"
    elif sh < 0.4 or wt == "Offshore": sw = "None"
    elif 0.4 <= sh <= 1.0 and wt == "Side-shore": sw = "Low"
    elif 1.0 < sh <= 1.8 and wt == "Onshore": sw = "High"
    else: sw = "Low"

    low_tide = is_low_tide_approx(now.hour, lat)
    rip = "Confirmed" if sp >= 14.0 and low_tide else ("High" if 10.0 <= sp < 14.0 else "Low")
    wr = "None" if ws < 10.0 else ("Low" if ws <= 25.0 else ("High" if ws <= 45.0 else "Confirmed"))

    score = sum({"None":10, "Low":5, "High":2}.get(r, -5) for r in [sw, rip, wr])
    if 0.5 <= sh <= 1.2: score += 10
    elif sh > 1.8: score -= 15
    if -2.0 <= trend <= -1.0: score += 10
    elif trend > 2.0: score -= 10
    score = max(0, min(45, score))

    if score >= 35 and sw == "None" and wr in ["None", "Low"] and rip in ["Low"]:
        verdict, expl = "ممتاز", "ظروف ممتازة: موج مناسب، رياح خفيفة، وانخفاض ضغط بطيء ينشط الأسماك."
    elif score >= 20 and "Confirmed" not in [sw, wr]:
        verdict, expl = "ممكن", "ظروف مقبولة للصيد مع بعض التحديات. استخدم معدات أثقل قليلاً."
    elif score >= 5:
        verdict, expl = "صعب جداً", "ظروف قاسية: أمواج عاتية أو رياح شديدة أو طحالب متراكمة."
    else:
        verdict, expl = "مستحيل", "الظروف خطرة: أمواج عاتية جداً أو رياح عاتية أو مخلفات طحالب مؤكدة."

    sinker = int(min(300, max(30, 50 + sh*40 + ws*0.8 + (20 if wt=="Onshore" else 0) + (30 if rip=="High" else 0))))

    return {
        "location": {"lat": round(lat, 4), "lon": round(lon, 4), "facing": beach_dir},
        "conditions": {"wind_speed_kmh": round(ws, 1), "wind_type": wt, "swell_height_m": round(sh, 2), "swell_period_s": round(sp, 1), "pressure_trend_hpa": round(trend, 2), "is_low_tide": low_tide},
        "risks": {"seaweed_debris": sw, "rip_currents": rip, "wind_danger": wr},        "verdict": {"status": verdict, "score": score, "explanation": expl, "sinker_weight_g": sinker}
    }

# ==========================================
# نماذج البيانات
# ==========================================
class AnalyzeReq(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    beach_direction: str = Field(..., pattern=r"^(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)$")
    @field_validator('beach_direction')
    @classmethod
    def norm_dir(cls, v: str) -> str: return v.strip().upper()

class SpotReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    facing: str = Field(..., pattern=r"^(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)$")
    @field_validator('facing')
    @classmethod
    def norm_face(cls, v: str) -> str: return v.strip().upper()

# ==========================================
# نقاط النهاية
# ==========================================
@app.get("/")
async def root(): return {"status": "online", "service": "Tunisia Surfcasting Analyzer API", "version": "1.0.0"}

@app.get("/health")
async def health(req: Request): return JSONResponse({"healthy": True, "timestamp": datetime.now(timezone.utc).isoformat(), "request_id": req.headers.get("x-request-id", "n/a")})

@app.post("/analyze")
async def analyze(req: AnalyzeReq):
    logger.info(f"Analyze: {req.lat},{req.lon},{req.beach_direction}")
    async with httpx.AsyncClient(timeout=15) as c:
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={req.lat}&longitude={req.lon}&hourly=wind_speed_10m,wind_direction_10m,surface_pressure&past_days=1&timezone=auto"
        m_url = f"https://marine-api.open-meteo.com/v1/marine?latitude={req.lat}&longitude={req.lon}&hourly=swell_wave_height,swell_wave_period,swell_wave_direction&past_days=1&timezone=auto"
        try:
            w_r, m_r = await asyncio.gather(c.get(w_url), c.get(m_url))
            w_r.raise_for_status()
            m_r.raise_for_status()
        except Exception as e:
            logger.error(f"API error: {e}")
            raise HTTPException(502, f"Open-Meteo error: {str(e)}")
        result = analyze_logic(req.lat, req.lon, req.beach_direction, w_r.json(), m_r.json())
        result["name"] = "موقع محدد"
        return result

@app.post("/best-spots")async 
def best_spots(custom: List[SpotReq]):
    spots = TUNISIAN_SPOTS + [{"name":s.name,"lat":s.lat,"lon":s.lon,"facing":s.facing,"region":"مفضل"} for s in custom]
    results = []
    async with httpx.AsyncClient(timeout=20) as c:
        for s in spots:
            try:
                w = await c.get(f"https://api.open-meteo.com/v1/forecast?latitude={s['lat']}&longitude={s['lon']}&hourly=wind_speed_10m,wind_direction_10m,surface_pressure&past_days=1&timezone=auto")
                m = await c.get(f"https://marine-api.open-meteo.com/v1/marine?latitude={s['lat']}&longitude={s['lon']}&hourly=swell_wave_height,swell_wave_period,swell_wave_direction&past_days=1&timezone=auto")
                w.raise_for_status()
                m.raise_for_status()
                r = analyze_logic(s["lat"], s["lon"], s["facing"], w.json(), m.json())
                r["name"] = s["name"]
                r["region"] = s.get("region", "")
                results.append(r)
                await asyncio.sleep(0.25)
            except Exception as e:
                logger.warning(f"Skip {s['name']}: {e}")
                continue
    results.sort(key=lambda x: x["verdict"]["score"], reverse=True)
    for i, r in enumerate(results, 1): r["rank"] = i
    return results

@app.exception_handler(HTTPException)
async def http_err(req: Request, exc: HTTPException):
    msgs = {400:"طلب غير صالح",404:"غير موجود",422:"بيانات خاطئة",429:"تجاوز الحد",500:"خطأ داخلي",502:"خطأ خارجي",503:"غير متاح",504:"انتهت المهلة"}
    return JSONResponse(status_code=exc.status_code, content={"error":True,"code":exc.status_code,"message_ar":msgs.get(exc.status_code,"خطأ غير متوقع"),"detail":exc.detail,"path":req.url.path})

if __name__ == "__main__":
    import uvicorn, os
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")