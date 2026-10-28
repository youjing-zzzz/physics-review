"""书目元数据：书名、出版社、ISBN。

为什么用豆瓣：它是最稳定的中文书目源，搜索页服务端渲染、条目页有 ISBN。
拿到 ISBN 之后，再去任何站点都用 ISBN 精确取（ISBN 不会因为 OCR 错字而错）。

定位：只做**元数据**，不碰正文。正文/试读归各站自己的规则。
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
TIMEOUT = 10


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", "replace")


def search(keyword: str, limit: int = 8) -> list[dict]:
    """按关键词搜书，返回 [{id,url}]。豆瓣搜索页服务端渲染，可直接解析。"""
    url = "https://search.douban.com/book/subject_search?search_text=" + urllib.parse.quote(keyword)
    try:
        html = _get(url)
    except Exception:
        return []
    ids: list[str] = []
    for sid in re.findall(r"subject/(\d{5,9})", html):
        if sid not in ids:
            ids.append(sid)
    return [{"id": sid, "url": f"https://book.douban.com/subject/{sid}/"} for sid in ids[:limit]]


def subject(sid: str) -> dict | None:
    """抓条目页，抽标题/ISBN/出版社/出版年。失败返回 None。"""
    url = f"https://book.douban.com/subject/{sid}/"
    try:
        html = _get(url)
    except Exception:
        return None

    title = ""
    m = re.search(r"<title>\s*(.*?)\s*(?:\(豆瓣\))?\s*</title>", html, re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()

    isbn = ""
    # 豆瓣页面里 ISBN 常以纯数字出现在结构化数据里，不一定跟着 "ISBN:" 字样
    m = re.search(r"(97[89][\d]{10})", html)
    if m:
        isbn = m.group(1)

    publisher = ""
    m = re.search(r"出版社[：:]?\s*</span>\s*(?:<a[^>]*>)?([^<]{2,40})", html)
    if m:
        publisher = m.group(1).strip()

    year = ""
    m = re.search(r"出版年[：:]?\s*</span>\s*([\d]{4})", html)
    if m:
        year = m.group(1)

    if not title:
        return None
    return {"id": sid, "title": title, "isbn": isbn, "publisher": publisher,
            "year": year, "url": url}


def find(keyword: str, limit: int = 5) -> list[dict]:
    """搜索 + 逐个补元数据。条数受限，避免把豆瓣打爆。"""
    out = []
    for hit in search(keyword, limit=limit):
        s = subject(hit["id"])
        if s:
            out.append(s)
    return out
