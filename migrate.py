#!/usr/bin/env python3
"""Add missing columns to existing database."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////data/glitztracker.db")
db_path = DATABASE_URL.replace("sqlite:////", "/").replace("sqlite:///", "")

import sqlite3
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("PRAGMA table_info(users)")
existing = {row[1] for row in cur.fetchall()}
print("Existing columns:", sorted(existing))

migrations = [
    ("notify_whatsapp", "INTEGER DEFAULT 0"),
    ("home_airport",    "TEXT DEFAULT ''"),
]

for col, definition in migrations:
    if col not in existing:
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            print(f"Added column: {col}")
        except Exception as e:
            print(f"Error adding {col}: {e}")
    else:
        print(f"Already exists: {col}")

conn.commit()
conn.close()
print("Migration complete.")
