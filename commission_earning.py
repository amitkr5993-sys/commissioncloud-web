import uuid

USER_SHARE_PERCENT = 0.50  # 50% User share, 50% Admin share


def calculate_commission_split(total_commission: float) -> dict:
    total = round(max(0.0, float(total_commission)), 2)
    user_share = round(total * USER_SHARE_PERCENT, 2)
    admin_share = round(total - user_share, 2)
    return {
        "total_commission": total,
        "user_share": user_share,
        "admin_share": admin_share,
    }


def ensure_earning_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS click_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sub_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            store_name TEXT NOT NULL,
            target_url TEXT NOT NULL,
            clicked_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
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
            status TEXT NOT NULL DEFAULT 'PENDING',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


# ==============================================================================
# --- CLICK TRACKER FUNCTIONS ---
# ==============================================================================

def create_and_log_click(conn, user_id: int, store_name: str, target_url: str) -> str:
    """
    यूज़र के क्लिक पर यूनिक sub_id बनाकर click_logs में स्टोर नाम के साथ सेव करता है।
    """
    ensure_earning_tables(conn)
    clean_store = str(store_name or "Store").strip()
    clean_url = str(target_url or "").strip()
    sub_id = f"SUB{uuid.uuid4().hex[:12].upper()}"

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
    return conn.execute(
        "SELECT id, sub_id, user_id, store_name, target_url, clicked_at FROM click_logs WHERE sub_id = ?",
        (clean_sub,),
    ).fetchone()


# ==============================================================================
# --- COMMISSION & CANCELLATION ENGINE (50/50 SPLIT) ---
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
    """
    शॉपिंग/कमीशन इवेंट को 50/50 स्प्लिट और सटीक कैंसिलेशन/कन्फर्मेशन लॉजिक के साथ प्रोसेस करता है।
    event_status: 'PENDING' | 'CONFIRMED' | 'CANCELLED'
    """
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

    split = calculate_commission_split(total_commission)

    existing = conn.execute(
        "SELECT * FROM affiliate_commissions WHERE order_id = ?",
        (clean_order_id,),
    ).fetchone()

    # 1. नया ऑर्डर रिकॉर्ड
    if not existing:
        if split["total_commission"] <= 0 and new_status != "CANCELLED":
            return {"ok": False, "error": "Commission must be greater than 0"}

        conn.execute(
            """
            INSERT INTO affiliate_commissions
                (order_id, user_id, sub_id, store_name, total_commission, user_share, admin_share, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                clean_order_id,
                user_id,
                clean_sub,
                clean_store,
                split["total_commission"],
                split["user_share"],
                split["admin_share"],
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

        conn.commit()
        return {
            "ok": True,
            "order_id": clean_order_id,
            "store_name": clean_store,
            "status": new_status,
            "user_share": split["user_share"],
            "admin_share": split["admin_share"],
        }

    # 2. पहले से मौजूद ऑर्डर का स्टेटस अपडेट
    prev_status = str(existing["status"]).upper()
    share = float(existing["user_share"])

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

    elif prev_status == "PENDING" and new_status == "CANCELLED":
        conn.execute(
            """
            UPDATE users
            SET pending_balance = MAX(0.0, ROUND(pending_balance - ?, 2))
            WHERE id = ?
            """,
            (share, user_id),
        )

    elif prev_status == "CONFIRMED" and new_status == "CANCELLED":
        conn.execute(
            """
            UPDATE users
            SET confirmed_balance = MAX(0.0, ROUND(confirmed_balance - ?, 2))
            WHERE id = ?
            """,
            (share, user_id),
        )

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
    }


def get_user_earning_summary(conn, user_id: int) -> dict:
    ensure_earning_tables(conn)
    user = conn.execute(
        "SELECT pending_balance, confirmed_balance FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    rows = conn.execute(
        """
        SELECT order_id, store_name, total_commission, user_share, admin_share, status, updated_at
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
