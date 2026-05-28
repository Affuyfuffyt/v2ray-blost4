#!/usr/bin/env python3
"""
حارس البوت (Watchdog) — يُشغّل كـ Scheduled Task على Alwaysdata
يفحص إذا البوت شغال ويعيد تشغيله إذا توقف.

الإعداد على Alwaysdata:
1. ادخل على admin.alwaysdata.net
2. اذهب إلى Advanced > Scheduled Tasks
3. أضف مهمة جديدة:
   - Type: python
   - Command: /home/linkapp/[اسم_المجلد]/watchdog.py
   - Frequency: Every 5 minutes
"""
import os
import sys
import subprocess
import time

HOME_DIR = os.path.expanduser("~")
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BOT_DIR, 'bot.pid')
LOG_FILE = os.path.join(BOT_DIR, 'watchdog.log')

def log(msg):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{timestamp}] {msg}\n")
    # نحافظ على حجم الملف صغير (آخر 100 سطر)
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        if len(lines) > 100:
            with open(LOG_FILE, 'w') as f:
                f.writelines(lines[-100:])
    except:
        pass

def is_bot_running():
    """فحص إذا البوت شغال عن طريق PID"""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        # فحص إذا العملية موجودة
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError, PermissionError):
        return False
    except Exception:
        return False

def start_bot():
    """تشغيل البوت بالخلفية"""
    try:
        bot_log = os.path.join(BOT_DIR, 'bot_output.log')
        process = subprocess.Popen(
            [sys.executable, os.path.join(BOT_DIR, 'run.py')],
            cwd=BOT_DIR,
            stdout=open(bot_log, 'a'),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
        log(f"✅ تم تشغيل البوت (PID: {process.pid})")
        return True
    except Exception as e:
        log(f"❌ فشل تشغيل البوت: {e}")
        return False

if __name__ == "__main__":
    if is_bot_running():
        log("✅ البوت شغال — لا حاجة للتدخل")
    else:
        log("⚠️ البوت متوقف — جاري إعادة التشغيل...")
        # حذف PID القديم
        try:
            os.remove(PID_FILE)
        except:
            pass
        start_bot()
