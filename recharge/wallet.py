import os
import re
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

WALLET_DB_PATH = os.path.join(os.path.dirname(__file__), "recharge_wallet.db")
TWO_PLACES = Decimal("0.01")


def q_money(val) -> Decimal:
    if val is None or isinstance(val, bool):
        return Decimal("0.00")
    if isinstance(val, Decimal):
        if not val.is_finite():
            return Decimal("0.00")
        return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    s = str(val).replace(",", "").replace("₹", "").strip()
    if not s:
        return Decimal("0.00")
    try:
        d = Decimal(s)
        if not d.is_finite():
            return Decimal("0.00")
        return d.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def _clean_uid(user_id) -> str:
    uid = re.sub(r"[\r\n\t\x00-\x1f]+", "", str(user_id or "")).strip()
    return uid[:120]


def get_wallet_conn(readonly: bool = False):
    if readonly and os.path.exists(WALLET_DB_PATH):
        uri = f"file:{os.path.abspath(WALLET_DB_PATH)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0, check_same_thread=False)
    else:
        conn = sqlite3.connect(WALLET_DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    if not readonly:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_wallet_db():
    conn = get_wallet_conn(readonly=False)
    try:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS user_recharge_wallets (
                        user_id TEXT PRIMARY KEY,
                        balance REAL DEFAULT 0.0 CHECK (balance >= 0),
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS wallet_ledger (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        order_id TEXT,
                        txn_type TEXT NOT NULL CHECK (txn_type IN ('CREDIT', 'DEBIT')),
                        amount REAL NOT NULL CHECK (amount > 0),
                        balance_after REAL DEFAULT 0.0,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        c.execute("PRAGMA table_info(wallet_ledger)")
        cols = {row[1] for row in c.fetchall()}
        if "balance_after" not in cols:
            c.execute("ALTER TABLE wallet_ledger ADD COLUMN balance_after REAL DEFAULT 0.0")

        c.execute("CREATE INDEX IF NOT EXISTS idx_ledger_user_created ON wallet_ledger (user_id, created_at DESC, id DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ledger_order_type ON wallet_ledger (order_id, txn_type)")
        conn.commit()
    finally:
        conn.close()


init_wallet_db()


def _ensure_wallet_row_locked(cursor, user_id: str) -> Decimal:
    uid = _clean_uid(user_id)
    if not uid:
        return Decimal("0.00")
    cursor.execute("SELECT balance FROM user_recharge_wallets WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    if not row:
        cursor.execute(
            "INSERT OR IGNORE INTO user_recharge_wallets (user_id, balance) VALUES (?, 0.0)",
            (uid,)
        )
        cursor.execute("SELECT balance FROM user_recharge_wallets WHERE user_id = ?", (uid,))
        row = cursor.fetchone()
    bal = q_money(row["balance"] if row else 0)
    return bal if bal >= Decimal("0.00") else Decimal("0.00")


def get_wallet_balance(user_id) -> float:
    uid = _clean_uid(user_id)
    if not uid:
        return 0.0
    conn = get_wallet_conn(readonly=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        bal = _ensure_wallet_row_locked(c, uid)
        conn.commit()
        return float(bal)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _already_processed_txn(cursor, order_id: str, txn_type: str, category_tag: str = "") -> bool:
    oid = str(order_id or "").strip()
    if not oid:
        return False
    if category_tag == "REFUND":
        cursor.execute(
            """SELECT 1 FROM wallet_ledger
               WHERE order_id = ? AND txn_type = ?
                 AND (UPPER(description) LIKE 'REFUND%' OR UPPER(description) LIKE '%REFUND%')
               LIMIT 1""",
            (oid, txn_type)
        )
    elif category_tag == "AGENT_REFUND":
        cursor.execute(
            """SELECT 1 FROM wallet_ledger
               WHERE order_id = ? AND txn_type = ?
                 AND UPPER(description) LIKE 'AGENT REFUND%'
               LIMIT 1""",
            (oid, txn_type)
        )
    elif category_tag == "CASHBACK":
        cursor.execute(
            """SELECT 1 FROM wallet_ledger
               WHERE order_id = ? AND txn_type = ?
                 AND description LIKE '%Recharge Cashback'
               LIMIT 1""",
            (oid, txn_type)
        )
    else:
        cursor.execute(
            "SELECT 1 FROM wallet_ledger WHERE order_id = ? AND txn_type = ? LIMIT 1",
            (oid, txn_type)
        )
    return cursor.fetchone() is not None


def add_cashback_to_wallet(user_id, cashback_amount, order_id, operator, number) -> float:
    uid = _clean_uid(user_id)
    if not uid:
        return 0.0
    amt = q_money(cashback_amount)
    if amt <= Decimal("0.00"):
        return get_wallet_balance(uid)

    op_str = str(operator or "").strip()
    num_str = str(number or "").strip()
    suffix = f" ({num_str})" if num_str else ""

    if op_str.upper().startswith("REFUND"):
        desc = f"{op_str}{suffix}"
        txn_guard_type = "REFUND"
    elif op_str.upper() == "AGENT WALLET REFUND":
        desc = f"Agent Refund{suffix}"
        txn_guard_type = "AGENT_REFUND"
    else:
        desc = f"{op_str}{suffix} Recharge Cashback".strip()
        txn_guard_type = "CASHBACK"

    conn = get_wallet_conn(readonly=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        current_bal = _ensure_wallet_row_locked(c, uid)

        if _already_processed_txn(c, order_id, "CREDIT", txn_guard_type):
            conn.commit()
            return float(current_bal)

        new_bal = q_money(current_bal + amt)
        c.execute(
            "UPDATE user_recharge_wallets SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (float(new_bal), uid)
        )
        c.execute(
            '''INSERT INTO wallet_ledger (user_id, order_id, txn_type, amount, balance_after, description)
               VALUES (?, ?, 'CREDIT', ?, ?, ?)''',
            (uid, str(order_id or "").strip(), float(amt), float(new_bal), desc)
        )
        conn.commit()
        return float(new_bal)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def deduct_wallet_for_recharge(user_id, used_amount, order_id, operator, number):
    uid = _clean_uid(user_id)
    if not uid:
        return 0.0, 0.0, False
    req_amt = q_money(used_amount)
    if req_amt <= Decimal("0.00"):
        return 0.0, get_wallet_balance(uid), True

    conn = get_wallet_conn(readonly=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        current_bal = _ensure_wallet_row_locked(c, uid)

        if _already_processed_txn(c, order_id, "DEBIT", ""):
            c.execute(
                "SELECT amount FROM wallet_ledger WHERE order_id = ? AND txn_type = 'DEBIT' LIMIT 1",
                (str(order_id or "").strip(),)
            )
            prev = c.fetchone()
            prev_amt = q_money(prev["amount"] if prev else 0)
            conn.commit()
            return float(prev_amt), float(current_bal), (prev_amt >= req_amt)

        actual_deduct = min(current_bal, req_amt)
        actual_deduct = q_money(actual_deduct)
        if actual_deduct <= Decimal("0.00"):
            conn.commit()
            return 0.0, float(current_bal), False

        new_bal = q_money(current_bal - actual_deduct)
        if new_bal < Decimal("0.00"):
            new_bal = Decimal("0.00")

        c.execute(
            "UPDATE user_recharge_wallets SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (float(new_bal), uid)
        )
        c.execute(
            '''INSERT INTO wallet_ledger (user_id, order_id, txn_type, amount, balance_after, description)
               VALUES (?, ?, 'DEBIT', ?, ?, ?)''',
            (uid, str(order_id or "").strip(), float(actual_deduct), float(new_bal), f"Used in {operator} ({number}) Recharge")
        )
        conn.commit()
        return float(actual_deduct), float(new_bal), (actual_deduct >= req_amt)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_wallet_transactions(user_id, limit=15):
    uid = _clean_uid(user_id)
    if not uid:
        return []
    conn = get_wallet_conn(readonly=False)
    try:
        c = conn.cursor()
        if limit is None:
            c.execute(
                "SELECT * FROM wallet_ledger WHERE user_id = ? ORDER BY created_at DESC, id DESC",
                (uid,)
            )
        else:
            safe_lim = max(1, int(limit))
            c.execute(
                "SELECT * FROM wallet_ledger WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (uid, safe_lim)
            )
        return c.fetchall()
    finally:
        conn.close()