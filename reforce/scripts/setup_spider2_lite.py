#!/usr/bin/env python3
"""
setup_spider2_lite.py
─────────────────────
Spider2-lite 데이터셋을 ReFoRCE가 읽을 수 있는 examples/ 구조로 변환합니다.

사용법:
    python scripts/setup_spider2_lite.py --spider2_path /path/to/Spider2/spider2-lite

실행 후 생성되는 구조:
    examples/
    ├── spider2-lite.jsonl       ← ReFoRCE가 태스크 목록으로 사용
    └── local003/                ← instance_id별 폴더 (SQLite만 지원)
        └── chinook.sqlite

이후 실행:
    python reconstruct_data.py --example_folder examples --add_description --add_sample_rows
    python run.py --task lite --db_path examples --output_path output/test-run
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path


def find_sqlite_file(sqlite_root: Path, db_name: str) -> Path | None:
    """db_name에 해당하는 .sqlite 파일을 resource/databases/sqlite/ 하위에서 탐색."""
    # 1순위: resource/databases/sqlite/{db_name}/*.sqlite
    db_dir = sqlite_root / db_name
    if db_dir.exists():
        for f in db_dir.rglob("*.sqlite"):
            return f
        for f in db_dir.rglob("*.db"):
            return f

    # 2순위: db_name이 정확히 매칭되지 않을 경우 퍼지 탐색
    for candidate in sqlite_root.iterdir():
        if candidate.is_dir() and db_name.lower() in candidate.name.lower():
            for f in candidate.rglob("*.sqlite"):
                return f
            for f in candidate.rglob("*.db"):
                return f

    return None


def setup(spider2_path: str, example_folder: str, limit: int | None):
    spider2_root = Path(spider2_path).resolve()
    sqlite_root = spider2_root / "resource" / "databases" / "sqlite"
    jsonl_src = spider2_root / "spider2-lite.jsonl"

    if not jsonl_src.exists():
        print(f"[ERROR] spider2-lite.jsonl 파일을 찾을 수 없습니다: {jsonl_src}")
        sys.exit(1)
    if not sqlite_root.exists():
        print(f"[ERROR] SQLite DB 폴더를 찾을 수 없습니다: {sqlite_root}")
        sys.exit(1)

    example_root = Path(example_folder).resolve()
    example_root.mkdir(parents=True, exist_ok=True)

    # ── 1. spider2-lite.jsonl 복사 ──────────────────────────────────────────
    dest_jsonl = example_root / "spider2-lite.jsonl"
    shutil.copy2(jsonl_src, dest_jsonl)
    print(f"[OK] JSONL 복사: {dest_jsonl}")

    # ── 2. 태스크별 SQLite 파일 복사 ─────────────────────────────────────────
    local_instances = []
    with open(jsonl_src, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry["instance_id"].startswith("local"):
                local_instances.append(entry)

    if limit:
        local_instances = local_instances[:limit]

    total = len(local_instances)
    ok, skip, fail = 0, 0, 0

    for entry in local_instances:
        instance_id = entry["instance_id"]
        db_name = entry.get("db", "")

        task_dir = example_root / instance_id
        task_dir.mkdir(exist_ok=True)

        # 이미 .sqlite 파일이 있으면 스킵
        existing = list(task_dir.glob("*.sqlite")) + list(task_dir.glob("*.db"))
        if existing:
            print(f"[SKIP] {instance_id}: 이미 존재 ({existing[0].name})")
            skip += 1
            continue

        sqlite_file = find_sqlite_file(sqlite_root, db_name)
        if sqlite_file is None:
            print(f"[FAIL] {instance_id}: DB '{db_name}' SQLite 파일 없음")
            fail += 1
            continue

        dest = task_dir / sqlite_file.name
        shutil.copy2(sqlite_file, dest)
        print(f"[OK]   {instance_id}: {sqlite_file.name} 복사 완료")
        ok += 1

    print(f"\n{'─'*50}")
    print(f"완료: {ok}개 성공 / {skip}개 스킵 / {fail}개 실패 (전체 {total}개)")
    print(f"{'─'*50}")

    if fail > 0:
        print(f"\n[주의] {fail}개 DB 파일을 찾지 못했습니다.")
        print("  → Spider2 repo에서 Git LFS 파일이 다운로드되지 않았을 수 있습니다.")
        print("  → git lfs pull 명령어로 LFS 파일을 받은 뒤 다시 실행하세요.")

    print(f"\n[다음 단계]")
    print(f"  1. 스키마 프롬프트 생성:")
    print(f"     python reconstruct_data.py --example_folder {example_folder} --add_description --add_sample_rows")
    print(f"  2. ReFoRCE 실행:")
    print(f"     python run.py --task lite --db_path {example_folder} --output_path output/test-run --model_vote --num_votes 3")
    print(f"  3. 평가:")
    print(f"     python get_metadata.py --result_path output/test-run --output_path output/test-result")
    print(f"     cd {spider2_path}/evaluation_suite")
    print(f"     python evaluate.py --result_dir <절대경로>/output/test-result --mode exec_result")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spider2-lite → ReFoRCE examples/ 셋업")
    parser.add_argument(
        "--spider2_path", type=str, required=True,
        help="Spider2 저장소의 spider2-lite 폴더 경로 (예: /path/to/Spider2/spider2-lite)"
    )
    parser.add_argument(
        "--example_folder", type=str, default="examples",
        help="ReFoRCE examples 폴더 경로 (기본값: examples)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="테스트용: 처음 N개 태스크만 처리 (예: --limit 10)"
    )
    args = parser.parse_args()
    setup(args.spider2_path, args.example_folder, args.limit)
