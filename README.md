# APC 데이터 자연어 조회 시스템 (POC) - v2

자연어 질문 → 구조화 JSON(QuerySpec) → SQL 조립 → DB 실행 → 자연어 응답

DBGorilla 논문의 Function Calling 방식 적용:
LLM은 SQL을 직접 생성하지 않고, "무엇을, 어떤 조건으로, 어떻게 집계할지"를
규격화된 JSON(QuerySpec)으로 기입. SQL 조립은 Query Builder가 담당.

## 빠른 시작

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에 DB/LLM 정보 입력

# 3. DB 샘플 데이터 적재
python db/seed_data.py

# 4. 실행
python main.py                          # 대화 루프
python main.py "2월 배치 수 알려줘"    # 단일 질문

# 5. 테스트
pytest tests/ -v
```

## 아키텍처

```
자연어 질문
    │
    ▼
LLM (with_structured_output)
    → QuerySpec JSON 생성
    │
    ▼
Query Builder
    → QuerySpec → SQLAlchemy 쿼리 조립
    │
    ▼
PostgreSQL
    │
    ▼
LLM → 자연어 응답
```

## 확장 방법

### 새 필터 타입 추가

```python
# 1. src/query/schema.py 에 새 필터 클래스 추가
class FloatRangeFilter(BaseModel):
    property_name: str
    min_value: float
    max_value: float

# 2. QuerySpec에 필드 추가
class QuerySpec(BaseModel):
    ...
    float_range_filter: Optional[FloatRangeFilter] = None

# 3. src/query/builder.py 에 처리 로직 추가
def _apply_float_range(self, query, model, spec):
    ...
```

### 새 데이터 소스(테이블) 추가

```python
# 1. db/registry.py 에 Collection 메타데이터 추가
COLLECTION_REGISTRY["mes_production"] = { ... }

# 2. src/models.py 에 SQLAlchemy 모델 추가

# 3. src/query/builder.py 의 _MODEL_MAP 에 추가
_MODEL_MAP["mes_production"] = MesProduction
```

자세한 내용은 [PRD.md](PRD.md) 참조.
