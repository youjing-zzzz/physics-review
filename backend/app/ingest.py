"""把「目录树 + 知识点」落进数据库。

一张照片走到这里，才算真正变成可计算的数据：
books -> chapters -> kps。
"""

from __future__ import annotations

import sqlite3


def save(conn: sqlite3.Connection, *, book_title: str, course_name: str,
         nodes: list[dict], kps: list[dict]) -> dict:
    """写库并返回统计。重复导入同一本书会复用 book 记录。"""
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO books (title, edition, publisher, subject) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(title, edition) DO UPDATE SET subject=excluded.subject",
        (book_title, "", "", course_name),
    )
    book_id = cur.execute(
        "SELECT id FROM books WHERE title=? AND edition=?", (book_title, "")
    ).fetchone()[0]

    # 重复导入：先清掉旧章节（级联删除 kps）
    cur.execute("DELETE FROM chapters WHERE book_id=?", (book_id,))

    id_by_no: dict[str, int] = {}

    def walk(items: list[dict], parent_id: int | None) -> None:
        for n in items:
            cur.execute(
                "INSERT INTO chapters (book_id, parent_id, no, title, level, page_start, page_end) "
                "VALUES (?, ?, ?, ?, ?, NULL, NULL)",
                (book_id, parent_id, n["no"], n["title"], n.get("level", 1)),
            )
            cid = cur.lastrowid
            id_by_no[n["no"]] = cid
            walk(n.get("children", []), cid)

    walk(nodes, None)

    for kp in kps:
        chapter_id = id_by_no.get(kp["chapter_no"])
        if not chapter_id:
            continue
        cur.execute(
            "INSERT INTO kps (chapter_id, code, name, type, depth, cost_min, page, summary) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name, type=excluded.type, "
            "depth=excluded.depth, cost_min=excluded.cost_min, chapter_id=excluded.chapter_id",
            (chapter_id, kp["code"], kp["name"], kp["type"], kp["depth"], kp["cost_min"]),
        )

    conn.commit()

    return {
        "book_id": book_id,
        "chapters": len(id_by_no),
        "kps": len(kps),
    }
