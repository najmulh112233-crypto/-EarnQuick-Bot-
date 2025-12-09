# telegram_bot.py (Telegram Bot Command Handler)

import os
import secrets
import logging
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
import psycopg2

load_dotenv()
logging.basicConfig(level=logging.INFO)

# --- কনফিগারেশন ---
DATABASE_URL = os.environ.get("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
RENDER_APP_URL = os.environ.get("RENDER_APP_URL", "https://your-render-app-url.onrender.com") 
REFERRAL_BONUS_POINTS = int(os.environ.get("REFERRAL_BONUS_POINTS", 250))
# ---

# --- ডেটাবেস সংযোগ ---
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logging.error(f"বট ডাটাবেস সংযোগ ব্যর্থ: {e}")
        return None

# --- ইউটিলিটি ফাংশন ---
def generate_referral_code(length=8):
    return secrets.token_hex(length // 2).upper()

# --- /start কমান্ড হ্যান্ডলার ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    username = user.username or f"User{user_id}"
    args = context.args 
    
    referrer_code = args[0].upper() if args else None
    referrer_id = None
    
    conn = get_db_connection()
    if conn is None:
        await update.message.reply_text("দুঃখিত, ডাটাবেস সংযোগে সমস্যা হচ্ছে।")
        return

    try:
        cursor = conn.cursor()
        
        # ১. ইউজারকে ডেটাবেসে খোঁজা
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
        user_exists = cursor.fetchone()
        
        # ২. রেজিস্ট্রেশন লজিক
        if not user_exists:
            # রেফারেল ট্র্যাকিং
            if referrer_code:
                cursor.execute("SELECT user_id FROM users WHERE referral_code = %s", (referrer_code,))
                referrer_result = cursor.fetchone()
                if referrer_result and referrer_result[0] != user_id:
                    referrer_id = referrer_result[0]
                    
            # নতুন ইউজার তৈরি করা
            new_referral_code = generate_referral_code()
            initial_balance = REFERRAL_BONUS_POINTS if referrer_id else 0
            
            cursor.execute("""
                INSERT INTO users (user_id, balance, referrer_id, referral_code)
                VALUES (%s, %s, %s, %s)
            """, (user_id, initial_balance, referrer_id, new_referral_code))
            
            conn.commit()
            
            message = (
                f"🎉 স্বাগতম {username}!\n"
                f"আপনি নিবন্ধিত হয়েছেন। আপনার প্রাথমিক ব্যালেন্স: **{initial_balance} পয়েন্ট**।"
            )
            if referrer_id:
                 message += f"\n\n🎁 আপনি রেফারেল বোনাস হিসেবে {REFERRAL_BONUS_POINTS} পয়েন্ট পেয়েছেন।"
                 
        else:
            message = f"👋 আবার স্বাগতম {username}! আপনি ইতিমধ্যেই নিবন্ধিত। নিচের বাটন ব্যবহার করুন।"

        # ৩. ওয়েব অ্যাপ বাটন তৈরি
        keyboard = [[InlineKeyboardButton("▶️ উপার্জন শুরু করুন", web_app=WebAppInfo(url=RENDER_APP_URL))]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        conn.rollback()
        logging.error(f"স্টার্ট কমান্ড ত্রুটি: {e}")
        await update.message.reply_text("একটি অভ্যন্তরীণ ত্রুটি ঘটেছে।")
    finally:
        if conn: conn.close()


def main():
    """বট অ্যাপ্লিকেশন শুরু করুন।"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    logging.info("বট শুরু হচ্ছে (Polling)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
