import os
import uuid
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, request, redirect, jsonify, session, flash, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from models import init_db, get_db
from vcommission import get_all_campaigns
from affiliate_links import AFFILIATE_STORES, get_active_stores
from commission_earning import (
    ensure_earning_tables,
    create_and_log_click,
    build_tracked_url,
    get_user_from_click,
    get_active_recent_clicks,
    record_commission_event,
    get_user_earning_summary,
)

app = Flask(__name__)
app.secret_key = "commission_cloud_secret_key_production"

init_db()
_init_conn = get_db()
ensure_earning_tables(_init_conn)
_init_conn.close()

# Google Cloud OAuth Client ID
GOOGLE_CLIENT_ID = "425959144248-1774ja2dr8ddje1sqe17tg412c93qoom.apps.googleusercontent.com"

MINIMUM_WITHDRAWAL = 200.0  # Minimum withdrawal limit in INR
REFERRAL_BONUS_AMOUNT = 25.0  # First-time referral bonus in INR (deducted from admin's share)
USER_CASHBACK_PERCENT = 0.50  # 50% User Share, 50% Admin Share


def get_all_claimable_stores():
    """Return all configured affiliate stores + live vCommission stores without duplicates."""
    seen = set()
    store_list = []

    for item in AFFILIATE_STORES:
        name = str(item.get("name") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            store_list.append({"name": name})

    try:
        vc_campaigns = get_all_campaigns() or []
        for camp in vc_campaigns:
            name = str(camp.get("name") or "").strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                store_list.append({"name": name})
    except Exception as e:
        print(f"vCommission API Fetch Error in store list: {e}")

    return store_list


# Context processor for global app settings
@app.context_processor
def inject_settings():
    conn = get_db()
    settings_rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    settings_dict = {row["key"]: row["value"] for row in settings_rows}
    return dict(app_settings=settings_dict)

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
# --- AUTHENTICATION ROUTES (Google + Email + Phone + Auto Referral) ---
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

        # 1. Instant Email Login Flow (No Password Needed)
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

        # 2. Phone + Password Flow
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
# --- MAIN APPLICATION DASHBOARD (AFFILIATE LINKS + vCOMMISSION API) ---
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

    stores = []

    # 1. affiliate_links.py से केवल उन्हीं स्टोर्स को जोड़ें जिनमें URL मौजूद हो, और उनका ऑटो-लोगो पास करें
    for item in get_active_stores():
        raw_url = str(item.get("url") or "").strip()
        if not raw_url:
            continue
        encoded_url = urllib.parse.quote(raw_url, safe="")
        encoded_store = urllib.parse.quote(item["name"], safe="")
        stores.append({
            "name": item["name"],
            "badge": item.get("badge", "Active Link"),
            "cashback_rate": "Up to 7% commission",
            "link": f"/redirect?store={encoded_store}&url={encoded_url}",
            "url": raw_url,
            "logo": item.get("logo", ""),
        })

    # 2. vCommission API से लाइव ब्रांड्स फेच करें
    try:
        vc_campaigns = get_all_campaigns()
        if vc_campaigns:
            for camp in vc_campaigns:
                camp_link = str(camp.get("link") or "").strip()
                if not camp_link:
                    continue
                encoded_url = urllib.parse.quote(camp_link, safe="")
                encoded_store = urllib.parse.quote(camp["name"], safe="")
                stores.append({
                    "name": camp["name"],
                    "badge": "Live API",
                    "cashback_rate": "Up to 7% commission",
                    "link": f"/redirect?store={encoded_store}&url={encoded_url}",
                    "url": camp_link,
                    "logo": camp.get("logo", ""),
                })
    except Exception as e:
        print(f"vCommission API Fetch Error: {e}")

    return render_template("index.html", stores=stores, user=user)

@app.route("/signup")
def signup():
    ref_code = request.args.get("ref", "").strip()
    return redirect(url_for("login", ref=ref_code))

@app.route("/redirect")
def redirect_link():
    if "user_id" not in session:
        return redirect("/login")

    target_url = (request.args.get("url") or "").strip()
    store_name = (request.args.get("store") or "Store").strip()

    if not target_url.startswith(("http://", "https://")):
        return "Invalid Link", 400

    conn = get_db()
    try:
        sub_id = create_and_log_click(conn, int(session["user_id"]), store_name, target_url)
    finally:
        conn.close()

    if not sub_id:
        return "Tracking Sub-ID failed. Please try again.", 500

    final_url = build_tracked_url(target_url, sub_id)
    return redirect(final_url)

@app.route("/earnings")
def earnings():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    clicks = get_active_recent_clicks(conn, int(session["user_id"]), limit=10)
    summary = get_user_earning_summary(conn, session["user_id"])
    conn.close()

    return render_template(
        "earnings.html",
        user=user,
        clicks=clicks,
        earning_summary=summary,
    )

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
        cursor.execute("UPDATE users SET confirmed_balance = ROUND(confirmed_balance - ?, 2) WHERE id = ?", (amount, user_id))
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
        store_name = (request.form.get("store_name") or "").strip()
        order_id = (request.form.get("order_id") or "").strip().upper()
        try:
            amount = float(request.form.get("amount", 0.0))
        except ValueError:
            amount = 0.0

        if not store_name:
            flash("Please select a store from the list.", "error")
        elif not order_id:
            flash("Please enter a valid Order ID.", "error")
        elif amount <= 0:
            flash("Please enter a valid order amount greater than 0.", "error")
        else:
            existing = conn.execute(
                "SELECT id FROM missing_claims WHERE user_id = ? AND UPPER(order_id) = ?",
                (session["user_id"], order_id),
            ).fetchone()
            if existing:
                flash("You have already submitted a claim for this Order ID.", "error")
            else:
                conn.execute(
                    "INSERT INTO missing_claims (user_id, store_name, order_id, order_amount, status) VALUES (?, ?, ?, ?, 'PENDING')",
                    (session["user_id"], store_name, order_id, amount),
                )
                conn.commit()
                flash("Missing cashback claim submitted successfully! Status is Under Review.", "success")

    claims = conn.execute(
        "SELECT * FROM missing_claims WHERE user_id = ? ORDER BY submitted_at DESC",
        (session["user_id"],),
    ).fetchall()
    conn.close()

    stores = get_all_claimable_stores()
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
# --- AUTOMATIC POSTBACK / WEBHOOK (Single Source: commission_earning.py) ---
# ==============================================================================
@app.route("/api/postback", methods=["GET", "POST"])
def affiliate_postback():
    data = request.args if request.method == "GET" else request.form

    sub_id = (data.get("subid") or data.get("sub_id") or "").strip()
    order_id = (data.get("order_id") or data.get("orderid") or "").strip().upper()
    status = str(data.get("status", "pending")).strip()

    try:
        total_payout = float(data.get("payout") or data.get("commission") or 0.0)
    except ValueError:
        total_payout = 0.0

    if not order_id:
        return jsonify({"status": "ignored", "message": "Missing order_id"}), 200

    conn = get_db()
    click = get_user_from_click(conn, sub_id) if sub_id else None

    if click:
        user_id = click["user_id"]
        store_name = click["store_name"]
    else:
        existing_order = conn.execute(
            "SELECT user_id, store_name, total_commission FROM affiliate_commissions WHERE UPPER(order_id) = ?",
            (order_id,),
        ).fetchone()
        if not existing_order:
            conn.close()
            return jsonify({"status": "error", "message": "Click Sub-ID or Order not found"}), 404
        user_id = existing_order["user_id"]
        store_name = existing_order["store_name"]
        if total_payout <= 0:
            total_payout = float(existing_order["total_commission"])

    result = record_commission_event(
        conn=conn,
        order_id=order_id,
        user_id=user_id,
        total_commission=total_payout,
        event_status=status,
        store_name=store_name,
        sub_id=sub_id,
    )

    if not result.get("ok"):
        conn.close()
        return jsonify({"status": "error", "message": result.get("error", "Failed")}), 400

    if result.get("status") == "CANCELLED":
        conn.execute("UPDATE missing_claims SET status = 'REJECTED' WHERE UPPER(order_id) = ?", (order_id,))

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "order_id": order_id,
        "user_id": user_id,
        "store_name": store_name,
        "order_status": result.get("status"),
        "user_share_50": result.get("user_share"),
        "admin_profit_50": result.get("admin_share"),
        "referrer_bonus": result.get("referrer_bonus", 0.0),
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

@app.route("/admin/order-status", methods=["POST"])
def admin_order_status():
    order_id = (request.form.get("order_id") or "").strip().upper()
    user_id = request.form.get("user_id", type=int)
    new_status = (request.form.get("status") or "").strip()
    store_name = (request.form.get("store_name") or "").strip()

    try:
        total_commission = float(request.form.get("total_commission") or 0.0)
    except ValueError:
        total_commission = 0.0

    conn = get_db()
    if not user_id and order_id:
        row = conn.execute(
            "SELECT user_id, store_name, total_commission FROM affiliate_commissions WHERE UPPER(order_id) = ?",
            (order_id,),
        ).fetchone()
        if row:
            user_id = row["user_id"]
            if not store_name:
                store_name = row["store_name"]
            if total_commission <= 0:
                total_commission = float(row["total_commission"])

    result = record_commission_event(
        conn=conn,
        order_id=order_id,
        user_id=user_id,
        total_commission=total_commission,
        event_status=new_status,
        store_name=store_name,
    )

    if not result.get("ok"):
        conn.close()
        flash(result.get("error", "Status update failed."), "error")
        return redirect("/admin/payouts")

    if result.get("status") == "CANCELLED":
        conn.execute("UPDATE missing_claims SET status = 'REJECTED' WHERE UPPER(order_id) = ?", (order_id,))

    conn.commit()
    conn.close()
    flash(f"Order {order_id} updated to {result.get('status')}.", "success")
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
        conn.execute("UPDATE users SET pending_balance = ROUND(pending_balance + ?, 2) WHERE id = ?", (user_cashback, user_id))
        conn.execute("UPDATE missing_claims SET status = 'APPROVED' WHERE id = ?", (claim_id,))
        conn.commit()
        flash(f"Claim #{claim_id} Tracked! ₹{user_cashback} added to User PENDING balance.", "success")
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
        user_share = round(cashback_amount * USER_CASHBACK_PERCENT, 2) if cashback_amount > 0 else 0.0

        conn.execute(
            "UPDATE users SET pending_balance = MAX(0.0, ROUND(pending_balance - ?, 2)), confirmed_balance = ROUND(confirmed_balance + ?, 2) WHERE id = ?",
            (user_share, user_share, user_id),
        )
        conn.execute("UPDATE missing_claims SET status = 'CONFIRMED' WHERE id = ?", (claim_id,))
        conn.commit()
        flash("Cashback approved and confirmed successfully!", "success")
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
