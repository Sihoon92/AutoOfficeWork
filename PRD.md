# PRD: APC 데이터 자연어 조회 시스템 (POC)

## 1. 개요

### 배경
사내 사무업무 자동화 니즈 대응을 위한 첫 번째 POC.
Text-to-SQL 수준의 완전 자동화 이전에, **정형화된 쿼리 함수 + LLM 조합**으로
자연어 질문 → 데이터 조회 → 이해하기 쉬운 응답 파이프라인을 검증한다.

### 목표
- 사용자가 자연어로 APC 데이터를 조회할 수 있는 POC 시스템 구축
- LangChain Tool Use 기반의 확장 가능한 함수 설계 패턴 확립
- 추후 다른 데이터 소스(MES, ERP 등) 확장을 위한 기반 마련

### 범위 (POC)
- 데이터: APC (Advanced Process Control) 데이터, PostgreSQL 저장
- LLM: 사내 OpenAI 호환 API (GPT OSS 모델)
- UI: CLI 또는 간단한 Web Chat (FastAPI + HTML)
- 자동화 스케줄링: 이번 POC 범위 외

---

## 2. 시스템 아키텍처

```
[사용자 자연어 질문]
        │
        ▼
[LangChain Agent]
  - LLM: 사내 OpenAI 호환 API
  - 사용자 질문을 분석하여 적절한 Tool(쿼리 함수) 선택
  - 필요한 파라미터 추출 (날짜, 배치ID 등)
        │
        ▼
[Query Tool Layer]  ← 이번 POC의 핵심 구현 대상
  - get_batches_by_date_range()
  - get_batch_count()
  - get_batch_ids()
  - (확장 가능한 구조)
        │
        ▼
[PostgreSQL DB]
  - APC 데이터 테이블
        │
        ▼
[LLM 응답 가공]
  - 조회된 데이터를 사용자 친화적 문장으로 변환
        │
        ▼
[사용자 응답 출력]
```

---

## 3. 데이터 설계

### 3-1. APC 테이블 스키마 (예시 기반 설계)

```sql
-- 배치(Batch) 기본 정보 테이블
CREATE TABLE apc_batch (
    batch_id        VARCHAR(50) PRIMARY KEY,   -- 배치 ID (예: BATCH-20260101-001)
    product_code    VARCHAR(50),               -- 제품 코드
    line_id         VARCHAR(20),               -- 생산 라인 ID
    start_time      TIMESTAMP NOT NULL,        -- 배치 시작 시간
    end_time        TIMESTAMP,                 -- 배치 종료 시간
    status          VARCHAR(20),               -- 상태 (completed, in_progress, failed)
    created_at      TIMESTAMP DEFAULT NOW()
);

-- 배치 파라미터/측정값 테이블
CREATE TABLE apc_measurement (
    id              SERIAL PRIMARY KEY,
    batch_id        VARCHAR(50) REFERENCES apc_batch(batch_id),
    param_name      VARCHAR(100),              -- 파라미터명 (온도, 압력 등)
    param_value     FLOAT,                     -- 측정값
    unit            VARCHAR(20),               -- 단위
    measured_at     TIMESTAMP NOT NULL
);
```

### 3-2. 샘플 데이터
- 약 3개월치 APC 데이터를 PostgreSQL에 적재
- 실제 사내 APC 데이터 포맷에 맞게 스키마 조정 필요

---

## 4. 기능 요구사항

### 4-1. 쿼리 함수 정의 (Query Tool Layer)

LangChain `@tool` 데코레이터로 정의. LLM이 자동으로 선택 및 호출.

| 함수명 | 설명 | 입력 파라미터 | 출력 |
|--------|------|--------------|------|
| `get_batches_by_date_range` | 특정 기간의 배치 목록 조회 | start_date, end_date, line_id(옵션) | 배치 목록 (ID, 시간, 상태) |
| `get_batch_count` | 특정 기간의 배치 수량 집계 | start_date, end_date, status(옵션) | 배치 카운트 |
| `get_batch_ids` | 배치 ID 목록만 조회 | start_date, end_date | ID 리스트 |
| `get_batch_detail` | 특정 배치 상세 정보 조회 | batch_id | 배치 상세 + 측정값 |

#### 확장성 설계 원칙
- 각 함수는 독립적으로 추가/제거 가능한 모듈 구조
- 새 데이터 소스(MES 등) 추가 시 동일한 `@tool` 패턴으로 확장
- 파라미터 타입과 description을 명확히 작성 → LLM이 정확히 선택하도록

### 4-2. 자연어 → 쿼리 매핑 예시

| 사용자 입력 | LLM 선택 함수 | 추출 파라미터 |
|------------|--------------|--------------|
| "2월 1일부터 2월 20일까지 생산된 배치가 무엇이고 몇 개인지 알려줘" | `get_batches_by_date_range` + `get_batch_count` | start_date=2026-02-01, end_date=2026-02-20 |
| "이번 달 A라인 배치 수 알려줘" | `get_batch_count` | start_date=이번달 1일, end_date=오늘, line_id=A |
| "BATCH-001 상세 정보 보여줘" | `get_batch_detail` | batch_id=BATCH-001 |

### 4-3. LLM 응답 가공

- 조회된 raw 데이터를 사람이 읽기 쉬운 자연어 문장으로 변환
- 예시 출력:
  ```
  2026년 2월 1일부터 20일까지 총 47개의 배치가 생산되었습니다.

  주요 배치 목록:
  - BATCH-20260201-001 (A라인, 완료)
  - BATCH-20260201-002 (B라인, 완료)
  ...
  ```

---

## 5. 기술 스택

| 구성요소 | 기술 | 비고 |
|---------|------|------|
| Language | Python 3.11+ | |
| LLM Framework | LangChain 0.3.x | Tool Use / Agent 기능 활용 |
| LLM | 사내 OpenAI 호환 API | GPT OSS 모델, base_url 설정으로 연동 |
| DB | PostgreSQL 15+ | |
| DB ORM | SQLAlchemy 2.x | 쿼리 추상화 |
| 데이터 처리 | Pandas | 결과 가공 |
| 설정 관리 | python-dotenv | DB URL, API key 등 환경변수 관리 |
| (옵션) Web UI | FastAPI + Jinja2 | CLI 검증 후 필요 시 추가 |

---

## 6. 구현 계획

### Phase 1: 환경 구성 및 데이터 준비
- [ ] PostgreSQL 설치 및 DB/테이블 생성
- [ ] APC 샘플 데이터 적재 스크립트 작성
- [ ] Python 환경 구성 (requirements.txt)
- [ ] .env 설정 (DB 접속 정보, LLM API 엔드포인트/키)

### Phase 2: 쿼리 함수 구현
- [ ] SQLAlchemy 모델 정의 (apc_batch, apc_measurement)
- [ ] 기본 쿼리 함수 4개 구현
- [ ] 단위 테스트 작성 (pytest)

### Phase 3: LangChain Agent 연동
- [ ] 사내 OpenAI 호환 API LangChain 연결
- [ ] 쿼리 함수를 LangChain Tool로 등록
- [ ] Agent 구성 및 대화 루프 구현

### Phase 4: 응답 가공 및 검증
- [ ] LLM 응답 포맷 프롬프트 튜닝
- [ ] 시나리오 기반 E2E 테스트
- [ ] 결과 정리 및 다음 단계 계획 수립

---

## 7. 디렉토리 구조

```
AutoOfficeWork/
├── PRD.md                          # 이 문서
├── README.md                       # 실행 방법
├── requirements.txt
├── .env.example                    # 환경변수 템플릿
│
├── db/
│   ├── schema.sql                  # 테이블 생성 DDL
│   └── seed_data.py                # 샘플 데이터 적재 스크립트
│
├── src/
│   ├── config.py                   # DB/LLM 설정
│   ├── models.py                   # SQLAlchemy ORM 모델
│   │
│   ├── tools/                      # LangChain Tool 함수들 (확장 지점)
│   │   ├── __init__.py
│   │   └── apc_tools.py            # APC 데이터 쿼리 Tools
│   │
│   └── agent.py                    # LangChain Agent 메인 로직
│
├── tests/
│   ├── test_tools.py               # 쿼리 함수 단위 테스트
│   └── test_agent.py               # Agent E2E 테스트
│
└── main.py                         # 진입점 (CLI)
```

---

## 8. 성공 기준 (POC)

| 항목 | 기준 |
|------|------|
| 정확도 | 5개 테스트 시나리오 중 4개 이상 정확한 함수 선택 |
| 응답 품질 | 조회 결과를 자연어로 명확하게 설명 |
| 응답 시간 | 단순 조회 기준 5초 이내 |
| 확장성 | 새 Tool 함수 추가 시 Agent 코드 수정 없이 동작 |

---

## 9. 향후 확장 방향 (POC 이후)

1. **데이터 소스 확장**: MES, ERP 연동 Tool 추가
2. **스케줄링**: APScheduler로 정기 리포트 자동 발송
3. **출력 가공**: 엑셀 차트 생성, 이메일 발송 Tool 추가
4. **UI**: Web 기반 채팅 인터페이스
5. **멀티 스텝**: 여러 Tool을 조합한 복잡한 업무 자동화
