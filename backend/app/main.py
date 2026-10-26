"""最小可用 API。D1 只做三件事：活着、库建好了、画像能列出来。"""

from __future__ import annotations

import os

try:
    from fastapi import FastAPI
except ImportError:  # 允许在没装依赖时 import 本模块做静态检查
    FastAPI = None  # type: ignore[assignment]

from . import db
from .schema import PROFILES, Tier

app = FastAPI(title="划重点 · 大学物理期末复习助手", version="0.1.0") if FastAPI else None


def _build_app():
    @app.get("/health")
    def health() -> dict:
        tables = db.counts()
        empty = all(n == 0 for n in tables.values())
        return {
            "status": "ok",
            "db": str(db.db_path()),
            "empty": empty,
            "tables": tables,
            "hint": "库是空的：把教材解析结果灌进来（D2/D3）后这里会有数" if empty else "",
        }

    @app.get("/api/profiles")
    def profiles() -> dict:
        return {
            "profiles": [
                {
                    "key": p.key,
                    "label": p.label,
                    "depth_cap": p.depth_cap,
                    "allow_proof": p.allow_proof,
                }
                for p in PROFILES.values()
            ],
            "tiers": [t.value for t in Tier],
        }

    return app


if FastAPI:
    _build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=bool(os.getenv("RELOAD")),
    )
