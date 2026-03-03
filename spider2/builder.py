"""
Spider2Builder: Spider2QuerySpec JSON → SQL 문자열 조립

설계 원칙:
- 결정론적(Deterministic): 동일한 Spider2QuerySpec은 항상 동일한 SQL 생성
- LLM과 완전 분리: Spider2QuerySpec 객체만 입력으로 받음
- SQLite 호환 SQL 출력 (Spider 2.0-Lite SQLite 예제 대상)
- 기존 APC QueryBuilder와 동일한 역할, 임의 스키마 대응
"""
from __future__ import annotations

from typing import Any, List, Union

from spider2.schema import Spider2QuerySpec, WhereCondition


class Spider2BuilderError(Exception):
    pass


class Spider2Builder:
    """
    Spider2QuerySpec을 받아 SQLite 호환 SQL 문자열을 조립하는 클래스.

    사용 예시:
        spec = Spider2QuerySpec(
            from_table="orders",
            select_columns=["customer_id", "SUM(amount) AS total"],
            where_conditions=[WhereCondition(column="status", operator="=", value="paid")],
            group_by=["customer_id"],
            order_by=[OrderByClause(column="total", direction="DESC")],
            limit=5,
        )
        sql = Spider2Builder(spec).build()
    """

    def __init__(self, spec: Spider2QuerySpec) -> None:
        self.spec = spec

    def build(self) -> str:
        """Spider2QuerySpec → SQL 문자열 반환"""
        parts: List[str] = []

        parts.append(self._build_select())
        parts.append(self._build_from())

        for join in self.spec.joins:
            parts.append(self._build_join(join))

        where_clause = self._build_where()
        if where_clause:
            parts.append(where_clause)

        group_clause = self._build_group_by()
        if group_clause:
            parts.append(group_clause)

        if self.spec.having:
            parts.append(f"HAVING {self.spec.having}")

        order_clause = self._build_order_by()
        if order_clause:
            parts.append(order_clause)

        if self.spec.limit is not None:
            parts.append(f"LIMIT {self.spec.limit}")

        return "\n".join(parts)

    # ── 절(Clause) 생성 메서드들 ─────────────────────────

    def _build_select(self) -> str:
        cols = ", ".join(self.spec.select_columns)
        distinct = "DISTINCT " if self.spec.distinct else ""
        return f"SELECT {distinct}{cols}"

    def _build_from(self) -> str:
        alias = f" AS {self.spec.from_alias}" if self.spec.from_alias else ""
        return f"FROM {self.spec.from_table}{alias}"

    def _build_join(self, join) -> str:
        alias = f" AS {join.alias}" if join.alias else ""
        return f"{join.join_type} JOIN {join.table}{alias} ON {join.on}"

    def _build_where(self) -> str:
        if not self.spec.where_conditions:
            return ""
        clauses = [self._format_condition(c) for c in self.spec.where_conditions]
        joiner = f" {self.spec.where_logic} "
        return f"WHERE {joiner.join(clauses)}"

    def _build_group_by(self) -> str:
        if not self.spec.group_by:
            return ""
        return f"GROUP BY {', '.join(self.spec.group_by)}"

    def _build_order_by(self) -> str:
        if not self.spec.order_by:
            return ""
        items = [f"{o.column} {o.direction}" for o in self.spec.order_by]
        return f"ORDER BY {', '.join(items)}"

    # ── WHERE 조건 포맷 ───────────────────────────────────

    def _format_condition(self, cond: WhereCondition) -> str:
        col = cond.column
        op = cond.operator

        if op in ("IS NULL", "IS NOT NULL"):
            return f"{col} {op}"

        if op == "BETWEEN":
            if not isinstance(cond.value, list) or len(cond.value) != 2:
                raise Spider2BuilderError(
                    f"BETWEEN 연산자는 [하한, 상한] 형식의 리스트가 필요합니다. "
                    f"컬럼: {col}, 전달값: {cond.value}"
                )
            lo = self._quote(cond.value[0])
            hi = self._quote(cond.value[1])
            return f"{col} BETWEEN {lo} AND {hi}"

        if op in ("IN", "NOT IN"):
            if not isinstance(cond.value, list):
                raise Spider2BuilderError(
                    f"IN/NOT IN 연산자는 리스트가 필요합니다. "
                    f"컬럼: {col}, 전달값: {cond.value}"
                )
            values = ", ".join(self._quote(v) for v in cond.value)
            return f"{col} {op} ({values})"

        return f"{col} {op} {self._quote(cond.value)}"

    @staticmethod
    def _quote(value: Any) -> str:
        """값 타입에 맞게 SQL 리터럴로 변환"""
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        # 문자열: 작은따옴표 이스케이프 후 감싸기
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"
