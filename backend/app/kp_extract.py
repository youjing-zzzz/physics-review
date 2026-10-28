"""从章节标题里拆知识点。

不是所有节都等于一个知识点：`2.1.1 二分法原理` 是"原理"型，
`2.3.2 牛顿迭代法的收敛性` 是"分析"型，学习成本差一倍。
这个差别直接决定它在 50/60/80 三档里该出现在哪一档，所以必须显式标注。

这里用**后缀规则**而不是让模型自由发挥：
规则可测、可解释、零成本，而且错了能一眼看出是哪条规则错了。
模型只在规则覆盖不到时兜底（后续接入 LLM 时再加）。
"""

from __future__ import annotations

from dataclasses import dataclass

# (后缀关键词, 类型, 认知深度 1-4, 预计掌握分钟)
TYPE_RULES: list[tuple[str, str, int, int]] = [
    ("原理", "原理", 2, 25),
    ("定义", "定义", 1, 10),
    ("概念", "概念", 1, 12),
    ("定理", "定理", 3, 35),
    ("公式", "公式", 2, 20),
    ("推导", "推导", 4, 40),
    ("证明", "证明", 4, 40),
    ("性质", "性质", 1, 10),
    ("方法", "方法", 2, 30),
    ("步骤", "方法", 2, 30),
    ("算法", "方法", 3, 35),
    ("收敛性", "分析", 3, 30),
    ("误差", "分析", 2, 25),
    ("稳定性", "分析", 3, 30),
    ("条件数", "分析", 3, 30),
    ("病态", "分析", 3, 30),
    ("应用", "应用", 2, 25),
    ("例题", "应用", 2, 20),
    ("加速", "方法", 3, 30),
]

DEFAULT = ("概念", 1, 15)


@dataclass
class KP:
    code: str
    chapter_no: str
    name: str
    type: str
    depth: int
    cost_min: int

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "chapter_no": self.chapter_no,
            "name": self.name,
            "type": self.type,
            "depth": self.depth,
            "cost_min": self.cost_min,
        }


def classify(title: str) -> tuple[str, int, int]:
    """标题 -> (类型, 深度, 分钟)。按规则表顺序匹配，先匹配更专有的。"""
    for kw, kind, depth, cost in TYPE_RULES:
        if kw in title:
            return kind, depth, cost
    return DEFAULT


def extract(nodes: list[dict], course_id: str) -> list[KP]:
    """把目录树拆成知识点列表。level>=2 的节点才算知识点。"""
    out: list[KP] = []

    def walk(items: list[dict]) -> None:
        for n in items:
            if n.get("level", 1) >= 2:
                kind, depth, cost = classify(n["title"])
                out.append(KP(
                    code=f"{course_id}.{n['no']}",
                    chapter_no=n["no"],
                    name=n["title"],
                    type=kind,
                    depth=depth,
                    cost_min=cost,
                ))
            walk(n.get("children", []))

    walk(nodes)
    return out
