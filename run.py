import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import subprocess
import time
import config
import os
from xray_core.panel_api import PanelAPI

# استدعاء المعالجات
from handlers import admin_start, create_flow, manage_flow, speed_test, radar_flow
from handlers import user_handlers # ملف واجهة المشتركين
from handlers import servers_flow # 🔥 إضافة ملف إدارة السيرفرات الجديد 🔥

# استدعاء المراقبين
from quota_monitor import start_quota_monitor 
from radar_monitor import start_radar_monitor 
try:
    from user_notifier import start_notifier # نظام التنبيهات
except ImportError:
    def start_notifier(bot): pass

# 1. تهيئة البوت والـ API
bot = telebot.TeleBot(config.BOT_TOKEN)
api = PanelAPI()

# 🔥 التصليح الجذري للفلتر حتى ما يعلك الأزرار (مثل حالة الخادم) 🔥
class IsAdmin(telebot.custom_filters.SimpleCustomFilter):
    key = 'is_admin'
    def check(self, obj):
        # إذا كانت الضغطة من زر (CallbackQuery)
        if hasattr(obj, 'message'):
            return str(obj.message.chat.id) == str(config.ADMIN_ID)
        # إذا كانت رسالة نصية عادية (Message)
        return str(obj.chat.id) == str(config.ADMIN_ID)

bot.add_custom_filter(IsAdmin())

# ==========================================
# 📊 قسم حالة الخادم (Server Status)
# ==========================================
live_monitors = {}

def get_server_status_text():
    try:
        # قراءة CPU من /proc/stat (أخف بكثير من top -bn1)
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
            parts = line.split()
            idle = int(parts[4])
            total = sum(int(p) for p in parts[1:])
            if not hasattr(get_server_status_text, '_prev'):
                get_server_status_text._prev = (idle, total)
            prev_idle, prev_total = get_server_status_text._prev
            diff_idle = idle - prev_idle
            diff_total = total - prev_total
            cpu_usage = (1.0 - diff_idle / diff_total) * 100 if diff_total > 0 else 0.0
            get_server_status_text._prev = (idle, total)
        except:
            cpu_usage = 0.0
        
        # قراءة RAM من /proc/meminfo (أخف من free -m)
        try:
            meminfo = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split()
                    meminfo[parts[0].rstrip(':')] = int(parts[1])
            ram_total = meminfo.get('MemTotal', 0) // 1024
            ram_available = meminfo.get('MemAvailable', 0) // 1024
            ram_used = ram_total - ram_available
            ram_percent = int((ram_used / ram_total) * 100) if ram_total > 0 else 0
        except:
            ram_total = ram_used = ram_percent = 0
        
        try:
            df_line = subprocess.getoutput("df -h / | tail -1").split()
            disk_total = df_line[1] if len(df_line) > 1 else "?"
            disk_used = df_line[2] if len(df_line) > 2 else "?"
            disk_percent_str = df_line[4].replace('%', '') if len(df_line) > 4 else "0"
            disk_percent = int(disk_percent_str) if disk_percent_str.isdigit() else 0
        except:
            disk_total = disk_used = "?"
            disk_percent = 0

        def make_bar(percent):
            filled = int(percent / 10)
            return '█' * filled + '▒' * (10 - filled)

        text = f"🖥️ | 𝗦𝗘𝗥𝗩𝗘𝗥 𝗥𝗘𝗦𝗢𝗨𝗥𝗖𝗘𝗦\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"⚙️ **CPU:** `[{make_bar(cpu_usage)}]` {cpu_usage:.1f}%\n"
        text += f"🗄️ **RAM:** `[{make_bar(ram_percent)}]` {ram_percent}%\n"
        text += f"    └ 📊 {ram_used}MB / {ram_total}MB\n"
        text += f"💾 **Disk:** `[{make_bar(disk_percent)}]` {disk_percent}%\n"
        text += f"    └ 📊 {disk_used} / {disk_total}\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"⏱️ _آخر تحديث: {time.strftime('%H:%M:%S')}_\n"
        
        return text
    except Exception as e:
        return "⚠️ حدث خطأ أثناء جلب بيانات السيرفر."

def get_status_keyboard(is_live=False):
    markup = InlineKeyboardMarkup(row_width=2)
    if not is_live:
        btn_refresh = InlineKeyboardButton("🔄 تحديث الآن", callback_data="status_refresh")
        btn_live = InlineKeyboardButton("📡 تحديث مستمر (2 دقيقة)", callback_data="status_live")
        markup.add(btn_refresh, btn_live)
    else:
        btn_stop = InlineKeyboardButton("🛑 إيقاف التحديث", callback_data="status_stop")
        markup.add(btn_stop)
    markup.add(InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="admin_main_menu"))
    return markup

# ==========================================
# 3. تسجيل المعالجات (Handlers)
# ==========================================
create_flow.register_create_handlers(bot)
manage_flow.register_manage_handlers(bot)
speed_test.register_speed_handlers(bot)
radar_flow.register_radar_handlers(bot)
user_handlers.register_user_handlers(bot) 
servers_flow.register_servers_handlers(bot) # 🔥 تفعيل أزرار شبكة السيرفرات الجديدة 🔥

# 🔥 فتح أمر البداية للكل مع صائد الأخطاء ومطابقة الـ ID 🔥
@bot.message_handler(commands=['start'])
def start_command(message):
    chat_id = message.chat.id
    try:
        # مقارنة دقيقة للتأكد من التعرف على الأدمن
        if str(chat_id) == str(config.ADMIN_ID):
            admin_start.show_main_menu(bot, chat_id)
        else:
            # توجيه المستخدم العادي
            user_handlers.show_user_main_menu(bot, chat_id)
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ عذراً، حدث خطأ داخلي في البوت:\n`{e}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "server_status", is_admin=True)
def send_server_status(call):
    text = get_server_status_text()
    markup = get_status_keyboard()
    bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("status_"), is_admin=True)
def handle_status_callbacks(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    if call.data == "status_refresh":
        text = get_server_status_text()
        markup = get_status_keyboard()
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")
        bot.answer_callback_query(call.id, "✅ تم تحديث بيانات السيرفر!")
        
    elif call.data == "status_live":
        bot.answer_callback_query(call.id, "📡 تم تفعيل المراقبة الحية لمدة دقيقتين!")
        live_monitors[msg_id] = True
        markup = get_status_keyboard(is_live=True)
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=markup)
        
        def live_update_thread():
            end_time = time.time() + 120
            while time.time() < end_time and live_monitors.get(msg_id, False):
                time.sleep(3)
                if not live_monitors.get(msg_id, False): break
                try:
                    text = get_server_status_text()
                    markup = get_status_keyboard(is_live=True)
                    bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")
                except: pass
            
            live_monitors[msg_id] = False
            try:
                final_text = get_server_status_text() + "\n*(انتهت المراقبة المستمرة)*"
                markup = get_status_keyboard(is_live=False)
                bot.edit_message_text(final_text, chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")
            except: pass

        threading.Thread(target=live_update_thread).start()
        
    elif call.data == "status_stop":
        live_monitors[msg_id] = False
        bot.answer_callback_query(call.id, "🛑 تم إيقاف المراقبة الحية.")

# ==========================================
# 🔍 قسم التشخيص وسجل الأخطاء
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "run_diagnostics", is_admin=True)
def run_diagnostics(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id, "🔍 جاري الفحص...")
    
    import json
    import sqlite3
    from database import JSON_DB_PATH, SQLITE_DB_PATH, load_db
    
    report = "🔍 **تقرير التشخيص الشامل**\n"
    report += "━━━━━━━━━━━━━━━━━━\n\n"
    
    # التشخيص التفصيلي من panel_api
    report += api.run_stats_diagnostic()
    
    # 6. قاعدة بيانات JSON
    report += "**6️⃣ قاعدة بيانات JSON:**\n"
    try:
        db = load_db()
        active = sum(1 for d in db.values() if d.get('is_active', True))
        with_usage = sum(1 for d in db.values() if d.get('used_bytes', 0) > 0)
        report += f"  📄 المسار: `{JSON_DB_PATH}`\n"
        report += f"  👥 إجمالي المشتركين: {len(db)}\n"
        report += f"  🟢 النشطين: {active}\n"
        report += f"  📊 لديهم استهلاك: {with_usage}\n"
        if db:
            for email, data in list(db.items())[:3]:
                used = data.get('used_bytes', 0)
                used_str = f"{used/1024/1024:.2f} MB" if used > 0 else "0"
                report += f"  └ `{email}`: {used_str}\n"
    except Exception as e:
        report += f"  ❌ خطأ: `{e}`\n"
    
    report += "\n"
    
    # 7. قاعدة بيانات SQLite
    report += "**7️⃣ قاعدة بيانات SQLite:**\n"
    try:
        if os.path.exists(SQLITE_DB_PATH):
            conn = sqlite3.connect(SQLITE_DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users WHERE status='active'")
            active_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE total_connection_seconds > 0")
            with_time = c.fetchone()[0]
            conn.close()
            report += f"  📄 المسار: `{SQLITE_DB_PATH}`\n"
            report += f"  🟢 النشطين: {active_count}\n"
            report += f"  ⏱️ لديهم وقت اتصال: {with_time}\n"
        else:
            report += f"  ❌ الملف غير موجود: `{SQLITE_DB_PATH}`\n"
    except Exception as e:
        report += f"  ❌ خطأ: `{e}`\n"
    
    report += "\n"
    
    # 8. سجل الأخطاء
    report += "**8️⃣ آخر الأخطاء:**\n"
    error_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'monitor_error.log')
    try:
        if os.path.exists(error_log) and os.path.getsize(error_log) > 0:
            with open(error_log, 'r') as f:
                lines = f.readlines()
                last_errors = lines[-5:]
                for line in last_errors:
                    report += f"  `{line.strip()}`\n"
        else:
            report += "  لا توجد أخطاء مسجلة\n"
    except:
        report += "  ⚠️ تعذرت القراءة\n"
    
    report += "\n━━━━━━━━━━━━━━━━━━\n"
    report += f"⏱️ _وقت الفحص: {time.strftime('%Y-%m-%d %H:%M:%S')}_"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 إعادة الفحص", callback_data="run_diagnostics"))
    markup.add(InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="admin_main_menu"))
    
    try:
        bot.edit_message_text(report, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, report, reply_markup=markup, parse_mode="Markdown")

# ==========================================
# 4. تشغيل النظام بالكامل
# ==========================================
if __name__ == "__main__":
    print(f"🚀 البوت يعمل الآن للأدمن ID: {config.ADMIN_ID}")
    
    threading.Thread(target=start_quota_monitor, daemon=True).start()
    threading.Thread(target=start_radar_monitor, daemon=True).start()
    
    # تشغيل مراقب الإشعارات التلقائية للعملاء بالخلفية
    threading.Thread(target=start_notifier, args=(bot,), daemon=True).start()
    
    print("📡 نظام الرادار ومراقبة الوقت يعملان الآن بالخلفية...")
    
    try:
        # إضافة timeout لتجنب توقف البوت فجأة
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ حدث خطأ في البوت: {e}")
