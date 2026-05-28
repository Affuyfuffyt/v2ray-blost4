import time
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_FILE = os.path.join(BASE_DIR, 'global_stats.json')

print("⚠️ نظام المراقبة الشامل معطل — يحتاج بورت إضافي (10085) غير متاح على هذا السيرفر")

# الحفاظ على الملف للتوافق
if not os.path.exists(STATS_FILE):
    with open(STATS_FILE, 'w') as f:
        json.dump({'total_down': 0, 'total_up': 0}, f)

while True:
    time.sleep(3600)
