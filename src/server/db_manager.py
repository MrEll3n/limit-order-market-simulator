import sqlite3

def create_user_db(db_path='users.db'):
    """
    Create a SQLite database for user management and insert initial users.
    :param db_path: Path to the SQLite database file.
    """

    # Connect to the SQLite database (or create it if it doesn't exist)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # Roles reference table — single source of truth for valid roles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            name        TEXT PRIMARY KEY,
            description TEXT NOT NULL
        )
    ''')

    # Seed the three built-in roles
    cursor.executemany(
        "INSERT OR IGNORE INTO roles (name, description) VALUES (?, ?)",
        [
            ("user",  "Regular human trader registered via the web frontend"),
            ("admin", "Administrator with access to management endpoints"),
            ("bot",   "Algorithmic trading bot using the FIX protocol"),
        ],
    )

    # Create the users table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            email    TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL,
            role     TEXT    NOT NULL DEFAULT 'user' REFERENCES roles(name)
        )
    ''')

    # Add role column to existing databases that were created before this migration
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    except Exception:
        pass  # Column already exists

    # Create the refresh_tokens table for JWT refresh token storage
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token      TEXT    PRIMARY KEY,
            email      TEXT    NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked    INTEGER NOT NULL DEFAULT 0
        )
    ''')

    # Create audit_log table — records every REST API call
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   INTEGER NOT NULL,
            email       TEXT,
            role        TEXT,
            method      TEXT    NOT NULL,
            path        TEXT    NOT NULL,
            status_code INTEGER NOT NULL,
            ip          TEXT
        )
    ''')

    # Insert initial bot accounts (role = 'bot')
    # Passwords are stored as plaintext here — bot accounts authenticate
    # via FIX protocol (UUID), not via the REST /api/auth/login endpoint.
    initial_bots = [
        'market_maker',
        'liquidity_generator',
        'lstm_trader',
        'momentum_trader_percentage_change',
        'momentum_trader_RSI',
        'momentum_trader_SMA',
        'momentum_trader_EMA',
        'ql_trader',
        'range_trader',
        'linear_trader',
        'ridge_trader',
        'lasso_trader',
        'bayesian_trader',
        'random_forest_trader',
        'scalping_trader',
        'spoofing_trader',
        'swing_trader',
        'test_trader',
    ]

    for email in initial_bots:
        try:
            cursor.execute(
                "INSERT INTO users (email, password, role) VALUES (?, ?, 'bot')",
                (email, 'password123'),
            )
        except sqlite3.IntegrityError:
            # Already exists — make sure role is set to 'bot'
            cursor.execute(
                "UPDATE users SET role='bot' WHERE email=? AND role='user'",
                (email,),
            )
        except sqlite3.Error as e:
            print(f"Error inserting bot {email}: {e}")

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = 'users.db'
    create_user_db(db_path)
