from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import uuid
import random
import string
import json
import base64
import time
import requests
import threading
import os
import urllib.parse
import ftplib
from io import BytesIO
import sqlite3

# 👇 استدعاء دوال الحفظ وقاعدة البيانات
from database import save_user, extend_json_expiry
from db import (
    add_user, get_active_users, set_user_expired, get_user_by_ref_code,
    extend_user_expiry, assign_ref_code, add_pending_reward,
    get_all_pending_rewards, remove_pending_reward, get_user_connection_seconds,
    get_all_servers, get_server_details, SQLITE_DB_PATH
)

# 👇 استدعاء واجهة الباندل المحلية (Xray-core)
try:
    from xray_core.panel_api import PanelAPI
except Exception:
    PanelAPI = None

# 👇 استدعاء نظام الإشعارات
try:
    from user_notifier import notify_extension
except ImportError:
    def notify_extension(bot, email, seconds_added): pass

creation_data = {}
watchdog_started = False

# ==========================================
# 🛡️ أداة مساعدة: التحقق من صحة الـ UUID
# ==========================================
def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except Exception:
        return False

# ==========================================
# 🛠️ دالة الإضافة الذكية (VLESS فقط - المسار الموحد)
# ==========================================
def add_client_to_config(user_name, uuid_val, protocol, server_id=1, bot=None, chat_id=None):
    """تضيف مشترك جديد إلى ملف config.json (محلي أو بعيد عبر FTP)."""
    try:
        # ===== السيرفر المحلي: نستخدم PanelAPI لإدارة الكونفك والريستارت =====
        if server_id == 1:
            if PanelAPI is None:
                if bot and chat_id:
                    bot.send_message(chat_id, "❌ لا يمكن تحميل وحدة PanelAPI المحلية.")
                return False
            api = PanelAPI()
            ok = api.create_client(user_name, uuid_val, protocol)
            if not ok and bot and chat_id:
                bot.send_message(chat_id, "❌ فشل في إضافة المشترك إلى السيرفر المحلي.")
            return ok

        # ===== السيرفر البعيد: نتصل عبر FTP =====
        server = get_server_details(server_id)
        if not server:
            if bot and chat_id:
                bot.send_message(chat_id, f"❌ السيرفر رقم {server_id} غير موجود.")
            return False

        s_id, s_name, s_site_id, s_api, s_host, s_user, s_pass = server
        ftp_domain = s_host if s_host.startswith("ftp-") else f"ftp-{s_host}"

        ftp = ftplib.FTP(ftp_domain)
        ftp.login(s_user, s_pass)
        try:
            r = BytesIO()
            ftp.retrbinary("RETR xray_core/config.json", r.write)
            config_data = json.loads(r.getvalue().decode('utf-8'))

            # ⚠️ إصلاح setdefault: يجب أن نُمرّر القاموس فعلياً، لا قاموس مؤقت
            inbounds = config_data.setdefault("inbounds", [])
            if not inbounds:
                if bot and chat_id:
                    bot.send_message(chat_id, "❌ السيرفر البعيد لا يحتوي على inbounds في الكونفك.")
                return False

            inbound  = inbounds[0]
            settings = inbound.setdefault("settings", {})
            clients  = settings.setdefault("clients", [])

            already = any(
                c.get("id") == uuid_val or c.get("email") == user_name
                for c in clients
            )
            if not already:
                clients.append({"id": uuid_val, "email": user_name, "level": 0})

                w = BytesIO(json.dumps(config_data, indent=2, ensure_ascii=False).encode('utf-8'))
                ftp.storbinary("STOR xray_core/config.json", w)
            return True
        finally:
            try: ftp.quit()
            except Exception: pass

    except Exception as e:
        print(f"Error adding to config: {e}")
        if bot and chat_id:
            bot.send_message(chat_id, f"⚠️ خطأ في تعديل ملف السيرفر: {e}")
        return False

# ==========================================
# 🗑️ دالة حذف المشترك المنتهي
# ==========================================
def remove_client_from_config(uuid_val, server_id=1):
    """تحذف مشترك بناءً على الـ UUID من ملف config.json (محلي أو بعيد)."""
    try:
        # ===== السيرفر المحلي =====
        if server_id == 1:
            if PanelAPI is None:
                return False
            return PanelAPI().remove_client(uuid_val)

        # ===== السيرفر البعيد =====
        server = get_server_details(server_id)
        if not server:
            return False

        s_id, s_name, s_site_id, s_api, s_host, s_user, s_pass = server
        ftp_domain = s_host if s_host.startswith("ftp-") else f"ftp-{s_host}"
        ftp = ftplib.FTP(ftp_domain)
        ftp.login(s_user, s_pass)
        try:
            r = BytesIO()
            ftp.retrbinary("RETR xray_core/config.json", r.write)
            config_data = json.loads(r.getvalue().decode('utf-8'))

            modified = False
            for inbound in config_data.get("inbounds", []):
                settings = inbound.get("settings") or {}
                clients  = settings.get("clients") or []
                new_clients = [c for c in clients if c.get("id") != uuid_val]
                if len(new_clients) != len(clients):
                    settings["clients"] = new_clients
                    inbound["settings"] = settings
                    modified = True

            if modified:
                w = BytesIO(json.dumps(config_data, indent=2, ensure_ascii=False).encode('utf-8'))
                ftp.storbinary("STOR xray_core/config.json", w)
            return True
        finally:
            try: ftp.quit()
            except Exception: pass

    except Exception as e:
        print(f"Error removing from config: {e}")
        return False

# ==========================================
# 🔄 دالة عمل ريستارت للسيرفر (مركزي عبر Alwaysdata API)
# ==========================================
def restart_alwaysdata(bot=None, chat_id=None, success_msg=None, fail_msg=None, server_id=1):
    try:
        SITE_ID = None
        API_KEY = None

        if server_id == 1:
            home_dir = os.path.expanduser("~")
            key_file = f"{home_dir}/alwaysdata_keys.txt"
            if os.path.exists(key_file):
                with open(key_file, 'r') as f:
                    lines = f.read().strip().split('\n')
                    if len(lines) >= 2:
                        SITE_ID = lines[0].strip()
                        API_KEY = lines[1].strip()
        else:
            server = get_server_details(server_id)
            if not server: return False
            SITE_ID = server[2]
            API_KEY = server[3]

        if not SITE_ID or not API_KEY:
            if bot and chat_id:
                bot.send_message(chat_id, "⚠️ لم يتم العثور على مفاتيح Alwaysdata.")
            return False

        url = f"https://api.alwaysdata.com/v1/site/{SITE_ID}/restart/"
        response = requests.post(url, auth=(API_KEY, ''), timeout=15)

        if bot and chat_id:
            if response.status_code in [200, 201, 202, 204]:
                bot.send_message(chat_id, success_msg, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, f"{fail_msg}\nكود الخطأ: {response.status_code}")
        return response.status_code in [200, 201, 202, 204]
    except Exception as e:
        if bot and chat_id:
            bot.send_message(chat_id, "⚠️ حدث خطأ في الاتصال بمنصة Alwaysdata.")
        print(f"Restart Error: {e}")
    return False

# ==========================================
# ⏱️ العداد التنازلي لطرد المشترك
# ==========================================
def auto_restart_on_expiry(bot, chat_id, expiry_time, user_name, uuid_val, protocol, server_id=1):
    wait_seconds = expiry_time - time.time()
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    # حذف المشترك من الكونفك (محلي أو بعيد)
    remove_client_from_config(uuid_val, server_id)

    success_msg = f"🛑 **تنبيه انتهاء صلاحية!** 🛑\n\n👤 المشترك: `{user_name}`\n⏳ انتهى وقته للتو.\n🔄 **تم سحب صلاحيته من السيرفر نهائياً!**"
    fail_msg = f"⚠️ انتهى وقت `{user_name}` ولكن فشل الريستارت التلقائي للسيرفر!"
    restart_alwaysdata(bot, chat_id, success_msg, fail_msg, server_id)


# ==========================================
# 👁️ مراقب قاعدة البيانات
# ==========================================
def database_expiry_watchdog(bot):
    admin_id = None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, ".env")

    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith("ADMIN_ID="):
                    try: admin_id = int(line.strip().split("=")[1])
                    except: pass

    while True:
        try:
            # 1. مراقبة انتهاء المشتركين
            active_users = get_active_users()
            current_time = time.time()
            expired_by_server = {}

            for email, uuid_val, expiry_date, s_id in active_users:
                if expiry_date and current_time >= float(expiry_date):
                    remove_client_from_config(uuid_val, s_id)
                    set_user_expired(email)
                    if s_id not in expired_by_server: expired_by_server[s_id] = []
                    expired_by_server[s_id].append(email)

            if admin_id:
                for s_id, names in expired_by_server.items():
                    success = restart_alwaysdata(server_id=s_id)
                    names_str = "\n".join([f"• `{n}`" for n in names])
                    if success:
                        msg = f"🛑 **تنبيه الطرد التلقائي!** 🛑\n\nالمنتهين في سيرفر ({s_id}):\n{names_str}\n\n🔄 **تم سحب الصلاحيات وعمل ريستارت للسيرفر لطردهم!**"
                    else:
                        msg = f"⚠️ تم مسح المشتركين ({names_str}) من السيرفر ({s_id}) ولكن فشل الريستارت!"
                    bot.send_message(admin_id, msg, parse_mode="Markdown")

            # 2. مراقبة المكافآت المعلقة
            pending_rewards = get_all_pending_rewards()
            for ref_email, inv_email, reward_sec, c_id in pending_rewards:
                if get_user_connection_seconds(inv_email) >= 60:
                    extend_user_expiry(ref_email, reward_sec)
                    try: extend_json_expiry(ref_email, reward_sec)
                    except: pass
                    
                    # 🔥 التعديل الجراحي: إضافة زراعة الكود من جديد وعمل ريستارت 🔥
                    try:
                        conn = sqlite3.connect(SQLITE_DB_PATH)
                        c = conn.cursor()
                        c.execute("SELECT uuid, server_id, expiry_date FROM users WHERE email=?", (ref_email,))
                        row = c.fetchone()
                        
                        if row:
                            user_uuid, user_server_id, current_expiry = row
                            now = time.time()
                            
                            # تصحيح المشكلة: إذا الكود كان منتهي قبل المكافأة، نجدد الوقت من اللحظة الحالية!
                            if current_expiry and float(current_expiry) < now:
                                new_expiry = now + reward_sec
                                c.execute("UPDATE users SET expiry_date=?, status='active' WHERE email=?", (str(new_expiry), ref_email))
                                conn.commit()
                            
                            # 1. زراعة الكود من جديد في ملف الكونفك
                            add_client_to_config(ref_email, user_uuid, "vless", user_server_id, bot, c_id)
                            
                            # 2. عمل ريستارت فوري لتفعيل الكود وإدخاله بالسيرفر
                            restart_alwaysdata(bot, c_id, f"🔄 تم تحديث السيرفر لتفعيل مكافأة الدعوة للمشترك `{ref_email}`! 🚀", f"⚠️ فشل الريستارت التلقائي للسيرفر ({user_server_id}).", user_server_id)
                            
                        conn.close()
                    except Exception as e:
                        print(f"Replant Error: {e}")
                    # 🔥 نهاية التعديل الجراحي 🔥

                    remove_pending_reward(inv_email)

                    bot.send_message(c_id, f"🎉 **تم تفعيل المكافأة المعلقة!**\n\nتم تمديد وقت المشترك الداعي `{ref_email}` وتمت إعادة زراعته في السيرفر بنجاح! 🚀", parse_mode="Markdown")
                    notify_extension(bot, ref_email, reward_sec)
        except Exception as e:
            pass
        time.sleep(60)

# ==========================================
# 🆕 بناء وتوزيع الكود
# ==========================================
def register_create_handlers(bot):
    global watchdog_started
    if not watchdog_started:
        threading.Thread(target=database_expiry_watchdog, args=(bot,), daemon=True).start()
        watchdog_started = True

    @bot.callback_query_handler(func=lambda call: call.data == "create_code")
    def start_creation(call):
        chat_id = call.message.chat.id
        servers = get_all_servers()

        if not servers:
            bot.send_message(chat_id, "❌ لا توجد سيرفرات متاحة. يرجى تهيئة قاعدة البيانات أو إضافة سيرفر.")
            return

        markup = InlineKeyboardMarkup(row_width=1)
        for s in servers:
            s_id, s_name, s_site_id, s_status = s
            if s_status == 'active':
                markup.add(InlineKeyboardButton(f"🖥️ {s_name}", callback_data=f"sel_srv_{s_id}"))
        markup.add(InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="admin_main_menu"))

        bot.edit_message_text("🌐 **في أي سيرفر تريد إنشاء المشترك؟**", chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("sel_srv_"))
    def process_server_selection(call):
        chat_id = call.message.chat.id
        server_id = int(call.data.split("_")[2])
        creation_data[chat_id] = {'server_id': server_id}

        msg = bot.send_message(chat_id, "📝 أرسل اسم المشترك (باللغة الإنجليزية وبدون مسافات):")
        bot.register_next_step_handler(msg, process_name, bot)

    def process_name(message, bot):
        chat_id = message.chat.id
        creation_data[chat_id]['name'] = message.text.strip()

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⏭️ تخطي كود الدعوة", callback_data="skip_referral"))
        msg = bot.send_message(chat_id, "🎁 **نظام المكافآت والدعوات:**\nإذا كان المشترك قادماً عن طريق شخص آخر، أرسل (كود دعوة) الشخص الداعي الآن ليتم مكافأته.\n\n👇 أو اضغط تخطي للاستمرار:", reply_markup=markup, parse_mode="Markdown")
        bot.register_next_step_handler(msg, check_referral_text, bot)

    @bot.callback_query_handler(func=lambda call: call.data == "skip_referral")
    def skip_ref(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id)
        ask_protocol(chat_id, bot, call.message.message_id)

    def check_referral_text(message, bot):
        chat_id = message.chat.id
        ref_code = message.text.strip()
        referrer = get_user_by_ref_code(ref_code)

        if referrer:
            referrer_email = referrer[0]
            creation_data[chat_id]['referrer'] = referrer_email

            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("تمديد 5 أيام 🎁", callback_data="rew_5"),
                InlineKeyboardButton("تمديد 10 أيام 🎁", callback_data="rew_10"),
                InlineKeyboardButton("تمديد 30 يوم 🎁", callback_data="rew_30"),
                InlineKeyboardButton("إدخال يدوي ✍️", callback_data="rew_manual"),
                InlineKeyboardButton("إلغاء التمديد والتخطي ⏭️", callback_data="skip_referral")
            )
            bot.send_message(chat_id, f"✅ **كود صحيح!**\nهذا الكود يعود للمشترك: `{referrer_email}`\n\nاختر كم تريد أن تمدد صلاحيته كمكافأة للدعوة:", reply_markup=markup, parse_mode="Markdown")
        else:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⏭️ الاستمرار بدون مكافأة (تخطي)", callback_data="skip_referral"))
            msg = bot.send_message(chat_id, "❌ كود الدعوة غير صحيح أو غير موجود!\nتأكد من الكود وأرسله مجدداً، أو اضغط تخطي:", reply_markup=markup)
            bot.register_next_step_handler(msg, check_referral_text, bot)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("rew_"))
    def process_reward(call):
        chat_id = call.message.chat.id
        choice = call.data.split('_')[1]

        if choice == "manual":
            bot.clear_step_handler_by_chat_id(chat_id)
            msg = bot.send_message(chat_id, "✍️ أرسل مدة التمديد:\n(مثال: `5m` لدقائق، `2h` لساعات، `10d` لأيام، `1mo` لشهر)", parse_mode="Markdown")
            bot.register_next_step_handler(msg, manual_reward_input, bot)
        else:
            days = int(choice)
            apply_reward(chat_id, bot, days * 86400)

    def manual_reward_input(message, bot):
        chat_id = message.chat.id
        text = message.text.lower().strip()

        try:
            if text.endswith('mo'): sec = int(text[:-2]) * 86400 * 30
            elif text.endswith('m'): sec = int(text[:-1]) * 60
            elif text.endswith('h'): sec = int(text[:-1]) * 3600
            elif text.endswith('d'): sec = int(text[:-1]) * 86400
            else:
                raise ValueError("invalid format")
        except Exception:
            msg = bot.send_message(chat_id, "❌ صيغة خاطئة! حاول مجدداً (مثال: `5m`, `2h`, `10d`, `1mo`):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, manual_reward_input, bot)
            return

        apply_reward(chat_id, bot, sec)

    def apply_reward(chat_id, bot, seconds):
        referrer_email = creation_data[chat_id].get('referrer')
        if referrer_email:
            creation_data[chat_id]['reward_seconds'] = seconds
            bot.send_message(chat_id, f"⏳ **تم تعليق المكافأة!**\nسيتم تفعيل المكافأة للداعي `{referrer_email}` **تلقائياً** بعد أن يتصل المشترك الجديد بالإنترنت لمدة دقيقة واحدة.", parse_mode="Markdown")
        ask_protocol(chat_id, bot)

    def ask_protocol(chat_id, bot, message_id=None):
        # تم تخطي سؤال البروتوكول، لأنه الآن VLESS إجباري
        creation_data[chat_id]['protocol'] = 'vless'
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("بورت 443 (TLS) 🔒", callback_data="port_443"),
            InlineKeyboardButton("بورت 80 🌐", callback_data="port_80"),
            InlineKeyboardButton("إدخال البورت يدوياً ✍️", callback_data="port_manual")
        )
        text = "🚪 اختر البورت:"
        if message_id:
            try: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            except: bot.send_message(chat_id, text, reply_markup=markup)
        else:
            bot.send_message(chat_id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("port_"))
    def process_port(call):
        chat_id = call.message.chat.id
        port_val = call.data.split('_')[1]
        if port_val == "manual":
            msg = bot.send_message(chat_id, "✍️ أرسل رقم البورت:")
            bot.register_next_step_handler(msg, lambda m: save_port_and_ask_ws(m, bot))
        else:
            creation_data[chat_id]['port'] = int(port_val)
            ask_ws(chat_id, bot, call.message.message_id)

    def save_port_and_ask_ws(message, bot):
        chat_id = message.chat.id
        try:
            creation_data[chat_id]['port'] = int(message.text.strip())
        except ValueError:
            msg = bot.send_message(chat_id, "❌ رقم البورت غير صالح. أرسل رقماً صحيحاً:")
            bot.register_next_step_handler(msg, lambda m: save_port_and_ask_ws(m, bot))
            return
        ask_ws(chat_id, bot)

    def ask_ws(chat_id, bot, message_id=None):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("WebSocket (WS) 🌐", callback_data="net_ws"))
        text = "📡 اختر نوع الشبكة:"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "net_ws")
    def process_ws(call):
        chat_id = call.message.chat.id
        creation_data[chat_id]['network'] = 'ws'
        ask_uuid(chat_id, bot, call.message.message_id)

    def ask_uuid(chat_id, bot, message_id=None):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("ID عشوائي 🎲", callback_data="id_random"),
            InlineKeyboardButton("ID يدوي ✍️", callback_data="id_manual")
        )
        text = "🔑 اختر المعرف (UUID):"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("id_"))
    def process_uuid(call):
        chat_id = call.message.chat.id
        choice = call.data.split('_')[1]
        if choice == "random":
            creation_data[chat_id]['uuid'] = str(uuid.uuid4())
            ask_ips(chat_id, bot, call.message.message_id)
        else:
            msg = bot.send_message(chat_id, "✍️ أرسل المعرف (UUID) بصيغة صحيحة (مثال: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx):")
            bot.register_next_step_handler(msg, lambda m: save_uuid_and_ask_ips(m, bot))

    def save_uuid_and_ask_ips(message, bot):
        chat_id = message.chat.id
        uuid_in = message.text.strip()
        if not is_valid_uuid(uuid_in):
            msg = bot.send_message(chat_id, "❌ UUID غير صالح. حاول مجدداً (مثال صحيح: `0782c5d7-3cfc-43dd-8fcf-74722ed2124f`):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: save_uuid_and_ask_ips(m, bot))
            return
        creation_data[chat_id]['uuid'] = uuid_in
        ask_ips(chat_id, bot)

    def ask_ips(chat_id, bot, message_id=None):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("متصل واحد 📱", callback_data="ip_1"), InlineKeyboardButton("العدد يدوي ✍️", callback_data="ip_manual"))
        text = "👥 حدد عدد الأجهزة المسموحة:"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("ip_"))
    def process_ips(call):
        chat_id = call.message.chat.id
        choice = call.data.split('_')[1]
        if choice == "manual":
            msg = bot.send_message(chat_id, "✍️ أرسل عدد الأجهزة (أرقام فقط):")
            bot.register_next_step_handler(msg, lambda m: save_ips_and_ask_duration(m, bot))
        else:
            creation_data[chat_id]['ips'] = int(choice)
            ask_duration(chat_id, bot, call.message.message_id)

    def save_ips_and_ask_duration(message, bot):
        chat_id = message.chat.id
        try:
            creation_data[chat_id]['ips'] = int(message.text)
            ask_duration(chat_id, bot)
        except ValueError:
            msg = bot.send_message(chat_id, "❌ خطأ! أرسل رقماً صحيحاً للأجهزة:")
            bot.register_next_step_handler(msg, lambda m: save_ips_and_ask_duration(m, bot))

    def ask_duration(chat_id, bot, message_id=None):
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("1 دقيقة ⏱️", callback_data="dur_1m"),
            InlineKeyboardButton("1 ساعة ⏳", callback_data="dur_1h"),
            InlineKeyboardButton("يوم", callback_data="dur_1d"),
            InlineKeyboardButton("شهر", callback_data="dur_30d"),
            InlineKeyboardButton("سنة", callback_data="dur_365d"),
            InlineKeyboardButton("مدة يدوية ✍️", callback_data="dur_manual")
        )
        text = "⏳ حدد مدة الكود:"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("dur_"))
    def process_duration(call):
        chat_id = call.message.chat.id
        choice = call.data.split('_')[1]
        if choice == "manual":
            msg = bot.send_message(chat_id, "✍️ أرسل المدة (مثال: 5m لدقائق، 2h لساعات، 10d لأيام، 1y لسنة):")
            bot.register_next_step_handler(msg, lambda m: save_duration_and_ask_quota(m, bot))
        else:
            creation_data[chat_id]['duration_str'] = choice
            ask_quota(chat_id, bot, call.message.message_id)

    def save_duration_and_ask_quota(message, bot):
        chat_id = message.chat.id
        text = message.text.lower().strip()
        if not (text.endswith('m') or text.endswith('h') or text.endswith('d') or text.endswith('y') or text.isdigit()):
            msg = bot.send_message(chat_id, "❌ خطأ! أرسل صيغة صحيحة (مثال 10m, 2h, 5d):")
            bot.register_next_step_handler(msg, lambda m: save_duration_and_ask_quota(m, bot))
            return
        creation_data[chat_id]['duration_str'] = text
        ask_quota(chat_id, bot)

    def ask_quota(chat_id, bot, message_id=None):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("10 MB", callback_data="quota_10m"),
            InlineKeyboardButton("100 MB", callback_data="quota_100m"),
            InlineKeyboardButton("100 GB", callback_data="quota_100g"),
            InlineKeyboardButton("1000 GB", callback_data="quota_1000g"),
            InlineKeyboardButton("بلا حدود ♾️", callback_data="quota_unlimited"),
            InlineKeyboardButton("سعة يدوية ✍️", callback_data="quota_manual")
        )
        text = "📊 حدد سعة الاستهلاك (Quota):"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("quota_"))
    def process_quota(call):
        chat_id = call.message.chat.id
        choice = call.data.split('_')[1]
        if choice == "manual":
            msg = bot.send_message(chat_id, "✍️ أرسل السعة بالجيجابايت (مثال: 50):")
            bot.register_next_step_handler(msg, lambda m: finalize_creation(m, bot, is_manual=True))
        else:
            quota_map = {
                "10m": 10 * 1024 * 1024,
                "100m": 100 * 1024 * 1024,
                "100g": 100 * 1024 * 1024 * 1024,
                "1000g": 1000 * 1024 * 1024 * 1024,
                "unlimited": 0
            }
            creation_data[chat_id]['quota_bytes'] = quota_map[choice]
            finalize_creation(call.message, bot, is_manual=False)

    def finalize_creation(message, bot, is_manual):
        chat_id = message.chat.id
        if is_manual:
            try:
                gb_val = float(message.text)
                creation_data[chat_id]['quota_bytes'] = int(gb_val * 1024 * 1024 * 1024)
            except ValueError:
                msg = bot.send_message(chat_id, "❌ خطأ! أرسل رقماً فقط:")
                bot.register_next_step_handler(msg, lambda m: finalize_creation(m, bot, is_manual=True))
                return

        data = creation_data[chat_id]
        server_id = data.get('server_id', 1)
        protocol = "vless"  # تم تثبيت البروتوكول إجبارياً
        fixed_path = "/xray"  # تم تثبيت المسار الجديد
        data['path'] = fixed_path

        dur_str = data['duration_str']
        try:
            if dur_str.endswith('m'): sec = int(dur_str[:-1]) * 60
            elif dur_str.endswith('h'): sec = int(dur_str[:-1]) * 3600
            elif dur_str.endswith('d'): sec = int(dur_str[:-1]) * 86400
            elif dur_str.endswith('y'): sec = int(dur_str[:-1]) * 86400 * 365
            else: sec = int(dur_str) * 86400
        except ValueError:
            bot.send_message(chat_id, "❌ صيغة المدة غير صحيحة.")
            creation_data.pop(chat_id, None)
            return

        expiry_time = time.time() + sec

        # الإضافة لملف config.json
        bot.send_message(chat_id, "⏳ جاري زراعة الكود في السيرفر المطلوب، يرجى الانتظار...")
        success = add_client_to_config(data['name'], data['uuid'], protocol, server_id, bot, chat_id)

        if not success:
            bot.send_message(chat_id, "❌ فشلت عملية الإضافة! راجع رسائل الخطأ أعلاه.")
            creation_data.pop(chat_id, None)
            return

        try: save_user(data['name'], data['uuid'], data['quota_bytes'], expiry_time)
        except: pass

        try:
            selected_port = data.get('port', 443)
            add_user(data['name'], data['uuid'], selected_port, data['quota_bytes'], expiry_time, server_id)
        except Exception as e:
            print(f"Error saving to SQLite DB: {e}")

        # المكافآت
        new_ref_code = "REF-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        try: assign_ref_code(data['name'], new_ref_code)
        except: pass

        reward_sec = data.get('reward_seconds')
        referrer_email = data.get('referrer')
        if reward_sec and referrer_email:
            try: add_pending_reward(referrer_email, data['name'], reward_sec, chat_id)
            except: pass

        threading.Thread(
            target=auto_restart_on_expiry,
            args=(bot, chat_id, expiry_time, data['name'], data['uuid'], protocol, server_id),
            daemon=True
        ).start()

        selected_port = data.get('port', 443)

        local_user = os.path.basename(os.path.expanduser("~"))
        host_domain = f"{local_user}.alwaysdata.net"

        if server_id == 1:
            try:
                home_dir = os.path.expanduser("~")
                key_file = f"{home_dir}/alwaysdata_keys.txt"
                if os.path.exists(key_file):
                    with open(key_file, 'r') as f:
                        lines = f.read().strip().split('\n')
                        if len(lines) >= 3 and lines[2].strip() != "":
                            host_domain = lines[2].strip()
            except: pass
        else:
            srv = get_server_details(server_id)
            if srv:
                raw_host = srv[4]
                if raw_host.startswith("ftp-"):
                    raw_host = raw_host[4:]
                host_domain = raw_host

        if selected_port == 443:
            security_type = "tls"
            sni_param = host_domain
            sni_str = f"&sni={sni_param}"
        else:
            security_type = "none"
            sni_param = ""
            sni_str = ""

        encoded_path = urllib.parse.quote(fixed_path, safe='')

        # توليد كود VLESS فقط
        final_link = f"vless://{data['uuid']}@{host_domain}:{selected_port}?type=ws&security={security_type}&path={encoded_path}&host={host_domain}{sni_str}#{data['name']}"

        quota_display = "بلا حدود ♾️" if data['quota_bytes'] == 0 else f"{data['quota_bytes'] / (1024**3):.2f} GB"

        srv_name = "السيرفر المحلي" if server_id == 1 else srv[1]
        summary = f"""
✅ **تم إنشاء الكود وتفعيله بنجاح!**

🖥️ **السيرفر المستخدم:** `{srv_name}`
👤 **الاسم:** `{data['name']}`
🌐 **البروتوكول:** `VLESS`
🚪 **البورت:** `{selected_port}`
⏳ **المدة:** `{data['duration_str']}`
📊 **السعة:** `{quota_display}`
🎁 **كود الدعوة الخاص به:** `{new_ref_code}`

🔗 **انسخ الكود أدناه والصقه في تطبيق (DarkTunnel أو v2rayNG):**
`{final_link}`
        """
        bot.send_message(chat_id, summary, parse_mode="Markdown")
        creation_data.pop(chat_id, None)

        time.sleep(1)
        success_msg = f"🔄 تم الريستارت التلقائي للسيرفر ({srv_name}) بنجاح! 🚀 الكود هسه شغال."
        fail_msg = f"⚠️ الكود انحفظ، بس فشل الريستارت التلقائي للسيرفر ({srv_name})."
        restart_alwaysdata(bot, chat_id, success_msg, fail_msg, server_id)
