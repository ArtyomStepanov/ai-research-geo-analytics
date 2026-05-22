# agent/db.py
import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = Path("geo_chat.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Оптимизация для конкурентных записей
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                last_active TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                history TEXT NOT NULL
            )
        """)
        conn.commit()

def load_chat_history(chat_id: str) -> list[dict] | None:
    with get_db() as conn:
        row = conn.execute("SELECT history FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
        if row:
            conn.execute("UPDATE chats SET last_active = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE chat_id = ?", (chat_id,))
            return json.loads(row["history"])
    return None

def save_chat_history(chat_id: str, history: list[dict]):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO chats (chat_id, history) VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET history = ?, last_active = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        """, (chat_id, json.dumps(history), json.dumps(history)))