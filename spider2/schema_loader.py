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

    실제 Spider 2.0-Lite 구조:
        {db_dir}/{db_id}/{db_id}.sqlite  또는
        {db_dir}/{db_id}/*.sqlite

    탐색 우선순위:
        1. 정확한 이름 매칭: {db_dir}/{db_id}/{db_id}.sqlite|.db
        2. 와일드카드:       {db_dir}/{db_id}/*.sqlite|.db
        3. 대소문자 무시:    폴더명이 db_id와 대소문자만 다를 경우도 처리

    Returns:
        Path 또는 None (파일을 찾지 못한 경우)
    """
    db_dir = Path(db_dir)

    # 정확한 이름 매칭
    db_subdir = db_dir / db_id
    if db_subdir.is_dir():
        for name in (f"{db_id}.sqlite", f"{db_id}.db"):
            p = db_subdir / name
            if p.exists():
                return p
        for ext in ("*.sqlite", "*.db"):
            matches = sorted(db_subdir.glob(ext))
            if matches:
                return matches[0]

    # 대소문자 무시 폴더 탐색
    # (Spider 2.0-Lite의 sqlite 폴더명은 대문자 포함: AdventureWorks 등)
    db_id_lower = db_id.lower()
    if db_dir.is_dir():
        for subdir in db_dir.iterdir():
            if subdir.is_dir() and subdir.name.lower() == db_id_lower:
                for name in (f"{subdir.name}.sqlite", f"{subdir.name}.db",
                             f"{db_id}.sqlite", f"{db_id}.db"):
                    p = subdir / name
                    if p.exists():
                        return p
                for ext in ("*.sqlite", "*.db"):
                    matches = sorted(subdir.glob(ext))
                    if matches:
                        return matches[0]

    return None
