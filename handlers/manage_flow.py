from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import uuid
import json
import time 
import requests 
import threading 
import os 
import sqlite3
from datetime import datetime
from database import load_db, update_db
from xray_core.panel_api import PanelAPI

# 👇 استدعاء نظام الإشعارات لإبلاغ العميل
try:
    from user_notifier import notify_extension
except ImportError:
    def notify_extension(bot, email, seconds_added): pass

# قاموس لحفظ بيانات التمديد المؤقتة
renew_data = {}

# 🔥 مسار قاعدة البيانات الذكي 🔥
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_data.db')

# ==========================================
# 🛠️ دوال العملية الجراحية لملف الكونفك والريستارت
# ==========================================
def add_client_to_config(user_name, uuid_val, protocol):
    try:
        home_dir = os.path.expanduser("~")
        config_path = f"{home_dir}/xray_core/config.json"
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            modified = False
            if "inbounds" in config_data:
                for inbound in config_data["inbounds"]:
                    # تنظيف أخطاء الـ API القديمة
                    if inbound.get("protocol") == "trojan" and "settings" in inbound:
                        clients = inbound["settings"].setdefault("clients", [])
                        for c in clients:
                            if "id" in c: 
                                c["password"] = c.pop("id")
                                modified = True

                    # إضافة المشترك حسب التاك
                    if inbound.get("tag") == protocol and "settings" in inbound:
                        clients = inbound["settings"].setdefault("clients", [])
                        exists = any(c.get("id") == uuid_val or c.get("password") == uuid_val for c in clients)
                        if not exists:
                            if protocol == "vless":
                                clients.append({"id": uuid_val, "email": user_name, "flow": ""})
                            elif protocol == "vmess":
                                clients.append({"id": uuid_val, "email": user_name, "alterId": 0})
                            elif protocol == "trojan":
                                clients.append({"password": uuid_val, "email": user_name})
                            modified = True
                        break 
                        
            if modified:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"Error adding to config: {e}")

def remove_client_from_config(uuid_val):
    try:
        home_dir = os.path.expanduser("~")
        config_path = f"{home_dir}/xray_core/config.json"
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            modified = False
            if "inbounds" in config_data:
                for inbound in config_data["inbounds"]:
                    if "settings" in inbound and "clients" in inbound["settings"]:
                        original = inbound["settings"]["clients"]
                        new_clients = [c for c in original if c.get("id") != uuid_val and c.get("password") != uuid_val]
                        if len(original) != len(new_clients):
                            inbound["settings"]["clients"] = new_clients
                            modified = True
                            
            if modified:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"Error removing from config: {e}")

def restart_alwaysdata(bot, chat_id, success_msg, fail_msg):
    try:
        home_dir = os.path.expanduser("~")
        key_file = f"{home_dir}/alwaysdata_keys.txt"
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                lines = f.read().strip().split('\n')
                if len(lines) >= 2:
                    SITE_ID = lines[0].strip()
                    API_KEY = lines[1].strip()
                    url = f"https://api.alwaysdata.com/v1/site/{SITE_ID}/restart/"
                    response = requests.post(url, auth=(API_KEY, ''))
                    if response.status_code in [200, 201, 202, 204]:
                        bot.send_message(chat_id, success_msg, parse_mode="Markdown")
                    else:
                        bot.send_message(chat_id, f"{fail_msg}\nكود الخطأ: {response.status_code}")
                else:
                    bot.send_message(chat_id, "⚠️ ملف alwaysdata_keys.txt ناقص بيانات.")
        else:
            bot.send_message(chat_id, "⚠️ لم يتم العثور على ملف alwaysdata_keys.txt.")
    except Exception as e:
        bot.send_message(chat_id, "⚠️ حدث خطأ في الاتصال بمنصة Alwaysdata.")
        print(f"Restart Error: {e}")


def register_manage_handlers(bot):
    api = PanelAPI()

    # 1. زر إظهار قائمة المشتركين
    @bot.callback_query_handler(func=lambda call: call.data == "manage_users")
    def show_users_list(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id) # 🔥 تنظيف الأوامر المعلقة
        db = load_db()
        
        if not db:
            bot.answer_callback_query(call.id, "📭 لا يوجد مشتركون حالياً.")
            return

        markup = InlineKeyboardMarkup(row_width=1)
        for email, data in db.items():
            status = "🟢" if data.get('is_active', True) else "🔴"
            markup.add(InlineKeyboardButton(f"{status} {email}", callback_data=f"user_{email}"))
        
        # 🔥 إضافة زر الرجوع للقائمة الرئيسية 🔥
        markup.add(InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="main_menu"))
        
        bot.edit_message_text("👥 **قائمة المشتركين:**\nاختر مشتركاً لعرض تفاصيله:", 
                              chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 2. زر تفاصيل المشترك
    @bot.callback_query_handler(func=lambda call: call.data.startswith("user_"))
    def show_user_details(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id) # 🔥 تنظيف الأوامر المعلقة
        email = call.data.split('user_')[1]
        
        db = load_db()
        if email not in db:
            bot.answer_callback_query(call.id, "❌ المشترك غير موجود.")
            return
            
        user = db[email]
        
        used_bytes = user.get('used_bytes', 0)
        used_mb = used_bytes / (1024 * 1024)
        used_gb = used_bytes / (1024**3)
        
        limit_bytes = user.get('limit_bytes', 0)
        limit_gb = limit_bytes / (1024**3)
        
        used_str = f"{used_gb:.2f} GB" if used_gb >= 1 else f"{used_mb:.2f} MB"
        limit_str = f"{limit_gb:.2f} GB" if limit_bytes > 0 else "بلا حدود ♾️"
        
        expiry_ts = user.get('expiry_time', 0)
        if expiry_ts > 0:
            expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%Y-%m-%d %H:%M:%S')
        else:
            expiry_date = "غير محدد"
            
        status = "فعال 🟢" if user.get('is_active', True) else "متوقف 🔴 (منتهي)"
        
        details = f"""
📊 **تفاصيل المشترك:** `{email}`
🔑 **المعرف:** `{user.get('uuid')}`
---
📉 **الاستهلاك الفعلي:** `{used_str}` من أصل `{limit_str}`
⏳ **موعد الانتهاء:** `{expiry_date}`
وضع الحساب: **{status}**
        """
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("♻️ تمديد وتصفير", callback_data=f"renew_{email}"),
            InlineKeyboardButton("🗑️ حذف نهائي", callback_data=f"del_{email}")
        )
        markup.add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="manage_users"))
        
        bot.edit_message_text(details, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # 3. الحذف النهائي (معدل ليحذف من الملف ويسوي ريستارت)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
    def delete_client(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id) # 🔥 تنظيف الأوامر المعلقة
        email = call.data.split("del_")[1]
        
        db_data = load_db()
        if email in db_data:
            uuid_val = db_data[email]['uuid']
            
            # 1. الحذف من API
            try: api.change_client_status(email, enable=False)
            except: pass
            try: api.delete_client(email)
            except: pass
            
            # 2. الحذف اليدوي من الكونفك لضمان الطرد
            remove_client_from_config(uuid_val)
            
            # 3. الحذف من JSON DB
            del db_data[email]
            update_db(db_data)
            
            # 4. الحذف من SQLite DB ديناميكياً
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE email=?", (email,))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"SQLite delete error: {e}")
            
            bot.edit_message_text(f"✅ تم حذف المشترك `{email}` من قاعدة البيانات.\n🔄 جاري عمل ريستارت لطرده نهائياً من السيرفر...", chat_id, call.message.message_id, parse_mode="Markdown")
            
            # 5. ريستارت فوري
            time.sleep(1)
            restart_alwaysdata(bot, chat_id, "✅ **تم طرد المشترك من السيرفر بنجاح!**", "⚠️ فشل الريستارت التلقائي أثناء الحذف.")
        else:
            bot.answer_callback_query(call.id, "❌ المشترك غير موجود أصلاً.")

    # ==================================================
    # 4. نظام التمديد (المطور مع الريستارت والبروتوكول)
    # ==================================================
    @bot.callback_query_handler(func=lambda call: call.data.startswith("renew_"))
    def start_renew(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id) # 🔥 تنظيف الأوامر المعلقة
        email = call.data.split("renew_")[1]
        renew_data[chat_id] = {'email': email}
        
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("1 دقيقة ⏱️", callback_data="rdur_1m"),
            InlineKeyboardButton("1 ساعة ⏳", callback_data="rdur_1h"),
            InlineKeyboardButton("يوم", callback_data="rdur_1d"),
            InlineKeyboardButton("شهر", callback_data="rdur_30d"),
            InlineKeyboardButton("مدة يدوية ✍️", callback_data="rdur_manual")
        )
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data=f"user_{email}")) # 🔥 زر رجوع
        
        bot.edit_message_text(f"♻️ تمديد للمشترك `{email}`\n\n⏳ اختر المدة الجديدة:", chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("rdur_"))
    def ask_renew_quota(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id) # 🔥 تنظيف الأوامر المعلقة
        choice = call.data.split('_')[1]
        
        if choice == "manual":
            msg = bot.send_message(chat_id, "✍️ أرسل المدة (مثال: `5m` لدقائق، `2h` لساعات، `10d` لأيام، `1mo` لشهر):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: save_rdur_manual(m, bot))
        else:
            renew_data[chat_id]['duration_str'] = choice
            show_renew_quota(chat_id, bot, call.message.message_id)

    # 🔥 تحديث إدخال المدة اليدوية (إضافة الدقائق m والأشهر mo) 🔥
    def save_rdur_manual(message, bot):
        chat_id = message.chat.id
        text = message.text.lower().strip()
        if not (text.endswith('mo') or text.endswith('m') or text.endswith('h') or text.endswith('d') or text.endswith('y') or text.isdigit()):
            msg = bot.send_message(chat_id, "❌ خطأ! أرسل صيغة صحيحة (مثال: `5m`, `2h`, `10d`, `1mo`):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: save_rdur_manual(m, bot))
            return
        renew_data[chat_id]['duration_str'] = text
        show_renew_quota(chat_id, bot)

    def show_renew_quota(chat_id, bot, message_id=None):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("100 MB", callback_data="rquota_100m"),
            InlineKeyboardButton("10 GB", callback_data="rquota_10g"),
            InlineKeyboardButton("100 GB", callback_data="rquota_100g"),
            InlineKeyboardButton("بلا حدود ♾️", callback_data="rquota_unlimited"),
            InlineKeyboardButton("سعة يدوية ✍️", callback_data="rquota_manual")
        )
        markup.add(InlineKeyboardButton("🔙 إلغاء والرجوع", callback_data="manage_users")) # 🔥 زر رجوع
        text = "📊 حدد السعة الجديدة للتمديد:"
        if message_id:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else:
            bot.send_message(chat_id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("rquota_"))
    def ask_renew_protocol(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id) # 🔥 تنظيف الأوامر المعلقة
        choice = call.data.split('_')[1]
        
        if choice == "manual":
            msg = bot.send_message(chat_id, "✍️ أرسل السعة بالجيجابايت (مثال: 50):")
            bot.register_next_step_handler(msg, lambda m: process_manual_quota(m, bot))
        else:
            quota_map = { "100m": 100*1024*1024, "10g": 10*1024**3, "100g": 100*1024**3, "unlimited": 0 }
            renew_data[chat_id]['new_quota'] = quota_map[choice]
            show_protocol_selection(chat_id, bot, call.message.message_id)

    def process_manual_quota(message, bot):
        chat_id = message.chat.id
        try:
            renew_data[chat_id]['new_quota'] = int(float(message.text) * 1024**3)
            show_protocol_selection(chat_id, bot)
        except:
            msg = bot.send_message(chat_id, "❌ خطأ! أرسل رقماً فقط:")
            bot.register_next_step_handler(msg, lambda m: process_manual_quota(m, bot))

    # 🔥 خطوة اختيار البروتوكول لضمان عمل التورجان بعد التمديد 🔥
    def show_protocol_selection(chat_id, bot, message_id=None):
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("VLESS", callback_data="rproto_vless"),
            InlineKeyboardButton("VMESS", callback_data="rproto_vmess"),
            InlineKeyboardButton("Trojan", callback_data="rproto_trojan")
        )
        markup.add(InlineKeyboardButton("🔙 إلغاء والرجوع", callback_data="manage_users")) # 🔥 زر رجوع
        text = "🌐 **أخيراً.. اختر بروتوكول المشترك لإعادة تفعيله:**"
        if message_id:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("rproto_"))
    def finalize_renew(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id) # 🔥 تنظيف الأوامر المعلقة
        protocol = call.data.split('_')[1]
        
        data = renew_data.get(chat_id)
        if not data: return
        
        email = data['email']
        new_quota = data['new_quota']
        dur_str = data['duration_str']
        
        if dur_str.endswith('mo'): sec = int(dur_str[:-2]) * 86400 * 30
        elif dur_str.endswith('m'): sec = int(dur_str[:-1]) * 60
        elif dur_str.endswith('h'): sec = int(dur_str[:-1]) * 3600
        elif dur_str.endswith('d'): sec = int(dur_str[:-1]) * 86400
        elif dur_str.endswith('y'): sec = int(dur_str[:-1]) * 86400 * 365
        else: sec = int(dur_str) * 86400
        
        new_expiry = time.time() + sec
        
        db_data = load_db()
        if email in db_data:
            uuid_val = db_data[email]['uuid']
            port_val = db_data[email].get('port', 443)
            
            # 1. تحديث JSON DB
            db_data[email]['limit_bytes'] = new_quota
            db_data[email]['expiry_time'] = new_expiry
            db_data[email]['used_bytes'] = 0 
            db_data[email]['is_active'] = True
            update_db(db_data)
            
            # 2. تحديث SQLite DB (ديناميكياً)
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE users SET quota_bytes=?, expiry_date=?, status='active' WHERE email=?", (new_quota, str(new_expiry), email))
                if c.rowcount == 0:
                    c.execute("INSERT INTO users (email, uuid, port, quota_bytes, expiry_date, status) VALUES (?, ?, ?, ?, ?, ?)",
                              (email, uuid_val, port_val, new_quota, str(new_expiry), 'active'))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"SQLite update error: {e}")
            
            # 3. زراعة المشترك يدوياً بالكونفك (لحل مشكلة التورجان)
            if protocol != "trojan":
                try: api.create_client(email, uuid_val, protocol)
                except: pass
            add_client_to_config(email, uuid_val, protocol)
            
            bot.edit_message_text(f"✅ **تم التمديد وتحديث قاعدة البيانات!**\n\n👤 المشترك: `{email}`\n🔄 جاري عمل ريستارت لتفعيل الكود...", chat_id, call.message.message_id, parse_mode="Markdown")
            
            # 4. ريستارت فوري ليعمل الكود
            time.sleep(1)
            restart_alwaysdata(bot, chat_id, "✅ **تم الريستارت! الكود شغال الآن 100%.** 🚀", "⚠️ التمديد نجح، بس فشل الريستارت التلقائي.")
            
            # 5. 🔥 إشعار العميل (المواطن) بالتمديد الجديد! 🔥
            notify_extension(bot, email, sec)
        
        renew_data.pop(chat_id, None)
