import json
import os
import sqlite3
import datetime
import time

# 🔥 الحل الجذري: تحديد مسار المجلد الحالي تلقائياً بدلاً من كتابة اسمه يدوياً 🔥
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_DB_PATH = os.path.join(BASE_DIR, 'users_db.json')
SQLITE_DB_PATH = os.path.join(BASE_DIR, 'bot_data.db')

# ==========================================
# 1️⃣ قسم قاعدة بيانات JSON (لضمان عمل أزرار البوت القديمة)
# ==========================================
def load_db():
    if not os.path.exists(JSON_DB_PATH):
        return {}
    try:
        with open(JSON_DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def update_db(data):
    with open(JSON_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def save_user(email, uuid, limit_bytes, expiry_time):
    data = load_db()
    data[email] = {
        'uuid': uuid, 
        'limit_bytes': limit_bytes, 
        'used_bytes': 0, 
        'expiry_time': expiry_time, 
        'is_active': True
    }
    update_db(data)

def renew_user(email, extra_bytes, new_expiry):
    data = load_db()
    if email in data:
        data[email]['limit_bytes'] = extra_bytes
        data[email]['expiry_time'] = new_expiry
        data[email]['is_active'] = True
        data[email]['used_bytes'] = 0 
        update_db(data)
        return True
    return False

# 🔥 الدالة السحرية لتمديد وقت اللوحة (مكافأة الدعوات) 🔥
def extend_json_expiry(email, extra_seconds):
    data = load_db()
    if email in data:
        current_expiry = data[email].get('expiry_time', time.time())
        data[email]['expiry_time'] = current_expiry + extra_seconds
        data[email]['is_active'] = True
        update_db(data)
        return True
    return False


# ==========================================
# 2️⃣ قسم قاعدة بيانات SQLite (لعمل المراقب الذكي والـ Radar وخدمة العملاء)
# ==========================================
def init_sqlite_db():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (email TEXT PRIMARY KEY, uuid TEXT, port INTEGER, quota_bytes REAL, expiry_date TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_usage
                 (email TEXT, date TEXT, total_used REAL)''')
    
    try: c.execute("ALTER TABLE users ADD COLUMN last_seen TEXT")
    except: pass 
    try: c.execute("ALTER TABLE users ADD COLUMN total_connection_seconds REAL DEFAULT 0")
    except: pass 
    try: c.execute("ALTER TABLE users ADD COLUMN ref_code TEXT")
    except: pass

    # جدول أرشيف الاتصال اليومي
    c.execute('''CREATE TABLE IF NOT EXISTS daily_connection
                 (email TEXT, date TEXT, connection_seconds REAL, PRIMARY KEY (email, date))''')

    # جدول المكافآت المعلقة
    c.execute('''CREATE TABLE IF NOT EXISTS pending_rewards
                 (referrer_email TEXT, invited_email TEXT, reward_seconds REAL, chat_id TEXT)''')

    # جدول خدمة العملاء (ربط حسابات المشتركين بتليجرام)
    c.execute('''CREATE TABLE IF NOT EXISTS user_subscriptions
                 (chat_id TEXT, email TEXT, PRIMARY KEY (chat_id, email))''')

    conn.commit()
    conn.close()

def add_user(email, uuid, port, quota_bytes, expiry_date):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email=?", (email,))
    if c.fetchone():
        c.execute("UPDATE users SET uuid=?, port=?, quota_bytes=?, expiry_date=?, status='active' WHERE email=?",
                  (uuid, port, quota_bytes, str(expiry_date), email))
    else:
        c.execute("INSERT INTO users (email, uuid, port, quota_bytes, expiry_date, status, last_seen, total_connection_seconds, ref_code) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, NULL)", 
                  (email, uuid, port, quota_bytes, str(expiry_date), 'active'))
    conn.commit()
    conn.close()

def get_active_users():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, uuid, expiry_date FROM users WHERE status='active'")
    users = c.fetchall()
    conn.close()
    return users

def set_user_expired(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET status='expired' WHERE email=?", (email,))
    conn.commit()
    conn.close()

# ==========================================
# 👥 دوال تطبيق خدمة العملاء (ربط الحسابات) 👥
# ==========================================
def link_user_subscription(chat_id, email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email=?", (email,))
    if c.fetchone():
        try:
            c.execute("INSERT INTO user_subscriptions (chat_id, email) VALUES (?, ?)", (str(chat_id), email))
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False # مربوط مسبقاً
    else:
        success = False # غير موجود
    conn.close()
    return success

def get_user_subscriptions(chat_id):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM user_subscriptions WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_subscription_details(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT expiry_date, quota_bytes, status, last_seen, total_connection_seconds FROM users WHERE email=?", (email,))
    data = c.fetchone()
    conn.close()
    return data

# ==========================================
# 🎁 دوال المكافآت والدعوات 🎁
# ==========================================
def assign_ref_code(email, ref_code):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET ref_code=? WHERE email=?", (ref_code, email))
    conn.commit()
    conn.close()

def get_user_by_ref_code(ref_code):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, expiry_date FROM users WHERE ref_code=?", (ref_code,))
    data = c.fetchone()
    conn.close()
    return data

def extend_user_expiry(email, extra_seconds):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM users WHERE email=?", (email,))
    data = c.fetchone()
    if data and data[0]:
        current_expiry = float(data[0])
        new_expiry = current_expiry + extra_seconds
        c.execute("UPDATE users SET expiry_date=?, status='active' WHERE email=?", (str(new_expiry), email))
        conn.commit()
        conn.close()
        return new_expiry
    return None

def add_pending_reward(referrer, invited, seconds, chat_id):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO pending_rewards VALUES (?, ?, ?, ?)", (referrer, invited, seconds, str(chat_id)))
    conn.commit()
    conn.close()

def get_all_pending_rewards():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT referrer_email, invited_email, reward_seconds, chat_id FROM pending_rewards")
    rows = c.fetchall()
    conn.close()
    return rows

def remove_pending_reward(invited_email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM pending_rewards WHERE invited_email=?", (invited_email,))
    conn.commit()
    conn.close()

def get_user_connection_seconds(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT total_connection_seconds FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ==========================================
# 📡 دوال الرادار الجديدة (Radar Functions)
# ==========================================
def update_radar_data(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE users SET last_seen=?, total_connection_seconds = COALESCE(total_connection_seconds, 0) + 60 WHERE email=?", (now_str, email))
    conn.commit()
    conn.close()

def get_radar_data(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT last_seen, total_connection_seconds FROM users WHERE email=?", (email,))
    result = c.fetchone()
    conn.close()
    if result:
        return {"last_seen": result[0], "total_seconds": result[1] or 0}
    return {"last_seen": None, "total_seconds": 0}

def log_daily_usage(email, total_used_bytes):
    today = str(datetime.date.today())
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO daily_usage VALUES (?, ?, ?)", (email, today, total_used_bytes))
    conn.commit()
    conn.close()

def get_usage_stats(email, current_total_used):
    today = str(datetime.date.today())
    yesterday = str(datetime.date.today() - datetime.timedelta(days=1))
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT total_used FROM daily_usage WHERE email=? AND date=?", (email, yesterday))
    y_data = c.fetchone()
    used_yesterday_total = y_data[0] if y_data else 0
    used_today = current_total_used - used_yesterday_total if current_total_used > used_yesterday_total else current_total_used
    conn.close()
    return used_today, used_yesterday_total


# ==========================================
# 3️⃣ كائن (db) لضمان التوافق مع بقية ملفات البوت
# ==========================================
class DummyDB:
    def init_db(self):
        init_sqlite_db()
        
    def get_all_users(self):
        return list(load_db().keys())
        
    def log_daily_usage_obj(self, email, usage):
        log_daily_usage(email, usage)
        
    def get_user(self, email):
        return load_db().get(email)
        
    def delete_user(self, email):
        data = load_db()
        if email in data:
            del data[email]
            update_db(data)
        
        try:
            conn = sqlite3.connect(SQLITE_DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM users WHERE email=?", (email,))
            conn.commit()
            conn.close()
        except: pass

    # 🔥 إضافة الدوال المفقودة لخدمة العملاء والإحصائيات بداخل الكائن 🔥
    def link_user_subscription(self, chat_id, email):
        return link_user_subscription(chat_id, email)
        
    def get_user_subscriptions(self, chat_id):
        return get_user_subscriptions(chat_id)
        
    def get_subscription_details(self, email):
        return get_subscription_details(email)
        
    def get_usage_stats(self, email, current_total_used):
        return get_usage_stats(email, current_total_used)

db = DummyDB()
db.init_db()
