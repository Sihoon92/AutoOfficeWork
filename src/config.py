"""DB / LLM 설정"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from langchain_openai import ChatOpenAI

load_dotenv()


def get_engine():
    url = (
        f"postgresql+psycopg2://"
        f"{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT', 5432)}"
        f"/{os.getenv('POSTGRES_DB')}"
    )
    return create_engine(url)


def get_llm():
    """사내 OpenAI 호환 API 연결"""
    return ChatOpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        temperature=0,
    )
