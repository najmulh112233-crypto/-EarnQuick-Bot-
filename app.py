import os
import sqlite3
import json
import logging
import datetime
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor

# --- ১. কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী সেট করা হয়েছে) ---
# গোপনীয়তা বজায় রাখতে এইগুলি Render Environment Variables হিসাবে সেট করা উচিত।
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8320840106:AAF9P0LhVzcvvu-UGxWirLmaRKUm-P2Y9Zw")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://earnquick-bot.onrender.com/") 
BOT_USERNAME = "@EarnQuick_Official_bot"
SPONSOR_CHANNEL = "https://t.me/EarnQuickOfficial"

# আয়ের নিয়ম
AD_INCOME = 20.00          # প্রতি বিজ্ঞাপনে পয়েন্ট (পরিবর্তিত)
DAILY_AD_LIMIT = 300       # দৈনিক বিজ্ঞাপনের সীমা
REFERRAL_BONUS_TK = 125.00 # রেফারেল বোনাস (টাকায়)
POINT_TO_TK_RATIO = 5000 / 20  # 5000 পয়েন্ট = 20 টাকা; অর্থাৎ 1 টাকা = 250 পয়েন্ট

# ডেটাবেস কনফিগারেশন
DB_NAME = 'user_data.db'

# লগিং সেটআপ
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ২. ডেটাবেস ফাংশন ---

def initialize_db():
    """ডেটাবেস টেবিল তৈরি করে।"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.00, 
            daily_ads_seen INTEGER DEFAULT 0,
            total_referrals INTEGER DEFAULT 0,
            referred_by INTEGER,
            last_ad_date TEXT 
        )
    ''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    """ইউজারের ডেটা ফেরত দেয়।"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    data = c.fetchone()
    conn.close()
    return data

def create_user(user_id, username, referred_by=None):
    """নতুন ইউজার তৈরি করে এবং রেফারেল বোনাস দেয় (যদি থাকে)।"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  (user_id, username, 0.00, 0, 0, referred_by, str(datetime.date.today())))
        conn.commit()
        
        # রেফারেল বোনাস লজিক 
        if referred_by and referred_by != user_id:
            bonus_points = REFERRAL_BONUS_TK * POINT_TO_TK_RATIO 
            c.execute("UPDATE users SET balance = balance + ?, total_referrals = total_referrals + 1 WHERE user_id = ?", 
                      (bonus_points, referred_by))
            conn.commit()
            logger.info(f"User {user_id} referred by {referred_by}. Bonus {bonus_points} points granted.")
            
    except Exception as e:
        logger.error(f"Error creating user or giving bonus: {e}")
    finally:
        conn.close()

def update_user_ad_status(user_id):
    """বিজ্ঞাপন দেখার পর ব্যালেন্স আপডেট করে।"""
    today = str(datetime.date.today())
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # দৈনিক কাউন্টার রিসেট করা
    c.execute("UPDATE users SET daily_ads_seen = 0 WHERE user_id = ? AND last_ad_date != ?", (user_id, today))
    conn.commit()

    c.execute("SELECT daily_ads_seen FROM users WHERE user_id = ?", (user_id,))
    ads_seen = c.fetchone()[0]

    if ads_seen < DAILY_AD_LIMIT:
        c.execute("UPDATE users SET balance = balance + ?, daily_ads_seen = daily_ads_seen + 1, last_ad_date = ? WHERE user_id = ?", 
                  (AD_INCOME, today, user_id))
        conn.commit()
        conn.close()
        return True, ads_seen + 1
    else:
        conn.close()
        return False, ads_seen

# --- ৩. টেলিগ্রাম হ্যান্ডলার্স ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start কমান্ড হ্যান্ডেল করে।"""
    user = update.effective_user
    username = user.username if user.username else user.first_name
    
    referred_by = None
    if context.args:
        try:
            referred_by = int(context.args[0])
            if referred_by == user.id: 
                 referred_by = None
        except ValueError:
            pass 

    if not get_user_data(user.id):
        create_user(user.id, username, referred_by)

    # মিনি অ্যাপ বাটন
    web_app_button = InlineKeyboardButton(
        text="💰 ইনকাম শুরু করুন 💰",
        web_app=WebAppInfo(url=WEB_APP_URL)
    )
    
    keyboard = InlineKeyboardMarkup([
        [web_app_button],
        [InlineKeyboardButton("🔗 স্পন্সর চ্যানেল", url=SPONSOR_CHANNEL)]
    ])

    await update.message.reply_html(
        f"✅ স্বাগতম **{user.first_name}**!\n\n"
        f"নিচের **ইনকাম শুরু করুন** বাটন থেকে Mini App খুলুন এবং দৈনিক বিজ্ঞাপন দেখে পয়েন্ট আয় করুন।\n\n"
        f"**পয়েন্ট রেট:** {int(POINT_TO_TK_RATIO)} পয়েন্ট = ১ টাকা।",
        reply_markup=keyboard
    )

async def handle_mini_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """মিনি অ্যাপ থেকে বিজ্ঞাপন দেখার ডেটা হ্যান্ডেল করা।"""
    user_id = update.effective_user.id
    try:
        data = json.loads(update.message.web_app_data.data)
        
        if data.get("action") == "ad_completed":
            success, ads_seen = update_user_ad_status(user_id)
            
            if success:
                await update.message.reply_text(
                    f"🎉 সফল! আপনি {AD_INCOME:.2f} পয়েন্ট আয় করেছেন।\n"
                    f"আজকের বিজ্ঞাপন দেখা হয়েছে: {ads_seen}/{DAILY_AD_LIMIT}"
                )
            else:
                await update.message.reply_text(
                    f"⚠️ দুঃখিত! আজকের জন্য আপনার {DAILY_AD_LIMIT}টি বিজ্ঞাপনের কোটা পূর্ণ হয়েছে। আগামীকাল আবার চেষ্টা করুন।"
                )
        
    except Exception as e:
        logger.error(f"Error handling mini app data: {e}")
        await update.message.reply_text("ডেটা প্রসেস করতে ত্রুটি হয়েছে।")


# --- ৪. ফ্লাস্ক ওয়েব সার্ভার এবং ওয়েবুক সেটআপ ---

flask_app = Flask(__name__)
PORT = int(os.environ.get('PORT', 5000))

@flask_app.route('/webhook', methods=['POST'])
async def webhook_handler():
    """টেলিগ্রাম থেকে আসা ওয়েবুক অনুরোধ হ্যান্ডেল করে।"""
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        executor.submit(lambda: application.update_queue.put_nowait(update))
        return "ok"
    return "ok"

@flask_app.route('/data', methods=['GET'])
def get_dashboard_data():
    """মিনি অ্যাপের জন্য ড্যাশবোর্ডের ডেটা JSON ফরম্যাটে সরবরাহ করে।"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "User ID required"}), 400
    
    data = get_user_data(int(user_id))
    if not data:
        # যদি ইউজার না থাকে, তবে একটি ইনিশিয়াল ডেটা ফেরত দিন
        return jsonify({
            "user_id": int(user_id),
            "balance": "0.00",
            "daily_ads_seen": 0,
            "total_referrals": 0,
            "daily_ad_limit": DAILY_AD_LIMIT,
            "ad_income": AD_INCOME,
            "referral_bonus_tk": REFERRAL_BONUS_TK
        })

    balance_in_points = data[2]
    
    user_data = {
        "user_id": data[0],
        "balance": f"{balance_in_points:.2f}", # পয়েন্টে ব্যালেন্স
        "daily_ads_seen": data[3],
        "total_referrals": data[4],
        "daily_ad_limit": DAILY_AD_LIMIT,
        "ad_income": AD_INCOME,
        "referral_bonus_tk": REFERRAL_BONUS_TK
    }
    return jsonify(user_data)


# টেলিগ্রাম বট সেটআপ
application = Application.builder().token(BOT_TOKEN).updater(None).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_mini_app_data))

# থ্রেড পুল ইনিশিয়ালাইজ করা
executor = ThreadPoolExecutor(max_workers=4)

# Render-এর জন্য Gunicorn/Flask অ্যাপ
app = flask_app

# --- ৫. ইনিশিয়ালাইজেশন ---
@flask_app.before_request
def before_request_check():
    """প্রতিটি অনুরোধের আগে ডেটাবেস ইনিশিয়ালাইজেশন নিশ্চিত করে।"""
    if not os.path.exists(DB_NAME):
        initialize_db()

# অ্যাপ চালু হওয়ার পর ওয়েবুক সেট করা
def setup_webhook():
    webhook_url = f"{WEB_APP_URL}webhook"
    application.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")

if os.environ.get("RENDER"):
    with application:
        setup_webhook()
