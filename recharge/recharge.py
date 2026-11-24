import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
from decimal import Decimal
import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify

from .wallet import (
    q_money,
    get_wallet_balance,
    add_cashback_to_wallet,
    deduct_wallet_for_recharge,
    get_wallet_transactions
)

logger = logging.getLogger("commissioncloud.recharge")
recharge_bp = Blueprint('recharge_bp', __name__, template_folder='templates')

PAYMENT_GATEWAY_URL = os.getenv("PAYMENT_GATEWAY_URL", "https://upi-geteway-s19b.onrender.com").strip().rstrip("/")
SMS_GATEWAY_KEY = os.getenv("SMS_GATEWAY_KEY", "").strip()
ADMIN_ACCESS_KEY = os.getenv("ADMIN_ACCESS_KEY", "").strip()
A1_CALLBACK_SECRET = os.getenv("A1_CALLBACK_SECRET", "").strip()
ALLOW_MANUAL_UTR_AUTO_RECHARGE = os.getenv("ALLOW_MANUAL_UTR_AUTO_RECHARGE", "0").strip() == "1"

A1_API_TOKEN = os.getenv("A1TOPUP_TOKEN", "").strip()
A1_MODE = os.getenv("A1TOPUP_MODE", "sandbox").strip().lower()

A1_BASE_URL = (
    "https://business.a1topup.com/recharge/api"
    if A1_MODE == "live"
    else "https://business.a1topup.com/sandbox/api"
)

A1_STATUS_URL = (
    "https://business.a1topup.com/recharge/status"
    if A1_MODE == "live"
    else "https://business.a1topup.com/sandbox/status"
)

ORDERS_DB_PATH = os.path.join(os.path.dirname(__file__), "recharge_orders.db")
TWO_PLACES = Decimal("0.01")

CASHBACK_RATES = {
    "Jio": 0.80,
    "Airtel": 1.00,
    "Vi": 2.00,
    "BSNL": 2.00,
    "BSNL Combo": 2.00,
    "BSNL Topup": 2.00,
    "BSNL_STV": 2.00,
    "DTH": 1.50,
    "Electricity": 0.25,
    "Gas": 0.25,
    "FASTag": 0.25,
}
CASHBACK_RATES_LOWER = {k.lower(): Decimal(str(v)) for k, v in CASHBACK_RATES.items()}

A1_OPERATOR_CODES = {
    "Airtel": "A",
    "BSNL - STV": "BR",
    "BSNL Combo": "BR",
    "BSNL_STV": "BR",
    "BSNL": "BR",
    "BSNL - TOPUP": "BT",
    "BSNL Topup": "BT",
    "Idea": "I",
    "RELIANCE - JIO": "RC",
    "Jio": "RC",
    "Vodafone": "V",
    "Vi": "V",
    "Airtel Digital DTH TV": "ATV",
    "Airtel DTH": "ATV",
    "DISH TV": "DTV",
    "Dish TV": "DTV",
    "SUNDIRECT DTH TV": "STV",
    "Sun Direct": "STV",
    "TATASKY DTH TV": "TTV",
    "Tata Play": "TTV",
    "VIDEOCON DTH TV": "VTV",
    "Videocon d2h": "VTV",
    "Adani power": "AEML",
    "Ajmer Vidyut Vitran Nigam - RAJASTHAN": "AJV",
    "APDCL (Non-RAPDR) - ASSAM": "APDCLN",
    "APEPDCL - ANDHRA PRADESH": "APEPDCL",
    "Assam Power Distribution Company Ltd (RAPDR)": "APDCLR",
    "Bangalore ElectricitySupply Company": "BESCOM",
    "BEST Mumbai": "BEST",
    "BharatpurElectricityServicesLtd": "BHES",
    "Bikaner Electricity Supply Limited": "BESL",
    "BrihanMumbaiElectricSupplyandTransportUndertaking": "BMESTU",
    "BSES Rajdhani Power Limited - Delhi": "BSES",
    "BSES Yamuna Power Limited - Delhi": "BSESY",
    "Central Power Distribution Company of Andhra Pradesh Ltd": "APCPDCL",
    "CESC - WEST BENGAL": "CESC",
    "Chamundeshwari Electricity Supply Corporation Ltd. (Cesc,Mysore)": "CESCOM",
    "Chhattisgarh State Power Distribution Company Ltd. (CSPDCL)": "CSPDCL",
    "Dakshin Gujarat Vij Company Ltd": "DGVCL",
    "DakshinHaryanaBijliVitranNigam": "DHBVN",
    "Department of Power Arunachal Pradesh": "ARPDOP",
    "Department of Power, Nagaland": "NDOP",
    "DNHPowerDistributionCompanyLimited": "DDCL",
    "Gift Power Company Limited": "GPCL",
    "Goa Electricity": "GOAELC",
    "Government of Puducherry Electricity Department": "PGPED",
    "GulbargaElectricitySupplyCompanyLimited": "GESCL",
    "Himachal Pradesh State Electricity Board Ltd": "HPSEBL",
    "Hubli Electricity Supply Company Ltd. (HESCOM)": "HESCOM",
    "India Power - WEST BENGAL": "IPWB",
    "IndiaPowerCorporationLimited": "IPCL",
    "Jaipur Vidyut Vitran Nigam - RAJASTHAN": "JVV",
    "Jammu & Kashmir power Development department": "JKPDD",
    "JamshedpurUtilitiesandServicesCompanyLimited": "JUSCL",
    "JBVNL - JHARKHAND": "JBVNL",
    "Jodhpur Vidyut Vitran Nigam - RAJASTHAN": "JDVV",
    "kannan devan hills power": "KDHPCPL",
    "Kanpur Electricity Supply Company": "KESCO",
    "KEDL - KOTA": "KEDL",
    "Kerala State Electricity Board Ltd.": "KSEB",
    "Lakshadweep Electricity Department": "LED",
    "Madhya Gujarat Vij Company Ltd": "MGVCL",
    "Madhya Pradesh Madhya Kshetra Vidyut Vitaran-RURAL": "MPPKVVCLMR",
    "Madhya Pradesh Poorv Kshetra Vidyut Vitaran-URBAN": "MPPKVVCL",
    "Madhyanchal Vidyut Vitran Nigam Limited": "MVVNL",
    "Mangalore Electricity Supply Co. Ltd (MESCOM) - RAPDR": "MESCOMR",
    "Mangalore Electricity Supply Co. Ltd (Non) - RAPDR": "MESCOMNR",
    "Manipur State Power Distribution Company Limited (Prepaid)": "MSPDCLPR",
    "MEPDCL - MEGHALAYA": "MEPDCL",
    "MP Madhaya Kshetra Vidyut Vitaran -Urban": "MKV",
    "MP Poorv Kshetra Vidyut Vitaran - Jabalpur": "MPPKVVCLPU",
    "MP Poorv Kshetra Vidyut Vitaran - Rular": "MPPKVVCLPU",
    "MSEDC - MAHARASHTRA": "MSEDC",
    "MUNICIPALCORPORATIONOFGURUGRAM": "MCG",
    "Muzaffarpur Vidyut Vitran": "MVV",
    "NESCO Odisha": "NESCO",
    "New Delhi Municipal Council (NDMC) - Electricity": "NDMC",
    "Noida Power - NOIDA": "NP",
    "North Bihar Electricity": "NBE",
    "NorthDelhiPowerLimited": "NDPL",
    "Paschim Gujarat Vij Company Ltd": "PGVCL",
    "Paschim Kshetra Vidyut Vitaran - MADHYA PRADESH": "PKV",
    "Power & Electricity Department - Mizoram": "MPED",
    "Punjab State Power Corporation Limted": "PSPCL",
    "Reliance Energy": "RELIANCE",
    "Sikkim Power Rural": "SPR",
    "Sikkim Power Urban": "SPU",
    "SNDL Power - NAGPUR": "SNDL",
    "South Bihar Electricity": "SBE",
    "SOUTHCO Odisha": "SOUTHCO",
    "Southern Power - ANDHRA PRADESH": "SPA",
    "Southern Power - TELANGANA": "SPT",
    "Tata Power - MUMBAI": "TPDM",
    "Tata Power Delhi Limited - Delhi": "TPD",
    "TNEB - TAMIL NADU": "TNEB",
    "Torrent Power agra": "TRP",
    "Torrent Power Ahemdabad": "TORRENTAHM",
    "Torrent Power Bhivandi": "TORRENTBHI",
    "Torrent Power Dahej": "TORRENTDAH",
    "Torrent Power SHIL": "TORRENTSHI",
    "Torrent Power Surat": "TORRENTSUR",
    "TP Ajmer Distribution Ltd": "TPADL",
    "TP central odisha distribution limited": "TPCODL",
    "TripuraStateElectricityCorporationLtd": "TSECL",
    "TSNPDCL Telangana northern power": "TSNPDCL",
    "UPPCL (URBAN) - UTTAR PRADESH": "UPPCLU",
    "Uttar Pradesh Power Corporation Limited(Rular)": "UPPCLR",
    "UttarakhandPowerCorporationLimited": "UKPCL",
    "UttarGujarat Vij Company Ltd": "UGVCL",
    "UttarHaryanaBijliVitranNigam": "UHBV",
    "WBSEDCL - WEST BENGAL": "WBSEDCL",
    "Western Electricity supply co. Of orissa ltd.": "WESCO",
    "Adani Gas": "AG",
    "Gujarat Gas": "GG",
    "Hindustan Petroleum Corporation Ltd": "HPCLGC",
    "Indraprastha Gas": "IG",
    "Mahanagar Gas": "MG",
    "Airtel Payments Bank": "APB",
    "Axis Bank Fastag": "AXF",
    "Bank Of Baroda - Fastag": "BBF",
    "Equitas Fastag Recharge": "EFF",
    "Federal Bank - Fastag": "FDF",
    "Hdfc Bank - Fastag": "HDF",
    "Icici Bank Fastag": "ICF",
    "Idbi Bank Fastag": "IBF",
    "Idfc First Bank- Fastag": "IFF",
    "Indian Highways Management Company Ltd Fastag": "IHMCF",
    "Indusind Bank Fastag": "INDF",
    "Jammu And Kashmir Bank Fastag": "JKF",
    "Kotak Mahindra Bank - Fastag": "KMF",
    "Paul Merchants": "PMF",
    "Paytm Payments Bank Fastag": "PTF",
    "Sbi Bank Fastag": "SBF",
}

MOBILE_OPERATORS = {
    "Airtel", "BSNL - STV", "BSNL Combo", "BSNL_STV", "BSNL",
    "BSNL - TOPUP", "BSNL Topup", "Idea", "RELIANCE - JIO", "Jio",
    "Vodafone", "Vi"
}

BILLER_LISTS_BY_TYPE = {
    "DTH": [
        "Airtel Digital DTH TV",
        "DISH TV",
        "SUNDIRECT DTH TV",
        "TATASKY DTH TV",
        "VIDEOCON DTH TV",
    ],
    "Electricity": [k for k in A1_OPERATOR_CODES.keys() if k not in {
        *MOBILE_OPERATORS,
        "Airtel Digital DTH TV", "Airtel DTH", "DISH TV",
        "Dish TV", "SUNDIRECT DTH TV", "Sun Direct", "TATASKY DTH TV",
        "Tata Play", "VIDEOCON DTH TV", "Videocon d2h",
        "Adani Gas", "Gujarat Gas", "Hindustan Petroleum Corporation Ltd",
        "Indraprastha Gas", "Mahanagar Gas",
        "Airtel Payments Bank", "Axis Bank Fastag", "Bank Of Baroda - Fastag",
        "Equitas Fastag Recharge", "Federal Bank - Fastag", "Hdfc Bank - Fastag",
        "Icici Bank Fastag", "Idbi Bank Fastag", "Idfc First Bank- Fastag",
        "Indian Highways Management Company Ltd Fastag", "Indusind Bank Fastag",
        "Jammu And Kashmir Bank Fastag", "Kotak Mahindra Bank - Fastag",
        "Paul Merchants", "Paytm Payments Bank Fastag", "Sbi Bank Fastag",
    }],
    "Gas": [
        "Adani Gas",
        "Gujarat Gas",
        "Hindustan Petroleum Corporation Ltd",
        "Indraprastha Gas",
        "Mahanagar Gas",
    ],
    "FASTag": [
        "Airtel Payments Bank",
        "Axis Bank Fastag",
        "Bank Of Baroda - Fastag",
        "Equitas Fastag Recharge",
        "Federal Bank - Fastag",
        "Hdfc Bank - Fastag",
        "Icici Bank Fastag",
        "Idbi Bank Fastag",
        "Idfc First Bank- Fastag",
        "Indian Highways Management Company Ltd Fastag",
        "Indusind Bank Fastag",
        "Jammu And Kashmir Bank Fastag",
        "Kotak Mahindra Bank - Fastag",
        "Paul Merchants",
        "Paytm Payments Bank Fastag",
        "Sbi Bank Fastag",
    ],
}

VALID_A1_CODES = {code.upper(): code for code in A1_OPERATOR_CODES.values()}

TERMINAL_OR_INFLIGHT_STATUSES = (
    'PROCESSING_RECHARGE',
    'RECHARGE_SUCCESS',
    'RECHARGE_PENDING',
    'RECHARGE_FAILED',
    'REFUNDED',
)

DEBIT_KEYWORDS = (
    "debited", "debit", "spent", "withdrawn", "purchase",
    "नामे", "निकासी", "निकाले", "खर्च"
)


def get_db_conn(readonly: bool = False):
    if readonly and os.path.exists(ORDERS_DB_PATH):
        uri = f"file:{os.path.abspath(ORDERS_DB_PATH)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0, check_same_thread=False)
    else:
        conn = sqlite3.connect(ORDERS_DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    if not readonly:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def clean_input_value(val):
    return (val or "").replace("#", "").strip()


def get_csrf_token() -> str:
    if "_cc_csrf" not in session:
        session["_cc_csrf"] = secrets.token_hex(24)
    return session["_cc_csrf"]


def verify_csrf_token() -> bool:
    expected = session.get("_cc_csrf", "")
    provided = clean_input_value(
        request.headers.get("X-CSRF-Token", "")
        or request.form.get("csrf_token", "")
    )
    return bool(expected and provided and secrets.compare_digest(expected, provided))


def is_admin_authorized() -> bool:
    if not ADMIN_ACCESS_KEY:
        return True
    if session.get("is_cc_admin") is True:
        return True
    provided = clean_input_value(
        request.headers.get("X-Admin-Key", "")
        or request.form.get("admin_key", "")
        or request.args.get("admin_key", "")
    )
    if provided and secrets.compare_digest(provided, ADMIN_ACCESS_KEY):
        session["is_cc_admin"] = True
        return True
    return False


def verify_callback_signature(order_id: str, cb_status: str, opid: str) -> bool:
    if not A1_CALLBACK_SECRET:
        return True
    provided_secret = clean_input_value(
        request.args.get("secret", "")
        or request.form.get("secret", "")
        or request.headers.get("X-Callback-Secret", "")
    )
    if provided_secret and secrets.compare_digest(provided_secret, A1_CALLBACK_SECRET):
        return True
    provided_sig = clean_input_value(
        request.args.get("sig", "")
        or request.form.get("sig", "")
        or request.headers.get("X-Callback-Signature", "")
    ).lower()
    if provided_sig:
        msg = f"{order_id}:{cb_status}:{opid}".encode("utf-8")
        expected_sig = hmac.new(A1_CALLBACK_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest().lower()
        return secrets.compare_digest(provided_sig, expected_sig)
    return False


def log_admin_action(conn, action: str, order_id: str, user_id: str, amount, note: str):
    c = conn.cursor()
    c.execute(
        """INSERT INTO admin_audit_logs (action, order_id, user_id, amount, note, ip_addr)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (action, order_id, user_id, float(q_money(amount)), str(note or "")[:300], request.remote_addr or "")
    )


def get_cashback_rate(operator: str, service_type: str) -> float:
    op_low = clean_input_value(operator).lower()
    svc_low = clean_input_value(service_type).lower()
    if op_low in CASHBACK_RATES_LOWER:
        return float(CASHBACK_RATES_LOWER[op_low])
    if "bsnl" in op_low:
        return 2.00
    if "dth" in op_low or svc_low == "dth":
        return 1.50
    if "electricity" in op_low or svc_low == "electricity":
        return 0.25
    if "gas" in op_low or svc_low == "gas":
        return 0.25
    if "fastag" in op_low or svc_low == "fastag":
        return 0.25
    return float(CASHBACK_RATES_LOWER.get(svc_low, Decimal("0.50")))


def validate_service_and_number(service_type: str, operator: str, number: str):
    svc_low = clean_input_value(service_type).lower()
    op_clean = clean_input_value(operator)
    num_clean = clean_input_value(number)

    if not op_clean or not num_clean:
        return False, "ऑपरेटर और नंबर/कंज्यूमर आईडी अनिवार्य है।"

    if "mobile" in svc_low or "prepaid" in svc_low:
        if op_clean not in MOBILE_OPERATORS and op_clean.lower() not in {m.lower() for m in MOBILE_OPERATORS}:
            return False, "मोबाइल रिचार्ज के लिए सही मोबाइल ऑपरेटर चुनें।"
        if not re.fullmatch(r"[6-9][0-9]{9}", num_clean):
            return False, "कृपया 10 अंकों का सही मोबाइल नंबर दर्ज करें।"
    elif svc_low == "dth":
        if op_clean not in BILLER_LISTS_BY_TYPE["DTH"]:
            return False, "कृपया सही DTH ऑपरेटर चुनें।"
        if not re.fullmatch(r"[A-Za-z0-9-]{5,22}", num_clean):
            return False, "कृपया सही DTH सब्सक्राइबर/VC नंबर दर्ज करें।"
    elif svc_low == "electricity":
        if op_clean not in BILLER_LISTS_BY_TYPE["Electricity"]:
            return False, "कृपया सही Electricity बोर्ड चुनें।"
        if not re.fullmatch(r"[A-Za-z0-9/.-]{4,28}", num_clean):
            return False, "कृपया सही कंज्यूमर नंबर दर्ज करें।"
    elif svc_low == "gas":
        if op_clean not in BILLER_LISTS_BY_TYPE["Gas"]:
            return False, "कृपया सही Gas प्रदाता चुनें।"
        if not re.fullmatch(r"[A-Za-z0-9/.-]{4,28}", num_clean):
            return False, "कृपया सही Gas कंज्यूमर आईडी दर्ज करें।"
    elif svc_low == "fastag":
        if op_clean not in BILLER_LISTS_BY_TYPE["FASTag"]:
            return False, "कृपया सही FASTag बैंक चुनें।"
        if not re.fullmatch(r"[A-Za-z0-9-]{4,22}", num_clean):
            return False, "कृपया सही गाड़ी नंबर या FASTag ID दर्ज करें।"

    return True, ""


def resolve_a1_operator_code(operator_name, plan_hint=""):
    op_clean = clean_input_value(operator_name)
    op_lower = op_clean.lower()
    hint_lower = clean_input_value(plan_hint).lower()

    if not op_clean:
        return ""

    if op_clean.upper() in VALID_A1_CODES:
        return VALID_A1_CODES[op_clean.upper()]

    if "bsnl" in op_lower:
        if "topup" in op_lower or "top-up" in op_lower or "topup" in hint_lower or "talktime" in hint_lower:
            return "BT"
        return "BR"

    if op_clean in A1_OPERATOR_CODES:
        return A1_OPERATOR_CODES[op_clean]

    for key, code in A1_OPERATOR_CODES.items():
        if key.lower() == op_lower:
            return code

    return op_clean


def is_debit_only_message(message_text: str) -> bool:
    low = (message_text or "").lower()
    has_credit_hint = any(k in low for k in ("credited", "received", "credit", "प्राप्त", "जमा"))
    has_debit_hint = any(k in low for k in DEBIT_KEYWORDS)
    return has_debit_hint and not has_credit_hint


def extract_amount_and_txid_from_message(message_text: str):
    text = (message_text or "").strip()
    amount = None
    txid = ""

    primary_amt_patterns = [
        r"(?:credited|received|paid|sent|प्राप्त|जमा)\s*(?:with|by|of|हुए|हुआ)?\s*(?:rs\.?|inr|₹|रु\.?|रुपये|रुपए)?\s*([0-9]+(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?)",
        r"(?:rs\.?|inr|₹|रु\.?|रुपये|रुपए)\s*([0-9]+(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?)\s*(?:is\s*)?(?:credited|received|paid|sent|प्राप्त|जमा)",
        r"(?:rs\.?|inr|₹|रु\.?|रुपये|रुपए)\s*([0-9]+(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?)",
        r"([0-9]+(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?)\s*(?:rs\.?|inr|₹|रु\.?|रुपये|रुपए)",
    ]
    for pat in primary_amt_patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            snippet_start = max(0, m.start() - 30)
            snippet_end = min(len(text), m.end() + 30)
            context_window = text[snippet_start:snippet_end].lower()
            if any(skip_kw in context_window for skip_kw in ("avl bal", "avail bal", "available bal", "balance", "cashback", "refund")):
                continue
            val = q_money(m.group(1))
            if val > Decimal("0.00"):
                amount = float(val)
                break
        if amount is not None:
            break

    tx_patterns = [
        r"(?:utr(?:\s*no)?|txn\s*id|transaction\s*id|upi\s*ref(?:\s*no)?|ref(?:\s*no)?|rrn)[:\s#=-]*([A-Za-z0-9_-]{8,25})",
        r"\b([0-9]{12})\b",
    ]
    for pat in tx_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            txid = m.group(1).strip().upper()
            break

    return amount, txid


def expire_stale_pending_orders(conn):
    c = conn.cursor()
    c.execute(
        """UPDATE recharge_orders
           SET status = 'EXPIRED_PAYMENT'
           WHERE status = 'PENDING_PAYMENT'
             AND created_at < datetime('now', '-25 minutes')"""
    )


def is_utr_already_used(conn, utr: str, exclude_order_id: str = "") -> bool:
    clean_u = clean_input_value(utr).upper()
    if not clean_u or clean_u == "ADMIN_APPROVED":
        return False
    c = conn.cursor()
    if exclude_order_id:
        c.execute(
            """SELECT 1 FROM recharge_orders
               WHERE UPPER(utr) = ?
                 AND local_order_id != ?
                 AND status IN ('PROCESSING_RECHARGE', 'RECHARGE_SUCCESS', 'RECHARGE_PENDING', 'REFUNDED')
               LIMIT 1""",
            (clean_u, exclude_order_id)
        )
    else:
        c.execute(
            """SELECT 1 FROM recharge_orders
               WHERE UPPER(utr) = ?
                 AND status IN ('PROCESSING_RECHARGE', 'RECHARGE_SUCCESS', 'RECHARGE_PENDING', 'REFUNDED')
               LIMIT 1""",
            (clean_u,)
        )
    return c.fetchone() is not None


def is_gateway_order_already_used(conn, gateway_order_id: str, exclude_order_id: str = "") -> bool:
    gw = clean_input_value(gateway_order_id).upper()
    if not gw or gw in ("WALLET_DIRECT", "SMS_AUTO_MATCH", "MANUAL_UTR", "ADMIN_APPROVED"):
        return False
    c = conn.cursor()
    c.execute(
        """SELECT 1 FROM recharge_orders
           WHERE UPPER(gateway_order_id) = ?
             AND local_order_id != ?
             AND status IN ('PROCESSING_RECHARGE', 'RECHARGE_SUCCESS', 'RECHARGE_PENDING', 'REFUNDED')
           LIMIT 1""",
        (gw, exclude_order_id)
    )
    return c.fetchone() is not None


def claim_order_for_processing(local_order_id: str, gateway_order_id: str = "", utr: str = ""):
    conn = get_db_conn(readonly=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        c.execute("SELECT * FROM recharge_orders WHERE local_order_id = ?", (local_order_id,))
        order = c.fetchone()
        if not order:
            conn.commit()
            return None, "ORDER_NOT_FOUND"

        if order['status'] in TERMINAL_OR_INFLIGHT_STATUSES:
            conn.commit()
            return dict(order), f"ALREADY_{order['status']}"

        clean_utr = clean_input_value(utr).upper() or clean_input_value(order['utr'] or "").upper()
        if clean_utr and is_utr_already_used(conn, clean_utr, exclude_order_id=local_order_id):
            conn.commit()
            return dict(order), "DUPLICATE_UTR"

        if is_gateway_order_already_used(conn, gateway_order_id, exclude_order_id=local_order_id):
            conn.commit()
            return dict(order), "DUPLICATE_GATEWAY_ORDER"

        c.execute(
            """UPDATE recharge_orders
               SET status = 'PROCESSING_RECHARGE',
                   gateway_order_id = COALESCE(NULLIF(?, ''), gateway_order_id),
                   utr = COALESCE(NULLIF(?, ''), utr),
                   updated_at = CURRENT_TIMESTAMP
               WHERE local_order_id = ? AND status NOT IN ('PROCESSING_RECHARGE', 'RECHARGE_SUCCESS', 'RECHARGE_PENDING', 'RECHARGE_FAILED', 'REFUNDED')""",
            (clean_input_value(gateway_order_id), clean_utr, local_order_id)
        )
        if c.rowcount == 0:
            conn.commit()
            return dict(order), "ALREADY_CLAIMED"

        c.execute("SELECT * FROM recharge_orders WHERE local_order_id = ?", (local_order_id,))
        claimed = dict(c.fetchone())
        conn.commit()
        return claimed, "CLAIMED"
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_orders_db():
    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS recharge_orders (
                        local_order_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        service_type TEXT,
                        operator TEXT,
                        number TEXT,
                        recharge_amount REAL,
                        wallet_used REAL,
                        payable_amount REAL,
                        cashback_earned REAL,
                        gateway_order_id TEXT,
                        utr TEXT,
                        a1_txid TEXT,
                        a1_opid TEXT,
                        status TEXT,
                        api_response TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        c.execute("PRAGMA table_info(recharge_orders)")
        cols = {row[1] for row in c.fetchall()}
        if "updated_at" not in cols:
            c.execute("ALTER TABLE recharge_orders ADD COLUMN updated_at TIMESTAMP DEFAULT NULL")

        c.execute('''CREATE TABLE IF NOT EXISTS operator_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        operator TEXT,
                        category TEXT,
                        plan_text TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS admin_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        action TEXT,
                        order_id TEXT,
                        user_id TEXT,
                        amount REAL,
                        note TEXT,
                        ip_addr TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_created ON recharge_orders (user_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_status_amt ON recharge_orders (status, payable_amount)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_utr ON recharge_orders (utr)")
        conn.commit()
    finally:
        conn.close()


init_orders_db()


def get_current_user_id():
    for key in ['user_id', 'email', 'username', 'user', 'id']:
        if key in session and session[key]:
            return str(session[key]).strip()[:120]
    if 'guest_recharge_uid' not in session:
        session['guest_recharge_uid'] = f"GUEST_{secrets.token_hex(6).upper()}"
    return session['guest_recharge_uid']


@recharge_bp.route('/recharge', methods=['GET'])
def recharge_home():
    user_id = get_current_user_id()
    wallet_balance = get_wallet_balance(user_id)
    wallet_txns = get_wallet_transactions(user_id)
    selected_service = clean_input_value(request.args.get('service', 'Mobile')) or 'Mobile'

    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute('''SELECT * FROM recharge_orders 
                     WHERE user_id = ? AND created_at >= datetime('now', '-180 days') 
                     ORDER BY created_at DESC LIMIT 20''', (user_id,))
        history = c.fetchall()
    finally:
        conn.close()

    return render_template(
        'recharge.html',
        wallet_balance=wallet_balance,
        wallet_txns=wallet_txns,
        cashback_rates=CASHBACK_RATES,
        selected_service=selected_service,
        history=history
    )


@recharge_bp.route('/recharge/history', methods=['GET'])
def recharge_history():
    user_id = get_current_user_id()
    wallet_balance = get_wallet_balance(user_id)

    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute('''SELECT * FROM recharge_orders
                     WHERE user_id = ? AND created_at >= datetime('now', '-180 days')
                     ORDER BY created_at DESC LIMIT 200''', (user_id,))
        orders = c.fetchall()
    finally:
        conn.close()

    return render_template(
        'recharge_history.html',
        orders=orders,
        wallet_balance=wallet_balance
    )


@recharge_bp.route('/recharge/billers', methods=['GET'])
def recharge_billers():
    raw_type = clean_input_value(request.args.get('type', 'Electricity')).lower()
    type_map = {
        "dth": "DTH",
        "electricity": "Electricity",
        "gas": "Gas",
        "fastag": "FASTag",
    }
    service_type = type_map.get(raw_type, "Electricity")
    billers = BILLER_LISTS_BY_TYPE.get(service_type, [])
    return render_template("billers.html", service_type=service_type, billers=billers)


@recharge_bp.route('/recharge/service', methods=['GET'])
def recharge_service_form():
    user_id = get_current_user_id()
    wallet_balance = get_wallet_balance(user_id)
    service_type = clean_input_value(request.args.get('type', 'Electricity')) or 'Electricity'
    operator = clean_input_value(request.args.get('operator', ''))
    return render_template(
        'service_form.html',
        service_type=service_type,
        operator=operator,
        wallet_balance=wallet_balance,
        csrf_token=get_csrf_token()
    )


@recharge_bp.route('/admin/logout', methods=['POST', 'GET'])
def admin_logout():
    session.pop("is_cc_admin", None)
    return redirect(url_for("recharge_bp.recharge_home"))


@recharge_bp.route('/admin', methods=['GET'])
@recharge_bp.route('/admin/plans', methods=['GET'])
def admin_plans_view():
    if not is_admin_authorized():
        return "Unauthorized Admin Access (pass ?admin_key=...)", 401
    conn = get_db_conn(readonly=False)
    try:
        expire_stale_pending_orders(conn)
        conn.commit()
        c = conn.cursor()
        c.execute("SELECT * FROM operator_plans ORDER BY id DESC")
        saved_plans = c.fetchall()
        c.execute('''SELECT * FROM recharge_orders
                     WHERE status != 'RECHARGE_SUCCESS'
                     ORDER BY created_at DESC LIMIT 200''')
        stuck_orders = c.fetchall()
    finally:
        conn.close()
    return render_template(
        'admin_plans.html',
        saved_plans=saved_plans,
        stuck_orders=stuck_orders,
        csrf_token=get_csrf_token()
    )


@recharge_bp.route('/admin/refund', methods=['GET'])
def admin_refund_page():
    if not is_admin_authorized():
        return "Unauthorized Admin Access (pass ?admin_key=...)", 401
    conn = get_db_conn(readonly=False)
    try:
        expire_stale_pending_orders(conn)
        conn.commit()
        c = conn.cursor()
        c.execute('''SELECT * FROM recharge_orders
                     WHERE status != 'RECHARGE_SUCCESS'
                     ORDER BY created_at DESC LIMIT 200''')
        stuck_orders = c.fetchall()
    finally:
        conn.close()
    return render_template(
        'agent_refund.html',
        stuck_orders=stuck_orders,
        csrf_token=get_csrf_token()
    )


@recharge_bp.route('/admin/audit-logs', methods=['GET'])
def admin_audit_logs_view():
    if not is_admin_authorized():
        return "Unauthorized Admin Access", 401
    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM admin_audit_logs ORDER BY id DESC LIMIT 100")
        logs = [dict(r) for r in c.fetchall()]
    finally:
        conn.close()
    return jsonify({"ok": True, "logs": logs})


@recharge_bp.route('/admin/refund-wallet', methods=['POST'])
def admin_refund_wallet():
    if not is_admin_authorized():
        return "Unauthorized Admin Access", 401
    if not verify_csrf_token():
        return "Invalid CSRF Token", 403

    order_id = clean_input_value(request.form.get('order_id', ''))
    user_id = clean_input_value(request.form.get('user_id', ''))
    amount = q_money(request.form.get('amount', 0))

    if not user_id or amount <= Decimal("0.00") or amount > Decimal("100000.00"):
        return "कृपया सही User ID और राशि (₹0.01 से ₹1,00,000) दर्ज करें।", 400

    conn = get_db_conn(readonly=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()

        if order_id:
            c.execute("SELECT * FROM recharge_orders WHERE local_order_id = ?", (order_id,))
            order = c.fetchone()
            if not order:
                conn.rollback()
                return "Order ID नहीं मिला।", 404
            if order['status'] in ['RECHARGE_SUCCESS', 'REFUNDED']:
                conn.rollback()
                return f"इस ऑर्डर का स्टेटस पहले से {order['status']} है, दोबारा रिफ़ंड नहीं हो सकता।", 400

            user_id = order['user_id']
            raw_ord_amt = order['payable_amount'] if order['payable_amount'] is not None else order['recharge_amount']
            amount = q_money(raw_ord_amt if q_money(raw_ord_amt) > Decimal("0.00") else amount)
            c.execute(
                """UPDATE recharge_orders
                   SET status = 'REFUNDED', api_response = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE local_order_id = ? AND status NOT IN ('RECHARGE_SUCCESS', 'REFUNDED')""",
                (f"AGENT_WALLET_REFUND: {amount}", order_id)
            )
            if c.rowcount == 0:
                conn.rollback()
                return "ऑर्डर पहले ही प्रोसेस/रिफ़ंड हो चुका है।", 409

        new_bal = add_cashback_to_wallet(
            user_id,
            float(amount),
            order_id or f"AGENT_REF_{int(time.time())}",
            "AGENT WALLET REFUND",
            order_id or user_id
        )
        log_admin_action(conn, "REFUND_WALLET", order_id, user_id, amount, "Agent cashback wallet refund")
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Refund failed")
        return "रिफ़ंड प्रोसेस करने में त्रुटि आई।", 500
    finally:
        conn.close()

    return f"सफल! User ({user_id}) के Cashback/Wallet में ₹{amount:.2f} जुड़ गए। नया बैलेंस: ₹{new_bal:.2f}", 200


@recharge_bp.route('/admin/approve-recharge', methods=['POST'])
def admin_approve_recharge():
    if not is_admin_authorized():
        return "Unauthorized Admin Access", 401
    if not verify_csrf_token():
        return "Invalid CSRF Token", 403

    order_id = clean_input_value(request.form.get('order_id', ''))
    txn_ref = clean_input_value(request.form.get('utr', '') or request.form.get('txn_id', '')).upper()

    if not order_id:
        return "कृपया सही Order ID दर्ज करें।", 400

    conn = get_db_conn(readonly=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        c.execute("SELECT * FROM recharge_orders WHERE local_order_id = ?", (order_id,))
        order = c.fetchone()
        if not order:
            conn.rollback()
            return "Order ID नहीं मिला।", 404

        if order['status'] in ['RECHARGE_SUCCESS', 'REFUNDED']:
            conn.rollback()
            return f"इस ऑर्डर का स्टेटस पहले से {order['status']} है।", 400

        final_utr = txn_ref or clean_input_value(order['utr'] or "").upper() or "ADMIN_APPROVED"
        if final_utr != "ADMIN_APPROVED" and is_utr_already_used(conn, final_utr, exclude_order_id=order_id):
            conn.rollback()
            return "यह UTR पहले ही किसी अन्य ऑर्डर में इस्तेमाल हो चुका है।", 409

        c.execute(
            "UPDATE recharge_orders SET status = 'PENDING_PAYMENT', utr = ?, updated_at = CURRENT_TIMESTAMP WHERE local_order_id = ?",
            (final_utr, order_id)
        )
        log_admin_action(conn, "APPROVE_RECHARGE", order_id, order['user_id'], q_money(order['recharge_amount']), f"UTR: {final_utr}")
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Approve recharge failed")
        return "अप्रूवल प्रोसेस करने में त्रुटि आई।", 500
    finally:
        conn.close()

    res_data = execute_recharge_and_cashback(order_id, "ADMIN_APPROVED", final_utr, as_json=True)
    return f"सफल! ऑर्डर {order_id} प्रोसेस हुआ। स्टेटस: {res_data.get('status', 'DONE')}", 200


@recharge_bp.route('/admin/save-plans', methods=['POST'])
def admin_save_plans():
    if not is_admin_authorized():
        return "Unauthorized Admin Access", 401
    if not verify_csrf_token():
        return "Invalid CSRF Token", 403

    operator = clean_input_value(request.form.get('operator', '')).title()
    category = clean_input_value(request.form.get('category', '')).lower()
    raw_data = request.form.get('plans_data', '')

    if operator and raw_data:
        conn = get_db_conn(readonly=False)
        try:
            c = conn.cursor()
            c.execute(
                "SELECT plan_text FROM operator_plans WHERE LOWER(operator) = LOWER(?) AND LOWER(category) = LOWER(?)",
                (operator, category)
            )
            existing = {row[0].strip() for row in c.fetchall() if row[0]}

            for line in raw_data.split('\n'):
                clean_line = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", line.strip())
                if clean_line and clean_line not in existing:
                    c.execute(
                        "INSERT INTO operator_plans (operator, category, plan_text) VALUES (?, ?, ?)",
                        (operator, category, clean_line)
                    )
                    existing.add(clean_line)
            conn.commit()
        finally:
            conn.close()
        return "Plans Saved Successfully!", 200
    return "Error: Empty Data", 400


@recharge_bp.route('/admin/delete-plan/<int:plan_id>', methods=['POST'])
def delete_plan(plan_id):
    if not is_admin_authorized():
        return "Unauthorized Admin Access", 401
    if not verify_csrf_token():
        return "Invalid CSRF Token", 403

    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute("DELETE FROM operator_plans WHERE id = ?", (plan_id,))
        deleted = c.rowcount
        conn.commit()
    finally:
        conn.close()
    if deleted == 0:
        return "Plan Not Found", 404
    return "Deleted", 200


@recharge_bp.route('/recharge/plans', methods=['GET'])
def select_plan_page():
    user_id = get_current_user_id()
    wallet_balance = get_wallet_balance(user_id)

    mobile_number = clean_input_value(request.args.get('number', ''))
    operator = clean_input_value(request.args.get('operator', 'Jio')).title()
    circle = clean_input_value(request.args.get('circle', ''))
    cb_rate = get_cashback_rate(operator, 'Mobile Prepaid')

    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        if "bsnl" in operator.lower():
            c.execute("SELECT * FROM operator_plans WHERE LOWER(operator) LIKE 'bsnl%' ORDER BY id DESC")
        else:
            c.execute("SELECT * FROM operator_plans WHERE LOWER(operator) = LOWER(?) ORDER BY id DESC", (operator,))
        plans = c.fetchall()
    finally:
        conn.close()

    return render_template(
        'select_plan.html',
        mobile_number=mobile_number,
        operator=operator,
        circle=circle,
        plans=plans,
        wallet_balance=wallet_balance,
        cashback_rate=cb_rate
    )


@recharge_bp.route('/recharge/initiate', methods=['POST'])
def initiate_recharge():
    user_id = get_current_user_id()
    wallet_balance = q_money(get_wallet_balance(user_id))

    service_type = clean_input_value(request.form.get('service_type', 'Mobile')) or 'Mobile'
    operator = clean_input_value(request.form.get('operator', ''))
    number = clean_input_value(request.form.get('number', ''))
    use_wallet = request.form.get('use_wallet') == 'on'

    is_valid, err_msg = validate_service_and_number(service_type, operator, number)
    if not is_valid:
        return err_msg, 400

    recharge_amount = q_money(request.form.get('amount', 0))
    if recharge_amount <= Decimal("0.00") or recharge_amount > Decimal("500000.00"):
        return "कृपया सही रिचार्ज/बिल राशि दर्ज करें।", 400

    rate_dec = Decimal(str(get_cashback_rate(operator, service_type)))
    cashback_earned = q_money((recharge_amount * rate_dec) / Decimal("100"))

    wallet_used = Decimal("0.00")
    if use_wallet and wallet_balance > Decimal("0.00"):
        wallet_used = q_money(min(wallet_balance, recharge_amount))

    payable_amount = q_money(max(Decimal("0.00"), recharge_amount - wallet_used))
    local_order_id = f"RCH{int(time.time() * 1000)}_{secrets.token_hex(2).upper()}"

    conn = get_db_conn(readonly=False)
    try:
        expire_stale_pending_orders(conn)
        c = conn.cursor()
        c.execute('''INSERT INTO recharge_orders 
                     (local_order_id, user_id, service_type, operator, number, recharge_amount, wallet_used, payable_amount, cashback_earned, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_PAYMENT')''',
                  (
                      local_order_id, user_id, service_type, operator, number,
                      float(recharge_amount), float(wallet_used), float(payable_amount), float(cashback_earned)
                  ))
        conn.commit()
    finally:
        conn.close()

    if payable_amount <= Decimal("0.00"):
        return execute_recharge_and_cashback(local_order_id, "WALLET_DIRECT", "")

    callback_url = url_for('recharge_bp.payment_callback', local_order_id=local_order_id, _external=True)
    params = urllib.parse.urlencode({
        "amount": f"{payable_amount:.2f}",
        "mobile": number,
        "operator": operator,
        "user_id": user_id,
        "order_id": local_order_id,
        "redirect_url": callback_url
    })
    return redirect(f"{PAYMENT_GATEWAY_URL}/?{params}")


@recharge_bp.route('/recharge/callback', methods=['GET'])
def payment_callback():
    local_order_id = clean_input_value(request.args.get('local_order_id', ''))
    gateway_order_id = clean_input_value(request.args.get('order_id', ''))
    utr = clean_input_value(request.args.get('utr', '')).upper()

    if not local_order_id or not gateway_order_id:
        return "Invalid Payment Callback", 400

    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM recharge_orders WHERE local_order_id = ?", (local_order_id,))
        order = c.fetchone()
        if not order:
            return "Order Not Found", 404

        if order['status'] in TERMINAL_OR_INFLIGHT_STATUSES:
            return redirect(url_for('recharge_bp.recharge_home'))

        if utr and is_utr_already_used(conn, utr, exclude_order_id=local_order_id):
            return "यह UTR नंबर पहले ही उपयोग हो चुका है।", 409

        if is_gateway_order_already_used(conn, gateway_order_id, exclude_order_id=local_order_id):
            return "यह Gateway Order ID पहले ही किसी अन्य ऑर्डर में उपयोग हो चुका है।", 409
    finally:
        conn.close()

    try:
        verify_res = requests.get(f"{PAYMENT_GATEWAY_URL}/api/payment/status/{gateway_order_id}", timeout=10).json()
        gw_status = str(verify_res.get('status', '')).upper()
        paid_amt = q_money(verify_res.get('amount', 0))
        gw_utr = clean_input_value(verify_res.get('utr', '') or verify_res.get('txnid', '')).upper()
        if not utr and gw_utr:
            utr = gw_utr
    except Exception:
        logger.exception("Payment gateway verification failed")
        return "पेमेंट गेटवे से सत्यापन नहीं हो सका, कृपया कुछ देर बाद पुनः प्रयास करें।", 502

    expected_pay = q_money(order['payable_amount'])
    if "PAID" not in gw_status or abs(paid_amt - expected_pay) > Decimal("0.05"):
        return "Payment not verified yet. Please complete payment first.", 400

    return execute_recharge_and_cashback(local_order_id, gateway_order_id, utr)


@recharge_bp.route('/recharge/submit-utr', methods=['POST'])
def submit_utr():
    local_order_id = clean_input_value(request.form.get('local_order_id', ''))
    utr = clean_input_value(request.form.get('utr', '')).upper()

    if not local_order_id or not re.fullmatch(r"[A-Z0-9]{10,25}", utr):
        return "कृपया सही Order ID और वैध UPI UTR नंबर दर्ज करें।", 400

    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute("SELECT status, api_response FROM recharge_orders WHERE local_order_id = ?", (local_order_id,))
        row = c.fetchone()
        if not row:
            return "Order ID नहीं मिला।", 404
        if row['status'] not in ('PENDING_PAYMENT', 'NEEDS_REVIEW'):
            return f"इस ऑर्डर का स्टेटस {row['status']} है, मैन्युअल UTR स्वीकार नहीं है।", 400

        if is_utr_already_used(conn, utr, exclude_order_id=local_order_id):
            return "यह UTR नंबर पहले ही किसी अन्य रिचार्ज में उपयोग किया जा चुका है!", 409

        if not ALLOW_MANUAL_UTR_AUTO_RECHARGE:
            c.execute(
                """UPDATE recharge_orders
                   SET status = 'NEEDS_REVIEW', utr = ?, api_response = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE local_order_id = ?""",
                (utr, f"MANUAL_UTR_SUBMITTED_FOR_REVIEW:{utr}", local_order_id)
            )
            conn.commit()
            return "आपका UTR नंबर सफलतापूर्वक दर्ज हो गया है और वेरिफ़िकेशन के लिए भेज दिया गया है।", 200
    finally:
        conn.close()

    return execute_recharge_and_cashback(local_order_id, "MANUAL_UTR", utr)


@recharge_bp.route('/recharge/sms-trigger', methods=['POST'])
def sms_payment_trigger():
    data = request.get_json(silent=True) or request.form or {}
    if SMS_GATEWAY_KEY:
        provided_key = clean_input_value(
            request.headers.get("X-SMS-Gateway-Key", "")
            or request.headers.get("X-SMS-Key", "")
            or request.headers.get("X-SMS-KEY", "")
            or request.headers.get("X-API-KEY", "")
            or data.get("key", "")
        )
        if not provided_key or not secrets.compare_digest(provided_key, SMS_GATEWAY_KEY):
            return jsonify({"ok": False, "error": "Unauthorized X-SMS-Gateway-Key"}), 401

    raw_message = clean_input_value(
        data.get('message', '') or data.get('sms', '') or data.get('text', '')
    )

    if raw_message and is_debit_only_message(raw_message):
        return jsonify({
            "ok": False,
            "action": "IGNORED_DEBIT_SMS",
            "reason": "यह डेबिट/खर्च का मैसेज है, क्रेडिट पेमेंट नहीं।"
        }), 200

    req_user_id = clean_input_value(data.get('user_id', ''))
    req_order_id = clean_input_value(
        data.get('order_id', '') or data.get('orderId', '') or data.get('local_order_id', '')
    )
    req_txid = clean_input_value(
        data.get('txn_id', '') or data.get('transaction_id', '') or data.get('utr', '')
    ).upper()

    parsed_amt, parsed_txid = extract_amount_and_txid_from_message(raw_message)
    raw_amt = data.get('amount')
    msg_amount = float(q_money(raw_amt)) if raw_amt not in (None, "") else parsed_amt

    tx_ref = req_txid or parsed_txid

    if not msg_amount or msg_amount <= 0:
        return jsonify({"ok": False, "error": "मैसेज या इनपुट से सही Amount नहीं मिला।"}), 400

    conn = get_db_conn(readonly=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        expire_stale_pending_orders(conn)
        c = conn.cursor()

        if tx_ref and is_utr_already_used(conn, tx_ref):
            conn.rollback()
            return jsonify({
                "ok": False,
                "error": "यह Transaction ID / UTR पहले ही प्रोसेस हो चुका है।",
                "txn_id": tx_ref
            }), 409

        query = """
            SELECT * FROM recharge_orders
            WHERE status = 'PENDING_PAYMENT'
              AND ABS(payable_amount - ?) <= 0.05
              AND created_at >= datetime('now', '-25 minutes')
        """
        params = [msg_amount]

        if req_order_id:
            query += " AND local_order_id = ?"
            params.append(req_order_id)
        if req_user_id:
            query += " AND user_id = ?"
            params.append(req_user_id)

        query += " ORDER BY created_at DESC"
        c.execute(query, params)
        candidates = c.fetchall()

        if len(candidates) == 1:
            matched = candidates[0]
            order_id = matched["local_order_id"]
            matched_user_id = matched["user_id"]
            conn.commit()
            res_data = execute_recharge_and_cashback(order_id, "SMS_AUTO_MATCH", tx_ref, as_json=True)
            return jsonify({
                "ok": True,
                "action": "RECHARGE_TRIGGERED",
                "order_id": order_id,
                "user_id": matched_user_id,
                "amount": msg_amount,
                "txn_id": tx_ref,
                "result": res_data
            }), 200

        if len(candidates) > 1:
            order_ids = [row["local_order_id"] for row in candidates]
            for oid in order_ids:
                c.execute(
                    """UPDATE recharge_orders
                       SET status = 'NEEDS_REVIEW',
                           api_response = ?,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE local_order_id = ?""",
                    (f"AMOUNT_CLASH_{msg_amount}_UTR:{tx_ref}_CANDIDATES:{','.join(order_ids)}", oid)
                )
            conn.commit()
            return jsonify({
                "ok": False,
                "action": "NEEDS_REVIEW",
                "reason": "एक ही अमाउंट के एक से अधिक पेंडिंग ऑर्डर मिले; एडमिन पैनल से मिलान करके अप्रूव करें।",
                "amount": msg_amount,
                "txn_id": tx_ref,
                "candidate_orders": order_ids
            }), 202

        conn.commit()
        return jsonify({
            "ok": False,
            "action": "NO_MATCHING_PENDING_ORDER",
            "amount": msg_amount,
            "txn_id": tx_ref,
            "user_id": req_user_id
        }), 404
    except Exception:
        conn.rollback()
        logger.exception("SMS trigger failed")
        return jsonify({"ok": False, "error": "SMS trigger internal error"}), 500
    finally:
        conn.close()


def execute_recharge_and_cashback(local_order_id, gateway_order_id, utr, as_json=False):
    order, claim_state = claim_order_for_processing(local_order_id, gateway_order_id, utr)
    if claim_state != "CLAIMED" or not order:
        if as_json:
            return {"ok": False, "status": claim_state}
        return redirect(url_for('recharge_bp.recharge_home'))

    wallet_used = q_money(order.get('wallet_used'))
    recharge_amount = q_money(order.get('recharge_amount'))
    payable_amount = q_money(order.get('payable_amount') if order.get('payable_amount') is not None else recharge_amount)
    cashback_earned = q_money(order.get('cashback_earned'))

    actual_wallet_cut = Decimal("0.00")
    if wallet_used > Decimal("0.00"):
        cut_val, _, _ = deduct_wallet_for_recharge(
            order['user_id'],
            float(wallet_used),
            local_order_id,
            order['operator'],
            order['number']
        )
        actual_wallet_cut = q_money(cut_val)

    op_code = resolve_a1_operator_code(order['operator'])
    final_status = "RECHARGE_PENDING"
    a1_txid = ""
    a1_opid = ""
    api_raw_msg = ""

    api_amount_str = (
        str(int(recharge_amount))
        if recharge_amount == recharge_amount.to_integral_value()
        else f"{recharge_amount:.2f}"
    )

    try:
        if A1_API_TOKEN:
            payload = {
                "token": A1_API_TOKEN,
                "operatorcode": op_code,
                "number": order['number'],
                "amount": api_amount_str,
                "orderid": local_order_id,
                "circlecode": "0",
                "format": "json"
            }
            print("A1TOPUP REQUEST ->", A1_BASE_URL, "orderid:", local_order_id, "op:", op_code, "num:", order['number'], "amt:", api_amount_str)
            api_resp = requests.post(A1_BASE_URL, data=payload, timeout=20)
            api_raw_msg = api_resp.text[:300]
            print("A1TOPUP RESPONSE <-", api_resp.status_code, api_raw_msg)
            try:
                resp_json = api_resp.json()
            except ValueError:
                resp_json = {}

            a1_status = str(resp_json.get("status", "")).lower()
            a1_txid = str(resp_json.get("txid", ""))
            a1_opid = str(resp_json.get("opid", ""))

            if a1_status == "success":
                final_status = "RECHARGE_SUCCESS"
            elif a1_status in ("pending", "inprogress", "processing", ""):
                final_status = "RECHARGE_PENDING"
            else:
                final_status = "RECHARGE_FAILED"
        else:
            final_status = "RECHARGE_FAILED"
            api_raw_msg = "A1TOPUP_TOKEN_NOT_SET_IN_ENV"
    except Exception as e:
        final_status = "RECHARGE_PENDING"
        api_raw_msg = f"A1Topup API Error: {str(e)}"
        logger.exception("A1Topup request failed for %s", local_order_id)

    new_wallet_bal = get_wallet_balance(order['user_id'])
    if final_status == "RECHARGE_FAILED":
        total_refund = q_money(actual_wallet_cut + payable_amount)
        if total_refund > Decimal("0.00"):
            new_wallet_bal = add_cashback_to_wallet(
                order['user_id'], float(total_refund), local_order_id, f"REFUND - {order['operator']}", order['number']
            )
    elif final_status == "RECHARGE_SUCCESS" and cashback_earned > Decimal("0.00"):
        new_wallet_bal = add_cashback_to_wallet(
            order['user_id'], float(cashback_earned), local_order_id, order['operator'], order['number']
        )

    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute('''UPDATE recharge_orders 
                     SET status = ?, wallet_used = ?, gateway_order_id = ?, utr = ?, a1_txid = ?, a1_opid = ?, api_response = ?, updated_at = CURRENT_TIMESTAMP
                     WHERE local_order_id = ?''',
                  (
                      final_status, float(actual_wallet_cut), clean_input_value(gateway_order_id),
                      clean_input_value(utr).upper(), a1_txid, a1_opid, api_raw_msg, local_order_id
                  ))
        conn.commit()
        c.execute("SELECT * FROM recharge_orders WHERE local_order_id = ?", (local_order_id,))
        updated_order = c.fetchone()
    finally:
        conn.close()

    if as_json:
        return {
            "ok": final_status == "RECHARGE_SUCCESS",
            "status": final_status,
            "order_id": local_order_id,
            "a1_txid": a1_txid,
            "a1_opid": a1_opid,
            "wallet_balance": new_wallet_bal
        }

    return render_template(
        'recharge.html',
        wallet_balance=new_wallet_bal,
        wallet_txns=get_wallet_transactions(order['user_id']),
        cashback_rates=CASHBACK_RATES,
        selected_service=order['service_type'],
        success_order=updated_order,
        history=[]
    )


@recharge_bp.route('/recharge/status/<order_id>', methods=['GET'])
def check_recharge_status(order_id):
    clean_order_id = clean_input_value(order_id)
    if not clean_order_id:
        return jsonify({"error": "Invalid order_id"}), 400

    conn = get_db_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM recharge_orders WHERE local_order_id = ?", (clean_order_id,))
        order = c.fetchone()

        if not order:
            return jsonify({"error": "Order not found"}), 404

        if order['status'] == 'RECHARGE_PENDING' and A1_API_TOKEN:
            try:
                api_r = requests.get(
                    A1_STATUS_URL,
                    params={"token": A1_API_TOKEN, "orderid": clean_order_id, "format": "json"},
                    timeout=15
                )
                res = api_r.json()
                st = str(res.get("status", "")).lower()
                opid = str(res.get("opid", ""))
                txid = str(res.get("txid", order['a1_txid'] or ""))

                conn.execute("BEGIN IMMEDIATE")
                c.execute("SELECT status, user_id, operator, number, recharge_amount, wallet_used, payable_amount, cashback_earned FROM recharge_orders WHERE local_order_id = ?", (clean_order_id,))
                fresh = c.fetchone()
                if fresh and fresh['status'] == 'RECHARGE_PENDING':
                    if st == "success":
                        c.execute(
                            """UPDATE recharge_orders
                               SET status = 'RECHARGE_SUCCESS', a1_txid = ?, a1_opid = ?, api_response = ?, updated_at = CURRENT_TIMESTAMP
                               WHERE local_order_id = ? AND status = 'RECHARGE_PENDING'""",
                            (txid, opid, f"STATUS_SUCCESS: {opid}", clean_order_id)
                        )
                        cb_amt = q_money(fresh['cashback_earned'])
                        if c.rowcount > 0 and cb_amt > Decimal("0.00"):
                            add_cashback_to_wallet(
                                fresh['user_id'], float(cb_amt), clean_order_id, fresh['operator'], fresh['number']
                            )
                    elif st in ("failure", "failed", "error", "refund"):
                        c.execute(
                            """UPDATE recharge_orders
                               SET status = 'RECHARGE_FAILED', a1_txid = ?, a1_opid = ?, api_response = ?, updated_at = CURRENT_TIMESTAMP
                               WHERE local_order_id = ? AND status = 'RECHARGE_PENDING'""",
                            (txid, opid, f"STATUS_FAILURE: {opid}", clean_order_id)
                        )
                        if c.rowcount > 0:
                            total_refund = q_money(q_money(fresh['wallet_used']) + q_money(fresh['payable_amount']))
                            if total_refund > Decimal("0.00"):
                                add_cashback_to_wallet(
                                    fresh['user_id'], float(total_refund), clean_order_id, f"REFUND - {fresh['operator']}", fresh['number']
                                )
                conn.commit()
            except Exception:
                conn.rollback()

        c.execute("SELECT local_order_id, operator, number, recharge_amount, status, a1_txid, a1_opid FROM recharge_orders WHERE local_order_id = ?", (clean_order_id,))
        updated = dict(c.fetchone())
        return jsonify(updated)
    finally:
        conn.close()


@recharge_bp.route('/a1-callback', methods=['GET', 'POST'])
def a1topup_webhook_callback():
    payload = request.get_json(silent=True) or request.form or request.args
    order_id = clean_input_value(payload.get('orderid') or payload.get('txid') or '')
    cb_status = clean_input_value(payload.get('status', '')).lower()
    opid = clean_input_value(payload.get('opid', ''))

    if not verify_callback_signature(order_id, cb_status, opid):
        return "Unauthorized Callback", 401

    if not order_id:
        return "Missing orderid/txid", 400

    conn = get_db_conn(readonly=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        c.execute(
            "SELECT * FROM recharge_orders WHERE local_order_id = ? OR a1_txid = ?",
            (order_id, order_id)
        )
        order = c.fetchone()

        if not order:
            conn.commit()
            return "Order Not Found", 200

        actual_order_id = order['local_order_id']
        if order['status'] in ['RECHARGE_SUCCESS', 'RECHARGE_FAILED', 'REFUNDED']:
            conn.commit()
            return "OK", 200

        if cb_status == "success":
            c.execute(
                """UPDATE recharge_orders
                   SET status = 'RECHARGE_SUCCESS', a1_opid = ?, api_response = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE local_order_id = ? AND status NOT IN ('RECHARGE_SUCCESS', 'RECHARGE_FAILED', 'REFUNDED')""",
                (opid, f"CALLBACK_SUCCESS: {opid}", actual_order_id)
            )
            cb_amt = q_money(order['cashback_earned'])
            if c.rowcount > 0 and cb_amt > Decimal("0.00"):
                add_cashback_to_wallet(
                    order['user_id'], float(cb_amt), actual_order_id, order['operator'], order['number']
                )
        elif cb_status in ("failure", "failed", "error", "refund"):
            c.execute(
                """UPDATE recharge_orders
                   SET status = 'RECHARGE_FAILED', a1_opid = ?, api_response = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE local_order_id = ? AND status NOT IN ('RECHARGE_SUCCESS', 'RECHARGE_FAILED', 'REFUNDED')""",
                (opid, f"CALLBACK_FAILURE: {opid}", actual_order_id)
            )
            if c.rowcount > 0:
                total_refund = q_money(q_money(order['wallet_used']) + q_money(order['payable_amount']))
                if total_refund > Decimal("0.00"):
                    add_cashback_to_wallet(
                        order['user_id'], float(total_refund), actual_order_id, f"REFUND - {order['operator']}", order['number']
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return "OK", 200