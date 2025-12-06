# app.py (Telegram Web App Backend Logic)

import os
from flask import Flask, jsonify, request, render_template
import psycopg2
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

# --- কনফিগারেশন লোড করা ---
DATABASE_URL = os.environ.get("DATABASE_URL") 
AD_REWARD_POINTS = int(os.environ.get("AD_REWARD_POINTS", 20))
REFERRAL_BONUS_POINTS = int(os.environ.get("REFERRAL_BONUS_POINTS", 250))
REFERRAL_COMMISSION_PERCENT = float(os.environ.get("REFERRAL_COMMISSION_PERCENT", 0.05))
MIN_WITHDRAW_POINTS = int(os.environ.get("MIN_WITHDRAW_POINTS", 5000))
POINTS_PER_BDT = int(os.environ.get("POINTS_PER_BDT", 250)) # 5000/20 = 250
RUNNING_HEADLINE = os.environ.get("RUNNING_HEADLINE", "EarnQuick BD is live!")

app = Flask(__name__)

# --- ডেটাবেস সংযোগ ---
def get_db_connection():
    if not DATABASE_URL:
        logging.error("DATABASE_URL is not set.")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logging.error(f"ডাটাবেস সংযোগ ব্যর্থ: {e}")
        return None

# --- API রুটসমূহ ---

@app.route('/')
def serve_webapp():
    """Telegram Web App এর জন্য HTML পরিবেশন।"""
    return render_template('index.html', 
        headline=RUNNING_HEADLINE,
        min_withdraw_points=MIN_WITHDRAW_POINTS,
        points_per_bdt=POINTS_PER_BDT
    )

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    """ইউজার ব্যালেন্স এবং টাস্ক লোড করে।"""
    # PRODUCTION: এখানে টেলিগ্রাম WebApp.initData থেকে সঠিক user_id পেতে হবে।
    user_id = 123 # ডেমো ID
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "ডাটাবেস সংযোগ ব্যর্থ"}), 500

    try:
        cursor = conn.cursor()
        # NOTE: 'users' টেবিলে 'balance', 'tasks_completed', 'referrer_id' কলাম নিশ্চিত করুন।
        cursor.execute("SELECT balance, tasks_completed FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        
        if result:
            balance, tasks_completed = result
            return jsonify({
                "success": True, 
                "balance": balance, 
                "tasks_completed": tasks_completed,
                "max_tasks": 30, # দৈনিক সীমা
            })
        else:
            return jsonify({"success": False, "message": "ইউজার খুঁজে পাওয়া যায়নি।"}) 
            
    except Exception as e:
        logging.error(f"ডাটাবেস ত্রুটি: {e}")
        return jsonify({"error": "সার্ভার ত্রুটি"}), 500
    finally:
        if conn: conn.close()

@app.route('/api/watch_ad', methods=['POST'])
def watch_ad():
    """বিজ্ঞাপন দেখার পর ব্যালেন্স আপডেট করে + রেফারেল কমিশন যোগ করে।"""
    user_id = request.json.get('user_id', 123)
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "ডাটাবেস সংযোগ ব্যর্থ"}), 500

    try:
        cursor = conn.cursor()
        
        # ১. টাস্ক সীমা এবং রেফারার ID বের করা
        cursor.execute("SELECT tasks_completed, referrer_id FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info or user_info[0] >= 30: # টাস্ক সীমা চেক করা
            return jsonify({"success": False, "message": "দৈনিক টাস্ক সীমা অতিক্রম করেছে বা ইউজার নেই"}), 400
            
        referrer_id = user_info[1]
        
        # ২. ব্যালেন্স এবং টাস্ক সংখ্যা আপডেট করা (২৫০ পয়েন্ট নয়, ২০ পয়েন্ট যোগ হবে)
        cursor.execute("""
            UPDATE users SET balance = balance + %s, tasks_completed = tasks_completed + 1
            WHERE user_id = %s 
            RETURNING balance, tasks_completed
        """, (AD_REWARD_POINTS, user_id))
        
        new_balance, new_tasks = cursor.fetchone()
        commission = 0
        
        # ৩. রেফারেল কমিশন যোগ করা
        if referrer_id:
            commission = AD_REWARD_POINTS * REFERRAL_COMMISSION_PERCENT
            cursor.execute("""
                UPDATE users SET balance = balance + %s 
                WHERE user_id = %s
            """, (commission, referrer_id))
            
        conn.commit()
        
        return jsonify({
            "success": True, 
            "message": f"বিজ্ঞাপন সফল! {AD_REWARD_POINTS} পয়েন্ট যোগ করা হয়েছে।", 
            "new_balance": new_balance,
            "new_tasks": new_tasks,
            "commission_added": commission
        })
        
    except Exception as e:
        conn.rollback()
        logging.error(f"ট্রানজেকশন ত্রুটি: {e}")
        return jsonify({"error": "ডাটাবেস আপডেট ব্যর্থ"}), 500
    finally:
        if conn: conn.close()

# --- উইথড্রয়াল রুট (অসম্পূর্ণ) ---
@app.route('/api/request_withdraw', methods=['POST'])
def request_withdraw():
    """ইউজারের উইথড্রয়াল রিকোয়েস্ট জমা নেয়।"""
    data = request.json
    user_id = data.get('user_id', 123)
    amount_points = data.get('amount_points')
    method = data.get('method')
    account_number = data.get('account_number')
    
    if amount_points < MIN_WITHDRAW_POINTS:
        return jsonify({"success": False, "message": f"সর্বনিম্ন উইথড্র {MIN_WITHDRAW_POINTS} পয়েন্ট।"}), 400
        
    # NOTE: এখানে ডাটাবেসে উইথড্রয়াল রিকোয়েস্ট সেভ করার লজিক যুক্ত হবে।
    # ইউজার অ্যাকাউন্টের ব্যালেন্স থেকে পয়েন্ট কেটে নেওয়ার লজিকও এখানে দরকার।
    
    # ডেমো রেসপন্স:
    amount_bdt = amount_points / POINTS_PER_BDT
    return jsonify({
        "success": True, 
        "message": f"উইথড্রয়াল রিকোয়েস্ট জমা দেওয়া হয়েছে! আপনি {amount_bdt:.2f} টাকা পাবেন।",
        "methods": "বিকাশ, নগদ, রকেট"
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
