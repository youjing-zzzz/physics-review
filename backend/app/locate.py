"""章节定位：把一段 OCR 出来的文字，落到具体章节。

为什么不用向量检索做这一步？
因为输入是"复习场景的短文本 + OCR 噪声"，向量容易漂到相邻章节；
而物理教材的章节有很强的关键词指纹（「力矩」「转动惯量」几乎只出现在刚体转动）。
先用关键词指纹做确定性打分，可解释、可复现，也方便把"为什么判成第 4 章"展示给用户。
向量检索留给后面"知识点级"的召回。

打分规则：
- 每个关键词有权重（越专有越高）
- 命中次数按 log 衰减，避免某章靠一个高频词刷分
- 置信度 = 最高分 / 总分，低于阈值就走 to-confirm
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# 章节关键词指纹（大学物理通用骨架，与具体教材版次无关）
CHAPTER_KEYWORDS: dict[str, tuple[str, dict[str, float]]] = {
    "1": ("质点运动学", {
        "运动方程": 3.0, "位移": 2.0, "路程": 2.0, "速度": 1.5, "加速度": 1.5,
        "圆周运动": 2.5, "抛体": 2.5, "切向": 2.0, "法向": 2.0, "质点": 1.0,
    }),
    "2": ("牛顿定律", {
        "牛顿第二定律": 3.0, "受力": 1.5, "摩擦力": 2.0, "惯性系": 2.5,
        "滑轮": 1.5, "张力": 1.5, "牛顿": 1.0,
    }),
    "3": ("动量守恒和能量守恒", {
        "动量守恒": 3.0, "冲量": 2.5, "动能定理": 3.0, "机械能守恒": 3.0,
        "势能": 2.0, "碰撞": 2.5, "做功": 1.5, "保守力": 2.5, "功": 1.0,
    }),
    "4": ("刚体的转动", {
        "转动惯量": 3.5, "力矩": 3.0, "角动量": 3.0, "角加速度": 2.5,
        "角速度": 2.0, "定轴": 2.5, "刚体": 2.5, "圆盘": 1.5, "转动": 1.5,
    }),
    "5": ("静电场", {
        "电场强度": 3.0, "电势": 2.5, "高斯定理": 3.0, "库仑": 2.5,
        "电通量": 2.5, "点电荷": 2.0, "电荷": 1.0, "电场": 1.5,
    }),
    "6": ("静电场中的导体和电介质", {
        "电介质": 3.0, "静电屏蔽": 3.0, "电容": 2.5, "极化": 2.5,
        "导体": 1.5, "击穿": 2.0,
    }),
    "7": ("恒定磁场", {
        "磁感应强度": 3.0, "安培力": 2.5, "洛伦兹": 3.0, "毕奥": 3.0,
        "磁通量": 2.5, "磁矩": 2.5, "磁力矩": 2.5, "磁场": 1.5, "线圈": 1.0,
    }),
    "8": ("电磁感应 电磁场", {
        "法拉第": 3.0, "楞次": 3.0, "感应电动势": 3.0, "自感": 2.5,
        "互感": 2.5, "位移电流": 2.5, "麦克斯韦": 2.5, "涡旋电场": 2.5,
    }),
    "9": ("振动", {
        "简谐": 3.0, "振幅": 2.0, "相位": 2.0, "单摆": 2.5, "阻尼": 2.0,
        "振动": 1.5, "周期": 1.0,
    }),
    "10": ("波动", {
        "波长": 2.0, "波速": 2.0, "驻波": 2.5, "多普勒": 2.5,
        "波动方程": 3.0, "相干": 2.0, "波节": 2.5, "波腹": 2.5,
    }),
    "11": ("光学", {
        "双缝": 3.0, "衍射": 2.5, "偏振": 2.5, "光程": 2.5, "光栅": 2.5,
        "干涉条纹": 2.5, "折射率": 2.0, "半波损失": 2.5,
    }),
    "12": ("气体动理论", {
        "理想气体": 2.5, "自由度": 2.5, "速率分布": 3.0, "平均自由程": 3.0,
        "气体动理论": 3.0, "压强": 1.5, "分子": 1.0,
    }),
    "13": ("热力学基础", {
        "热力学第一定律": 3.0, "等温": 2.0, "绝热": 2.5, "熵": 3.0,
        "卡诺": 2.5, "循环": 2.0, "摩尔热容": 2.5, "热机": 2.0,
    }),
    "14": ("相对论", {
        "洛伦兹变换": 3.0, "相对论": 2.5, "质能": 2.5, "时间膨胀": 3.0,
        "尺缩": 2.5, "光速不变": 3.0,
    }),
    "15": ("量子物理", {
        "光电效应": 3.0, "德布罗意": 3.0, "波函数": 2.5, "不确定性": 2.5,
        "氢原子": 2.0, "康普顿": 2.5, "量子": 1.5,
    }),
}

# 低于这个置信度就交给用户确认，不硬下结论
CONFIRM_THRESHOLD = 0.45

# 绝对下限（惨痛教训）：只看比例会被"全篇只命中一个弱词"骗到 1.0。
# 真实反例：一份《数值分析》目录因为出现"牛顿迭代法"，被以置信度 1.0 判成物理第 2 章。
# 所以除了比例，还要求绝对得分与命中词数同时达标。
MIN_SCORE = 3.0
MIN_KEYWORDS = 2


@dataclass
class ChapterHit:
    no: str
    title: str
    score: float
    hits: list[str]
    confidence: float = 0.0  # 由 locate() 填，= 本章得分 / 所有章得分之和


def _normalize(text: str) -> str:
    # OCR 常把标点认成全角/半角混合，统一后再匹配
    return re.sub(r"\s+", "", text)


def locate(text: str, top: int = 3) -> dict:
    """返回 {status, best, candidates}。

    status: confident / confirm / unknown
    """
    body = _normalize(text)
    if not body:
        return {"status": "unknown", "reason": "文本为空", "best": None, "candidates": []}

    scored: list[ChapterHit] = []
    for no, (title, keys) in CHAPTER_KEYWORDS.items():
        hits: list[str] = []
        raw = 0.0
        for kw, weight in keys.items():
            n = body.count(kw)
            if n:
                hits.append(f"{kw}×{n}")
                raw += weight * (1 + math.log(n))  # 次数取对数，避免单词刷分
        if raw > 0:
            scored.append(ChapterHit(no=no, title=title, score=round(raw, 2), hits=hits))

    if not scored:
        return {"status": "unknown", "reason": "没有命中任何章节关键词", "best": None, "candidates": []}

    scored.sort(key=lambda h: h.score, reverse=True)
    total = sum(h.score for h in scored)
    for h in scored:
        h.confidence = round(h.score / total, 3)

    candidates = [
        {"no": h.no, "title": h.title, "score": h.score, "confidence": h.confidence, "hits": h.hits[:5]}
        for h in scored[:top]
    ]
    best = candidates[0]

    # 三档判定：证据不足 → unknown；证据够但分散 → confirm；集中且够强 → confident
    if best["score"] < MIN_SCORE or len(best["hits"]) < MIN_KEYWORDS:
        return {
            "status": "unknown",
            "reason": "命中太少，可能不属于本课程（或这张图不是目录页）",
            "best": None,
            "candidates": candidates,
        }

    if best["confidence"] >= CONFIRM_THRESHOLD:
        return {"status": "confident", "reason": "", "best": best, "candidates": candidates}

    return {
        "status": "confirm",
        "reason": "命中分散或不够强，建议让用户确认章节",
        "best": best,
        "candidates": candidates,
    }
