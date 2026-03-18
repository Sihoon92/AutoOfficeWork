"""WASCaller — MESSearchParams + 컨텍스트 → WAS 요청 JSON 구성 및 호출.

SQL Builder 대신 WAS HTTP API 요청을 구성하는 역할.
PoC 단계에서는 실제 HTTP 호출 없이 요청 payload 구성까지만 수행할 수 있다.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mes.config import WASConfig
from mes.schema import MESSearchParams

logger = logging.getLogger(__name__)


class WASCaller:
    """WAS API 호출자.

    MESSearchParams(LLM 추출 결과)와 WASConfig(고정 컨텍스트)를
    병합하여 WAS가 기대하는 전체 JSON payload를 구성한다.
    """

    def __init__(self, config: Optional[WASConfig] = None):
        self.config = config or WASConfig()

    def build_request(self, params: MESSearchParams) -> Dict[str, Any]:
        """MESSearchParams → WAS 전체 요청 JSON 구성.

        1. F_ 컨텍스트 파라미터 (config에서)
        2. ACTION_ID
        3. S_ 검색 파라미터 (LLM이 추출한 값)
        """
        payload: Dict[str, Any] = {}

        # 1. 고정 컨텍스트 (F_ prefix)
        payload.update(self.config.get_context_params())

        # 2. 액션 식별자
        payload["ACTION_ID"] = params.action_id

        # 3. 날짜/시간
        if params.date_range:
            payload["S_FROM_DATE"] = params.date_range.from_date
            payload["S_FROM_TIME"] = params.date_range.get_from_datetime()
            payload["S_TO_DATE"] = params.date_range.to_date
            payload["S_TO_TIME"] = params.date_range.get_to_datetime()
        else:
            payload["S_FROM_DATE"] = ""
            payload["S_FROM_TIME"] = ""
            payload["S_TO_DATE"] = ""
            payload["S_TO_TIME"] = ""

        # 4. 위치/설비
        payload["S_FCT_ID"] = params.factory_id or ""
        payload["S_LINE_ID_M"] = params.line_ids or ""
        payload["S_BLD_ID"] = params.building_id or ""
        payload["S_SHOP_ID_M"] = params.shop_ids or ""

        # 5. 제품
        payload["S_PROD_ID_M"] = params.product_ids or ""
        payload["S_PROD_OPTN"] = params.product_option or "ALL"

        # 6. 공정
        payload["S_STEP_ID_M"] = params.step_ids or ""
        payload["S_MFG_TYPE_ID_M"] = (
            [item.model_dump() for item in params.mfg_types]
            if params.mfg_types
            else []
        )

        # 7. Y/N 플래그
        payload["S_STRIPE_YN"] = params.stripe_yn or ""
        payload["S_NOTCHING_YN"] = params.notching_yn or ""

        # 8. 그룹 ID (확장 필드)
        payload["S_LINE_GROUP_ID_M"] = params.line_group_id or ""
        payload["S_LINE_RPRS_GROUP_ID_M"] = params.line_rprs_group_id or ""
        payload["S_ASSY_LINE_ID_M"] = params.assy_line_ids or ""
        payload["S_STEP_MID_GROUP_ID_M"] = params.step_mid_group_id or ""
        payload["S_STEP_LAGE_GROUP_ID_M"] = params.step_lage_group_id or ""
        payload["S_PROD_MID_GROUP_ID_M"] = params.prod_mid_group_id or ""
        payload["S_PROD_LAGE_GROUP_ID_M"] = params.prod_lage_group_id or ""

        return payload

    def call(self, params: MESSearchParams) -> Dict[str, Any]:
        """WAS API 호출 후 응답 파싱.

        PoC 단계: 실제 HTTP 호출 대신 요청 payload만 반환.
        실서비스에서는 httpx/requests로 WAS에 POST 요청.
        """
        payload = self.build_request(params)
        logger.info("WAS request payload built: ACTION_ID=%s", params.action_id)

        # TODO: 실제 WAS 연동 시 아래 주석 해제
        # import httpx
        # response = httpx.post(self.config.was_url, json=payload, timeout=30)
        # response.raise_for_status()
        # return self._parse_response(response.json())

        # PoC: payload만 반환 (WAS 없이 테스트 가능)
        return {"request_payload": payload, "mock": True}

    @staticmethod
    def _parse_response(raw: Dict[str, Any]) -> Dict[str, Any]:
        """WAS 응답 파싱.

        WAS 응답 형태: {"META_DS_DATA_0": Dict, "DS_DATA_0": List[Dict], ...}
        """
        return {
            "metadata": raw.get("META_DS_DATA_0", {}),
            "data": raw.get("DS_DATA_0", []),
        }
