import asyncio
import logging
import math
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("surfcast-ref-v6")

app = FastAPI(title="Tunisia Surfcasting Reference API", version="6.0.0", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ==========================================
# 📍 قاعدة بيانات مرجعية شاملة (38 موقعاً مدققاً)
# ==========================================
TUNISIAN_SPOTS = [
    # تونس العاصمة (8)
    {"name": "قلعة الأندلس", "lat": 36.9150, "lon": 10.1550, "facing": "N", "region": "تونس", "delegation": "حلق الوادي"},
    {"name": "شاطئ رواد", "lat": 36.9380, "lon": 10.2150, "facing": "NE", "region": "تونس", "delegation": "رواد"},
    {"name": "قرطاج الشاطئ", "lat": 36.8610, "lon": 10.3280, "facing": "E", "region": "تونس", "delegation": "قرطاج"},
    {"name": "المرسى الشاطئ", "lat": 36.8780, "lon": 10.3450, "facing": "NE", "region": "تونس", "delegation": "المرسى"},
    {"name": "سيدي بوسعيد الساحل", "lat": 36.8680, "lon": 10.3420, "facing": "NE", "region": "تونس", "delegation": "سيدي بوسعيد"},
    {"name": "الكاف الساحلي", "lat": 36.8450, "lon": 10.3150, "facing": "E", "region": "تونس", "delegation": "الكرم"},
    {"name": "رادس الشاطئ", "lat": 36.7650, "lon": 10.2850, "facing": "SE", "region": "تونس", "delegation": "رادس"},
    {"name": "برج السدرية", "lat": 36.7150, "lon": 10.3100, "facing": "E", "region": "تونس", "delegation": "حمام الأنف"},

    # نابل (12)
    {"name": "الهوارية الرأس", "lat": 37.0500, "lon": 11.0150, "facing": "N", "region": "نابل", "delegation": "الهوارية"},
    {"name": "سيدي داود", "lat": 36.9850, "lon": 10.9850, "facing": "NW", "region": "نابل", "delegation": "الهوارية"},
    {"name": "بني خيار الساحل", "lat": 36.9450, "lon": 10.9350, "facing": "NW", "region": "نابل", "delegation": "بني خيار"},
    {"name": "قليبية الميناء", "lat": 36.8500, "lon": 11.1000, "facing": "E", "region": "نابل", "delegation": "قليبية"},
    {"name": "حمام الغزاز", "lat": 36.8850, "lon": 11.1150, "facing": "NE", "region": "نابل", "delegation": "قليبية"},
    {"name": "دار شعبان الفهري", "lat": 36.8150, "lon": 11.0650, "facing": "E", "region": "نابل", "delegation": "دار شعبان الفهري"},
    {"name": "قربة الشاطئ", "lat": 36.5850, "lon": 10.8650, "facing": "E", "region": "نابل", "delegation": "قربة"},
    {"name": "منزل تميم", "lat": 36.7650, "lon": 10.9850, "facing": "E", "region": "نابل", "delegation": "منزل تميم"},
    {"name": "الحمامات الشمالية", "lat": 36.4050, "lon": 10.6150, "facing": "NE", "region": "نابل", "delegation": "الحمامات"},
    {"name": "الحمامات الجنوبية", "lat": 36.3850, "lon": 10.6350, "facing": "SE", "region": "نابل", "delegation": "الحمامات"},
    {"name": "نابل المدينة", "lat": 36.4550, "lon": 10.7350, "facing": "E", "region": "نابل", "delegation": "نابل"},
    {"name": "الميدون", "lat": 36.4250, "lon": 10.6850, "facing": "E", "region": "نابل", "delegation": "نابل"},

    # بنزرت (9)
    {"name": "كاب سيرات", "lat": 37.2300, "lon": 9.2100, "facing": "NW", "region": "بنزرت", "delegation": "غار الملح"},
    {"name": "سيدي مشرق", "lat": 37.1600, "lon": 9.1200, "facing": "N", "region": "بنزرت", "delegation": "غار الملح"},
    {"name": "الرمال بنزرت", "lat": 37.2750, "lon": 9.9150, "facing": "NW", "region": "بنزرت", "delegation": "بنزرت الشمالية"},
    {"name": "رأس الأنف (كاب بلانك)", "lat": 37.3450, "lon": 9.7350, "facing": "N", "region": "بنزرت", "delegation": "بنزرت الشمالية"},    {"name": "شاطئ ريمال", "lat": 37.1850, "lon": 9.8650, "facing": "W", "region": "بنزرت", "delegation": "منزل بورقيبة"},
    {"name": "سيدي علي المكي", "lat": 37.1250, "lon": 10.0150, "facing": "NE", "region": "بنزرت", "delegation": "ماطر"},
    {"name": "ماطر الساحل", "lat": 37.0850, "lon": 9.9850, "facing": "NE", "region": "بنزرت", "delegation": "ماطر"},
    {"name": "منزل جميل", "lat": 37.1450, "lon": 9.7850, "facing": "N", "region": "بنزرت", "delegation": "منزل جميل"},
    {"name": "رأس زبيب", "lat": 37.2950, "lon": 9.8150, "facing": "N", "region": "بنزرت", "delegation": "بنزرت الشمالية"},

    # سوسة (9)
    {"name": "شط مريم", "lat": 35.9350, "lon": 10.5600, "facing": "E", "region": "سوسة", "delegation": "أكودة"},
    {"name": "هرقلة", "lat": 36.0300, "lon": 10.5100, "facing": "NE", "region": "سوسة", "delegation": "هرقلة"},
    {"name": "بوجعفر", "lat": 35.8450, "lon": 10.6350, "facing": "E", "region": "سوسة", "delegation": "سوسة الرياض"},
    {"name": "النفيضة الشاطئ", "lat": 36.1150, "lon": 10.4850, "facing": "NE", "region": "سوسة", "delegation": "النفيضة"},
    {"name": "قلعة الكبيرة", "lat": 35.7650, "lon": 10.5850, "facing": "SE", "region": "سوسة", "delegation": "قلعة الكبيرة"},
    {"name": "سيدي بوسعيد الساحل", "lat": 35.6850, "lon": 10.6150, "facing": "E", "region": "سوسة", "delegation": "مساكن"},
    {"name": "أكودة", "lat": 35.9850, "lon": 10.5350, "facing": "E", "region": "سوسة", "delegation": "أكودة"},
    {"name": "سوسة المدينة", "lat": 35.8250, "lon": 10.6350, "facing": "E", "region": "سوسة", "delegation": "سوسة المدينة"},
    {"name": "القنطاوي", "lat": 35.8850, "lon": 10.5950, "facing": "NE", "region": "سوسة", "delegation": "سوسة الرياض"}
]

# ==========================================
# 🧮 دوال أساسية وهندسية
# ==========================================
def dir_to_deg(d: str) -> float:
    m = {"N":0,"NNE":22.5,"NE":45,"ENE":67.5,"E":90,"ESE":112.5,"SE":135,"SSE":157.5,"S":180,"SSW":202.5,"SW":225,"WSW":247.5,"W":270,"WNW":292.5,"NW":315,"NNW":337.5}
    return m.get(d.strip().upper(), 0.0)

def angular_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d

def topographic_correction(wind_deg: float, swell_deg: float, region: str, spot_name: str) -> Tuple[float, float]:
    w_corr, s_corr = wind_deg, swell_deg
    if region == "نابل" and any(k in spot_name for k in ["هوارية","قليبية","سيدي داود","بني خيار"]):
        if 270 <= wind_deg <= 330: w_corr = (wind_deg + 20) % 360
        if 270 <= swell_deg <= 330: s_corr = (swell_deg + 15) % 360
    elif region == "تونس" and any(k in spot_name for k in ["رواد","قرطاج","مرسى","سيدي بوسعيد","كرم"]):
        if 45 <= wind_deg <= 135: w_corr = (wind_deg - 10) % 360
        if 45 <= swell_deg <= 135: s_corr = (swell_deg - 5) % 360
    elif region == "بنزرت" and any(k in spot_name for k in ["سيرات","مشرق","رأس","رمال","زبيب","جميل"]):
        if 340 <= wind_deg or wind_deg <= 40: w_corr = (wind_deg + 15) % 360
        if 340 <= swell_deg or swell_deg <= 40: s_corr = (swell_deg + 10) % 360
    elif region == "سوسة":
        if 90 <= swell_deg <= 150: s_corr = (swell_deg - 8) % 360
    return w_corr % 360, s_corr % 360

def classify_wind(wind_deg: float, beach_dir: str, region: str) -> str:
    diff = angular_diff(wind_deg, dir_to_deg(beach_dir))
    if region == "نابل" and beach_dir in ["N","NE"]:
        return "Onshore" if diff <= 30 else ("Offshore" if diff >= 150 else "Side-shore")
    if region == "بنزرت" and beach_dir in ["N","NW"]:
        return "Onshore" if diff <= 40 else ("Offshore" if diff >= 140 else "Side-shore")
        return "Onshore" if diff <= 45 else ("Offshore" if diff >= 135 else "Side-shore")

def get_moon_data(dt: datetime) -> dict:
    diff = dt - datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    days = diff.total_seconds() / 86400
    phase = (days % 29.53058867) / 29.53058867
    if phase < 0.03 or phase > 0.97: name, icon = "محاق", "🌑"
    elif phase < 0.25: name, icon = "هلال متزايد", "🌒"
    elif phase < 0.28: name, icon = "تربيع أول", "🌓"
    elif phase < 0.50: name, icon = "أحدب متزايد", "🌔"
    elif phase < 0.53: name, icon = "بدر", "🌕"
    elif phase < 0.75: name, icon = "أحدب متناقص", "🌖"
    elif phase < 0.78: name, icon = "تربيع ثاني", "🌗"
    else: name, icon = "هلال متناقص", "🌘"
    activity = 1.3 if (phase < 0.05 or phase > 0.95 or 0.45 < phase < 0.55) else 1.0
    tide_amp = 1.25 if (phase < 0.1 or phase > 0.9 or 0.4 < phase < 0.6) else 0.85
    return {"name": name, "icon": icon, "phase": round(phase, 3), "activity_boost": activity, "tide_amplitude": tide_amp}

def safe_get(lst: list, i: int, default: Any = None) -> Any:
    try:
        val = lst[i] if 0 <= i < len(lst) else default
        return default if val is None else val
    except Exception:
        return default

# ==========================================
# 🔬 جودة البيانات والفيزياء البحرية
# ==========================================
def smooth_series(series: list, max_jump_pct: float = 0.45) -> list:
    if not series or len(series) < 3: return [x for x in series if x is not None] or [0.0]
    cleaned = [x if x is not None else 0.0 for x in series]
    for i in range(1, len(cleaned)-1):
        prev, curr, nxt = cleaned[i-1], cleaned[i], cleaned[i+1]
        if prev == 0: prev = 0.1
        if abs(curr - prev) / prev > max_jump_pct:
            cleaned[i] = (prev + nxt) / 2
    return [sorted(cleaned[max(0,i-1):min(len(cleaned),i+2)])[1] for i in range(len(cleaned))]

def validate_api_data(w_h: dict, m_h: dict, min_len: int = 12) -> bool:
    w_t, m_t = w_h.get("time", []), m_h.get("time", [])
    if len(w_t) < min_len or len(m_t) < min_len: return False
    for k in ["wind_speed_10m","wind_direction_10m","surface_pressure","precipitation","weather_code"]:
        if len(w_h.get(k, [])) != len(w_t): return False
    for k in ["swell_wave_height","swell_wave_period","swell_wave_direction","sea_surface_temperature"]:
        if len(m_h.get(k, [])) != len(m_t): return False
    return True

def corrected_tide_window(utc_hour: int, region: str, pressure_hpa: float, wind_speed: float, wind_type: str, tide_amp: float) -> bool:
    base_offset = {"تونس":3.1, "نابل":3.3, "بنزرت":2.7, "سوسة":3.4}.get(region, 3.0)
    p_corr = ((1013.0 - pressure_hpa) / 10.0) * 0.25
    w_corr = min(1.0, (wind_speed - 20) / 30.0) if wind_type == "Onshore" and wind_speed > 20 else 0.0
    amp_corr = (tide_amp - 1.0) * 0.5
    phase = ((utc_hour - (base_offset + p_corr + w_corr + amp_corr)) % 12.42) / 12.42 * 360
    return phase < 35 or phase > 325

def calculate_debris_energy(w_h: dict, m_h: dict, start_idx: int, end_idx: int, beach_dir: str, region: str) -> Tuple[str, float]:
    if start_idx >= end_idx: return "Low", 0.0
    wd, ws, sh = w_h.get("wind_direction_10m",[])[start_idx:end_idx], w_h.get("wind_speed_10m",[])[start_idx:end_idx], m_h.get("swell_wave_height",[])[start_idx:end_idx]
    energy, hours = 0.0, 0
    for w_dir, w_spd, s_h in zip(wd, ws, sh):
        if classify_wind(w_dir, beach_dir, region) == "Onshore" and w_spd > 12 and s_h > 0.6:
            energy += w_spd * s_h; hours += 1
    if energy > 180 or hours >= 18: return "Confirmed/Persistent", energy
    if energy > 90 or hours >= 10: return "High", energy
    if energy > 40: return "Low", energy
    return "None", energy

def calculate_rain_turbidity(precip: list) -> Tuple[str, float]:
    if not precip: return "None", 0.0
    acc = sum(x for x in precip if x is not None)
    if acc > 25: return "Confirmed", acc
    if acc > 12: return "High", acc
    if acc > 5: return "Low", acc
    return "None", acc

def assess_sea_confusion(wind_dir: float, swell_dir: float, wind_spd: float, swell_h: float) -> dict:
    diff = angular_diff(wind_dir, swell_dir)
    is_cross = diff > 60
    is_choppy = wind_spd > 22 and swell_h < 1.0
    level = "High" if is_cross and swell_h > 0.8 else ("Medium" if is_choppy else ("Low" if is_cross else "None"))
    return {"level": level, "angle_diff": round(diff, 1), "is_cross": is_cross}

def check_thunderstorm_risk(weather_codes: list) -> bool:
    if not weather_codes: return False
    return any(code in [95, 96, 99] for code in weather_codes if code is not None)

def adjust_for_sst(temp_c: float, verdict: str, expl: str) -> Tuple[str, str]:
    if temp_c < 14.0: return "صعب", expl + " ⚠️ ماء بارد (<14°): خمول أسماك واضح."
    if temp_c > 26.5: return "صعب", expl + " ⚠️ ماء دافئ (>26.5°): هجرة للعمق أو نشاط ليلي فقط."
    return verdict, expl

def calculate_confidence(fc_hours: float, variance: float, stability: str) -> int:
    decay = math.exp(-fc_hours / 18.0)
    penalty = min(0.4, variance * 0.15)
    bonus = 0.0 if stability == "متقلب" else 0.1
    return int(max(35, min(95, decay * (1 - penalty + bonus) * 100)))

# ==========================================
# 🧠 محرك التحليل المرجعي
# ==========================================def analyze_window(w_h: dict, m_h: dict, start_idx: int, end_idx: int, beach_dir: str, region: str, spot_name: str, lat: float, moon: dict) -> Optional[dict]:
    if start_idx >= end_idx or start_idx >= len(w_h.get("time",[])): return None
    if not validate_api_data(w_h, m_h, end_idx-start_idx): return None
    
    ws = smooth_series(w_h.get("wind_speed_10m",[])[start_idx:end_idx])
    wd_raw = w_h.get("wind_direction_10m",[])[start_idx:end_idx]
    sh = smooth_series(m_h.get("swell_wave_height",[])[start_idx:end_idx])
    sp = smooth_series(m_h.get("swell_wave_period",[])[start_idx:end_idx])
    sd_raw = m_h.get("swell_wave_direction",[])[start_idx:end_idx]
    pr = smooth_series(w_h.get("surface_pressure",[])[start_idx:end_idx])
    rain = w_h.get("precipitation",[])[start_idx:end_idx]
    w_codes = w_h.get("weather_code",[])[start_idx:end_idx]
    
    if not ws: return None
    
    avg_ws, max_ws = sum(ws)/len(ws), max(ws)
    avg_sh, max_sh = sum(sh)/len(sh), max(sh)
    avg_sp = sum(sp)/len(sp)
    p_now = pr[-1] if pr else 1015.0
    p_trend = pr[-1] - pr[0] if len(pr) > 1 else 0.0
    
    wd_corr = [topographic_correction(w, s, region, spot_name)[0] for w,s in zip(wd_raw,sd_raw)]
    sd_corr = [topographic_correction(w, s, region, spot_name)[1] for w,s in zip(wd_raw,sd_raw)]
    
    beach_deg = dir_to_deg(beach_dir)
    eff_sh = [h * max(0, math.cos(math.radians(angular_diff(d, beach_deg)))) for h,d in zip(sh,sd_corr)]
    avg_eff = sum(eff_sh)/len(eff_sh) if eff_sh else avg_sh
    
    wd_counts = {}
    for w in wd_corr:
        c = classify_wind(w, beach_dir, region)
        wd_counts[c] = wd_counts.get(c,0)+1
    dom_wind = max(wd_counts, key=wd_counts.get)
    
    debris_risk, debris_energy = calculate_debris_energy(w_h, m_h, max(0,start_idx-24), start_idx, beach_dir, region)
    rain_risk, rain_acc = calculate_rain_turbidity(rain)
    confusion = assess_sea_confusion(sum(wd_corr)/len(wd_corr), sum(sd_corr)/len(sd_corr), avg_ws, avg_sh)
    sst = safe_get(m_h.get("sea_surface_temperature",[]), start_idx, 18.0)
    has_lightning = check_thunderstorm_risk(w_codes)
    
    mid_t = w_h.get("time",[])[(start_idx+end_idx)//2] if (start_idx+end_idx)//2 < len(w_h.get("time",[])) else ""
    utc_h = datetime.fromisoformat(mid_t.replace("Z","+00:00")).hour if mid_t else 12
    low_tide = corrected_tide_window(utc_h, region, p_now, avg_ws, dom_wind, moon["tide_amplitude"])
    
    rip_sc = (2 if avg_sp>=12 else 0) + (1 if avg_eff>1.0 else 0) + (2 if low_tide else 0)
    rip_sc *= moon["tide_amplitude"]
    rip = "Confirmed" if rip_sc>=4.5 else ("High" if rip_sc>=3.0 else ("Medium" if rip_sc>=2.0 else "Low"))
    wr = "None" if max_ws<10 else ("Low" if max_ws<=25 else ("High" if max_ws<=45 else "Confirmed"))
    
    red_flags = []
    if has_lightning: red_flags.append("⛈️ خطر صواعق/عواصف رعدية")
    if avg_eff > 1.4 and dom_wind == "Onshore" and avg_sp > 9.0: red_flags.append("سحب الرصاص للشاطئ")
    if max_sh > 1.8 and dom_wind == "Onshore": red_flags.append("خروج أعشاب وأوساخ")
    if max_ws > 38: red_flags.append("رياح تعيق الرمي والثبات")
    if avg_sp >= 12 and low_tide and avg_eff > 1.0: red_flags.append("تيارات سحب مع جزر")
    if rain_risk in ["High","Confirmed"]: red_flags.append(f"ماء معكر/جريان أودية ({rain_acc:.0f}مم)")
    if confusion["level"] == "High": red_flags.append("بحر متقاطع غير مستقر")
    is_red = len(red_flags) > 0
    
    # 🛡️ Safety Veto System
    safety_veto = False
    if has_lightning or max_ws > 50 or (rip == "Confirmed" and moon["tide_amplitude"] > 1.1 and dom_wind == "Onshore"):
        safety_veto = True
    
    score = sum({"None":10,"Low":6,"Medium":3,"High":-2,"Confirmed":-8}.get(r,0) for r in [debris_risk,rip,wr])
    if 0.5 <= avg_eff <= 1.3: score += 8
    elif avg_eff > 1.8: score -= 10
    if -2.5 <= p_trend <= -0.5: score += 6
    elif p_trend > 3.0: score -= 8
    if confusion["level"] == "Medium": score -= 4
    
    ws_var = max(ws) - min(ws) if ws else 0
    sh_var = max(sh) - min(sh) if sh else 0
    data_variance = (ws_var/10.0 + sh_var/1.0) / 2.0
    stability = "مستقر" if data_variance < 0.8 else "متقلب"
    
    if safety_veto:
        v, e = "🚫 خطر/ممنوع", "ظروف تهدد السلامة: صواعق أو رياح عاتية أو تيارات قاتلة. الانسحاب الفوري مطلوب."
    elif is_red:
        v, e = "🚩 علم أحمر", f"غير قابل للصيد: {'، '.join(red_flags)}. غيّر الشاطئ فوراً."
    elif score >= 28 and debris_risk=="None" and wr in ["None","Low"]:
        v, e = "ممتاز", "ظروف مستقرة ومثالية. نشاط أسماك متوقع مع ثبات الطعم."
    elif score >= 18 and "Confirmed" not in [debris_risk,wr]:
        v, e = "جيد", "ظروف مقبولة مع تقلبات طفيفة. انتبه للتيارات."
    elif score >= 8:
        v, e = "صعب", "تقلبات واضحة أو رياح/أمواج مرتفعة. يتطلب خبرة."
    else:
        v, e = "غير مناسب", "ظروف قاسية أو غير مستقرة. يُنصح بالتأجيل."
    
    v, e = adjust_for_sst(sst, v, e)
    
    fc_hours = max(0, (datetime.fromisoformat(mid_t.replace("Z","+00:00")) - datetime.now(timezone.utc)).total_seconds()/3600) if mid_t else 0
    confidence = calculate_confidence(fc_hours, data_variance, stability)
    if confidence < 60 or data_variance > 1.2:
        if v == "ممتاز": v, e = "جيد", e + " (ثقة منخفضة/بيانات متقلبة)"
        elif v == "جيد": v, e = "صعب", e + " (تقلبات سريعة متوقعة)"
        
    sinker = int(min(400, max(30, 50 + avg_eff*45 + avg_ws*1.0 + (25 if dom_wind=="Onshore" else 0) + (30 if rip in ["High","Confirmed"] else 0))))
    
    return {        "avg_wind": round(avg_ws,1), "max_wind": round(max_ws,1), "wind_type": dom_wind,
        "avg_swell": round(avg_sh,2), "max_swell": round(max_sh,2), "effective_swell": round(avg_eff,2),
        "avg_period": round(avg_sp,1), "pressure_now": round(p_now,1), "pressure_trend": round(p_trend,2),
        "sst_c": round(sst,1), "rain_acc_mm": round(rain_acc,1), "has_lightning": has_lightning,
        "risks": {"seaweed": debris_risk, "rip": rip, "wind": wr, "rain_turbidity": rain_risk, "sea_confusion": confusion["level"]},
        "red_flags": red_flags, "is_red_flag": is_red, "safety_veto": safety_veto,
        "verdict": v, "explanation": e, "sinker_g": sinker, "stability": stability,
        "confidence": confidence, "data_variance": round(data_variance,2),
        "debris_energy": round(debris_energy,1), "tide_status": "جزر مصحح" if low_tide else "مد/استقرار",
        "tide_amplitude": moon["tide_amplitude"], "cross_swell_angle": confusion["angle_diff"],
        "direction_confidence": "عالية (±10°)" if region=="سوسة" else ("متوسطة (±15°)" if region in ["تونس","نابل"] else "متوسطة-منخفضة (±20°)")
    }

# ==========================================
# 📡 نماذج ونقاط نهاية
# ==========================================
class AnalyzeReq(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    beach_direction: str = Field(..., pattern=r"^(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)$")
    region: str = Field(..., min_length=1, max_length=20)
    delegation: str = Field(default="", max_length=30)
    @field_validator('beach_direction')
    @classmethod
    def norm_dir(cls, v): return v.strip().upper()

class SpotReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    facing: str = Field(..., pattern=r"^(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW)$")
    region: str = Field(..., min_length=1, max_length=20)
    delegation: str = Field(default="", max_length=30)
    @field_validator('facing')
    @classmethod
    def norm_face(cls, v): return v.strip().upper()

@app.get("/")
async def root(): return {"service":"Tunisia Surfcasting Reference API","version":"6.0.0","status":"online","spots":len(TUNISIAN_SPOTS),"indicators":["Wind","Swell","SST","Pressure","Tide","Debris","Rain","Cross-Swell","Rip","Moon","Lightning","Confidence","SafetyVeto"]}

@app.get("/health")
async def health(req: Request): return JSONResponse({"healthy":True,"ts":datetime.now(timezone.utc).isoformat()})

@app.post("/analyze")
async def analyze(req: AnalyzeReq):
    logger.info(f"Ref Analyze v6: {req.lat},{req.lon},{req.region}/{req.delegation}")
    async with httpx.AsyncClient(timeout=20) as c:
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={req.lat}&longitude={req.lon}&hourly=wind_speed_10m,wind_direction_10m,surface_pressure,precipitation,weather_code,visibility&past_days=2&forecast_days=2&timezone=auto"
        m_url = f"https://marine-api.open-meteo.com/v1/marine?latitude={req.lat}&longitude={req.lon}&hourly=swell_wave_height,swell_wave_period,swell_wave_direction,sea_surface_temperature&past_days=2&forecast_days=2&timezone=auto"
        try:
            w_r, m_r = await asyncio.gather(c.get(w_url), c.get(m_url))
            w_r.raise_for_status(); m_r.raise_for_status()
        except Exception as e:
            raise HTTPException(502, f"Open-Meteo error: {str(e)}")
        
        w_h, m_h = w_r.json().get("hourly",{}), m_r.json().get("hourly",{})
        times = w_h.get("time",[])
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc + timedelta(hours=1)
        now_idx = min(range(len(times)), key=lambda i: abs(datetime.fromisoformat(times[i].replace("Z","+00:00")) - now_utc)) if times else 0
        
        moon = get_moon_data(now_utc)
        morning = analyze_window(w_h, m_h, now_idx, min(now_idx+6, len(times)), req.beach_direction, req.region, req.delegation, req.lat, moon)
        evening = analyze_window(w_h, m_h, min(now_idx+10, len(times)-6), min(now_idx+16, len(times)), req.beach_direction, req.region, req.delegation, req.lat, moon)
        night = analyze_window(w_h, m_h, min(now_idx+16, len(times)-6), min(now_idx+22, len(times)), req.beach_direction, req.region, req.delegation, req.lat, moon)
        
        water_temp = safe_get(m_h.get("sea_surface_temperature",[]), now_idx, 18.0)
        best_window = "الصباحية" if (morning and morning["verdict"] in ["ممتاز","جيد"]) else ("المسائية" if (evening and evening["verdict"] in ["ممتاز","جيد"]) else ("الليلية" if (night and night["verdict"] in ["ممتاز","جيد"]) else "لا توجد نافذة مثالية اليوم"))
        red_periods = [p for p in [morning,evening,night] if p and p["is_red_flag"]]
        migration_advice = "🚨 معظم الفترات تحمل أعلاماً حمراء. يُنصح بتغيير المنطقة أو الانتقال لواجهة معاكسة." if len(red_periods) >= 2 else ""
        
        return {
            "location": {"lat":req.lat,"lon":req.lon,"facing":req.beach_direction,"region":req.region,"delegation":req.delegation},
            "astronomy": {"moon": moon, "water_temp_c": round(water_temp,1)},
            "best_window": best_window, "migration_advice": migration_advice,
            "windows": {"morning": morning, "evening": evening, "night": night},
            "pro_tips": [
                f"نشاط الأسماك مضاعف بـ {moon['activity_boost']}x بسبب طور القمر",
                "استخدم خيطاً أرفع (0.30-0.35mm) إذا كانت الرؤية > 10كم والماء صافٍ",
                "عند ظهور علم أحمر أو خطر صواعق، لا تضيع الوقت: غيّر الواجهة أو انسحب فوراً",
                "الاتجاهات مُصححة طبوغرافياً، والثقة الإحصائية تحمي من المفاجآت"
            ]
        }

@app.post("/best-spots")
async def best_spots(custom: List[SpotReq]):
    spots = TUNISIAN_SPOTS + [s.model_dump() for s in custom]
    results = []
    semaphore = asyncio.Semaphore(3)
    
    async def fetch_spot(s):
        async with semaphore:
            try:
                w = await httpx.AsyncClient(timeout=15).get(f"https://api.open-meteo.com/v1/forecast?latitude={s['lat']}&longitude={s['lon']}&hourly=wind_speed_10m,wind_direction_10m,surface_pressure,precipitation,weather_code&past_days=1&forecast_days=1&timezone=auto")
                m = await httpx.AsyncClient(timeout=15).get(f"https://marine-api.open-meteo.com/v1/marine?latitude={s['lat']}&longitude={s['lon']}&hourly=swell_wave_height,swell_wave_period,swell_wave_direction,sea_surface_temperature&past_days=1&forecast_days=1&timezone=auto")
                w.raise_for_status(); m.raise_for_status()
                w_h, m_h = w.json().get("hourly",{}), m.json().get("hourly",{})
                times = w_h.get("time",[])
                now_idx = min(range(len(times)), key=lambda i: abs(datetime.fromisoformat(times[i].replace("Z","+00:00")) - datetime.now(timezone.utc))) if times else 0
                moon = get_moon_data(datetime.now(timezone.utc))
                res = analyze_window(w_h, m_h, now_idx, min(now_idx+8, len(times)), s["facing"], s["region"], s["name"], s["lat"], moon)
                if res:
                    res["name"] = s["name"]; res["region"] = s["region"]; res["delegation"] = s.get("delegation","")
                    return res
            except Exception as e:
                logger.warning(f"Skip {s.get('name')}: {e}")
            return None

    tasks = [fetch_spot(s) for s in spots]
    raw_results = await asyncio.gather(*tasks)
    results = [r for r in raw_results if r is not None]
    
    results.sort(key=lambda x: sum({"ممتاز":30,"جيد":20,"صعب":10}.get(x["verdict"],0) for x in [x]), reverse=True)
    for i,r in enumerate(results,1): r["rank"]=i
    return results

@app.exception_handler(HTTPException)
async def err_h(req: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error":True,"code":exc.status_code,"detail":exc.detail})

if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT",8000)), reload=False)