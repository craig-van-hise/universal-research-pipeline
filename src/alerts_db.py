import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "../data/alerts.db")

def init_db():
    """Initialize the alerts database and create tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            search_query TEXT NOT NULL,
            search_source TEXT NOT NULL,
            last_run TIMESTAMP,
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"✅ Database initialized at {DB_PATH}")

def add_subscription(email: str, query: str, source: str) -> int:
    """Add a new alert subscription."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO subscriptions (user_email, search_query, search_source, last_run)
        VALUES (?, ?, ?, ?)
    """, (email, query, source, datetime.now()))
    
    subscription_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return subscription_id

def get_active_subscriptions() -> List[Dict]:
    """Retrieve all active subscriptions."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM subscriptions WHERE active = 1
        ORDER BY created_at DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_all_subscriptions() -> List[Dict]:
    """Retrieve all subscriptions (active and inactive)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM subscriptions
        ORDER BY created_at DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def update_last_run(subscription_id: int, timestamp: datetime):
    """Update the last run timestamp for a subscription."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE subscriptions
        SET last_run = ?
        WHERE id = ?
    """, (timestamp, subscription_id))
    
    conn.commit()
    conn.close()

def toggle_subscription(subscription_id: int, active: bool):
    """Enable or disable a subscription."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE subscriptions
        SET active = ?
        WHERE id = ?
    """, (1 if active else 0, subscription_id))
    
    conn.commit()
    conn.close()

def delete_subscription(subscription_id: int):
    """Delete a subscription."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
    
    conn.commit()
    conn.close()

def reset_dates_for_testing():
    """Reset all last_run dates to 30 days ago for testing purposes."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    cursor.execute("""
        UPDATE subscriptions
        SET last_run = ?
    """, (thirty_days_ago,))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"✅ Reset {affected} subscription(s) to 30 days ago for testing")

if __name__ == "__main__":
    # Test the database
    init_db()
    print("Database initialized successfully!")
