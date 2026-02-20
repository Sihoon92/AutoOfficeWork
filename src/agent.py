"""
LangChain Agent - 자연어 → 쿼리 함수 → LLM 응답 파이프라인
"""
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.config import get_llm
from src.tools import ALL_TOOLS

SYSTEM_PROMPT = """당신은 APC(Advanced Process Control) 데이터 조회를 도와주는 어시스턴트입니다.

사용자의 질문을 이해하고, 적절한 도구(Tool)를 선택하여 데이터를 조회한 뒤,
조회 결과를 사람이 이해하기 쉬운 자연어로 설명해 주세요.

규칙:
- 날짜가 명확하지 않으면 사용자에게 확인하세요.
- 조회 결과가 없으면 "해당 조건에 맞는 데이터가 없습니다"라고 안내하세요.
- 숫자는 단위를 포함하여 명확하게 표현하세요.
- 오늘 날짜: {today}
"""


def build_agent() -> AgentExecutor:
    from datetime import date
    llm = get_llm()

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT.format(today=date.today().isoformat())),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, ALL_TOOLS, prompt)
    return AgentExecutor(agent=agent, tools=ALL_TOOLS, verbose=True)


def run(question: str, agent: AgentExecutor = None) -> str:
    if agent is None:
        agent = build_agent()
    result = agent.invoke({"input": question})
    return result["output"]
