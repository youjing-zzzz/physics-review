"""HTTP 接口 + 静态页面。

链路：图片 → OCR → 目录树 → 科目 → 知识点 → 三档裁剪 → 页面展示。

设计取舍：
- OCR 走本机 PowerShell（Windows 自带引擎，零依赖），接口只负责转交，不重写识别逻辑。
- 分析接口接收**文本**而不是图片，这样前端可以先预览/修改 OCR 结果再分析；
  用户改一个错字，胜过我们在后端猜。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from fastapi import FastAPI, File, UploadFile
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel
except ImportError:  # 允许没装依赖时做静态检查
    FastAPI = None  # type: ignore[assignment]

from . import course as course_mod
from . import db, kp_extract, tiering, toc
from .schema import PROFILES, Tier

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "backend" / "static"
OCR_SCRIPT = ROOT / "scripts" / "ocr_windows.ps1"
UPLOADS = ROOT / "data" / "ocr-cache" / "uploads"


class AnalyzeIn(BaseModel):
    text: str
    profile: str = "tier2_normal"


def _analyze(text: str, profile_key: str) -> dict:
    profile = PROFILES.get(profile_key) or PROFILES["tier2_normal"]
    tree = toc.parse(text)
    guess = course_mod.detect(tree["nodes"])

    if guess["status"] == "confident":
        course_id = guess["course"]["course_id"]
    else:
        course_id = "unknown"

    kps = kp_extract.extract(tree["nodes"], course_id)
    tiered = tiering.build(
        [k.to_dict() for k in kps],
        {
            "key": profile.key,
            "label": profile.label,
            "depth_cap": profile.depth_cap,
            "allow_proof": profile.allow_proof,
            "weight_bias": profile.weight_bias,
        },
    )

    return {
        "tree": tree,
        "course": guess,
        "kps": [k.to_dict() for k in kps],
        "tiers": tiered,
    }


def _run_ocr(path: Path) -> str:
    """调用本机 Windows OCR。返回识别文本；失败时抛 RuntimeError。"""
    if not OCR_SCRIPT.exists():
        raise RuntimeError("找不到 OCR 脚本 scripts/ocr_windows.ps1")
    txt = path.with_suffix(".txt")
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(OCR_SCRIPT), "-Path", str(path), "-OutDir", str(path.parent),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if proc.returncode != 0 or not txt.exists():
        raise RuntimeError("OCR 失败（脚本返回非零，或没有生成文本）")
    return txt.read_text(encoding="utf-8", errors="replace")


app = FastAPI(title="划重点 · 期末复习范围编译器", version="0.2.0") if FastAPI else None


def _build_app() -> None:
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "db": str(db.db_path()), "tables": db.counts()}

    @app.get("/api/profiles")
    def profiles() -> dict:
        return {
            "profiles": [
                {"key": p.key, "label": p.label, "depth_cap": p.depth_cap,
                 "allow_proof": p.allow_proof}
                for p in PROFILES.values()
            ],
            "tiers": [t.value for t in Tier],
        }

    @app.post("/api/analyze")
    def analyze(body: AnalyzeIn) -> JSONResponse:
        if not body.text.strip():
            return JSONResponse({"error": "文本为空"}, status_code=400)
        try:
            return JSONResponse(_analyze(body.text, body.profile))
        except Exception as exc:  # 解析失败要给出人能看懂的原因
            return JSONResponse({"error": f"分析失败：{exc}"}, status_code=500)

    @app.post("/api/ocr")
    async def ocr(file: UploadFile = File(...)) -> JSONResponse:
        UPLOADS.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
        target = UPLOADS / f"upload{suffix}"
        with target.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        try:
            text = _run_ocr(target)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        return JSONResponse({"text": text, "chars": len(text)})

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/static/{name}")
    def static_file(name: str):
        return FileResponse(STATIC / name)


if FastAPI:
    _build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
