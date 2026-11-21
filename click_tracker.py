import uuid


def ensure_click_logs_table(conn):
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
    conn.commit()


def create_and_log_click(conn, user_id: int, store_name: str, target_url: str) -> str:
    """
    लॉगिन यूज़र के लिए यूनिक sub_id बनाकर click_logs में स्टोर के साथ सेव करता है।
    """
    ensure_click_logs_table(conn)

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


def get_click_details(conn, sub_id: str):
    """
    sub_id के आधार पर user_id और store_name निकालता है।
    """
    ensure_click_logs_table(conn)
    clean_sub = str(sub_id or "").strip()
    if not clean_sub:
        return None

    return conn.execute(
        """
        SELECT id, sub_id, user_id, store_name, target_url, clicked_at
        FROM click_logs
        WHERE sub_id = ?
        """,
        (clean_sub,),
    ).fetchone()


def build_tracked_url(target_url: str, sub_id: str) -> str:
    clean_url = str(target_url or "").strip()
    if not clean_url or not sub_id:
        return clean_url
    sep = "&" if "?" in clean_url else "?"
    return f"{clean_url}{sep}subid={sub_id}"
