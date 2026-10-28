"""目录指纹匹配：判断「这张照片的目录」和「这本书的目录」是不是同一本。

为什么需要它：
- 教材版本极多（第 5/6/7/8 版），章节号和标题会变；
- OCR 有错字（"牛顿—割线法" 可能变成 "牛贝一割线法"）；
- 各家站点的搜索只做精确匹配，错一个字就搜不到。

所以不能靠"书名搜"，要靠"结构比对"：
把目录归一化成标题序列，用「序列相似度 + 二元组重合度」打分，
选出最像的那一本，再拿它的 ISBN 去各站精确取资源。

归一化规则：
- 去掉编号（2.1 / 第三章）、标点、空白
- 全角转半角
- 只保留中文、字母、数字
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_NUM_PREFIX = re.compile(r"^(第?\s*[\d一二三四五六七八九十百]+[\.．、,，]?)+")
_NON_WORD = re.compile(r"[^\w\u4e00-\u9fff]+")


def normalize_title(t: str) -> str:
    s = unicodedata.normalize("NFKC", t or "")
    s = _NUM_PREFIX.sub("", s)
    s = _NON_WORD.sub("", s)
    return s.lower()


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def toc_similarity(photo_titles: list[str], book_titles: list[str]) -> float:
    """0..1。序列相似度与词元重合度各占一半。"""
    pa = [normalize_title(t) for t in photo_titles if normalize_title(t)]
    pb = [normalize_title(t) for t in book_titles if normalize_title(t)]
    if not pa or not pb:
        return 0.0

    seq = SequenceMatcher(None, "|".join(pa), "|".join(pb)).ratio()
    grams = jaccard(_bigrams("|".join(pa)), _bigrams("|".join(pb)))
    return round(0.6 * seq + 0.4 * grams, 4)


def rank(photo_titles: list[str], candidates: list[dict]) -> list[dict]:
    """candidates: [{id,title,toc:[...],isbn?,publisher?,year?}]

    返回按相似度降序的候选，附 score 与判定：
    >=0.72 认为"基本就是这本"，0.5-0.72 需要用户确认，<0.5 不建议采用。
    """
    scored = []
    for c in candidates:
        s = toc_similarity(photo_titles, c.get("toc") or [])
        if s >= 0.72:
            verdict = "match"
        elif s >= 0.50:
            verdict = "confirm"
        else:
            verdict = "unlikely"
        scored.append({**c, "score": s, "verdict": verdict})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored
