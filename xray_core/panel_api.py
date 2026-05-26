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
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', FIXED_PORT))
            sock.close()
            if result == 0:
                return True
        except:
            pass
        try:
            result = subprocess.getoutput("ps aux 2>/dev/null | grep '[x]ray'")
            if result.strip():
                return True
        except:
            pass
        return False

    # ----------------------------------------------------------------------
    # 🔍 فحص إذا Stats API شغال (عبر بورت 10085)
    # ----------------------------------------------------------------------
    def _is_stats_port_open(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', STATS_API_PORT))
            sock.close()
            return result == 0
        except:
            return False

    # ----------------------------------------------------------------------
    # 🛠️ بناء كونفك VLESS مع نظام الإحصائيات (دائماً)
    # ----------------------------------------------------------------------
    def _build_full_config(self, existing_clients, config):
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

        if not config.get('outbounds'):
            config['outbounds'] = [{"protocol": "freedom", "tag": "freedom"}]

        routing = config.get('routing', {})
        rules = routing.get('rules', [])
        api_rule = {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
        has_api_rule = any(r.get('outboundTag') == 'api' for r in rules)
        if not has_api_rule:
            rules.insert(0, api_rule)
        routing['rules'] = rules
        config['routing'] = routing

        return config

    # ----------------------------------------------------------------------
    # 🛠️ ضبط الكونفك — دائماً مع نظام الإحصائيات
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

            # نتحقق إذا الكونفك الحالي سليم (فيه stats + VLESS)
            has_stats = 'stats' in config
            has_api = 'api' in config
            has_vless = any(
                inb.get('protocol') in ('vless', 'vmess', 'trojan')
                for inb in config.get('inbounds', [])
            )
            has_api_inbound = any(
                inb.get('protocol') == 'dokodemo-door'
                for inb in config.get('inbounds', [])
            )

            if has_stats and has_api and has_vless and has_api_inbound:
                # الكونفك سليم — ما نحتاج نعدل ولا نعيد تشغيل
                print(f"✅ الكونفك سليم — VLESS + إحصائيات على البورت {FIXED_PORT}")
                # نتحقق بس إذا Stats API شغال
                if self._is_stats_port_open():
                    self.stats_available = True
                    print(f"📊 Stats API شغال على بورت {STATS_API_PORT}")
                else:
                    self.stats_available = False
                    print(f"⚠️ Stats API مو شغال على بورت {STATS_API_PORT} — يحتاج ريستارت xray")
                return

            # الكونفك يحتاج تعديل — نضيف نظام الإحصائيات
            print("🔧 جاري تحديث الكونفك مع نظام الإحصائيات...")
            full_config = self._build_full_config(existing_clients, config)
            self._save_config(full_config)
            self.restart_xray()

            # ننتظر حتى xray يبدأ
            time.sleep(3)
            if self._is_stats_port_open():
                self.stats_available = True
                print(f"✅ تم ضبط الكونفك بنجاح — VLESS + إحصائيات على البورت {FIXED_PORT}")
            else:
                self.stats_available = False
                print(f"⚠️ تم حفظ الكونفك مع الإحصائيات — بورت {STATS_API_PORT} يحتاج وقت أكثر أو ريستارت يدوي")

            try:
                with open(f'{HOME_DIR}/active_port.txt', 'w') as f:
                    f.write(str(FIXED_PORT))
            except Exception:
                pass

        except Exception as e:
            print(f"Error ensuring base config: {e}")

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
            # نحاول نتحقق مرة ثانية — ممكن صار شغال بعد ريستارت
            if self._is_stats_port_open():
                self.stats_available = True
                print("📊 Stats API رجع شغال!")
            else:
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
    # 🔍 تشخيص تفصيلي لنظام الإحصائيات
    # ----------------------------------------------------------------------
    def run_stats_diagnostic(self):
        """يرجع تقرير تفصيلي عن سبب عدم عمل نظام الإحصائيات"""
        report = ""

        # 1. فحص ملف xray
        report += "**1️⃣ ملف xray:**\n"
        if os.path.exists(XRAY_BIN):
            is_exec = os.access(XRAY_BIN, os.X_OK)
            report += f"  📄 المسار: `{XRAY_BIN}`\n"
            report += f"  ✅ موجود\n"
            report += f"  {'✅' if is_exec else '❌'} قابل للتنفيذ: {'نعم' if is_exec else 'لا'}\n"
            try:
                ver = subprocess.getoutput(f"{XRAY_BIN} version 2>&1")
                first_line = ver.strip().split('\n')[0] if ver.strip() else '?'
                report += f"  📋 النسخة: `{first_line}`\n"
            except:
                report += "  ⚠️ تعذر قراءة النسخة\n"
        else:
            report += f"  ❌ غير موجود: `{XRAY_BIN}`\n"

        report += "\n"

        # 2. فحص ملف الكونفك بالتفصيل
        report += "**2️⃣ ملف كونفك xray:**\n"
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    cfg = json.load(f)

                has_stats = 'stats' in cfg
                has_api = 'api' in cfg
                has_policy = 'policy' in cfg

                api_inbound = False
                api_port = None
                vless_inbound = False
                vless_port = None
                clients_count = 0
                for inb in cfg.get('inbounds', []):
                    if inb.get('protocol') == 'dokodemo-door':
                        api_inbound = True
                        api_port = inb.get('port')
                    if inb.get('protocol') in ('vless', 'vmess', 'trojan'):
                        vless_inbound = True
                        vless_port = inb.get('port')
                        clients_count = len(inb.get('settings', {}).get('clients', []))

                report += f"  📄 المسار: `{CONFIG_PATH}`\n"
                report += f"  📊 stats: {'✅ مفعل' if has_stats else '❌ غير مفعل ← السبب الرئيسي!'}\n"
                report += f"  🔌 api: {'✅ مفعلة' if has_api else '❌ غير موجودة ← السبب الرئيسي!'}\n"
                report += f"  📋 policy: {'✅ مفعل' if has_policy else '❌ غير مفعل ← السبب الرئيسي!'}\n"
                report += f"  🚪 بوابة API (dokodemo): {'✅ بورت ' + str(api_port) if api_inbound else '❌ غير موجودة!'}\n"
                report += f"  📡 بوابة VLESS: {'✅ بورت ' + str(vless_port) if vless_inbound else '❌ غير موجودة!'}\n"
                report += f"  👥 المشتركين بالكونفك: {clients_count}\n"

                # فحص routing
                routing = cfg.get('routing', {})
                rules = routing.get('rules', [])
                has_api_rule = any(r.get('outboundTag') == 'api' for r in rules)
                report += f"  🔀 قاعدة routing API: {'✅ موجودة' if has_api_rule else '❌ غير موجودة!'}\n"

                if not (has_stats and has_api and has_policy and api_inbound):
                    report += "\n  💡 **الحل:** الكونفك ناقص أقسام الإحصائيات.\n"
                    report += "  اضغط 'إصلاح الإحصائيات' بالأسفل.\n"
            else:
                report += f"  ❌ غير موجود: `{CONFIG_PATH}`\n"
        except Exception as e:
            report += f"  ❌ خطأ بقراءة الكونفك: `{e}`\n"

        report += "\n"

        # 3. فحص عملية xray
        report += "**3️⃣ عملية xray:**\n"
        try:
            ps = subprocess.getoutput("ps aux 2>/dev/null | grep '[x]ray'")
            if ps.strip():
                report += f"  ✅ شغال\n"
                for line in ps.strip().split('\n')[:2]:
                    parts = line.split()
                    if len(parts) > 10:
                        report += f"  └ PID: {parts[1]} | CPU: {parts[2]}% | MEM: {parts[3]}%\n"
            else:
                report += "  🔴 غير شغال (ps aux)\n"
        except:
            report += "  ⚠️ تعذر فحص العمليات\n"

        # فحص البورتات
        vless_open = self._is_xray_running()
        stats_open = self._is_stats_port_open()
        report += f"  🚪 بورت {FIXED_PORT} (VLESS): {'✅ مفتوح' if vless_open else '❌ مغلق'}\n"
        report += f"  🚪 بورت {STATS_API_PORT} (Stats): {'✅ مفتوح' if stats_open else '❌ مغلق'}\n"

        if vless_open and not stats_open:
            report += "  💡 xray شغال بس بدون نظام إحصائيات — الكونفك يحتاج تحديث\n"

        report += "\n"

        # 4. فحص Stats API مباشرة
        report += "**4️⃣ فحص Stats API:**\n"
        report += f"  📊 stats\\_available: `{self.stats_available}`\n"
        try:
            cmd = f"{XRAY_BIN} api statsquery -server=127.0.0.1:{STATS_API_PORT}"
            result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=5).decode('utf-8').strip()
            if result:
                stats = json.loads(result)
                stat_list = stats.get('stat', [])
                user_stats = [s for s in stat_list if s.get('name', '').startswith('user>>>')]
                report += f"  ✅ الاتصال ناجح!\n"
                report += f"  📊 إجمالي الإحصائيات: {len(stat_list)}\n"
                report += f"  👤 إحصائيات مشتركين: {len(user_stats)}\n"
                for s in user_stats[:4]:
                    name = s.get('name', '')
                    val = int(s.get('value', 0))
                    parts = name.split('>>>')
                    email = parts[1] if len(parts) > 1 else '?'
                    direction = parts[3] if len(parts) > 3 else '?'
                    report += f"  └ `{email}` ({direction}): {val/1024:.1f} KB\n"
            else:
                report += "  ⚠️ اتصال ناجح لكن لا توجد بيانات\n"
        except subprocess.CalledProcessError as e:
            err = e.output.decode('utf-8', errors='ignore') if e.output else str(e)
            report += f"  ❌ فشل:\n  `{err[:300]}`\n"
        except Exception as e:
            report += f"  ❌ خطأ: `{str(e)[:200]}`\n"

        report += "\n"

        # 5. سجل xray
        report += "**5️⃣ سجل xray (آخر 5 أسطر):**\n"
        xray_log = f"{HOME_DIR}/xray_core/xray.log"
        try:
            if os.path.exists(xray_log) and os.path.getsize(xray_log) > 0:
                with open(xray_log, 'r') as f:
                    lines = f.readlines()
                    for line in lines[-5:]:
                        report += f"  `{line.strip()[:100]}`\n"
            else:
                report += "  (فارغ أو غير موجود)\n"
        except:
            report += "  ⚠️ تعذرت القراءة\n"

        return report

    # ----------------------------------------------------------------------
    # 🔧 إصلاح الإحصائيات يدوياً
    # ----------------------------------------------------------------------
    def fix_stats_config(self):
        """يحدّث الكونفك لإضافة نظام الإحصائيات ويعيد تشغيل xray"""
        try:
            config = self._load_config()
            if config is None:
                return False, "ملف الكونفك غير موجود"

            existing_clients = []
            if isinstance(config.get('inbounds'), list):
                for inb in config['inbounds']:
                    if inb.get('protocol') in ('vless', 'vmess', 'trojan'):
                        settings = inb.get('settings') or {}
                        existing_clients = settings.get('clients') or []
                        break

            full_config = self._build_full_config(existing_clients, config)
            self._save_config(full_config)
            self.restart_xray()

            time.sleep(5)
            if self._is_stats_port_open():
                self.stats_available = True
                return True, "تم تفعيل نظام الإحصائيات بنجاح!"
            elif self._is_xray_running():
                self.stats_available = False
                return True, "xray شغال لكن بورت Stats لسه ما فتح — جرب ريستارت من لوحة التحكم"
            else:
                self.stats_available = False
                return False, "xray ما اشتغل — ممكن البورت 10085 مو مدعوم. جرب ريستارت xray من لوحة التحكم"
        except Exception as e:
            return False, f"خطأ: {e}"

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
