"""
Lightweight SQLite persistence so contracts survive a Streamlit rerun /
app restart. No external DB needed — works out of the box on Streamlit
Community Cloud (ephemeral disk is fine for a demo/MVP; swap in a hosted
Postgres later if you need durability across redeploys).
"""

import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager
from models import Contract

DB_PATH = "contracts.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def add_contract(c: Contract) -> int:
    c.created_at = c.created_at or datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO contracts (data, created_at) VALUES (?, ?)",
            (json.dumps(c.to_dict()), c.created_at),
        )
        return cur.lastrowid


def update_contract(contract_id: int, c: Contract):
    with get_conn() as conn:
        conn.execute(
            "UPDATE contracts SET data = ? WHERE id = ?",
            (json.dumps(c.to_dict()), contract_id),
        )


def delete_contract(contract_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))


def get_all_contracts():
    with get_conn() as conn:
        rows = conn.execute("SELECT id, data FROM contracts ORDER BY id DESC").fetchall()
    contracts = []
    for row in rows:
        d = json.loads(row["data"])
        d["id"] = row["id"]
        contracts.append(Contract(**d))
    return contracts


def get_contract(contract_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT id, data FROM contracts WHERE id = ?", (contract_id,)).fetchone()
    if not row:
        return None
    d = json.loads(row["data"])
    d["id"] = row["id"]
    return Contract(**d)
