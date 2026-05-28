import json
import os
import requests
import time
from dotenv import load_dotenv

# 🔥 مسارات ديناميكية ذكية
HOME_DIR = os.path.expanduser("~")
CONFIG_PATH = f'{HOME_DIR}/xray_core/config.json'

# ⚙️ الإعدادات الثابتة التي يجب أن تطابق ما يرسله تطبيق DarkTunnel
FIXED_PORT     = 8100
FIXED_PROTOCOL = "vless"
FIXED_NETWORK  = "ws"
FIXED_PATH     = "/xray"
FIXED_LISTEN   = "0.0.0.0"


class PanelAPI:
    def __init__(self):
        load_dotenv()
        # مفاتيح Alwaysdata API (لإعادة تشغيل الموقع بعد التعديل)
        self.api_key = os.getenv('AD_API_KEY')
        self.site_id = os.getenv('AD_SITE_ID')
        # نضمن أن ملف الكونفك بالشكل الصحيح فور تشغيل البوت — بدون مسح المشتركين
        self.ensure_base_config()

    # ----------------------------------------------------------------------
    # 📂 قراءة وحفظ ملف الكونفك
    # ----------------------------------------------------------------------
    def _load_config(self):
        if not os.path.exists(CONFIG_PATH):
            return None
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_config(self, config):
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    # ----------------------------------------------------------------------
    # 🛠️ ضبط الكونفك الأساسي بدون المساس بالمشتركين الموجودين
    # ----------------------------------------------------------------------
    def ensure_base_config(self):
        """يضمن وجود بوابة VLESS واحدة بإعدادات صحيحة،
        مع الحفاظ على قائمة المشتركين (clients) كما هي."""
        try:
            config = self._load_config()
            if config is None:
                print(f"❌ ملف الكونفك غير موجود: {CONFIG_PATH}")
                return

            # نلتقط المشتركين الموجودين سلفاً كي لا نفقدهم عند إعادة الضبط
            existing_clients = []
            if isinstance(config.get('inbounds'), list) and config['inbounds']:
                settings = config['inbounds'][0].get('settings') or {}
                existing_clients = settings.get('clients') or []

            # نعيد بناء البوابة الواحدة بشكل نظيف (VLESS + WS + Path /xray)
            config['inbounds'] = [{
                "port": FIXED_PORT,
                "listen": FIXED_LISTEN,
                "protocol": FIXED_PROTOCOL,
                "settings": {
                    "clients": existing_clients,
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": FIXED_NETWORK,
                    "wsSettings": {
                        "path": FIXED_PATH
                    }
                }
            }]

            # نتأكد من وجود outbound افتراضي
            if not config.get('outbounds'):
                config['outbounds'] = [{"protocol": "freedom", "tag": "freedom"}]

            # نتأكد من إعدادات اللوك (نحافظ على القيم الحالية إن وُجدت)
            log_cfg = config.get('log') or {}
            log_cfg.setdefault('access', 'access.log')
            log_cfg.setdefault('error', 'error.log')
            log_cfg.setdefault('loglevel', 'warning')
            config['log'] = log_cfg

            self._save_config(config)

            # نسجل البورت النشط بملف نصي للمراقبة
            try:
                with open(f'{HOME_DIR}/active_port.txt', 'w') as f:
                    f.write(str(FIXED_PORT))
            except Exception:
                pass

            print(f"✅ تم ضبط ملف الكونفك بنجاح — VLESS فقط على البورت {FIXED_PORT}")
            self.restart_xray()
        except Exception as e:
            print(f"Error ensuring base config: {e}")

    # ----------------------------------------------------------------------
    # 👤 إضافة مشترك (الزراعة)
    # ----------------------------------------------------------------------
    def create_client(self, email, uuid, protocol="vless"):
        """يضيف مشترك جديد إلى البوابة الأولى ثم يعيد تشغيل xray."""
        try:
            config = self._load_config()
            if config is None:
                print(f"❌ ملف الكونفك غير موجود: {CONFIG_PATH}")
                return False
            if not config.get('inbounds'):
                print("❌ لا يوجد inbounds في ملف الكونفك")
                return False

            # نتأكد من أن settings و clients موجودين (setdefault على dict جذري)
            inbound  = config['inbounds'][0]
            settings = inbound.setdefault('settings', {})
            clients  = settings.setdefault('clients', [])

            already_exists = any(
                c.get('email') == email or c.get('id') == uuid
                for c in clients
            )
            if not already_exists:
                clients.append({"id": uuid, "email": email, "level": 0})
                self._save_config(config)
                print(f"✅ تمت زراعة المشترك: {email}")
            else:
                print(f"ℹ️ المشترك {email} موجود سلفاً — تم تخطي الإضافة")

            return self.restart_xray()
        except Exception as e:
            print(f"Error creating client locally: {e}")
            return False

    # ----------------------------------------------------------------------
    # 🗑️ حذف مشترك (بالاسم أو بالـ UUID)
    # ----------------------------------------------------------------------
    def delete_client(self, email):
        """يحذف مشترك بناءً على الـ email."""
        return self._remove_client(lambda c: c.get('email') != email)

    def remove_client(self, uuid):
        """يحذف مشترك بناءً على الـ UUID."""
        return self._remove_client(lambda c: c.get('id') != uuid)

    def _remove_client(self, filter_fn):
        try:
            config = self._load_config()
            if config is None or not config.get('inbounds'):
                return False

            changed = False
            for inbound in config.get('inbounds', []):
                settings = inbound.get('settings') or {}
                clients  = settings.get('clients') or []
                new_clients = [c for c in clients if filter_fn(c)]
                if len(new_clients) != len(clients):
                    settings['clients'] = new_clients
                    inbound['settings'] = settings
                    changed = True

            if changed:
                self._save_config(config)
                return self.restart_xray()
            return True
        except Exception as e:
            print(f"Error removing client: {e}")
            return False

    # ----------------------------------------------------------------------
    # 🔄 تغيير حالة مشترك (التعطيل = حذف)
    # ----------------------------------------------------------------------
    def change_client_status(self, email, inbound_id=None, uuid=None, enable=True):
        if not enable:
            return self.delete_client(email)
        # التفعيل يتم عبر create_client من create_flow.py
        return True

    # ----------------------------------------------------------------------
    # 📊 إحصائيات الترافيك (غير مدعومة في وضع xray-core المحلي)
    # ----------------------------------------------------------------------
    def get_client_traffic(self, email):
        return 0

    # ----------------------------------------------------------------------
    # 🔄 إعادة تشغيل xray (Alwaysdata API أولاً، ثم pkill/nohup كاحتياطي)
    # ----------------------------------------------------------------------
    def restart_xray(self):
        # 1) إذا توفرت مفاتيح Alwaysdata نستخدم الـ API الرسمي
        if self.api_key and self.site_id:
            try:
                url = f"https://api.alwaysdata.com/v1/site/{self.site_id}/restart/"
                r = requests.post(url, auth=(self.api_key, ''), timeout=15)
                if r.status_code in (200, 201, 202, 204):
                    return True
                print(f"⚠️ Alwaysdata restart failed: {r.status_code} {r.text}")
            except Exception as e:
                print(f"⚠️ Alwaysdata restart error: {e}")

        # 2) الـ fallback: تشغيل xray مباشرة (مفيد على VPS عادي)
        try:
            os.system(
                f"pkill -9 xray 2>/dev/null ; "
                f"nohup {HOME_DIR}/xray_core/xray run -c {CONFIG_PATH} "
                f"> {HOME_DIR}/xray_core/xray.log 2>&1 &"
            )
            time.sleep(0.5)
            return True
        except Exception as e:
            print(f"Restart fallback error: {e}")
            return False
