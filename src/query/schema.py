"""
QuerySpec: LLM이 자연어를 파싱하여 채워넣는 구조화 쿼리 명세

설계 원칙 (DBGorilla 논문 방식):
- LLM은 SQL을 직접 생성하지 않는다
- 대신 "무엇을, 어떤 조건으로, 어떻게 집계"를 JSON 항목으로 분해하여 기입
- SQL 조립은 QueryBuilder(애플리케이션)가 담당

확장 방법:
- 새로운 필터 타입이 필요하면 이 파일에 클래스 추가 후
  QueryBuilder에 해당 처리 로직 추가
- Agent(LLM) 코드는 수정 불필요
"""
from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── 날짜 범위 필터 ───────────────────────────────────
class DateRangeFilter(BaseModel):
    """시계열 데이터의 기간 필터. APC 데이터 조회의 핵심 필터."""

    property_name: str = Field(
        default="start_time",
        description="기간 필터를 적용할 날짜/시간 컬럼명",
    )
    start: str = Field(description="조회 시작일 (YYYY-MM-DD)")
    end: str = Field(description="조회 종료일 (YYYY-MM-DD)")


# ── 정형 필터들 ──────────────────────────────────────
class IntegerFilter(BaseModel):
    """숫자형 컬럼에 대한 비교 필터"""

    property_name: str = Field(description="필터를 적용할 숫자형 컬럼명")
    operator: Literal["=", "<", ">", "<=", ">=", "!="] = Field(
        description="비교 연산자"
    )
    value: float = Field(description="비교 기준값")


class StringFilter(BaseModel):
    """문자열 컬럼에 대한 필터"""

    property_name: str = Field(description="필터를 적용할 문자열 컬럼명")
    operator: Literal["=", "!=", "LIKE", "IN"] = Field(description="비교 연산자")
    value: Union[str, List[str]] = Field(
        description="비교값. IN 연산자의 경우 리스트로 전달"
    )


class BooleanFilter(BaseModel):
    """불리언 컬럼에 대한 필터"""

    property_name: str = Field(description="필터를 적용할 불리언 컬럼명")
    value: bool


# ── 집계 ─────────────────────────────────────────────
class IntegerAggregation(BaseModel):
    """숫자형 집계 연산"""

    operator: Literal["COUNT", "SUM", "AVG", "MIN", "MAX"] = Field(
        description="집계 함수"
    )
    property_name: Optional[str] = Field(
        default=None,
        description="집계 대상 컬럼명. COUNT(*)의 경우 None으로 생략 가능",
    )


# ── 정렬 ─────────────────────────────────────────────
class OrderBy(BaseModel):
    property_name: str = Field(description="정렬 기준 컬럼명")
    direction: Literal["ASC", "DESC"] = Field(default="DESC")


# ── 최상위 QuerySpec ─────────────────────────────────
class QuerySpec(BaseModel):
    """
    LLM이 자연어를 분석하여 생성하는 구조화 쿼리 명세.
    Query Builder가 이 스펙을 SQL로 변환한다.
    """

    collection_name: str = Field(
        description="조회할 테이블명 (Collection Registry에 등록된 이름)"
    )

    # 텍스트 의미 검색 (향후 벡터 검색 확장 포인트)
    search_query: Optional[str] = Field(
        default=None,
        description="텍스트 의미 검색어. 특정 키워드나 개념으로 검색할 때 사용",
    )

    # 필터들 (복수 필터는 AND 조건으로 결합)
    date_range_filter: Optional[DateRangeFilter] = Field(
        default=None,
        description="날짜/시간 범위 필터. 기간 조회 시 반드시 사용",
    )
    integer_filter: Optional[IntegerFilter] = Field(
        default=None,
        description="숫자형 컬럼 비교 필터 (예: param_value > 200)",
    )
    string_filter: Optional[StringFilter] = Field(
        default=None,
        description="문자열 컬럼 필터 (예: line_id = 'A', status IN ['completed','failed'])",
    )
    boolean_filter: Optional[BooleanFilter] = Field(
        default=None,
        description="불리언 컬럼 필터",
    )

    # 집계
    integer_aggregation: Optional[IntegerAggregation] = Field(
        default=None,
        description="숫자 집계. '몇 개', '평균', '합계' 등의 질문에 사용",
    )

    # 그룹화 (집계와 함께 사용)
    groupby_property: Optional[str] = Field(
        default=None,
        description="그룹화 기준 컬럼명. '~별로' 와 같이 분류가 필요할 때 사용",
    )

    # 결과 제한 및 정렬
    limit: Optional[int] = Field(
        default=None,
        description="반환할 최대 행 수. '가장 최근 N개' 등의 질문에 사용",
    )
    order_by: Optional[OrderBy] = Field(
        default=None,
        description="결과 정렬 기준",
    )
