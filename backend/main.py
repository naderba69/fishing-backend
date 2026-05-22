# ==============================================================================
# TUNISIAN SURFCASTING DECISION ENGINE — main.py
# Principal Marine Hydrodynamic Engineer / Core Data Scientist Build
# FastAPI Backend — Deploy on Render.com
# ==============================================================================

import math
import datetime
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# ==============================================================================
# APP INITIALIZATION & CORS
# ==============================================================================
app = FastAPI(
    title="Tunisian Surfcasting Decision Engine",
    description="Scientific verdict system for Tunisian surfcasters",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# SECTION 1: TUNISIAN BEACH DICTIONARY
# Hardcoded micro-coordinate nodes with hydrodynamic profiles
# Fields:
#   lat, lon           — WGS84 coordinates
#   shore_normal       — True bearing (0-360°) of the outward shoreline normal
#                        (perpendicular to shore, pointing seaward)
#   shelter_factor     — 0.4 (heavily sheltered) → 1.0 (fully open ocean)
#   tidal_regime       — "macro" (Gabes/Zarzis >1m range) | "micro" (<0.3m)
#   bottom_type        — affects seaweed accumulation model
#   description_fr     — human-readable spot description
# ==============================================================================
BEACH_DB = {
    "Bizerte": [
        {
            "name": "Cap Blanc / Ras Angela",
            "lat": 37.345, "lon": 9.803,
            "shore_normal": 350.0,   # near-north facing, open Mediterranean
            "shelter_factor": 0.95,
            "tidal_regime": "micro",
            "bottom_type": "rocky_sand",
            "description_fr": "Cap le plus au nord de l'Afrique, exposition maximale nord."
        },
        {
            "name": "Ghar El Melh (Porto Farina)",
            "lat": 37.193, "lon": 10.177,
            "shore_normal": 40.0,    # NE facing, partially sheltered by lagoon bar
            "shelter_factor": 0.60,
            "tidal_regime": "micro",
            "bottom_type": "muddy_sand",
            "description_fr": "Lagon semi-fermé, facteur d'abri élevé, courant de lagune possible."
        },
        {
            "name": "Raf Raf",
            "lat": 37.175, "lon": 10.185,
            "shore_normal": 55.0,    # NE, open to Sicilian channel swell
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
            "description_fr": "Baie semi-ouverte, fond rocheux favorable aux mérous."
        },
    ],
    "Nabeul": [
        {
            "name": "Kelibia — Plage Mansourah",
            "lat": 36.876, "lon": 11.118,
            "shore_normal": 70.0,    # ENE, open Cap Bon channel
            "shelter_factor": 0.92,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Plage ouverte NE, grosse houle sicilienne, spot de référence."
        },
        {
            "name": "Kelibia — Petit Paris",
            "lat": 36.896, "lon": 11.112,
            "shore_normal": 50.0,
            "shelter_factor": 0.88,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Anse nord de Kelibia, légèrement plus protégée par cap rocheux."
        },
        {
            "name": "Retiba",
            "lat": 36.745, "lon": 11.045,
            "shore_normal": 90.0,    # due East, fully open Sicilian channel
            "shelter_factor": 1.00,
            "tidal_regime": "micro",
            "bottom_type": "coarse_rocky_sand",
            "description_fr": "Côte ouverte plein Est, pas d'abri topographique. Spot de storm fishing."
        },
        {
            "name": "Kerkouane",
            "lat": 36.960, "lon": 11.073,
            "shore_normal": 30.0,    # NNE, partially sheltered by peninsula tip
            "shelter_factor": 0.78,
            "tidal_regime": "micro",
            "bottom_type": "rocky",
            "description_fr": "Site archéologique punique, côte rocheuse NNE, fonds riches."
        },
        {
            "name": "Sidi Mahrsi",
            "lat": 36.820, "lon": 11.090,
            "shore_normal": 80.0,
            "shelter_factor": 0.90,
            "tidal_regime": "micro",
            "bottom_type": "mixed_rocky_sand",
            "description_fr": "Village de pêcheurs, fonds mixtes, bon spot Warata/Mankous."
        },
        {
            "name": "Hammamet Nord",
            "lat": 36.430, "lon": 10.630,
            "shore_normal": 110.0,   # ESE into Gulf of Hammamet — SHELTERED BAY
            "shelter_factor": 0.48,  # SEVERELY sheltered by Cap Bon mass
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Golfe très protégé par Cap Bon. Vagues offshore atténuées ~52%."
        },
        {
            "name": "Hammamet Sud (Yasmine)",
            "lat": 36.370, "lon": 10.600,
            "shore_normal": 120.0,
            "shelter_factor": 0.44,  # deep bay shelter
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Golfe d'Hammamet profond, abri maximal. Mer calme quasi-permanent."
        },
        {
            "name": "Nabeul Plage",
            "lat": 36.456, "lon": 10.735,
            "shore_normal": 100.0,
            "shelter_factor": 0.55,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Plage centrale de Nabeul, exposée ESE mais golfe modère les houles."
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
            "description_fr": "Golfe de Tunis, exposition NNE modérée, fond sableux."
        },
        {
            "name": "Gammarth",
            "lat": 36.912, "lon": 10.278,
            "shore_normal": 20.0,
            "shelter_factor": 0.72,
            "tidal_regime": "micro",
            "bottom_type": "rocky_sand",
            "description_fr": "Cap Gammarth, fond rocheux, bon pour Loup/Dorade."
        },
        {
            "name": "Raoued",
            "lat": 36.892, "lon": 10.215,
            "shore_normal": 350.0,
            "shelter_factor": 0.65,
            "tidal_regime": "micro",
            "bottom_type": "muddy_sand",
            "description_fr": "Côte nord Golfe de Tunis, fond sablo-vaseux."
        },
        {
            "name": "Rades / Ben Arous",
            "lat": 36.762, "lon": 10.271,
            "shore_normal": 90.0,
            "shelter_factor": 0.50,
            "tidal_regime": "micro",
            "bottom_type": "muddy",
            "description_fr": "Côte industrielle Golfe de Tunis. Fortement abrité, fond vaseux."
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
            "description_fr": "Côte centrale est, exposition ESE, houle modérée."
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
            "description_fr": "Côte rocheuse de Monastir, fond mixte, diversité piscicole."
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
            "name": "Mahdia Cap (El Haouaria du Sud)",
            "lat": 35.500, "lon": 11.065,
            "shore_normal": 75.0,
            "shelter_factor": 0.88,
            "tidal_regime": "micro",
            "bottom_type": "rocky",
            "description_fr": "Cap rocheux exposé, fonds profonds, excellent pour grands pélagiques."
        },
        {
            "name": "Mahdia Plage Centrale",
            "lat": 35.495, "lon": 11.043,
            "shore_normal": 90.0,
            "shelter_factor": 0.80,
            "tidal_regime": "micro",
            "bottom_type": "fine_sand",
            "description_fr": "Longue plage de sable blanc, fonds doux."
        },
        {
            "name": "Ras Dimass",
            "lat": 35.460, "lon": 11.020,
            "shore_normal": 95.0,
            "shelter_factor": 0.85,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Cap isolé, peu fréquenté, excellent fond pour Qaros."
        },
    ],
    "Sfax": [
        {
            "name": "Sfax Sidi Mansour",
            "lat": 34.800, "lon": 10.830,
            "shore_normal": 100.0,
            "shelter_factor": 0.58,  # partially sheltered by Kerkennah islands
            "tidal_regime": "micro",
            "bottom_type": "muddy_sand",
            "description_fr": "Abrité par îles Kerkennah, fond vaseux, pêche Bouri/Sorra."
        },
        {
            "name": "Kerkennah — Sidi Fredj",
            "lat": 34.720, "lon": 11.230,
            "shore_normal": 150.0,
            "shelter_factor": 0.65,
            "tidal_regime": "micro",
            "bottom_type": "coarse_sand",
            "description_fr": "Île Kerkennah, côte SE, fond sablo-vaseux peu profond."
        },
    ],
    "Gabes": [
        {
            "name": "Gabes Plage",
            "lat": 33.887, "lon": 10.097,
            "shore_normal": 95.0,
            "shelter_factor": 0.72,
            "tidal_regime": "macro",  # MACROTIDAL — range up to 1.8m
            "bottom_type": "muddy_sand",
            "description_fr": "MARÉES IMPORTANTES (>1.5m). Mer montante décisive pour activité pisciaire."
        },
        {
            "name": "El Hamma (Golfe de Gabes Nord)",
            "lat": 33.951, "lon": 9.865,
            "shore_normal": 80.0,
            "shelter_factor": 0.60,
            "tidal_regime": "macro",
            "bottom_type": "muddy",
            "description_fr": "Fond vaseux profond Golfe Gabes. Marées critiques pour accès spot."
        },
    ],
    "Medenine": [
        {
            "name": "Zarzis Plage",
            "lat": 33.510, "lon": 11.110,
            "shore_normal": 110.0,
            "shelter_factor": 0.80,
            "tidal_regime": "macro",  # macrotidal in gulf
            "bottom_type": "fine_sand",
            "description_fr": "Plage de Zarzis, marées marquées, exposition ESE."
        },
        {
            "name": "Djerba — Plage Seguia",
            "lat": 33.780, "lon": 10.990,
            "shore_normal": 140.0,
            "shelter_factor": 0.70,
            "tidal_regime": "macro",
            "bottom_type": "fine_sand",
            "description_fr": "Île de Djerba, côte SE, marées importantes, fond sableux."
        },
        {
            "name": "Djerba — El Abassia (Nord)",
            "lat": 33.870, "lon": 10.870,
            "shore_normal": 30.0,
            "shelter_factor": 0.75,
            "tidal_regime": "macro",
            "bottom_type": "rocky_sand",
            "description_fr": "Côte nord Djerba, fond rocheux, exposition NNE."
        },
        {
            "name": "Ras Jdir (frontière Lybie)",
            "lat": 33.155, "lon": 11.490,
            "shore_normal": 90.0,
            "shelter_factor": 0.90,
            "tidal_regime": "macro",
            "bottom_type": "coarse_sand",
            "description_fr": "Plage isolée extrême sud-est, exposition maximale, marée forte."
        },
    ],
}

# ==============================================================================
# SECTION 2: PYDANTIC MODELS
# ==============================================================================
class SpotRequest(BaseModel):
    lat: float
    lon: float

class GovernorateRequest(BaseModel):
    governorate: str

# ==============================================================================
# SECTION 3: OPEN-METEO API FETCHER
# Fetches 48h historical + 7-day forecast hourly data
# Marine API: https://marine-api.open-meteo.com/v1/marine
# Weather API: https://api.open-meteo.com/v1/forecast
# ==============================================================================
def fetch_marine_and_weather_data(lat: float, lon: float) -> dict:
    """
    Fetches combined marine (wave/swell) and weather (wind) data
    from Open-Meteo free APIs. Returns 48h past + 168h future (7 days).
    Uses past_days=2 to guarantee 48h historical window for lag calculations.
    """
    today = datetime.date.today()
    
    marine_url = "https://marine-api.open-meteo.com/v1/marine"
    marine_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": (
            "wave_height,wave_direction,wave_period,"
            "wind_wave_height,wind_wave_direction,wind_wave_period,"
            "swell_wave_height,swell_wave_direction,swell_wave_period,"
            "swell_wave_peak_period"
        ),
        "past_days": 2,
        "forecast_days": 7,
        "timezone": "Africa/Tunis"
    }

    weather_url = "https://api.open-meteo.com/v1/forecast"
    weather_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "kn",
        "past_days": 2,
        "forecast_days": 7,
        "timezone": "Africa/Tunis"
    }

    try:
        m_resp = requests.get(marine_url, params=marine_params, timeout=15)
        m_resp.raise_for_status()
        marine_data = m_resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Marine API error: {str(e)}")

    try:
        w_resp = requests.get(weather_url, params=weather_params, timeout=15)
        w_resp.raise_for_status()
        weather_data = w_resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather API error: {str(e)}")

    return {"marine": marine_data, "weather": weather_data}

# ==============================================================================
# SECTION 4: SHORELINE NORMAL VECTOR ENGINE
# Dynamic computation of delta angles between meteo vectors and shore normal
# Convention: all angles in meteorological degrees (FROM direction)
# Delta = absolute minimum angular difference ∈ [0°, 180°]
# ==============================================================================
def angular_delta(bearing_from_deg: float, shore_normal_deg: float) -> float:
    """
    Computes the absolute minimum angular difference between a meteorological
    direction vector (FROM bearing) and the local outward shore normal.
    
    The shore normal points SEAWARD (away from land).
    A wave/wind FROM the sea = near 180° relative to shore normal = ONSHORE.
    
    We use the convention: delta = angle between incoming vector and shore normal
    - Delta < 60°  → ONSHORE (energy directed at shore)
    - 60 ≤ Delta ≤ 120° → LONGSHORE DRIFT
    - Delta > 120° → OFFSHORE
    
    The incoming direction is the direction TOWARD shore (i.e., bearing_from + 180°).
    """
    # Convert FROM-direction to TO-direction (the direction energy travels)
    energy_to_dir = (bearing_from_deg + 180.0) % 360.0
    
    # Compute absolute angular difference
    diff = abs(energy_to_dir - shore_normal_deg) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff  # [0, 180]

def classify_vector(delta: float) -> str:
    """Returns physical category string for a given delta angle."""
    if delta < 60.0:
        return "ONSHORE"
    elif delta <= 120.0:
        return "LONGSHORE"
    else:
        return "OFFSHORE"

# ==============================================================================
# SECTION 5: TIDAL MODEL FOR TUNISIA
# Tunisia has two distinct tidal regimes:
#   - Micro-tidal (North/East coast): range 0.1–0.3m, minimal effect
#   - Macro-tidal (Gabes/Zarzis/Djerba): range 0.8–1.8m, CRITICAL for fishing
#
# Open-Meteo does not provide tidal data. We model the tidal cycle using a
# simplified harmonic approximation based on the known M2/S2 constituents
# for the Gulf of Gabes (dominant semi-diurnal period ~12.42h for M2).
# The phase is calibrated to Tunisia local time (UTC+1).
#
# For microtidal coasts, a minor 0.15m amplitude is used (negligible).
# ==============================================================================
def compute_tidal_state(tidal_regime: str, dt: datetime.datetime) -> dict:
    """
    Returns tidal state at given datetime using harmonic approximation.
    M2 constituent dominates Tunisia. Period = 12.4206h.
    Phase offset calibrated for Gulf of Gabes (approximate).
    """
    M2_PERIOD_H = 12.4206
    PHASE_OFFSET_GABES_H = 2.5  # approximate high tide phase for Gabes
    
    if tidal_regime == "macro":
        amplitude = 0.85   # half-range meters (full range ~1.7m)
        phase_h = PHASE_OFFSET_GABES_H
    else:
        amplitude = 0.12   # micro-tidal half-range
        phase_h = 1.0

    # Hours since reference epoch
    epoch = datetime.datetime(2024, 1, 1, 0, 0, 0)
    hours_elapsed = (dt - epoch).total_seconds() / 3600.0
    
    # M2 tide height (simplified single-constituent)
    omega = 2.0 * math.pi / M2_PERIOD_H
    height = amplitude * math.cos(omega * (hours_elapsed - phase_h))
    
    # Tidal velocity (dh/dt, proxy for current strength)
    velocity = -amplitude * omega * math.sin(omega * (hours_elapsed - phase_h))
    
    # State classification
    if height > 0.7 * amplitude:
        state = "HIGH_TIDE"
    elif height < -0.7 * amplitude:
        state = "LOW_TIDE"
    elif velocity > 0:
        state = "RISING"   # Mer montante
    else:
        state = "FALLING"

    # Boost factor: RISING tide gives maximum fish activity
    # The 2-hour window before high tide is peak feeding time
    hours_to_high = (phase_h - (hours_elapsed % M2_PERIOD_H) + M2_PERIOD_H) % M2_PERIOD_H
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
        "tidal_boost": tidal_boost,
        "hours_to_high": round(hours_to_high % M2_PERIOD_H, 1),
        "regime": tidal_regime,
        "amplitude_m": amplitude
    }

# ==============================================================================
# SECTION 6: SEAWEED / HACHICH INDEX CALCULATOR
# Integrates 48h of onshore wind/swell energy to compute:
#   - Hachich Accumulation Index (0–100%)
#   - Rip Current Safety Index (0–100, lower = more dangerous)
#
# Physics:
#   - Wave Energy Flux E ∝ H² × T (proportional to Hs² × Tp)
#   - Onshore energy (Delta < 60°) accumulates seaweed when sustained
#   - Threshold: >12 knots wind sustained >18 cumulative hours → exponential
#   - Last-6h offshore shift → linear clearing decay (25% per 6h), but
#     floating debris warning remains active
#   - Rip currents: perpendicular swell (H>1.2m, T>8.5s) over 48h creates
#     sandbar breach risk that persists even when current hour is calm
# ==============================================================================
def compute_seaweed_and_rip_index(
    times: list, wave_heights: list, wave_periods: list,
    wave_dirs: list, wind_speeds: list, wind_dirs: list,
    shore_normal: float
) -> dict:
    """
    Computes Seaweed Accumulation Index and Rip Current Danger Index
    by iterating over all available historical data (up to last 48 hours).
    """
    now_utc = datetime.datetime.utcnow()
    cutoff_48h = now_utc - datetime.timedelta(hours=48)
    cutoff_6h = now_utc - datetime.timedelta(hours=6)

    # Accumulators
    onshore_wind_hours = 0.0        # cumulative hours with onshore wind > 12kn
    total_onshore_energy = 0.0      # sum of H² × T for onshore intervals
    last_6h_offshore_energy = 0.0   # offshore energy in last 6h (clearing)
    last_6h_onshore_energy = 0.0    # onshore energy last 6h
    rip_energy_accumulator = 0.0    # perpendicular swell energy over 48h
    rip_peak_hours = 0              # hours with H>1.2m, T>8.5s onshore swell

    n = len(times)
    for i in range(n):
        try:
            dt = datetime.datetime.fromisoformat(times[i])
        except Exception:
            continue
        if dt.tzinfo is not None:
            import pytz
            dt = dt.replace(tzinfo=None)  # strip tz for comparison
        
        if dt > now_utc or dt < cutoff_48h:
            continue

        wh = wave_heights[i] if wave_heights[i] is not None else 0.0
        wp = wave_periods[i] if wave_periods[i] is not None else 6.0
        wd = wave_dirs[i] if wave_dirs[i] is not None else shore_normal
        ws = wind_speeds[i] if wind_speeds[i] is not None else 0.0
        wdir = wind_dirs[i] if wind_dirs[i] is not None else shore_normal

        wave_delta = angular_delta(wd, shore_normal)
        wind_delta = angular_delta(wdir, shore_normal)

        # Wave energy proxy (Hs² × Tp)
        wave_energy = (wh ** 2) * wp

        is_in_last_6h = dt >= cutoff_6h

        # ── Seaweed accumulation (onshore energy)
        if wave_delta < 60.0:  # ONSHORE
            total_onshore_energy += wave_energy
            if is_in_last_6h:
                last_6h_onshore_energy += wave_energy
            # Sustained onshore wind > 12 knots
            if wind_delta < 60.0 and ws > 12.0:
                onshore_wind_hours += 1.0

        # ── Offshore clearing energy (last 6h)
        if wave_delta > 120.0 and is_in_last_6h:
            last_6h_offshore_energy += wave_energy

        # ── Rip current accumulation: perpendicular + energetic swell
        # Most dangerous: near-perpendicular (delta 30–80°) + H>1.2m + T>8.5s
        if 20.0 < wave_delta < 80.0 and wh > 1.2 and wp > 8.5:
            rip_energy_accumulator += wave_energy
            rip_peak_hours += 1

    # ── Seaweed index calculation
    # Base: normalized by reference energy (H=1.5m, T=8s sustained 48h)
    REF_ENERGY_48H = (1.5 ** 2) * 8.0 * 24  # reference 24 active hours
    base_weed = min(1.0, total_onshore_energy / (REF_ENERGY_48H + 1e-6))

    # Exponential escalation if sustained onshore wind > 18 cumulative hours
    if onshore_wind_hours >= 18.0:
        escalation = 1.0 + 0.8 * math.exp((onshore_wind_hours - 18.0) / 12.0)
        base_weed = min(1.0, base_weed * escalation)

    # Clearing decay from last-6h offshore shift
    offshore_clearing_ratio = last_6h_offshore_energy / (
        last_6h_offshore_energy + last_6h_onshore_energy + 1e-6
    )
    # Linear clearing: up to 35% reduction if fully offshore last 6h
    clearing_factor = 1.0 - (0.35 * offshore_clearing_ratio)
    seaweed_index = base_weed * clearing_factor
    seaweed_pct = round(seaweed_index * 100.0, 1)

    # Floating debris warning: clearing in progress but not complete
    floating_debris_warning = (
        offshore_clearing_ratio > 0.5 and seaweed_pct > 15.0
    )

    # ── Rip current danger index
    # Reference: H=1.5m, T=10s sustained 48h perpendicular = critical
    RIP_REF_ENERGY = (1.5 ** 2) * 10.0 * 24
    rip_base = min(1.0, rip_energy_accumulator / (RIP_REF_ENERGY + 1e-6))

    # CRITICAL flag: if >6 hours of qualifying onshore swell over 48h
    rip_critical = rip_peak_hours >= 6

    # Rip danger 0–100 (100 = maximum danger)
    rip_danger = round(rip_base * 100.0, 1)
    if rip_critical:
        rip_danger = max(rip_danger, 65.0)  # floor at 65 for CRITICAL condition

    # Safety index: inverse of danger (100 = perfectly safe)
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
# SECTION 7: FISH ACTIVITY MATRIX
# Computes 0–100% suitability for each target species based on:
#   - Wave height (adjusted by shelter factor)
#   - Wave period
#   - Wind vector classification
#   - Seaweed index
#   - Tidal boost
#   - Bottom type compatibility
#
# Species:
#   Warata (Dorade Royale / Sparus aurata)
#   Mankous (Marbré / Lithognathus mormyrus)
#   Qaros (Loup / Dicentrarchus labrax)
#   Sorra/Qoradh (Toadfish / Halobatrachus didactylus) — LINE CUTTING ALERT
#   Bouri (Mulet / Mugil cephalus)
#   Domibak (Pagre commun / Pagrus pagrus)
# ==============================================================================
def compute_fish_matrix(
    wave_h_adj: float,       # shelter-adjusted wave height (m)
    wave_period: float,      # wave period (s)
    wind_speed: float,       # wind speed (kn)
    wind_delta: float,       # wind vector delta vs shore normal
    seaweed_pct: float,      # seaweed accumulation %
    tidal_boost: float,      # tidal activity multiplier
    bottom_type: str,        # from beach profile
    rip_safety: float        # rip current safety %
) -> dict:
    """
    Species-specific suitability matrix based on known Mediterranean
    surfcasting ethology and hydrodynamic preferences.
    """

    # ── Shared penalty factors
    weed_penalty = max(0.0, 1.0 - (seaweed_pct / 100.0) * 0.8)
    safety_factor = rip_safety / 100.0

    # ── WARATA (Dorade Royale) ─────────────────────────────────────
    # Loves moderate onshore swell (0.3–1.2m), clean bottom, incoming tide
    # Optimal wave height: 0.4–1.0m adj. Penalized by very calm or very rough
    w_wave = 1.0
    if wave_h_adj < 0.2:
        w_wave = 0.4
    elif wave_h_adj <= 1.2:
        w_wave = 0.5 + 0.5 * math.sin(math.pi * (wave_h_adj - 0.2) / 1.0)
    else:
        w_wave = max(0.2, 1.0 - (wave_h_adj - 1.2) * 0.4)
    
    w_bottom = 1.0 if "sand" in bottom_type or "rocky" in bottom_type else 0.6
    warata_score = w_wave * weed_penalty * tidal_boost * w_bottom * safety_factor
    warata_score = round(min(100.0, warata_score * 100.0), 1)

    # ── MANKOUS (Marbré) ─────────────────────────────────────────
    # Prefers moderately agitated water over sandy/rocky-sand bottoms
    # Tolerates more turbulence than Warata. Weak tidal dependency.
    mk_wave = 1.0
    if wave_h_adj < 0.15:
        mk_wave = 0.35
    elif wave_h_adj <= 1.5:
        mk_wave = 0.4 + 0.6 * (wave_h_adj / 1.5)
    else:
        mk_wave = max(0.3, 1.0 - (wave_h_adj - 1.5) * 0.35)
    
    mk_bottom = 1.0 if "sand" in bottom_type else 0.65
    mankous_score = mk_wave * weed_penalty * 0.9 * mk_bottom * safety_factor  # minor tidal sensitivity
    mankous_score = round(min(100.0, mankous_score * 100.0), 1)

    # ── QAROS (Loup / Bar) ────────────────────────────────────────
    # Highly active in agitated water, especially during onshore chop
    # Loves rips and turbulent zones at headland tips. Strong tidal preference.
    q_wave = 1.0
    if wave_h_adj < 0.3:
        q_wave = 0.25
    elif wave_h_adj <= 2.0:
        q_wave = 0.3 + 0.7 * (wave_h_adj / 2.0)
    else:
        q_wave = 0.9  # still active in rough water

    q_wind = 1.1 if wind_delta < 60.0 else 0.8  # loves onshore wind
    q_bottom = 1.0 if "rocky" in bottom_type else 0.75
    qaros_score = q_wave * q_wind * weed_penalty * tidal_boost * q_bottom * safety_factor
    qaros_score = round(min(100.0, qaros_score * 100.0), 1)

    # ── SORRA / QORADH (Crapaud de mer / Toadfish) ────────────────
    # Ambush predator, loves warm shallow water, ANY conditions
    # CRITICAL WARNING: razor-sharp teeth + spines = monofilament cutting
    s_wave = 0.85 if wave_h_adj < 1.0 else 0.60
    s_bottom = 1.0 if "muddy" in bottom_type or "sand" in bottom_type else 0.5
    sorra_score = s_wave * s_bottom * tidal_boost * 0.7  # always present risk
    sorra_score = round(min(100.0, sorra_score * 100.0), 1)
    sorra_alert = sorra_score > 40.0  # trigger monofilament alert

    # ── BOURI (Mulet / Mugil) ─────────────────────────────────────
    # Prefers calmer, slightly turbid waters near estuaries/ports
    # Penalized by strong onshore turbulence
    b_wave = 1.0 if wave_h_adj < 0.6 else max(0.3, 1.0 - (wave_h_adj - 0.6) * 0.5)
    b_turbidity = 1.1 if seaweed_pct > 20.0 else 0.9  # likes turbid water
    bouri_score = b_wave * b_turbidity * tidal_boost
    bouri_score = round(min(100.0, bouri_score * 100.0), 1)

    # ── DOMIBAK (Pagre / Pagrus) ─────────────────────────────────
    # Deep-water species, rocky bottoms, offshore from headlands
    # Needs moderate conditions, excellent tidal sensitivity
    d_wave = 1.0
    if wave_h_adj > 2.0:
        d_wave = max(0.3, 1.0 - (wave_h_adj - 2.0) * 0.4)
    elif wave_h_adj < 0.2:
        d_wave = 0.5
    d_bottom = 1.0 if "rocky" in bottom_type else 0.55
    domibak_score = d_wave * weed_penalty * tidal_boost * d_bottom * safety_factor
    domibak_score = round(min(100.0, domibak_score * 100.0), 1)

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
# SECTION 8: VERDICT ENGINE
# Computes the final SPOT APPROVED / CHANGE SPOT verdict and generates
# the complete Decision Report in Arabic/French bilingual prose.
# ==============================================================================
def compute_verdict_and_report(
    beach: dict,
    current_hour_data: dict,
    seaweed_data: dict,
    tidal_data: dict,
    fish_matrix: dict,
    wave_delta: float,
    wind_delta: float,
    swell_delta: float,
    wave_classification: str,
    adj_wave_height: float,
    forecast_summary: list,
) -> dict:
    """
    Applies the full multi-vector scoring rubric to generate:
    - Numerical score (0–100)
    - Binary verdict (SPOT_APPROVED / CHANGE_SPOT)
    - Bilingual Decision Report
    """
    score = 100.0
    penalties = []
    bonuses = []
    report_lines = []

    # ── P1: Seaweed Penalty ───────────────────────────────────────
    if seaweed_data["seaweed_pct"] > 70:
        score -= 35
        penalties.append(f"عشب بحري حرج ({seaweed_data['seaweed_pct']}%) | Algues CRITIQUES ({seaweed_data['seaweed_pct']}%)")
    elif seaweed_data["seaweed_pct"] > 40:
        score -= 20
        penalties.append(f"عشب بحري مرتفع ({seaweed_data['seaweed_pct']}%) | Algues ÉLEVÉES ({seaweed_data['seaweed_pct']}%)")
    elif seaweed_data["seaweed_pct"] > 20:
        score -= 8
        penalties.append(f"عشب بحري معتدل ({seaweed_data['seaweed_pct']}%) | Algues MODÉRÉES")

    if seaweed_data["floating_debris_warning"]:
        score -= 5
        penalties.append("تحذير: حطام طافٍ أو طحالب قاعية متبقية | Débris flottants / Algues de fond résiduelles")

    # ── P2: Rip Current Penalty ───────────────────────────────────
    if seaweed_data["rip_critical"]:
        score -= 30
        penalties.append(f"خطر تيارات قطع حرجة! ({seaweed_data['rip_peak_hours_48h']}h) | Courants de rip CRITIQUES actifs")
    elif seaweed_data["rip_danger_pct"] > 50:
        score -= 15
        penalties.append(f"خطر تيارات قطع مرتفع ({seaweed_data['rip_danger_pct']}%) | Danger courants de rip ÉLEVÉ")

    # ── P3: Longshore Drift / Lead Instability ────────────────────
    if wave_classification == "LONGSHORE":
        score -= 25
        penalties.append(f"دريفت ساحلي شديد — زاوية موجة Δ={wave_delta:.1f}° | Dérive longshore SÉVÈRE — instabilité du plomb garantie")
    
    if classify_vector(wind_delta) == "LONGSHORE":
        score -= 10
        penalties.append(f"رياح طولية ساحلية Δ={wind_delta:.1f}° | Vent parallèle — embrouillement des lignes")

    # ── P4: Wave Height Penalty (shelter-adjusted) ────────────────
    if adj_wave_height > 2.5:
        score -= 20
        penalties.append(f"ارتفاع أمواج خطر ({adj_wave_height:.2f}m معدّل) | Vagues DANGEREUSES ({adj_wave_height:.2f}m ajustées)")
    elif adj_wave_height > 1.8:
        score -= 10
        penalties.append(f"أمواج قوية ({adj_wave_height:.2f}m) | Vagues FORTES")

    # ── B1: Onshore Bonus ─────────────────────────────────────────
    if wave_classification == "ONSHORE" and 0.3 <= adj_wave_height <= 1.5:
        score += 10
        bonuses.append("موجة شاطئية مثالية | Vague onshore OPTIMALE — activation pisciaire garantie")

    # ── B2: Tidal Bonus ───────────────────────────────────────────
    if tidal_data["state"] == "RISING":
        score += 8
        bonuses.append(f"مد صاعد — نشاط السمك في ذروته | Mer MONTANTE — activité maximale ({tidal_data['hours_to_high']}h avant haute mer)")
    elif tidal_data["state"] == "HIGH_TIDE":
        score += 5
        bonuses.append("مد عالٍ — نشاط جيد | Haute mer active")

    # ── B3: Fish Activity Bonus ───────────────────────────────────
    top_fish = max(
        fish_matrix["Warata_Dorade"],
        fish_matrix["Mankous_Marbre"],
        fish_matrix["Qaros_Loup"]
    )
    if top_fish > 75:
        score += 8
        bonuses.append(f"نشاط سمكي ممتاز ({top_fish:.0f}%) | Activité poisson EXCELLENTE")
    elif top_fish > 50:
        score += 4
        bonuses.append(f"نشاط سمكي جيد ({top_fish:.0f}%) | Activité poisson BONNE")

    # ── Final Score Clamp ─────────────────────────────────────────
    final_score = round(max(0.0, min(100.0, score)), 1)

    # ── Binary Verdict ────────────────────────────────────────────
    if final_score >= 55:
        verdict_en = "SPOT_APPROVED"
        verdict_ar = "✅ أعزل السيرف"
        verdict_fr = "✅ SPOT APPROUVÉ"
    else:
        verdict_en = "CHANGE_SPOT"
        verdict_ar = "🚫 بدل السپوت"
        verdict_fr = "🚫 CHANGEZ DE SPOT"

    # ── Build Decision Report (bilingual) ────────────────────────
    report_lines.append(f"━━━ تقرير القرار العلمي | Rapport de Décision Scientifique ━━━")
    report_lines.append(f"📍 الموقع: {beach['name']} | {beach['description_fr']}")
    report_lines.append(f"🕐 التوقيت: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    report_lines.append("")

    report_lines.append(f"── المتجهات الهيدروديناميكية | Vecteurs Hydrodynamiques ──")
    wc = current_hour_data
    report_lines.append(
        f"🌊 ارتفاع الموجة الخام: {wc.get('wave_height', 0):.2f}m → معدّلة بعامل الحماية ({beach['shelter_factor']}): {adj_wave_height:.2f}m"
    )
    report_lines.append(
        f"   Hauteur vague brute: {wc.get('wave_height', 0):.2f}m → ajustée (facteur abri {beach['shelter_factor']}): {adj_wave_height:.2f}m"
    )
    report_lines.append(f"⏱️ دورة الموجة: {wc.get('wave_period', 0):.1f}s | Période: {wc.get('wave_period', 0):.1f}s")
    report_lines.append(
        f"🧭 اتجاه الموجة: {wc.get('wave_direction', 0):.0f}° → Δ بالنسبة للسواحل: {wave_delta:.1f}° → تصنيف: {wave_classification}"
    )
    report_lines.append(
        f"   Direction vague: {wc.get('wave_direction', 0):.0f}° → Δ/normale littoral: {wave_delta:.1f}° → Classification: {wave_classification}"
    )
    report_lines.append(
        f"💨 الريح: {wc.get('wind_speed', 0):.1f} عقدة من {wc.get('wind_direction', 0):.0f}° | Vent: {wc.get('wind_speed', 0):.1f}kn de {wc.get('wind_direction', 0):.0f}°"
    )

    swell_cls = classify_vector(swell_delta)
    report_lines.append(
        f"🌐 تضخم: {wc.get('swell_height', 0):.2f}m, {wc.get('swell_period', 0):.1f}s → Δ: {swell_delta:.1f}° → {swell_cls}"
    )
    report_lines.append("")

    report_lines.append(f"── المد والجزر | Marées ──")
    report_lines.append(
        f"🌊 النظام: {'ماكروتيدال (متفاوت كبير)' if tidal_data['regime']=='macro' else 'ميكروتيدال (هادئ)'} | "
        f"Régime: {'Macrotidal (Golfe de Gabès)' if tidal_data['regime']=='macro' else 'Microtidal (faible marnage)'}"
    )
    report_lines.append(
        f"   الحالة: {tidal_data['state']} | Hauteur: {tidal_data['height_m']}m | "
        f"Haute mer dans: {tidal_data['hours_to_high']}h | Multiplicateur activité: ×{tidal_data['tidal_boost']}"
    )
    report_lines.append("")

    report_lines.append(f"── مؤشرات السلامة البيئية | Indices Environnementaux ──")
    report_lines.append(
        f"🪸 مؤشر الأعشاب البحرية (الهاشيش): {seaweed_data['seaweed_pct']}% | "
        f"Index Algues (Hachich): {seaweed_data['seaweed_pct']}%"
    )
    report_lines.append(
        f"   رياح شاطئية متراكمة على 48 ساعة: {seaweed_data['onshore_wind_hours_48h']}h | "
        f"Vent onshore cumulé 48h: {seaweed_data['onshore_wind_hours_48h']}h"
    )
    report_lines.append(
        f"🌀 خطر التيارات الشاطئية (رياح قطع): {seaweed_data['rip_danger_pct']}% | "
        f"Danger Courant de Rip: {seaweed_data['rip_danger_pct']}%"
    )
    if seaweed_data["rip_critical"]:
        report_lines.append(
            "   ⚠️ تحذير: تأثير صدمة الأمواج مستمر — خطر تمزق الرمال — خطير حتى في هدوء ظاهري!"
        )
        report_lines.append(
            "   ⚠️ ALERTE: Énergie de déferlement résiduelle — risque de rupture de banc de sable — DANGEREUX même si calme apparent!"
        )
    report_lines.append("")

    report_lines.append(f"── نشاط الأسماك | Activité Piscicole ──")
    report_lines.append(f"🐟 وراطة (دوراد): {fish_matrix['Warata_Dorade']}% | Dorade Royale: {fish_matrix['Warata_Dorade']}%")
    report_lines.append(f"🐟 منقوس (مربري): {fish_matrix['Mankous_Marbre']}% | Marbré: {fish_matrix['Mankous_Marbre']}%")
    report_lines.append(f"🐟 قاروس (لو): {fish_matrix['Qaros_Loup']}% | Loup (Bar): {fish_matrix['Qaros_Loup']}%")
    report_lines.append(f"🐟 بوري (موليه): {fish_matrix['Bouri_Mulet']}% | Mulet Bouri: {fish_matrix['Bouri_Mulet']}%")
    report_lines.append(f"🐟 دومبك (باغر): {fish_matrix['Domibak_Pagre']}% | Pagre: {fish_matrix['Domibak_Pagre']}%")
    report_lines.append(
        f"🦈 صرّة/قرداح (كرابو دو مير): {fish_matrix['Sorra_Qoradh']}%"
    )
    if fish_matrix["sorra_line_cut_alert"]:
        report_lines.append(
            "   ⚠️ تحذير: احتمال مرتفع لعضة قرداح وقطع الخيط المونوفيلان! استخدم خيوطاً مقواة (braided line)."
        )
        report_lines.append(
            "   ⚠️ ALERTE SORRA: Risque élevé de crapaud de mer — coupe du monofilament quasi-certaine! Utilisez du tresse."
        )
    report_lines.append("")

    # ── Penalties/Bonuses Summary ─────────────────────────────────
    if penalties:
        report_lines.append("── عوامل الخصم | Facteurs de Pénalité ──")
        for p in penalties:
            report_lines.append(f"  ❌ {p}")
        report_lines.append("")
    if bonuses:
        report_lines.append("── عوامل الإضافة | Facteurs de Bonus ──")
        for b in bonuses:
            report_lines.append(f"  ✅ {b}")
        report_lines.append("")

    report_lines.append(f"── النتيجة النهائية | Score Final: {final_score}/100 ──")
    report_lines.append(f"{'='*50}")
    report_lines.append(f"  {verdict_ar}  |  {verdict_fr}")
    report_lines.append(f"{'='*50}")

    # ── 7-day forecast snippet ────────────────────────────────────
    if forecast_summary:
        report_lines.append("")
        report_lines.append("── توقعات 7 أيام (أفضل 3 ساعات) | Prévision 7 jours (Top 3 créneaux) ──")
        for entry in forecast_summary[:3]:
            report_lines.append(
                f"  📅 {entry['time']} — Vague: {entry['wave_h']:.2f}m adj, "
                f"Score: {entry['score']:.0f}/100"
            )

    return {
        "score": final_score,
        "verdict": verdict_en,
        "verdict_ar": verdict_ar,
        "verdict_fr": verdict_fr,
        "report": "\n".join(report_lines),
        "penalties": penalties,
        "bonuses": bonuses
    }

# ==============================================================================
# SECTION 9: CORE ANALYSIS ENGINE
# Orchestrates all calculations for a single beach node
# ==============================================================================
def analyze_beach(beach: dict, raw_data: dict) -> dict:
    """
    Full pipeline for one beach node:
    1. Extract current-hour data slice
    2. Apply shelter factor
    3. Compute all delta vectors
    4. Run seaweed/rip engine over 48h history
    5. Compute tidal state
    6. Compute fish matrix
    7. Run verdict engine
    """
    marine = raw_data["marine"]
    weather = raw_data["weather"]
    
    times = marine["hourly"]["time"]
    wave_heights = marine["hourly"].get("wave_height", [])
    wave_dirs = marine["hourly"].get("wave_direction", [])
    wave_periods = marine["hourly"].get("wave_period", [])
    swell_heights = marine["hourly"].get("swell_wave_height", [])
    swell_dirs = marine["hourly"].get("swell_wave_direction", [])
    swell_periods = marine["hourly"].get("swell_wave_period", [])
    wind_speeds = weather["hourly"].get("wind_speed_10m", [])
    wind_dirs = weather["hourly"].get("wind_direction_10m", [])

    # ── Find current-hour index
    now_utc = datetime.datetime.utcnow()
    now_str = now_utc.strftime("%Y-%m-%dT%H:00")
    
    current_idx = 0
    for i, t in enumerate(times):
        if t.startswith(now_str[:13]):  # match YYYY-MM-DDTHH
            current_idx = i
            break
    
    def safe_get(lst, idx, default=0.0):
        try:
            v = lst[idx]
            return v if v is not None else default
        except IndexError:
            return default

    wh = safe_get(wave_heights, current_idx, 0.2)
    wd = safe_get(wave_dirs, current_idx, beach["shore_normal"])
    wp = safe_get(wave_periods, current_idx, 6.0)
    sh = safe_get(swell_heights, current_idx, 0.1)
    sd = safe_get(swell_dirs, current_idx, beach["shore_normal"])
    sp = safe_get(swell_periods, current_idx, 8.0)
    ws = safe_get(wind_speeds, current_idx, 0.0)
    wdir = safe_get(wind_dirs, current_idx, beach["shore_normal"])

    shore_n = beach["shore_normal"]
    sf = beach["shelter_factor"]

    # ── Shelter-adjusted wave height
    adj_wh = wh * sf

    # ── Delta angles
    wave_delta = angular_delta(wd, shore_n)
    swell_delta = angular_delta(sd, shore_n)
    wind_delta = angular_delta(wdir, shore_n)
    wave_cls = classify_vector(wave_delta)

    current_hour_data = {
        "wave_height": wh,
        "wave_direction": wd,
        "wave_period": wp,
        "swell_height": sh,
        "swell_direction": sd,
        "swell_period": sp,
        "wind_speed": ws,
        "wind_direction": wdir,
    }

    # ── Seaweed & Rip Index (48h rolling)
    min_len = min(len(times), len(wave_heights), len(wave_dirs),
                  len(wind_speeds), len(wind_dirs))
    seaweed_data = compute_seaweed_and_rip_index(
        times[:min_len],
        [wave_heights[i] if i < len(wave_heights) else None for i in range(min_len)],
        [wave_periods[i] if i < len(wave_periods) else None for i in range(min_len)],
        [wave_dirs[i] if i < len(wave_dirs) else None for i in range(min_len)],
        [wind_speeds[i] if i < len(wind_speeds) else None for i in range(min_len)],
        [wind_dirs[i] if i < len(wind_dirs) else None for i in range(min_len)],
        shore_n
    )

    # ── Tidal State
    tidal_data = compute_tidal_state(beach["tidal_regime"], now_utc)

    # ── Fish Matrix
    fish_matrix = compute_fish_matrix(
        adj_wh, wp, ws, wind_delta,
        seaweed_data["seaweed_pct"],
        tidal_data["tidal_boost"],
        beach["bottom_type"],
        seaweed_data["rip_safety_pct"]
    )

    # ── 7-Day Forecast Scoring (best windows)
    forecast_summary = []
    future_cutoff = now_utc + datetime.timedelta(hours=1)
    for i in range(current_idx + 1, min(current_idx + 168, len(times))):
        try:
            ft = datetime.datetime.fromisoformat(times[i])
        except Exception:
            continue
        fwh = safe_get(wave_heights, i, 0.2) * sf
        fws = safe_get(wind_speeds, i, 0.0)
        fwd = safe_get(wave_dirs, i, shore_n)
        fwp = safe_get(wave_periods, i, 6.0)
        fwdir = safe_get(wind_dirs, i, shore_n)
        f_wave_delta = angular_delta(fwd, shore_n)
        f_wind_delta = angular_delta(fwdir, shore_n)
        f_wave_cls = classify_vector(f_wave_delta)
        
        # Quick score for forecast window
        f_score = 70.0
        if f_wave_cls == "ONSHORE" and 0.3 <= fwh <= 1.5:
            f_score += 15
        if f_wave_cls == "LONGSHORE":
            f_score -= 20
        if fwh > 2.5:
            f_score -= 20
        f_tidal = compute_tidal_state(beach["tidal_regime"], ft)
        f_score *= f_tidal["tidal_boost"]
        f_score = min(100.0, max(0.0, f_score))
        
        forecast_summary.append({
            "time": times[i],
            "wave_h": fwh,
            "wave_cls": f_wave_cls,
            "score": round(f_score, 1)
        })

    # Sort forecast by score descending
    forecast_summary.sort(key=lambda x: x["score"], reverse=True)

    # ── Verdict & Report
    verdict_data = compute_verdict_and_report(
        beach, current_hour_data, seaweed_data, tidal_data,
        fish_matrix, wave_delta, wind_delta, swell_delta,
        wave_cls, adj_wh, forecast_summary
    )

    return {
        "beach_name": beach["name"],
        "governorate": None,  # filled by caller
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
        **verdict_data
    }

# ==============================================================================
# SECTION 10: FASTAPI ENDPOINTS
# ==============================================================================

@app.get("/")
async def root():
    return {
        "service": "Tunisian Surfcasting Decision Engine",
        "version": "2.0.0",
        "status": "operational",
        "endpoints": ["/analyze", "/governorate_rank", "/health"]
    }

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat()}

@app.post("/analyze")
async def analyze_spot(req: SpotRequest):
    """
    Analyzes a custom GPS coordinate (from map visor).
    Finds the nearest beach node in the database, fetches live data,
    and returns the full scientific verdict.
    """
    # Find nearest beach node using Haversine distance
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * \
            math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.asin(math.sqrt(a))

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
        raise HTTPException(status_code=404, detail="No beach found near these coordinates")

    # Use exact requested coordinates for API fetch (more precise than beach node)
    raw_data = fetch_marine_and_weather_data(req.lat, req.lon)
    result = analyze_beach(nearest_beach, raw_data)
    result["governorate"] = nearest_gov
    result["nearest_node_distance_km"] = round(min_dist, 2)
    result["queried_coordinates"] = {"lat": req.lat, "lon": req.lon}

    return result


@app.post("/governorate_rank")
async def rank_governorate(req: GovernorateRequest):
    """
    Evaluates ALL beach nodes in a given governorate and returns
    a ranked leaderboard with Top 3 best spots and their scientific justifications.
    """
    gov = req.governorate
    if gov not in BEACH_DB:
        available = list(BEACH_DB.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Governorate '{gov}' not found. Available: {available}"
        )

    beaches = BEACH_DB[gov]
    results = []
    
    for beach in beaches:
        raw_data = fetch_marine_and_weather_data(beach["lat"], beach["lon"])
        result = analyze_beach(beach, raw_data)
        result["governorate"] = gov
        results.append(result)

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    
    top3 = results[:3]
    
    return {
        "governorate": gov,
        "total_spots_evaluated": len(results),
        "timestamp_utc": datetime.datetime.utcnow().isoformat(),
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
                "seaweed_pct": r["seaweed"]["seaweed_pct"],
                "rip_safety_pct": r["seaweed"]["rip_safety_pct"],
                "tidal_state": r["tidal"]["state"],
                "tidal_boost": r["tidal"]["tidal_boost"],
                "fish_activity": r["fish_activity"],
                "top_justification": r["penalties"][:2] + r["bonuses"][:2],
                "coordinates": r["coordinates"],
                "shelter_factor": r["shelter_factor"],
                "forecast_top3": r["forecast_top3"],
                "report_summary": "\n".join(r["report"].split("\n")[:20])
            }
            for i, r in enumerate(top3)
        ],
        "all_spots_ranked": [
            {"rank": i+1, "name": r["beach_name"], "score": r["score"], "verdict": r["verdict"]}
            for i, r in enumerate(results)
        ]
    }
