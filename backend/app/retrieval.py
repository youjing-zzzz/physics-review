"""联网补内容：把「2.1.1 二分法原理」变成"这东西讲什么"。

为什么先接维基百科，而不是通用搜索：
- 有稳定 API、结构化返回、许可清晰；
- 词条质量对本场景够用（定义 + 原理 + 收敛性都有）；
- 通用搜索要抓 HTML、抗反爬、还容易被封，不适合比赛现场演示。

代价（写进文档）：维基对中文工科教材的覆盖不均衡，
冷门知识点会查不到。所以接口必须"查不到就返回空"，不能编。

缓存策略：同一个词条只抓一次，落 sources/contents 表。
演示时第一次慢（每次 1-2 秒），之后是本地命中。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

WIKI_API = "https://zh.wikipedia.org/w/api.php"
UA = "ReviewCompiler/0.2 (student project; contact: unknown)"
TIMEOUT = 8


def _get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def _clean(text: str, limit: int = 220) -> str:
    t = " ".join((text or "").split())
    # 去掉维基常见的"本条目…"式声明，但保留正文
    cut = t.find("。", 60)
    if cut > 0 and limit > len(t[:cut]):
        t = t[: cut + 1]
    return t[:limit]


# 领域词：摘要里一个都没有，说明抓到了同名的别的意思
# 真实案例：「二分法」词条讲的是"把事物分成两部分"，不是方程求根
DOMAIN_WORDS = ("方程", "根", "迭代", "收敛", "数值", "函数", "定理", "算法", "误差", "近似")


def _looks_relevant(text: str) -> bool:
    return any(w in text for w in DOMAIN_WORDS)


def _search_title(term: str, context: str = "数值分析") -> str | None:
    try:
        data = _get({
            "action": "query", "format": "json", "list": "search",
            "srsearch": f"{term} {context}", "srlimit": 3,
        })
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            if term[:2] in title:
                return title
    except Exception:
        return None
    return None


def fetch(term: str) -> dict | None:
    """返回 {term,title,url,text,status}；查不到返回 None。"""
    try:
        data = _get({
            "action": "query", "format": "json", "prop": "extracts",
            "exintro": 1, "explaintext": 1, "redirects": 1,
            "titles": term,
        })
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid == "-1" or "missing" in page:
                break
            text = _clean(page.get("extract", ""))
            if not text:
                break
            return {
                "term": term,
                "title": page.get("title", term),
                "url": "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(page.get("title", term)),
                "text": text,
                "status": "ok",
            }
    except Exception as exc:  # 网络/超时/解析失败一律降级，不能拖垮主流程
        return {"term": term, "title": term, "url": "", "text": "",
                "status": f"error:{type(exc).__name__}"}
    return {"term": term, "title": term, "url": "", "text": "", "status": "not_found"}


def enrich(name: str) -> dict:
    """给一个知识点名补内容：原词 → 退化后缀 → 搜索定位，逐级降级。"""
    hit = fetch(name)
    if hit and hit["status"] == "ok" and _looks_relevant(hit["text"]):
        return hit

    # "二分法的计算步骤" 这种带后缀的，退化成 "二分法"
    for suffix in ("的收敛性", "的计算步骤", "原理", "公式", "及其几何意义",
                   "求解代数方程", "迭代法", "法"):
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            base = name[: -len(suffix)]
            alt = fetch(base)
            if alt and alt["status"] == "ok" and _looks_relevant(alt["text"]):
                alt["matched_by"] = f"退化关键词：{base}"
                return alt

    # 搜索兜底：同名词条抓错了意思时，用领域词重新定位
    title = _search_title(name)
    if title and title != name:
        alt = fetch(title)
        if alt and alt["status"] == "ok" and alt["text"]:
            alt["matched_by"] = f"搜索定位：{title}"
            if not _looks_relevant(alt["text"]):
                alt["status"] = "weak_match"  # 找到了，但可能不是你要的那个意思
            return alt

    if hit and hit.get("text"):
        hit["status"] = "weak_match"
        return hit
    return hit or {"term": name, "title": name, "url": "", "text": "", "status": "not_found"}
