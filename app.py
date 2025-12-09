# app.py (Updated Backend Logic for Render Deployment)

import os
from flask import Flask, jsonify, request, render_template
import psycopg2
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

# --- কনফিগারেশন লোড করা ---
DATABASE_URL = os.environ.get("DATABASE_URL") 
MONETAG_ZONE_ID = os.environ.get("MONETAG_ZONE_ID", "10070523") # Default Value is set based on your provided tag

AD_REWARD_POINTS = int(os.environ.get("AD_REWARD_POINTS", 20))
REFERRAL_COMMISSION_PERCENT = float(os.environ.get("REFERRAL_COMMISSION_PERCENT", 0.05))
MIN_WITHDRAW_POINTS = int(os.environ.get("MIN_WITHDRAW_POINTS", 5000))
POINTS_PER_BDT = int(os.environ.get("POINTS_PER_BDT", 250)) 
RUNNING_HEADLINE = os.environ.get("RUNNING_HEADLINE", "EarnQuick BD is live!")
MAX_DAILY_TASKS = 30 

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
        points_per_bdt=POINTS_PER_BDT,
        ad_reward_points=AD_REWARD_POINTS,
        monetag_zone_id=MONETAG_ZONE_ID
    )

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    """ইউজার ব্যালেন্স লোড করে। (NOTE: Production-এ user_id অবশ্যই validate করতে হবে)"""
    user_id = request.args.get('user_id', 123) 
    
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "ডাটাবেস সংযোগ ব্যর্থ"}), 500

    try:
        cursor = conn.cursor()
        # এখানে অবশ্যই নিশ্চিত করুন যে 'users' টেবিলটি ডাটাবেসে তৈরি হয়েছে।
        cursor.execute("SELECT balance, tasks_completed FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        
        if result:
            balance, tasks_completed = result
            return jsonify({
                "success": True, "balance": balance, "tasks_completed": tasks_completed, "max_tasks": MAX_DAILY_TASKS
            })
        else:
            return jsonify({"success": False, "message": "ইউজার খুঁজে পাওয়া যায়নি। বটটি /start কমান্ড দিয়ে শুরু করুন।"}), 404
            
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
    if conn is None: return jsonify({"error": "ডাটাবেস সংযোগ ব্যর্থ"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT tasks_completed, referrer_id FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info or user_info[0] >= MAX_DAILY_TASKS: 
            return jsonify({"success": False, "message": "দৈনিক টাস্ক সীমা অতিক্রম করেছে বা ইউজার ডেটা নেই"}), 400
            
        referrer_id = user_info[1]
        
        # ব্যালেন্স এবং টাস্ক সংখ্যা আপডেট করা
        cursor.execute("""
            UPDATE users SET balance = balance + %s, tasks_completed = tasks_completed + 1
            WHERE user_id = %s 
            RETURNING balance, tasks_completed
        """, (AD_REWARD_POINTS, user_id))
        
        new_balance, new_tasks = cursor.fetchone()
        
        # রেফারেল কমিশন যোগ করা
        commission = 0
        if referrer_id:
            commission = AD_REWARD_POINTS * REFERRAL_COMMISSION_PERCENT
            cursor.execute("""
                UPDATE users SET balance = balance + %s 
                WHERE user_id = %s
            """, (commission, referrer_id))
            
        conn.commit()
        
        return jsonify({
            "success": True, "message": f"বিজ্ঞাপন সফল! {AD_REWARD_POINTS} পয়েন্ট যোগ করা হয়েছে।", 
            "new_balance": new_balance, "new_tasks": new_tasks, "commission_added": commission
        })
        
    except Exception as e:
        conn.rollback()
        logging.error(f"ট্রানজেকশন ত্রুটি: {e}")
        return jsonify({"error": "ডাটাবেস আপডেট ব্যর্থ"}), 500
    finally:
        if conn: conn.close()

@app.route('/api/request_withdraw', methods=['POST'])
def request_withdraw():
    """উইথড্রয়াল রিকোয়েস্ট জমা দেয়।"""
    data = request.json
    user_id = data.get('user_id', 123)
    amount_points = data.get('amount_points')
    method = data.get('method')
    account_number = data.get('account_number')
    
    if amount_points < MIN_WITHDRAW_POINTS:
        return jsonify({"success": False, "message": f"সর্বনিম্ন উইথড্র {MIN_WITHDRAW_POINTS} পয়েন্ট।"}), 400
        
    conn = get_db_connection()
    if conn is None: return jsonify({"error": "ডাটাবেস সংযোগ ব্যর্থ"}), 500
    
    try:
        cursor = conn.cursor()
        # ১. ব্যালেন্স চেক করা
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        current_balance = cursor.fetchone()[0]
        
        if current_balance < amount_points:
             return jsonify({"success": False, "message": "অপর্যাপ্ত ব্যালেন্স।"}), 400
        
        amount_bdt = amount_points / POINTS_PER_BDT
        
        # ২. ব্যালেন্স থেকে পয়েন্ট কেটে নেওয়া
        cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount_points, user_id))

        # ৩. উইথড্রয়াল রিকোয়েস্ট সেভ করা
        cursor.execute("""
            INSERT INTO withdraw_requests (user_id, amount_points, amount_bdt, method, account_number)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, amount_points, amount_bdt, method, account_number))
        
        conn.commit()
        
        return jsonify({
            "success": True, 
            "message": f"উইথড্রয়াল রিকোয়েস্ট জমা দেওয়া হয়েছে! আপনি {amount_bdt:.2f} টাকা পাবেন।",
        })
    except Exception as e:
        conn.rollback()
        logging.error(f"উইথড্রয়াল ত্রুটি: {e}")
        return jsonify({"error": "উইথড্র রিকোয়েস্ট জমা দেওয়া ব্যর্থ"}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
