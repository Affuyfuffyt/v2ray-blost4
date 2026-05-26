import time
import os
from database import load_db, update_db
from xray_core.panel_api import PanelAPI

# 🔥 تحديد مسار ملف الأخطاء ديناميكياً بدلاً من المسار الثابت 🔥
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ERROR_LOG = os.path.join(BASE_DIR, 'monitor_error.log')

def start_quota_monitor():
    api = PanelAPI()
    print("🕵️‍♂️ نظام مراقبة الاستهلاك يعمل الآن (كل 60 ثانية)")
    
    while True:
        time.sleep(60)
        
        # =========================================================
        # نظام قياس الاستهلاك 📊 (كل 60 ثانية)
        # =========================================================
        try:
            if not api.stats_available:
                continue
            traffic = api.get_all_clients_traffic(reset=True)
            if traffic:
                db = load_db()
                changed = False
                for email, bytes_used in traffic.items():
                    if email in db and bytes_used > 0:
                        old_bytes = db[email].get('used_bytes', 0)
                        db[email]['used_bytes'] = old_bytes + bytes_used
                        changed = True
                if changed:
                    update_db(db)
        except Exception as e:
            with open(ERROR_LOG, 'a') as f:
                f.write(f"\n[{time.ctime()}] Traffic Monitor Error: {str(e)}")
