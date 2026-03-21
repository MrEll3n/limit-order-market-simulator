import sqlite3

def create_user_db(db_path='users.db'):
    """
    Create a SQLite database for user management and insert initial users.
    :param db_path: Path to the SQLite database file.
    """

    # Connect to the SQLite database (or create it if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create the users table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')

    # Insert initial users - no web registration needed for these
    initial_users = [
        ('market_maker', 'password123'),
        ('liquidity_generator', 'password123'),
        ('lstm_trader', 'password123'),
        ('momentum_trader_percentage_change', 'password123'),
        ('momentum_trader_RSI', 'password123'),
        ('momentum_trader_SMA', 'password123'),
        ('momentum_trader_EMA', 'password123'),
        ('ql_trader', 'password123'),
        ('range_trader', 'password123'),
        ('linear_trader', 'password123'),
        ('ridge_trader', 'password123'),
        ('lasso_trader', 'password123'),
        ('bayesian_trader', 'password123'),
        ('random_forest_trader', 'password123'),
        ('scalping_trader', 'password123'),
        ('spoofing_trader', 'password123'),
        ('swing_trader', 'password123'),
        ('test_trader', 'password123'),
    ]

    for email, password in initial_users:
        try:
            cursor.execute('INSERT INTO users (email, password) VALUES (?, ?)', (email, password))
        except sqlite3.IntegrityError:
            # Skip if the user already exists
            pass
        except sqlite3.Error as e:
            print(f"Error inserting user {email}: {e}")
            pass

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = 'users.db'
    create_user_db(db_path)
