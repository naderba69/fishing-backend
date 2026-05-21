import asyncio
import httpx
import math
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Dict, List, Tuple

app = FastAPI(title="Surfcasting Tunisia - The Tactical Field Commander", version="9.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- DATABASES (Spots & Fish Profiles) ---
PREDEFINED_SPOTS = {
    "Tunis": [
        {"name": "قلعة الأندلس", "lat": 36.9150, "lon": 10.1550, "beach_angle": 20},
        {"name": "شاطئ رواد", "lat": 36.9380, "lon": 10.2150, "beach_angle": 45}
    ],
    "Nabeul": [
        {"name": "قليبية", "lat": 36.8500, "lon": 11.1000, "beach_angle": 70},
        {"name": "الهوارية", "lat": 37.0500, "lon": 11.0150, "beach_angle": 315},
        {"name": "حمام الغزاز", "lat": 36.8850, "lon": 11.1150, "beach_angle": 90}
    ],
    "Bizerte": [
        {"name": "كاب سيرات", "lat": 37.2300, "lon": 9.2100, "beach_angle": 340},
        {"name": "سيدي مشرق", "lat": 37.1600, "lon": 9.1200, "beach_angle": 330},
        {"name": "الرمال", "lat": 37.2750, "lon": 9.9150, "beach_angle": 40}
    ],
    "Sousse": [
        {"name": "شط مريم", "lat": 35.9350, "lon": 10.5600, "beach_angle": 90},
        {"name": "هرقلة", "lat": 36.0300, "lon": 10.5100, "beach_angle": 90}
    ],
}

FISH_PROFILES = {
    "sea_bass": {"name": "القاروص (Loup)", "ideal_swell": (0.8, 2.2), "ideal_sst": (13, 19), "peak_season": [1, 2, 3, 11, 12]},
    "sea_bream": {"name": "الوراطة (Daurade)", "ideal_swell": (0.2, 0.9), "ideal_sst": (17, 24), "peak_season": [4, 5, 6, 9, 10, 11]},
    "bluefish": {"name": "التاسرغال (Tassergal)", "ideal_swell": (0.7, 1.8), "ideal_sst": (19, 26), "peak_season": [6, 7, 8, 9, 10]},
    "sargus": {"name": "القارص / الشرغو (Sar)", "ideal_swell": (0.6, 1.5), "ideal_sst": (14, 21), "peak_season": [2, 3, 4, 10, 11]}
}

# --- CORE PHYSICS & ANALYSIS FUNCTIONS ---
def get_shore_relation(deg: float, beach_angle: float) -> Tuple[str, float]:
    angle_diff = min(abs(deg - beach_angle) % 360, 360 - abs(deg - beach_angle) % 360)
    if angle_diff <= 50: return "Onshore", angle_diff
    if angle_diff >= 130: return "Offshore", angle_diff
    return "Side-shore", angle_diff

def predict_fish(h: Dict, current_month: int, pressure_trend: str) -> List[str]:
    likely = []
    for profile in FISH_PROFILES.values():
        if current_month in profile['peak_season'] and \
           profile['ideal_sst'][0] <= h['sst'] <= profile['ideal_sst'][1] and \
           profile['ideal_swell'][0] <= h['swell_height'] <= profile['ideal_swell'][1]:
            
            # محاكاة تأثير الضغط الجوي على شهية الحوت
            if profile['name'] == "القاروص (Loup)" and pressure_trend == "Dropping":
                likely.append(f"{profile['name']} 🎯 (نشاط عالي جداً)")
            else:
                likely.append(profile['name'])
    return likely

def analyze_hour(h: Dict, persistent_debris: bool, current_month: int, pressure_trend: str) -> Dict:
    swell_h, swell_p, wind_s = h['swell_height'], h['swell_period'], h['wind_speed']
    wind_shore_type, _ = h['wind_shore']
    swell_shore_type, swell_angle_diff = h['swell_shore']
    wave_energy = (swell_h ** 2) * swell_p

    # 1. تحليل الأعشاب والأوساخ (Seaweed Logic)
    seaweed = "None"
    if persistent_debris: 
        seaweed = "Confirmed"
    elif (wind_shore_type == "Onshore" or swell_shore_type == "Onshore") and swell_h > 1.2: 
        seaweed = "High"
    elif wind_shore_type == "Onshore" and swell_shore_type == "Onshore" and swell_h > 1.6: 
        seaweed = "Confirmed"

    # 2. تحليل التيارات الجانبية (Longshore Drift)
    longshore = "None"
    if 40 < swell_angle_diff < 85 and swell_h > 0.8: longshore = "High"
    if 40 < swell_angle_diff < 85 and swell_h > 1.4: longshore = "Confirmed"

    # 3. تحليل التيارات الساحبة الخطيرة (Rip Currents Logic)
    rip_current = "None"
    if swell_shore_type == "Onshore" and swell_angle_diff <= 30 and swell_p >= 10:
        rip_current = "High"
    if swell_shore_type == "Onshore" and swell_angle_diff <= 20 and swell_p >= 13 and swell_h > 1.0:
        rip_current = "Confirmed"

    # 4. محرك حساب النقاط التكتيكي (Tactical Score Engine)
    score = 100
    if seaweed == "High": score -= 35
    if seaweed == "Confirmed": score -= 75
    if longshore == "High": score -= 25
    if longshore == "Confirmed": score -= 55
    if rip_current == "High": score -= 30
    if rip_current == "Confirmed": score -= 70
    if wind_s > 25: score -= 30
    if wind_s > 45: score -= 75
    if swell_h > 2.2: score -= 90
    
    # تحسين النقاط بناءً على الضغط الجوي المناسب للسمك
    if pressure_trend == "Dropping": score += 5 
    if pressure_trend == "Rising Fast": score -= 15
    score = max(0, min(100, score)) # حصر النتيجة بين 0 و 100

    verdict = "مستحيل"
    if score > 35: verdict = "صعب جداً"
    if score > 60: verdict = "ممكن"
    if score > 85: verdict = "ممتاز"
    
    likely_fish = []
    if verdict in ["ممتاز", "ممكن"]:
        likely_fish = predict_fish(h, current_month, pressure_trend)

    # مرشد الرصاص الاحترافي بناءً على طاقة و زاوية البحر
    sinker_advice = "رصاص هرمي خفيف (100غ - 110غ)"
    if wave_energy < 3: 
        sinker_advice = "رصاص كروي أو مخروطي (80غ - 100غ)"
    elif rip_current in ["High", "Confirmed"] or longshore in ["High", "Confirmed"]: 
        sinker_advice = "رصاص عنكبوتي جراف (Grapple Sinker) +130غ لتثبيت الخيط"
    elif wave_energy > 15: 
        sinker_advice = "رصاص هرمي ثقيل (130غ - 150غ)"

    # بناء التقرير التفسيري (ماذا اعتمد الذكاء الاصطناعي)
    explanation = "العوامل آمنة والموج مثالي للصيد."
    if seaweed in ["High", "Confirmed"]:
        explanation = f"التقييم منخفض بسبب خطر تراكم الأعشاب نتيجة موج الـ Onshore."
    if rip_current in ["High", "Confirmed"]:
        explanation = f"خطر التيارات الساحبة عالي جداً بسبب دخول أمواج السويد الطويلة ({swell_p} ثواني) عمودياً."
    if pressure_trend == "Dropping" and verdict in ["ممتاز", "ممكن"]:
        explanation += " الضغط الجوي ينخفض ببطء، هجوم السمك متوقع وشره!"

    return {
        "verdict": verdict, 
        "score": score, 
        "likely_fish": likely_fish, 
        "sinker_advice": sinker_advice, 
        "explanation": explanation,
        "risks": {"seaweed": seaweed, "longshore_drift": longshore, "rip_current": rip_current}
    }

async def get_full_spot_analysis(lat: float, lon: float, angle: float, spot_name: str = "مكان مخصص") -> Dict:
    current_month = datetime.now().month
    
    params = {"latitude": lat, "longitude": lon, "hourly": "wind_speed_10m,wind_direction_10m,surface_pressure", "wind_speed_unit": "kmh", "past_days": 1, "forecast_days": 1, "timezone": "auto"}
    marine_params = {"latitude": lat, "longitude": lon, "hourly": "swell_wave_height,swell_wave_period,swell_wave_direction,sea_surface_temperature", "past_days": 1, "forecast_days": 1, "timezone": "auto"}
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        w_task = client.get("https://api.open-meteo.com/v1/forecast", params=params)
        m_task = client.get("https://marine-api.open-meteo.com/v1/marine", params=marine_params)
        w_resp, m_resp = await asyncio.gather(w_task, m_task)

    if w_resp.status_code != 200 or m_resp.status_code != 200: return None
    w, m = w_resp.json()['hourly'], m_resp.json()['hourly']

    # كاشف مخلفات البحر لـ 24 ساعة الماضية
    persistent_debris = any(s > 2.0 for s in m['swell_wave_height'][:24] if s is not None)

    hourly_analysis = []
    for i in range(24, 48): # فحص ساعات يوم الغد/اليوم الحالي الموقوت
        # حساب ترند الضغط الجوي (مقارنة بالساعات الـ 3 الماضية)
        p_now = w['surface_pressure'][i] or 1013
        p_past = w['surface_pressure'][i-3] or 1013
        p_diff = p_now - p_past
        
        pressure_trend = "Stable"
        if p_diff < -0.8: pressure_trend = "Dropping"
        elif p_diff > 1.2: pressure_trend = "Rising Fast"

        hour_data = {
            "time": w['time'][i],
            "swell_height": m['swell_wave_height'][i] or 0, 
            "swell_period": m['swell_wave_period'][i] or 0,
            "wind_speed": w['wind_speed_10m'][i] or 0, 
            "sst": m['sea_surface_temperature'][i] or 18,
            "pressure": p_now,
            "pressure_trend": pressure_trend,
            "wind_shore": get_shore_relation(w['wind_direction_10m'][i] or 0, angle),
            "swell_shore": get_shore_relation(m['swell_wave_direction'][i] or 0, angle),
        }
        analysis = analyze_hour(hour_data, persistent_debris, current_month, pressure_trend)
        hour_data.update(analysis)
        hourly_analysis.append(hour_data)
    
    return {"spot_name": spot_name, "persistent_debris": persistent_debris, "analysis": hourly_analysis}

# --- API ENDPOINTS ---
@app.get("/forecast")
async def get_detailed_forecast(lat: float, lon: float, angle: float):
    res = await get_full_spot_analysis(lat, lon, angle)
    if not res: raise HTTPException(status_code=500, detail="خطأ في جلب بيانات الطقس البحرية")
    return res

@app.get("/decision-maker")
async def get_best_spot_decision():
    all_spots = [spot for region in PREDEFINED_SPOTS.values() for spot in region]
    tasks = [get_full_spot_analysis(spot['lat'], spot['lon'], spot['beach_angle'], spot['name']) for spot in all_spots]
    results = await asyncio.gather(*tasks)
    
    summaries = []
    for res in results:
        if res:
            # حساب متوسط أفضل فترة صيد متاحة (مثال: الفترة الصباحية من 6 إلى 12)
            morning_hours = [h for h in res['analysis'] if 6 <= datetime.fromisoformat(h['time']).hour < 12]
            if morning_hours:
                avg_score = sum(h['score'] for h in morning_hours) / len(morning_hours)
                best_fish = max(morning_hours, key=lambda x: x['score'])['likely_fish']
                explanation = max(morning_hours, key=lambda x: x['score'])['explanation']
                sinker = max(morning_hours, key=lambda x: x['score'])['sinker_advice']
            else:
                avg_score = sum(h['score'] for h in res['analysis']) / len(res['analysis'])
                best_fish = []
                explanation = "العوامل متقلبة على مدار اليوم"
                sinker = "رصاص هرمي قياسي"

            verdict = "مستحيل"
            if avg_score > 35: verdict = "صعب جداً"
            if avg_score > 60: verdict = "ممكن"
            if avg_score > 85: verdict = "ممتاز"
            
            summaries.append({
                "spot_name": res['spot_name'], 
                "score": round(avg_score, 1),
                "verdict": verdict, 
                "persistent_debris": res['persistent_debris'], 
                "likely_fish": best_fish,
                "explanation": explanation,
                "sinker_advice": sinker
            })

    # ترتيب الشواطئ تصاعدياً من الأفضل إلى الأسوأ بناءً على النتيجة الحقيقية المحسوبة
    sorted_summaries = sorted(summaries, key=lambda x: x['score'], reverse=True)
    return sorted_summaries

@app.get("/predefined-spots")
async def get_spots(): 
    return PREDEFINED_SPOTS
