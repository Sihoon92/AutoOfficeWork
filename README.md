# APC 데이터 자연어 조회 시스템 (POC)

자연어로 APC 데이터를 조회하는 LangChain 기반 POC 시스템.

## 빠른 시작

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 DB/LLM 정보 입력

# 3. DB 샘플 데이터 적재
python db/seed_data.py

# 4. 실행
python main.py                                    # 대화 루프
python main.py "2월 배치 수 알려줘"               # 단일 질문

# 5. 테스트
pytest tests/ -v
```

## 구조

```
src/tools/apc_tools.py   ← 쿼리 함수 추가 지점
src/agent.py             ← LangChain Agent
src/config.py            ← DB/LLM 설정
db/schema.sql            ← 테이블 DDL
db/seed_data.py          ← 샘플 데이터
```

## 새 쿼리 함수 추가

```python
# src/tools/apc_tools.py 에 추가
@tool
def get_defect_rate(start_date: str, end_date: str) -> str:
    """불량율을 조회합니다."""
    ...

# src/tools/__init__.py 의 ALL_TOOLS 에 추가
ALL_TOOLS = [..., get_defect_rate]
```

자세한 내용은 [PRD.md](PRD.md) 참조.
