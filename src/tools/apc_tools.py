"""
APC 데이터 조회 LangChain Tools

새로운 쿼리 추가 방법:
  1. 함수에 @tool 데코레이터 추가
  2. docstring에 LLM이 이해할 수 있는 설명 작성 (한/영 모두 OK)
  3. src/tools/__init__.py 의 ALL_TOOLS 리스트에 추가
"""
from datetime import date, datetime
from typing import Optional

import pandas as pd
from langchain_core.tools import tool
from sqlalchemy.orm import Session

from src.config import get_engine
from src.models import ApcBatch, ApcMeasurement


def _session():
    return Session(get_engine())


# ──────────────────────────────────────────────
# Tool 1: 기간별 배치 목록 조회
# ──────────────────────────────────────────────
@tool
def get_batches_by_date_range(
    start_date: str,
    end_date: str,
    line_id: Optional[str] = None,
) -> str:
    """
    특정 기간에 생산된 배치 목록을 조회합니다.

    Args:
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date:   조회 종료일 (YYYY-MM-DD)
        line_id:    생산 라인 ID (옵션, 예: 'A', 'B')

    Returns:
        배치 ID, 제품코드, 라인, 시작시간, 상태를 담은 문자열
    """
    with _session() as s:
        q = s.query(ApcBatch).filter(
            ApcBatch.start_time >= _to_dt(start_date),
            ApcBatch.start_time <= _to_dt(end_date, end=True),
        )
        if line_id:
            q = q.filter(ApcBatch.line_id == line_id)

        rows = q.order_by(ApcBatch.start_time).all()

    if not rows:
        return "해당 기간에 조회된 배치가 없습니다."

    df = pd.DataFrame([{
        "batch_id":     r.batch_id,
        "product_code": r.product_code,
        "line_id":      r.line_id,
        "start_time":   r.start_time.strftime("%Y-%m-%d %H:%M"),
        "status":       r.status,
    } for r in rows])

    return df.to_string(index=False)


# ──────────────────────────────────────────────
# Tool 2: 기간별 배치 수량 집계
# ──────────────────────────────────────────────
@tool
def get_batch_count(
    start_date: str,
    end_date: str,
    status: Optional[str] = None,
) -> str:
    """
    특정 기간의 배치 생산 수량을 집계합니다.

    Args:
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date:   조회 종료일 (YYYY-MM-DD)
        status:     배치 상태 필터 (옵션: 'completed', 'failed', 'in_progress')

    Returns:
        총 배치 수 및 상태별 집계 결과 문자열
    """
    with _session() as s:
        q = s.query(ApcBatch).filter(
            ApcBatch.start_time >= _to_dt(start_date),
            ApcBatch.start_time <= _to_dt(end_date, end=True),
        )
        if status:
            q = q.filter(ApcBatch.status == status)

        rows = q.all()

    total = len(rows)
    if total == 0:
        return "해당 기간에 조회된 배치가 없습니다."

    # 상태별 집계
    status_counts: dict = {}
    for r in rows:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    summary = f"총 배치 수: {total}개\n"
    for st, cnt in status_counts.items():
        summary += f"  - {st}: {cnt}개\n"

    return summary.strip()


# ──────────────────────────────────────────────
# Tool 3: 배치 ID 목록 조회
# ──────────────────────────────────────────────
@tool
def get_batch_ids(start_date: str, end_date: str) -> str:
    """
    특정 기간에 생산된 배치의 ID 목록만 반환합니다.

    Args:
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date:   조회 종료일 (YYYY-MM-DD)

    Returns:
        배치 ID 목록 (콤마 구분)
    """
    with _session() as s:
        rows = (
            s.query(ApcBatch.batch_id)
            .filter(
                ApcBatch.start_time >= _to_dt(start_date),
                ApcBatch.start_time <= _to_dt(end_date, end=True),
            )
            .order_by(ApcBatch.start_time)
            .all()
        )

    if not rows:
        return "해당 기간에 조회된 배치가 없습니다."

    ids = [r.batch_id for r in rows]
    return f"배치 ID 목록 ({len(ids)}개):\n" + ", ".join(ids)


# ──────────────────────────────────────────────
# Tool 4: 특정 배치 상세 조회
# ──────────────────────────────────────────────
@tool
def get_batch_detail(batch_id: str) -> str:
    """
    특정 배치의 상세 정보와 측정값을 반환합니다.

    Args:
        batch_id: 배치 ID (예: BATCH-20260201-001)

    Returns:
        배치 기본 정보 + 측정 파라미터 상세
    """
    with _session() as s:
        batch = s.query(ApcBatch).filter(ApcBatch.batch_id == batch_id).first()
        if not batch:
            return f"배치 '{batch_id}'를 찾을 수 없습니다."

        measurements = (
            s.query(ApcMeasurement)
            .filter(ApcMeasurement.batch_id == batch_id)
            .all()
        )

    result = (
        f"[배치 정보]\n"
        f"  배치 ID   : {batch.batch_id}\n"
        f"  제품 코드  : {batch.product_code}\n"
        f"  라인      : {batch.line_id}\n"
        f"  시작 시간  : {batch.start_time}\n"
        f"  종료 시간  : {batch.end_time}\n"
        f"  상태      : {batch.status}\n"
    )

    if measurements:
        result += "\n[측정값]\n"
        for m in measurements:
            result += f"  {m.param_name}: {m.param_value} {m.unit}\n"

    return result.strip()


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────
def _to_dt(date_str: str, end: bool = False) -> datetime:
    """'YYYY-MM-DD' 문자열을 datetime으로 변환. end=True면 23:59:59"""
    d = date.fromisoformat(date_str)
    if end:
        return datetime(d.year, d.month, d.day, 23, 59, 59)
    return datetime(d.year, d.month, d.day, 0, 0, 0)
