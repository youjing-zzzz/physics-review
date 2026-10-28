"""把真题 PDF 抽成纯文本，供后续切题与知识点标注。

用法：
    python scripts/extract_exams.py --probe      # 只看每份前 400 字，判断有没有文字层
    python scripts/extract_exams.py              # 全量导出到 data/parsed/exams/

设计取舍：
- 不做 OCR。扫描件（无文字层）在这里会被标记为 needs_ocr，交给 OCR 模块处理，
  避免"抽出一堆空白却以为是缺题"这种沉默失败。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit("缺少 pypdf：请先运行 python -m pip install pypdf")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "exams"
OUT = ROOT / "data" / "parsed" / "exams"

CJK = re.compile(r"[\u4e00-\u9fff]")


def clean(text: str) -> str:
    """去掉公式字体留下的私有区字符和孤立代理项。

    PDF 里的数学符号常用私有区码位（U+E000–U+F8FF）或落单的 UTF-16 代理项，
    这些东西既不能写盘也不能显示，先剥掉；公式的完整还原是后续 OCR/LLM 的事。
    """
    out = []
    for ch in text:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF or 0xE000 <= cp <= 0xF8FF:
            continue
        out.append(ch)
    return "".join(out)


def cjk_ratio(text: str) -> float:
    """中文占比。用来判断抽出来的是正文还是乱码。"""
    if not text:
        return 0.0
    return len(CJK.findall(text)) / len(text)


def extract(pdf: Path) -> dict:
    reader = PdfReader(str(pdf))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # 单页失败不影响整体
            text = ""
            print(f"  ! page {i} 抽取失败: {exc}")
        pages.append({"page": i, "text": clean(text)})

    joined = "\n".join(p["text"] for p in pages)
    chars = len(joined.strip())
    ratio = cjk_ratio(joined)

    if chars < 100:
        status = "needs_ocr"          # 没有文字层，扫描件
    elif ratio < 0.15:
        status = "garbled"            # 有字符但基本不是中文，多半编码坏了
    else:
        status = "ok"

    return {
        "file": pdf.name,
        "pages": len(pages),
        "chars": chars,
        "cjk_ratio": round(ratio, 3),
        "status": status,
        "text_pages": pages,
    }


def main() -> int:
    # Windows 控制台默认 GBK，遇到公式字体的私有区字符会直接崩
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="只打印摘要与前 400 字")
    args = ap.parse_args()

    if not SRC.exists():
        sys.exit(f"找不到真题目录：{SRC}")

    pdfs = sorted(SRC.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"{SRC} 下没有 PDF")

    results = []
    for pdf in pdfs:
        print(f"\n=== {pdf.name}")
        r = extract(pdf)
        results.append(r)
        print(f"  页数={r['pages']} 字符={r['chars']} 中文占比={r['cjk_ratio']} 状态={r['status']}")
        if args.probe:
            head = "\n".join(p["text"] for p in r["text_pages"])[:400]
            print("  --- 前 400 字 ---")
            print("  " + head.replace("\n", "\n  "))
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", pdf.stem)
            txt = OUT / f"{stem}.txt"
            txt.write_text("\n\n".join(f"# page {p['page']}\n{p['text']}" for p in r["text_pages"]),
                           encoding="utf-8")
            print(f"  -> {txt.relative_to(ROOT)}")

    summary = OUT / "summary.json"
    if not args.probe:
        OUT.mkdir(parents=True, exist_ok=True)
        summary.write_text(
            json.dumps([{k: v for k, v in r.items() if k != "text_pages"} for r in results],
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n摘要 -> {summary.relative_to(ROOT)}")

    bad = [r["file"] for r in results if r["status"] != "ok"]
    if bad:
        print(f"\n需要 OCR 或人工处理的文件：{', '.join(bad)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
