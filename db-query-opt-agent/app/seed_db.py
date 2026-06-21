import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "demo.db")

def seed_database():
    # Remove existing db if it exists
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            value DECIMAL(10,2) NOT NULL
        )
    """)

    # Seed data
    users_data = [
        ('alice', 'alice@example.com', 1),
        ('bob', 'bob@example.com', 1),
        ('charlie', 'charlie@example.com', 0),
        ('diana', 'diana@example.com', 1)
    ]
    cursor.executemany("INSERT INTO users (username, email, active) VALUES (?, ?, ?)", users_data)

    orders_data = [
        (1, 'completed', 150.50),
        (1, 'pending', 45.00),
        (2, 'completed', 99.99),
        (3, 'cancelled', 250.00)
    ]
    cursor.executemany("INSERT INTO orders (user_id, status, amount) VALUES (?, ?, ?)", orders_data)

    metrics_data = [
        ('cpu_usage', 45.2),
        ('memory_usage', 82.5),
        ('disk_space', 15.0)
    ]
    cursor.executemany("INSERT INTO metrics (name, value) VALUES (?, ?)", metrics_data)

    conn.commit()
    conn.close()

    print(f"Database successfully seeded at {DB_PATH}")

if __name__ == "__main__":
    seed_database()
