"""小工具：打印数据库里实际存在的表和行数。跑 D1/D2 的自检用。

用法：python scripts/check_db.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import db  # noqa: E402


def main() -> int:
    db.init_db()
    path = db.db_path()
    print(f"db: {path}")
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (name,) in rows:
            n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            print(f"  {name:<12} {n:>6} rows")
    print(f"\n共 {len(rows)} 张表")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
