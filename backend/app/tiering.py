"""三档裁剪：把知识点清单编译成「考 50 / 60 / 80 分分别该学什么」。

产品命门不是"排序"，是**决定哪些不学**。所以每档都是一份完整可执行清单。

两种定档来源，绝不混用却不说清：

1. **有真题统计**（exam_stats）：按频次与分值打分，用分数阈值定档。
2. **没有真题**：按知识点类型定档（先验），并在理由里写明「按类型估算」。
   假装有数据是最容易被评委一问就崩的地方。

两个硬约束来自学校画像，是「不要讲太深」这句需求的可执行版本：
- `depth_cap`：认知深度上限
- `allow_proof`：是否允许出现证明/推导类

踩过的坑（v1 的 bug）：门槛设成了升序（50 < 60 < 80），配上"取第一个满足的档"，
导致所有分数够高的点都落进 50 档，三档清单一模一样。
正确语义是：分数越高 → 越是保底要学的 → 档位越靠前（50）。
所以门槛必须**降序**，且先验模式下直接按类型映射，别硬凑分数。
"""

from __future__ import annotations

from dataclasses import dataclass

TIER_ORDER = ["50", "60", "80"]

# 有真题时：分数越高越靠前档。门槛必须降序。
THRESHOLDS = {"50": 0.58, "60": 0.46, "80": 0.34}

# 无真题时：按类型定档（先验）。这是"可解释"的底线——
# 至少能回答"为什么它在 50 档"：因为它是定义/概念。
TYPE_TIER = {
    "定义": "50", "概念": "50",
    "方法": "60", "公式": "60", "定理": "60", "原理": "60",
    "分析": "80", "应用": "80", "推导": "80", "证明": "80",
}


@dataclass
class Tiered:
    kp: dict
    score: float
    min_tier: str      # 最低从哪一档开始要求；"skip" 表示不学
    reason: str
    basis: str         # 真题 / 类型先验


def _score(kp: dict, stats: dict | None) -> tuple[float, str, str]:
    if stats and stats.get("count"):
        freq = min(1.0, stats["count"] / 3.0)
        avg = min(1.0, (stats.get("avg_score") or 0) / 10.0)
        cost = min(1.0, kp.get("cost_min", 20) / 40.0)
        score = round(0.45 * freq + 0.25 * avg + 0.20 * (1 - cost) + 0.10 * 0.5, 4)
        return score, "真题", f"真题出现 {stats['count']} 次，平均 {stats.get('avg_score', 0):.1f} 分"
    cost = min(1.0, kp.get("cost_min", 20) / 40.0)
    score = round(0.55 * (1 - cost) + 0.45 * (1.0 - min(1.0, kp.get("depth", 1) / 4.0)), 4)
    return score, "类型先验", f"暂无真题数据，按「{kp.get('type', '概念')}」类型与学习成本估算"


def _depth_ok(kp: dict, profile: dict, tier: str) -> bool:
    cap = profile.get("depth_cap", 2)
    if tier == "80" and profile.get("allow_proof"):
        cap += 1
    if kp.get("depth", 1) > cap:
        return False
    if kp.get("type") in {"证明", "推导"} and not profile.get("allow_proof"):
        return False
    return True


def _min_tier(kp: dict, profile: dict, score: float, has_stats: bool) -> str | None:
    if has_stats:
        bias = profile.get("weight_bias", 1.0)
        for t in TIER_ORDER:
            if score >= THRESHOLDS[t] / bias and _depth_ok(kp, profile, t):
                return t
        return None

    # 先验：按类型定档，再按深度上限往后挪；挪不动就排除
    start = TYPE_TIER.get(kp.get("type", "概念"), "60")
    for t in TIER_ORDER[TIER_ORDER.index(start):]:
        if _depth_ok(kp, profile, t):
            return t
    return None


def build(kps: list[dict], profile: dict, stats_by_code: dict[str, dict] | None = None) -> dict:
    stats_by_code = stats_by_code or {}
    has_stats = bool(stats_by_code)
    label = profile.get("label", profile.get("key", ""))

    tiers: dict[str, list[Tiered]] = {t: [] for t in TIER_ORDER}
    evaluated: list[Tiered] = []

    for kp in kps:
        score, basis, note = _score(kp, stats_by_code.get(kp["code"]))
        mt = _min_tier(kp, profile, score, has_stats)

        if mt is None:
            capped = kp.get("depth", 1) > profile.get("depth_cap", 2)
            why = (f"深度 {kp.get('depth')} 超过「{label}」的上限 "
                   f"{profile.get('depth_cap')}，按『不学』处理") if capped else "分数低于 80 分档门槛"
            evaluated.append(Tiered(kp=kp, score=score, min_tier="skip",
                                    reason=f"{note}；{why}", basis=basis))
            continue

        evaluated.append(Tiered(kp=kp, score=score, min_tier=mt,
                                reason=f"{note}；定档依据：{basis}", basis=basis))

    # 累积分档：80 包含 60 包含 50
    for item in evaluated:
        if item.min_tier == "skip":
            continue
        start = TIER_ORDER.index(item.min_tier)
        for t in TIER_ORDER[start:]:
            tiers[t].append(item)

    def pack(items: list[Tiered], t: str) -> dict:
        return {
            "count": len(items),
            "minutes": sum(i.kp.get("cost_min", 0) for i in items),
            "items": [
                {
                    "code": i.kp["code"],
                    "name": i.kp["name"],
                    "type": i.kp.get("type"),
                    "depth": i.kp.get("depth"),
                    "cost_min": i.kp.get("cost_min"),
                    "score": i.score,
                    "basis": i.basis,
                    "reason": i.reason,
                    "new_in_this_tier": i.min_tier == t,
                }
                for i in items
            ],
        }

    return {
        "profile": profile,
        "tiers": {t: pack(tiers[t], t) for t in TIER_ORDER},
        "skipped": [
            {"code": i.kp["code"], "name": i.kp["name"], "score": i.score, "reason": i.reason}
            for i in evaluated if i.min_tier == "skip"
        ],
        "summary": {
            "total_kps": len(kps),
            "skipped": sum(1 for i in evaluated if i.min_tier == "skip"),
            "basis": "真题" if has_stats else "类型先验",
        },
    }
