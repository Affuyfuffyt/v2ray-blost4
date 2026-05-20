import os
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env
load_dotenv()

# استدعاء المتغيرات وتجهيزها للاستخدام في باقي الملفات
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else 0

PANEL_URL = os.getenv('PANEL_URL')
PANEL_USER = os.getenv('PANEL_USER')
PANEL_PASS = os.getenv('PANEL_PASS')
