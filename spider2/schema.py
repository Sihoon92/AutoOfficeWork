"""
Spider2QuerySpec: 임의 DB 스키마에 대응하는 일반화된 쿼리 명세

설계 원칙 (APC QuerySpec과 동일한 철학):
- LLM은 SQL 텍스트를 직접 쓰지 않는다
- 대신 구조화된 JSON 항목(테이블·컬럼·조건·집계)을 채운다
- SQL 조립은 Spider2Builder(애플리케이션)가 담당한다

APC QuerySpec 대비 확장된 부분:
- 임의 테이블/컬럼 (collection_name 고정 없음)
- 복수 WHERE 조건 (AND/OR 조합)
- JOIN 지원 (INNER / LEFT / RIGHT)
- GROUP BY + HAVING
- 복합 ORDER BY
"""
from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── JOIN 절 ───────────────────────────────────────────
class JoinClause(BaseModel):
    """테이블 JOIN 명세"""

    table: str = Field(description="조인할 테이블명")
    alias: Optional[str] = Field(
        default=None, description="테이블 별칭 (예: 't2'). 없으면 테이블명을 그대로 사용"
    )
    on: str = Field(
        description="JOIN 조건 문자열 (예: 't1.dept_id = t2.id')"
    )
    join_type: Literal["INNER", "LEFT", "RIGHT"] = Field(
        default="INNER", description="JOIN 종류"
    )


# ── WHERE 조건 ────────────────────────────────────────
class WhereCondition(BaseModel):
    """단일 WHERE 조건 하나를 표현"""

    column: str = Field(
        description="조건을 적용할 컬럼명. 테이블 별칭 포함 가능 (예: 't1.age', 'salary')"
    )
    operator: Literal[
        "=", "!=", "<", ">", "<=", ">=",
        "LIKE", "NOT LIKE",
        "IN", "NOT IN",
        "IS NULL", "IS NOT NULL",
        "BETWEEN",
    ] = Field(description="비교 연산자")
    value: Optional[Union[str, int, float, List[Union[str, int, float]]]] = Field(
        default=None,
        description=(
            "비교값. IN/NOT IN은 리스트, BETWEEN은 [하한, 상한] 리스트, "
            "IS NULL/IS NOT NULL은 None으로 생략"
        ),
    )


# ── ORDER BY 절 ───────────────────────────────────────
class OrderByClause(BaseModel):
    column: str = Field(description="정렬 기준 컬럼명")
    direction: Literal["ASC", "DESC"] = Field(default="ASC")


# ── 최상위 Spider2QuerySpec ───────────────────────────
class Spider2QuerySpec(BaseModel):
    """
    LLM이 자연어를 분석해 채우는 일반화 쿼리 명세.
    Spider2Builder가 이 스펙을 SQLite 호환 SQL로 변환한다.

    사용 예시:
        Spider2QuerySpec(
            from_table="employees",
            from_alias="e",
            select_columns=["e.name", "d.dept_name", "COUNT(*) AS cnt"],
            joins=[JoinClause(table="departments", alias="d", on="e.dept_id = d.id")],
            where_conditions=[
                WhereCondition(column="e.salary", operator=">", value=50000)
            ],
            group_by=["d.dept_name"],
            order_by=[OrderByClause(column="cnt", direction="DESC")],
            limit=10,
        )
    """

    # 메인 FROM 테이블
    from_table: str = Field(description="메인 테이블명 (FROM 절)")
    from_alias: Optional[str] = Field(
        default=None, description="메인 테이블 별칭 (없으면 테이블명 그대로)"
    )

    # SELECT 컬럼 목록 (집계 표현식 포함 가능)
    select_columns: List[str] = Field(
        default_factory=lambda: ["*"],
        description=(
            "SELECT할 컬럼 목록. 집계 표현식(COUNT(*), AVG(price)) 및 "
            "DISTINCT 접두사도 여기에 포함 가능. 예: ['name', 'COUNT(*) AS cnt']"
        ),
    )
    distinct: bool = Field(
        default=False,
        description="SELECT DISTINCT 여부",
    )

    # JOIN
    joins: List[JoinClause] = Field(
        default_factory=list,
        description="JOIN 절 목록. 순서대로 적용됨",
    )

    # WHERE
    where_conditions: List[WhereCondition] = Field(
        default_factory=list,
        description="WHERE 조건 목록",
    )
    where_logic: Literal["AND", "OR"] = Field(
        default="AND",
        description="WHERE 조건들 사이의 논리 연산자",
    )

    # GROUP BY / HAVING
    group_by: List[str] = Field(
        default_factory=list,
        description="GROUP BY 컬럼 목록",
    )
    having: Optional[str] = Field(
        default=None,
        description=(
            "HAVING 절 조건 문자열. 집계 함수가 포함된 조건은 "
            "구조화하기 어려우므로 문자열로 직접 기입 (예: 'COUNT(*) > 5')"
        ),
    )

    # ORDER BY / LIMIT
    order_by: List[OrderByClause] = Field(
        default_factory=list,
        description="ORDER BY 절 목록",
    )
    limit: Optional[int] = Field(
        default=None,
        description="반환할 최대 행 수 (LIMIT)",
    )
