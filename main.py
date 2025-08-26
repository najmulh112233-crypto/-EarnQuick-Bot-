import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Environment variables
TOKEN = os.environ.get('8004127220:AAFa1SmmQIr0SCl7EvkgDTotA27JNBnvbA0')  # Heroku/VPS থেকে Token নিন
ADMIN_ID = int(os.environ.get('ADMIN_ID', '5168384940'))  # Admin ID

# Sample offers & channels
OFFERS = [
    {"name": "Offer 1", "link": "https://data684.click/a52aa74cca7001f35a15/d56d74326c/?placementName=default"},
    {"name": "Offer 2", "link": "https://data684.click/a22029d6979cd7a03357/d1d43e0efb/?placementName=default"},
    {"name": "Offer 3", "link": "https://data684.click/3c4f67768a935d0127c1/66422737b8/?placementName=default"}
]

CHANNELS = [
    {"name": "EarnQuick_Official", "link": "https://t.me/boost/EarnQuick_Official"},
    {"name": "WhatsApp Channel", "link": "https://whatsapp.com/channel/0029VbBGYJxKwqSUQL4DY103"}
]

# In-memory referral tracking
referrals = {}  # {user_id: referral_count}

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("💰 Offers", callback_data="offers")],
        [InlineKeyboardButton("🔗 Referral", callback_data="referral")],
        [InlineKeyboardButton("📢 Join Channels", callback_data="channels")],
        [InlineKeyboardButton("📊 My Referrals", callback_data="myreferrals")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to 💸 EarnQuick Bot 💸", reply_markup=reply_markup)

# Callback handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "offers":
        msg = "🔥 Available Offers:\n"
        for offer in OFFERS:
            msg += f"{offer['name']}: {offer['link']}\n"
        await query.edit_message_text(msg)
    
    elif query.data == "referral":
        referral_link = f"https://t.me/YOUR_BOT_USERNAME?start={user_id}"
        await query.edit_message_text(f"Share your referral link:\n{referral_link}")
    
    elif query.data == "channels":
        msg = "📢 Join our channels:\n"
        for channel in CHANNELS:
            msg += f"{channel['name']}: {channel['link']}\n"
        await query.edit_message_text(msg)

    elif query.data == "myreferrals":
        count = referrals.get(user_id, 0)
        await query.edit_message_text(f"Your total referrals: {count}")

    elif query.data == "admin" and user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast Message", callback_data="broadcast")],
            [InlineKeyboardButton("⚙️ Update Offers", callback_data="update_offers")],
            [InlineKeyboardButton("💰 Withdraw Report", callback_data="withdraw")],
            [InlineKeyboardButton("🔍 View Referrals", callback_data="view_referrals")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Admin Panel:", reply_markup=reply_markup)

# Main function
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    print("💸 EarnQuick Bot is running...")
    app.run_polling()
