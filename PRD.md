# PRD: APC 데이터 자연어 조회 시스템 (POC)
# v2 - DBGorilla 논문 기반 Function Calling 방식 적용

## 개정 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|---------|
| v1 | 2026-02-20 | 초안 (개별 @tool 함수 방식) |
| v2 | 2026-02-20 | DBGorilla 논문 기반 단일 통합 스키마 방식으로 전면 개정 |

---

## 1. 개요

### 배경
사내 사무업무 자동화 니즈 대응을 위한 첫 번째 POC.

**v1 방식의 문제** (개별 @tool 함수 방식):
- 업무가 늘어날수록 함수 수가 폭발적으로 증가
- LLM이 "어떤 함수를 선택"할지 결정해야 하므로 유사 함수 간 혼동 발생
- 새로운 필터/집계 조건이 생길 때마다 함수 신규 개발 필요

**v2 방식의 핵심 (DBGorilla 논문 방식)**:
> LLM은 "어떤 함수를 쓸지" 선택하는 게 아니라,
> "무엇을, 어떤 조건으로, 어떻게 집계할지"를 **하나의 규격화된 JSON으로 기입**한다.
> SQL 조립과 실행은 애플리케이션(Query Builder)이 담당한다.

### 목표
- 자연어 → 구조화 JSON(쿼리 명세) → SQL 조립 → DB 실행 → 자연어 응답 파이프라인 구축
- LLM은 SQL 문법을 몰라도 되는 역할 분리 구조 확립
- 필터/집계/그룹화 연산자를 JSON 항목 추가만으로 확장 가능한 설계

### 범위 (POC)
- 데이터: APC (Advanced Process Control) 데이터, PostgreSQL 저장
- LLM: 사내 OpenAI 호환 API (GPT OSS 모델)
- UI: CLI (검증 후 Web Chat 추가 고려)
- 자동화 스케줄링: POC 범위 외

---

## 2. 핵심 개념: 역할 분리

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM의 역할 (의도 파악)                                          │
│    자연어 → 쿼리 명세 JSON 작성                                   │
│    "무엇을(collection), 어떤 조건으로(filter),                    │
│     어떻게 집계(aggregation), 어떻게 묶을지(groupby)"             │
│    ※ SQL 문법은 전혀 몰라도 됨                                    │
├─────────────────────────────────────────────────────────────────┤
│  Query Builder의 역할 (기계적 변환)                               │
│    JSON 명세 → SQL 조립 (결정론적, 100% 예측 가능)                │
│    "integer_filter.operator='<', value=20"                      │
│    → "WHERE start_time BETWEEN ... AND ..."                     │
├─────────────────────────────────────────────────────────────────┤
│  DB의 역할 (실행)                                                 │
│    조립된 SQL 실행 → 결과 반환                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 시스템 아키텍처

```
[사용자 자연어 질문]
        │
        ▼
[LangChain Agent + LLM]
  역할: 자연어를 파싱하여 QuerySpec JSON을 생성
  출력: 구조화된 쿼리 명세 (JSON)
        │
        │  예시 출력:
        │  {
        │    "collection_name": "apc_batch",
        │    "date_range_filter": {"start": "2026-02-01", "end": "2026-02-20"},
        │    "string_filter": {"property_name": "line_id", "value": "A"},
        │    "integer_aggregation": {"operator": "COUNT"},
        │    "groupby_property": "status"
        │  }
        │
        ▼
[Query Builder]  ← 이번 POC의 핵심 구현 대상
  역할: QuerySpec JSON → SQLAlchemy 쿼리 조립 (기계적 변환)
  - collection_name → FROM 절
  - date_range_filter → WHERE start_time BETWEEN ... AND ...
  - string_filter → WHERE line_id = 'A'
  - integer_aggregation → SELECT COUNT(*)
  - groupby_property → GROUP BY status
        │
        ▼
[PostgreSQL DB]
        │
        ▼
[LLM 응답 가공]
  역할: raw 결과 데이터 → 자연어 설명
        │
        ▼
[사용자 응답 출력]
```

---

## 4. 핵심 설계: 통합 쿼리 스키마 (QuerySpec)

### 4-1. QuerySpec 구조 정의

LLM이 생성해야 하는 JSON의 전체 스키마. 각 항목은 선택적(Optional)이며, 질문의 복잡도에 따라 조합된다.

```python
class QuerySpec(BaseModel):
    # 필수: 조회 대상 테이블
    collection_name: str

    # 검색 (텍스트 의미 검색 - 향후 벡터 검색 확장 가능)
    search_query: Optional[str]

    # 날짜 범위 필터 (APC 시계열 데이터에 특화)
    date_range_filter: Optional[DateRangeFilter]

    # 정형 필터들
    integer_filter: Optional[IntegerFilter]    # 숫자 비교 (=, <, >, <=, >=)
    string_filter:  Optional[StringFilter]     # 문자열 비교 (=, LIKE, IN)
    boolean_filter: Optional[BooleanFilter]    # 불리언 (True/False)

    # 집계
    integer_aggregation: Optional[IntegerAggregation]  # COUNT, SUM, AVG, MIN, MAX

    # 그룹화
    groupby_property: Optional[str]

    # 결과 제한
    limit: Optional[int]
    order_by: Optional[OrderBy]
```

### 4-2. 각 컴포넌트 상세

```python
class DateRangeFilter(BaseModel):
    property_name: str = "start_time"   # 기본값: start_time
    start: str                           # YYYY-MM-DD
    end: str                             # YYYY-MM-DD

class IntegerFilter(BaseModel):
    property_name: str
    operator: Literal["=", "<", ">", "<=", ">=", "!="]
    value: float

class StringFilter(BaseModel):
    property_name: str
    operator: Literal["=", "LIKE", "IN", "!="]
    value: Union[str, List[str]]         # IN 연산자의 경우 리스트

class BooleanFilter(BaseModel):
    property_name: str
    value: bool

class IntegerAggregation(BaseModel):
    operator: Literal["COUNT", "SUM", "AVG", "MIN", "MAX"]
    property_name: Optional[str]         # COUNT(*) 이외의 경우 대상 컬럼

class OrderBy(BaseModel):
    property_name: str
    direction: Literal["ASC", "DESC"] = "DESC"
```

### 4-3. 자연어 → QuerySpec 변환 예시

**예시 1: 단순 기간 조회**
```
질문: "2월 1일부터 20일까지 생산된 배치 목록 알려줘"

QuerySpec:
{
  "collection_name": "apc_batch",
  "date_range_filter": {
    "property_name": "start_time",
    "start": "2026-02-01",
    "end": "2026-02-20"
  }
}

→ SQL: SELECT * FROM apc_batch
        WHERE start_time BETWEEN '2026-02-01' AND '2026-02-20'
```

**예시 2: 기간 + 집계**
```
질문: "2월 1일부터 20일까지 생산된 배치가 몇 개야?"

QuerySpec:
{
  "collection_name": "apc_batch",
  "date_range_filter": {"start": "2026-02-01", "end": "2026-02-20"},
  "integer_aggregation": {"operator": "COUNT"}
}

→ SQL: SELECT COUNT(*) FROM apc_batch
        WHERE start_time BETWEEN '2026-02-01' AND '2026-02-20'
```

**예시 3: 기간 + 필터 + 집계 + 그룹화**
```
질문: "이번 달 A라인 배치를 상태별로 몇 개인지 알려줘"

QuerySpec:
{
  "collection_name": "apc_batch",
  "date_range_filter": {"start": "2026-02-01", "end": "2026-02-20"},
  "string_filter": {"property_name": "line_id", "operator": "=", "value": "A"},
  "integer_aggregation": {"operator": "COUNT"},
  "groupby_property": "status"
}

→ SQL: SELECT status, COUNT(*) FROM apc_batch
        WHERE start_time BETWEEN '2026-02-01' AND '2026-02-20'
          AND line_id = 'A'
        GROUP BY status
```

**예시 4: 측정값 집계**
```
질문: "지난달 온도 파라미터의 평균값은?"

QuerySpec:
{
  "collection_name": "apc_measurement",
  "date_range_filter": {"property_name": "measured_at", "start": "2026-01-01", "end": "2026-01-31"},
  "string_filter": {"property_name": "param_name", "operator": "=", "value": "temperature"},
  "integer_aggregation": {"operator": "AVG", "property_name": "param_value"}
}

→ SQL: SELECT AVG(param_value) FROM apc_measurement
        WHERE measured_at BETWEEN '2026-01-01' AND '2026-01-31'
          AND param_name = 'temperature'
```

---

## 5. 데이터 설계

### 5-1. APC 테이블 스키마

```sql
-- 배치(Batch) 기본 정보
CREATE TABLE apc_batch (
    batch_id        VARCHAR(50) PRIMARY KEY,
    product_code    VARCHAR(50),
    line_id         VARCHAR(20),
    start_time      TIMESTAMP NOT NULL,
    end_time        TIMESTAMP,
    status          VARCHAR(20) DEFAULT 'completed',  -- completed | in_progress | failed
    created_at      TIMESTAMP DEFAULT NOW()
);

-- 배치 측정값
CREATE TABLE apc_measurement (
    id              SERIAL PRIMARY KEY,
    batch_id        VARCHAR(50) REFERENCES apc_batch(batch_id),
    param_name      VARCHAR(100),   -- temperature, pressure, flow_rate 등
    param_value     FLOAT,
    unit            VARCHAR(20),
    measured_at     TIMESTAMP NOT NULL
);
```

### 5-2. Collection 메타데이터 (LLM에게 제공)

LLM이 QuerySpec을 정확히 작성하려면 어떤 테이블에 어떤 컬럼이 있는지 알아야 한다.
이를 **Collection Registry**로 관리한다.

```python
COLLECTION_REGISTRY = {
    "apc_batch": {
        "description": "배치 생산 기록. 라인별, 제품별 배치 정보를 포함.",
        "columns": {
            "batch_id":     {"type": "string",  "description": "배치 고유 ID"},
            "product_code": {"type": "string",  "description": "제품 코드"},
            "line_id":      {"type": "string",  "description": "생산 라인 (A, B, C)"},
            "start_time":   {"type": "datetime","description": "배치 시작 시간"},
            "end_time":     {"type": "datetime","description": "배치 종료 시간"},
            "status":       {"type": "string",  "description": "상태: completed | failed | in_progress"},
        }
    },
    "apc_measurement": {
        "description": "배치별 공정 파라미터 측정값 (온도, 압력, 유량 등)",
        "columns": {
            "batch_id":    {"type": "string",  "description": "배치 ID (apc_batch 참조)"},
            "param_name":  {"type": "string",  "description": "파라미터명: temperature | pressure | flow_rate"},
            "param_value": {"type": "float",   "description": "측정값"},
            "unit":        {"type": "string",  "description": "단위"},
            "measured_at": {"type": "datetime","description": "측정 시간"},
        }
    }
}
```

---

## 6. 기술 스택

| 구성요소 | 기술 | 비고 |
|---------|------|------|
| Language | Python 3.11+ | |
| 스키마 검증 | Pydantic v2 | QuerySpec 모델 정의 및 검증 |
| LLM Framework | LangChain 0.3.x | Structured Output 기능 활용 |
| LLM | 사내 OpenAI 호환 API | base_url 설정으로 연동 |
| DB | PostgreSQL 15+ | |
| DB ORM | SQLAlchemy 2.x | Query Builder 조립에 활용 |
| 데이터 처리 | Pandas | 결과 가공 |
| 설정 관리 | python-dotenv | |

---

## 7. 구현 계획

### Phase 1: 환경 구성 및 데이터 준비
- [ ] PostgreSQL 설치 및 DB/테이블 생성
- [ ] APC 샘플 데이터 적재 스크립트 (seed_data.py)
- [ ] Python 환경 구성 (requirements.txt)
- [ ] Collection Registry 정의

### Phase 2: QuerySpec + Query Builder 구현 ← 핵심
- [ ] Pydantic으로 QuerySpec 모델 정의 (필터, 집계, 그룹화 등)
- [ ] Query Builder 구현 (JSON → SQLAlchemy 쿼리 조립)
- [ ] Query Builder 단위 테스트 (다양한 QuerySpec 조합)

### Phase 3: LangChain Structured Output 연동
- [ ] LLM → QuerySpec JSON 생성 (with_structured_output 활용)
- [ ] Collection Registry를 System Prompt에 삽입
- [ ] Agent 구성 및 전체 파이프라인 연결

### Phase 4: 응답 가공 및 검증
- [ ] 쿼리 결과 → LLM 자연어 응답 가공
- [ ] 시나리오 기반 E2E 테스트 (아래 8개 시나리오)
- [ ] 결과 정리

---

## 8. 디렉토리 구조

```
AutoOfficeWork/
├── PRD.md
├── README.md
├── requirements.txt
├── .env.example
│
├── db/
│   ├── schema.sql
│   ├── seed_data.py
│   └── registry.py              # Collection Registry (테이블/컬럼 메타데이터)
│
├── src/
│   ├── config.py                # DB/LLM 연결 설정
│   ├── models.py                # SQLAlchemy ORM 모델
│   │
│   ├── query/                   ← v2 핵심 신규 레이어
│   │   ├── __init__.py
│   │   ├── schema.py            # QuerySpec Pydantic 모델 정의
│   │   └── builder.py           # QuerySpec → SQL 조립 (Query Builder)
│   │
│   └── agent.py                 # LangChain Agent (Structured Output 방식)
│
├── tests/
│   ├── test_builder.py          # Query Builder 단위 테스트
│   └── test_agent.py            # E2E 시나리오 테스트
│
└── main.py
```

---

## 9. 성공 기준 (POC)

### 테스트 시나리오 8종

| # | 질문 | 기대 QuerySpec 핵심 | 검증 포인트 |
|---|------|-------------------|------------|
| 1 | "2월 1일~20일 배치 목록" | date_range_filter만 | 기본 기간 조회 |
| 2 | "이번 달 배치 몇 개야?" | date_range_filter + COUNT | 집계 |
| 3 | "A라인 배치 수" | string_filter + COUNT | 문자열 필터 |
| 4 | "이번 달 A라인 배치를 상태별로" | date+string+COUNT+groupby | 그룹화 |
| 5 | "failed 배치 목록" | string_filter(status=failed) | 상태 필터 |
| 6 | "온도 파라미터 평균값" | measurement + AVG | 측정값 집계 |
| 7 | "지난달 배치 중 가장 최근 것" | date+ORDER BY DESC+limit=1 | 정렬+제한 |
| 8 | "B라인 이번 달 completed 배치 수" | date+string×2+COUNT | 다중 필터 |

### 성공 지표

| 항목 | 기준 |
|------|------|
| QuerySpec 정확도 | 8개 시나리오 중 7개 이상 올바른 JSON 생성 |
| Query Builder 정확도 | 유효한 QuerySpec 입력 시 100% 올바른 SQL 생성 |
| 응답 품질 | 조회 결과를 자연어로 명확하게 설명 |
| 응답 시간 | 단순 조회 기준 5초 이내 |
| 확장성 | 새 필터 타입 추가 시 Builder에만 로직 추가, Agent 무수정 |

---

## 10. v1 대비 v2 핵심 차이점 요약

| 항목 | v1 (개별 @tool 함수) | v2 (통합 QuerySpec) |
|------|---------------------|---------------------|
| LLM의 역할 | 여러 함수 중 하나를 선택 | 하나의 JSON 양식을 채움 |
| 확장 방법 | 새 함수 추가 (개발 필요) | JSON 항목 추가 (스키마 확장) |
| SQL 생성 | 함수 내부에서 직접 작성 | Query Builder가 기계적 조립 |
| LLM 혼동 가능성 | 유사 함수 간 선택 오류 | 단일 스키마이므로 선택 불필요 |
| 복합 조건 처리 | 여러 함수 호출 필요 | 단일 JSON에 모든 조건 포함 |
| DB 종속성 | 함수마다 SQL 직접 포함 | Builder만 교체하면 다른 DB 지원 |

---

## 11. 향후 확장 방향 (POC 이후)

1. **필터 확장**: `list_filter` (IN 연산), `null_filter` (IS NULL) 추가
2. **텍스트 검색**: `search_query` 필드를 벡터 검색(pgvector)으로 확장
3. **다중 테이블**: JOIN 연산 지원 (BatchWithMeasurement 뷰 방식)
4. **데이터 소스 확장**: MES, ERP용 Collection Registry + Builder 추가
5. **출력 가공**: 엑셀 차트 생성, 이메일 발송 Tool 연계
6. **스케줄링**: APScheduler로 정기 리포트 자동화
