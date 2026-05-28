import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def show_main_menu(bot, chat_id, message_id=None):
    # إنشاء لوحة المفاتيح الشفافة
    markup = InlineKeyboardMarkup(row_width=1)
    
    # الأزرار الأساسية
    btn_create = InlineKeyboardButton("➕ إنشاء كود جديد", callback_data="create_code")
    btn_manage = InlineKeyboardButton("👥 إدارة المشتركين", callback_data="manage_users")
    
    # 🔥 الزر الجديد: إدارة السيرفرات 🔥
    btn_servers = InlineKeyboardButton("🌐 إدارة شبكة السيرفرات", callback_data="manage_servers")
    
    # رادار السيرفر
    btn_radar = InlineKeyboardButton("📡 رادار السيرفر (المتصلين الآن)", callback_data="radar_status")
    
    # الأزرار الباقية
    btn_speed = InlineKeyboardButton("📈 فحص الاستهلاك المباشر (Live Test)", callback_data="speed_test")
    btn_server = InlineKeyboardButton("🖥️ حالة الخادم", callback_data="server_status")
    btn_diag = InlineKeyboardButton("🔍 سجل التشخيص والأخطاء", callback_data="run_diagnostics")
    btn_admins = InlineKeyboardButton("👑 إدارة الأدمنية", callback_data="manage_admins")
    
    # ترتيب الأزرار في اللوحة
    markup.add(btn_create)
    markup.add(btn_manage)
    markup.add(btn_servers)
    markup.add(btn_radar)
    markup.add(btn_speed)
    markup.add(btn_server)
    markup.add(btn_diag)
    markup.add(btn_admins)
    
    welcome_text = "⚙️ مرحباً بك في لوحة تحكم V2Ray (النسخة الاحترافية)\nاختر من القائمة أدناه:"
    
    if message_id:
        try:
            bot.edit_message_text(welcome_text, chat_id, message_id, reply_markup=markup)
        except:
            bot.send_message(chat_id, welcome_text, reply_markup=markup)
    else:
        bot.send_message(chat_id, welcome_text, reply_markup=markup)
