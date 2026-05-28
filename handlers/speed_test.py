import os
import json
import time

# 🔥 الحل الجذري: مسار ديناميكي يكتشف مجلد البوت تلقائياً 🔥
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEED_FILE = os.path.join(BASE_DIR, 'live_speed.json')

def register_speed_handlers(bot):
    # تم تصحيح الكول باك ليتطابق مع الزر في اللوحة الرئيسية
    @bot.callback_query_handler(func=lambda call: call.data == "speed_test")
    def ask_test_duration(call):
        chat_id = call.message.chat.id
        msg = bot.send_message(chat_id, "⏱️ أرسل عدد الثواني لإجراء الفحص (مثال: 10 أو 20):")
        bot.register_next_step_handler(msg, run_speed_test, bot)

    def run_speed_test(message, bot):
        chat_id = message.chat.id
        try:
            duration = int(message.text)
            if duration > 60:
                bot.send_message(chat_id, "❌ الحد الأقصى للفحص هو 60 ثانية لحماية السيرفر من الحظر.")
                return
        except:
            bot.send_message(chat_id, "❌ يرجى إرسال رقم صحيح للثواني.")
            return

        status_msg = bot.send_message(chat_id, "🔄 جاري الاتصال بالسيرفر لبدء الفحص المباشر...")
        
        # تحديث الرسالة كل ثانية لتعطيك شعور الـ Dashboard المباشر!
        for i in range(duration):
            try:
                if os.path.exists(SPEED_FILE):
                    with open(SPEED_FILE, 'r') as f:
                        speed_data = json.load(f)
                else:
                    speed_data = {'down_bps': 0, 'up_bps': 0}
                
                # تحويل البايت إلى ميجابايت (MB/s)
                down_mb = speed_data.get('down_bps', 0) / (1024 * 1024)
                up_mb = speed_data.get('up_bps', 0) / (1024 * 1024)
                
                text = f"📈 **مراقب السيرفر المباشر (Live)**\n\n"
                text += f"⏱️ الوقت المتبقي: `{duration - i}` ثانية\n\n"
                text += f"⬇️ سرعة التنزيل الحالية: `{down_mb:.2f} MB/s`\n"
                text += f"⬆️ سرعة الرفع الحالية: `{up_mb:.2f} MB/s`\n\n"
                text += "*(يتم التحديث تلقائياً بالثانية...)*"
                
                bot.edit_message_text(text, chat_id, status_msg.message_id, parse_mode="Markdown")
            except Exception as e:
                pass
            
            time.sleep(1) # التحديث بالتيليجرام كل ثانية
            
        bot.edit_message_text(f"✅ **انتهى الفحص بنجاح.**\nالمدة الإجمالية: {duration} ثواني.", chat_id, status_msg.message_id, parse_mode="Markdown")
