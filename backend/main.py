# main.py - v7.0 The Realistic Guide
import asyncio
import httpx
import math
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, time
from typing import Dict, List, Tuple

app = FastAPI(title="Surfcasting Tunisia - The Realistic Guide", version="7.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- DATABASE 1: SPOTS ---
PREDEFINED_SPOTS = {
    "Tunis": [{"name": "قلعة الأندلس", "lat": 36.9150, "lon": 10.1550, "beach_angle": 20}],
    "Nabeul": [{"name": "قليبية", "lat": 36.8500, "lon": 11.1000, "beach_angle": 70}],
    "Bizerte": [{"name": "كاب سيرات", "lat": 37.2300, "lon": 9.2100, "beach_angle": 340}],
    "Sousse": [{"name": "شط مريم", "lat": 35.9350, "lon": 10.5600, "beach_angle": 90}],
}

# --- DATABASE 2: REALISTIC FISH PROFILES FOR TUNISIA ---
FISH_PROFILES = {
    "sea_bass": {
        "name": "القاروص", "ideal_swell": (0.8, 1.8), "ideal_wind": (10, 25),
        "ideal_sst": (14, 20), "peak_season": [1, 2, 3, 4, 5, 10, 11, 12] # Winter/Spring
    },
    "sea_bream": {
        "name": "الوراطة", "ideal_swell": (0.3, 1.0), "ideal_wind": (0, 15),
        "ideal_sst": (16, 23), "peak_season": [3, 4, 5, 9, 10, 11] # Spring/Autumn
    },
    "bluefish": {
        "name": "التاسرغال", "ideal_swell": (0.8, 2.0), "ideal_wind": (15, 30),
        "ideal_sst": (18, 26), "peak_season": [5, 6, 7, 8, 9, 10] # Summer/Autumn
    },
}

# --- CORE PHYSICS & ANALYSIS FUNCTIONS ---
def get_shore_relation(deg: float, beach_angle: float) -> Tuple[str, float]:
    angle_diff = min(abs(deg - beach_angle) % 360, 360 - abs(deg - beach_angle) % 360)
    if angle_diff <= 45: return "Onshore", angle_diff
    if angle_diff >= 135: return "Offshore", angle_diff
    return "Side-shore", angle_diff

def predict_fish(h: Dict, current_month: int) -> List[str]:
    likely = []
    for profile in FISH_PROFILES.values():
        # 3-Stage Check: Season -> Temperature -> Conditions
        is_in_season = current_month in profile['peak_season']
        is_temp_ok = profile['ideal_sst'][0] <= h['sst'] <= profile['ideal_sst'][1]
        is_swell_ok = profile['ideal_swell'][0] <= h['swell_height'] <= profile['ideal_swell'][1]
        
        if is_in_season and is_temp_ok and is_swell_ok:
            likely.append(profile['name'])
    return likely

def analyze_hour(h: Dict, persistent_debris: bool, current_month: int) -> Dict:
    swell_h, swell_p, wind_s = h['swell_height'], h['swell_period'], h['wind_speed']
    wind_shore_type, _ = h['wind_shore']
    swell_shore_type, swell_angle = h['swell_shore']
    
    seaweed = "None"
    if persistent_debris: seaweed = "Confirmed"
    elif (wind_shore_type == "Onshore" or swell_shore_type == "Onshore") and swell_h > 1.0: seaweed = "High"
    elif wind_shore_type == "Onshore" and swell_shore_type == "Onshore" and swell_h > 0.8: seaweed = "Confirmed"

    longshore = "None"
    if 45 < swell_angle < 120 and swell_h > 0.7: longshore = "High"
    if 45 < swell_angle < 120 and swell_h > 1.2: longshore = "Confirmed"

    score = 100
    if seaweed == "High": score -= 40
    if seaweed == "Confirmed": score -= 80
    if longshore == "High": score -= 30
    if longshore == "Confirmed": score -= 70
    if wind_s > 26: score -= 30
    if wind_s > 45: score -= 80
    if swell_h > 2.5: score -= 100
    
    verdict = "مستحيل"
    if score > 40: verdict = "صعب"
    if score > 65: verdict = "ممكن"
    if score > 90: verdict = "ممتاز"
    
    likely_fish = []
    if verdict in ["ممتاز", "ممكن"]:
        likely_fish = predict_fish(h, current_month)

    return {"verdict": verdict, "score": score, "likely_fish": likely_fish}

async def get_full_spot_analysis(spot: Dict) -> Dict:
    lat, lon, angle = spot['lat'], spot['lon'], spot['beach_angle']
    current_month = datetime.now().month
    
    params = {"latitude": lat, "longitude": lon, "hourly": "wind_speed_10m,wind_direction_10m", "wind_speed_unit": "kmh", "past_days": 1, "forecast_days": 1, "timezone": "auto"}
    marine_params = {"latitude": lat, "longitude": lon, "hourly": "swell_wave_height,swell_wave_period,swell_wave_direction,sea_surface_temperature", "past_days": 1, "forecast_days": 1, "timezone": "auto"}
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        w_task = client.get("https://api.open-meteo.com/v1/forecast", params=params)
        m_task = client.get("https://marine-api.open-meteo.com/v1/marine", params=marine_params)
        w_resp, m_resp = await asyncio.gather(w_task, m_task)

    if w_resp.status_code != 200 or m_resp.status_code != 200: return None
    w, m = w_resp.json()['hourly'], m_resp.json()['hourly']

    persistent_debris = any(s > 2.0 for s in m['swell_wave_height'][:24] if s is not None)

    hourly_analysis = []
    for i in range(24, 48):
        hour_data = {
            "swell_height": m['swell_wave_height'][i] or 0, "swell_period": m['swell_wave_period'][i] or 0,
            "wind_speed": w['wind_speed_10m'][i] or 0, "sst": m['sea_surface_temperature'][i] or 18,
            "wind_shore": get_shore_relation(w['wind_direction_10m'][i] or 0, angle),
            "swell_shore": get_shore_relation(m['swell_wave_direction'][i] or 0, angle),
        }
        analysis = analyze_hour(hour_data, persistent_debris, current_month)
        hour_data.update(analysis)
        hourly_analysis.append(hour_data)
    
    return {"spot_name": spot['name'], "persistent_debris": persistent_debris, "analysis": hourly_analysis}

# --- API ENDPOINTS ---
@app.get("/decision-maker")
async def get_best_spot_decision():
    all_spots = [spot for region in PREDEFINED_SPOTS.values() for spot in region]
    tasks = [get_full_spot_analysis(spot) for spot in all_spots]
    results = await asyncio.gather(*tasks)
    
    summaries = []
    for res in results:
        if res:
            periods = {
                "صباحًا (6-12)": [h for h in res['analysis'] if 6 <= datetime.fromisoformat(h['time']).hour < 12],
                "مساءً (13-19)": [h for h in res['analysis'] if 13 <= datetime.fromisoformat(h['time']).hour < 19],
                "ليلاً (20-02)": [h for h in res['analysis'] if datetime.fromisoformat(h['time']).hour >= 20 or datetime.fromisoformat(h['time']).hour < 2],
            }
            
            best_period_name, best_avg_score, best_fish = "لا توجد فرصة", 0, []
            for name, hours in periods.items():
                if hours:
                    avg_score = sum(h['score'] for h in hours) / len(hours)
                    if avg_score > best_avg_score:
                        best_avg_score = avg_score
                        best_period_name = name
                        # Collect fish from the best hour in that period
                        best_hour = max(hours, key=lambda x: x['score'])
                        best_fish = best_hour['likely_fish']
            
            verdict = "مستحيل"
            if best_avg_score > 40: verdict = "صعب"
            if best_avg_score > 65: verdict = "ممكن"
            if best_avg_score > 90: verdict = "ممتاز"
            
            summaries.append({
                "spot_name": res['spot_name'], "best_period": best_period_name,
                "verdict": verdict, "score": int(best_avg_score),
                "persistent_debris": res['persistent_debris'], "likely_fish": best_fish
            })

    sorted_summaries = sorted(summaries, key=lambda x: x['score'] * (0.2 if x['persistent_debris'] else 1), reverse=True)
    return sorted_summaries

@app.get("/predefined-spots")
async def get_spots(): return PREDEFINED_SPOTS
