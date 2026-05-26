import time
import os
from database import load_db, update_db
from xray_core.panel_api import PanelAPI

# 🔥 تحديد مسار ملف الأخطاء ديناميكياً بدلاً من المسار الثابت 🔥
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ERROR_LOG = os.path.join(BASE_DIR, 'monitor_error.log')

def start_quota_monitor():
    api = PanelAPI()
    print("🕵️‍♂️ نظام مراقبة الوقت + الاستهلاك يعمل الآن")
    
    traffic_counter = 0  # عداد لفحص الاستهلاك كل 30 ثانية
    first_traffic_check = True  # لطباعة نتيجة أول فحص
    
    while True:
        time.sleep(3)
        traffic_counter += 3
        
        # =========================================================
        # 1. نظام الطرد الصارم للوقت ⏱️ (يشتغل كل 3 ثواني)
        # =========================================================
        try:
            db = load_db()
            db_changed = False
            now = time.time()
            
            for email, data in list(db.items()):
                if data.get('is_active', True):
                    expiry = data.get('expiry_time', 0)
                    
                    # فحص انتهاء المدة فقط
                    if expiry > 0 and now >= expiry:
                        print(f"⏱️ طرد فوري: {email} | السبب: انتهاء الوقت")
                        db[email]['is_active'] = False
                        api.change_client_status(email, enable=False)
                        db_changed = True
            
            if db_changed:
                update_db(db)
        except Exception as e:
            with open(ERROR_LOG, 'a') as f:
                f.write(f"\n[{time.ctime()}] Time Monitor Logic Error: {str(e)}")

        # =========================================================
        # 2. نظام قياس الاستهلاك 📊 (يشتغل كل 30 ثانية)
        # =========================================================
        if traffic_counter >= 30:
            traffic_counter = 0
            try:
                traffic = api.get_all_clients_traffic(reset=True)
                
                if first_traffic_check:
                    first_traffic_check = False
                    if traffic:
                        print(f"📊 نظام الاستهلاك يعمل! تم رصد {len(traffic)} مشترك")
                    else:
                        print("⚠️ نظام الاستهلاك: لم يتم رصد ترافيك (قد يحتاج وقت أو تحقق من إعدادات xray)")
                
                if traffic:
                    db = load_db()
                    changed = False
                    for email, bytes_used in traffic.items():
                        if email in db and bytes_used > 0:
                            old_bytes = db[email].get('used_bytes', 0)
                            db[email]['used_bytes'] = old_bytes + bytes_used
                            total_mb = (old_bytes + bytes_used) / (1024 * 1024)
                            print(f"📊 {email}: +{bytes_used/1024:.1f} KB | المجموع: {total_mb:.2f} MB")
                            changed = True
                    if changed:
                        update_db(db)
            except Exception as e:
                print(f"⚠️ خطأ في قياس الاستهلاك: {e}")
                with open(ERROR_LOG, 'a') as f:
                    f.write(f"\n[{time.ctime()}] Traffic Monitor Error: {str(e)}")
