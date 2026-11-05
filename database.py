import sqlite3

DB_NAME = "commission_cloud.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. यूज़र्स टेबल
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            upi_id TEXT DEFAULT '',
            pending_balance REAL DEFAULT 0.0,
            available_balance REAL DEFAULT 0.0
        )
    ''')
    
    # 2. ऑर्डर्स और कैशबैक ट्रैकिंग टेबल
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            store_name TEXT,
            order_amount REAL,
            user_commission REAL,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # 3. विथड्रॉल / पेआउट रिक्वेस्ट टेबल (₹50+ होने पर)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payout_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            upi_id TEXT,
            amount REAL,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Commission Cloud Database Initialized Successfully!")

if __name__ == "__main__":
    init_db()