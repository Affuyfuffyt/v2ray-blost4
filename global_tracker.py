import time
import subprocess
import json
import os

# 🔥 الحل الجذري: تحديد المسارات ديناميكياً لتجنب تضارب الأسماء 🔥
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_SERVER = '127.0.0.1:10085'
# اكتشاف مسار المحرك تلقائياً في أي حساب
XRAY_BIN = os.path.expanduser('~/xray_core/xray')
# حفظ ملف الإحصائيات داخل مجلد البوت الحالي مهما كان اسمه
STATS_FILE = os.path.join(BASE_DIR, 'global_stats.json')

# الأرقام التراكمية
total_down = 0
total_up = 0

# قراءة الاستهلاك القديم إذا كان السيرفر مطفي واشتغل
if os.path.exists(STATS_FILE):
    try:
        with open(STATS_FILE, 'r') as f:
            data = json.load(f)
            total_down = data.get('total_down', 0)
            total_up = data.get('total_up', 0)
    except:
        pass

print(f"🚀 بدء نظام المراقبة الشامل في مجلد: {os.path.basename(BASE_DIR)}")

while True:
    try:
        # سحب وتصفير العداد من المحرك عبر API
        cmd = f"{XRAY_BIN} api statsquery -server={API_SERVER} -reset=true"
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=2).decode('utf-8')
        
        if result.strip():
            stats = json.loads(result)
            stat_list = stats.get('stat', [])
            
            for stat in stat_list:
                name = stat.get('name', '')
                value = int(stat.get('value', 0))
                
                # 🎯 السر هنا: نراقب مخرج الـ freedom حصراً لأنه يمثل الإنترنت الفعلي
                if 'outbound>>>freedom' in name:
                    if 'downlink' in name:
                        total_down += value
                    elif 'uplink' in name:
                        total_up += value
            
            # حفظ الاستهلاك الكلي بالملف بشكل آمن
            with open(STATS_FILE, 'w') as f:
                json.dump({'total_down': total_down, 'total_up': total_up}, f)
            
            # طباعة الأرقام بالميجا بايت بالشاشة للمتابعة
            mb_down = total_down / 1024 / 1024
            mb_up = total_up / 1024 / 1024
            print(f"📊 استهلاك السيرفر: تحميل ({mb_down:.2f} MB) | رفع ({mb_up:.2f} MB)")
            
    except Exception as e:
        # في حال وجود خطأ في الـ API (مثل المحرك متوقف) لا يتوقف السكربت
        pass
        
    time.sleep(1) # التحديث كل ثانية واحدة
