# Food Delivery Rider Bot (Telegram)

একটি সম্পূর্ণ Telegram Bot যা Food Delivery Rider এবং Vendor ম্যানেজমেন্টের জন্য তৈরি।  
Python + python-telegram-bot + SQLite/PostgreSQL + Render Free Plan সাপোর্টসহ।

---

## 🚀 Features (সব ফিচার)

### 1. Rider Registration
- `/start` বা `/registration` দিয়ে শুরু
- Telegram Contact শেয়ার করে ফোন নাম্বার নেয় (অটো)
- নাম নেয়
- **শুধুমাত্র Current Location Share** করে Home Address সেভ করে (টাইপ করে ঠিকানা দেওয়া যায় না)
- পরে `/change_home_address` দিয়ে নতুন লোকেশন শেয়ার করে আপডেট করা যায়

### 2. Rider Online / Offline
- Inline বাটন বা `/go_online` / `/go_offline`
- Online হতে **Live Location** শেয়ার করতে হয়
- বট continuously location আপডেট করে Database-এ
- Live Location বন্ধ/timeout হলে অটো **Offline** হয়ে যায়
- একবার অর্ডার Accept করলে Complete না করা পর্যন্ত নতুন অর্ডার আসে না (`is_busy`)

### 3. Rider Range Setting
- `/range` বা বাটন দিয়ে Home থেকে কত কিমি পর্যন্ত ডেলিভারি নিতে চান সেট করা যায়
- Vendor এবং Customer **উভয়** লোকেশন Rider-এর সেট করা Range-এর ভিতরে না থাকলে অর্ডার যাবে না

### 4. Admin Panel (`/admin`)
- Vendor অ্যাড করা (Telegram ID + নাম + ফোন + Location)
- Vendor-এর Location শুধু Admin এডিট করতে পারে
- সব Rider / Vendor লিস্ট দেখা
- নাম্বার বা Telegram ID দিয়ে সার্চ (`/search`)
- `/suspend <telegram_id>` এবং `/unsuspend <telegram_id>`
- Delivery Rate সেট করা (`/set_rates`)
- Stats দেখা

### 5. Vendor Menu (`/vendor`)
- Inline অপশন:
  - **Order (Normal)** → Vendor থেকে **১ কিমি** এর মধ্যে Rider খোঁজে
  - **Broadcast** → **৫ কিমি** পর্যন্ত + Vendor Rider-কে extra টাকা দেয় (প্রতি কিমি Admin সেট করে)
- অর্ডার টেক্সট + Customer-এর Google Maps Pin Link একসাথে পাঠাতে হয়
- বট লিংক থেকে lat/lon এক্সট্র্যাক্ট করে

### 6. Order Matching Logic
- **Normal Order**: Vendor → Rider ≤ 1 km  
  + Vendor ও Customer উভয়ই Rider-এর Home Range-এর ভিতরে
- **Broadcast**: Vendor → Rider ≤ 5 km  
  + একই Range চেক  
  + Vendor Rider-কে দূরত্ব অনুযায়ী extra টাকা দেয়
- Distance **Road-based** হিসাব করার চেষ্টা করে (OSRM free server)। ব্যর্থ হলে Haversine × 1.3 ব্যবহার করে
- Delivery Charge: Admin সেট করা রেট অনুযায়ী (উদাহরণ ৩ কিমি পর্যন্ত ৫০ টাকা + এরপর প্রতি কিমি ২০ টাকা)
- অর্ডার পোস্টের সময় Rider ও Vendor উভয়কে Charge দেখানো হয়

### 7. Accept / Reject / Complete / Cancel
- Rider-এর কাছে **Accept** ও **Reject** বাটন
- ১ মিনিটের মধ্যে Accept না করলে অটো Expire
- Accept করলে:
  - Rider ও Vendor একে অপরের ফোন নাম্বার দেখে কল করতে পারে
  - **Complete** বাটন → ডেলিভারি শেষ
  - **Cancel / Problem** → অর্ডার আবার অন্য নিকটবর্তী Rider-দের কাছে যায় (reassign)
- Accept করা Rider Complete না করা পর্যন্ত নতুন অর্ডার পায় না

### 8. Keep-Alive (Render Free Plan)
- Flask server চলে একই প্রসেসে (`/` এবং `/ping` endpoint)
- UptimeRobot দিয়ে প্রতি ৫ মিনিট পর পর `https://your-app.onrender.com/ping` পিং করলে server sleep হবে না

---

## 📁 Project Structure

```
telegram_rider_bot/
├── main.py              # Entry point + Keep-alive + Handlers registration
├── config.py            # সব কনফিগ (Token, Admin IDs, Rates...)
├── database.py          # SQLAlchemy models + DB helpers
├── handlers/
│   ├── start.py         # Registration flow
│   ├── rider.py         # Online/Offline, Range, Home change
│   ├── vendor.py        # Vendor menu & order posting
│   ├── admin.py         # Admin commands
│   └── order.py         # Matching, Accept, Complete, Reassign
├── utils/
│   ├── distance.py      # Road distance (OSRM + Haversine fallback)
│   └── location.py      # Google Maps link → lat/lon parser
├── requirements.txt
├── Procfile
├── runtime.txt
├── .env.example
└── README.md
```

---

## ⚙️ Setup & Deploy (Render Free)

### 1. Local Test
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# .env এ BOT_TOKEN এবং ADMIN_IDS বসান
python main.py
```

### 2. Environment Variables (.env)
```
BOT_TOKEN=123456:ABC-DEF...
ADMIN_IDS=123456789,987654321
DATABASE_URL=sqlite:///rider_bot.db
PORT=10000
KEEP_ALIVE=true

# Optional overrides
NORMAL_RADIUS_KM=1.0
BROADCAST_RADIUS_KM=5.0
ACCEPT_TIMEOUT_SECONDS=60
DEFAULT_BASE_KM=3
DEFAULT_BASE_PRICE=50
DEFAULT_EXTRA_PER_KM=20
DEFAULT_BROADCAST_PER_KM=15
LIVE_LOCATION_TIMEOUT=120
```

### 3. Render Deploy
1. GitHub-এ এই রিপো আপলোড করুন
2. Render → New → Web Service
3. Repo সিলেক্ট করুন
4. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: Free
5. Environment Variables এ `BOT_TOKEN`, `ADMIN_IDS` ইত্যাদি দিন
6. Deploy করুন

### 4. UptimeRobot (Server ঘুম থেকে বাঁচাতে)
- https://uptimerobot.com → Add New Monitor
- Monitor Type: HTTP(s)
- URL: `https://your-app-name.onrender.com/ping`
- Interval: 5 minutes
- Create

---

## 📱 ব্যবহারের ফ্লো (সংক্ষেপে)

**Rider:**
1. `/start` → Contact শেয়ার → নাম → Location শেয়ার
2. `/go_online` → Live Location শেয়ার
3. `/range` → নিজের জোন সেট
4. অর্ডার এলে Accept / Reject
5. ডেলিভারি শেষে Complete

**Vendor (Admin আগে অ্যাড করে দিবে):**
1. `/vendor`
2. Order বা Broadcast বাটন চাপুন
3. অর্ডার টেক্সট + Customer Maps Link পাঠান

**Admin:**
1. `/admin`
2. `/add_vendor` → Telegram ID, নাম, ফোন, Location
3. `/set_rates` → রেট আপডেট
4. `/suspend` / `/unsuspend` / `/search` / `/stats`

---

## ⚠️ গুরুত্বপূর্ণ নোট

- **Road Distance**: OSRM পাবলিক সার্ভার ব্যবহার করা হয়। ব্যস্ত সময়ে ব্যর্থ হতে পারে → তখন Haversine × 1.3 ব্যবহার হয়। প্রোডাকশনে নিজের OSRM বা Google Distance Matrix API Key দিলে আরও ভালো হবে।
- **Live Location**: Telegram Live Location-এর সময়সীমা শেষ হলে বা ইউজার বন্ধ করলে বট তাকে Offline করে দেয়।
- **Database**: ডিফল্ট SQLite। Render-এ PostgreSQL ব্যবহার করতে চাইলে `DATABASE_URL` এ Postgres connection string দিন (Render Free Postgres আলাদা সার্ভিস হিসেবে নিতে হয়)।
- **Security**: `ADMIN_IDS` সঠিকভাবে সেট করুন। শুধুমাত্র সেই ID গুলো Admin কমান্ড চালাতে পারবে।

---

## 📞 Support / Customize

কোড ওপেন সোর্স স্টাইলে লেখা। প্রয়োজন অনুযায়ী রেট, রেডিয়াস, টেক্সট, বাটন ইত্যাদি সহজেই পরিবর্তন করা যায় `config.py` এবং handlers ফোল্ডারে।

শুভ ব্যবহার!
