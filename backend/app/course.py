"""科目判定：从章节标题判断这份目录属于哪门课。

设计要点（吃过亏的地方）：
- 只看比例会撒谎。上一次《数值分析》目录因为"牛顿迭代法"被判成物理第 2 章，
  置信度还是 1.0。所以这里同时要求「绝对得分」和「命中词数」达标，
  否则直接返回 unknown，让前端去问用户"这是哪门课"。
- 判定结果要带证据（命中了哪些词），用户能一眼看出为什么。

为什么用本地指纹而不是联网搜索：
MVP 阶段没有搜索 API key，也不能让"判科目"依赖网络抖动。
联网留给下一步：确认之后再去补"这个知识点具体讲什么"。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 课程指纹：关键词 -> 权重（越专有越高）
COURSE_FINGERPRINTS: dict[str, dict] = {
    "numerical_analysis": {
        "name": "数值分析 / 计算方法",
        "keywords": {
            "二分法": 3.0, "不动点迭代": 3.0, "牛顿迭代": 3.0, "割线法": 3.0,
            "迭代加速": 2.5, "插值": 2.5, "样条": 2.5, "数值积分": 3.0,
            "龙格": 2.5, "最小二乘": 2.5, "矩阵分解": 2.5, "收敛阶": 2.5,
            "病态": 2.0, "条件数": 2.5, "有效数字": 2.5, "截断误差": 2.5,
            "数值稳定性": 3.0, "线性方程组的数值": 3.0,
        },
    },
    "college_physics": {
        "name": "大学物理",
        "keywords": {
            "质点运动学": 3.0, "牛顿定律": 2.5, "动量守恒": 3.0, "转动惯量": 3.0,
            "力矩": 2.5, "静电场": 3.0, "高斯定理": 3.0, "电势": 2.5,
            "安培": 2.5, "洛伦兹": 3.0, "电磁感应": 3.0, "简谐": 2.5,
            "驻波": 2.5, "衍射": 2.5, "偏振": 2.5, "热力学": 2.5, "熵": 2.5,
        },
    },
    "calculus": {
        "name": "高等数学",
        "keywords": {
            "极限": 2.5, "导数": 2.5, "微分中值定理": 3.0, "不定积分": 3.0,
            "定积分": 2.5, "级数": 2.5, "偏导数": 2.5, "重积分": 3.0,
            "曲线积分": 3.0, "微分方程": 2.0, "泰勒": 2.5, "洛必达": 3.0,
        },
    },
    "linear_algebra": {
        "name": "线性代数",
        "keywords": {
            "行列式": 3.0, "矩阵": 2.0, "向量组": 3.0, "特征值": 3.0,
            "特征向量": 3.0, "相似对角化": 3.0, "二次型": 3.0, "秩": 2.0,
            "线性方程组": 2.0, "正交": 2.0,
        },
    },
    "data_structure": {
        "name": "数据结构",
        "keywords": {
            "链表": 3.0, "栈": 2.0, "队列": 2.0, "二叉树": 3.0, "红黑树": 3.0,
            "图": 1.0, "最短路径": 3.0, "排序": 2.0, "哈希": 2.5,
            "时间复杂度": 2.5, "堆": 2.0, "并查集": 3.0,
        },
    },
}

# 判定门槛：比例之外，还要绝对分与命中词数
MIN_SCORE = 4.0
MIN_KEYWORDS = 2
MIN_CONFIDENCE = 0.5


@dataclass
class CourseGuess:
    course_id: str
    name: str
    score: float
    confidence: float
    hits: list[str] = field(default_factory=list)


def _titles(nodes: list[dict]) -> list[str]:
    out: list[str] = []
    for n in nodes:
        out.append(n.get("title", ""))
        out.extend(_titles(n.get("children", [])))
    return out


def detect(nodes: list[dict]) -> dict:
    """输入 toc.parse() 的 nodes，返回 {status, course, candidates, evidence}。"""
    text = " ".join(_titles(nodes))
    if not text.strip():
        return {"status": "unknown", "reason": "目录为空", "course": None, "candidates": []}

    scored: list[CourseGuess] = []
    for cid, spec in COURSE_FINGERPRINTS.items():
        raw = 0.0
        hits: list[str] = []
        for kw, w in spec["keywords"].items():
            if kw in text:
                raw += w
                hits.append(kw)
        if raw > 0:
            scored.append(CourseGuess(course_id=cid, name=spec["name"], score=round(raw, 2),
                                      confidence=0.0, hits=hits))

    if not scored:
        return {"status": "unknown", "reason": "没有命中任何课程指纹", "course": None, "candidates": []}

    scored.sort(key=lambda g: g.score, reverse=True)
    total = sum(g.score for g in scored)
    for g in scored:
        g.confidence = round(g.score / total, 3)

    top = scored[0]
    candidates = [{"course_id": g.course_id, "name": g.name, "score": g.score,
                   "confidence": g.confidence, "hits": g.hits} for g in scored[:3]]

    # 双下限：得分够高、命中够多、比例够集中，三条同时满足才算判出来
    if top.score < MIN_SCORE or len(top.hits) < MIN_KEYWORDS or top.confidence < MIN_CONFIDENCE:
        return {
            "status": "unknown",
            "reason": "证据不足，无法确定科目，建议让用户选择",
            "course": None,
            "candidates": candidates,
        }

    return {
        "status": "confident",
        "reason": "",
        "course": {"course_id": top.course_id, "name": top.name,
                   "confidence": top.confidence, "evidence": top.hits},
        "candidates": candidates,
    }
