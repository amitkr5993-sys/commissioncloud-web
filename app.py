import logging
import os
import re
import secrets
import sqlite3
from dotenv import load_dotenv
from flask import Flask, request, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# recharge फोल्डर से ब्लूप्रिंट इम्पोर्ट करें
from recharge.recharge import recharge_bp

logger = logging.getLogger("recharge.app")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

ORDERS_DB_PATH = os.path.join(BASE_DIR, "recharge", "recharge_orders.db")


def get_orders_conn():
    conn = sqlite3.connect(ORDERS_DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def extract_plan_amount_from_text(plan_text: str) -> float:
    text = plan_text or ""
    m = re.search(r"(?:₹|rs\.?|inr)\s*([0-9]+(?:\.[0-9]{1,2})?)", text, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\b([0-9]{1,5}(?:\.[0-9]{1,2})?)\s*(?:\/-|\/[0-9]+\s*d)", text, flags=re.IGNORECASE)
    if m:
        try:
            val = round(float(m.group(1)), 2)
            return val if val > 0 else 0.0
        except ValueError:
            return 0.0
    return 0.0


# ऑपरेटर एपीआई
@app.route('/get-operators')
def get_operators():
    service_type = (request.args.get('service_type') or 'Mobile Prepaid').strip()
    op_list = []

    if 'Mobile' in service_type or 'Prepaid' in service_type:
        conn = None
        try:
            conn = get_orders_conn()
            c = conn.cursor()
            c.execute(
                """SELECT DISTINCT operator FROM operator_plans
                   WHERE LOWER(operator) IN ('jio', 'airtel', 'vi', 'bsnl', 'bsnl combo', 'bsnl topup', 'bsnl_stv')"""
            )
            rows = c.fetchall()
            op_list = [r[0] for r in rows if r[0]]
        except Exception:
            logger.exception("Failed to fetch operators")
            op_list = []
        finally:
            if conn:
                conn.close()

        if not op_list:
            op_list = ["Jio", "Airtel", "Vi", "BSNL Combo", "BSNL Topup"]

    return jsonify(op_list)


@app.route('/get-plans')
def get_plans():
    operator = (request.args.get('operator') or 'Jio').strip()
    plans_list = []
    conn = None

    try:
        conn = get_orders_conn()
        c = conn.cursor()
        if operator.lower().startswith("bsnl"):
            c.execute("SELECT * FROM operator_plans WHERE LOWER(operator) LIKE 'bsnl%' ORDER BY id DESC")
        else:
            c.execute("SELECT * FROM operator_plans WHERE LOWER(operator) = LOWER(?) ORDER BY id DESC", (operator,))
        rows = c.fetchall()

        for r in rows:
            plan_txt = r['plan_text'] or ""
            plans_list.append({
                'id': r['id'],
                'operator': r['operator'],
                'circle': 'Bihar',
                'category': r['category'],
                'amount': extract_plan_amount_from_text(plan_txt),
                'validity': 'NA',
                'data_limit': 'NA',
                'sms_limit': 'NA',
                'description': plan_txt
            })
    except Exception:
        logger.exception("Failed to fetch plans for operator %s", operator)
        plans_list = []
    finally:
        if conn:
            conn.close()

    return jsonify(plans_list)


app.register_blueprint(recharge_bp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    is_debug = os.getenv("FLASK_DEBUG", "0").strip() == "1"
    app.run(host="0.0.0.0", debug=is_debug, port=port)