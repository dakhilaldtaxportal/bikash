"""
Distance calculation utilities.
Priority:
1. OSRM (free public server) for road distance
2. Fallback to Haversine (straight-line) if OSRM fails
"""

import math
import httpx
import logging
from typing import Optional, Tuple
import config

logger = logging.getLogger(__name__)

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers."""
    R = 6371.0  # Earth radius km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

async def osrm_road_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    """Try OSRM public routing server for driving distance."""
    try:
        url = (
            f"{config.OSRM_SERVER}/route/v1/driving/"
            f"{lon1},{lat1};{lon2},{lat2}?overview=false"
        )
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    # distance is in meters
                    meters = data["routes"][0]["distance"]
                    return meters / 1000.0
    except Exception as e:
        logger.warning(f"OSRM failed: {e}")
    return None

async def get_road_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Best effort road distance.
    Falls back to Haversine * 1.3 (rough road factor) if OSRM unavailable.
    """
    if None in (lat1, lon1, lat2, lon2):
        return 9999.0

    road = await osrm_road_distance_km(lat1, lon1, lat2, lon2)
    if road is not None and road > 0:
        return round(road, 2)

    # Fallback
    straight = haversine_km(lat1, lon1, lat2, lon2)
    # Approximate road distance (typical factor 1.2 - 1.4 in cities)
    approx = straight * 1.3
    return round(approx, 2)

def calculate_delivery_charge(distance_km: float, base_km: float, base_price: float, extra_per_km: float) -> float:
    if distance_km <= base_km:
        return base_price
    extra_km = distance_km - base_km
    return round(base_price + (extra_km * extra_per_km), 2)

def calculate_broadcast_extra(distance_vendor_rider_km: float, per_km: float) -> float:
    return round(distance_vendor_rider_km * per_km, 2)
