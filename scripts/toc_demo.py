"""手动验证目录解析：给一段 OCR 文本，打印还原出的章节树。

用法：
    python scripts/toc_demo.py data/ocr-cache/inbox/xxx.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.toc import parse  # noqa: E402


def render(nodes, indent: int = 0) -> None:
    for n in nodes:
        print("  " * indent + f"[{n['no']}] {n['title']}  (L{n['level']})")
        render(n["children"], indent + 1)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true", help="同时打印 JSON")
    args = ap.parse_args()

    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    result = parse(text)

    print(f"覆盖率：{result['coverage']}  （识别 {result['matched']} / 候选 {result['considered']} 行）")
    print("--- 章节树 ---")
    render(result["nodes"])

    if result["skipped"]:
        print("\n--- 没认出来的行（前 10）---")
        for s in result["skipped"]:
            print(f"  {s}")

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(result["nodes"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
