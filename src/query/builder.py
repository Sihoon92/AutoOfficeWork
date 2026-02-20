"""
Query Builder: QuerySpec JSON → SQLAlchemy 쿼리 조립

설계 원칙:
- 결정론적(Deterministic): 동일한 QuerySpec은 항상 동일한 SQL 생성
- LLM과 완전 분리: 이 모듈은 QuerySpec 객체만 받아 처리
- DB 종속성 격리: SQLAlchemy를 통해 PostgreSQL 문법을 추상화

확장 방법:
- 새 필터 타입 추가: _apply_new_filter() 메서드 추가 후 build()에서 호출
- 다른 DB 지원: SQLAlchemy 엔진만 교체 (코드 변경 없음)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.config import get_engine
from src.models import ApcBatch, ApcMeasurement
from src.query.schema import QuerySpec

# 지원하는 collection → SQLAlchemy 모델 매핑
_MODEL_MAP: dict = {
    "apc_batch": ApcBatch,
    "apc_measurement": ApcMeasurement,
}


class QueryBuilderError(Exception):
    pass


class QueryBuilder:
    """
    QuerySpec을 받아 SQLAlchemy 쿼리를 조립하고 실행하는 클래스.

    사용 예시:
        spec = QuerySpec(
            collection_name="apc_batch",
            date_range_filter=DateRangeFilter(start="2026-02-01", end="2026-02-20"),
            integer_aggregation=IntegerAggregation(operator="COUNT"),
        )
        result = QueryBuilder().execute(spec)
    """

    def execute(self, spec: QuerySpec) -> str:
        """QuerySpec을 SQL로 변환하여 실행하고 결과를 문자열로 반환"""
        model = self._get_model(spec.collection_name)

        with Session(get_engine()) as session:
            query = session.query(model)

            # 1. 날짜 범위 필터
            query = self._apply_date_range(query, model, spec)

            # 2. 정형 필터
            query = self._apply_integer_filter(query, model, spec)
            query = self._apply_string_filter(query, model, spec)
            query = self._apply_boolean_filter(query, model, spec)

            # 3. 집계 + 그룹화 (집계가 있으면 별도 쿼리 경로)
            if spec.integer_aggregation:
                return self._execute_aggregation(session, model, query, spec)

            # 4. 정렬 및 제한 (일반 조회)
            query = self._apply_order_by(query, model, spec)
            if spec.limit:
                query = query.limit(spec.limit)

            rows = query.all()

        return self._to_string(rows, spec)

    # ── 내부 메서드들 ───────────────────────────────────

    def _get_model(self, collection_name: str):
        model = _MODEL_MAP.get(collection_name)
        if model is None:
            available = list(_MODEL_MAP.keys())
            raise QueryBuilderError(
                f"알 수 없는 collection: '{collection_name}'. "
                f"사용 가능한 collection: {available}"
            )
        return model

    def _apply_date_range(self, query, model, spec: QuerySpec):
        if not spec.date_range_filter:
            return query
        f = spec.date_range_filter
        col = getattr(model, f.property_name, None)
        if col is None:
            raise QueryBuilderError(
                f"'{spec.collection_name}' 에 '{f.property_name}' 컬럼이 없습니다."
            )
        start_dt = datetime.fromisoformat(f.start)
        end_dt = datetime.fromisoformat(f.end).replace(hour=23, minute=59, second=59)
        return query.filter(col >= start_dt, col <= end_dt)

    def _apply_integer_filter(self, query, model, spec: QuerySpec):
        if not spec.integer_filter:
            return query
        f = spec.integer_filter
        col = getattr(model, f.property_name)
        ops = {
            "=": col == f.value,
            "!=": col != f.value,
            "<": col < f.value,
            ">": col > f.value,
            "<=": col <= f.value,
            ">=": col >= f.value,
        }
        return query.filter(ops[f.operator])

    def _apply_string_filter(self, query, model, spec: QuerySpec):
        if not spec.string_filter:
            return query
        f = spec.string_filter
        col = getattr(model, f.property_name)
        if f.operator == "=":
            return query.filter(col == f.value)
        elif f.operator == "!=":
            return query.filter(col != f.value)
        elif f.operator == "LIKE":
            return query.filter(col.like(f.value))
        elif f.operator == "IN":
            values = f.value if isinstance(f.value, list) else [f.value]
            return query.filter(col.in_(values))
        return query

    def _apply_boolean_filter(self, query, model, spec: QuerySpec):
        if not spec.boolean_filter:
            return query
        f = spec.boolean_filter
        col = getattr(model, f.property_name)
        return query.filter(col == f.value)

    def _apply_order_by(self, query, model, spec: QuerySpec):
        if not spec.order_by:
            return query
        col = getattr(model, spec.order_by.property_name)
        if spec.order_by.direction == "DESC":
            return query.order_by(col.desc())
        return query.order_by(col.asc())

    def _execute_aggregation(self, session, model, base_query, spec: QuerySpec) -> str:
        """집계 쿼리 실행 (COUNT, SUM, AVG, MIN, MAX)"""
        agg = spec.integer_aggregation
        agg_funcs = {
            "COUNT": func.count,
            "SUM": func.sum,
            "AVG": func.avg,
            "MIN": func.min,
            "MAX": func.max,
        }
        agg_func = agg_funcs[agg.operator]

        # 집계 대상 컬럼 결정
        if agg.property_name:
            target_col = getattr(model, agg.property_name)
            agg_expr = agg_func(target_col).label("result")
        else:
            agg_expr = agg_func("*").label("result")  # COUNT(*)

        # 그룹화 여부에 따라 분기
        if spec.groupby_property:
            group_col = getattr(model, spec.groupby_property)
            # base_query의 WHERE 절 필터를 재사용하기 위해 subquery로 처리
            subq = base_query.subquery()
            group_col_sub = getattr(subq.c, spec.groupby_property)
            agg_col_sub = (
                getattr(subq.c, agg.property_name)
                if agg.property_name
                else text("1")
            )
            agg_expr_sub = agg_func(agg_col_sub).label("result")

            rows = (
                session.query(group_col_sub, agg_expr_sub)
                .group_by(group_col_sub)
                .order_by(agg_expr_sub.desc())
                .all()
            )
            df = pd.DataFrame(rows, columns=[spec.groupby_property, agg.operator])
            return df.to_string(index=False)
        else:
            subq = base_query.subquery()
            agg_col_sub = (
                getattr(subq.c, agg.property_name)
                if agg.property_name
                else text("1")
            )
            result = session.query(agg_func(agg_col_sub)).scalar()
            return f"{agg.operator}: {result}"

    def _to_string(self, rows: list, spec: QuerySpec) -> str:
        if not rows:
            return "조회된 데이터가 없습니다."

        # SQLAlchemy 모델 객체 → dict
        records = []
        for row in rows:
            record: dict[str, Any] = {}
            for col in row.__table__.columns:
                val = getattr(row, col.name)
                if isinstance(val, datetime):
                    val = val.strftime("%Y-%m-%d %H:%M")
                record[col.name] = val
            records.append(record)

        df = pd.DataFrame(records)
        return df.to_string(index=False)
