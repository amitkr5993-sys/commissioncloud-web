import os
import uuid
import json
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, request, redirect, jsonify, session, flash, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from models import init_db, get_db

app = Flask(__name__)
app.secret_key = "commission_cloud_secret_key_production"

init_db()

# Google Cloud OAuth Client ID
GOOGLE_CLIENT_ID = "425959144248-1774ja2dr8ddje1sqe17tg412c93qoom.apps.googleusercontent.com"

# vCommission Affiliate ID
AFFILIATE_ID = "133696"

MINIMUM_WITHDRAWAL = 200.0  # Minimum withdrawal limit in INR
REFERRAL_BONUS_AMOUNT = 50.0  # Referral bonus in INR
USER_CASHBACK_PERCENT = 0.40  # 40% User Share, 60% Admin Margin

# Context processor for global app settings
@app.context_processor
def inject_settings():
    conn = get_db()
    settings_rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    settings_dict = {row["key"]: row["value"] for row in settings_rows}
    return dict(app_settings=settings_dict)

# Function to load stores directly from local stores.json file (100% Reliable & No 404)
def fetch_vcommission_campaigns():
    if os.path.exists("stores.json"):
        try:
            with open("stores.json", "r") as f:
                stores = json.load(f)
                formatted_stores = []
                for store in stores:
                    formatted_stores.append({
                        "name": store.get("name", "Brand Offer"),
                        "category": store.get("category", "E-commerce"),
                        "cashback_rate": store.get("cashback_rate", "Upto 7% Cashback"),
                        "target_url": store.get("target_url", "https://www.vcommission.com"),
                        "badge": "Live Offer"
                    })
                if formatted_stores:
                    return formatted_stores
        except Exception as e:
            print("JSON Read Error:", str(e))
    
    # Fallback to local database stores table if JSON is missing
    conn = get_db()
    stores = conn.execute("SELECT * FROM stores").fetchall()
    conn.close()
    return [dict(s) for s in stores]

# ==============================================================================
# --- LANDING & ONBOARDING ROUTES ---
# ==============================================================================

@app.route('/')
def home():
    if "user_id" in session:
        return redirect("/dashboard")
    return render_template('welcome.html')

@app.route('/welcome')
def welcome():
    return redirect('/')

# ==============================================================================
# --- AUTHENTICATION ROUTES ---
# ==============================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect("/dashboard")

    ref_code = request.args.get("ref", "").strip()

    if request.method == "POST":
        login_type = request.form.get("login_type", "email")
        referral_input = request.form.get("referral_code", "").strip() or ref_code
        conn = get_db()

        if login_type == "email":
            email = request.form.get("email", "").strip().lower()
            if not email or "@" not in email:
                flash("Please enter a valid Email address.", "error")
                conn.close()
                return redirect(url_for("login", ref=ref_code))

            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user:
                session["user_id"] = user["id"]
                conn.close()
                flash(f"Welcome back, {user['name']}!", "success")
                return redirect("/dashboard")
            else:
                referrer = None
                if referral_input:
                    referrer = conn.execute("SELECT id FROM users WHERE referral_code = ?", (referral_input,)).fetchone()

                referrer_id = referrer["id"] if referrer else None
                new_user_code = f"USER{uuid.uuid4().hex[:5].upper()}"
                user_prefix = email.split("@")[0].capitalize()
                default_name = f"User {user_prefix}"

                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (name, email, phone, password, referral_code, confirmed_balance, pending_balance, referred_by, referral_bonus_given)
                    VALUES (?, ?, NULL, NULL, ?, 0.0, 0.0, ?, 0)
                ''', (default_name, email, new_user_code, referrer_id))
                
                new_id = cursor.lastrowid
                conn.commit()
                conn.close()

                session["user_id"] = new_id
                flash("Account created instantly! Welcome to Commission Cloud.", "success")
                return redirect("/dashboard")

        elif login_type == "phone":
            phone = request.form.get("phone", "").strip()
            password = request.form.get("password", "").strip()

            if not phone or len(phone) < 10 or not password:
                flash("Please enter a valid 10-digit Mobile Number and Password.", "error")
                conn.close()
                return redirect(url_for("login", ref=ref_code))

            user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
            if user:
                if user["password"] == password:
                    session["user_id"] = user["id"]
                    conn.close()
                    flash(f"Welcome back, {user['name']}!", "success")
                    return redirect("/dashboard")
                else:
                    conn.close()
                    flash("Incorrect password. Please try again.", "error")
                    return redirect(url_for("login", ref=ref_code))
            else:
                referrer = None
                if referral_input:
                    referrer = conn.execute("SELECT id FROM users WHERE referral_code = ?", (referral_input,)).fetchone()

                referrer_id = referrer["id"] if referrer else None
                new_user_code = f"USER{uuid.uuid4().hex[:5].upper()}"
                default_name = f"User {phone[-4:]}"
                dummy_email = f"user_{phone}@commissioncloud.local"

                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (name, email, phone, password, referral_code, confirmed_balance, pending_balance, referred_by, referral_bonus_given)
                    VALUES (?, ?, ?, ?, ?, 0.0, 0.0, ?, 0)
                ''', (default_name, dummy_email, phone, password, new_user_code, referrer_id))
                
                new_id = cursor.lastrowid
                conn.commit()
                conn.close()

                session["user_id"] = new_id
                flash("Account created successfully! Welcome to Commission Cloud.", "success")
                return redirect("/dashboard")

    return render_template("login.html", auto_ref=ref_code)

@app.route("/api/google-login", methods=["POST"])
def google_login():
    data = request.get_json() or {}
    token = data.get("credential")
    referral_input = (data.get("referral_code") or "").strip()

    if not token:
        return jsonify({"status": "error", "message": "Missing Google token"}), 400

    try:
        id_info = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        email = id_info.get("email")
        name = id_info.get("name") or (email.split("@")[0] if email else "User")

        if not email:
            return jsonify({"status": "error", "message": "Google did not provide an email"}), 400

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user:
            session["user_id"] = user["id"]
            conn.close()
            return jsonify({"status": "success", "message": "Logged in successfully"})
        else:
            referrer_id = None
            if referral_input:
                ref_user = conn.execute("SELECT id FROM users WHERE referral_code = ?", (referral_input,)).fetchone()
                if ref_user:
                    referrer_id = ref_user["id"]

            new_ref_code = f"USER{uuid.uuid4().hex[:5].upper()}"
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (name, email, phone, password, referral_code, confirmed_balance, pending_balance, referred_by, referral_bonus_given)
                VALUES (?, ?, NULL, NULL, ?, 0.0, 0.0, ?, 0)
            ''', (name, email, new_ref_code, referrer_id))

            new_user_id = cursor.lastrowid
            conn.commit()
            conn.close()

            session["user_id"] = new_user_id
            return jsonify({"status": "success", "message": "Account created successfully"})

    except Exception as e:
        return jsonify({"status": "error", "message": f"Verification failed: {str(e)}"}), 400

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out successfully.", "info")
    return redirect("/login")


# ==============================================================================
# --- MAIN APPLICATION DASHBOARD ---
# ==============================================================================

@app.route("/dashboard")
@app.route("/home")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()

    if not user:
        session.pop("user_id", None)
        return redirect("/login")

    stores = fetch_vcommission_campaigns()
    return render_template("index.html", stores=stores, user=user)

@app.route("/signup")
def signup():
    ref_code = request.args.get("ref", "").strip()
    return redirect(url_for("login", ref=ref_code))

# ==============================================================================
# --- RELIABLE OUTBOUND TRACKING LINK GENERATOR (JSON BASED) ---
# ==============================================================================
@app.route("/go/<path:store_name>")
def outbound_click(store_name):
    if "user_id" not in session:
        return redirect("/login")

    user_id = session.get("user_id")
    sub_id = f"cc_{user_id}_{uuid.uuid4().hex[:8]}"

    # Find store tracking URL from stores.json
    target_url = "https://www.vcommission.com"
    if os.path.exists("stores.json"):
        try:
            with open("stores.json", "r") as f:
                stores = json.load(f)
                for store in stores:
                    if store.get("name", "").strip().lower() == store_name.strip().lower():
                        target_url = store.get("target_url", target_url)
                        break
        except Exception as e:
            print("JSON Click Error:", str(e))

    conn = get_db()
    conn.execute("INSERT INTO click_logs (user_id, store_name, sub_id) VALUES (?, ?, ?)",
                 (user_id, store_name, sub_id))
    conn.commit()
    conn.close()

    # Append subid cleanly
    if "network.vcommission.com" in target_url or "trackier.com" in target_url:
        separator = "&" if "?" in target_url else "?"
        final_url = f"{target_url}{separator}subid={sub_id}"
        return redirect(final_url)
    else:
        encoded_target = urllib.parse.quote(target_url, safe="")
        affiliate_url = f"https://network.vcommission.com/click?aff_id={AFFILIATE_ID}&target={encoded_target}&subid={sub_id}"
        return redirect(affiliate_url)

@app.route("/earnings")
def earnings():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    clicks = conn.execute("SELECT * FROM click_logs WHERE user_id = ? ORDER BY clicked_at DESC LIMIT 10", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("earnings.html", user=user, clicks=clicks)

@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    user_id = session["user_id"]
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", 0))
        except ValueError:
            amount = 0.0

        payout_method = request.form.get("payout_method")
        
        if payout_method == "UPI":
            payment_details = f"UPI: {request.form.get('upi_id', '').strip()}"
        else:
            acc = request.form.get("account_number", "").strip()
            ifsc = request.form.get("ifsc_code", "").strip()
            name = request.form.get("holder_name", "").strip()
            payment_details = f"Name: {name} | A/C: {acc} | IFSC: {ifsc}"

        if amount < MINIMUM_WITHDRAWAL:
            flash(f"Minimum withdrawal amount is ₹{MINIMUM_WITHDRAWAL}.", "error")
            conn.close()
            return redirect("/withdraw")

        if amount > user["confirmed_balance"]:
            flash("Insufficient confirmed balance in your account.", "error")
            conn.close()
            return redirect("/withdraw")

        cursor = conn.cursor()
        cursor.execute("UPDATE users SET confirmed_balance = confirmed_balance - ? WHERE id = ?", (amount, user_id))
        cursor.execute('''
            INSERT INTO payout_requests (user_id, amount, payout_method, payment_details, status)
            VALUES (?, ?, ?, ?, 'PENDING')
        ''', (user_id, amount, payout_method, payment_details))
        conn.commit()
        conn.close()

        flash("Withdrawal request submitted successfully! Amount will be credited within 24 hours.", "success")
        return redirect("/payment-history")

    history = conn.execute("SELECT * FROM payout_requests WHERE user_id = ? ORDER BY requested_at DESC LIMIT 5", (user_id,)).fetchall()
    conn.close()
    return render_template("withdraw.html", user=user, history=history, min_limit=MINIMUM_WITHDRAWAL)

@app.route("/payment-history")
def payment_history():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    user_id = session["user_id"]
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    
    history = conn.execute('''
        SELECT * FROM payout_requests 
        WHERE user_id = ? 
        ORDER BY requested_at DESC
    ''', (user_id,)).fetchall()
    conn.close()
    
    return render_template("history.html", user=user, history=history)

@app.route("/refer")
def refer():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    
    referred_friends = conn.execute('''
        SELECT name, confirmed_balance, referral_bonus_given 
        FROM users 
        WHERE referred_by = ?
    ''', (session["user_id"],)).fetchall()
    conn.close()

    referral_url = f"{request.host_url.rstrip('/')}/login?ref={user['referral_code']}"
    return render_template("refer.html", user=user, referral_url=referral_url, friends=referred_friends)

@app.route("/missing", methods=["GET", "POST"])
def missing():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    if request.method == "POST":
        store_name = request.form.get("store_name", "").strip()
        order_id = request.form.get("order_id", "").strip()
        try:
            amount = float(request.form.get("amount", 0.0))
        except ValueError:
            amount = 0.0

        existing = conn.execute("SELECT id FROM missing_claims WHERE user_id = ? AND order_id = ?", 
                                (session["user_id"], order_id)).fetchone()
        if existing:
            flash("You have already submitted a claim for this Order ID.", "error")
        else:
            conn.execute("INSERT INTO missing_claims (user_id, store_name, order_id, order_amount, status) VALUES (?, ?, ?, ?, 'PENDING')",
                         (session["user_id"], store_name, order_id, amount))
            conn.commit()
            flash("Missing cashback claim submitted successfully! Status is Under Review.", "success")
    
    claims = conn.execute("SELECT * FROM missing_claims WHERE user_id = ? ORDER BY submitted_at DESC", (session["user_id"],)).fetchall()
    stores = fetch_vcommission_campaigns()
    conn.close()
    return render_template("missing.html", claims=claims, stores=stores)

@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("profile.html", user=user)

# ==============================================================================
# --- vCOMMISSION AUTOMATIC POSTBACK / WEBHOOK ---
# ==============================================================================
@app.route("/api/postback", methods=["GET", "POST"])
def affiliate_postback():
    data = request.args if request.method == "GET" else request.form
    
    sub_id = data.get("subid") or data.get("sub_id")
    order_id = data.get("order_id") or data.get("orderid") or "NA"
    status = str(data.get("status", "pending")).strip().lower()
    
    try:
        total_payout = float(data.get("payout") or data.get("commission") or 0.0)
    except ValueError:
        total_payout = 0.0

    if not sub_id or total_payout <= 0:
        return jsonify({"status": "ignored", "message": "Missing subid or zero commission"}), 200

    conn = get_db()

    click = conn.execute("SELECT user_id, store_name FROM click_logs WHERE sub_id = ?", (sub_id,)).fetchone()
    if not click:
        conn.close()
        return jsonify({"status": "error", "message": "Click Sub-ID not found"}), 404

    user_id = click["user_id"]
    user_share = round(total_payout * USER_CASHBACK_PERCENT, 2)
    admin_profit = round(total_payout - user_share, 2)

    duplicate_claim = conn.execute("SELECT id, status FROM missing_claims WHERE order_id = ?", (order_id,)).fetchone()
    if duplicate_claim and str(duplicate_claim["status"]).upper() in ["APPROVED", "CONFIRMED"]:
        conn.close()
        return jsonify({"status": "ignored", "message": "Order already processed manually"}), 200

    if status in ["pending", "tracked"]:
        conn.execute("UPDATE users SET pending_balance = pending_balance + ? WHERE id = ?", (user_share, user_id))
        conn.commit()

    elif status in ["cancelled", "declined", "rejected"]:
        conn.execute("UPDATE users SET pending_balance = MAX(0.0, pending_balance - ?) WHERE id = ?", (user_share, user_id))
        conn.execute("UPDATE missing_claims SET status = 'REJECTED' WHERE order_id = ?", (order_id,))
        conn.commit()

    elif status in ["confirmed", "approved"]:
        conn.execute('''
            UPDATE users 
            SET pending_balance = MAX(0.0, pending_balance - ?),
                confirmed_balance = confirmed_balance + ? 
            WHERE id = ?
        ''', (user_share, user_share, user_id))

        friend = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if friend and friend["confirmed_balance"] >= 50.0 and friend["referral_bonus_given"] == 0 and friend["referred_by"]:
            referrer_id = friend["referred_by"]
            conn.execute("UPDATE users SET confirmed_balance = confirmed_balance + ? WHERE id = ?", 
                         (REFERRAL_BONUS_AMOUNT, referrer_id))
            conn.execute("UPDATE users SET referral_bonus_given = 1 WHERE id = ?", (user_id,))

        conn.commit()

    conn.close()
    return jsonify({
        "status": "success",
        "user_id": user_id,
        "total_commission": total_payout,
        "user_share_40": user_share,
        "admin_profit_60": admin_profit
    }), 200


# ==============================================================================
# --- ADMIN PANEL ROUTES ---
# ==============================================================================

@app.route("/admin/payouts")
def admin_payouts():
    conn = get_db()
    requests_list = conn.execute('''
        SELECT p.*, u.name, u.email, u.phone 
        FROM payout_requests p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.status DESC, p.requested_at ASC
    ''').fetchall()

    claims_list = conn.execute('''
        SELECT c.*, u.name, u.email, u.phone 
        FROM missing_claims c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.submitted_at DESC
    ''').fetchall()

    conn.close()
    return render_template("admin_payouts.html", requests=requests_list, claims=claims_list)

@app.route("/admin/pay-confirm/<int:req_id>", methods=["POST"])
def admin_pay_confirm(req_id):
    utr = request.form.get("utr_number", "MANUAL_PAY").strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    conn.execute('''
        UPDATE payout_requests 
        SET status = 'PAID', utr_number = ?, processed_at = ?
        WHERE id = ?
    ''', (utr, now, req_id))
    conn.commit()
    conn.close()
    flash("Payout confirmed and marked as PAID successfully!", "success")
    return redirect("/admin/payouts")

@app.route("/admin/approve-claim/<int:claim_id>", methods=["POST"])
def admin_approve_claim(claim_id):
    try:
        total_commission = float(request.form.get("total_commission", 0.0))
    except ValueError:
        total_commission = 0.0

    if total_commission <= 0:
        flash("Please enter a valid commission amount greater than 0.", "error")
        return redirect("/admin/payouts")

    user_cashback = round(total_commission * USER_CASHBACK_PERCENT, 2)

    conn = get_db()
    claim = conn.execute("SELECT * FROM missing_claims WHERE id = ?", (claim_id,)).fetchone()
    
    if claim:
        current_status = str(claim["status"]).strip().upper()
        if current_status in ["APPROVED", "CONFIRMED"]:
            flash("Claim has already been approved previously.", "error")
            conn.close()
            return redirect("/admin/payouts")

        user_id = claim["user_id"]
        conn.execute("UPDATE users SET pending_balance = pending_balance + ? WHERE id = ?", (user_cashback, user_id))
        conn.execute("UPDATE missing_claims SET status = 'APPROVED' WHERE id = ?", (claim_id,))
        conn.commit()
        flash(f"Claim #{claim_id} Tracked! ₹{user_cashback} (40%) added to User PENDING balance.", "success")
    else:
        flash("Claim not found.", "error")

    conn.close()
    return redirect("/admin/payouts")

@app.route("/admin/confirm-claim/<int:claim_id>", methods=["POST"])
def admin_confirm_claim(claim_id):
    try:
        cashback_amount = float(request.form.get("cashback_amount", 0.0))
    except ValueError:
        cashback_amount = 0.0

    conn = get_db()
    claim = conn.execute("SELECT * FROM missing_claims WHERE id = ?", (claim_id,)).fetchone()

    if claim and str(claim["status"]).strip().upper() == "APPROVED":
        user_id = claim["user_id"]

        conn.execute("UPDATE users SET pending_balance = MAX(0.0, pending_balance - ?), confirmed_balance = confirmed_balance + ? WHERE id = ?",
                     (cashback_amount, cashback_amount, user_id))
        conn.execute("UPDATE missing_claims SET status = 'CONFIRMED' WHERE id = ?", (claim_id,))

        friend = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if friend and friend["confirmed_balance"] >= 50.0 and friend["referral_bonus_given"] == 0 and friend["referred_by"]:
            referrer_id = friend["referred_by"]
            conn.execute("UPDATE users SET confirmed_balance = confirmed_balance + ? WHERE id = ?", 
                         (REFERRAL_BONUS_AMOUNT, referrer_id))
            conn.execute("UPDATE users SET referral_bonus_given = 1 WHERE id = ?", (user_id,))

        conn.commit()
        flash("Cashback approved and referral reward processed successfully!", "success")
    else:
        flash("Claim not eligible for confirmation.", "error")

    conn.close()
    return redirect("/admin/payouts")

@app.route("/admin/update-support", methods=["POST"])
def update_support():
    whatsapp = request.form.get("support_whatsapp", "").strip()

    conn = get_db()
    conn.execute("UPDATE app_settings SET value = ? WHERE key = 'support_whatsapp'", (whatsapp,))
    conn.commit()
    conn.close()

    flash("WhatsApp support number updated successfully!", "success")
    return redirect("/admin/payouts")

# ==============================================================================
# --- LEGAL ROUTES ---
# ==============================================================================

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy-policy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/auth/google/callback')
def google_callback():
    token = request.args.get('id_token')
    
    if not token:
        return "Google Sign-In Error: ID Token missing!", 400
    
    try:
        id_info = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        email = id_info.get("email")
        name = id_info.get("name") or (email.split("@")[0] if email else "User")

        if not email:
            return "Google did not provide an email", 400

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user:
            session["user_id"] = user["id"]
        else:
            new_ref_code = f"USER{uuid.uuid4().hex[:5].upper()}"
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (name, email, phone, password, referral_code, confirmed_balance, pending_balance, referred_by, referral_bonus_given)
                VALUES (?, ?, NULL, NULL, ?, 0.0, 0.0, NULL, 0)
            ''', (name, email, new_ref_code))
            
            new_user_id = cursor.lastrowid
            conn.commit()
            session["user_id"] = new_user_id

        conn.close()
        
        return redirect("/dashboard")

    except Exception as e:
        return f"Verification failed: {str(e)}", 400
        
if __name__ == "__main__":
    app.run(debug=True)
