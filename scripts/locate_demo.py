"""手动验证章节定位：给一段文本，看它落到哪一章。

用法：
    python scripts/locate_demo.py data/ocr-cache/xxx/page-01-283kb.txt
    python scripts/locate_demo.py --text "刚体的转动惯量与力矩"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.locate import locate  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="包含文本的文件路径")
    ap.add_argument("--text", help="直接给一段文本")
    args = ap.parse_args()

    if args.text:
        text = args.text
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    else:
        ap.error("需要 file 或 --text")

    result = locate(text)
    print(f"状态：{result['status']}")
    if result["reason"]:
        print(f"原因：{result['reason']}")
    for c in result["candidates"]:
        print(f"  第{c['no']}章 {c['title']}  分数={c['score']} 置信度={c['confidence']}")
        print(f"    命中：{', '.join(c['hits'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
