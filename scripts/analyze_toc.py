"""端到端：一张目录照片的 OCR 文本 -> 科目 + 章节树 + 知识点 -> 数据库。

用法：
    python scripts/analyze_toc.py data/ocr-cache/orient/xxx.txt
    python scripts/analyze_toc.py data/ocr-cache/orient/xxx.txt --save
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import course, db, ingest, kp_extract, toc  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--save", action="store_true", help="写入 data/app.db")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = Path(args.file).read_text(encoding="utf-8", errors="replace")

    # 建表是幂等的；不先建，connect() 会打开一个空文件导致 no such table
    db.init_db()

    tree = toc.parse(text)
    print(f"[1/3] 目录解析：覆盖率 {tree['coverage']}，识别 {tree['matched']} 个节点")

    guess = course.detect(tree["nodes"])
    if guess["status"] == "confident":
        c = guess["course"]
        print(f"[2/3] 科目判定：{c['name']}（置信度 {c['confidence']}）")
        print(f"      证据：{'、'.join(c['evidence'])}")
        course_id = c["course_id"]
        course_name = c["name"]
    else:
        print(f"[2/3] 科目判定：无法确定（{guess['reason']}）")
        for cand in guess["candidates"]:
            print(f"      候选：{cand['name']} 分={cand['score']} 置信度={cand['confidence']}")
        print("      -> 产品上这里应该弹一个「这是哪门课？」让用户选；本次不写库")
        course_id = "unknown"
        course_name = "未知课程"

    kps = kp_extract.extract(tree["nodes"], course_id)
    print(f"[3/3] 知识点拆分：{len(kps)} 个")
    for kp in kps[:15]:
        print(f"      {kp.code:<18} {kp.name:<24} 类型={kp.type:<3} 深度={kp.depth} 成本={kp.cost_min}min")
    if len(kps) > 15:
        print(f"      ... 其余 {len(kps) - 15} 个略")

    if args.save and course_id != "unknown":
        conn = db.connect()
        try:
            stat = ingest.save(conn, book_title=f"{course_name}（照片导入）",
                               course_name=course_name, nodes=tree["nodes"],
                               kps=[k.to_dict() for k in kps])
        finally:
            conn.close()
        print(f"      已写库：{stat}")

    if args.json:
        print(json.dumps({
            "coverage": tree["coverage"],
            "course": guess,
            "kps": [k.to_dict() for k in kps],
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
