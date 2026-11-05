import sqlite3

DB_NAME = "cashback.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Users Table with Phone, Password, and Referral Tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT UNIQUE,
            password TEXT,
            referral_code TEXT UNIQUE NOT NULL,
            referred_by INTEGER,
            referral_bonus_given INTEGER DEFAULT 0,
            confirmed_balance REAL DEFAULT 0.0,
            pending_balance REAL DEFAULT 0.0
        )
    ''')

    # Safe Schema Migrations
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = [col[1] for col in cursor.fetchall()]

    if "phone" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")

    if "password" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN password TEXT")

    if "referral_bonus_given" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN referral_bonus_given INTEGER DEFAULT 0")

    # 2. Stores Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            cashback_rate TEXT NOT NULL,
            target_url TEXT NOT NULL,
            badge TEXT
        )
    ''')

    # 3. Outgoing Click Logs (SubID Tracking)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS click_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            store_name TEXT NOT NULL,
            sub_id TEXT UNIQUE NOT NULL,
            clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 4. Missing Cashback Claims Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS missing_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            store_name TEXT NOT NULL,
            order_id TEXT NOT NULL,
            order_amount REAL NOT NULL,
            status TEXT DEFAULT 'Under Review',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 5. Payout Requests Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payout_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payout_method TEXT NOT NULL,
            payment_details TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            utr_number TEXT,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 6. App Settings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    # Default App Settings
    default_settings = [
        ('support_phone', '+91-9876543210'),
        ('support_whatsapp', '919876543210')
    ]
    cursor.executemany("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", default_settings)

    # Default Stores
    cursor.execute("SELECT COUNT(*) FROM stores")
    if cursor.fetchone()[0] == 0:
        stores_data = [
            ("Flipkart", "E-commerce", "Upto 6.50% Cashback", "https://www.flipkart.com", "Sale Live Now"),
            ("Amazon", "E-commerce", "Upto 7% Rewards", "https://www.amazon.in", "Sale Live Now"),
            ("Myntra", "Fashion", "Upto 6% Cashback", "https://www.myntra.com", "Sale Live Now"),
            ("Ajio", "Fashion", "Upto 7% Cashback", "https://www.ajio.com", "Diwali Edit"),
            ("Nykaa", "Beauty", "Upto 6% Cashback", "https://www.nykaa.com", "Sale Live Now"),
            ("Meesho", "Fashion", "Flat 12% Cashback", "https://www.meesho.com", "Hot Deal")
        ]
        cursor.executemany("INSERT INTO stores (name, category, cashback_rate, target_url, badge) VALUES (?, ?, ?, ?, ?)", stores_data)

    # Default Test User
    cursor.execute("SELECT COUNT(*) FROM users WHERE id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO users (id, name, email, phone, password, referral_code, confirmed_balance, pending_balance, referred_by, referral_bonus_given)
            VALUES (1, 'Amit Chaudhary', 'amitkr5993@gmail.com', '9876543210', '123456', 'AMIT2001', 500.0, 150.0, NULL, 0)
        ''')
    else:
        # Ensure default test user has phone and password set
        cursor.execute('''
            UPDATE users 
            SET phone = COALESCE(phone, '9876543210'),
                password = COALESCE(password, '123456')
            WHERE id = 1
        ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully with all tables.")