import os
from dotenv import load_dotenv

load_dotenv()

# ====================== BOT CONFIG ======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Admin Telegram IDs (comma separated in .env or list here)
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "123456789").split(",") if x.strip().isdigit()]

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///rider_bot.db")

# ====================== BUSINESS RULES ======================
# Normal order search radius (km)
NORMAL_RADIUS_KM = float(os.getenv("NORMAL_RADIUS_KM", "1.0"))

# Broadcast order search radius (km)
BROADCAST_RADIUS_KM = float(os.getenv("BROADCAST_RADIUS_KM", "5.0"))

# Accept timeout in seconds
ACCEPT_TIMEOUT_SECONDS = int(os.getenv("ACCEPT_TIMEOUT_SECONDS", "60"))

# Default delivery charge settings (Admin can change via bot later)
DEFAULT_BASE_KM = float(os.getenv("DEFAULT_BASE_KM", "3.0"))          # first X km
DEFAULT_BASE_PRICE = float(os.getenv("DEFAULT_BASE_PRICE", "50.0"))    # price for first X km
DEFAULT_EXTRA_PER_KM = float(os.getenv("DEFAULT_EXTRA_PER_KM", "20.0")) # extra per km after base

# Broadcast extra pay to rider (per km from vendor to rider)
DEFAULT_BROADCAST_PER_KM = float(os.getenv("DEFAULT_BROADCAST_PER_KM", "15.0"))

# Rider default range from home (km)
DEFAULT_RIDER_RANGE_KM = float(os.getenv("DEFAULT_RIDER_RANGE_KM", "10.0"))

# How long a live location is considered valid (seconds). If no update, set offline.
LIVE_LOCATION_TIMEOUT = int(os.getenv("LIVE_LOCATION_TIMEOUT", "120"))

# Keep-alive / Render
PORT = int(os.getenv("PORT", "10000"))
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "true").lower() == "true"

# Optional: Google Maps / OSRM for road distance (leave empty to use Haversine)
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
OSRM_SERVER = os.getenv("OSRM_SERVER", "https://router.project-osrm.org")
