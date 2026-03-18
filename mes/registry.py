"""WAS Action Registry — LLM 컨텍스트용 메타데이터.

각 ACTION_ID가 어떤 조회를 수행하고, 어떤 파라미터가 필수/선택인지 기술한다.
LLM 시스템 프롬프트에 삽입되어 자연어 → 파라미터 추출을 안내한다.

실제 WAS 액션이 추가될 때마다 여기에 등록한다.
"""

from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Action Registry
# ---------------------------------------------------------------------------

MES_ACTION_REGISTRY: Dict[str, Dict[str, Any]] = {
    # PoC 예시: 라인별 생산 실적 조회
    "PROD_RESULT_BY_LINE": {
        "description": "라인별 생산 실적 조회 — 기간 내 각 라인의 생산 수량, 양품/불량 수, 가동률 등을 조회한다.",
        "required_params": ["date_range", "factory_id"],
        "optional_params": [
            "line_ids",
            "product_ids",
            "mfg_types",
            "shop_ids",
            "product_option",
        ],
        "returns": "라인별 생산 수량, 양품 수, 불량 수, 가동률",
        "example_question": "3월 1일부터 14일까지 CAB01 공장의 라인별 생산 실적 알려줘",
    },
}


def get_action_list() -> List[str]:
    """등록된 ACTION_ID 목록을 반환한다."""
    return list(MES_ACTION_REGISTRY.keys())


def get_registry_prompt() -> str:
    """LLM 시스템 프롬프트에 삽입할 Action Registry 텍스트를 생성한다.

    db/registry.py의 get_registry_prompt()와 동일한 역할.
    """
    lines: list[str] = ["사용 가능한 WAS 액션 목록:\n"]
    for action_id, meta in MES_ACTION_REGISTRY.items():
        lines.append(f"## ACTION_ID: {action_id}")
        lines.append(f"  설명: {meta['description']}")
        lines.append(f"  필수 파라미터: {', '.join(meta['required_params'])}")
        lines.append(f"  선택 파라미터: {', '.join(meta['optional_params'])}")
        lines.append(f"  반환 데이터: {meta['returns']}")
        if "example_question" in meta:
            lines.append(f"  예시 질문: {meta['example_question']}")
        lines.append("")
    return "\n".join(lines)
