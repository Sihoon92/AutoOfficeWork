"""MES WAS Agent — 자연어 → WAS 파라미터 추출 → WAS 호출 파이프라인.

APC agent.py의 3-step 패턴을 재사용:
  Step 1: 자연어 → MESSearchParams (with_structured_output)
  Step 2: MESSearchParams → WAS 호출
  Step 3: 결과 → 자연어 답변 생성
"""

from __future__ import annotations

import json
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from mes.caller import WASCaller
from mes.config import WASConfig
from mes.registry import get_registry_prompt
from mes.schema import MESSearchParams
from src.config import get_llm


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_PARSE_SYSTEM_PROMPT = """\
당신은 사용자의 자연어 질문을 분석하여 MES WAS API 검색 파라미터(MESSearchParams)를
JSON으로 작성하는 전문가입니다.

{registry}

## 파라미터 필드 설명:
- action_id: 위 액션 목록에서 질문에 가장 적합한 ACTION_ID를 선택하세요.
- date_range: 조회 기간. from_date/to_date는 YYYYMMDD 형식입니다.
- factory_id: 공장 ID (예: CAB01)
- line_ids: 라인 ID, 여러 개일 경우 콤마로 구분 (예: LINE01,LINE02)
- product_ids: 제품 ID, 여러 개일 경우 콤마로 구분
- mfg_types: 제조 유형 목록. [{{"value": "PP01"}}, {{"value": "PP03"}}] 형태
- stripe_yn, notching_yn: Y 또는 N

## 날짜 해석 규칙:
- 오늘 날짜: {today}
- '이번 달'은 {first_day} ~ {today}
- '지난달'은 {last_month_start} ~ {last_month_end}
- 날짜가 명시되지 않았다면 '이번 달' 전체로 해석하세요.
- from_date, to_date는 반드시 YYYYMMDD 형식으로 작성하세요 (예: 20260301)

## 규칙:
1. 반드시 MESSearchParams 형식으로만 응답하세요.
2. 질문에 언급되지 않은 선택 파라미터는 생략하세요 (null/None).
3. action_id는 반드시 위 액션 목록에서 선택하세요.
4. 필수 파라미터가 질문에 없으면, 합리적인 기본값을 사용하세요.
"""

_ANSWER_SYSTEM_PROMPT = """\
당신은 MES 데이터 조회 결과를 사용자에게 친절하게 설명하는 어시스턴트입니다.
조회된 데이터를 바탕으로 사용자의 질문에 대한 명확하고 이해하기 쉬운 답변을 작성하세요.
숫자는 단위와 함께 명확히 표현하고, 표나 목록이 있으면 가독성 있게 정리해 주세요.
"""


# ---------------------------------------------------------------------------
# Helper: build system prompt with dynamic dates
# ---------------------------------------------------------------------------

def _build_parse_prompt() -> str:
    """현재 날짜 기준으로 파싱 시스템 프롬프트를 구성한다."""
    today = date.today()
    first_day = today.replace(day=1)

    # 지난달 계산
    if today.month == 1:
        last_month_start = today.replace(year=today.year - 1, month=12, day=1)
    else:
        last_month_start = today.replace(month=today.month - 1, day=1)
    # 지난달 마지막 날 = 이번달 1일 - 1일
    last_month_end = first_day.replace(day=1)
    from datetime import timedelta

    last_month_end = last_month_end - timedelta(days=1)

    return _PARSE_SYSTEM_PROMPT.format(
        registry=get_registry_prompt(),
        today=today.strftime("%Y%m%d"),
        first_day=first_day.strftime("%Y%m%d"),
        last_month_start=last_month_start.strftime("%Y%m%d"),
        last_month_end=last_month_end.strftime("%Y%m%d"),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(question: str, config: WASConfig | None = None) -> str:
    """자연어 질문 → MES WAS 파라미터 추출 → WAS 호출 → 자연어 답변.

    Args:
        question: 사용자 자연어 질문
        config: WAS 연결 설정 (None이면 기본값 사용)

    Returns:
        자연어 답변 문자열
    """
    llm = get_llm()
    caller = WASCaller(config)

    # Step 1: 자연어 → MESSearchParams
    structured_llm = llm.with_structured_output(MESSearchParams)
    params: MESSearchParams = structured_llm.invoke([
        SystemMessage(content=_build_parse_prompt()),
        HumanMessage(content=question),
    ])

    print(f"[MES] 추출된 파라미터:\n{params.model_dump_json(indent=2, exclude_none=True)}")

    # Step 2: WAS 호출
    result = caller.call(params)

    # Step 3: 결과 → 자연어 답변
    answer_context = (
        f"사용자 질문: {question}\n\n"
        f"추출된 WAS 파라미터:\n{params.model_dump_json(indent=2, exclude_none=True)}\n\n"
        f"WAS 조회 결과:\n{json.dumps(result, ensure_ascii=False, indent=2)}"
    )
    response = llm.invoke([
        SystemMessage(content=_ANSWER_SYSTEM_PROMPT),
        HumanMessage(content=answer_context),
    ])
    return response.content
