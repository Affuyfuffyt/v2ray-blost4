from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sys
import os

# إجبار الملف على قراءة المسار الرئيسي لقاعدة البيانات
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db

server_data = {}

def register_servers_handlers(bot):
    # 1. عرض قائمة السيرفرات
    @bot.callback_query_handler(func=lambda call: call.data == "manage_servers", is_admin=True)
    def show_servers_menu(call):
        chat_id = call.message.chat.id
        servers = db.get_all_servers()
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("➕ إضافة سيرفر جديد", callback_data="add_server"))
        
        for s in servers:
            s_id, s_name, s_site_id, s_status = s
            icon = "🟢" if s_status == 'active' else "🔴"
            markup.add(InlineKeyboardButton(f"{icon} {s_name}", callback_data=f"view_server_{s_id}"))
            
        markup.add(InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="admin_main_menu"))
        
        text = "🌐 **إدارة شبكة السيرفرات:**\n\nاختر سيرفر من القائمة أو قم بإضافة سيرفر جديد:"
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 2. الرجوع للقائمة الرئيسية
    @bot.callback_query_handler(func=lambda call: call.data == "admin_main_menu", is_admin=True)
    def back_to_main(call):
        from handlers import admin_start
        admin_start.show_main_menu(bot, call.message.chat.id, call.message.message_id)

    # 3. خطوات إضافة سيرفر جديد
    @bot.callback_query_handler(func=lambda call: call.data == "add_server", is_admin=True)
    def add_server_start(call):
        chat_id = call.message.chat.id
        msg = bot.send_message(chat_id, "📝 **أرسل اسم السيرفر الجديد:**\n(مثال: `سيرفر ألمانيا 1`، `Alwaysdata 2`)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_server_name, bot)

    def process_server_name(message, bot):
        chat_id = message.chat.id
        server_data[chat_id] = {'name': message.text.strip()}
        msg = bot.send_message(chat_id, "🔗 **أرسل الـ Site ID الخاص بالسيرفر:**\n(تجده في حساب Alwaysdata)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_site_id, bot)
        
    def process_site_id(message, bot):
        chat_id = message.chat.id
        server_data[chat_id]['site_id'] = message.text.strip()
        msg = bot.send_message(chat_id, "🔑 **أرسل الـ API Key الخاص بالسيرفر:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_api_key, bot)

    def process_api_key(message, bot):
        chat_id = message.chat.id
        server_data[chat_id]['api_key'] = message.text.strip()
        msg = bot.send_message(chat_id, "🌐 **أرسل الـ FTP Host:**\n(مثال: `ftp-wathfor.alwaysdata.net`)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_ftp_host, bot)
        
    def process_ftp_host(message, bot):
        chat_id = message.chat.id
        server_data[chat_id]['ftp_host'] = message.text.strip()
        msg = bot.send_message(chat_id, "👤 **أرسل الـ FTP User (اسم المستخدم):**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_ftp_user, bot)
        
    def process_ftp_user(message, bot):
        chat_id = message.chat.id
        server_data[chat_id]['ftp_user'] = message.text.strip()
        msg = bot.send_message(chat_id, "🔒 **أرسل الـ FTP Password (كلمة السر):**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_ftp_pass, bot)
        
    def process_ftp_pass(message, bot):
        chat_id = message.chat.id
        server_data[chat_id]['ftp_pass'] = message.text.strip()
        
        data = server_data[chat_id]
        try:
            db.add_server(data['name'], data['site_id'], data['api_key'], data['ftp_host'], data['ftp_user'], data['ftp_pass'])
            bot.send_message(chat_id, f"✅ **تمت إضافة السيرفر ({data['name']}) بنجاح!**", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ حدث خطأ أثناء الحفظ: {e}")
            
        from handlers import admin_start
        admin_start.show_main_menu(bot, chat_id)
        server_data.pop(chat_id, None)

    # 4. عرض تفاصيل السيرفر وحذفه
    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_server_"), is_admin=True)
    def view_server(call):
        chat_id = call.message.chat.id
        server_id = int(call.data.split("_")[2])
        
        server = db.get_server_details(server_id)
        if not server:
            bot.answer_callback_query(call.id, "❌ السيرفر غير موجود.")
            return
            
        s_id, s_name, s_site_id, s_api, s_host, s_user, s_pass = server
        
        text = f"🖥️ **تفاصيل السيرفر:**\n\n"
        text += f"📌 **الاسم:** `{s_name}`\n"
        text += f"🔗 **Site ID:** `{s_site_id}`\n"
        text += f"🌐 **FTP Host:** `{s_host}`\n"
        
        markup = InlineKeyboardMarkup(row_width=1)
        # نمنع حذف السيرفر الرئيسي (رقم 1) لأن بي المشتركين القدامى
        if s_id != 1: 
            markup.add(InlineKeyboardButton("🗑️ حذف السيرفر", callback_data=f"del_server_{s_id}"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="manage_servers"))
        
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("del_server_"), is_admin=True)
    def delete_server(call):
        server_id = int(call.data.split("_")[2])
        
        if server_id == 1:
            bot.answer_callback_query(call.id, "❌ لا يمكن حذف السيرفر الرئيسي!")
            return
            
        db.delete_server(server_id)
        bot.answer_callback_query(call.id, "✅ تم حذف السيرفر بنجاح!")
        
        # نرجع لقائمة السيرفرات بعد الحذف
        show_servers_menu(call)
