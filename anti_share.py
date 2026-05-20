import time
import os
from database import load_db, update_db
from xray_core.panel_api import PanelAPI

LOG_PATH = os.path.expanduser('~/xray_core/access.log')

# ذاكرة مؤقتة لحفظ آخر ظهور لكل IP 
# الصيغة: { 'email': { 'ip1': timestamp, 'ip2': timestamp } }
active_users = {}

def start_monitor():
    api = PanelAPI()
    print("🛡️ Anti-Share Monitor Started...")
    
    while True:
        time.sleep(10) # الراحة كل 10 ثواني
        
        if not os.path.exists(LOG_PATH):
            open(LOG_PATH, 'w').close()
            continue
            
        with open(LOG_PATH, 'r') as f:
            lines = f.readlines()
            
        # تفريغ السجل فوراً لمنع ثقل السيرفر
        open(LOG_PATH, 'w').close() 
        
        current_time = time.time()
        
        # 1. قراءة السجلات وتحديث الذاكرة
        for line in lines:
            if 'accepted' in line and 'email:' in line:
                try:
                    parts = line.split()
                    email_idx = parts.index('email:') + 1
                    email = parts[email_idx]
                    ip = parts[2].split(':')[0]
                    
                    if email not in active_users:
                        active_users[email] = {}
                    
                    # تحديث وقت آخر ظهور لهذا الـ IP
                    active_users[email][ip] = current_time
                except:
                    continue
                    
        db = load_db()
        db_changed = False
        
        # 2. تنظيف الـ IPs القديمة (اللي ما سوت أي نشاط لـ 60 ثانية)
        for email in list(active_users.keys()):
            for ip in list(active_users[email].keys()):
                if current_time - active_users[email][ip] > 60:
                    del active_users[email][ip]
            
            if not active_users[email]:
                del active_users[email]
                
        # 3. تطبيق الطرد للمخالفين
        for email, ips in active_users.items():
            if email in db:
                limit = db[email].get('limit', 0)
                # إذا مسجل أكثر من جهاز وعدد الـ IPs الفعلي أكبر من المسموح
                if limit > 0 and len(ips) > limit:
                    print(f"🚨 طرد {email}! أجهزة: {len(ips)}، المسموح: {limit}")
                    api.change_client_status(email, enable=False)
                    # حظر لمدة 30 ثانية
                    db[email]['banned_until'] = current_time + 30 
                    db_changed = True
                    # تصفير ذاكرة هذا المستخدم حتى ما ينطرد فوراً بعد فك الحظر
                    active_users[email] = {}
                    
        # 4. فك الحظر عن اللي خلصت فترة عقوبتهم
        for email, data in db.items():
            if data.get('banned_until', 0) > 0 and current_time > data['banned_until']:
                print(f"✅ فك الحظر عن {email}")
                api.change_client_status(email, uuid=data['uuid'], enable=True)
                data['banned_until'] = 0
                db_changed = True
                
        if db_changed:
            update_db(db)
