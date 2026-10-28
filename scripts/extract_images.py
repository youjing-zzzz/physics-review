"""从 PDF 里把内嵌的 JPEG 图片抽出来（扫描件专用）。

为什么需要：扫描版试卷的文字层是空的，但页面其实是一张张 JPEG。
把它们抽出来交给 OCR，比先渲染 PDF 再截图简单得多，也不需要额外依赖。

用法：python scripts/extract_images.py
输出：data/ocr-cache/<pdf名>/page-XX-N.jpg
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "exams"
OUT = ROOT / "data" / "ocr-cache"


def safe(name: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name)


def extract_jpegs(pdf: Path) -> list[bytes]:
    """扫描 PDF 原始字节，取出所有 DCTDecode 的流。

    不做完整的 PDF 解析：DCTDecode 流就是裸 JPEG，
    直接找 SOI(FFD8) 到 EOI(FFD9) 即可，对扫描件足够稳。
    """
    data = pdf.read_bytes()
    found: list[bytes] = []
    pos = 0
    while True:
        start = data.find(b"\xff\xd8\xff", pos)
        if start < 0:
            break
        end = data.find(b"\xff\xd9", start)
        if end < 0:
            break
        found.append(data[start : end + 2])
        pos = end + 2
    return found


def main() -> int:
    if not SRC.exists():
        sys.exit(f"找不到目录：{SRC}")

    total = 0
    for pdf in sorted(SRC.glob("*.pdf")):
        # 有文字层的不用抽图
        if "24-25" in pdf.name:
            print(f"跳过（有文字层）: {pdf.name}")
            continue
        imgs = extract_jpegs(pdf)
        if not imgs:
            print(f"没有内嵌 JPEG: {pdf.name}")
            continue
        d = OUT / safe(pdf.stem)
        d.mkdir(parents=True, exist_ok=True)
        for i, blob in enumerate(imgs, start=1):
            f = d / f"page-{i:02d}-{len(blob)//1024}kb.jpg"
            f.write_bytes(blob)
        print(f"{pdf.name}: 抽出 {len(imgs)} 张 -> {d.relative_to(ROOT)}")
        total += len(imgs)

    print(f"\n共 {total} 张，放在 {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
