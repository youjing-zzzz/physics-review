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
from . import db, kp_extract, resources, retrieval, tiering, toc
from .schema import PROFILES, Tier

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "backend" / "static"
OCR_SCRIPT = ROOT / "scripts" / "ocr_windows.ps1"
UPLOADS = ROOT / "data" / "ocr-cache" / "uploads"


if FastAPI:

    class AnalyzeIn(BaseModel):
        text: str
        profile: str = "normal"
        enrich: bool = True      # 是否联网补"这个知识点讲什么"
        enrich_limit: int = 6    # 每次最多补几个，控制演示耗时


def _attach_content(tiered: dict, kps: list[dict], limit: int) -> dict:
    """给 50 分档的前若干个知识点补联网摘要。

    只补 50 档：那是"保底必须学"的部分，也是用户第一眼要看的。
    超时或查不到就留空，绝不编内容。
    """
    name_by_code = {k["code"]: k["name"] for k in kps}
    targets = [i["code"] for i in tiered["tiers"]["50"]["items"]][:limit]
    found: dict[str, dict] = {}
    for code in targets:
        name = name_by_code.get(code)
        if not name:
            continue
        found[code] = retrieval.enrich(name)

    for tier in tiered["tiers"].values():
        for item in tier["items"]:
            hit = found.get(item["code"])
            if hit:
                item["content"] = hit.get("text", "")
                item["source"] = hit.get("url", "")
                item["content_status"] = hit.get("status", "")

    return {
        "attempted": len(targets),
        "ok": sum(1 for v in found.values() if v.get("status") == "ok"),
        "failed": [v["term"] for v in found.values() if v.get("status") != "ok"],
    }


def _analyze(text: str, profile_key: str, enrich: bool = False, enrich_limit: int = 6) -> dict:
    profile = PROFILES.get(profile_key) or PROFILES["normal"]
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
            "tier_shift": profile.tier_shift,
        },
    )

    kp_dicts = [k.to_dict() for k in kps]
    enrichment = None
    if enrich and kp_dicts:
        enrichment = _attach_content(tiered, kp_dicts, max(0, min(enrich_limit, 12)))

    lines = [ln for ln in text.splitlines() if ln.strip()]
    avg_len = (sum(len(ln) for ln in lines) / len(lines)) if lines else 0

    # 页面类型粗判：目录页的行短、带编号；正文页的行长、是句子
    if tree["matched"] and not tree["fallback"]:
        page_type = "toc"
        hint = ""
    elif tree["fallback"] and avg_len > 15:
        page_type = "text"
        hint = "这看起来是正文页而不是目录页：没有编号且每行较长。请拍教材的目录页（章节列表）"
    elif tree["fallback"]:
        page_type = "no-numbers"
        hint = "没有识别到编号，已按行序编号，请核对顺序是否正确"
    else:
        page_type = "unknown"
        hint = "没有识别到任何目录行，请检查图片是否清晰、是否真的是目录页"

    return {
        "tree": tree,
        "course": guess,
        "kps": [k.to_dict() for k in kps],
        "tiers": tiered,
        "enrichment": enrichment,
        # 诊断信息：解析出 0 个节点时，让用户能立刻看出是"图没识别好"还是"格式不是目录"
        "diagnostics": {
            "lines": len(lines),
            "considered": tree["considered"],
            "matched": tree["matched"],
            "head": lines[:3],
            "page_type": page_type,
            "avg_line_len": round(avg_len, 1),
            "hint": hint,
        },
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
            return JSONResponse(_analyze(body.text, body.profile, body.enrich, body.enrich_limit))
        except Exception as exc:  # 解析失败要给出人能看懂的原因
            return JSONResponse({"error": f"分析失败：{exc}"}, status_code=500)

    @app.post("/api/resources")
    def find_resources(payload: dict) -> JSONResponse:
        school = str(payload.get("school", "")).strip()
        course = str(payload.get("course", "")).strip()
        if not school and not course:
            return JSONResponse({"error": "至少填学校或课程"}, status_code=400)
        try:
            return JSONResponse(resources.discover(school, course))
        except Exception as exc:
            return JSONResponse({"error": f"资源发现失败：{exc}"}, status_code=500)

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
