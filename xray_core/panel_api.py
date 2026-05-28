import json
import os
import requests
import time
import subprocess
import socket
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
        self.api_key = os.getenv('AD_API_KEY')
        self.site_id = os.getenv('AD_SITE_ID')
        self.stats_available = False
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
    # 🔍 فحص إذا xray شغال (عبر بورت VLESS)
    # ----------------------------------------------------------------------
    def _is_xray_running(self):
        # طريقة 1: فحص البورت (timeout سريع)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(('127.0.0.1', FIXED_PORT))
            sock.close()
            if result == 0:
                return True
        except:
            pass
        # طريقة 2: فحص error.log — على Alwaysdata البوت ما يشوف عملية xray
        try:
            error_log = f"{HOME_DIR}/xray_core/error.log"
            if os.path.exists(error_log):
                mod_time = os.path.getmtime(error_log)
                if time.time() - mod_time < 300:
                    with open(error_log, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(0, os.SEEK_END)
                        size = f.tell()
                        f.seek(max(0, size - 2000))
                        tail = f.read()
                        for line in reversed(tail.splitlines()[-5:]):
                            if 'started' in line.lower():
                                return True
        except:
            pass
        return False

    # ----------------------------------------------------------------------
    # 🛠️ بناء كونفك VLESS فقط (بدون بورتات إضافية)
    # ----------------------------------------------------------------------
    def _build_clean_config(self, existing_clients, config):
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

        config['inbounds'] = [vless_inbound]

        # إزالة كل ما يتعلق بالإحصائيات (يحتاج بورت إضافي)
        config.pop('stats', None)
        config.pop('api', None)
        config.pop('policy', None)

        # إزالة قاعدة توجيه API
        routing = config.get('routing', {})
        rules = routing.get('rules', [])
        rules = [r for r in rules if r.get('outboundTag') != 'api']
        routing['rules'] = rules
        config['routing'] = routing

        if not config.get('outbounds'):
            config['outbounds'] = [{"protocol": "freedom", "tag": "freedom"}]

        return config

    # ----------------------------------------------------------------------
    # 🛠️ ضبط الكونفك — VLESS فقط على بورت 8100
    # ----------------------------------------------------------------------
    def ensure_base_config(self):
        try:
            config = self._load_config()
            if config is None:
                print(f"❌ ملف الكونفك غير موجود: {CONFIG_PATH}")
                return

            # نلتقط المشتركين الموجودين سلفاً
            existing_clients = []
            if isinstance(config.get('inbounds'), list):
                for inb in config['inbounds']:
                    if inb.get('protocol') in ('vless', 'vmess', 'trojan'):
                        settings = inb.get('settings') or {}
                        existing_clients = settings.get('clients') or []
                        break

            log_cfg = config.get('log') or {}
            log_cfg.setdefault('access', 'access.log')
            log_cfg.setdefault('error', 'error.log')
            log_cfg.setdefault('loglevel', 'warning')
            config['log'] = log_cfg

            # نتحقق إذا الكونفك سليم (VLESS فقط، بدون dokodemo-door)
            has_vless = False
            has_bad_inbound = False
            for inb in config.get('inbounds', []):
                if inb.get('protocol') in ('vless', 'vmess', 'trojan'):
                    has_vless = True
                    # نتحقق إن البورت والإعدادات صحيحة
                    if inb.get('port') != FIXED_PORT:
                        has_bad_inbound = True
                if inb.get('protocol') == 'dokodemo-door':
                    has_bad_inbound = True  # لازم نشيله — يمنع xray من التشغيل

            # نتحقق إذا فيه أقسام إحصائيات (لازم نشيلها)
            has_stats_sections = 'stats' in config or 'api' in config

            if has_vless and not has_bad_inbound and not has_stats_sections:
                # الكونفك سليم — ما نعدل شي
                print(f"✅ الكونفك سليم — VLESS على البورت {FIXED_PORT}")
                # نتحقق إذا Stats API شغال (لو المستخدم على VPS)
                self._check_stats()
                return

            # الكونفك يحتاج تنظيف
            print("🔧 جاري تنظيف الكونفك (إزالة بورتات إضافية)...")
            clean_config = self._build_clean_config(existing_clients, config)
            self._save_config(clean_config)
            self.restart_xray()
            self.stats_available = False
            print(f"✅ تم ضبط الكونفك — VLESS فقط على البورت {FIXED_PORT}")

            try:
                with open(f'{HOME_DIR}/active_port.txt', 'w') as f:
                    f.write(str(FIXED_PORT))
            except Exception:
                pass

        except Exception as e:
            print(f"Error ensuring base config: {e}")

    # ----------------------------------------------------------------------
    # 📊 فحص إذا Stats API متاح (للسيرفرات اللي تدعم بورت إضافي)
    # ----------------------------------------------------------------------
    _stats_checked = False

    def _check_stats(self):
        if PanelAPI._stats_checked:
            return
        PanelAPI._stats_checked = True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(('127.0.0.1', STATS_API_PORT))
            sock.close()
            if result == 0:
                self.stats_available = True
                print(f"📊 Stats API شغال على بورت {STATS_API_PORT}")
            else:
                self.stats_available = False
        except:
            self.stats_available = False

    # ----------------------------------------------------------------------
    # 👤 إضافة مشترك (الزراعة)
    # ----------------------------------------------------------------------
    def create_client(self, email, uuid, protocol="vless"):
        try:
            config = self._load_config()
            if config is None:
                print(f"❌ ملف الكونفك غير موجود: {CONFIG_PATH}")
                return False
            if not config.get('inbounds'):
                print("❌ لا يوجد inbounds في ملف الكونفك")
                return False

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
        return self._remove_client(lambda c: c.get('email') != email)

    def remove_client(self, uuid):
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
        return True

    # ----------------------------------------------------------------------
    # 📊 إحصائيات الترافيك لكل مشترك
    # ----------------------------------------------------------------------
    def get_client_traffic(self, email):
        traffic = self.get_all_clients_traffic(reset=False)
        return traffic.get(email, 0)

    def get_all_clients_traffic(self, reset=True):
        if not self.stats_available:
            return {}
        try:
            reset_flag = "-reset=true" if reset else ""
            cmd = f"{XRAY_BIN} api statsquery -server=127.0.0.1:{STATS_API_PORT} {reset_flag}"
            result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=5).decode('utf-8').strip()
            if not result:
                return {}
            stats = json.loads(result)
            traffic = {}
            for stat in stats.get('stat', []):
                name = stat.get('name', '')
                value = int(stat.get('value', 0))
                if name.startswith('user>>>'):
                    parts = name.split('>>>')
                    if len(parts) >= 4:
                        email = parts[1]
                        traffic[email] = traffic.get(email, 0) + value
            return traffic
        except subprocess.CalledProcessError as e:
            err = e.output.decode('utf-8', errors='ignore') if e.output else str(e)
            print(f"⚠️ xray Stats API خطأ: {err}")
            self.stats_available = False
            return {}
        except Exception as e:
            print(f"⚠️ خطأ في جلب الترافيك: {e}")
            return {}

    # ----------------------------------------------------------------------
    # 🔍 تشخيص تفصيلي
    # ----------------------------------------------------------------------
    def run_stats_diagnostic(self):
        report = ""

        # 1. ملف xray
        report += "**1️⃣ ملف xray:**\n"
        if os.path.exists(XRAY_BIN):
            is_exec = os.access(XRAY_BIN, os.X_OK)
            report += f"  📄 المسار: `{XRAY_BIN}`\n"
            report += f"  {'✅' if is_exec else '❌'} قابل للتنفيذ: {'نعم' if is_exec else 'لا'}\n"
            try:
                ver = subprocess.getoutput(f"{XRAY_BIN} version 2>&1")
                first_line = ver.strip().split('\n')[0] if ver.strip() else '?'
                report += f"  📋 النسخة: `{first_line}`\n"
            except:
                pass
        else:
            report += f"  ❌ غير موجود: `{XRAY_BIN}`\n"
        report += "\n"

        # 2. ملف الكونفك
        report += "**2️⃣ ملف كونفك xray:**\n"
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    cfg = json.load(f)

                has_stats = 'stats' in cfg
                has_api = 'api' in cfg

                vless_inbound = False
                vless_port = None
                dokodemo = False
                clients_count = 0
                for inb in cfg.get('inbounds', []):
                    if inb.get('protocol') == 'dokodemo-door':
                        dokodemo = True
                    if inb.get('protocol') in ('vless', 'vmess', 'trojan'):
                        vless_inbound = True
                        vless_port = inb.get('port')
                        clients_count = len(inb.get('settings', {}).get('clients', []))

                report += f"  📄 المسار: `{CONFIG_PATH}`\n"
                report += f"  📡 بوابة VLESS: {'✅ بورت ' + str(vless_port) if vless_inbound else '❌ غير موجودة!'}\n"
                report += f"  👥 المشتركين: {clients_count}\n"
                if dokodemo:
                    report += f"  ⚠️ بوابة dokodemo-door موجودة — تمنع xray من التشغيل!\n"
                if has_stats or has_api:
                    report += f"  ⚠️ أقسام stats/api موجودة — تحتاج بورت إضافي!\n"
                if not dokodemo and not has_stats and not has_api:
                    report += f"  ✅ الكونفك نظيف (بدون بورتات إضافية)\n"
            else:
                report += f"  ❌ غير موجود: `{CONFIG_PATH}`\n"
        except Exception as e:
            report += f"  ❌ خطأ: `{e}`\n"
        report += "\n"

        # 3. عملية xray
        report += "**3️⃣ عملية xray:**\n"
        xray_running = self._is_xray_running()
        if xray_running:
            report += f"  ✅ شغال (error.log يؤكد التشغيل)\n"
            report += f"  ℹ️ البوت ما يقدر يشوف العملية مباشرة (user programs منفصلين)\n"
        else:
            report += f"  🔴 غير شغال\n"

        vless_open = False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            vless_open = sock.connect_ex(('127.0.0.1', FIXED_PORT)) == 0
            sock.close()
        except:
            pass
        if vless_open:
            report += f"  🚪 بورت {FIXED_PORT} (VLESS): ✅ مفتوح\n"
        elif xray_running:
            report += f"  🚪 بورت {FIXED_PORT}: ℹ️ لا يمكن الفحص من البوت (عمليات منفصلة)\n"
        else:
            report += f"  🚪 بورت {FIXED_PORT} (VLESS): ❌ مغلق\n"
        report += "\n"

        # 4. نظام الإحصائيات
        report += "**4️⃣ نظام قياس الاستهلاك (KB/MB):**\n"
        report += f"  📊 الحالة: {'✅ مفعل' if self.stats_available else '❌ غير متاح'}\n"
        if not self.stats_available:
            report += "  💡 السبب: السيرفر يدعم بورت واحد فقط (8100)\n"
            report += "  💡 قياس KB/MB يحتاج بورت إضافي (10085) للـ Stats API\n"
            report += "  💡 الحل: استخدم VPS (DigitalOcean/Hetzner) يدعم بورتات متعددة\n"
        else:
            try:
                cmd = f"{XRAY_BIN} api statsquery -server=127.0.0.1:{STATS_API_PORT}"
                result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=5).decode('utf-8').strip()
                if result:
                    stats = json.loads(result)
                    stat_list = stats.get('stat', [])
                    user_stats = [s for s in stat_list if s.get('name', '').startswith('user>>>')]
                    report += f"  ✅ Stats API شغال!\n"
                    report += f"  📊 إحصائيات: {len(stat_list)} | مشتركين: {len(user_stats)}\n"
                    for s in user_stats[:4]:
                        name = s.get('name', '')
                        val = int(s.get('value', 0))
                        parts = name.split('>>>')
                        email = parts[1] if len(parts) > 1 else '?'
                        direction = parts[3] if len(parts) > 3 else '?'
                        report += f"  └ `{email}` ({direction}): {val/1024:.1f} KB\n"
            except Exception as e:
                report += f"  ⚠️ خطأ: `{str(e)[:150]}`\n"
        report += "\n"

        # 5. سجل xray
        report += "**5️⃣ سجل xray (آخر 3 أسطر):**\n"
        xray_log = f"{HOME_DIR}/xray_core/xray.log"
        xray_err = f"{HOME_DIR}/xray_core/error.log"
        found_log = False
        for log_path in [xray_log, xray_err]:
            try:
                if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
                    found_log = True
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(0, os.SEEK_END)
                        size = f.tell()
                        f.seek(max(0, size - 2000))
                        tail = f.read()
                        last_lines = tail.splitlines()[-3:]
                        report += f"  📄 `{os.path.basename(log_path)}`:\n"
                        for line in last_lines:
                            report += f"  `{line.strip()[:100]}`\n"
            except:
                pass
        if not found_log:
            report += "  (فارغ أو غير موجود)\n"
        report += "\n"

        return report

    # ----------------------------------------------------------------------
    # 🔄 إعادة تشغيل xray (Alwaysdata API أولاً، ثم pkill/nohup كاحتياطي)
    # ----------------------------------------------------------------------
    def restart_xray(self):
        if self.api_key and self.site_id:
            try:
                url = f"https://api.alwaysdata.com/v1/site/{self.site_id}/restart/"
                r = requests.post(url, auth=(self.api_key, ''), timeout=15)
                if r.status_code in (200, 201, 202, 204):
                    return True
                print(f"⚠️ Alwaysdata restart failed: {r.status_code} {r.text}")
            except Exception as e:
                print(f"⚠️ Alwaysdata restart error: {e}")

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
