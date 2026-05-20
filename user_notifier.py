import time
import sqlite3
import os
import json
import threading

# 🔥 الحل الجذري: اكتشاف مسار المجلد الحالي تلقائياً 🔥
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bot_data.db")
NOTIFIED_FILE = os.path.join(BASE_DIR, "notified_users.json")

# تحميل الإشعارات السابقة حتى ما يكرر الرسالة أكثر من مرة
def load_notified():
    if os.path.exists(NOTIFIED_FILE):
        try:
            with open(NOTIFIED_FILE, 'r') as f:
                return json.load(f)
        except: return {}
    return {}

def save_notified(data):
    with open(NOTIFIED_FILE, 'w') as f:
        json.dump(data, f)

def start_notifier(bot):
    print("🔔 نظام التنبيهات الذكي للمشتركين بدأ العمل...")
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # جلب المشتركين المربوطين بتليجرام فقط لإرسال التنبيهات لهم
            c.execute('''SELECT u.email, u.expiry_date, s.chat_id 
                         FROM users u JOIN user_subscriptions s ON u.email = s.email''')
            rows = c.fetchall()
            conn.close()

            notified = load_notified()
            now = time.time()

            for email, expiry_str, chat_id in rows:
                if not expiry_str: continue
                expiry_time = float(expiry_str)
                time_left = expiry_time - now

                if email not in notified:
                    notified[email] = []

                # تنبيه قبل يومين
                if 86400 * 2.1 >= time_left > 86400 * 1.9 and "2_days" not in notified[email]:
                    send_alert(bot, chat_id, email, "يومين")
                    notified[email].append("2_days")
                
                # تنبيه قبل يوم
                elif 86400 * 1.1 >= time_left > 86400 * 0.9 and "1_day" not in notified[email]:
                    send_alert(bot, chat_id, email, "يوم واحد")
                    notified[email].append("1_day")
                    
                # تنبيه قبل ساعة
                elif 3600 * 1.2 >= time_left > 0 and "1_hour" not in notified[email]:
                    send_alert(bot, chat_id, email, "ساعة واحدة")
                    notified[email].append("1_hour")

                # تنبيه الانتهاء
                elif time_left <= 0 and "expired" not in notified[email]:
                    send_expired_alert(bot, chat_id, email)
                    notified[email].append("expired")

                # تصفير الإشعارات إذا جدد الاشتراك (زاد الوقت)
                if time_left > 86400 * 2.5:
                    notified[email] = []

            save_notified(notified)

        except Exception as e:
            print(f"Notifier Error: {e}")
        
        time.sleep(300) # يفحص كل 5 دقائق لضمان عدم إثقال السيرفر

def send_alert(bot, chat_id, email, time_str):
    text = f"⚠️ **تنبيه قرب انتهاء الاشتراك!** ⚠️\n\n👤 المشترك: `{email}`\n⏳ الوقت المتبقي: **{time_str}**\n\nيرجى التجديد قبل توقف الخدمة لتجنب الانقطاع.\n\n🛒 لتجديد الاشتراك تواصل مع المبيعات:\n@l_t22\n\n📢 تابع قناتنا لكل جديد:\nhttps://t.me/r338888"
    try: bot.send_message(chat_id, text, parse_mode="Markdown")
    except: pass

def send_expired_alert(bot, chat_id, email):
    text = f"❌ **انتهى اشتراكك!** ❌\n\n👤 المشترك: `{email}`\nلقد انتهى وقت الاشتراك وتوقفت الخدمة.\n\n🛒 لتجديد الاشتراك وتفعيل الخدمة فوراً تواصل مع المبيعات:\n@l_t22\n\n📢 تابع قناتنا:\nhttps://t.me/r338888"
    try: bot.send_message(chat_id, text, parse_mode="Markdown")
    except: pass

# دالة لإبلاغ العميل بحدوث تمديد لاشتراكه (تستدعى من create_flow أو manage_flow)
def notify_extension(bot, email, seconds_added):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT chat_id FROM user_subscriptions WHERE email=?", (email,))
        rows = c.fetchall()
        conn.close()
        
        if not rows: return
        
        days = int(seconds_added // 86400)
        hours = int((seconds_added % 86400) // 3600)
        mins = int((seconds_added % 3600) // 60)
        
        added_str = ""
        if days > 0: added_str += f"{days} يوم "
        if hours > 0: added_str += f"{hours} ساعة "
        if mins > 0: added_str += f"{mins} دقيقة"
        
        text = f"🎉 **تم تمديد اشتراكك بنجاح!** 🎉\n\n👤 المشترك: `{email}`\n⏳ مدة التمديد: **{added_str.strip()}**\n\nشكراً لاستخدامك خدماتنا! 🚀"
        
        for row in rows:
            try: bot.send_message(row[0], text, parse_mode="Markdown")
            except: pass
    except: pass
