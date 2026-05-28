import os
import time
import threading
from db import update_radar_data 

active_users_cache = set()

def flush_radar_data():
    """
    هذه الدالة هي المسؤولة عن 'حقن' البيانات في قاعدة البيانات.
    تشتغل كل 60 ثانية، تأخذ كل الأسماء اللي ظهرت باللوج وتضيفلهم دقيقة واحدة.
    """
    while True:
        time.sleep(60)
        if active_users_cache:
            users_to_update = list(active_users_cache)
            active_users_cache.clear()
            
            for email in users_to_update:
                try:
                    update_radar_data(email)
                except Exception as e:
                    print(f"Radar Update Error ({email}): {e}")

def start_radar_monitor():
    """
    هذه الدالة تراقب ملف السجلات (access.log) لحظة بلحظة.
    """
    print("📡 رادار السيرفر الاستخباراتي بدأ بالعمل 24/7...")
    
    threading.Thread(target=flush_radar_data, daemon=True).start()
    
    home_dir = os.path.expanduser("~")
    log_path = os.path.join(home_dir, "xray_core", "access.log")
    
    if not os.path.exists(log_path):
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            open(log_path, 'a').close()
        except:
            pass

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(0, os.SEEK_END)
            
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                
                if "accepted" in line:
                    parts = line.strip().split()
                    if parts:
                        email = parts[-1].strip("[]")
                        
                        if email and len(email) > 1:
                            active_users_cache.add(email)
                            
    except Exception as e:
        print(f"Radar Monitor Error: {e}")
        time.sleep(5)
        start_radar_monitor()
