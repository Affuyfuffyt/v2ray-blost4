#!/bin/bash
clear
echo "=================================================="
echo "    🚀 أداة إدارة V2Ray (النسخة الاحترافية) "
echo "        تثبيت ديناميكي - مستودع v2ray-blost4"
echo "=================================================="

# 1. تنظيف وإيقاف العمليات السابقة
pkill -9 xray
pkill -9 -f run.py

# 2. أخذ البيانات المطلوبة
read -p "🔑 أدخل توكن البوت: " BOT_TOKEN
read -p "👑 أدخل الآيدي الخاص بك (ADMIN_ID): " ADMIN_ID
read -p "🛠️ أدخل Alwaysdata API Key: " AD_API_KEY
read -p "🆔 أدخل Site ID الخاص بك: " AD_SITE_ID
read -p "🌐 أدخل الدومين الخاص بك (مثال: google.com): " AD_DOMAIN
read -p "📂 أدخل اسم المجلد الجديد (مثلاً week_blust): " APP_DIR

# إذا لم يدخل اسماً، نستخدم الافتراضي
APP_DIR=${APP_DIR:-v2ray_manager}

# 3. تجهيز المجلدات
HOME_PATH=$(eval echo ~$USER)
WORK_DIR="$HOME_PATH/$APP_DIR"
XRAY_DIR="$HOME_PATH/xray_core"

mkdir -p $XRAY_DIR
rm -rf $WORK_DIR
mkdir -p $WORK_DIR

# 4. تحميل المحرك Xray (إذا لم يكن موجوداً)
if [ ! -f "$XRAY_DIR/xray" ]; then
    echo "[+] جاري تحميل محرك Xray..."
    cd $XRAY_DIR
    wget -q https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip
    unzip -q Xray-linux-64.zip
    rm Xray-linux-64.zip
    chmod +x xray
fi

# 5. سحب ملفات البوت من المستودع الجديد
echo "[+] جاري سحب ملفات البوت من v2ray-blost..."
git clone https://github.com/Affuyfuffyt/v2ray-blost4.git $WORK_DIR
cd $WORK_DIR

# 🔥 الخطوة السحرية: تبديل اسم المجلد داخل كل ملفات المشروع تلقائياً 🔥
echo "[+] جاري تهيئة الملفات للاسم الجديد: $APP_DIR"
find $WORK_DIR -type f -name "*.py" -exec sed -i "s/v2ray_manager/$APP_DIR/g" {} +

# 6. نقل ملف config.json للمكان الصحيح وتصحيح المسارات تلقائياً
cp xray_core/config.json $XRAY_DIR/config.json
sed -i "s|/home/.*/xray_core/access.log|access.log|g" $XRAY_DIR/config.json
sed -i "s|/home/.*/xray_core/error.log|error.log|g" $XRAY_DIR/config.json

# 7. تخزين كل المفاتيح في ملف البيئة المخفي
echo "BOT_TOKEN=$BOT_TOKEN" > .env
echo "ADMIN_ID=$ADMIN_ID" >> .env
echo "AD_API_KEY=$AD_API_KEY" >> .env
echo "AD_SITE_ID=$AD_SITE_ID" >> .env
echo "AD_DOMAIN=$AD_DOMAIN" >> .env

# تجهيز ملف المفاتيح الموحد للريستارت
echo "$AD_SITE_ID" > $HOME_PATH/alwaysdata_keys.txt
echo "$AD_API_KEY" >> $HOME_PATH/alwaysdata_keys.txt
echo "$AD_DOMAIN" >> $HOME_PATH/alwaysdata_keys.txt

# 8. تثبيت المكاتب
echo "[+] جاري تثبيت المتطلبات..."
pip install -r requirements.txt

# 🔥 9. إنشاء ملف المراقب الأبدي (Keep Alive) باسم المجلد الجديد 🔥
cat << EOF > $HOME_PATH/keep_alive.sh
#!/bin/bash
if ! pgrep -f "run.py" > /dev/null
then
    echo "البوت كان متوقف... جاري إعادة تشغيله."
    cd $WORK_DIR
    nohup python3 run.py > system.log 2>&1 &
fi
EOF
chmod +x $HOME_PATH/keep_alive.sh

# تشغيل البوت لأول مرة
nohup python3 run.py > system.log 2>&1 &

echo "=================================================="
echo "✅ تم التثبيت بنجاح في مجلد: $APP_DIR"
echo "⚠️ الكود الآن ديناميكي ويعمل على مستودع v2ray-blost"
echo "⚠️ خطوة أخيرة مهمة: قم بإضافة $HOME_PATH/keep_alive.sh إلى Scheduled Tasks في لوحة Alwaysdata."
echo "=================================================="
