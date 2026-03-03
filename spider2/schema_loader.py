"""
Spider2 Schema Loader: SQLite DB → LLM 프롬프트용 스키마 텍스트 변환

역할:
- APC의 정적 Collection Registry(db/registry.py)를 대체하는 동적 로더
- SQLite .db 파일에서 테이블·컬럼·외래키 정보를 읽어 텍스트로 변환
- LLM이 Spider2QuerySpec을 올바르게 채울 수 있도록 컨텍스트 제공

출력 포맷: db/registry.py의 get_registry_prompt()와 동일한 가독성 형식
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def load_sqlite_schema(db_path: str | Path) -> str:
    """
    SQLite DB 파일에서 전체 스키마를 로드하여 LLM 프롬프트용 텍스트로 반환.

    Args:
        db_path: SQLite .db 파일 경로

    Returns:
        테이블·컬럼·외래키 정보를 담은 텍스트 (LLM System Prompt에 삽입용)

    Raises:
        FileNotFoundError: db_path 파일이 존재하지 않을 때
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB 파일이 없습니다: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        return _build_schema_text(conn, db_path.stem)
    finally:
        conn.close()


def _build_schema_text(conn: sqlite3.Connection, db_name: str) -> str:
    cursor = conn.cursor()

    # 사용자 테이블만 조회 (시스템 테이블 제외)
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    if not tables:
        return f"데이터베이스 '{db_name}'에 테이블이 없습니다."

    lines: list[str] = [f"데이터베이스: {db_name}\n사용 가능한 테이블 목록:\n"]

    for table_name in tables:
        lines.append(f"## {table_name}")

        # 컬럼 정보
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        # (cid, name, type, notnull, dflt_value, pk)
        lines.append("컬럼:")
        for col in columns:
            _, col_name, col_type, notnull, _, is_pk = col
            tags: list[str] = []
            if is_pk:
                tags.append("PK")
            if notnull:
                tags.append("NOT NULL")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"  - {col_name} ({col_type or 'TEXT'}){tag_str}")

        # 외래키 정보
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        fks = cursor.fetchall()
        if fks:
            lines.append("외래키:")
            for fk in fks:
                # (id, seq, ref_table, from_col, to_col, ...)
                lines.append(f"  - {table_name}.{fk[3]} → {fk[2]}.{fk[4]}")

        lines.append("")  # 빈 줄로 테이블 구분

    return "\n".join(lines)


def find_sqlite_db(db_dir: str | Path, db_id: str) -> Path | None:
    """
    Spider 2.0-Lite 디렉토리 구조에서 db_id에 해당하는 SQLite 파일을 탐색.

    탐색 경로 우선순위:
        1. {db_dir}/{db_id}/{db_id}.sqlite
        2. {db_dir}/{db_id}/{db_id}.db
        3. {db_dir}/{db_id}/*.sqlite (첫 번째 파일)
        4. {db_dir}/{db_id}/*.db    (첫 번째 파일)

    Returns:
        Path 또는 None (파일을 찾지 못한 경우)
    """
    db_dir = Path(db_dir)
    db_subdir = db_dir / db_id

    candidates = [
        db_subdir / f"{db_id}.sqlite",
        db_subdir / f"{db_id}.db",
    ]
    for path in candidates:
        if path.exists():
            return path

    # 와일드카드 탐색
    for ext in ("*.sqlite", "*.db"):
        matches = list(db_subdir.glob(ext))
        if matches:
            return matches[0]

    return None
