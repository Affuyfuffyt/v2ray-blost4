import json
import os
import sqlite3
import datetime
import time

# 🔥 الحل الجذري: تحديد مسار المجلد الحالي تلقائياً (سواء كان week_blust أو غيره) 🔥
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_DB_PATH = os.path.join(BASE_DIR, 'users_db.json')
SQLITE_DB_PATH = os.path.join(BASE_DIR, 'bot_data.db')

# ==========================================
# 1️⃣ قسم قاعدة بيانات JSON (للتوافق القديم)
# ==========================================
def load_db():
    if not os.path.exists(JSON_DB_PATH): return {}
    try:
        with open(JSON_DB_PATH, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def update_db(data):
    with open(JSON_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

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
# 2️⃣ قسم قاعدة بيانات SQLite (المركزية الشاملة)
# ==========================================
def init_sqlite_db():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    
    # 1. جدول المشتركين
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (email TEXT PRIMARY KEY, uuid TEXT, port INTEGER, quota_bytes REAL, expiry_date TEXT, status TEXT)''')
    
    # تحديثات جدول المشتركين
    try: c.execute("ALTER TABLE users ADD COLUMN last_seen TEXT")
    except: pass 
    try: c.execute("ALTER TABLE users ADD COLUMN total_connection_seconds REAL DEFAULT 0")
    except: pass 
    try: c.execute("ALTER TABLE users ADD COLUMN ref_code TEXT")
    except: pass
    
    # 🔥 إضافة حقل لمعرفة المشترك بيا سيرفر موجود 🔥
    try: c.execute("ALTER TABLE users ADD COLUMN server_id INTEGER DEFAULT 1")
    except: pass

    # 2. جداول الاستهلاك والرادار
    c.execute('''CREATE TABLE IF NOT EXISTS daily_usage
                 (email TEXT, date TEXT, total_used REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_connection
                 (email TEXT, date TEXT, connection_seconds REAL, PRIMARY KEY (email, date))''')

    # 3. جداول المكافآت وخدمة العملاء
    c.execute('''CREATE TABLE IF NOT EXISTS pending_rewards
                 (referrer_email TEXT, invited_email TEXT, reward_seconds REAL, chat_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_subscriptions
                 (chat_id TEXT, email TEXT, PRIMARY KEY (chat_id, email))''')

    # 🔥🔥 4. الجدول الجديد: شبكة السيرفرات 🔥🔥
    c.execute('''CREATE TABLE IF NOT EXISTS servers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT, 
                  site_id TEXT, 
                  api_key TEXT, 
                  ftp_host TEXT, 
                  ftp_user TEXT, 
                  ftp_pass TEXT, 
                  status TEXT)''')
                  
    # تسجيل السيرفر الحالي كسيرفر رئيسي (حتى ما تعطل الأكواد القديمة)
    c.execute("SELECT COUNT(*) FROM servers")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO servers (id, name, site_id, api_key, ftp_host, ftp_user, ftp_pass, status) VALUES (1, 'السيرفر الرئيسي (المحلي)', 'local', 'local', 'local', 'local', 'local', 'active')")

    conn.commit()
    conn.close()

# ==========================================
# 🖥️ دوال إدارة شبكة السيرفرات (جديد)
# ==========================================
def add_server(name, site_id, api_key, ftp_host, ftp_user, ftp_pass):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO servers (name, site_id, api_key, ftp_host, ftp_user, ftp_pass, status) VALUES (?, ?, ?, ?, ?, ?, 'active')",
              (name, site_id, api_key, ftp_host, ftp_user, ftp_pass))
    conn.commit()
    conn.close()

def get_all_servers():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, site_id, status FROM servers")
    rows = c.fetchall()
    conn.close()
    return rows

def get_server_details(server_id):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, site_id, api_key, ftp_host, ftp_user, ftp_pass FROM servers WHERE id=?", (server_id,))
    row = c.fetchone()
    conn.close()
    return row

def delete_server(server_id):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM servers WHERE id=?", (server_id,))
    conn.commit()
    conn.close()

# ==========================================
# 👥 دوال المشتركين العامة
# ==========================================
# تم إضافة server_id للدالة
def add_user(email, uuid, port, quota_bytes, expiry_date, server_id=1):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email=?", (email,))
    if c.fetchone():
        c.execute("UPDATE users SET uuid=?, port=?, quota_bytes=?, expiry_date=?, status='active', server_id=? WHERE email=?",
                  (uuid, port, quota_bytes, str(expiry_date), server_id, email))
    else:
        c.execute("INSERT INTO users (email, uuid, port, quota_bytes, expiry_date, status, last_seen, total_connection_seconds, ref_code, server_id) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, NULL, ?)", 
                  (email, uuid, port, quota_bytes, str(expiry_date), 'active', server_id))
    conn.commit()
    conn.close()

def get_active_users():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, uuid, expiry_date, server_id FROM users WHERE status='active'")
    users = c.fetchall()
    conn.close()
    return users

def get_all_users():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def set_user_expired(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET status='expired' WHERE email=?", (email,))
    conn.commit()
    conn.close()

# ==========================================
# 📱 دوال خدمة العملاء (ربط الحسابات)
# ==========================================
def link_user_subscription(chat_id, email):
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT email FROM users WHERE email=?", (email,))
        if c.fetchone():
            c.execute('''CREATE TABLE IF NOT EXISTS user_subscriptions (chat_id TEXT, email TEXT, PRIMARY KEY (chat_id, email))''')
            try:
                c.execute("INSERT INTO user_subscriptions (chat_id, email) VALUES (?, ?)", (str(chat_id), email))
                conn.commit()
                success = True
            except: success = False
        else: success = False
        conn.close()
        return success
    except: return False

def get_user_subscriptions(chat_id):
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT email FROM user_subscriptions WHERE chat_id=?", (str(chat_id),))
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except: return []

def get_subscription_details(email):
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT expiry_date, quota_bytes, status, last_seen, total_connection_seconds, server_id FROM users WHERE email=?", (email,))
        data = c.fetchone()
        conn.close()
        return data
    except: return None

# ==========================================
# 🎁 دوال المكافآت والدعوات
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
# 📡 دوال الرادار
# ==========================================
def update_radar_data(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_str = str(datetime.date.today())
    c.execute("UPDATE users SET last_seen=?, total_connection_seconds = COALESCE(total_connection_seconds, 0) + 60 WHERE email=?", (now_str, email))
    c.execute("INSERT INTO daily_connection (email, date, connection_seconds) VALUES (?, ?, 60) ON CONFLICT(email, date) DO UPDATE SET connection_seconds = connection_seconds + 60", (email, today_str))
    conn.commit()
    conn.close()

def get_radar_data(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT last_seen, total_connection_seconds FROM users WHERE email=?", (email,))
    result = c.fetchone()
    conn.close()
    if result: return {"last_seen": result[0], "total_seconds": result[1] or 0}
    return {"last_seen": None, "total_seconds": 0}

def get_full_radar_stats(email):
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT last_seen, total_connection_seconds FROM users WHERE email=?", (email,))
    user_data = c.fetchone()
    if not user_data:
        conn.close()
        return None
    last_seen, total_sec = user_data
    total_sec = total_sec or 0
    c.execute("SELECT date, connection_seconds FROM daily_connection WHERE email=? ORDER BY date DESC", (email,))
    history = c.fetchall()
    conn.close()
    today_str = str(datetime.date.today())
    today_sec = 0
    archive = []
    for row in history:
        date_str, sec = row
        if date_str == today_str: today_sec = sec
        else: archive.append({"date": date_str, "seconds": sec})
    return {"last_seen": last_seen, "total_seconds": total_sec, "today_seconds": today_sec, "history": archive}

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

# تشغيل التهيئة فوراً
init_sqlite_db()
