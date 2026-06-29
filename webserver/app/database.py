import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "hub.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                device_type   TEXT NOT NULL DEFAULT '',
                meta          TEXT NOT NULL DEFAULT '{}',
                registered_at REAL NOT NULL,
                last_heartbeat REAL,
                status        TEXT NOT NULL DEFAULT 'offline'
            )
        """)


# --- query helpers ---

def upsert_device(device_id: str, name: str, device_type: str, meta: dict) -> None:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO devices (id, name, device_type, meta, registered_at, status)
            VALUES (?, ?, ?, ?, ?, 'offline')
            ON CONFLICT(id) DO UPDATE SET
                name        = excluded.name,
                device_type = excluded.device_type,
                meta        = excluded.meta
        """, (device_id, name, device_type, json.dumps(meta), time.time()))


def update_heartbeat(device_id: str) -> bool:
    """Returns True if the device exists."""
    with get_db() as conn:
        cur = conn.execute("""
            UPDATE devices SET last_heartbeat = ?, status = 'online'
            WHERE id = ?
        """, (time.time(), device_id))
        return cur.rowcount > 0


def mark_stale_offline(max_age_s: float = 120.0) -> int:
    cutoff = time.time() - max_age_s
    with get_db() as conn:
        cur = conn.execute("""
            UPDATE devices SET status = 'offline'
            WHERE status = 'online' AND (last_heartbeat IS NULL OR last_heartbeat < ?)
        """, (cutoff,))
        return cur.rowcount


def get_device(device_id: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()


def list_devices() -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM devices ORDER BY registered_at DESC").fetchall()


def set_device_offline(device_id: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE devices SET status = 'offline' WHERE id = ?", (device_id,))


def delete_device(device_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        return cur.rowcount > 0
