# ==============================================================================
# TUNISIAN SURFCASTING DECISION ENGINE — main.py v3.0 CORRECTED
# كل الأخطاء المكتشفة في الجرد تم إصلاحها
# ==============================================================================

import math
import datetime
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(
    title="Tunisian Surfcasting Decision Engine",
    description="Scientific verdict system for Tunisian surfcasters — v3.0",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# CONSTANTS
# ==============================================================================
# FIX #7/#14: كل العتبات مبنية الآن على km/h
# 1 knot = 1.852 km/h
# 12 knots = 22.2 km/h  (عتبة تراكم العشب)
# 25 knots = 46.3 km/h  (عتبة الريح القوية)
WIND_WEED_THRESHOLD_KMH = 22.2   # يعادل 12 عقدة
WIND_STRONG_KMH = 46.3           # يعادل 25 عقدة
WIND_GAUGE_MAX_KMH = 74.0        # يعادل 40 عقدة — max gauge

# ==============================================================================
# BEACH DATABASE
# ==============================================================================
BEACH_DB = {
    "Bizerte": [
        {
            "name": "Cap Blanc / Ras Angela",
            "lat": 37.345, "lon": 9.803,
            "shore_normal": 350.0,
            "shelter_factor": 0.95,
            "tidal_regime": "micro",
            "bottom_type": "rocky_sand",
            "description_fr": "Cap le plus au nord de l'Afrique, exposition maximale nord."
        },
        {
            "name": "Ghar El Melh (Porto Farina)",
            "lat": 37.193, "lon": 10.177,
            "shore_normal": 40.0,
            "shelter_factor": 0.60,
            "tidal_regime": "micro",
            "bottom_type": "muddy_sand",
            "description_fr": "Lagon semi-fermé, facteur d'abri élevé."
        },
        {
            "name": "Raf Raf",
            "lat": 37.175, "lon": 10.185,
            "shore_normal": 55.0,
            "shelter_factor": 0.85,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Plage de sable fin, exposition NE aux houles siciliennes."
        },
        {
            "name": "Sidi Ali El Mekki",
            "lat": 37.153, "lon": 10.097,
            "shore_normal": 15.0,
            "shelter_factor": 0.80,
            "tidal_regime": "micro",
            "bottom_type": "rocky_sand",
            "description_fr": "Baie semi-ouverte, fond rocheux."
        },
    ],
    "Nabeul": [
        {
            "name": "Kelibia — Plage Mansourah",
            "lat": 36.876, "lon": 11.118,
            "shore_normal": 70.0,
            "shelter_factor": 0.92,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Plage ouverte NE, grosse houle sicilienne."
        },
        {
            "name": "Kelibia — Petit Paris",
            "lat": 36.896, "lon": 11.112,
            "shore_normal": 50.0,
            "shelter_factor": 0.88,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Anse nord de Kelibia, légèrement protégée."
        },
        {
            "name": "Retiba",
            "lat": 36.745, "lon": 11.045,
            "shore_normal": 90.0,
            "shelter_factor": 1.00,
            "tidal_regime": "micro",
            "bottom_type": "coarse_rocky_sand",
            "description_fr": "Côte ouverte plein Est, aucun abri topographique."
        },
        {
            "name": "Kerkouane",
            "lat": 36.960, "lon": 11.073,
            "shore_normal": 30.0,
            "shelter_factor": 0.78,
            "tidal_regime": "micro",
            "bottom_type": "rocky",
            "description_fr": "Site archéologique punique, côte rocheuse NNE."
        },
        {
            "name": "Sidi Mahrsi",
            "lat": 36.820, "lon": 11.090,
            "shore_normal": 80.0,
            "shelter_factor": 0.90,
            "tidal_regime": "micro",
            "bottom_type": "mixed_rocky_sand",
            "description_fr": "Village de pêcheurs, fonds mixtes."
        },
        {
            "name": "Hammamet Nord",
            "lat": 36.430, "lon": 10.630,
            "shore_normal": 110.0,
            "shelter_factor": 0.48,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Golfe très protégé par Cap Bon. Vagues atténuées 52%."
        },
        {
            "name": "Hammamet Sud (Yasmine)",
            "lat": 36.370, "lon": 10.600,
            "shore_normal": 120.0,
            "shelter_factor": 0.44,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Golfe d'Hammamet profond, abri maximal."
        },
        {
            "name": "Nabeul Plage",
            "lat": 36.456, "lon": 10.735,
            "shore_normal": 100.0,
            "shelter_factor": 0.55,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Plage centrale de Nabeul, exposée ESE."
        },
    ],
    "Tunis_Ariana_BenArous": [
        {
            "name": "La Marsa",
            "lat": 36.878, "lon": 10.326,
            "shore_normal": 35.0,
            "shelter_factor": 0.70,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Golfe de Tunis, exposition NNE modérée."
        },
        {
            "name": "Gammarth",
            "lat": 36.912, "lon": 10.278,
            "shore_normal": 20.0,
            "shelter_factor": 0.72,
            "tidal_regime": "micro",
            "bottom_type": "rocky_sand",
            "description_fr": "Cap Gammarth, fond rocheux."
        },
        {
            "name": "Raoued",
            "lat": 36.892, "lon": 10.215,
            "shore_normal": 350.0,
            "shelter_factor": 0.65,
            "tidal_regime": "micro",
            "bottom_type": "muddy_sand",
            "description_fr": "Côte nord Golfe de Tunis."
        },
        {
            "name": "Rades / Ben Arous",
            "lat": 36.762, "lon": 10.271,
            "shore_normal": 90.0,
            "shelter_factor": 0.50,
            "tidal_regime": "micro",
            "bottom_type": "muddy",
            "description_fr": "Côte industrielle Golfe de Tunis."
        },
    ],
    "Sousse": [
        {
            "name": "Sousse Nord",
            "lat": 35.860, "lon": 10.640,
            "shore_normal": 95.0,
            "shelter_factor": 0.75,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Côte centrale est, exposition ESE."
        },
        {
            "name": "Port El Kantaoui",
            "lat": 35.896, "lon": 10.592,
            "shore_normal": 90.0,
            "shelter_factor": 0.70,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Marina artificielle avec digue, abri partiel."
        },
        {
            "name": "Akouda",
            "lat": 35.923, "lon": 10.569,
            "shore_normal": 85.0,
            "shelter_factor": 0.78,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Plage ouverte, bon fond pour Mankous/Warata."
        },
    ],
    "Monastir": [
        {
            "name": "Monastir Corniche",
            "lat": 35.764, "lon": 10.826,
            "shore_normal": 100.0,
            "shelter_factor": 0.72,
            "tidal_regime": "micro",
            "bottom_type": "rocky_sand",
            "description_fr": "Côte rocheuse de Monastir, fond mixte."
        },
        {
            "name": "Khniss (Monastir Sud)",
            "lat": 35.720, "lon": 10.858,
            "shore_normal": 110.0,
            "shelter_factor": 0.68,
            "tidal_regime": "micro",
            "bottom_type": "rocky_sand",
            "description_fr": "Pointe sud Monastir, fond rocheux profond."
        },
    ],
    "Mahdia": [
        {
            "name": "Mahdia Cap",
            "lat": 35.500, "lon": 11.065,
            "shore_normal": 75.0,
            "shelter_factor": 0.88,
            "tidal_regime": "micro",
            "bottom_type": "rocky",
            "description_fr": "Cap rocheux exposé, fonds profonds."
        },
        {
            "name": "Mahdia Plage Centrale",
            "lat": 35.495, "lon": 11.043,
            "shore_normal": 90.0,
            "shelter_factor": 0.80,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Longue plage de sable blanc."
        },
        {
            "name": "Ras Dimass",
            "lat": 35.460, "lon": 11.020,
            "shore_normal": 95.0,
            "shelter_factor": 0.85,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Cap isolé, excellent fond pour Qaros."
        },
    ],
    "Sfax": [
        {
            "name": "Sfax Sidi Mansour",
            "lat": 34.800, "lon": 10.830,
            "shore_normal": 100.0,
            "shelter_factor": 0.58,
            "tidal_regime": "micro",
            "bottom_type": "muddy_sand",
            "description_fr": "Abrité par îles Kerkennah."
        },
        {
            "name": "Kerkennah — Sidi Fredj",
            "lat": 34.720, "lon": 11.230,
            "shore_normal": 150.0,
            "shelter_factor": 0.65,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Île Kerkennah, côte SE."
        },
    ],
    "Gabes": [
        {
            "name": "Gabes Plage",
            "lat": 33.887, "lon": 10.097,
            "shore_normal": 95.0,
            "shelter_factor": 0.72,
            "tidal_regime": "macro",
            "bottom_type": "muddy_sand",
            "description_fr": "MARÉES >1.5m. Mer montante décisive."
        },
        {
            "name": "El Hamma (Golfe de Gabes Nord)",
            "lat": 33.951, "lon": 9.865,
            "shore_normal": 80.0,
            "shelter_factor": 0.60,
            "tidal_regime": "macro",
            "bottom_type": "muddy",
            "description_fr": "Fond vaseux profond. Marées critiques."
        },
    ],
    "Medenine": [
        {
            "name": "Zarzis Plage",
            "lat": 33.510, "lon": 11.110,
            "shore_normal": 110.0,
            "shelter_factor": 0.80,
            "tidal_regime": "macro",
            "bottom_type": "fine_sand",
            "description_fr": "Plage de Zarzis, marées marquées."
        },
        {
            "name": "Djerba — Plage Seguia",
            "lat": 33.780, "lon": 10.990,
            "shore_normal": 140.0,
            "shelter_factor": 0.70,
            "tidal_regime": "macro",
            "bottom_type": "fine_sand",
            "description_fr": "Île de Djerba, côte SE."
        },
        {
            "name": "Djerba — El Abassia (Nord)",
            "lat": 33.870, "lon": 10.870,
            "shore_normal": 30.0,
            "shelter_factor": 0.75,
            "tidal_regime": "macro",
            "bottom_type": "rocky_sand",
            "description_fr": "Côte nord Djerba, fond rocheux."
        },
        {
            "name": "Ras Jdir",
            "lat": 33.155, "lon": 11.490,
            "shore_normal": 90.0,
            "shelter_factor": 0.90,
            "tidal_regime": "macro",
            "bottom_type": "coarse_sand",
            "description_fr": "Plage isolée extrême sud-est."
        },
    ],
}

# ==============================================================================
# PYDANTIC MODELS
# ==============================================================================
class SpotRequest(BaseModel):
    lat: float
    lon: float

class GovernorateRequest(BaseModel):
    governorate: str

# ==============================================================================
# FIX #1 #2 #6: OPEN-METEO API FETCHER — CORRIGÉ
# - wind_speed_unit: "kmh" (correct API parameter)
# - Suppression de "swell_wave_peak_period" (n'existe pas)
# - Remplacement de past_days par start_date/end_date (marine API)
# - Timezone: Africa/Tunis pour cohérence
# ==============================================================================
def fetch_marine_and_weather_data(lat: float, lon: float) -> dict:
    """
    Fetches combined marine and weather data from Open-Meteo.
    FIX: wind_speed_unit=kmh | correct marine variables | start/end dates
    """
    today = datetime.date.today()
    two_days_ago = today - datetime.timedelta(days=2)
    seven_days_later = today + datetime.timedelta(days=7)

    # Marine API — variables confirmées dans la doc officielle
    marine_url = "https://marine-api.open-meteo.com/v1/marine"
    marine_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": (
            "wave_height,wave_direction,wave_period,"
            "wind_wave_height,wind_wave_direction,wind_wave_period,"
            "swell_wave_height,swell_wave_direction,swell_wave_period"
        ),
        # FIX #6: Marine API utilise start_date/end_date, pas past_days
        "start_date": two_days_ago.isoformat(),
        "end_date": seven_days_later.isoformat(),
        "timezone": "Africa/Tunis"
    }

    # Weather API
    weather_url = "https://api.open-meteo.com/v1/forecast"
    weather_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m",
        # FIX #1: "kmh" est le paramètre correct (pas "kn")
        "wind_speed_unit": "kmh",
        "past_days": 2,
        "forecast_days": 7,
        "timezone": "Africa/Tunis"
    }

    try:
        m_resp = requests.get(marine_url, params=marine_params, timeout=20)
        m_resp.raise_for_status()
        marine_data = m_resp.json()
        if "error" in marine_data and marine_data["error"]:
            raise HTTPException(status_code=502,
                detail=f"Marine API error: {marine_data.get('reason', 'Unknown')}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Marine API connection error: {str(e)}")

    try:
        w_resp = requests.get(weather_url, params=weather_params, timeout=20)
        w_resp.raise_for_status()
        weather_data = w_resp.json()
        if "error" in weather_data and weather_data["error"]:
            raise HTTPException(status_code=502,
                detail=f"Weather API error: {weather_data.get('reason', 'Unknown')}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Weather API connection error: {str(e)}")

    return {"marine": marine_data, "weather": weather_data}

# ==============================================================================
# VECTOR MATHEMATICS
# ==============================================================================
def angular_delta(bearing_from_deg: float, shore_normal_deg: float) -> float:
    """
    Computes absolute minimum angular difference [0,180] between
    incoming energy direction and outward shore normal.
    FIX #9: Ajout de validation des entrées None/invalides
    """
    try:
        bearing_from_deg = float(bearing_from_deg)
        shore_normal_deg = float(shore_normal_deg)
    except (TypeError, ValueError):
        return 90.0  # Valeur neutre en cas d'erreur

    energy_to_dir = (bearing_from_deg + 180.0) % 360.0
    diff = abs(energy_to_dir - shore_normal_deg) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff

def classify_vector(delta: float) -> str:
    if delta < 60.0:
        return "ONSHORE"
    elif delta <= 120.0:
        return "LONGSHORE"
    else:
        return "OFFSHORE"

# ==============================================================================
# FIX #3: TIMEZONE-SAFE INDEX FINDER
# Tunis = UTC+1. API retourne des heures en Africa/Tunis.
# On cherche l'heure actuelle en heure locale tunisienne.
# ==============================================================================
def find_current_hour_index(times: list) -> int:
    """
    FIX #3: Trouve l'index de l'heure actuelle dans les données API.
    L'API renvoie les temps en Africa/Tunis (UTC+1).
    On convertit l'UTC actuel en heure tunisienne pour la comparaison.
    """
    # Heure actuelle en Tunis (UTC+1, pas DST en Tunisie)
    tunis_offset = datetime.timedelta(hours=1)
    now_tunis = datetime.datetime.utcnow() + tunis_offset
    target_str = now_tunis.strftime("%Y-%m-%dT%H:00")

    # Cherche la correspondance exacte d'abord
    for i, t in enumerate(times):
        if t == target_str:
            return i

    # Si pas de correspondance exacte, cherche le plus proche
    best_idx = 0
    best_diff = float("inf")
    for i, t in enumerate(times):
        try:
            dt = datetime.datetime.fromisoformat(t)
            diff = abs((dt - now_tunis).total_seconds())
            if diff < best_diff:
                best_diff = diff
                best_idx = i
        except Exception:
            continue
    return best_idx

# ==============================================================================
# FIX #10: TIDAL MODEL — Phase de référence corrigée
# On utilise une date de référence de marée haute connue pour Gabès:
# Marée haute de référence à Gabès: 2024-01-01 à 02:30 UTC+1
# Période M2 = 12.4206 heures
# ==============================================================================
def compute_tidal_state(tidal_regime: str, dt: datetime.datetime) -> dict:
    """
    Modèle harmonique M2 simplifié pour la Tunisie.
    FIX #10: Phase de référence calibrée sur une marée haute documentée.
    dt doit être en heure locale Tunis (UTC+1, naive).
    """
    M2_PERIOD_H = 12.4206

    if tidal_regime == "macro":
        amplitude = 0.85   # demi-marnage Gabès ~1.7m total
        # Date de référence haute mer Gabès: 2024-01-01 02:30 heure locale
        ref_high_tide = datetime.datetime(2024, 1, 1, 2, 30, 0)
    else:
        amplitude = 0.12   # microtidal
        ref_high_tide = datetime.datetime(2024, 1, 1, 1, 0, 0)

    # Heures depuis la marée haute de référence
    hours_since_ref = (dt - ref_high_tide).total_seconds() / 3600.0

    omega = 2.0 * math.pi / M2_PERIOD_H
    height = amplitude * math.cos(omega * hours_since_ref)
    velocity = -amplitude * omega * math.sin(omega * hours_since_ref)

    if height > 0.7 * amplitude:
        state = "HIGH_TIDE"
    elif height < -0.7 * amplitude:
        state = "LOW_TIDE"
    elif velocity > 0:
        state = "RISING"
    else:
        state = "FALLING"

    # Heures jusqu'à la prochaine marée haute
    phase_in_cycle = hours_since_ref % M2_PERIOD_H
    hours_to_high = (M2_PERIOD_H - phase_in_cycle) % M2_PERIOD_H
    if hours_to_high > M2_PERIOD_H / 2:
        hours_to_high = M2_PERIOD_H - hours_to_high

    # Boost de pêche selon état de marée
    if hours_to_high <= 2.0 and state in ("RISING", "HIGH_TIDE"):
        tidal_boost = 1.30
    elif state == "RISING":
        tidal_boost = 1.15
    elif state == "HIGH_TIDE":
        tidal_boost = 1.10
    else:
        tidal_boost = 0.85

    return {
        "height_m": round(height, 3),
        "state": state,
        "tidal_boost": round(tidal_boost, 2),
        "hours_to_high": round(hours_to_high, 1),
        "regime": tidal_regime,
        "amplitude_m": amplitude
    }

# ==============================================================================
# FIX #4 #5: SEAWEED & RIP INDEX — pytz supprimé, comparaison naive datetime
# FIX #7: Seuil vent en km/h (22.2 au lieu de 12)
# ==============================================================================
def compute_seaweed_and_rip_index(
    times: list, wave_heights: list, wave_periods: list,
    wave_dirs: list, wind_speeds_kmh: list, wind_dirs: list,
    shore_normal: float
) -> dict:
    """
    Calcul de l'index d'algues et de courant de rip sur 48h.
    FIX #4: Import pytz supprimé — tout en naive datetime UTC+1
    FIX #5: Pas de comparaison aware vs naive
    FIX #7: Seuil vent = 22.2 km/h (équivalent 12 noeuds)
    """
    # Heure actuelle en Tunis (naive, UTC+1)
    tunis_offset = datetime.timedelta(hours=1)
    now_tunis = datetime.datetime.utcnow() + tunis_offset
    cutoff_48h = now_tunis - datetime.timedelta(hours=48)
    cutoff_6h = now_tunis - datetime.timedelta(hours=6)

    onshore_wind_hours = 0.0
    total_onshore_energy = 0.0
    last_6h_offshore_energy = 0.0
    last_6h_onshore_energy = 0.0
    rip_energy_accumulator = 0.0
    rip_peak_hours = 0

    n = min(len(times), len(wave_heights), len(wave_dirs),
            len(wind_speeds_kmh), len(wind_dirs), len(wave_periods))

    for i in range(n):
        try:
            # FIX #5: Tous les datetime sont naifs (pas de tz info)
            t_str = times[i]
            # Supprimer le tzinfo si présent dans la chaîne
            if "+" in t_str:
                t_str = t_str.split("+")[0]
            elif t_str.endswith("Z"):
                t_str = t_str[:-1]
            dt = datetime.datetime.fromisoformat(t_str)
        except Exception:
            continue

        # Filtrer: uniquement les 48h passées
        if dt > now_tunis or dt < cutoff_48h:
            continue

        wh = wave_heights[i] if wave_heights[i] is not None else 0.0
        wp = wave_periods[i] if wave_periods[i] is not None else 6.0
        wd = wave_dirs[i] if wave_dirs[i] is not None else shore_normal
        ws_kmh = wind_speeds_kmh[i] if wind_speeds_kmh[i] is not None else 0.0
        wdir = wind_dirs[i] if wind_dirs[i] is not None else shore_normal

        wave_delta = angular_delta(wd, shore_normal)
        wind_delta = angular_delta(wdir, shore_normal)
        wave_energy = (wh ** 2) * wp
        is_in_last_6h = dt >= cutoff_6h

        if wave_delta < 60.0:
            total_onshore_energy += wave_energy
            if is_in_last_6h:
                last_6h_onshore_energy += wave_energy
            # FIX #7: seuil en km/h
            if wind_delta < 60.0 and ws_kmh > WIND_WEED_THRESHOLD_KMH:
                onshore_wind_hours += 1.0

        if wave_delta > 120.0 and is_in_last_6h:
            last_6h_offshore_energy += wave_energy

        if 20.0 < wave_delta < 80.0 and wh > 1.2 and wp > 8.5:
            rip_energy_accumulator += wave_energy
            rip_peak_hours += 1

    # Calcul index algues
    REF_ENERGY_48H = (1.5 ** 2) * 8.0 * 24
    base_weed = min(1.0, total_onshore_energy / (REF_ENERGY_48H + 1e-6))

    if onshore_wind_hours >= 18.0:
        escalation = 1.0 + 0.8 * math.exp((onshore_wind_hours - 18.0) / 12.0)
        base_weed = min(1.0, base_weed * escalation)

    offshore_clearing_ratio = last_6h_offshore_energy / (
        last_6h_offshore_energy + last_6h_onshore_energy + 1e-6
    )
    clearing_factor = 1.0 - (0.35 * offshore_clearing_ratio)
    seaweed_index = base_weed * clearing_factor
    seaweed_pct = round(seaweed_index * 100.0, 1)
    floating_debris_warning = offshore_clearing_ratio > 0.5 and seaweed_pct > 15.0

    # Calcul rip current
    RIP_REF_ENERGY = (1.5 ** 2) * 10.0 * 24
    rip_base = min(1.0, rip_energy_accumulator / (RIP_REF_ENERGY + 1e-6))
    rip_critical = rip_peak_hours >= 6
    rip_danger = round(rip_base * 100.0, 1)
    if rip_critical:
        rip_danger = max(rip_danger, 65.0)
    rip_safety = round(max(0.0, 100.0 - rip_danger), 1)

    return {
        "seaweed_pct": seaweed_pct,
        "onshore_wind_hours_48h": round(onshore_wind_hours, 1),
        "floating_debris_warning": floating_debris_warning,
        "rip_danger_pct": rip_danger,
        "rip_safety_pct": rip_safety,
        "rip_critical": rip_critical,
        "rip_peak_hours_48h": rip_peak_hours
    }

# ==============================================================================
# FISH ACTIVITY MATRIX
# FIX #7: wind thresholds maintenant en km/h
# ==============================================================================
def compute_fish_matrix(
    wave_h_adj: float,
    wave_period: float,
    wind_speed_kmh: float,   # FIX: maintenant en km/h
    wind_delta: float,
    seaweed_pct: float,
    tidal_boost: float,
    bottom_type: str,
    rip_safety: float
) -> dict:
    weed_penalty = max(0.0, 1.0 - (seaweed_pct / 100.0) * 0.8)
    safety_factor = rip_safety / 100.0

    # WARATA (Dorade Royale)
    w_wave = 1.0
    if wave_h_adj < 0.2:
        w_wave = 0.4
    elif wave_h_adj <= 1.2:
        w_wave = 0.5 + 0.5 * math.sin(math.pi * (wave_h_adj - 0.2) / 1.0)
    else:
        w_wave = max(0.2, 1.0 - (wave_h_adj - 1.2) * 0.4)
    w_bottom = 1.0 if "sand" in bottom_type or "rocky" in bottom_type else 0.6
    warata_score = round(min(100.0, w_wave * weed_penalty * tidal_boost * w_bottom * safety_factor * 100.0), 1)

    # MANKOUS (Marbré)
    mk_wave = 1.0
    if wave_h_adj < 0.15:
        mk_wave = 0.35
    elif wave_h_adj <= 1.5:
        mk_wave = 0.4 + 0.6 * (wave_h_adj / 1.5)
    else:
        mk_wave = max(0.3, 1.0 - (wave_h_adj - 1.5) * 0.35)
    mk_bottom = 1.0 if "sand" in bottom_type else 0.65
    mankous_score = round(min(100.0, mk_wave * weed_penalty * 0.9 * mk_bottom * safety_factor * 100.0), 1)

    # QAROS (Loup / Bar)
    q_wave = 1.0
    if wave_h_adj < 0.3:
        q_wave = 0.25
    elif wave_h_adj <= 2.0:
        q_wave = 0.3 + 0.7 * (wave_h_adj / 2.0)
    else:
        q_wave = 0.9
    q_wind = 1.1 if wind_delta < 60.0 else 0.8
    q_bottom = 1.0 if "rocky" in bottom_type else 0.75
    qaros_score = round(min(100.0, q_wave * q_wind * weed_penalty * tidal_boost * q_bottom * safety_factor * 100.0), 1)

    # SORRA / QORADH (Toadfish)
    s_wave = 0.85 if wave_h_adj < 1.0 else 0.60
    s_bottom = 1.0 if "muddy" in bottom_type or "sand" in bottom_type else 0.5
    sorra_score = round(min(100.0, s_wave * s_bottom * tidal_boost * 0.7 * 100.0), 1)
    sorra_alert = sorra_score > 40.0

    # BOURI (Mulet)
    b_wave = 1.0 if wave_h_adj < 0.6 else max(0.3, 1.0 - (wave_h_adj - 0.6) * 0.5)
    b_turbidity = 1.1 if seaweed_pct > 20.0 else 0.9
    bouri_score = round(min(100.0, b_wave * b_turbidity * tidal_boost * 100.0), 1)

    # DOMIBAK (Pagre)
    d_wave = 1.0
    if wave_h_adj > 2.0:
        d_wave = max(0.3, 1.0 - (wave_h_adj - 2.0) * 0.4)
    elif wave_h_adj < 0.2:
        d_wave = 0.5
    d_bottom = 1.0 if "rocky" in bottom_type else 0.55
    domibak_score = round(min(100.0, d_wave * weed_penalty * tidal_boost * d_bottom * safety_factor * 100.0), 1)

    return {
        "Warata_Dorade": warata_score,
        "Mankous_Marbre": mankous_score,
        "Qaros_Loup": qaros_score,
        "Sorra_Qoradh": sorra_score,
        "sorra_line_cut_alert": sorra_alert,
        "Bouri_Mulet": bouri_score,
        "Domibak_Pagre": domibak_score,
    }

# ==============================================================================
# VERDICT ENGINE
# FIX: wind_speed maintenant en km/h dans le rapport
# ==============================================================================
def compute_verdict_and_report(
    beach: dict, current_hour_data: dict, seaweed_data: dict,
    tidal_data: dict, fish_matrix: dict, wave_delta: float,
    wind_delta: float, swell_delta: float, wave_classification: str,
    adj_wave_height: float, forecast_summary: list,
) -> dict:
    score = 100.0
    penalties = []
    bonuses = []

    # P1: Seaweed Penalty
    if seaweed_data["seaweed_pct"] > 70:
        score -= 35
        penalties.append(f"عشب بحري حرج ({seaweed_data['seaweed_pct']}%) | Algues CRITIQUES")
    elif seaweed_data["seaweed_pct"] > 40:
        score -= 20
        penalties.append(f"عشب بحري مرتفع ({seaweed_data['seaweed_pct']}%) | Algues ÉLEVÉES")
    elif seaweed_data["seaweed_pct"] > 20:
        score -= 8
        penalties.append(f"عشب بحري معتدل ({seaweed_data['seaweed_pct']}%) | Algues MODÉRÉES")

    if seaweed_data["floating_debris_warning"]:
        score -= 5
        penalties.append("حطام طافٍ متبقٍّ | Débris flottants résiduels")

    # P2: Rip Current Penalty
    if seaweed_data["rip_critical"]:
        score -= 30
        penalties.append(f"خطر تيارات قطع حرجة ({seaweed_data['rip_peak_hours_48h']}h) | Courants de rip CRITIQUES")
    elif seaweed_data["rip_danger_pct"] > 50:
        score -= 15
        penalties.append(f"خطر تيارات متوسط ({seaweed_data['rip_danger_pct']}%) | Rip danger ÉLEVÉ")

    # P3: Longshore Drift
    if wave_classification == "LONGSHORE":
        score -= 25
        penalties.append(f"دريفت ساحلي شديد Δ={wave_delta:.1f}° | Dérive longshore SÉVÈRE — plomb instable")

    if classify_vector(wind_delta) == "LONGSHORE":
        score -= 10
        penalties.append(f"ريح طولية ساحلية Δ={wind_delta:.1f}° | Vent parallèle — embrouillement lignes")

    # P4: Wave Height Penalty
    if adj_wave_height > 2.5:
        score -= 20
        penalties.append(f"أمواج خطيرة ({adj_wave_height:.2f}m) | Vagues DANGEREUSES")
    elif adj_wave_height > 1.8:
        score -= 10
        penalties.append(f"أمواج قوية ({adj_wave_height:.2f}m) | Vagues FORTES")

    # B1: Onshore Bonus
    if wave_classification == "ONSHORE" and 0.3 <= adj_wave_height <= 1.5:
        score += 10
        bonuses.append("موجة شاطئية مثالية | Vague onshore OPTIMALE")

    # B2: Tidal Bonus
    if tidal_data["state"] == "RISING":
        score += 8
        bonuses.append(f"مد صاعد — ذروة نشاط السمك | Mer MONTANTE (H+{tidal_data['hours_to_high']}h)")
    elif tidal_data["state"] == "HIGH_TIDE":
        score += 5
        bonuses.append("مد عالٍ | Haute mer active")

    # B3: Fish Bonus
    top_fish = max(fish_matrix["Warata_Dorade"],
                   fish_matrix["Mankous_Marbre"],
                   fish_matrix["Qaros_Loup"])
    if top_fish > 75:
        score += 8
        bonuses.append(f"نشاط سمكي ممتاز ({top_fish:.0f}%) | Activité piscicole EXCELLENTE")
    elif top_fish > 50:
        score += 4
        bonuses.append(f"نشاط سمكي جيد ({top_fish:.0f}%) | Activité piscicole BONNE")

    final_score = round(max(0.0, min(100.0, score)), 1)

    if final_score >= 55:
        verdict_en = "SPOT_APPROVED"
        verdict_ar = "✅ أعزل السيرف"
        verdict_fr = "✅ SPOT APPROUVÉ"
    else:
        verdict_en = "CHANGE_SPOT"
        verdict_ar = "🚫 بدل السپوت"
        verdict_fr = "🚫 CHANGEZ DE SPOT"

    # FIX: عرض سرعة الريح بالـ km/h في التقرير
    wind_kmh = current_hour_data.get("wind_speed_kmh", 0.0)
    wind_kn_equiv = round(wind_kmh / 1.852, 1)

    report_lines = [
        "━━━ تقرير القرار العلمي | Rapport de Décision Scientifique ━━━",
        f"📍 الموقع: {beach['name']}",
        f"   {beach['description_fr']}",
        f"🕐 التوقيت: {(datetime.datetime.utcnow() + datetime.timedelta(hours=1)).strftime('%Y-%m-%d %H:%M')} (Tunis)",
        "",
        "── المتجهات الهيدروديناميكية | Vecteurs Hydrodynamiques ──",
        f"🌊 ارتفاع الموجة: {current_hour_data.get('wave_height', 0):.2f}m (خام) → {adj_wave_height:.2f}m (معدّل × عامل حماية {beach['shelter_factor']})",
        f"   Vague brute: {current_hour_data.get('wave_height', 0):.2f}m → Ajustée: {adj_wave_height:.2f}m (shelter ×{beach['shelter_factor']})",
        f"⏱️ دورة الموجة: {current_hour_data.get('wave_period', 0):.1f}s",
        f"🧭 اتجاه الموجة: {current_hour_data.get('wave_direction', 0):.0f}° → Δ={wave_delta:.1f}° → {wave_classification}",
        f"💨 الريح: {wind_kmh:.1f} كم/س ({wind_kn_equiv} عقدة) من {current_hour_data.get('wind_direction', 0):.0f}°",
        f"   Vent: {wind_kmh:.1f} km/h ({wind_kn_equiv} kn) de {current_hour_data.get('wind_direction', 0):.0f}°",
        f"🌐 تضخم: {current_hour_data.get('swell_height', 0):.2f}m / {current_hour_data.get('swell_period', 0):.1f}s → Δ={swell_delta:.1f}° → {classify_vector(swell_delta)}",
        "",
        "── المد والجزر | Marées ──",
        f"🌊 النظام: {'ماكروتيدال (مدّ كبير — خليج قابس)' if tidal_data['regime'] == 'macro' else 'ميكروتيدال (مدّ طفيف — الساحل الشمالي/الشرقي)'}",
        f"   Régime: {'Macrotidal (Golfe de Gabès, marnage >1.5m)' if tidal_data['regime'] == 'macro' else 'Microtidal (côte nord/est, marnage <0.3m)'}",
        f"   الحالة: {tidal_data['state']} | الارتفاع: {tidal_data['height_m']}m | مد عالٍ في: {tidal_data['hours_to_high']}h | مضاعف النشاط: ×{tidal_data['tidal_boost']}",
        "",
        "── مؤشرات بيئية | Indices Environnementaux ──",
        f"🪸 عشب بحري (هاشيش/زريق): {seaweed_data['seaweed_pct']}% | ساعات الرياح الشاطئية (48h): {seaweed_data['onshore_wind_hours_48h']}h",
        f"   Algues (Hachich/Zrayg): {seaweed_data['seaweed_pct']}% | Heures vent onshore (48h): {seaweed_data['onshore_wind_hours_48h']}h",
        f"🌀 خطر تيارات القطع: {seaweed_data['rip_danger_pct']}% | سلامة: {seaweed_data['rip_safety_pct']}%",
    ]

    if seaweed_data["rip_critical"]:
        report_lines.append("   ⚠️ خطر حرج: كسر الحواجز الرملية نشط! خطر مميت حتى في مظهر الهدوء!")
        report_lines.append("   ⚠️ CRITIQUE: Rupture de banc de sable active! Danger même si mer calme en apparence!")

    report_lines += [
        "",
        "── نشاط الأسماك | Activité Piscicole ──",
        f"🐟 وراطة (Dorade):       {fish_matrix['Warata_Dorade']}%",
        f"🐟 منقوس (Marbré):       {fish_matrix['Mankous_Marbre']}%",
        f"🐟 قاروس (Loup/Bar):     {fish_matrix['Qaros_Loup']}%",
        f"🐟 بوري (Mulet):         {fish_matrix['Bouri_Mulet']}%",
        f"🐟 دومبك (Pagre):        {fish_matrix['Domibak_Pagre']}%",
        f"⚠️  صرّة/قرداح (Toadfish): {fish_matrix['Sorra_Qoradh']}%",
    ]

    if fish_matrix["sorra_line_cut_alert"]:
        report_lines.append("   🔴 تحذير: احتمال عضة قرداح وقطع الخيط! استخدم خيطاً مضفراً (Tresse/Braid) حتماً!")
        report_lines.append("   🔴 ALERTE SORRA: Coupe monofilament quasi-certaine! Utilisez du tressé obligatoirement!")

    if penalties:
        report_lines += ["", "── عوامل الخصم | Pénalités ──"]
        for p in penalties:
            report_lines.append(f"  ❌ {p}")

    if bonuses:
        report_lines += ["", "── عوامل الإضافة | Bonus ──"]
        for b in bonuses:
            report_lines.append(f"  ✅ {b}")

    report_lines += [
        "",
        f"── النتيجة النهائية | Score Final: {final_score}/100 ──",
        "=" * 52,
        f"  {verdict_ar}",
        f"  {verdict_fr}",
        "=" * 52,
    ]

    if forecast_summary:
        report_lines += ["", "── أفضل 3 نوافذ صيد (7 أيام) | Meilleures fenêtres (7j) ──"]
        for entry in forecast_summary[:3]:
            report_lines.append(
                f"  📅 {entry['time']} | Vague: {entry['wave_h']:.2f}m | Score: {entry['score']:.0f}/100"
            )

    return {
        "score": final_score,
        "verdict": verdict_en,
        "verdict_ar": verdict_ar,
        "verdict_fr": verdict_fr,
        "report": "\n".join(report_lines),
        "penalties": penalties,
        "bonuses": bonuses,
    }

# ==============================================================================
# CORE ANALYSIS ENGINE — FIX #3 intégré
# ==============================================================================
def analyze_beach(beach: dict, raw_data: dict) -> dict:
    marine = raw_data["marine"]
    weather = raw_data["weather"]

    times = marine.get("hourly", {}).get("time", [])
    wave_heights = marine.get("hourly", {}).get("wave_height", [])
    wave_dirs = marine.get("hourly", {}).get("wave_direction", [])
    wave_periods = marine.get("hourly", {}).get("wave_period", [])
    swell_heights = marine.get("hourly", {}).get("swell_wave_height", [])
    swell_dirs = marine.get("hourly", {}).get("swell_wave_direction", [])
    swell_periods = marine.get("hourly", {}).get("swell_wave_period", [])
    wind_speeds_kmh = weather.get("hourly", {}).get("wind_speed_10m", [])
    wind_dirs = weather.get("hourly", {}).get("wind_direction_10m", [])

    if not times:
        raise HTTPException(status_code=502, detail="API returned empty time series")

    # FIX #3: Index de l'heure actuelle en heure locale Tunis
    current_idx = find_current_hour_index(times)

    def safe_get(lst, idx, default=0.0):
        try:
            v = lst[idx]
            return float(v) if v is not None else default
        except (IndexError, TypeError, ValueError):
            return default

    wh = safe_get(wave_heights, current_idx, 0.2)
    wd = safe_get(wave_dirs, current_idx, beach["shore_normal"])
    wp = safe_get(wave_periods, current_idx, 6.0)
    sh = safe_get(swell_heights, current_idx, 0.1)
    sd = safe_get(swell_dirs, current_idx, beach["shore_normal"])
    sp = safe_get(swell_periods, current_idx, 8.0)
    ws_kmh = safe_get(wind_speeds_kmh, current_idx, 0.0)
    wdir = safe_get(wind_dirs, current_idx, beach["shore_normal"])

    shore_n = beach["shore_normal"]
    sf = beach["shelter_factor"]
    adj_wh = wh * sf

    wave_delta = angular_delta(wd, shore_n)
    swell_delta = angular_delta(sd, shore_n)
    wind_delta = angular_delta(wdir, shore_n)
    wave_cls = classify_vector(wave_delta)

    current_hour_data = {
        "wave_height": round(wh, 3),
        "wave_direction": round(wd, 1),
        "wave_period": round(wp, 1),
        "swell_height": round(sh, 3),
        "swell_direction": round(sd, 1),
        "swell_period": round(sp, 1),
        "wind_speed_kmh": round(ws_kmh, 1),          # km/h — principal
        "wind_speed_kn": round(ws_kmh / 1.852, 1),   # noeuds — info supplémentaire
        "wind_direction": round(wdir, 1),
    }

    # Seaweed & Rip — sur les données historiques (48h passées)
    min_len = min(len(times), len(wave_heights), len(wave_dirs),
                  len(wind_speeds_kmh), len(wind_dirs), len(wave_periods))

    seaweed_data = compute_seaweed_and_rip_index(
        times[:min_len],
        wave_heights[:min_len],
        wave_periods[:min_len],
        wave_dirs[:min_len],
        wind_speeds_kmh[:min_len],
        wind_dirs[:min_len],
        shore_n
    )

    # FIX #3: Heure locale Tunis pour le modèle tidal
    tunis_offset = datetime.timedelta(hours=1)
    now_tunis = datetime.datetime.utcnow() + tunis_offset
    tidal_data = compute_tidal_state(beach["tidal_regime"], now_tunis)

    fish_matrix = compute_fish_matrix(
        adj_wh, wp, ws_kmh, wind_delta,
        seaweed_data["seaweed_pct"],
        tidal_data["tidal_boost"],
        beach["bottom_type"],
        seaweed_data["rip_safety_pct"]
    )

    # Forecast scoring (7 jours à partir de maintenant)
    forecast_summary = []
    for i in range(current_idx + 1, min(current_idx + 168, len(times))):
        fwh = safe_get(wave_heights, i, 0.2) * sf
        fwd = safe_get(wave_dirs, i, shore_n)
        fws_kmh = safe_get(wind_speeds_kmh, i, 0.0)
        fwdir = safe_get(wind_dirs, i, shore_n)
        fwp = safe_get(wave_periods, i, 6.0)
        f_wave_delta = angular_delta(fwd, shore_n)
        f_wave_cls = classify_vector(f_wave_delta)

        f_score = 70.0
        if f_wave_cls == "ONSHORE" and 0.3 <= fwh <= 1.5:
            f_score += 15
        if f_wave_cls == "LONGSHORE":
            f_score -= 20
        if fwh > 2.5:
            f_score -= 20
        try:
            ft = datetime.datetime.fromisoformat(times[i])
        except Exception:
            continue
        f_tidal = compute_tidal_state(beach["tidal_regime"], ft)
        f_score *= f_tidal["tidal_boost"]
        f_score = round(min(100.0, max(0.0, f_score)), 1)
        forecast_summary.append({
            "time": times[i],
            "wave_h": round(fwh, 2),
            "wave_cls": f_wave_cls,
            "score": f_score
        })

    forecast_summary.sort(key=lambda x: x["score"], reverse=True)

    verdict_data = compute_verdict_and_report(
        beach, current_hour_data, seaweed_data, tidal_data,
        fish_matrix, wave_delta, wind_delta, swell_delta,
        wave_cls, adj_wh, forecast_summary
    )

    return {
        "beach_name": beach["name"],
        "governorate": None,
        "coordinates": {"lat": beach["lat"], "lon": beach["lon"]},
        "shore_normal_deg": shore_n,
        "shelter_factor": sf,
        "current_conditions": {
            **current_hour_data,
            "wave_height_adjusted": round(adj_wh, 3),
            "wave_delta_deg": round(wave_delta, 1),
            "wind_delta_deg": round(wind_delta, 1),
            "swell_delta_deg": round(swell_delta, 1),
            "wave_classification": wave_cls,
        },
        "seaweed": seaweed_data,
        "tidal": tidal_data,
        "fish_activity": fish_matrix,
        "forecast_top3": forecast_summary[:3],
        **verdict_data,
    }

# ==============================================================================
# HAVERSINE DISTANCE
# ==============================================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0, min(1, a))))

# ==============================================================================
# ENDPOINTS
# ==============================================================================
@app.get("/")
async def root():
    return {
        "service": "Tunisian Surfcasting Decision Engine v3.0",
        "status": "operational",
        "fixes_applied": [
            "wind_speed_unit=kmh (API parameter corrected)",
            "swell_wave_peak_period removed (invalid variable)",
            "timezone alignment UTC+1 Tunis",
            "pytz dependency removed",
            "aware/naive datetime comparison fixed",
            "marine API start_date/end_date instead of past_days",
            "all wind thresholds in km/h",
        ]
    }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp_utc": datetime.datetime.utcnow().isoformat(),
        "timestamp_tunis": (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).isoformat()
    }

@app.post("/analyze")
async def analyze_spot(req: SpotRequest):
    """Analyse un spot GPS précis via le viseur de la carte."""
    nearest_beach = None
    nearest_gov = None
    min_dist = float("inf")

    for gov, beaches in BEACH_DB.items():
        for beach in beaches:
            d = haversine(req.lat, req.lon, beach["lat"], beach["lon"])
            if d < min_dist:
                min_dist = d
                nearest_beach = beach
                nearest_gov = gov

    if nearest_beach is None:
        raise HTTPException(status_code=404, detail="No beach found near coordinates")

    raw_data = fetch_marine_and_weather_data(req.lat, req.lon)
    result = analyze_beach(nearest_beach, raw_data)
    result["governorate"] = nearest_gov
    result["nearest_node_distance_km"] = round(min_dist, 2)
    result["queried_coordinates"] = {"lat": req.lat, "lon": req.lon}
    return result


@app.post("/governorate_rank")
async def rank_governorate(req: GovernorateRequest):
    """Évalue tous les spots d'un gouvernorat et retourne le TOP 3."""
    gov = req.governorate
    if gov not in BEACH_DB:
        raise HTTPException(
            status_code=404,
            detail=f"Gouvernorat '{gov}' non trouvé. Disponibles: {list(BEACH_DB.keys())}"
        )

    beaches = BEACH_DB[gov]
    results = []
    errors = []

    for beach in beaches:
        try:
            raw_data = fetch_marine_and_weather_data(beach["lat"], beach["lon"])
            result = analyze_beach(beach, raw_data)
            result["governorate"] = gov
            results.append(result)
        except Exception as e:
            errors.append({"beach": beach["name"], "error": str(e)})

    if not results:
        raise HTTPException(status_code=502, detail=f"Tous les spots ont échoué: {errors}")

    results.sort(key=lambda x: x["score"], reverse=True)
    top3 = results[:3]

    return {
        "governorate": gov,
        "total_spots_evaluated": len(results),
        "failed_spots": len(errors),
        "timestamp_tunis": (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).isoformat(),
        "leaderboard": [
            {
                "rank": i + 1,
                "beach_name": r["beach_name"],
                "score": r["score"],
                "verdict": r["verdict"],
                "verdict_ar": r["verdict_ar"],
                "verdict_fr": r["verdict_fr"],
                "wave_classification": r["current_conditions"]["wave_classification"],
                "adjusted_wave_height_m": r["current_conditions"]["wave_height_adjusted"],
                "wind_speed_kmh": r["current_conditions"]["wind_speed_kmh"],
                "wind_speed_kn": r["current_conditions"]["wind_speed_kn"],
                "wind_direction_deg": r["current_conditions"]["wind_direction"],
                "seaweed_pct": r["seaweed"]["seaweed_pct"],
                "rip_safety_pct": r["seaweed"]["rip_safety_pct"],
                "tidal_state": r["tidal"]["state"],
                "tidal_boost": r["tidal"]["tidal_boost"],
                "fish_activity": r["fish_activity"],
                "top_justification": r["penalties"][:2] + r["bonuses"][:2],
                "coordinates": r["coordinates"],
                "shelter_factor": r["shelter_factor"],
                "forecast_top3": r["forecast_top3"],
                "report_summary": "\n".join(r["report"].split("\n")[:25])
            }
            for i, r in enumerate(top3)
        ],
        "all_spots_ranked": [
            {
                "rank": i + 1,
                "name": r["beach_name"],
                "score": r["score"],
                "verdict": r["verdict"],
                "wind_kmh": r["current_conditions"]["wind_speed_kmh"],
                "wave_adj_m": r["current_conditions"]["wave_height_adjusted"],
            }
            for i, r in enumerate(results)
        ]
        }
