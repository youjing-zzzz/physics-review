-- 划重点 · 大学物理期末复习助手
-- 数据模型 v1
--
-- 设计原则（技术文档会展开）：
--   1) 一切重要性可追溯：exam_stats 存原始真题标注，聚合分数由代码计算，
--      不把模型的主观"重要性评分"落库 —— 否则无法解释、无法复现。
--   2) 章节树与知识点分离：同一知识点在不同教材版次里可能落在不同章节。
--   3) 三档清单不落库：按需用参数（学校画像 + 目标分数）实时计算，
--      换学校、换目标分不需要重建数据。

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id        INTEGER PRIMARY KEY,
    title     TEXT NOT NULL,
    edition   TEXT,
    publisher TEXT,
    subject   TEXT NOT NULL DEFAULT '大学物理',
    UNIQUE (title, edition)
);

CREATE TABLE IF NOT EXISTS chapters (
    id         INTEGER PRIMARY KEY,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    parent_id  INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    no         TEXT,      -- 章号/节号：'5' 或 '5.3'
    title      TEXT NOT NULL,
    level      INTEGER NOT NULL CHECK (level IN (1, 2)),  -- 1=章 2=节
    page_start INTEGER,
    page_end   INTEGER
);

CREATE TABLE IF NOT EXISTS kps (
    id         INTEGER PRIMARY KEY,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    code       TEXT UNIQUE NOT NULL,   -- 稳定标识，如 phys.mech.newton.ideal
    name       TEXT NOT NULL,
    type       TEXT,                   -- 定义/定理/公式/计算/实验
    depth      INTEGER CHECK (depth BETWEEN 1 AND 4),  -- 认知深度
    cost_min   INTEGER,                -- 预计掌握分钟数（认知成本）
    page       INTEGER,
    summary    TEXT
);

-- 知识点依赖边：错题回退时沿 prereq 反向走
CREATE TABLE IF NOT EXISTS kp_edges (
    src  INTEGER NOT NULL REFERENCES kps(id) ON DELETE CASCADE,
    dst  INTEGER NOT NULL REFERENCES kps(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'prereq',
    PRIMARY KEY (src, dst, kind)
);

-- 检索块：按知识点切，不按固定字数切
CREATE TABLE IF NOT EXISTS chunks (
    id      INTEGER PRIMARY KEY,
    kp_id   INTEGER REFERENCES kps(id) ON DELETE CASCADE,
    page    INTEGER,
    text    TEXT NOT NULL,
    tokens  INTEGER,
    vec_ref TEXT
);

-- 真题标注：重要性分数的唯一来源
CREATE TABLE IF NOT EXISTS exam_stats (
    id          INTEGER PRIMARY KEY,
    kp_id       INTEGER NOT NULL REFERENCES kps(id) ON DELETE CASCADE,
    year        INTEGER,
    score       REAL,     -- 该题分值
    qtype       TEXT,     -- 选择/填空/计算/证明
    school_tier TEXT      -- 985 / 一本 / 二本
);

CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY,
    kp_id       INTEGER REFERENCES kps(id) ON DELETE CASCADE,
    tier        INTEGER CHECK (tier IN (50, 60, 80)),
    stem        TEXT NOT NULL,
    answer      TEXT,
    explanation TEXT,
    difficulty  INTEGER CHECK (difficulty BETWEEN 1 AND 5),
    source      TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY,
    session_id  TEXT NOT NULL,
    question_id INTEGER REFERENCES questions(id),
    correct     INTEGER NOT NULL CHECK (correct IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chapters_book   ON chapters(book_id, no);
CREATE INDEX IF NOT EXISTS idx_kps_chapter     ON kps(chapter_id);
CREATE INDEX IF NOT EXISTS idx_exam_kp         ON exam_stats(kp_id);
CREATE INDEX IF NOT EXISTS idx_attempt_session ON attempts(session_id);
