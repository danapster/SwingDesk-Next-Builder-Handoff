"""Swing Desk — local SQLite (WAL) repository.

Single writer, simple schema, versioned migrations. Data lives under
%LOCALAPPDATA%/SwingDesk on Windows or ~/.local/share/SwingDesk elsewhere,
mirroring the production storage contract.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import AlertRule, LifecycleState, Plan

SCHEMA_VERSION = 1

_MIGRATIONS: list[str] = [
    """
    CREATE TABLE plans (
        id TEXT PRIMARY KEY,
        broker_symbol TEXT NOT NULL,
        canonical_name TEXT NOT NULL,
        direction TEXT NOT NULL,
        entry REAL NOT NULL,
        stop REAL NOT NULL,
        target REAL NOT NULL,
        risk_percent REAL NOT NULL,
        volume REAL NOT NULL,
        thesis TEXT NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        engine_snapshot TEXT NOT NULL DEFAULT '',
        actual_fill REAL,
        realised_r REAL,
        behaviour_flags TEXT NOT NULL DEFAULT '[]',
        review_note TEXT NOT NULL DEFAULT '',
        review_completed INTEGER NOT NULL DEFAULT 0,
        closed_at TEXT
    );
    CREATE TABLE alerts (
        id TEXT PRIMARY KEY,
        broker_symbol TEXT NOT NULL,
        kind TEXT NOT NULL,
        level REAL NOT NULL,
        note TEXT NOT NULL,
        enabled INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        fired_at TEXT
    );
    CREATE TABLE alert_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at TEXT NOT NULL,
        message TEXT NOT NULL
    );
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
]


def data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "SwingDesk"
    d.mkdir(parents=True, exist_ok=True)
    (d / "exports").mkdir(exist_ok=True)
    return d


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (data_dir() / "swingdesk.db")
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ------------------------------------------------------------ migrations
    def _migrate(self) -> None:
        cur = self.conn.execute("PRAGMA user_version")
        current = cur.fetchone()[0]
        for i, script in enumerate(_MIGRATIONS[current:], start=current):
            with self.conn:
                self.conn.executescript(script)
                self.conn.execute(f"PRAGMA user_version={i + 1}")

    def close(self) -> None:
        """Close the SQLite handle explicitly (important for temp/self-test stores)."""
        self.conn.close()

    # ---------------------------------------------------------------- plans
    def save_plan(self, plan: Plan) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO plans (id, broker_symbol, canonical_name, direction, entry,
                     stop, target, risk_percent, volume, thesis, state, created_at, updated_at,
                     engine_snapshot, actual_fill, realised_r, behaviour_flags, review_note,
                     review_completed, closed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     state=excluded.state, updated_at=excluded.updated_at,
                     entry=excluded.entry, stop=excluded.stop, target=excluded.target,
                     risk_percent=excluded.risk_percent, volume=excluded.volume,
                     thesis=excluded.thesis, engine_snapshot=excluded.engine_snapshot,
                     actual_fill=excluded.actual_fill, realised_r=excluded.realised_r,
                     behaviour_flags=excluded.behaviour_flags,
                     review_note=excluded.review_note,
                     review_completed=excluded.review_completed,
                     closed_at=excluded.closed_at""",
                (plan.id, plan.broker_symbol, plan.canonical_name, plan.direction,
                 plan.entry, plan.stop, plan.target, plan.risk_percent, plan.volume,
                 plan.thesis, plan.state.value, plan.created_at, plan.updated_at,
                 plan.engine_snapshot, plan.actual_fill, plan.realised_r,
                 json.dumps(plan.behaviour_flags), plan.review_note,
                 1 if plan.review_completed else 0, plan.closed_at))

    def plans(self) -> list[Plan]:
        rows = self.conn.execute("SELECT * FROM plans ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            out.append(Plan(
                id=r["id"], broker_symbol=r["broker_symbol"],
                canonical_name=r["canonical_name"], direction=r["direction"],
                entry=r["entry"], stop=r["stop"], target=r["target"],
                risk_percent=r["risk_percent"], volume=r["volume"],
                thesis=r["thesis"], state=LifecycleState(r["state"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
                engine_snapshot=r["engine_snapshot"], actual_fill=r["actual_fill"],
                realised_r=r["realised_r"],
                behaviour_flags=json.loads(r["behaviour_flags"]),
                review_note=r["review_note"], review_completed=bool(r["review_completed"]),
                closed_at=r["closed_at"]))
        return out

    def delete_plan(self, plan_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM plans WHERE id=?", (plan_id,))

    # --------------------------------------------------------------- alerts
    def save_alert(self, rule: AlertRule) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO alerts (id, broker_symbol, kind, level, note, enabled,
                     created_at, fired_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled,
                     fired_at=excluded.fired_at, note=excluded.note""",
                (rule.id, rule.broker_symbol, rule.kind, rule.level, rule.note,
                 1 if rule.enabled else 0, rule.created_at, rule.fired_at))

    def alerts(self) -> list[AlertRule]:
        rows = self.conn.execute("SELECT * FROM alerts ORDER BY created_at DESC").fetchall()
        return [AlertRule(r["id"], r["broker_symbol"], r["kind"], r["level"], r["note"],
                          bool(r["enabled"]), r["created_at"], r["fired_at"]) for r in rows]

    def delete_alert(self, alert_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM alerts WHERE id=?", (alert_id,))

    def log_alert(self, message: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO alert_log (at, message) VALUES (?,?)",
                              (now_iso(), message))

    def alert_log(self, limit: int = 50) -> list[tuple[str, str]]:
        rows = self.conn.execute(
            "SELECT at, message FROM alert_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [(r["at"], r["message"]) for r in rows]

    # ------------------------------------------------------------- settings
    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"
