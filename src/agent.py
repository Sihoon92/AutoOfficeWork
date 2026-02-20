"""
LangChain Agent - v2 (Structured Output 방식)

흐름:
  자연어 → LLM(with_structured_output) → QuerySpec JSON
        → QueryBuilder → SQL 실행 → raw 결과
        → LLM → 자연어 응답
"""
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from db.registry import get_registry_prompt
from src.config import get_llm
from src.query import QueryBuilder, QuerySpec

_PARSE_SYSTEM_PROMPT = """당신은 사용자의 자연어 질문을 분석하여 데이터 쿼리 명세(QuerySpec)를 JSON으로 작성하는 전문가입니다.

{registry}

규칙:
1. 오직 위에 등록된 collection_name과 컬럼명만 사용하세요.
2. 날짜가 명시되지 않았다면, '이번 달'은 {first_day} ~ {today}로 해석하세요.
3. '지난달'은 {last_month_start} ~ {last_month_end}로 해석하세요.
4. 집계('몇 개', '평균', '합계')가 필요하면 integer_aggregation을 반드시 포함하세요.
5. '~별로', '~에 따라' 표현은 groupby_property를 사용하세요.
6. 정렬이나 제한이 필요하면 order_by, limit을 사용하세요.
"""

_ANSWER_SYSTEM_PROMPT = """당신은 데이터 조회 결과를 사용자에게 친절하게 설명하는 어시스턴트입니다.
조회된 데이터를 바탕으로 사용자의 질문에 대한 명확하고 이해하기 쉬운 답변을 작성하세요.
숫자는 단위와 함께 명확히 표현하고, 표나 목록이 있으면 가독성 있게 정리해 주세요.
"""


def _build_parse_prompt() -> str:
    today = date.today()
    first_day = today.replace(day=1)
    if today.month == 1:
        last_month_end = today.replace(day=1).replace(month=12, year=today.year - 1)
        last_month_start = last_month_end.replace(day=1)
    else:
        last_month_end = today.replace(day=1).replace(month=today.month - 1)
        last_month_end = last_month_end.replace(
            day=__import__("calendar").monthrange(last_month_end.year, last_month_end.month)[1]
        )
        last_month_start = last_month_end.replace(day=1)

    return _PARSE_SYSTEM_PROMPT.format(
        registry=get_registry_prompt(),
        today=today.isoformat(),
        first_day=first_day.isoformat(),
        last_month_start=last_month_start.isoformat(),
        last_month_end=last_month_end.isoformat(),
    )


def run(question: str) -> str:
    """
    자연어 질문 → QuerySpec → SQL 실행 → 자연어 응답

    Args:
        question: 사용자의 자연어 질문

    Returns:
        자연어 형태의 최종 응답
    """
    llm = get_llm()

    # Step 1: 자연어 → QuerySpec (Structured Output)
    structured_llm = llm.with_structured_output(QuerySpec)
    spec: QuerySpec = structured_llm.invoke([
        SystemMessage(content=_build_parse_prompt()),
        HumanMessage(content=question),
    ])

    # Step 2: QuerySpec → SQL 실행
    builder = QueryBuilder()
    try:
        raw_result = builder.execute(spec)
    except Exception as e:
        return f"데이터 조회 중 오류가 발생했습니다: {e}"

    # Step 3: raw 결과 → 자연어 응답
    answer_prompt = (
        f"사용자 질문: {question}\n\n"
        f"쿼리 명세:\n{spec.model_dump_json(indent=2, exclude_none=True)}\n\n"
        f"조회 결과:\n{raw_result}"
    )
    response = llm.invoke([
        SystemMessage(content=_ANSWER_SYSTEM_PROMPT),
        HumanMessage(content=answer_prompt),
    ])
    return response.content
