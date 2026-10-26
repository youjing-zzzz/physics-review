"""领域模型：知识点、学校画像、分档规则。

为什么把"学校难度"写成显式参数，而不是让模型自由发挥？
因为比赛评审（和用户）一定会问："这个知识点凭什么进 60 分档？"
答案必须是一个可复算的数字，而不是"模型觉得"。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tier(str, Enum):
    """目标分数档位。数字本身是标签，不是及格线。"""

    T50 = "50"
    T60 = "60"
    T80 = "80"


@dataclass(frozen=True)
class SchoolProfile:
    """学校难度画像。所有字段都会实际参与计算。"""

    key: str
    label: str
    depth_cap: int          # 允许讲到的最深认知层级（1..4）
    prereq_cap: int         # 允许的最长前置依赖链
    allow_proof: bool       # 是否出现证明题
    comprehensive: float    # 综合题权重系数
    weight_bias: float      # 真题分值权重偏差


# 先做两档，D4 再按真实真题分布校准
PROFILES: dict[str, SchoolProfile] = {
    "tier1_985": SchoolProfile(
        key="tier1_985",
        label="985 / 双一流",
        depth_cap=4,
        prereq_cap=4,
        allow_proof=True,
        comprehensive=0.35,
        weight_bias=1.15,
    ),
    "tier2_normal": SchoolProfile(
        key="tier2_normal",
        label="普通一本 / 二本",
        depth_cap=2,
        prereq_cap=2,
        allow_proof=False,
        comprehensive=0.15,
        weight_bias=0.95,
    ),
}


@dataclass
class KnowledgePoint:
    """内存中的知识点视图（对应 kps 表）。"""

    code: str
    name: str
    type: str = "定义"
    depth: int = 1
    cost_min: int = 20
    page: int | None = None
    summary: str = ""


def importance(
    *,
    freq: float,
    avg_score: float,
    cost_min: float,
    prereq_len: float,
) -> float:
    """知识点重要性打分 v0（D4 会被真题分布重新校准）。

    freq        : 近 N 年出现次数归一化 0..1
    avg_score   : 该点平均分值归一化 0..1
    cost_min    : 认知成本归一化 0..1（越大越难）
    prereq_len  : 前置链长度归一化 0..1（越大越靠后）

    权重刻意偏向"高频"而非"高分"：期末复习里，
    出现 5 次的选择题比出现 1 次的压轴题更值得优先学。
    """
    return round(
        0.45 * freq
        + 0.25 * avg_score
        + 0.20 * (1.0 - cost_min)
        + 0.10 * (1.0 - prereq_len),
        4,
    )


def assign_tier(score: float, profile: SchoolProfile) -> Tier:
    """按画像把知识点分到某一档。阈值随画像浮动。"""
    threshold_50 = 0.30 / profile.weight_bias
    threshold_60 = 0.48 / profile.weight_bias
    threshold_80 = 0.66 / profile.weight_bias

    if score >= threshold_80:
        return Tier.T80
    if score >= threshold_60:
        return Tier.T60
    if score >= threshold_50:
        return Tier.T50
    return Tier.T50  # 低于阈值也不直接丢弃，由调用方决定是否裁掉
