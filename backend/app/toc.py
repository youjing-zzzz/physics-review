"""目录结构解析：把 OCR 出来的文字，还原成章节树。

为什么这是主路径而不是关键词匹配：
用户拍的通常就是教材/讲义的目录页，天然带编号（2.1、2.1.1、第三章）。
编号是**科目无关**的结构信号，物理、数值分析、数据结构都长这样。
关键词指纹只适合做兜底（图里没编号时）。

OCR 噪声处理（都是实测遇到的）：
- 全角点号 2．1、间隔号 2·1、顿号 2、1
- 编号与标题之间没有空格：2.1二分法
- 页码/装饰符：2.1.2 二分法的计算步骤一（末尾的"一"是页码被识别成汉字）
- 水印行：扫描全能王 创建
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 编号：1 / 2.1 / 2.1.1 / 2.1.1.3，允许全角点与间隔号
NUM = r"\d{1,2}(?:[.．·・]\d{1,2}){0,3}"

# 行首编号 + 标题。标题允许紧贴编号，也允许有分隔符
LINE_RE = re.compile(rf"^\s*(?:第\s*)?({NUM})\s*[)）]?\s*[.．·、,，:：\-—\s]*(.+?)\s*$")
# "第X章 标题"
CHAP_RE = re.compile(r"^\s*第\s*([一二三四五六七八九十百\d]+)\s*章\s*(.*)$")
# 整行只有一个编号（OCR 常把编号与标题拆成两行）
PURE_NO = re.compile(rf"^\s*({NUM})\s*$")
# 纯噪声行
NOISE = re.compile(r"^(扫描全能王|第\s*\d+\s*页|共\s*\d+\s*页|目录|目\s*录|contents?)\b", re.I)

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass
class Node:
    no: str            # 2.1 / 2 / 第三章
    title: str
    level: int         # 1=章 2=节 3=小节
    parent: str | None = None
    children: list["Node"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "no": self.no,
            "title": self.title,
            "level": self.level,
            "parent": self.parent,
            "children": [c.to_dict() for c in self.children],
        }


def _clean_title(raw: str) -> str:
    t = raw.strip()
    # 去掉尾部页码：标题末尾的 一/二/三 或 数字，通常是页码被 OCR 成了汉字
    t = re.sub(r"[\s.．·…]+$", "", t)
    t = re.sub(r"(?<=[\u4e00-\u9fff])[一二三四五六七八九十]$", "", t)
    t = re.sub(r"[\s.．·…]+$", "", t)
    return t


def _level_of(no: str) -> int:
    return no.count(".") + 1


def _normalize_no(no: str) -> str:
    """把全角点、间隔号统一成半角点，并去掉尾部点。"""
    return re.sub(r"[.．·・]", ".", no).strip(".")


def parse(text: str) -> dict:
    """解析目录文本，返回 {nodes, coverage, skipped}。

    nodes     : 章节树（根节点列表）
    coverage  : 被识别成目录行的比例，低说明这张图可能不是目录页
    skipped   : 没认出来的行（前 10 条，便于人工看）
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    roots: list[Node] = []
    index: dict[str, Node] = {}
    matched = 0
    skipped: list[str] = []
    pending: str | None = None  # 上一个"只有编号、没有标题"的行

    for ln in lines:
        if NOISE.match(ln) or len(ln) < 3:
            continue

        # 编号独占一行：先记下，等下一行的标题来配
        pure = PURE_NO.match(ln)
        if pure:
            pending = _normalize_no(pure.group(1))
            continue

        chap = CHAP_RE.match(ln)
        if chap:
            raw_no, title = chap.group(1), chap.group(2)
            if raw_no.isdigit():
                no = str(int(raw_no))
            else:
                # 中文数字：只处理 1-10，够用
                no = str(CN_NUM.get(raw_no[0], raw_no))
            node = Node(no=no, title=_clean_title(title) or f"第{no}章", level=1)
            roots.append(node)
            index[no] = node
            matched += 1
            continue

        m = LINE_RE.match(ln)
        if not m and pending and re.search(r"[\u4e00-\u9fff]", ln):
            # 上一行是孤立编号，本行是标题：拼起来再走同一套解析
            m = LINE_RE.match(f"{pending} {ln}")
            pending = None
        if not m:
            skipped.append(ln)
            continue

        no, title = _normalize_no(m.group(1)), _clean_title(m.group(2))
        # 标题太短或全是符号，视为噪声
        if len(title) < 2 or not re.search(r"[\u4e00-\u9fffA-Za-z]", title):
            skipped.append(ln)
            continue

        node = Node(no=no, title=title, level=_level_of(no))

        # 挂到最近的上级：逐级截编号找父节点
        parts = no.split(".")
        parent = None
        for cut in range(len(parts) - 1, 0, -1):
            cand = ".".join(parts[:cut])
            if cand in index:
                parent = index[cand]
                break

        if parent:
            node.parent = parent.no
            parent.children.append(node)
        else:
            roots.append(node)
        index[no] = node
        matched += 1

    considered = len([ln for ln in lines if not NOISE.match(ln) and len(ln) >= 3])
    coverage = round(matched / considered, 3) if considered else 0.0

    return {
        "nodes": [r.to_dict() for r in roots],
        "coverage": coverage,
        "matched": matched,
        "considered": considered,
        "skipped": skipped[:10],
    }
