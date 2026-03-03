"""
Spider 2.0-Lite 평가 스크립트

실제 Spider 2.0-Lite 레포 구조:
    Spider2/                           ← git clone 대상 (레포 루트)
    └── spider2-lite/                  ← --data_dir 에 지정
        ├── spider2-lite.jsonl         ← 질문 목록 (instance_id, db, question)
        ├── resource/
        │   └── databases/
        │       └── sqlite/            ← --db_dir 에 지정
        │           ├── Airlines/
        │           ├── Baseball/
        │           └── .../{db}.sqlite
        └── evaluation_suite/
            └── gold/
                └── sql/               ← --gold_dir 에 지정
                    └── {instance_id}.sql

사용법:
    python -m spider2.evaluator \\
        --data_dir  ./Spider2/spider2-lite \\
        --db_dir    ./Spider2/spider2-lite/resource/databases/sqlite \\
        --gold_dir  ./Spider2/spider2-lite/evaluation_suite/gold/sql

    # 예제 수 제한
    python -m spider2.evaluator ... --limit 20

    # 결과 JSON 저장
    python -m spider2.evaluator ... --output results.json

평가 지표:
    - Execution Accuracy: pred SQL 실행 결과 == gold SQL 실행 결과 비율
    - 오류 유형: builder_error / execution_error / mismatch / correct / no_gold

JSONL 실제 필드 (Spider 2.0-Lite):
    - instance_id : 예제 ID (예: local_001, bq011)
    - db          : 데이터베이스 이름 (폴더명과 일치)
    - question    : 자연어 질문
    - external_knowledge : 외부 문서명 (옵션)
    ※ gold_sql / dialect 필드는 JSONL에 없음
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from spider2.graph import run as graph_run
from spider2.schema_loader import find_sqlite_db


# ── Gold SQL 로더 ─────────────────────────────────────
def load_gold_sql(gold_sql_dir: Path, instance_id: str) -> Optional[str]:
    """
    evaluation_suite/gold/sql/{instance_id}.sql 파일에서 gold SQL을 읽어 반환.
    파일이 없으면 None 반환.
    """
    sql_file = gold_sql_dir / f"{instance_id}.sql"
    if not sql_file.exists():
        return None
    return sql_file.read_text(encoding="utf-8").strip()


# ── JSONL 로더 ────────────────────────────────────────
def load_examples(data_dir: Path, db_dir: Path) -> list[dict]:
    """
    Spider 2.0-Lite JSONL에서 SQLite 예제만 로드.

    SQLite 판별 방식:
        JSONL에 dialect/type 필드 없음 → `db` 필드값으로 db_dir 내 폴더 존재 여부 확인.
        폴더가 존재하면 local SQLite 예제로 간주.

    JSONL 실제 필드: instance_id, db, question, external_knowledge
    """
    candidates = (
        list(data_dir.glob("spider2-lite.jsonl"))
        + list(data_dir.glob("*.jsonl"))
        + list(data_dir.rglob("spider2-lite.jsonl"))
    )
    if not candidates:
        raise FileNotFoundError(f"JSONL 파일을 찾을 수 없습니다: {data_dir}")

    jsonl_path = candidates[0]
    print(f"데이터 파일: {jsonl_path}")

    examples: list[dict] = []
    skipped_bq_sf = 0

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)

            instance_id = raw.get("instance_id") or raw.get("id") or ""
            db_name = raw.get("db") or raw.get("db_id") or ""
            question = raw.get("question") or raw.get("instruction") or ""

            if not instance_id or not db_name or not question:
                continue

            # SQLite DB 파일이 db_dir 내에 존재하는지로 local 예제 판별
            db_file = find_sqlite_db(db_dir, db_name)
            if db_file is None:
                skipped_bq_sf += 1
                continue

            examples.append(
                {
                    "instance_id": instance_id,
                    "question": question,
                    "db_name": db_name,
                    "db_file": str(db_file),
                }
            )

    print(f"SQLite 예제 수: {len(examples)}  (BigQuery/Snowflake 제외: {skipped_bq_sf}개)")
    return examples


# ── SQL 실행 결과 비교 ─────────────────────────────────
def execute_sql_on_db(db_path: str, sql: str) -> Optional[set]:
    """SQLite DB에서 SQL 실행 후 결과 집합 반환. 오류 시 None."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return set(rows)
    except Exception:
        return None


def results_match(gold: Optional[set], pred: Optional[set]) -> bool:
    """두 실행 결과 집합이 동일한지 비교 (순서 무관)"""
    if gold is None or pred is None:
        return False
    return gold == pred


# ── 평가 실행 ─────────────────────────────────────────
def evaluate(
    data_dir: str,
    db_dir: str,
    gold_sql_dir: str,
    limit: Optional[int] = None,
    output: Optional[str] = None,
) -> dict:
    """Spider 2.0-Lite SQLite 예제 전체 평가."""
    data_path = Path(data_dir)
    db_path_root = Path(db_dir)
    gold_path = Path(gold_sql_dir)

    examples = load_examples(data_path, db_path_root)
    if limit:
        examples = examples[:limit]

    results: list[dict] = []
    stats = {
        "correct": 0,
        "mismatch": 0,
        "builder_error": 0,
        "execution_error": 0,
        "no_gold": 0,
    }

    for i, ex in enumerate(examples, 1):
        instance_id = ex["instance_id"]
        question = ex["question"]
        db_file = ex["db_file"]

        print(f"\n[{i}/{len(examples)}] {instance_id}  db={ex['db_name']}")
        print(f"  Q: {question[:80]}{'...' if len(question) > 80 else ''}")

        # Gold SQL 로드
        gold_sql = load_gold_sql(gold_path, instance_id)
        if gold_sql is None:
            print(f"  - gold SQL 없음: {gold_path}/{instance_id}.sql")
            stats["no_gold"] += 1
            results.append({**ex, "status": "no_gold", "pred_sql": None})
            continue

        # 파이프라인 실행
        t0 = time.time()
        try:
            state = graph_run(question, db_file)
        except Exception as e:
            print(f"  ✗ 파이프라인 오류: {e}")
            stats["execution_error"] += 1
            results.append({**ex, "status": "execution_error", "pred_sql": None, "error": str(e)})
            continue
        elapsed = time.time() - t0

        pred_sql = state.get("sql")
        retry_count = state.get("retry_count", 0)
        error = state.get("error")

        # 빌더/실행 오류 판단
        if error and not pred_sql:
            print(f"  ✗ 빌더 오류 (retry={retry_count}): {error[:80]}")
            stats["builder_error"] += 1
            results.append({**ex, "status": "builder_error", "pred_sql": None,
                            "retry_count": retry_count, "error": error})
            continue

        if error and pred_sql:
            print(f"  ✗ 실행 오류 (retry={retry_count}): {error[:80]}")
            stats["execution_error"] += 1
            results.append({**ex, "status": "execution_error", "pred_sql": pred_sql,
                            "retry_count": retry_count, "error": error})
            continue

        # Gold vs Pred 결과 비교
        gold_result = execute_sql_on_db(db_file, gold_sql)
        pred_result = execute_sql_on_db(db_file, pred_sql) if pred_sql else None

        if results_match(gold_result, pred_result):
            status = "correct"
            stats["correct"] += 1
            print(f"  ✓ 정답  (retry={retry_count}, {elapsed:.1f}s)")
        else:
            status = "mismatch"
            stats["mismatch"] += 1
            print(f"  △ 불일치 (retry={retry_count}, {elapsed:.1f}s)")
            if pred_sql:
                print(f"    pred: {pred_sql[:120]}")

        results.append({
            **ex,
            "status": status,
            "pred_sql": pred_sql,
            "gold_sql": gold_sql,
            "retry_count": retry_count,
            "elapsed_sec": round(elapsed, 2),
        })

    # 요약
    total = len(examples)
    evaluated = total - stats["no_gold"]
    accuracy = stats["correct"] / evaluated if evaluated > 0 else 0.0

    summary = {
        "total": total,
        "evaluated": evaluated,
        "accuracy": round(accuracy, 4),
        "stats": stats,
        "results": results,
    }

    print("\n" + "=" * 50)
    print(f"Execution Accuracy : {accuracy:.2%}  ({stats['correct']}/{evaluated})")
    print(f"  정답:      {stats['correct']}")
    print(f"  불일치:    {stats['mismatch']}")
    print(f"  빌더 오류: {stats['builder_error']}")
    print(f"  실행 오류: {stats['execution_error']}")
    print(f"  gold 없음: {stats['no_gold']}")
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
    parser.add_argument("--data_dir", required=True,
                        help="spider2-lite.jsonl이 있는 디렉토리 (spider2-lite/)")
    parser.add_argument("--db_dir", required=True,
                        help="SQLite DB 폴더 (resource/databases/sqlite/)")
    parser.add_argument("--gold_dir", required=True,
                        help="Gold SQL .sql 파일 폴더 (evaluation_suite/gold/sql/)")
    parser.add_argument("--limit", type=int, default=None,
                        help="평가할 최대 예제 수 (기본: 전체)")
    parser.add_argument("--output", default=None,
                        help="결과를 저장할 JSON 파일 경로")
    args = parser.parse_args()

    evaluate(
        data_dir=args.data_dir,
        db_dir=args.db_dir,
        gold_sql_dir=args.gold_dir,
        limit=args.limit,
        output=args.output,
    )


if __name__ == "__main__":
    main()
