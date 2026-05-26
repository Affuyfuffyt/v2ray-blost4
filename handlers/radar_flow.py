from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import get_active_users, get_full_radar_stats
import time
from datetime import datetime

# دالة ذكية لتحويل الثواني إلى (ساعات، دقائق، ثواني) بشكل مرتب
def format_duration(seconds):
    try:
        seconds = int(seconds)
    except:
        seconds = 0
    if seconds == 0:
        return "0 ثانية"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h > 0: parts.append(f"{h} ساعة")
    if m > 0: parts.append(f"{m} دقيقة")
    if s > 0 or not parts: parts.append(f"{s} ثانية")
    return " و ".join(parts)

def register_radar_handlers(bot):
    
    # ==========================================
    # 1️⃣ اللوحة الرئيسية للرادار (عرض الأزرار)
    # ==========================================
    @bot.callback_query_handler(func=lambda call: call.data == "radar_status")
    def show_radar(call):
        chat_id = call.message.chat.id
        
        try:
            active_users = get_active_users()
            markup = InlineKeyboardMarkup(row_width=1)
            now = datetime.now()
            
            online_count = 0
            today_count = 0
            offline_count = 0
            
            online_btns = []
            today_btns = []
            offline_btns = []
            
            for user in active_users:
                try:
                    email = str(user[0])
                    stats = get_full_radar_stats(email)
                    
                    if not stats or not stats.get("last_seen") or stats["last_seen"] == "None" or stats["last_seen"] == "NULL":
                        offline_btns.append(InlineKeyboardButton(f"🔴 {email} (خامل)", callback_data=f"ruser_{email}"))
                        offline_count += 1
                        continue
                        
                    last_seen_str = str(stats["last_seen"])
                    
                    try:
                        last_seen_dt = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
                        diff = (now - last_seen_dt).total_seconds()
                    except:
                        offline_btns.append(InlineKeyboardButton(f"🔴 {email} (خامل)", callback_data=f"ruser_{email}"))
                        offline_count += 1
                        continue
                    
                    if diff <= 120:
                        online_btns.append(InlineKeyboardButton(f"🟢 {email} (متصل الآن)", callback_data=f"ruser_{email}"))
                        online_count += 1
                    elif diff <= 86400:
                        today_btns.append(InlineKeyboardButton(f"🟡 {email} (نشط اليوم)", callback_data=f"ruser_{email}"))
                        today_count += 1
                    else:
                        offline_btns.append(InlineKeyboardButton(f"🔴 {email} (غير متصل)", callback_data=f"ruser_{email}"))
                        offline_count += 1
                except Exception as inner_e:
                    continue

            for btn in online_btns: markup.add(btn)
            for btn in today_btns: markup.add(btn)
            for btn in offline_btns: markup.add(btn)

            text = f"📡 **رادار السيرفر المركزي**\n━━━━━━━━━━━━━━━\n"
            text += f"🟢 متصل الآن: {online_count}\n"
            text += f"🟡 نشط اليوم: {today_count}\n"
            text += f"🔴 خامل: {offline_count}\n\n"
            text += "👇 **اضغط على اسم المشترك لعرض لوحته الاستخباراتية:**"

            markup.add(InlineKeyboardButton("🔄 تحديث الرادار", callback_data="radar_status"))
            markup.add(InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="admin_main_menu"))

            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "✅ تم التحديث")
            
        except Exception as e:
            error_msg = str(e).lower()
            # 🔥 الحل السحري لخطأ التلجرام: إذا ماكو تغيير بالبيانات، تجاهل الخطأ 🔥
            if "message is not modified" in error_msg:
                bot.answer_callback_query(call.id, "✅ اللوحة محدثة بالفعل (لا يوجد تغيير).")
            else:
                bot.send_message(chat_id, f"⚠️ حدث خطأ غير متوقع:\n`{str(e)}`", parse_mode="Markdown")

    # ==========================================
    # 2️⃣ اللوحة الاستخباراتية (تفاصيل المشترك)
    # ==========================================
    @bot.callback_query_handler(func=lambda call: call.data.startswith("ruser_"))
    def show_user_radar_details(call):
        chat_id = call.message.chat.id
        email = call.data.split("ruser_")[1]
        
        try:
            stats = get_full_radar_stats(email)
            if not stats:
                bot.answer_callback_query(call.id, "❌ لا توجد بيانات لهذا المشترك حالياً!")
                return
            
            last_seen = stats.get("last_seen")
            if not last_seen or last_seen == "None" or last_seen == "NULL":
                last_seen = "لم يتصل أبداً"
            
            status_emoji = "🔴 لم يتصل"
            if last_seen != "لم يتصل أبداً":
                try:
                    now = datetime.now()
                    last_seen_dt = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
                    diff = (now - last_seen_dt).total_seconds()
                    
                    if diff <= 120:
                        status_emoji = "🟢 متصل الآن"
                        last_seen = "الآن (نشط)"
                    elif diff <= 86400:
                        status_emoji = "🟡 كان متصل اليوم"
                    else:
                        status_emoji = "🔴 غير متصل"
                except:
                    pass

            text = f"🕵️‍♂️ **اللوحة الاستخباراتية للمشترك:** `{email}`\n"
            text += f"━━━━━━━━━━━━━━━━━\n"
            text += f"📡 **حالة الاتصال:** {status_emoji}\n"
            text += f"👁️ **آخر ظهور:** `{last_seen}`\n\n"
            
            text += f"⏳ **إجمالي وقت الاتصال:**\n└ `{format_duration(stats.get('total_seconds', 0))}`\n\n"
            text += f"📅 **وقت الاتصال لليوم:**\n└ `{format_duration(stats.get('today_seconds', 0))}`\n"
            text += f"━━━━━━━━━━━━━━━━━\n"
            
            if stats.get("history"):
                text += "🗂️ **أرشيف الأيام السابقة:**\n"
                for record in stats["history"][:7]: 
                    text += f"▪️ `{record['date']}` ⬅️ {format_duration(record['seconds'])}\n"
            else:
                text += "📭 لا يوجد أرشيف لأيام سابقة."

            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 تحديث بيانات المشترك", callback_data=f"ruser_{email}"))
            markup.add(InlineKeyboardButton("🔙 رجوع للرادار", callback_data="radar_status"))

            bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "✅ تم التحديث")
            
        except Exception as e:
            error_msg = str(e).lower()
            if "message is not modified" in error_msg:
                bot.answer_callback_query(call.id, "✅ البيانات محدثة بالفعل.")
            else:
                bot.send_message(chat_id, f"⚠️ خطأ في التفاصيل:\n`{str(e)}`", parse_mode="Markdown")
