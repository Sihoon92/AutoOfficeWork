"""
Spider 2.0-Lite 평가 스크립트

사용법:
    # 기본 (전체 SQLite 예제 평가)
    python -m spider2.evaluator --data_dir ./spider2-lite --db_dir ./spider2-lite/resource/databases

    # 예제 수 제한
    python -m spider2.evaluator --data_dir ./spider2-lite --db_dir ./spider2-lite/resource/databases --limit 20

    # 결과를 JSON 파일로 저장
    python -m spider2.evaluator --data_dir ./spider2-lite --db_dir ./spider2-lite/resource/databases --output results.json

평가 지표:
    - Execution Accuracy: 생성된 SQL 실행 결과가 gold SQL 실행 결과와 일치하는 비율
    - 오류 유형 분류: builder_error / execution_error / mismatch / correct

Spider 2.0-Lite JSONL 필드 (지원하는 변형):
    - instance_id / id
    - instruction / question
    - db_id
    - gold_sql / sql (gold SQL 문자열)
    - type / dialect (sqlite 필터링용)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

from spider2.graph import run as graph_run
from spider2.schema_loader import find_sqlite_db


# ── JSONL 로더 ────────────────────────────────────────
def load_examples(data_dir: Path, dialect_filter: str = "sqlite") -> list[dict]:
    """
    Spider 2.0-Lite JSONL 파일에서 SQLite 예제를 로드.

    여러 필드명 변형을 처리:
        question  ← instruction | question
        gold_sql  ← gold_sql | sql
        dialect   ← type | dialect
    """
    candidates = list(data_dir.glob("*.jsonl")) + list(data_dir.glob("spider2-lite*.jsonl"))
    if not candidates:
        # 재귀 탐색
        candidates = list(data_dir.rglob("spider2-lite*.jsonl"))
    if not candidates:
        candidates = list(data_dir.rglob("*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"JSONL 파일을 찾을 수 없습니다: {data_dir}")

    jsonl_path = candidates[0]
    print(f"데이터 파일: {jsonl_path}")

    examples: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)

            # 필드명 정규화
            dialect = raw.get("type") or raw.get("dialect") or ""
            if dialect_filter and dialect_filter.lower() not in dialect.lower():
                continue

            question = raw.get("instruction") or raw.get("question") or ""
            gold_sql = raw.get("gold_sql") or raw.get("sql") or ""
            instance_id = raw.get("instance_id") or raw.get("id") or ""
            db_id = raw.get("db_id") or ""

            if not question or not db_id:
                continue

            examples.append(
                {
                    "instance_id": instance_id,
                    "question": question,
                    "db_id": db_id,
                    "gold_sql": gold_sql,
                    "dialect": dialect,
                }
            )

    print(f"SQLite 예제 수: {len(examples)}")
    return examples


# ── SQL 실행 결과 비교 ─────────────────────────────────
def execute_sql_on_db(db_path: str, sql: str) -> Optional[set]:
    """
    SQLite DB에서 SQL을 실행하고 결과 집합(frozenset of tuples)을 반환.
    오류 발생 시 None 반환.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return set(rows)
    except Exception:
        return None


def results_match(gold_result: Optional[set], pred_result: Optional[set]) -> bool:
    """두 실행 결과 집합이 동일한지 비교 (순서 무관)"""
    if gold_result is None or pred_result is None:
        return False
    return gold_result == pred_result


# ── 평가 실행 ─────────────────────────────────────────
def evaluate(
    data_dir: str,
    db_dir: str,
    limit: Optional[int] = None,
    output: Optional[str] = None,
) -> dict:
    """
    Spider 2.0-Lite SQLite 예제에 대해 전체 평가를 수행.

    Returns:
        평가 요약 dict (accuracy, 오류 분류, 상세 결과 포함)
    """
    data_path = Path(data_dir)
    db_path_root = Path(db_dir)

    examples = load_examples(data_path)
    if limit:
        examples = examples[:limit]

    results: list[dict] = []
    stats = {"correct": 0, "mismatch": 0, "builder_error": 0, "execution_error": 0, "db_not_found": 0}

    for i, ex in enumerate(examples, 1):
        instance_id = ex["instance_id"]
        question = ex["question"]
        db_id = ex["db_id"]
        gold_sql = ex["gold_sql"]

        print(f"\n[{i}/{len(examples)}] {instance_id}")
        print(f"  Q: {question[:80]}...")

        # DB 파일 탐색
        db_file = find_sqlite_db(db_path_root, db_id)
        if db_file is None:
            print(f"  ✗ DB 파일 없음: {db_id}")
            stats["db_not_found"] += 1
            results.append({**ex, "status": "db_not_found", "pred_sql": None, "retry_count": 0})
            continue

        # 파이프라인 실행
        t0 = time.time()
        try:
            state = graph_run(question, str(db_file))
        except Exception as e:
            print(f"  ✗ 파이프라인 오류: {e}")
            stats["execution_error"] += 1
            results.append({**ex, "status": "execution_error", "pred_sql": None, "retry_count": 0, "error": str(e)})
            continue
        elapsed = time.time() - t0

        pred_sql = state.get("sql")
        pred_result_str = state.get("result")
        retry_count = state.get("retry_count", 0)
        error = state.get("error")

        # 오류 판단
        if error and not pred_sql:
            print(f"  ✗ 빌더 오류 (retry={retry_count}): {error[:60]}")
            stats["builder_error"] += 1
            results.append({
                **ex, "status": "builder_error",
                "pred_sql": None, "retry_count": retry_count, "error": error,
            })
            continue

        if error and pred_sql:
            print(f"  ✗ 실행 오류 (retry={retry_count}): {error[:60]}")
            stats["execution_error"] += 1
            results.append({
                **ex, "status": "execution_error",
                "pred_sql": pred_sql, "retry_count": retry_count, "error": error,
            })
            continue

        # Gold SQL 실행 결과와 비교
        gold_result = execute_sql_on_db(str(db_file), gold_sql) if gold_sql else None
        pred_result = execute_sql_on_db(str(db_file), pred_sql) if pred_sql else None

        if results_match(gold_result, pred_result):
            status = "correct"
            stats["correct"] += 1
            print(f"  ✓ 정답 (retry={retry_count}, {elapsed:.1f}s)")
        else:
            status = "mismatch"
            stats["mismatch"] += 1
            print(f"  △ 불일치 (retry={retry_count}, {elapsed:.1f}s)")
            if pred_sql:
                print(f"  pred_sql: {pred_sql[:100]}")

        results.append({
            **ex,
            "status": status,
            "pred_sql": pred_sql,
            "retry_count": retry_count,
            "elapsed_sec": round(elapsed, 2),
        })

    # 요약
    total = len(examples)
    evaluated = total - stats["db_not_found"]
    accuracy = stats["correct"] / evaluated if evaluated > 0 else 0.0

    summary = {
        "total": total,
        "evaluated": evaluated,
        "accuracy": round(accuracy, 4),
        "stats": stats,
        "results": results,
    }

    print("\n" + "=" * 50)
    print(f"Execution Accuracy: {accuracy:.2%} ({stats['correct']}/{evaluated})")
    print(f"  정답:      {stats['correct']}")
    print(f"  불일치:    {stats['mismatch']}")
    print(f"  빌더 오류: {stats['builder_error']}")
    print(f"  실행 오류: {stats['execution_error']}")
    print(f"  DB 없음:   {stats['db_not_found']}")
    print("=" * 50)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\n결과 저장: {output}")

    return summary


# ── CLI 진입점 ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Spider 2.0-Lite Text-to-SQL 평가 (SQLite 예제 대상)"
    )
    parser.add_argument(
        "--data_dir",
        required=True,
        help="spider2-lite JSONL 파일이 있는 디렉토리 경로",
    )
    parser.add_argument(
        "--db_dir",
        required=True,
        help="SQLite DB 파일들이 있는 디렉토리 (databases/)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="평가할 최대 예제 수 (기본: 전체)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="결과를 저장할 JSON 파일 경로",
    )
    args = parser.parse_args()

    evaluate(
        data_dir=args.data_dir,
        db_dir=args.db_dir,
        limit=args.limit,
        output=args.output,
    )


if __name__ == "__main__":
    main()
