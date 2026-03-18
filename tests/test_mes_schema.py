"""MES WAS 모듈 단위 테스트.

- MESSearchParams Pydantic 모델 유효성 검증
- WASCaller.build_request() 요청 JSON 구성 테스트
- DateTimeRange 날짜 포맷 변환 테스트
"""

import pytest

from mes.schema import DateTimeRange, MESSearchParams, MFGTypeValue
from mes.caller import WASCaller
from mes.config import WASConfig


# ---------------------------------------------------------------------------
# DateTimeRange tests
# ---------------------------------------------------------------------------

class TestDateTimeRange:
    def test_basic_date_range(self):
        dt = DateTimeRange(from_date="20260301", to_date="20260314")
        assert dt.get_from_datetime() == "20260301000000"
        assert dt.get_to_datetime() == "20260314235959"

    def test_with_explicit_time(self):
        dt = DateTimeRange(
            from_date="20260301",
            to_date="20260314",
            from_time="080000",
            to_time="170000",
        )
        assert dt.get_from_datetime() == "20260301080000"
        assert dt.get_to_datetime() == "20260314170000"

    def test_default_times_are_none(self):
        dt = DateTimeRange(from_date="20260101", to_date="20260131")
        assert dt.from_time is None
        assert dt.to_time is None


# ---------------------------------------------------------------------------
# MESSearchParams tests
# ---------------------------------------------------------------------------

class TestMESSearchParams:
    def test_minimal_params(self):
        """action_id만으로 생성 가능."""
        params = MESSearchParams(action_id="PROD_RESULT_BY_LINE")
        assert params.action_id == "PROD_RESULT_BY_LINE"
        assert params.date_range is None
        assert params.factory_id is None
        assert params.product_option == "ALL"

    def test_full_params(self):
        """모든 필드를 채운 경우."""
        params = MESSearchParams(
            action_id="PROD_RESULT_BY_LINE",
            date_range=DateTimeRange(from_date="20260301", to_date="20260314"),
            factory_id="CAB01",
            line_ids="LINE01,LINE02",
            building_id="BLD01",
            shop_ids="SHOP01",
            product_ids="PROD001",
            product_option="ALL",
            step_ids="STEP01",
            mfg_types=[
                MFGTypeValue(value="PP01"),
                MFGTypeValue(value="PP03"),
            ],
            stripe_yn="N",
            notching_yn="N",
        )
        assert params.factory_id == "CAB01"
        assert len(params.mfg_types) == 2
        assert params.mfg_types[0].value == "PP01"
        assert params.stripe_yn == "N"

    def test_mfg_types_serialization(self):
        """MFG 유형 목록의 직렬화 확인."""
        params = MESSearchParams(
            action_id="TEST",
            mfg_types=[
                MFGTypeValue(value="PP01"),
                MFGTypeValue(value="PP04"),
            ],
        )
        dump = params.model_dump(exclude_none=True)
        assert dump["mfg_types"] == [{"value": "PP01"}, {"value": "PP04"}]

    def test_json_round_trip(self):
        """JSON 직렬화/역직렬화."""
        params = MESSearchParams(
            action_id="PROD_RESULT_BY_LINE",
            date_range=DateTimeRange(from_date="20260301", to_date="20260314"),
            factory_id="CAB01",
        )
        json_str = params.model_dump_json(exclude_none=True)
        restored = MESSearchParams.model_validate_json(json_str)
        assert restored.action_id == params.action_id
        assert restored.date_range.from_date == "20260301"

    def test_yn_literal_validation(self):
        """Y/N 필드가 유효한 값만 허용."""
        params = MESSearchParams(action_id="TEST", stripe_yn="Y")
        assert params.stripe_yn == "Y"

        with pytest.raises(Exception):
            MESSearchParams(action_id="TEST", stripe_yn="INVALID")


# ---------------------------------------------------------------------------
# WASCaller tests
# ---------------------------------------------------------------------------

class TestWASCaller:
    def setup_method(self):
        self.config = WASConfig(
            was_url="http://test:8080/api",
            f_fct_id="FCT01",
            f_site_id="SITE01",
            lang_cd="KOR",
            crud="R",
        )
        self.caller = WASCaller(self.config)

    def test_build_request_minimal(self):
        """최소 파라미터로 요청 구성."""
        params = MESSearchParams(action_id="PROD_RESULT_BY_LINE")
        payload = self.caller.build_request(params)

        # 컨텍스트 필드 확인
        assert payload["F_FCT_ID"] == "FCT01"
        assert payload["F_SITE_ID"] == "SITE01"
        assert payload["LANG_CD"] == "KOR"
        assert payload["CRUD"] == "R"

        # 액션 ID
        assert payload["ACTION_ID"] == "PROD_RESULT_BY_LINE"

        # 빈 날짜
        assert payload["S_FROM_DATE"] == ""
        assert payload["S_TO_DATE"] == ""

    def test_build_request_with_dates(self):
        """날짜 범위 포함 요청 구성."""
        params = MESSearchParams(
            action_id="PROD_RESULT_BY_LINE",
            date_range=DateTimeRange(from_date="20260301", to_date="20260314"),
            factory_id="CAB01",
        )
        payload = self.caller.build_request(params)

        assert payload["S_FROM_DATE"] == "20260301"
        assert payload["S_FROM_TIME"] == "20260301000000"
        assert payload["S_TO_DATE"] == "20260314"
        assert payload["S_TO_TIME"] == "20260314235959"
        assert payload["S_FCT_ID"] == "CAB01"

    def test_build_request_with_mfg_types(self):
        """제조 유형 목록 포함 요청 구성."""
        params = MESSearchParams(
            action_id="PROD_RESULT_BY_LINE",
            mfg_types=[
                MFGTypeValue(value="PP01"),
                MFGTypeValue(value="PP03"),
                MFGTypeValue(value="PP04"),
            ],
        )
        payload = self.caller.build_request(params)

        assert payload["S_MFG_TYPE_ID_M"] == [
            {"value": "PP01"},
            {"value": "PP03"},
            {"value": "PP04"},
        ]

    def test_build_request_optional_fields_empty(self):
        """선택 필드 미지정 시 빈 문자열."""
        params = MESSearchParams(action_id="TEST")
        payload = self.caller.build_request(params)

        assert payload["S_LINE_ID_M"] == ""
        assert payload["S_PROD_ID_M"] == ""
        assert payload["S_STEP_ID_M"] == ""
        assert payload["S_PROD_OPTN"] == "ALL"
        assert payload["S_MFG_TYPE_ID_M"] == []

    def test_call_returns_mock(self):
        """PoC 단계: call()이 mock 결과를 반환."""
        params = MESSearchParams(
            action_id="PROD_RESULT_BY_LINE",
            factory_id="CAB01",
        )
        result = self.caller.call(params)
        assert result["mock"] is True
        assert "request_payload" in result

    def test_parse_response(self):
        """WAS 응답 파싱."""
        raw = {
            "META_DS_DATA_0": {"col1": "string", "col2": "int"},
            "DS_DATA_0": [
                {"col1": "A", "col2": 100},
                {"col1": "B", "col2": 200},
            ],
        }
        parsed = WASCaller._parse_response(raw)
        assert parsed["metadata"] == {"col1": "string", "col2": "int"}
        assert len(parsed["data"]) == 2
        assert parsed["data"][0]["col1"] == "A"

    def test_context_params_from_config(self):
        """config의 F_ 파라미터가 payload에 올바르게 병합되는지."""
        config = WASConfig(
            f_fct_id="FACTORY_A",
            f_site_id="SITE_X",
            f_app_id="APP_1",
            f_biz_id="BIZ_99",
            lang_cd="ENG",
            crud="C",
        )
        caller = WASCaller(config)
        params = MESSearchParams(action_id="TEST")
        payload = caller.build_request(params)

        assert payload["F_FCT_ID"] == "FACTORY_A"
        assert payload["F_SITE_ID"] == "SITE_X"
        assert payload["F_APP_ID"] == "APP_1"
        assert payload["F_BIZ_ID"] == "BIZ_99"
        assert payload["LANG_CD"] == "ENG"
        assert payload["CRUD"] == "C"
