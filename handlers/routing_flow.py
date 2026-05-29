import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import ftplib
from io import BytesIO
from db import get_all_servers, get_server_details

# القائمة الذهبية الشاملة لملايين المواقع والتطبيقات
DEFAULT_DIRECT_DOMAINS = [
    "geosite:category-social-media", # كل مواقع التواصل (فيسبوك، انستكرام، تويتر، تيك توك، الخ)
    "geosite:category-entertainment", # كل مواقع الستريمنج (يوتيوب، نتفلكس، شاهد، الخ)
    "geosite:category-games", # كل سيرفرات الألعاب (ببجي، كول اوف ديوتي، الخ)
    "geosite:category-ecommerce", # كل المتاجر (أمازون، علي اكسبرس، الخ)
    "geosite:category-tech", # شركات التقنية
    "geosite:apple", # سيرفرات ابل وايكلاود
    "geosite:google", # سيرفرات جوجل وبلاي ستور
    "geosite:microsoft", # سيرفرات مايكروسوفت
    "geosite:amazon", # سيرفرات أمازون
    "geosite:speedtest", # مواقع فحص السرعة
    "domain:fast.com",
    "domain:pubgmobile.com"
]

user_states = {}

def get_config_from_server(server_id):
    if server_id == 1:
        try:
            home_dir = os.path.expanduser("~")
            with open(f"{home_dir}/xray_core/config.json", 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return None
    else:
        server = get_server_details(server_id)
        if not server: return None
        s_id, s_name, s_site_id, s_api, s_host, s_user, s_pass = server
        ftp_domain = s_host if s_host.startswith("ftp-") else f"ftp-{s_host}"
        try:
            ftp = ftplib.FTP(ftp_domain)
            ftp.login(s_user, s_pass)
            r = BytesIO()
            ftp.retrbinary("RETR xray_core/config.json", r.write)
            ftp.quit()
            return json.loads(r.getvalue().decode('utf-8'))
        except: return None

def save_config_to_server(server_id, config_data):
    if server_id == 1:
        try:
            home_dir = os.path.expanduser("~")
            with open(f"{home_dir}/xray_core/config.json", 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            return True
        except: return False
    else:
        server = get_server_details(server_id)
        if not server: return False
        s_id, s_name, s_site_id, s_api, s_host, s_user, s_pass = server
        ftp_domain = s_host if s_host.startswith("ftp-") else f"ftp-{s_host}"
        try:
            ftp = ftplib.FTP(ftp_domain)
            ftp.login(s_user, s_pass)
            w = BytesIO(json.dumps(config_data, indent=2, ensure_ascii=False).encode('utf-8'))
            ftp.storbinary("STOR xray_core/config.json", w)
            ftp.quit()
            return True
        except: return False

def register_routing_handlers(bot):
    
    @bot.callback_query_handler(func=lambda call: call.data == "manage_routing")
    def ask_server_for_routing(call):
        chat_id = call.message.chat.id
        bot.clear_step_handler_by_chat_id(chat_id)
        servers = get_all_servers()
        if not servers:
            bot.answer_callback_query(call.id, "❌ لا توجد سيرفرات متاحة.")
            return

        markup = InlineKeyboardMarkup(row_width=1)
        for s in servers:
            markup.add(InlineKeyboardButton(f"🖥️ {s[1]}", callback_data=f"rout_srv_{s[0]}"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="admin_main_menu"))

        bot.edit_message_text("🔀 **اختر السيرفر لإدارة المواقع המفتوحة السرعة فيه:**", chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("rout_srv_"))
    def show_routing_menu(call):
        chat_id = call.message.chat.id
        server_id = int(call.data.split("_")[2])
        user_states[chat_id] = {"server_id": server_id}
        
        config = get_config_from_server(server_id)
        if not config:
            bot.answer_callback_query(call.id, "❌ فشل الاتصال بالسيرفر وجلب الكونفك.")
            return

        domains = []
        try:
            rules = config.get("routing", {}).get("rules", [])
            for rule in rules:
                if rule.get("outboundTag") == "direct" and "domain" in rule:
                    domains = rule.get("domain", [])
                    break
        except: pass

        text = f"🔀 **إدارة المواقع المباشرة (السرعة القصوى)**\n\n"
        text += f"📊 عدد المواقع/التصنيفات المضافة حالياً: `{len(domains)}`\n\n"
        text += "💡 *المواقع المضافة هنا لا تمر عبر النفق السري (WARP)، مما يعطيها أقصى سرعة ممكنة للسيرفر.*"

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("👁️ عرض المواقع المضافة", callback_data="rout_view"))
        markup.add(InlineKeyboardButton("➕ إضافة موقع جديد", callback_data="rout_add"))
        markup.add(InlineKeyboardButton("🌟 وضع القائمة الذهبية (ملايين المواقع)", callback_data="rout_gold"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="manage_routing"))

        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data == "rout_view")
    def view_domains(call):
        chat_id = call.message.chat.id
        server_id = user_states.get(chat_id, {}).get("server_id", 1)
        config = get_config_from_server(server_id)
        
        domains = []
        try:
            for rule in config["routing"]["rules"]:
                if rule.get("outboundTag") == "direct" and "domain" in rule:
                    domains = rule["domain"]
                    break
        except: pass

        if not domains:
            bot.answer_callback_query(call.id, "القائمة فارغة حالياً!", show_alert=True)
            return

        text = "📋 **قائمة المواقع ذات السرعة القصوى:**\n\n"
        for i, d in enumerate(domains, 1):
            text += f"`{d}`\n"

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data=f"rout_srv_{server_id}"))
        
        try: bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        except: bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data == "rout_gold")
    def apply_gold_list(call):
        chat_id = call.message.chat.id
        server_id = user_states.get(chat_id, {}).get("server_id", 1)
        config = get_config_from_server(server_id)
        
        if not config:
            bot.answer_callback_query(call.id, "❌ فشل جلب الكونفك.")
            return

        # تحديث قواعد التوجيه
        routing = config.setdefault("routing", {"domainStrategy": "AsIs", "rules": []})
        rules = routing.setdefault("rules", [])
        
        # البحث عن قاعدة direct للمواقع وتحديثها
        found = False
        for rule in rules:
            if rule.get("outboundTag") == "direct" and "domain" in rule:
                rule["domain"] = DEFAULT_DIRECT_DOMAINS
                found = True
                break
        
        if not found:
            rules.insert(0, {
                "type": "field",
                "outboundTag": "direct",
                "domain": DEFAULT_DIRECT_DOMAINS
            })

        if save_config_to_server(server_id, config):
            bot.answer_callback_query(call.id, "✅ تم زرع القائمة الذهبية بنجاح! يرجى عمل ريستارت للسيرفر.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ فشل حفظ التعديلات في السيرفر.")
        
        show_routing_menu(call)

    @bot.callback_query_handler(func=lambda call: call.data == "rout_add")
    def ask_domain_add(call):
        chat_id = call.message.chat.id
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 إلغاء", callback_data=f"rout_srv_{user_states.get(chat_id, {}).get('server_id', 1)}"))
        
        text = "➕ **إضافة موقع جديد**\n\n"
        text += "اختر الصيغة المناسبة وأرسلها:\n"
        text += "1. موقع محدد: `domain:example.com`\n"
        text += "2. كلمة مفتاحية: `keyword:pubg`\n"
        text += "3. تصنيف شامل: `geosite:category-news`\n\n"
        text += "✍️ أرسل الموقع الآن:"
        
        msg = bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_domain, bot)

    def process_add_domain(message, bot):
        chat_id = message.chat.id
        domain_to_add = message.text.strip()
        server_id = user_states.get(chat_id, {}).get("server_id", 1)
        
        config = get_config_from_server(server_id)
        if config:
            rules = config.setdefault("routing", {}).setdefault("rules", [])
            found = False
            for rule in rules:
                if rule.get("outboundTag") == "direct" and "domain" in rule:
                    if domain_to_add not in rule["domain"]:
                        rule["domain"].append(domain_to_add)
                    found = True
                    break
            
            if not found:
                rules.insert(0, {
                    "type": "field",
                    "outboundTag": "direct",
                    "domain": [domain_to_add]
                })

            if save_config_to_server(server_id, config):
                bot.send_message(chat_id, f"✅ تم إضافة `{domain_to_add}` لسرعة 1000 ميكا بنجاح!\nلا تنسَ عمل ريستارت للسيرفر.", parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "❌ فشل الحفظ بالسيرفر.")
        
        # إعادة عرض القائمة
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data=f"rout_srv_{server_id}"))
        bot.send_message(chat_id, "اختر:", reply_markup=markup)
