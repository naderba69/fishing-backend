import math
import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

# ==========================================
# 1. تهيئة التطبيق وفتح CORS بالكامل
# ==========================================
app = FastAPI(
    title="Tunisia Surfcasting Analyzer",
    description="تحليل ذكي لظروف صيد الشاطئ في تونس مع تقييم المخاطر ومصفوفة القرار",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # يسمح بالاتصال من Vercel، GitHub Pages، أي نطاق
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. قاعدة بيانات الشواطئ التونسية
# ==========================================
TUNISIAN_SPOTS = [
    {"name": "قلعة الأندلس (تونس)", "lat": 36.9150, "lon": 10.1550, "facing": "N"},
    {"name": "شاطئ رواد (تونس)", "lat": 36.9380, "lon": 10.2150, "facing": "NE"},
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
# 3. الدوال المساعدة والمنطق الجغرافي/البحري
# ==========================================
def dir_to_deg(d: str) -> float:
    return {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}.get(d.upper(), 0)

def classify_wind(wind_deg: float, beach_dir: str) -> str:
    """تحويل درجات الرياح إلى اتجاه نسبي مقارنة بواجهة الشاطئ"""    beach_deg = dir_to_deg(beach_dir)
    diff = abs(wind_deg - beach_deg)
    if diff > 180:
        diff = 360 - diff
    if diff <= 45:
        return "Onshore"
    elif diff >= 135:
        return "Offshore"
    return "Side-shore"

def is_low_tide_approx(utc_hour: int) -> bool:
    """محاكاة تقريبية لنظام المد والجزر شبه اليومي في الساحل التونسي"""
    phase = ((utc_hour - 3) % 12.42) / 12.42 * 360
    return phase < 40 or phase > 320

def get_current_utc_index(times_list: List[str]) -> int:
    """إيجاد الفهرس الأقرب للوقت الحالي UTC في مصفوفة Open-Meteo"""
    now = datetime.now(timezone.utc)
    closest_idx, min_diff = 0, timedelta(hours=24)
    for i, t_str in enumerate(times_list):
        t = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        diff = abs(now - t)
        if diff < min_diff:
            min_diff, closest_idx = diff, i
    return closest_idx

# ==========================================
# 4. محرك التحليل الذكي (Fishing Logic & Risk Matrix)
# ==========================================
def analyze_single_spot(lat: float, lon: float, beach_dir: str, weather_data: dict, marine_data: dict) -> dict:
    now_utc = datetime.now(timezone.utc)
    
    # استخراج المصفوفات من JSON
    w_times = weather_data.get("hourly", {}).get("time", [])
    w_pres = weather_data.get("hourly", {}).get("surface_pressure", [])
    w_wind_spd = weather_data.get("hourly", {}).get("wind_speed_10m", [])
    w_wind_dir = weather_data.get("hourly", {}).get("wind_direction_10m", [])
    
    m_times = marine_data.get("hourly", {}).get("time", [])
    m_swell_h = marine_data.get("hourly", {}).get("swell_wave_height", [])
    m_swell_p = marine_data.get("hourly", {}).get("swell_wave_period", [])
    m_swell_dir = marine_data.get("hourly", {}).get("swell_wave_direction", [])
    
    current_idx = get_current_utc_index(w_times)
    
    # القيم الحالية
    wind_spd = w_wind_spd[current_idx] if current_idx < len(w_wind_spd) else 15.0
    wind_dir = w_wind_dir[current_idx] if current_idx < len(w_wind_dir) else 270.0
    current_pres = w_pres[current_idx] if current_idx < len(w_pres) else 1015.0
    swell_h = m_swell_h[current_idx] if current_idx < len(m_swell_h) else 0.8    swell_p = m_swell_p[current_idx] if current_idx < len(m_swell_p) else 8.0
    swell_dir = m_swell_dir[current_idx] if current_idx < len(m_swell_dir) else 0.0
    
    # اتجاه الضغط الجوي قبل 3 ساعات
    idx_3h_ago = max(0, current_idx - 3)
    pres_3h_ago = w_pres[idx_3h_ago] if idx_3h_ago < len(w_pres) else 1015.0
    pres_trend = current_pres - pres_3h_ago  # سالب = انخفاض، موجب = ارتفاع
    
    wind_type = classify_wind(wind_dir, beach_dir)
    
    # منطق الطحالب والحطام (Persistent 24H Logic)
    persistent_seaweed = False
    start_idx_24h = max(0, current_idx - 24)
    for i in range(start_idx_24h, current_idx):
        if i >= len(m_swell_h): break
        if m_swell_h[i] > 2.0:
            if classify_wind(w_wind_dir[i] if i < len(w_wind_dir) else 0, beach_dir) == "Onshore":
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

    # تيارات السحب (Rip Currents)
    is_low = is_low_tide_approx(now_utc.hour)
    if swell_p >= 14.0 and is_low:
        rip_risk = "Confirmed"
    elif 10.0 <= swell_p < 14.0:
        rip_risk = "High"
    else:
        rip_risk = "Low"

    # خطر الرياح
    if wind_spd < 10: wind_risk = "None"
    elif 10 <= wind_spd <= 25: wind_risk = "Low"
    elif 26 <= wind_spd <= 45: wind_risk = "High"
    else: wind_risk = "Confirmed"

    # مصفوفة القرار النهائية (Ultimate Verdict Matrix)
    score = 0
    for r in [seaweed_risk, rip_risk, wind_risk]:
        if r == "None": score += 10        elif r == "Low": score += 5
        elif r == "High": score += 2
        elif "Confirmed" in r: score -= 5

    if 0.5 <= swell_h <= 1.2: score += 10
    elif swell_h > 1.8: score -= 15
    
    if -2.0 <= pres_trend <= -1.0: score += 10
    elif pres_trend > 2.0: score -= 10
    
    score = max(0, min(45, score))

    if score >= 35 and seaweed_risk == "None" and wind_risk in ["None", "Low"] and rip_risk in ["Low"]:
        verdict = "ممتاز"
        explanation = "ظروف ممتازة: موج مناسب (0.5-1.2م)، رياح خفيفة، وانخفاض ضغط بطيء ينشط الأسماك. التيارات والطحالب تحت السيطرة."
    elif score >= 20 and "Confirmed" not in [seaweed_risk, wind_risk]:
        verdict = "ممكن"
        explanation = "ظروف مقبولة للصيد مع بعض التحديات. استخدم معدات أثقل قليلاً وراقب التيارات الجانبية."
    elif score >= 5:
        verdict = "صعب جداً"
        explanation = "ظروف قاسية: أمواج عاتية أو رياح شديدة أو طحالب متراكمة. يتطلب خبرة عالية وتجهيزات ثقيلة."
    else:
        verdict = "مستحيل"
        explanation = "الظروف خطرة: أمواج عاتية جداً مع رياح عاتية أو مخلفات طحالب مؤكدة. لا يُنصح بالنزول للشاطئ إطلاقاً."

    # حساب وزن الرصاص (Sinker Weight Logic)
    base_weight = 50
    weight = base_weight + (swell_h * 40) + (wind_spd * 0.8)
    if wind_type == "Onshore": weight += 20
    if rip_risk == "High": weight += 30
    sinker_g = int(min(300, max(30, weight)))

    return {
        "location": {"lat": lat, "lon": lon, "facing": beach_dir},
        "conditions": {
            "wind_speed_kmh": round(wind_spd, 1),
            "wind_type": wind_type,
            "swell_height_m": round(swell_h, 2),
            "swell_period_s": round(swell_p, 1),
            "pressure_trend_hpa": round(pres_trend, 2),
            "is_low_tide": is_low
        },
        "risks": {
            "seaweed_debris": seaweed_risk,
            "rip_currents": rip_risk,
            "wind_danger": wind_risk
        },
        "verdict": {
            "status": verdict,
            "score": score,            "explanation": explanation,
            "sinker_weight_g": sinker_g
        }
    }

# ==========================================
# 5. نماذج البيانات (Pydantic)
# ==========================================
class AnalyzeRequest(BaseModel):
    lat: float
    lon: float
    beach_direction: str

class BatchSpot(BaseModel):
    name: str
    lat: float
    lon: float
    facing: str

# ==========================================
# 6. نقاط النهاية (API Endpoints)
# ==========================================
@app.post("/analyze")
async def analyze_spot(req: AnalyzeRequest):
    """تحليل نقطة واحدة مع جلب البيانات من Weather و Marine APIs بالتوازي"""
    async with httpx.AsyncClient(timeout=12.0) as client:
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={req.lat}&longitude={req.lon}"
            f"&hourly=wind_speed_10m,wind_direction_10m,surface_pressure"
            f"&past_days=1&timezone=auto"
        )
        marine_url = (
            f"https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={req.lat}&longitude={req.lon}"
            f"&hourly=swell_wave_height,swell_wave_period,swell_wave_direction"
            f"&past_days=1&timezone=auto"
        )
        
        try:
            # جلب متزامن حقيقي (Simultaneous)
            weather_resp, marine_resp = await asyncio.gather(
                client.get(weather_url),
                client.get(marine_url)
            )
            weather_resp.raise_for_status()
            marine_resp.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"فشل الاتصال بـ Open-Meteo: {str(e)}")
                    result = analyze_single_spot(req.lat, req.lon, req.beach_direction, weather_resp.json(), marine_resp.json())
        result["name"] = "موقع محدد"
        return result

@app.post("/best-spots")
async def get_best_spots(custom_spots: List[BatchSpot]):
    """مسح وتقييم جميع الشواطئ المبرمجة + المفضلات، وترتيبها من الأفضل للأسوأ"""
    all_spots = TUNISIAN_SPOTS + [s.model_dump() for s in custom_spots]
    results = []
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for spot in all_spots:
            w_url = f"https://api.open-meteo.com/v1/forecast?latitude={spot['lat']}&longitude={spot['lon']}&hourly=wind_speed_10m,wind_direction_10m,surface_pressure&past_days=1&timezone=auto"
            m_url = f"https://marine-api.open-meteo.com/v1/marine?latitude={spot['lat']}&longitude={spot['lon']}&hourly=swell_wave_height,swell_wave_period,swell_wave_direction&past_days=1&timezone=auto"
            
            try:
                w_res, m_res = await asyncio.gather(client.get(w_url), client.get(m_url))
                res = analyze_single_spot(spot["lat"], spot["lon"], spot["facing"], w_res.json(), m_res.json())
                res["name"] = spot["name"]
                results.append(res)
            except:
                continue  # تخطي النقطة في حال فشل API مؤقتاً
                
    # الترتيب حسب النقاط (الأعلى أولاً)
    results.sort(key=lambda x: x["verdict"]["score"], reverse=True)
    return results

# ==========================================
# 7. تشغيل محلي (اختياري، Render يستخدم Start Command)
# ==========================================
if __name__ == "__main__":
    import uvicorn
    # يعمل محلياً على المنفذ 8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
