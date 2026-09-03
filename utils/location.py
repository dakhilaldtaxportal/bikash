"""
Parse Google Maps / location links to extract lat, lon.
Supports common formats:
- https://maps.google.com/?q=23.81,90.41
- https://www.google.com/maps/place/.../@23.81,90.41,17z
- https://maps.app.goo.gl/xxxxx  (short links - limited support)
- geo:23.81,90.41
"""

import re
import logging
from typing import Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

# Common patterns
PATTERNS = [
    # @lat,lon
    re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)"),
    # q=lat,lon
    re.compile(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)"),
    # ll=lat,lon
    re.compile(r"[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)"),
    # !3dlat!4dlon (Google place)
    re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)"),
    # geo:lat,lon
    re.compile(r"geo:(-?\d+\.\d+),(-?\d+\.\d+)"),
    # plain lat,lon somewhere
    re.compile(r"(-?\d{1,3}\.\d{4,}),\s*(-?\d{1,3}\.\d{4,})"),
]

async def extract_lat_lon_from_text(text: str) -> Optional[Tuple[float, float]]:
    if not text:
        return None

    text = text.strip()

    # Direct try patterns
    for pat in PATTERNS:
        m = pat.search(text)
        if m:
            try:
                lat = float(m.group(1))
                lon = float(m.group(2))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
            except ValueError:
                continue

    # Try to resolve short Google Maps links (maps.app.goo.gl)
    if "maps.app.goo.gl" in text or "goo.gl/maps" in text:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                resp = await client.get(text)
                final_url = str(resp.url)
                for pat in PATTERNS:
                    m = pat.search(final_url)
                    if m:
                        lat = float(m.group(1))
                        lon = float(m.group(2))
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            return lat, lon
        except Exception as e:
            logger.warning(f"Could not resolve short map link: {e}")

    return None
