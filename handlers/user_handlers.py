import os
import time
import datetime
import json
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# مسار قاعدة البيانات المباشر (للاستغناء عن الاستدعاء الخارجي)
HOME_DIR = os.path.expanduser("~")
SQLITE_DB_PATH = f'{HOME_DIR}/v2ray_manager/bot_data.db'

# ==========================================
# 🛠️ دوال قاعدة البيانات المدمجة (مستقلة 100%)
# ==========================================
def link_user_subscription(chat_id, email):
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT email FROM users WHERE email=?", (email,))
        if c.fetchone():
            c.execute('''CREATE TABLE IF NOT EXISTS user_subscriptions
                         (chat_id TEXT, email TEXT, PRIMARY KEY (chat_id, email))''')
            try:
                c.execute("INSERT INTO user_subscriptions (chat_id, email) VALUES (?, ?)", (str(chat_id), email))
                conn.commit()
                success = True
            except sqlite3.IntegrityError:
                success = False # مربوط مسبقاً
        else:
            success = False # غير موجود بالأساس
        conn.close()
        return success
    except Exception as e:
        print(f"DB Link Error: {e}")
        return False

def get_user_subscriptions(chat_id):
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS user_subscriptions
                     (chat_id TEXT, email TEXT, PRIMARY KEY (chat_id, email))''')
        c.execute("SELECT email FROM user_subscriptions WHERE chat_id=?", (str(chat_id),))
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        print(f"DB Get Subs Error: {e}")
        return []

def get_subscription_details(email):
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT expiry_date, quota_bytes, status, last_seen, total_connection_seconds FROM users WHERE email=?", (email,))
        data = c.fetchone()
        conn.close()
        return data
    except Exception as e:
        print(f"DB Details Error: {e}")
        return None

# ==========================================
# 📱 أوامر البوت للمشتركين العاديين
# ==========================================
def register_user_handlers(bot):
    @bot.callback_query_handler(func=lambda call: call.data == "add_user_sub")
    def add_sub_callback(call):
        msg = bot.send_message(call.message.chat.id, "📝 **الرجاء إرسال اسم الاشتراك الخاص بك:**\n(أرسل الاسم كما استلمته من المبيعات بالضبط)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_sub, bot)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_sub_"))
    def view_sub_callback(call):
        email = call.data.split("view_sub_")[1]
        show_sub_details(bot, call.message.chat.id, email, call.message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "user_main_menu")
    def back_to_main(call):
        show_user_main_menu(bot, call.message.chat.id, call.message.message_id)

def process_add_sub(message, bot):
    email = message.text.strip()
    chat_id = message.chat.id
    try:
        success = link_user_subscription(chat_id, email)
        
        if success:
            bot.send_message(chat_id, f"✅ **تم إضافة الحساب بنجاح!**\nتم ربط الاشتراك `{email}` بحسابك.", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "❌ **عذراً!** إما أن الاسم غير صحيح، أو أنه مربوط بحساب آخر مسبقاً.", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ حدث خطأ أثناء ربط الحساب: {e}")
    
    show_user_main_menu(bot, chat_id)

def show_user_main_menu(bot, chat_id, message_id=None):
    try:
        subs = get_user_subscriptions(chat_id)
        markup = InlineKeyboardMarkup(row_width=1)
        
        markup.add(InlineKeyboardButton("➕ إضافة حساب اشتراك", callback_data="add_user_sub"))
        
        for sub in subs:
            markup.add(InlineKeyboardButton(f"👤 {sub}", callback_data=f"view_sub_{sub}"))
            
        text = "👋 **مرحباً بك في بوابة المشتركين!**\n\nمن خلال هذا البوت يمكنك:\n🔹 متابعة استهلاكك للبيانات\n🔹 معرفة متى ينتهي اشتراكك\n🔹 استلام تنبيهات التجديد\n\n👇 اضغط على **إضافة حساب اشتراك** وأرسل اسمك لربط حسابك."
        
        if message_id:
            try: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
            except: bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ حدث خطأ في القائمة: {e}")

def show_sub_details(bot, chat_id, email, message_id):
    try:
        details = get_subscription_details(email)
        if not details:
            bot.send_message(chat_id, "❌ حدث خطأ في جلب بيانات الاشتراك.")
            return
        
        expiry_date, quota_bytes, status, last_seen, total_sec = details
        
        # 1. جلب الاستهلاك الفعلي بدقة (من ملف JSON)
        used_bytes = 0
        try:
            for json_name in ["users_db.json", "database.json", "data.json"]:
                db_path = os.path.join(HOME_DIR, "v2ray_manager", json_name)
                if os.path.exists(db_path):
                    with open(db_path, 'r', encoding='utf-8') as f:
                        db_data = json.load(f)
                        if email in db_data:
                            used_bytes = db_data[email].get('used_bytes', 0)
                            break
        except:
            pass
            
        used_gb = used_bytes / (1024**3)
        used_mb = used_bytes / (1024**2)
        used_str = f"{used_gb:.2f} GB" if used_gb >= 1 else f"{used_mb:.2f} MB"
        quota_str = "بلا حدود ♾️" if quota_bytes == 0 else f"{quota_bytes / (1024**3):.2f} GB"

        # 2. حساب الوقت المتبقي
        now = time.time()
        expiry_time = float(expiry_date)
        time_left = expiry_time - now
        
        # 3. 🔥 النظام الذكي لمعرفة حالة الاتصال الحقيقية (متصل / غير متصل) 🔥
        is_online = False
        if last_seen:
            try:
                # تحويل وقت آخر ظهور إلى ثواني للمقارنة
                last_seen_dt = datetime.datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
                last_seen_ts = last_seen_dt.timestamp()
                # إذا كان آخر ظهور خلال آخر 3 دقائق (180 ثانية)، نعتبره متصل
                if now - last_seen_ts <= 180:
                    is_online = True
            except:
                pass

        if time_left <= 0:
            time_str = "منتهي ❌"
            status_icon = "⚫ منتهي الصلاحية"
        else:
            days = int(time_left // 86400)
            hours = int((time_left % 86400) // 3600)
            time_str = f"{days} يوم و {hours} ساعة"
            
            # تحديد الأيقونة والنص بناءً على حالة الرادار
            if status == 'active':
                if is_online:
                    status_icon = "🟢 متصل الآن"
                else:
                    status_icon = "🔴 غير متصل"
            else:
                status_icon = "🔴 متوقف من الإدارة"
        
        # 4. فورمات الوقت الكلي (مع الحماية من القيم الفارغة)
        total_sec = total_sec or 0
        total_hours = int(total_sec // 3600)
        total_mins = int((total_sec % 3600) // 60)
        
        last_seen_str = last_seen if last_seen else "لم يتصل بعد"

        text = f"📊 **تفاصيل الاشتراك:** `{email}`\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"🚦 **الحالة:** {status_icon}\n"
        text += f"⏳ **الوقت المتبقي:** {time_str}\n"
        text += f"📅 **موعد الانتهاء:** {datetime.datetime.fromtimestamp(expiry_time).strftime('%Y-%m-%d %H:%M')}\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"📉 **الاستهلاك:** `{used_str}` من أصل `{quota_str}`\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"📡 **آخر ظهور:** {last_seen_str}\n"
        text += f"⏱️ **إجمالي وقت التشغيل:** {total_hours} ساعة و {total_mins} دقيقة\n"
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🛒 تجديد الاشتراك", url="https://t.me/l_t22"))
        markup.add(InlineKeyboardButton("📢 قناة التحديثات", url="https://t.me/r338888"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="user_main_menu"))
        
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ حدث خطأ في جلب التفاصيل: {e}")
