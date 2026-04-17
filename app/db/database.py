"""SQLite config CRUD — save, load, list, delete named mission profiles."""
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent / "configs.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS configs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL UNIQUE,
    params    TEXT    NOT NULL,
    note      TEXT    DEFAULT '',
    created   TEXT    DEFAULT (datetime('now')),
    updated   TEXT    DEFAULT (datetime('now'))
);
"""


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_CREATE_SQL)
    con.commit()
    return con


# ── CRUD ────────────────────────────────────────────────────────────────────

def save_config(name: str, params: Dict[str, Any], note: str = "") -> Dict[str, Any]:
    """Insert or replace a named config. Returns the saved row."""
    payload = json.dumps(params)
    with _conn() as con:
        con.execute(
            """
            INSERT INTO configs (name, params, note, updated)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(name) DO UPDATE SET
                params  = excluded.params,
                note    = excluded.note,
                updated = datetime('now')
            """,
            (name, payload, note),
        )
    return load_config(name)


def load_config(name: str) -> Optional[Dict[str, Any]]:
    """Return a config row by name, or None if not found."""
    with _conn() as con:
        row = con.execute(
            "SELECT id, name, params, note, created, updated FROM configs WHERE name = ?",
            (name,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id":      row["id"],
        "name":    row["name"],
        "params":  json.loads(row["params"]),
        "note":    row["note"],
        "created": row["created"],
        "updated": row["updated"],
    }


def list_configs() -> List[Dict[str, Any]]:
    """Return all configs (metadata only, no full params)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, name, note, created, updated FROM configs ORDER BY updated DESC"
        ).fetchall()
    return [
        {
            "id":      r["id"],
            "name":    r["name"],
            "note":    r["note"],
            "created": r["created"],
            "updated": r["updated"],
        }
        for r in rows
    ]


def delete_config(name: str) -> bool:
    """Delete a config by name. Returns True if a row was deleted."""
    with _conn() as con:
        cur = con.execute("DELETE FROM configs WHERE name = ?", (name,))
    return cur.rowcount > 0


def rename_config(old_name: str, new_name: str) -> Optional[Dict[str, Any]]:
    """Rename a config. Returns updated row, or None if old_name not found.
    Raises ValueError if new_name already exists."""
    try:
        with _conn() as con:
            cur = con.execute(
                "UPDATE configs SET name = ?, updated = datetime('now') WHERE name = ?",
                (new_name, old_name),
            )
    except sqlite3.IntegrityError:
        raise ValueError(f"Config '{new_name}' already exists")
    if cur.rowcount == 0:
        return None
    return load_config(new_name)
