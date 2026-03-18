"""Pydantic models for MES WAS API parameters.

LLM extracts search parameters from natural language into these models.
The WASCaller then merges them with fixed context parameters to build
the full WAS request payload.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class DateTimeRange(BaseModel):
    """조회 기간 (날짜/시간 범위).

    WAS 포맷: YYYYMMDD (날짜), YYYYMMDDHHmmss (시간)
    LLM에게는 YYYYMMDD 형태만 요구하고, 시간은 기본값으로 채운다.
    """

    from_date: str = Field(..., description="시작 날짜 (YYYYMMDD, 예: 20260301)")
    to_date: str = Field(..., description="종료 날짜 (YYYYMMDD, 예: 20260314)")
    from_time: Optional[str] = Field(
        default=None,
        description="시작 시간 (HHmmss). 미지정 시 000000",
    )
    to_time: Optional[str] = Field(
        default=None,
        description="종료 시간 (HHmmss). 미지정 시 235959",
    )

    def get_from_datetime(self) -> str:
        """WAS 전송용 S_FROM_TIME (YYYYMMDDHHmmss)."""
        return self.from_date + (self.from_time or "000000")

    def get_to_datetime(self) -> str:
        """WAS 전송용 S_TO_TIME (YYYYMMDDHHmmss)."""
        return self.to_date + (self.to_time or "235959")


class MFGTypeValue(BaseModel):
    """제조 유형 단일 값 — S_MFG_TYPE_ID_M 의 리스트 요소."""

    value: str = Field(..., description="제조 유형 코드 (예: PP01, PP03)")


# ---------------------------------------------------------------------------
# Main search parameters (LLM output)
# ---------------------------------------------------------------------------

class MESSearchParams(BaseModel):
    """LLM이 자연어에서 추출하는 WAS 검색 파라미터.

    with_structured_output(MESSearchParams) 로 사용하여
    LLM이 반드시 이 스키마에 맞는 JSON을 반환하도록 강제한다.
    """

    # --- 필수: 어떤 WAS 액션을 실행할지 ---
    action_id: str = Field(
        ...,
        description="실행할 WAS 액션 ID (Registry에 등록된 ACTION_ID)",
    )

    # --- 날짜/시간 ---
    date_range: Optional[DateTimeRange] = Field(
        default=None,
        description="조회 기간. 대부분의 액션에서 필수.",
    )

    # --- 위치/설비 ---
    factory_id: Optional[str] = Field(
        default=None, description="공장 ID (S_FCT_ID, 예: CAB01)",
    )
    line_ids: Optional[str] = Field(
        default=None,
        description="라인 ID, 복수 시 콤마 구분 (S_LINE_ID_M, 예: LINE01,LINE02)",
    )
    building_id: Optional[str] = Field(
        default=None, description="건물/동 ID (S_BLD_ID)",
    )
    shop_ids: Optional[str] = Field(
        default=None,
        description="Shop ID, 복수 시 콤마 구분 (S_SHOP_ID_M)",
    )

    # --- 제품 ---
    product_ids: Optional[str] = Field(
        default=None,
        description="제품 ID, 복수 시 콤마 구분 (S_PROD_ID_M)",
    )
    product_option: Optional[str] = Field(
        default="ALL",
        description="제품 옵션 (S_PROD_OPTN, 기본값 ALL)",
    )

    # --- 공정 ---
    step_ids: Optional[str] = Field(
        default=None,
        description="공정 단계 ID, 복수 시 콤마 구분 (S_STEP_ID_M)",
    )
    mfg_types: Optional[List[MFGTypeValue]] = Field(
        default=None,
        description='제조 유형 목록 (S_MFG_TYPE_ID_M, 예: [{"value":"PP01"},{"value":"PP03"}])',
    )

    # --- Y/N 플래그 ---
    stripe_yn: Optional[Literal["Y", "N"]] = Field(
        default=None, description="Stripe 여부 (S_STRIPE_YN)",
    )
    notching_yn: Optional[Literal["Y", "N"]] = Field(
        default=None, description="Notching 여부 (S_NOTCHING_YN)",
    )

    # --- 기타 그룹 ID (확장용) ---
    line_group_id: Optional[str] = Field(
        default=None, description="라인 그룹 ID (S_LINE_GROUP_ID_M)",
    )
    line_rprs_group_id: Optional[str] = Field(
        default=None, description="라인 대표 그룹 ID (S_LINE_RPRS_GROUP_ID_M)",
    )
    assy_line_ids: Optional[str] = Field(
        default=None, description="조립 라인 ID (S_ASSY_LINE_ID_M)",
    )
    step_mid_group_id: Optional[str] = Field(
        default=None, description="공정 중분류 그룹 ID (S_STEP_MID_GROUP_ID_M)",
    )
    step_lage_group_id: Optional[str] = Field(
        default=None, description="공정 대분류 그룹 ID (S_STEP_LAGE_GROUP_ID_M)",
    )
    prod_mid_group_id: Optional[str] = Field(
        default=None, description="제품 중분류 그룹 ID (S_PROD_MID_GROUP_ID_M)",
    )
    prod_lage_group_id: Optional[str] = Field(
        default=None, description="제품 대분류 그룹 ID (S_PROD_LAGE_GROUP_ID_M)",
    )
