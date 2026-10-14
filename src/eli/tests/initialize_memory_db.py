#!/usr/bin/env python3
# initialize_memory_db.py
import sqlite3
import os
from pathlib import Path

def initialize_database():
    # Path to database
    db_path = Path.home() / ".eli_memory.db"
    
    print(f"Initializing SQLite3 database at: {db_path}")
    
    # Create directory if it doesn't exist
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect to database (creates it if it doesn't exist)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create memories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            embedding BLOB,
            metadata TEXT,
            source TEXT
        )
    ''')
    
    # Create indexes for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON memories(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags ON memories(tags)')
    
    # Create full-text search table for better search
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts 
        USING fts5(content, tags, tokenize="porter")
    ''')
    
    # Create triggers to keep FTS table in sync
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories
        BEGIN
            INSERT INTO memories_fts(rowid, content, tags)
            VALUES (new.id, new.content, new.tags);
        END;
    ''')
    
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories
        BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, tags)
            VALUES('delete', old.id, old.content, old.tags);
        END;
    ''')
    
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories
        BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, tags)
            VALUES('delete', old.id, old.content, old.tags);
            INSERT INTO memories_fts(rowid, content, tags)
            VALUES (new.id, new.content, new.tags);
        END;
    ''')
    
    # Check if table is empty and add some example data
    cursor.execute("SELECT COUNT(*) FROM memories")
    count = cursor.fetchone()[0]
    
    if count == 0:
        print("Adding example memories...")
        examples = [
            (1696000000.0, "ELI system initialized successfully.", "system,boot", '{"type": "system"}'),
            (1696000100.0, "User prefers dark mode interface.", "preference,ui", '{"type": "preference"}'),
            (1696000200.0, "Spotify is the default media player.", "media,preference", '{"type": "preference"}'),
        ]
        
        cursor.executemany('''
            INSERT INTO memories (timestamp, content, tags, metadata)
            VALUES (?, ?, ?, ?)
        ''', examples)
    
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM memories")
    final_count = cursor.fetchone()[0]
    print(f"Database initialized with {final_count} memory records.")
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables created:", [t[0] for t in tables])
    
    conn.close()
    print("✅ Memory database initialization complete!")
    return db_path

if __name__ == "__main__":
    db_path = initialize_database()
    print(f"\nDatabase ready at: {db_path}")
    print("You can inspect it with: sqlite3 ~/.eli_memory.db")
