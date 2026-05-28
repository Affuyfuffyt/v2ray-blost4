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
            return str(obj.message.chat.id) == str(config.ADMIN_ID) or is_admin_in_db(str(obj.message.chat.id))
        # إذا كانت رسالة نصية عادية (Message)
        return str(obj.chat.id) == str(config.ADMIN_ID) or is_admin_in_db(str(obj.chat.id))

bot.add_custom_filter(IsAdmin())

def check_is_admin(chat_id):
    """فحص إذا المستخدم أدمن (المالك الرئيسي أو أدمن مضاف)"""
    return str(chat_id) == str(config.ADMIN_ID) or is_admin_in_db(chat_id)

def is_owner(chat_id):
    """فحص إذا المستخدم هو المالك الرئيسي (اللي بملف .env)"""
    return str(chat_id) == str(config.ADMIN_ID)

# ==========================================
# 📊 قسم حالة الخادم (Server Status)
# ==========================================
live_monitors = {}

def get_server_status_text():
    try:
        cpu_usage = subprocess.getoutput("top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}'")
        cpu_usage = float(cpu_usage) if cpu_usage else 0.0
        
        ram_total = int(subprocess.getoutput("free -m | grep Mem | awk '{print $2}'"))
        ram_used = int(subprocess.getoutput("free -m | grep Mem | awk '{print $3}'"))
        ram_percent = int((ram_used / ram_total) * 100) if ram_total > 0 else 0
        
        disk_total = subprocess.getoutput("df -h / | tail -1 | awk '{print $2}'")
        disk_used = subprocess.getoutput("df -h / | tail -1 | awk '{print $3}'")
        disk_percent_str = subprocess.getoutput("df -h / | tail -1 | awk '{print $5}'").replace('%', '')
        disk_percent = int(disk_percent_str) if disk_percent_str.isdigit() else 0

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
servers_flow.register_servers_handlers(bot) 

# 🔥 المتحكم المركزي الموحد لزر "الرجوع" (يسيطر على كل الملفات) 🔥
@bot.callback_query_handler(func=lambda call: call.data in ["main_menu", "admin_main_menu", "back"])
def global_back_handler(call):
    chat_id = call.message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id) 
    if check_is_admin(chat_id):
        admin_start.show_main_menu(bot, chat_id, call.message.message_id)
    else:
        user_handlers.show_user_main_menu(bot, chat_id, call.message.message_id)

# 🔥 فتح أمر البداية للكل مع صائد الأخطاء ومطابقة الـ ID 🔥
@bot.message_handler(commands=['start'])
def start_command(message):
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id) 
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
# 👑 قسم إدارة الأدمنية (تم الدمج بنجاح)
# ==========================================
admin_add_state = {}

@bot.callback_query_handler(func=lambda call: call.data == "manage_admins", is_admin=True)
def manage_admins_menu(call):
    chat_id = call.message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id)
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
    bot.clear_step_handler_by_chat_id(chat_id)
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
    bot.clear_step_handler_by_chat_id(chat_id)
    bot.answer_callback_query(call.id, "تم الإلغاء")
    show_admins_panel(chat_id, call.message.message_id)

@bot.message_handler(func=lambda msg: admin_add_state.get(msg.chat.id) and is_owner(msg.chat.id))
def handle_admin_id_input(msg):
    chat_id = msg.chat.id
    admin_add_state.pop(chat_id, None)
    bot.clear_step_handler_by_chat_id(chat_id)
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
    bot.clear_step_handler_by_chat_id(chat_id)
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
