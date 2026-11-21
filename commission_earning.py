import uuid

USER_SHARE_PERCENT = 0.50  # 50% User share, 50% Admin share
REFERRAL_BONUS_AMOUNT = 25.0  # First-time referral bonus (deducted from admin's 50% share)
REFERRAL_MIN_COMMISSION = 50.0  # Minimum ₹50 total commission condition


def calculate_commission_split(total_commission: float, is_first_referral_order: bool = False) -> dict:
    total = round(max(0.0, float(total_commission)), 2)
    user_share = round(total * USER_SHARE_PERCENT, 2)
    admin_gross_half = round(total - user_share, 2)

    if is_first_referral_order and total >= REFERRAL_MIN_COMMISSION:
        referrer_bonus = REFERRAL_BONUS_AMOUNT
        admin_share = round(max(0.0, admin_gross_half - referrer_bonus), 2)
    else:
        referrer_bonus = 0.0
        admin_share = admin_gross_half

    return {
        "total_commission": total,
        "user_share": user_share,
        "admin_share": admin_share,
        "referrer_bonus": referrer_bonus,
    }


def _ensure_column(conn, table_name: str, column_name: str, column_def: str):
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in cols:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def ensure_earning_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS click_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sub_id TEXT UNIQUE,
            user_id INTEGER NOT NULL,
            store_name TEXT DEFAULT 'Store',
            target_url TEXT DEFAULT '',
            clicked_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _ensure_column(conn, "click_logs", "sub_id", "TEXT")
    _ensure_column(conn, "click_logs", "store_name", "TEXT DEFAULT 'Store'")
    _ensure_column(conn, "click_logs", "target_url", "TEXT DEFAULT ''")
    _ensure_column(conn, "click_logs", "clicked_at", "TEXT")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS affiliate_commissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            sub_id TEXT DEFAULT '',
            store_name TEXT DEFAULT '',
            total_commission REAL NOT NULL,
            user_share REAL NOT NULL,
            admin_share REAL NOT NULL,
            referrer_id INTEGER,
            referrer_bonus REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _ensure_column(conn, "affiliate_commissions", "referrer_id", "INTEGER")
    _ensure_column(conn, "affiliate_commissions", "referrer_bonus", "REAL NOT NULL DEFAULT 0.0")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS referral_first_order_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referred_user_id INTEGER UNIQUE NOT NULL,
            referrer_id INTEGER NOT NULL,
            order_id TEXT NOT NULL,
            bonus_amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'CONFIRMED',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


# ==============================================================================
# --- CLICK TRACKER FUNCTIONS ---
# ==============================================================================

def create_and_log_click(conn, user_id: int, store_name: str, target_url: str) -> str:
    ensure_earning_tables(conn)
    clean_store = str(store_name or "Store").strip()
    clean_url = str(target_url or "").strip()
    sub_id = f"SUB{uuid.uuid4().hex[:12].upper()}"

    cols = [row[1] for row in conn.execute("PRAGMA table_info(click_logs)").fetchall()]
    if "click_id" in cols and "sub_id" in cols:
        conn.execute(
            """
            INSERT INTO click_logs (click_id, sub_id, user_id, store_name, target_url, clicked_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (sub_id, sub_id, int(user_id), clean_store, clean_url),
        )
    else:
        conn.execute(
            """
            INSERT INTO click_logs (sub_id, user_id, store_name, target_url, clicked_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (sub_id, int(user_id), clean_store, clean_url),
        )
    conn.commit()
    return sub_id


def build_tracked_url(target_url: str, sub_id: str) -> str:
    clean_url = str(target_url or "").strip()
    if not clean_url or not sub_id:
        return clean_url
    sep = "&" if "?" in clean_url else "?"
    return f"{clean_url}{sep}subid={sub_id}"


def get_user_from_click(conn, sub_id: str):
    ensure_earning_tables(conn)
    clean_sub = str(sub_id or "").strip()
    if not clean_sub:
        return None
    cols = [row[1] for row in conn.execute("PRAGMA table_info(click_logs)").fetchall()]
    if "click_id" in cols:
        return conn.execute(
            "SELECT * FROM click_logs WHERE sub_id = ? OR click_id = ?",
            (clean_sub, clean_sub),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM click_logs WHERE sub_id = ?",
        (clean_sub,),
    ).fetchone()


# ==============================================================================
# --- FIRST REFERRAL ORDER HELPERS (₹25 FROM ADMIN 50% SHARE) ---
# ==============================================================================

def _get_referrer_if_first_order_eligible(conn, user_id: int, total_commission: float):
    if round(float(total_commission or 0.0), 2) < REFERRAL_MIN_COMMISSION:
        return None

    user_row = conn.execute(
        "SELECT id, referred_by FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if not user_row or not user_row["referred_by"]:
        return None

    referrer_id = user_row["referred_by"]
    if referrer_id == user_id:
        return None

    already_rewarded = conn.execute(
        "SELECT id FROM referral_first_order_rewards WHERE referred_user_id = ?",
        (user_id,),
    ).fetchone()
    if already_rewarded:
        return None

    prior_confirmed = conn.execute(
        """
        SELECT id FROM affiliate_commissions
        WHERE user_id = ? AND status = 'CONFIRMED'
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if prior_confirmed:
        return None

    return referrer_id


def _credit_referrer_bonus_if_confirmed(conn, order_id: str, referred_user_id: int, referrer_id: int, bonus_amount: float):
    if not referrer_id or bonus_amount <= 0:
        return

    existing = conn.execute(
        "SELECT id FROM referral_first_order_rewards WHERE referred_user_id = ?",
        (referred_user_id,),
    ).fetchone()
    if existing:
        return

    conn.execute(
        """
        UPDATE users
        SET confirmed_balance = ROUND(confirmed_balance + ?, 2)
        WHERE id = ?
        """,
        (bonus_amount, referrer_id),
    )
    conn.execute(
        """
        INSERT INTO referral_first_order_rewards
            (referred_user_id, referrer_id, order_id, bonus_amount, status)
        VALUES (?, ?, ?, ?, 'CONFIRMED')
        """,
        (referred_user_id, referrer_id, order_id, bonus_amount),
    )


def _reverse_referrer_bonus_if_cancelled(conn, order_id: str):
    reward_row = conn.execute(
        "SELECT * FROM referral_first_order_rewards WHERE order_id = ? AND status = 'CONFIRMED'",
        (order_id,),
    ).fetchone()
    if not reward_row:
        return

    conn.execute(
        """
        UPDATE users
        SET confirmed_balance = MAX(0.0, ROUND(confirmed_balance - ?, 2))
        WHERE id = ?
        """,
        (float(reward_row["bonus_amount"]), reward_row["referrer_id"]),
    )
    conn.execute(
        "UPDATE referral_first_order_rewards SET status = 'CANCELLED' WHERE order_id = ?",
        (order_id,),
    )


# ==============================================================================
# --- COMMISSION & CANCELLATION ENGINE (50/50 SPLIT + TOTAL REVERSAL) ---
# ==============================================================================

def normalize_order_status(raw_status: str):
    status_norm = str(raw_status or "").strip().upper()
    if status_norm in ["PENDING", "TRACKED"]:
        return "PENDING"
    if status_norm in ["CONFIRMED", "APPROVED", "COMPLETED"]:
        return "CONFIRMED"
    if status_norm in ["CANCELLED", "CANCELED", "REJECTED", "DECLINED", "RETURNED", "REFUNDED"]:
        return "CANCELLED"
    return None


def record_commission_event(
    conn,
    order_id: str,
    user_id: int,
    total_commission: float,
    event_status: str,
    store_name: str = "",
    sub_id: str = "",
) -> dict:
    ensure_earning_tables(conn)

    clean_order_id = str(order_id or "").strip()
    clean_store = str(store_name or "").strip()
    clean_sub = str(sub_id or "").strip()
    new_status = normalize_order_status(event_status)

    if not clean_order_id or not user_id:
        return {"ok": False, "error": "Invalid order_id or user_id"}

    if not new_status:
        return {"ok": False, "error": f"Unsupported status: {event_status}"}

    user_row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user_row:
        return {"ok": False, "error": "User not found"}

    existing = conn.execute(
        "SELECT * FROM affiliate_commissions WHERE order_id = ?",
        (clean_order_id,),
    ).fetchone()

    # 1. नया ऑर्डर रिकॉर्ड
    if not existing:
        total_val = round(max(0.0, float(total_commission)), 2)
        if total_val <= 0 and new_status != "CANCELLED":
            return {"ok": False, "error": "Commission must be greater than 0"}

        referrer_id = _get_referrer_if_first_order_eligible(conn, user_id, total_val)
        is_first_ref = bool(referrer_id)
        split = calculate_commission_split(total_val, is_first_referral_order=is_first_ref)

        if new_status == "CANCELLED":
            split["user_share"] = 0.0
            split["admin_share"] = 0.0
            split["referrer_bonus"] = 0.0

        conn.execute(
            """
            INSERT INTO affiliate_commissions
                (order_id, user_id, sub_id, store_name, total_commission, user_share, admin_share, referrer_id, referrer_bonus, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                clean_order_id,
                user_id,
                clean_sub,
                clean_store,
                split["total_commission"],
                split["user_share"],
                split["admin_share"],
                referrer_id,
                split["referrer_bonus"],
                new_status,
            ),
        )

        if new_status == "PENDING":
            conn.execute(
                "UPDATE users SET pending_balance = ROUND(pending_balance + ?, 2) WHERE id = ?",
                (split["user_share"], user_id),
            )
        elif new_status == "CONFIRMED":
            conn.execute(
                "UPDATE users SET confirmed_balance = ROUND(confirmed_balance + ?, 2) WHERE id = ?",
                (split["user_share"], user_id),
            )
            if is_first_ref and split["referrer_bonus"] > 0:
                _credit_referrer_bonus_if_confirmed(
                    conn, clean_order_id, user_id, referrer_id, split["referrer_bonus"]
                )

        conn.commit()
        return {
            "ok": True,
            "order_id": clean_order_id,
            "store_name": clean_store,
            "status": new_status,
            "user_share": split["user_share"],
            "admin_share": split["admin_share"],
            "referrer_bonus": split["referrer_bonus"],
        }

    # 2. पहले से मौजूद ऑर्डर का स्टेटस अपडेट
    prev_status = str(existing["status"]).upper()
    share = float(existing["user_share"])
    referrer_id = existing["referrer_id"]
    referrer_bonus = float(existing["referrer_bonus"] or 0.0)

    if prev_status == new_status:
        return {"ok": True, "order_id": clean_order_id, "status": new_status, "duplicate_ignored": True}

    if prev_status == "CANCELLED":
        return {"ok": True, "order_id": clean_order_id, "status": "CANCELLED", "already_cancelled": True}

    if prev_status == "PENDING" and new_status == "CONFIRMED":
        conn.execute(
            """
            UPDATE users
            SET pending_balance = MAX(0.0, ROUND(pending_balance - ?, 2)),
                confirmed_balance = ROUND(confirmed_balance + ?, 2)
            WHERE id = ?
            """,
            (share, share, user_id),
        )
        if referrer_id and referrer_bonus > 0:
            _credit_referrer_bonus_if_confirmed(conn, clean_order_id, user_id, referrer_id, referrer_bonus)

    elif prev_status == "PENDING" and new_status == "CANCELLED":
        conn.execute(
            """
            UPDATE users
            SET pending_balance = MAX(0.0, ROUND(pending_balance - ?, 2))
            WHERE id = ?
            """,
            (share, user_id),
        )
        _reverse_referrer_bonus_if_cancelled(conn, clean_order_id)
        conn.execute(
            """
            UPDATE affiliate_commissions
            SET status = 'CANCELLED', user_share = 0.0, admin_share = 0.0, referrer_bonus = 0.0, updated_at = datetime('now')
            WHERE order_id = ?
            """,
            (clean_order_id,),
        )
        conn.commit()
        return {
            "ok": True,
            "order_id": clean_order_id,
            "previous_status": prev_status,
            "status": "CANCELLED",
            "user_share": 0.0,
            "admin_share": 0.0,
            "referrer_bonus": 0.0,
        }

    elif prev_status == "CONFIRMED" and new_status == "CANCELLED":
        conn.execute(
            """
            UPDATE users
            SET confirmed_balance = MAX(0.0, ROUND(confirmed_balance - ?, 2))
            WHERE id = ?
            """,
            (share, user_id),
        )
        _reverse_referrer_bonus_if_cancelled(conn, clean_order_id)
        conn.execute(
            """
            UPDATE affiliate_commissions
            SET status = 'CANCELLED', user_share = 0.0, admin_share = 0.0, referrer_bonus = 0.0, updated_at = datetime('now')
            WHERE order_id = ?
            """,
            (clean_order_id,),
        )
        conn.commit()
        return {
            "ok": True,
            "order_id": clean_order_id,
            "previous_status": prev_status,
            "status": "CANCELLED",
            "user_share": 0.0,
            "admin_share": 0.0,
            "referrer_bonus": 0.0,
        }

    conn.execute(
        """
        UPDATE affiliate_commissions
        SET status = ?, updated_at = datetime('now')
        WHERE order_id = ?
        """,
        (new_status, clean_order_id),
    )
    conn.commit()

    return {
        "ok": True,
        "order_id": clean_order_id,
        "previous_status": prev_status,
        "status": new_status,
        "user_share": share,
        "admin_share": float(existing["admin_share"]),
        "referrer_bonus": referrer_bonus,
    }


def get_user_earning_summary(conn, user_id: int) -> dict:
    ensure_earning_tables(conn)
    user = conn.execute(
        "SELECT pending_balance, confirmed_balance FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    rows = conn.execute(
        """
        SELECT order_id, store_name, total_commission, user_share, admin_share, referrer_bonus, status, updated_at
        FROM affiliate_commissions
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()

    return {
        "pending_balance": float(user["pending_balance"]) if user else 0.0,
        "confirmed_balance": float(user["confirmed_balance"]) if user else 0.0,
        "orders": [dict(r) for r in rows],
    }
