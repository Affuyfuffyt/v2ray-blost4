import json
import os
import requests
import time
import subprocess
from dotenv import load_dotenv

# 🔥 مسارات ديناميكية ذكية
HOME_DIR = os.path.expanduser("~")
CONFIG_PATH = f'{HOME_DIR}/xray_core/config.json'
XRAY_BIN = f'{HOME_DIR}/xray_core/xray'

# ⚙️ الإعدادات الثابتة التي يجب أن تطابق ما يرسله تطبيق DarkTunnel
FIXED_PORT     = 8100
FIXED_PROTOCOL = "vless"
FIXED_NETWORK  = "ws"
FIXED_PATH     = "/xray"
FIXED_LISTEN   = "0.0.0.0"
STATS_API_PORT = 10085


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
            if isinstance(config.get('inbounds'), list):
                for inb in config['inbounds']:
                    if inb.get('protocol') in ('vless', 'vmess', 'trojan'):
                        settings = inb.get('settings') or {}
                        existing_clients = settings.get('clients') or []
                        break

            # نعيد بناء البوابة (VLESS + WS + Path /xray) + بوابة API للإحصائيات
            vless_inbound = {
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
                },
                "tag": "vless-in"
            }

            api_inbound = {
                "listen": "127.0.0.1",
                "port": STATS_API_PORT,
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"},
                "tag": "api"
            }

            config['inbounds'] = [api_inbound, vless_inbound]

            # تفعيل نظام الإحصائيات لكل مشترك
            config['stats'] = {}
            config['api'] = {
                "tag": "api",
                "services": ["StatsService"]
            }
            config['policy'] = {
                "levels": {
                    "0": {
                        "statsUserUplink": True,
                        "statsUserDownlink": True
                    }
                },
                "system": {
                    "statsInboundUplink": True,
                    "statsInboundDownlink": True
                }
            }

            # نتأكد من وجود outbound افتراضي
            if not config.get('outbounds'):
                config['outbounds'] = [{"protocol": "freedom", "tag": "freedom"}]

            # إضافة قاعدة توجيه API (لازم تكون أول قاعدة)
            routing = config.get('routing', {})
            rules = routing.get('rules', [])
            api_rule = {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
            has_api_rule = any(r.get('outboundTag') == 'api' for r in rules)
            if not has_api_rule:
                rules.insert(0, api_rule)
            routing['rules'] = rules
            config['routing'] = routing

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
        """يضيف مشترك جديد إلى بوابة VLESS ثم يعيد تشغيل xray."""
        try:
            config = self._load_config()
            if config is None:
                print(f"❌ ملف الكونفك غير موجود: {CONFIG_PATH}")
                return False
            if not config.get('inbounds'):
                print("❌ لا يوجد inbounds في ملف الكونفك")
                return False

            # نبحث عن بوابة VLESS (مو بوابة API)
            inbound = None
            for inb in config['inbounds']:
                if inb.get('protocol') in ('vless', 'vmess', 'trojan'):
                    inbound = inb
                    break
            if inbound is None:
                print("❌ لا توجد بوابة VLESS في الكونفك")
                return False
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
    # 📊 إحصائيات الترافيك لكل مشترك
    # ----------------------------------------------------------------------
    def get_client_traffic(self, email):
        """يرجع إجمالي الترافيك (uplink + downlink) لمشترك معين بالبايت."""
        try:
            cmd = f"{XRAY_BIN} api statsquery --server=127.0.0.1:{STATS_API_PORT} -pattern 'user>>>{email}>>>'"
            result = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=3).decode('utf-8').strip()
            if not result:
                return 0
            stats = json.loads(result)
            total = 0
            for stat in stats.get('stat', []):
                total += int(stat.get('value', 0))
            return total
        except Exception:
            return 0

    def get_all_clients_traffic(self, reset=True):
        """يرجع قاموس بالترافيك لكل المشتركين. مع reset=True يصفر العدادات بعد القراءة."""
        try:
            reset_flag = "-reset" if reset else ""
            cmd = f"{XRAY_BIN} api statsquery --server=127.0.0.1:{STATS_API_PORT} -pattern 'user>>>' {reset_flag}"
            result = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=3).decode('utf-8').strip()
            if not result:
                return {}
            stats = json.loads(result)
            traffic = {}
            for stat in stats.get('stat', []):
                name = stat.get('name', '')
                value = int(stat.get('value', 0))
                parts = name.split('>>>')
                if len(parts) >= 4 and parts[0] == 'user':
                    email = parts[1]
                    traffic[email] = traffic.get(email, 0) + value
            return traffic
        except Exception:
            return {}

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
