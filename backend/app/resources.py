"""资源发现：给定「学校 + 课程」，找出这门课真实的资料源。

为什么这一步不能用 LLM：
LLM 从目录"编"知识点，等于没有依据。比赛评委一问"依据哪本教材"就崩。
所以必须先有**来源**，内容才有出处。

现实约束（实测得出）：
- 高校培养方案/教学大纲**多数公开**，可直接抓（已验证西安科技大学理学院可访问）；
- 但每所学校站点结构不同，没法写一个通用解析器 → 用"种子表 + 探测"：
  种子给入口，探测给可达性与命中情况，剩下的交给用户判断。
- 抓不到时不编：明确返回"没找到"，并给通用搜索链接当线索。

可信度分级（输出必须带）：
  curriculum(0.9) > syllabus(0.8) > portal(0.85) > mooc(0.55) > search(0.45)
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "schools.yml"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ReviewCompiler/0.2"


def load_seed() -> dict:
    if not SEED.exists():
        return {"schools": [], "default_sources": [], "textbook_hints": [], "course_keywords": []}
    return yaml.safe_load(SEED.read_text(encoding="utf-8")) or {}


def _match_school(seed: dict, school: str) -> dict | None:
    if not school:
        return None
    key = school.strip().lower()
    for item in seed.get("schools", []):
        names = [item["name"], *item.get("aliases", [])]
        for n in names:
            nl = str(n).lower()
            if nl and (nl in key or key in nl):
                return item
    return None


def candidates(school: str, course: str) -> list[dict]:
    """返回候选源列表（未探测）。学校没命中时只返回通用兜底。"""
    seed = load_seed()
    out: list[dict] = []

    hit = _match_school(seed, school)
    if hit:
        for src in hit.get("sources", []):
            out.append({**src, "origin": f"种子：{hit['name']}"})

    for src in seed.get("default_sources", []):
        url = src["url"].format(school=urllib.parse.quote(school or ""),
                                course=urllib.parse.quote(course or ""))
        out.append({**src, "url": url, "origin": "通用兜底"})

    return out


def _strip_html(raw: str) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_textbook(text: str, hints: list[str]) -> list[str]:
    """从页面文本里找"指定教材"的线索。

    只做线索抽取，不猜书名：找不到就返回空。
    """
    found: list[str] = []
    for hint in hints:
        for m in re.finditer(hint, text):
            window = text[max(0, m.start() - 10): m.start() + 90]
            book = re.search(r"《([^》]{2,40})》", window)
            if book:
                snippet = f"{hint}：《{book.group(1)}》"
                if snippet not in found:
                    found.append(snippet)
    return found[:5]


def _extract_links(raw: str, base: str) -> list[dict]:
    """抽取页面上的附件/大纲链接。

    培养方案页通常把教材与大纲放在附件里（PDF/DOC），
    正文里抽不到文字，但链接本身就是"资源入口"，必须给用户。
    """
    out: list[dict] = []
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw, re.S | re.I):
        href, label = m.group(1), _strip_html(m.group(2))
        if not label or len(label) < 2:
            continue
        if not re.search(r"(大纲|培养方案|课程|教材|方案|计划|附件)", label):
            continue
        if href.lower().startswith(("javascript:", "#", "mailto:")):
            continue
        url = urllib.parse.urljoin(base, href)
        if url.startswith("http") and url not in [o["url"] for o in out]:
            out.append({"text": label[:40], "url": url})
        if len(out) >= 8:
            break
    return out


def probe(src: dict, course: str, hints: list[str], keywords: list[str],
          timeout: int = 8) -> dict:
    """探测一个源：是否可达、页面标题、是否与课程相关、有没有教材线索。"""
    result = {
        "name": src.get("name", ""),
        "url": src.get("url", ""),
        "kind": src.get("kind", ""),
        "trust": src.get("trust", 0.0),
        "note": src.get("note", ""),
        "origin": src.get("origin", ""),
        "status": "unknown",
        "title": "",
        "chars": 0,
        "matched": [],
        "textbook": [],
    }
    try:
        req = urllib.request.Request(src["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        text = _strip_html(raw)
        result["chars"] = len(text)
        result["title"] = (re.search(r"<title>(.*?)</title>", raw, re.S | re.I) or [None, ""])[1].strip()
        result["matched"] = [k for k in keywords if k in text]
        if course and course in text:
            result["matched"].append(course)
        result["textbook"] = extract_textbook(text, hints)
        result["links"] = _extract_links(raw, src["url"])
        result["status"] = "ok" if result["matched"] else "unrelated"
    except Exception as exc:
        result["status"] = f"error:{type(exc).__name__}"
    return result


def discover(school: str, course: str, limit: int = 5) -> dict:
    seed = load_seed()
    hints = seed.get("textbook_hints", [])
    keywords = seed.get("course_keywords", [])
    school_hit = _match_school(seed, school)

    cands = candidates(school, course)
    # 优先探测种子源；通用搜索只给链接，不去抓（抓搜索结果没意义）
    probed = []
    for src in cands:
        if src.get("kind") == "search":
            probed.append({**src, "status": "link_only", "title": "", "chars": 0,
                           "matched": [], "textbook": []})
            continue

    for src in cands:
        if src.get("kind") == "search":
            continue
        if len(probed) >= limit:
            break
        probed.append(probe(src, course, hints, keywords))

    ok = [p for p in probed if p["status"] == "ok" and p["textbook"]]
    return {
        "school": school,
        "course": course,
        "school_matched": bool(school_hit),
        "school_note": "" if school_hit else "该学校不在种子表中，只给通用线索；需要人工补充入口",
        "sources": probed,
        "textbooks": [t for p in ok for t in p["textbook"]],
    }
