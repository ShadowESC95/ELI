# eli/brain/auth.py
import sqlite3
import hashlib
import secrets
from pathlib import Path

from eli.brain.paths import get_paths

DB_PATH = Path(get_paths().config_dir) / "users.db"

class AuthManager:
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    salt TEXT,
                    created REAL,
                    preferences TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    token TEXT UNIQUE,
                    expires REAL
                )
            """)
    
    def create_user(self, username: str, password: str):
        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac(
            'sha256', password.encode(), salt.encode(), 100000
        ).hex()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, created) VALUES (?, ?, ?, ?)",
                (username, password_hash, salt, time.time())
            )
    
    def login(self, username: str, password: str) -> Optional[str]:
        # Verify password, create session token
        # Return token or None
        pass
