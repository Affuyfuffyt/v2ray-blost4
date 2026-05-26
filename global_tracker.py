import time
import subprocess
import json
import os
import socket

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_SERVER = '127.0.0.1:10085'
API_PORT = 10085
XRAY_BIN = os.path.expanduser('~/xray_core/xray')
STATS_FILE = os.path.join(BASE_DIR, 'global_stats.json')

total_down = 0
total_up = 0

if os.path.exists(STATS_FILE):
    try:
        with open(STATS_FILE, 'r') as f:
            data = json.load(f)
            total_down = data.get('total_down', 0)
            total_up = data.get('total_up', 0)
    except:
        pass

print(f"🚀 بدء نظام المراقبة الشامل في مجلد: {os.path.basename(BASE_DIR)}")

def is_api_available():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('127.0.0.1', API_PORT))
        sock.close()
        return result == 0
    except:
        return False

api_available = is_api_available()
if not api_available:
    print("⚠️ Stats API غير متاح (بورت 10085 مغلق) — المراقبة متوقفة")

while True:
    if not api_available:
        time.sleep(300)
        api_available = is_api_available()
        continue
    try:
        cmd = f"{XRAY_BIN} api statsquery -server={API_SERVER} -reset=true"
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=5).decode('utf-8')
        
        if result.strip():
            stats = json.loads(result)
            stat_list = stats.get('stat', [])
            
            for stat in stat_list:
                name = stat.get('name', '')
                value = int(stat.get('value', 0))
                if 'outbound>>>freedom' in name:
                    if 'downlink' in name:
                        total_down += value
                    elif 'uplink' in name:
                        total_up += value
            
            with open(STATS_FILE, 'w') as f:
                json.dump({'total_down': total_down, 'total_up': total_up}, f)
            
            mb_down = total_down / 1024 / 1024
            mb_up = total_up / 1024 / 1024
            print(f"📊 استهلاك السيرفر: تحميل ({mb_down:.2f} MB) | رفع ({mb_up:.2f} MB)")
            
    except Exception as e:
        api_available = is_api_available()
        if not api_available:
            print("⚠️ Stats API غير متاح — المراقبة متوقفة مؤقتاً")
        
    time.sleep(30)
