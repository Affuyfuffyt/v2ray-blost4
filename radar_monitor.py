import os
import time
import threading
# 👇 الاستدعاء من ملف db اللي صار ديناميكي الآن
from db import update_radar_data 

active_users_cache = set()

def flush_radar_data():
    """
    هذه الدالة هي المسؤولة عن 'حقن' البيانات في قاعدة البيانات.
    تشتغل كل 60 ثانية، تأخذ كل الأسماء اللي ظهرت باللوج وتضيفلهم دقيقة واحدة.
    """
    while True:
        time.sleep(60) # ينتظر دقيقة
        if active_users_cache:
            # نأخذ نسخة من المستخدمين النشطين خلال هذه الدقيقة
            users_to_update = list(active_users_cache)
            # نفرغ القائمة لاستقبال المتصلين في الدقيقة القادمة
            active_users_cache.clear()
            
            for email in users_to_update:
                try:
                    # تحديث الوقت الكلي واليومي وآخر ظهور في قاعدة البيانات
                    update_radar_data(email)
                except Exception as e:
                    print(f"Radar Update Error ({email}): {e}")

def start_radar_monitor():
    """
    هذه الدالة تراقب ملف السجلات (access.log) لحظة بلحظة.
    """
    print("📡 رادار السيرفر الاستخباراتي بدأ بالعمل 24/7...")
    
    # تشغيل خيط الحفظ المجدول بالخلفية
    threading.Thread(target=flush_radar_data, daemon=True).start()
    
    # 🔥 تحديد المسار بطريقة احترافية ديناميكية 🔥
    home_dir = os.path.expanduser("~")
    log_path = os.path.join(home_dir, "xray_core", "access.log")
    
    # التأكد من وجود الملف أو إنشاؤه إذا كان مفقوداً
    if not os.path.exists(log_path):
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            open(log_path, 'a').close()
        except:
            pass

    try:
        # قراءة ملف اللوج "Live" بدون سحب كل الذاكرة
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            # القفز إلى نهاية الملف حتى لا يقرأ الدخول القديم عند تشغيل البوت
            f.seek(0, os.SEEK_END)
            
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5) # انتظار بسيط حتى لا يستهلك المعالج
                    continue
                
                # البحث عن كلمة accepted التي تعني اتصال ناجح
                if "accepted" in line:
                    parts = line.strip().split()
                    if parts:
                        # استخراج الإيميل (الاسم) من نهاية السطر
                        # Xray عادة يضع الاسم هكذا بملف اللوج: [email]
                        email = parts[-1].strip("[]")
                        
                        if email and len(email) > 1:
                            # إضافة المشترك لقائمة 'النشطين خلال هذه الدقيقة'
                            active_users_cache.add(email)
                            
    except Exception as e:
        print(f"Radar Monitor Error: {e}")
        # إعادة تشغيل المراقبة في حال حدث خطأ مفاجئ لضمان الاستمرارية
        time.sleep(5)
        start_radar_monitor()
