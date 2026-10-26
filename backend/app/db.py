"""SQLite 访问层。刻意只用标准库，避免早期引入 ORM 依赖。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # physics-review/
SCHEMA = ROOT / "backend" / "db" / "schema.sql"
DEFAULT_DB = ROOT / "data" / "app.db"


def db_path() -> Path:
    return Path(os.getenv("DB_PATH", str(DEFAULT_DB)))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> Path:
    """建库建表。幂等，可重复调用。"""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA.read_text(encoding="utf-8")
    with sqlite3.connect(path) as conn:
        conn.executescript(sql)
    return path


def counts() -> dict[str, int]:
    """给 /health 用的量化指标：表是不是真的建起来了。"""
    today_tables = ["books", "chapters", "kps", "kp_edges", "chunks", "exam_stats"]
    result: dict[str, int] = {}
    with connect() as conn:
        for table in today_tables:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            result[table] = int(row["n"])
    return result
