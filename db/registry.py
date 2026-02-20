"""
Collection Registry: LLM에게 제공하는 테이블/컬럼 메타데이터

LLM은 이 정보를 바탕으로 QuerySpec의
- collection_name
- 각 filter의 property_name
- groupby_property
를 올바르게 작성한다.
"""

COLLECTION_REGISTRY: dict = {
    "apc_batch": {
        "description": (
            "배치(Batch) 생산 기록 테이블. "
            "라인별, 제품별 배치의 시작/종료 시간과 상태를 포함한다."
        ),
        "columns": {
            "batch_id": {
                "type": "string",
                "description": "배치 고유 ID (예: BATCH-20260201-001)",
            },
            "product_code": {
                "type": "string",
                "description": "제품 코드 (예: PROD-001, PROD-002, PROD-003)",
            },
            "line_id": {
                "type": "string",
                "description": "생산 라인 ID (A, B, C 중 하나)",
            },
            "start_time": {
                "type": "datetime",
                "description": "배치 시작 시간 (기간 필터의 기본 기준 컬럼)",
            },
            "end_time": {
                "type": "datetime",
                "description": "배치 종료 시간",
            },
            "status": {
                "type": "string",
                "description": "배치 상태: completed | in_progress | failed",
            },
        },
    },
    "apc_measurement": {
        "description": (
            "배치별 공정 파라미터 측정값 테이블. "
            "온도(temperature), 압력(pressure), 유량(flow_rate) 등의 측정 데이터."
        ),
        "columns": {
            "batch_id": {
                "type": "string",
                "description": "apc_batch 참조 배치 ID",
            },
            "param_name": {
                "type": "string",
                "description": "파라미터명: temperature | pressure | flow_rate",
            },
            "param_value": {
                "type": "float",
                "description": "측정값 (숫자 집계의 대상 컬럼)",
            },
            "unit": {
                "type": "string",
                "description": "단위 (°C, bar, L/min 등)",
            },
            "measured_at": {
                "type": "datetime",
                "description": "측정 시간 (기간 필터 사용 시 이 컬럼 지정)",
            },
        },
    },
}


def get_registry_prompt() -> str:
    """LLM System Prompt에 삽입할 Collection Registry 설명 문자열 생성"""
    lines = ["사용 가능한 데이터 컬렉션(테이블) 목록:\n"]
    for name, meta in COLLECTION_REGISTRY.items():
        lines.append(f"## {name}")
        lines.append(f"설명: {meta['description']}")
        lines.append("컬럼:")
        for col, info in meta["columns"].items():
            lines.append(f"  - {col} ({info['type']}): {info['description']}")
        lines.append("")
    return "\n".join(lines)
