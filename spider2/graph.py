"""
Spider2 LangGraph Simple Loop

워크플로우:
    [load_schema] → [generate_spec] → [execute_query]
                         ↑                   ↓
                         └── retry (error) ──┤
                                             ↓ success
                                        [finalize]

노드 설명:
    load_schema   : SQLite DB에서 테이블·컬럼 스키마를 로드
    generate_spec : LLM → Spider2QuerySpec JSON 생성 (with_structured_output)
    execute_query : Spider2Builder로 SQL 조립 → SQLite 실행
    finalize      : 결과 정리 (평가용 raw 결과 또는 오류 메시지)

Self-Correction:
    execute_query에서 오류 발생 시 error_message를 generate_spec으로 피드백하여
    LLM이 QuerySpec을 자가 수정하도록 한다. MAX_RETRY 초과 시 finalize로 이동.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from spider2.builder import Spider2Builder, Spider2BuilderError
from spider2.schema import Spider2QuerySpec
from spider2.schema_loader import load_sqlite_schema
from src.config import get_llm

MAX_RETRY = int(os.getenv("SPIDER2_MAX_RETRY", "3"))

# ── LangGraph 상태 정의 ────────────────────────────────
class Spider2State(TypedDict):
    question: str
    db_path: str
    schema_text: str          # load_schema 출력
    spec: Optional[Spider2QuerySpec]  # generate_spec 출력
    sql: Optional[str]        # execute_query 출력 (성공 시)
    result: Optional[str]     # execute_query 출력 (실행 결과)
    error: Optional[str]      # execute_query 출력 (오류 메시지)
    retry_count: int
    final_answer: Optional[str]


# ── 프롬프트 ───────────────────────────────────────────
_GENERATE_SYSTEM = """\
당신은 데이터베이스 전문가입니다. 아래 스키마를 참고하여 사용자 질문을 분석하고,
Spider2QuerySpec JSON을 작성하세요.

{schema}

규칙:
1. from_table, select_columns 는 반드시 실제 존재하는 테이블/컬럼을 사용하세요.
2. JOIN이 필요하면 joins 필드에 명시하세요. on 조건에 테이블 별칭을 활용하세요.
3. 여러 WHERE 조건은 where_conditions 리스트에 순서대로 나열하세요.
4. 집계(COUNT, SUM, AVG 등)는 select_columns에 집계 표현식으로 포함시키세요.
   예: ["dept_name", "COUNT(*) AS cnt"]
5. HAVING 절은 having 필드에 문자열로 작성하세요.
6. SQL을 직접 작성하지 마세요. 반드시 Spider2QuerySpec 형식으로만 응답하세요.
"""

_RETRY_SUFFIX = """\

※ 이전 시도에서 다음 오류가 발생했습니다. 오류를 참고하여 QuerySpec을 수정하세요:
{error}
"""


# ── 노드 함수들 ────────────────────────────────────────
def load_schema_node(state: Spider2State) -> dict:
    """Node 1: SQLite DB 스키마 로드"""
    schema_text = load_sqlite_schema(state["db_path"])
    return {"schema_text": schema_text}


def generate_spec_node(state: Spider2State) -> dict:
    """Node 2: LLM → Spider2QuerySpec 생성 (with_structured_output)"""
    llm = get_llm()
    structured_llm = llm.with_structured_output(Spider2QuerySpec)

    system_content = _GENERATE_SYSTEM.format(schema=state["schema_text"])
    if state.get("error") and state["retry_count"] > 0:
        system_content += _RETRY_SUFFIX.format(error=state["error"])

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=state["question"]),
    ]

    spec: Spider2QuerySpec = structured_llm.invoke(messages)
    return {"spec": spec, "error": None}


def execute_query_node(state: Spider2State) -> dict:
    """Node 3: Spider2QuerySpec → SQL 조립 → SQLite 실행"""
    spec = state["spec"]

    # QuerySpec → SQL 조립
    try:
        sql = Spider2Builder(spec).build()
    except Spider2BuilderError as e:
        return {
            "sql": None,
            "result": None,
            "error": f"[SQL 조립 오류] {e}",
            "retry_count": state["retry_count"] + 1,
        }

    # SQLite 실행
    try:
        conn = sqlite3.connect(state["db_path"])
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            result = "(결과 없음)"
        else:
            # 헤더 + 행 형식으로 포맷
            headers = list(rows[0].keys())
            header_line = " | ".join(headers)
            sep_line = "-" * len(header_line)
            data_lines = [
                " | ".join(str(row[h]) for h in headers) for row in rows
            ]
            result = "\n".join([header_line, sep_line] + data_lines)

        return {"sql": sql, "result": result, "error": None}

    except sqlite3.Error as e:
        return {
            "sql": sql,
            "result": None,
            "error": f"[SQL 실행 오류] {e}\n실행한 SQL:\n{sql}",
            "retry_count": state["retry_count"] + 1,
        }


def finalize_node(state: Spider2State) -> dict:
    """Node 4: 최종 결과 정리"""
    if state.get("result") is not None:
        final = state["result"]
    else:
        final = f"[오류] 최대 재시도({MAX_RETRY}회) 초과. 마지막 오류: {state.get('error')}"
    return {"final_answer": final}


# ── 조건부 엣지 함수 ──────────────────────────────────
def _should_retry(state: Spider2State) -> str:
    """execute_query 이후 라우팅: 오류가 있고 재시도 가능하면 generate_spec으로"""
    if state.get("error") and state["retry_count"] < MAX_RETRY:
        return "generate_spec"
    return "finalize"


# ── 그래프 정의 ────────────────────────────────────────
def build_graph():
    """
    Spider2 LangGraph Simple Loop 그래프 빌드 및 컴파일.

    Returns:
        컴파일된 LangGraph (invoke/stream 가능)
    """
    graph = StateGraph(Spider2State)

    graph.add_node("load_schema", load_schema_node)
    graph.add_node("generate_spec", generate_spec_node)
    graph.add_node("execute_query", execute_query_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("load_schema")
    graph.add_edge("load_schema", "generate_spec")
    graph.add_edge("generate_spec", "execute_query")
    graph.add_conditional_edges("execute_query", _should_retry)
    graph.add_edge("finalize", END)

    return graph.compile()


# 싱글턴 - 모듈 임포트 시 1회 컴파일
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run(question: str, db_path: str) -> dict:
    """
    단일 질문에 대해 Spider2 파이프라인 실행.

    Args:
        question: 자연어 질문
        db_path : SQLite DB 파일 경로

    Returns:
        최종 상태 dict. 주요 키:
            - final_answer : 쿼리 결과 또는 오류 메시지
            - sql          : 실행된 SQL (성공 시)
            - retry_count  : 재시도 횟수
    """
    initial_state: Spider2State = {
        "question": question,
        "db_path": db_path,
        "schema_text": "",
        "spec": None,
        "sql": None,
        "result": None,
        "error": None,
        "retry_count": 0,
        "final_answer": None,
    }
    return get_graph().invoke(initial_state)
