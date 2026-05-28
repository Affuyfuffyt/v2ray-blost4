import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import subprocess
import time
import config
import os
from xray_core.panel_api import PanelAPI
from db import is_admin_in_db, add_admin, remove_admin, get_all_admins

# استدعاء المعالجات
from handlers import admin_start, create_flow, manage_flow, speed_test, radar_flow
from handlers import user_handlers # ملف واجهة المشتركين
from handlers import servers_flow # 🔥 إضافة ملف إدارة السيرفرات الجديد 🔥

# استدعاء المراقبين
try:
    from user_notifier import start_notifier
except ImportError:
    def start_notifier(bot): pass

# 1. تهيئة البوت والـ API
bot = telebot.TeleBot(config.BOT_TOKEN)
api = PanelAPI()

def check_is_admin(chat_id):
    """فحص إذا المستخدم أدمن (المالك الرئيسي أو أدمن مضاف)"""
    return str(chat_id) == str(config.ADMIN_ID) or is_admin_in_db(chat_id)

def is_owner(chat_id):
    """فحص إذا المستخدم هو المالك الرئيسي (اللي بملف .env)"""
    return str(chat_id) == str(config.ADMIN_ID)

class IsAdmin(telebot.custom_filters.SimpleCustomFilter):
    key = 'is_admin'
    def check(self, obj):
        if hasattr(obj, 'message'):
            return check_is_admin(obj.message.chat.id)
        return check_is_admin(obj.chat.id)

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
        if check_is_admin(chat_id):
            admin_start.show_main_menu(bot, chat_id)
        else:
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
    
    # 5. قاعدة بيانات JSON
    report += "**5️⃣ قاعدة بيانات JSON:**\n"
    try:
        db = load_db()
        active = sum(1 for d in db.values() if d.get('is_active', True))
        report += f"  📄 المسار: `{JSON_DB_PATH}`\n"
        report += f"  👥 إجمالي المشتركين: {len(db)}\n"
        report += f"  🟢 النشطين: {active}\n"
    except Exception as e:
        report += f"  ❌ خطأ: `{e}`\n"
    
    report += "\n"
    
    # 6. قاعدة بيانات SQLite
    report += "**6️⃣ قاعدة بيانات SQLite:**\n"
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
    
    # 7. سجل الأخطاء
    report += "**7️⃣ آخر الأخطاء:**\n"
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
# 👑 قسم إدارة الأدمنية
# ==========================================
admin_add_state = {}

@bot.callback_query_handler(func=lambda call: call.data == "manage_admins", is_admin=True)
def manage_admins_menu(call):
    chat_id = call.message.chat.id
    if not is_owner(chat_id):
        bot.answer_callback_query(call.id, "⛔ فقط المالك الرئيسي يقدر يدير الأدمنية!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    show_admins_panel(chat_id, call.message.message_id)

def show_admins_panel(chat_id, message_id=None):
    admins = get_all_admins()
    text = "👑 **إدارة الأدمنية**\n"
    text += "━━━━━━━━━━━━━━━━━━\n\n"
    text += f"👤 **المالك الرئيسي:** `{config.ADMIN_ID}`\n\n"
    if admins:
        text += f"📋 **الأدمنية المضافين ({len(admins)}):**\n"
        for i, (admin_id, added_by, added_at) in enumerate(admins, 1):
            date_str = added_at[:10] if added_at else "?"
            text += f"  {i}. `{admin_id}` (أضيف: {date_str})\n"
    else:
        text += "📋 لا يوجد أدمنية مضافين حالياً\n"

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ إضافة أدمن جديد", callback_data="admin_add_new"))
    if admins:
        markup.add(InlineKeyboardButton("🗑️ حذف أدمن", callback_data="admin_remove_menu"))
    markup.add(InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="admin_main_menu"))

    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        except:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_new", is_admin=True)
def admin_add_new(call):
    chat_id = call.message.chat.id
    if not is_owner(chat_id):
        bot.answer_callback_query(call.id, "⛔ فقط المالك الرئيسي!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    admin_add_state[chat_id] = True
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ إلغاء", callback_data="admin_cancel_add"))
    bot.edit_message_text(
        "👑 **إضافة أدمن جديد**\n\n"
        "أرسل **ID** الأدمن الجديد (الرقم فقط):\n\n"
        "💡 _يمكن للأدمن الجديد معرفة الـ ID الخاص به عن طريق بوت @userinfobot_",
        chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_cancel_add", is_admin=True)
def admin_cancel_add(call):
    chat_id = call.message.chat.id
    admin_add_state.pop(chat_id, None)
    bot.answer_callback_query(call.id, "تم الإلغاء")
    show_admins_panel(chat_id, call.message.message_id)

@bot.message_handler(func=lambda msg: admin_add_state.get(msg.chat.id) and is_owner(msg.chat.id))
def handle_admin_id_input(msg):
    chat_id = msg.chat.id
    admin_add_state.pop(chat_id, None)
    new_id = msg.text.strip()

    if not new_id.lstrip('-').isdigit():
        bot.send_message(chat_id, "❌ الـ ID لازم يكون رقم فقط. جرب مرة ثانية.")
        show_admins_panel(chat_id)
        return

    if str(new_id) == str(config.ADMIN_ID):
        bot.send_message(chat_id, "ℹ️ هذا هو ID المالك الرئيسي — موجود تلقائياً.")
        show_admins_panel(chat_id)
        return

    success = add_admin(new_id, added_by=str(chat_id))
    if success:
        bot.send_message(chat_id, f"✅ تم إضافة الأدمن `{new_id}` بنجاح!", parse_mode="Markdown")
    else:
        bot.send_message(chat_id, f"ℹ️ الأدمن `{new_id}` موجود مسبقاً!", parse_mode="Markdown")
    show_admins_panel(chat_id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_remove_menu", is_admin=True)
def admin_remove_menu(call):
    chat_id = call.message.chat.id
    if not is_owner(chat_id):
        bot.answer_callback_query(call.id, "⛔ فقط المالك الرئيسي!", show_alert=True)
        return
    bot.answer_callback_query(call.id)

    admins = get_all_admins()
    if not admins:
        bot.edit_message_text("📋 لا يوجد أدمنية لحذفهم.", chat_id, call.message.message_id)
        return

    markup = InlineKeyboardMarkup(row_width=1)
    for admin_id, _, _ in admins:
        markup.add(InlineKeyboardButton(f"🗑️ حذف {admin_id}", callback_data=f"admin_del_{admin_id}"))
    markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="manage_admins"))

    bot.edit_message_text("🗑️ **اختر الأدمن لحذفه:**", chat_id, call.message.message_id,
                          reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_del_"), is_admin=True)
def admin_delete(call):
    chat_id = call.message.chat.id
    if not is_owner(chat_id):
        bot.answer_callback_query(call.id, "⛔ فقط المالك الرئيسي!", show_alert=True)
        return

    target_id = call.data.replace("admin_del_", "")
    success = remove_admin(target_id)
    if success:
        bot.answer_callback_query(call.id, f"✅ تم حذف الأدمن {target_id}")
    else:
        bot.answer_callback_query(call.id, f"❌ الأدمن {target_id} غير موجود")
    show_admins_panel(chat_id, call.message.message_id)

# ==========================================
# 4. تشغيل النظام بالكامل
# ==========================================
if __name__ == "__main__":
    print(f"🚀 البوت يعمل الآن للأدمن ID: {config.ADMIN_ID}")
    
    # تشغيل مراقب الإشعارات التلقائية للعملاء بالخلفية
    threading.Thread(target=start_notifier, args=(bot,), daemon=True).start()
    
    try:
        # إضافة timeout لتجنب توقف البوت فجأة
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ حدث خطأ في البوت: {e}")
