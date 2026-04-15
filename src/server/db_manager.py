import logging
import os
import sqlite3
import bcrypt

def create_user_db(db_path='market.db'):
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

    def _hash(plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    # Insert initial admin account (role = 'admin')
    admin_email    = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_email or not admin_password:
        logging.warning("ADMIN_EMAIL or ADMIN_PASSWORD not set — skipping admin account creation.")
    else:
        try:
            cursor.execute(
                "INSERT INTO users (email, password, role) VALUES (?, ?, 'admin')",
                (admin_email, _hash(admin_password)),
            )
        except sqlite3.IntegrityError:
            cursor.execute("UPDATE users SET role='admin' WHERE email=?", (admin_email,))

    # Insert initial bot accounts (role = 'bot')
    # Passwords are read from environment variables and stored hashed with bcrypt.
    bot_password           = os.environ.get("BOT_PASSWORD")
    market_maker_email     = os.environ.get("MARKET_MAKER_EMAIL", "market_maker")
    market_maker_password  = os.environ.get("MARKET_MAKER_PASSWORD")
    liquidity_gen_email    = os.environ.get("LIQUIDITY_GENERATOR_EMAIL", "liquidity_generator")
    liquidity_gen_password = os.environ.get("LIQUIDITY_GENERATOR_PASSWORD")

    _DEFAULT = "changeme"
    missing = [name for name, val in [
        ("BOT_PASSWORD", bot_password),
        ("MARKET_MAKER_PASSWORD", market_maker_password),
        ("LIQUIDITY_GENERATOR_PASSWORD", liquidity_gen_password),
    ] if not val]
    if missing:
        logging.warning(
            "Bot passwords not set in environment (%s) — using insecure default '%s'.",
            ", ".join(missing), _DEFAULT,
        )

    bot_password           = bot_password or _DEFAULT
    market_maker_password  = market_maker_password or _DEFAULT
    liquidity_gen_password = liquidity_gen_password or _DEFAULT

    bot_passwords = {
        market_maker_email:  _hash(market_maker_password),
        liquidity_gen_email: _hash(liquidity_gen_password),
    }
    default_hash = _hash(bot_password)

    initial_bots = [
        market_maker_email,
        liquidity_gen_email,
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
        hashed = bot_passwords.get(email, default_hash)
        try:
            cursor.execute(
                "INSERT INTO users (email, password, role) VALUES (?, ?, 'bot')",
                (email, hashed),
            )
        except sqlite3.IntegrityError:
            # Already exists — make sure role is set to 'bot'
            cursor.execute(
                "UPDATE users SET role='bot' WHERE email=? AND role='user'",
                (email,),
            )
        except sqlite3.Error as e:
            print(f"Error inserting bot {email}: {e}")

    # Create the api_keys table for agent authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash   TEXT    NOT NULL UNIQUE,
            email      TEXT    NOT NULL REFERENCES users(email),
            name       TEXT    NOT NULL,
            created_at INTEGER NOT NULL,
            active     INTEGER NOT NULL DEFAULT 1
        )
    ''')

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    db_path = 'market.db'
    create_user_db(db_path)
