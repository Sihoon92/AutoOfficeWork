"""
Query Builder 단위 테스트

QuerySpec → SQL 조립이 올바른지 검증.
DB 연결 없이 Mock으로 테스트 가능한 항목과
실제 DB 연결이 필요한 통합 테스트를 분리.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.query.schema import (
    BooleanFilter,
    DateRangeFilter,
    IntegerAggregation,
    IntegerFilter,
    OrderBy,
    QuerySpec,
    StringFilter,
)
from src.query.builder import QueryBuilder, QueryBuilderError


# ── Schema 유효성 테스트 (DB 불필요) ──────────────────

class TestQuerySpecValidation:
    def test_minimal_spec(self):
        """collection_name만 있는 최소 스펙"""
        spec = QuerySpec(collection_name="apc_batch")
        assert spec.collection_name == "apc_batch"
        assert spec.date_range_filter is None
        assert spec.integer_aggregation is None

    def test_full_spec(self):
        """모든 필드를 포함한 완전 스펙"""
        spec = QuerySpec(
            collection_name="apc_batch",
            date_range_filter=DateRangeFilter(start="2026-02-01", end="2026-02-20"),
            string_filter=StringFilter(property_name="line_id", operator="=", value="A"),
            integer_aggregation=IntegerAggregation(operator="COUNT"),
            groupby_property="status",
        )
        assert spec.string_filter.value == "A"
        assert spec.integer_aggregation.operator == "COUNT"

    def test_date_range_default_property(self):
        """date_range_filter의 property_name 기본값 확인"""
        f = DateRangeFilter(start="2026-02-01", end="2026-02-20")
        assert f.property_name == "start_time"

    def test_string_filter_in_operator(self):
        """IN 연산자는 리스트 값 허용"""
        f = StringFilter(
            property_name="status",
            operator="IN",
            value=["completed", "failed"],
        )
        assert isinstance(f.value, list)
        assert len(f.value) == 2

    def test_invalid_operator_raises(self):
        """정의되지 않은 연산자는 ValidationError 발생"""
        with pytest.raises(Exception):
            IntegerFilter(property_name="param_value", operator="BETWEEN", value=10)


# ── Query Builder 테스트 (DB Mock) ────────────────────

class TestQueryBuilderUnknownCollection:
    def test_unknown_collection_raises(self):
        """등록되지 않은 collection_name은 에러 발생"""
        spec = QuerySpec(collection_name="unknown_table")
        builder = QueryBuilder()
        with pytest.raises(QueryBuilderError, match="알 수 없는 collection"):
            builder.execute(spec)


# ── 시나리오별 QuerySpec 생성 검증 ────────────────────

class TestScenarioSpecs:
    """PRD 8개 테스트 시나리오에 해당하는 QuerySpec을 직접 정의하고 구조 검증"""

    def test_scenario_1_date_range_only(self):
        """시나리오 1: 기간별 배치 목록"""
        spec = QuerySpec(
            collection_name="apc_batch",
            date_range_filter=DateRangeFilter(start="2026-02-01", end="2026-02-20"),
        )
        assert spec.date_range_filter is not None
        assert spec.integer_aggregation is None

    def test_scenario_2_count_aggregation(self):
        """시나리오 2: 이번 달 배치 수"""
        spec = QuerySpec(
            collection_name="apc_batch",
            date_range_filter=DateRangeFilter(start="2026-02-01", end="2026-02-20"),
            integer_aggregation=IntegerAggregation(operator="COUNT"),
        )
        assert spec.integer_aggregation.operator == "COUNT"
        assert spec.groupby_property is None

    def test_scenario_4_groupby(self):
        """시나리오 4: 상태별 그룹화"""
        spec = QuerySpec(
            collection_name="apc_batch",
            date_range_filter=DateRangeFilter(start="2026-02-01", end="2026-02-20"),
            string_filter=StringFilter(property_name="line_id", operator="=", value="A"),
            integer_aggregation=IntegerAggregation(operator="COUNT"),
            groupby_property="status",
        )
        assert spec.groupby_property == "status"

    def test_scenario_6_measurement_avg(self):
        """시나리오 6: 온도 파라미터 평균"""
        spec = QuerySpec(
            collection_name="apc_measurement",
            date_range_filter=DateRangeFilter(
                property_name="measured_at",
                start="2026-01-01",
                end="2026-01-31",
            ),
            string_filter=StringFilter(
                property_name="param_name", operator="=", value="temperature"
            ),
            integer_aggregation=IntegerAggregation(
                operator="AVG", property_name="param_value"
            ),
        )
        assert spec.integer_aggregation.operator == "AVG"
        assert spec.integer_aggregation.property_name == "param_value"

    def test_scenario_7_order_limit(self):
        """시나리오 7: 가장 최근 배치 1개"""
        spec = QuerySpec(
            collection_name="apc_batch",
            date_range_filter=DateRangeFilter(start="2026-01-01", end="2026-01-31"),
            order_by=OrderBy(property_name="start_time", direction="DESC"),
            limit=1,
        )
        assert spec.limit == 1
        assert spec.order_by.direction == "DESC"

    def test_scenario_8_multi_string_filter(self):
        """시나리오 8: 복수 문자열 필터 (IN 연산자 활용)"""
        spec = QuerySpec(
            collection_name="apc_batch",
            date_range_filter=DateRangeFilter(start="2026-02-01", end="2026-02-20"),
            string_filter=StringFilter(
                property_name="status", operator="IN", value=["completed"]
            ),
            integer_aggregation=IntegerAggregation(operator="COUNT"),
        )
        assert spec.string_filter.operator == "IN"
