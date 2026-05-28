#!/usr/bin/env python3
"""
حارس البوت (Watchdog) المطوّر — يُشغّل كـ Scheduled Task على Alwaysdata
يفحص وجود عملية run.py تحديداً بدلاً من الاعتماد على PID الوهمي.
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
    try:
        # إضافة ترميز utf-8 لضمان حفظ اللغة العربية بدون مشاكل
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {msg}\n")
        # نحافظ على حجم الملف صغير (آخر 100 سطر)
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if len(lines) > 100:
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.writelines(lines[-100:])
    except Exception:
        pass

def is_bot_running():
    """فحص دقيق جداً: يتأكد من اسم الملف run.py في نظام السيرفر بدلاً من رقم PID"""
    try:
        # نبحث عن سكربت run.py في العمليات الشغالة الفعلية
        # استخدام [r] يمنع أمر grep من صيد نفسه بالخطأ
        cmd = "ps x -o pid,command | grep '[r]un.py'"
        output = subprocess.check_output(cmd, shell=True).decode('utf-8')
        
        # إذا وجدنا run.py ضمن القائمة، فالبوت يعمل
        if 'run.py' in output:
            return True
    except subprocess.CalledProcessError:
        # إذا فشل الأمر، معناه run.py غير موجود بالعمليات
        pass
    
    return False

def start_bot():
    """تشغيل البوت بالخلفية وفصله عن الجلسة لمنع الإغلاق المفاجئ"""
    try:
        bot_log = os.path.join(BOT_DIR, 'bot_output.log')
        process = subprocess.Popen(
            [sys.executable, os.path.join(BOT_DIR, 'run.py')],
            cwd=BOT_DIR,
            stdout=open(bot_log, 'a'),
            stderr=subprocess.STDOUT,
            start_new_session=True # 🔥 تمنع السيرفر من إغلاق البوت عند انتهاء مهمة الحارس
        )
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
        log(f"✅ تم تشغيل البوت (run.py) بنجاح (PID: {process.pid})")
        return True
    except Exception as e:
        log(f"❌ فشل تشغيل البوت: {e}")
        return False

if __name__ == "__main__":
    if is_bot_running():
        log("✅ البوت (run.py) شغال — لا حاجة للتدخل")
    else:
        log("⚠️ البوت متوقف — جاري إعادة التشغيل فوراً...")
        # حذف ملف PID القديم لتنظيف السجلات
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except:
            pass
        
        start_bot()
