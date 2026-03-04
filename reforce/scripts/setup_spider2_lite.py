#!/usr/bin/env python3
"""
setup_spider2_lite.py
─────────────────────
spider_git/spider2-lite 데이터셋을 ReFoRCE가 읽을 수 있는 examples/ 구조로 변환합니다.

Spider2-lite 구조:
    spider2-lite/
    ├── spider2-lite.jsonl
    └── resource/databases/
        ├── sqlite/{DB_NAME}/          ← JSON 스키마 메타데이터 (prompts.txt 생성용)
        │   ├── DDL.csv
        │   ├── all_star.json
        │   └── ...
        └── spider2-localdb/           ← 실제 .sqlite 파일 (별도 다운로드 필요)
            ├── baseball.sqlite
            └── ...

ReFoRCE examples/ 목표 구조:
    examples/
    ├── spider2-lite.jsonl
    └── local003/
        ├── baseball.sqlite            ← SQL 실행용 (spider2-localdb에서 복사)
        ├── Baseball/                  ← prompts.txt 생성용 JSON + DDL
        │   ├── DDL.csv
        │   ├── all_star.json
        │   └── ...
        └── prompts.txt                ← reconstruct_data.py가 생성

사전 조건:
    - spider2-localdb의 .sqlite 파일은 Spider2 README에 안내된
      Google Drive 링크에서 별도 다운로드 필요
    - 다운로드 후 spider2-lite/resource/databases/spider2-localdb/ 에 배치

사용법:
    python scripts/setup_spider2_lite.py \\
        --spider2_path /path/to/spider_git/spider2-lite \\
        --example_folder examples \\
        [--limit 10]
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path


def find_sqlite_file(localdb_root: Path, db_name: str) -> Path | None:
    """spider2-localdb/ 에서 db_name에 해당하는 .sqlite 파일 탐색."""
    if not localdb_root.exists():
        return None

    db_name_lower = db_name.lower()

    # 정확한 이름 매칭: {db_name}.sqlite
    for candidate in localdb_root.iterdir():
        if candidate.suffix in (".sqlite", ".db"):
            stem_lower = candidate.stem.lower()
            # 정확 일치
            if stem_lower == db_name_lower:
                return candidate
            # 언더스코어/하이픈/대소문자 무시 비교
            if stem_lower.replace("_", "").replace("-", "") == db_name_lower.replace("_", "").replace("-", ""):
                return candidate

    # 부분 매칭 (포함 관계)
    for candidate in localdb_root.iterdir():
        if candidate.suffix in (".sqlite", ".db"):
            if db_name_lower in candidate.stem.lower() or candidate.stem.lower() in db_name_lower:
                return candidate

    return None


def copy_json_schema_files(schema_src: Path, task_dir: Path, db_name: str) -> bool:
    """resource/databases/sqlite/{db_name}/ 의 JSON+DDL 파일을 task_dir/{db_name}/ 에 복사."""
    if not schema_src.exists():
        return False

    dest_db_dir = task_dir / db_name
    dest_db_dir.mkdir(exist_ok=True)

    count = 0
    for f in schema_src.iterdir():
        if f.suffix in (".json", ".csv"):
            shutil.copy2(f, dest_db_dir / f.name)
            count += 1

    return count > 0


def setup(spider2_path: str, example_folder: str, limit: int | None):
    spider2_root = Path(spider2_path).resolve()
    sqlite_schema_root = spider2_root / "resource" / "databases" / "sqlite"
    localdb_root = spider2_root / "resource" / "databases" / "spider2-localdb"
    jsonl_src = spider2_root / "spider2-lite.jsonl"

    # ── 사전 조건 확인 ─────────────────────────────────────────────────────
    if not jsonl_src.exists():
        print(f"[ERROR] spider2-lite.jsonl 파일을 찾을 수 없습니다: {jsonl_src}")
        sys.exit(1)

    if not sqlite_schema_root.exists():
        print(f"[ERROR] JSON 스키마 폴더를 찾을 수 없습니다: {sqlite_schema_root}")
        sys.exit(1)

    has_localdb = localdb_root.exists() and any(
        f.suffix in (".sqlite", ".db") for f in localdb_root.iterdir()
    ) if localdb_root.exists() else False

    if not has_localdb:
        print("=" * 60)
        print("[주의] spider2-localdb 폴더에 .sqlite 파일이 없습니다.")
        print()
        print("  실제 SQL 실행을 위한 SQLite DB 파일을 별도로 다운로드해야 합니다.")
        print("  Spider2 README의 'local database' Google Drive 링크에서 다운로드 후")
        print(f"  {localdb_root} 에 압축 해제하세요.")
        print()
        print("  .sqlite 없이도 JSON 스키마만으로 prompts.txt 생성은 가능합니다.")
        print("  단, SQL 실행(run.py)은 .sqlite 파일이 있어야 동작합니다.")
        print("=" * 60)

    example_root = Path(example_folder).resolve()
    example_root.mkdir(parents=True, exist_ok=True)

    # ── 1. spider2-lite.jsonl 복사 ──────────────────────────────────────────
    dest_jsonl = example_root / "spider2-lite.jsonl"
    shutil.copy2(jsonl_src, dest_jsonl)
    print(f"[OK] JSONL 복사: {dest_jsonl}")

    # ── 2. 태스크별 파일 복사 ────────────────────────────────────────────────
    local_instances = []
    with open(jsonl_src, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry["instance_id"].startswith("local"):
                local_instances.append(entry)

    if limit:
        local_instances = local_instances[:limit]

    total = len(local_instances)
    ok_sqlite, ok_json_only, skip, fail = 0, 0, 0, 0

    for entry in local_instances:
        instance_id = entry["instance_id"]
        db_name = entry.get("db", "")

        task_dir = example_root / instance_id
        task_dir.mkdir(exist_ok=True)

        # 이미 .sqlite 파일이 있으면 스킵
        existing_sqlite = list(task_dir.glob("*.sqlite")) + list(task_dir.glob("*.db"))
        if existing_sqlite and (task_dir / db_name).exists():
            print(f"[SKIP] {instance_id}: 이미 존재")
            skip += 1
            continue

        # ── (A) 실제 .sqlite 파일 복사 ──────────────────────────────────
        sqlite_copied = False
        if has_localdb and not existing_sqlite:
            sqlite_file = find_sqlite_file(localdb_root, db_name)
            if sqlite_file:
                dest = task_dir / sqlite_file.name
                shutil.copy2(sqlite_file, dest)
                sqlite_copied = True

        # ── (B) JSON 스키마 파일 복사 (prompts.txt 생성 + DDL schema linking용) ──
        schema_src = sqlite_schema_root / db_name
        json_copied = copy_json_schema_files(schema_src, task_dir, db_name)

        # ── 결과 보고 ────────────────────────────────────────────────────
        if sqlite_copied and json_copied:
            print(f"[OK]   {instance_id} (db={db_name}): sqlite + JSON 복사 완료")
            ok_sqlite += 1
        elif json_copied:
            print(f"[JSON] {instance_id} (db={db_name}): JSON만 복사 (sqlite 없음, prompts.txt만 생성 가능)")
            ok_json_only += 1
        else:
            print(f"[FAIL] {instance_id} (db={db_name}): 파일 없음")
            fail += 1

    # ── 요약 ─────────────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"완료: {ok_sqlite}개 완전 셋업 / {ok_json_only}개 JSON만 / {skip}개 스킵 / {fail}개 실패 (전체 {total}개)")
    print(f"{'─' * 60}")

    print(f"\n[다음 단계]")
    print(f"  1. 스키마 프롬프트 생성:")
    print(f"     cd /path/to/reforce")
    print(f"     python reconstruct_data.py --example_folder {example_folder} --add_description --add_sample_rows")
    print(f"  2. ReFoRCE 실행 (.sqlite 파일 필요):")
    print(f"     python run.py --task lite --db_path {example_folder} --output_path output/test-run --model_vote --num_votes 3")
    print(f"  3. 결과 수집:")
    print(f"     python get_metadata.py --result_path output/test-run --output_path output/test-final")
    print(f"  4. Spider2 공식 평가:")
    print(f"     cd {spider2_path}/evaluation_suite")
    print(f"     python evaluate.py --result_dir <reforce경로>/output/test-final --mode exec_result")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spider2-lite → ReFoRCE examples/ 셋업")
    parser.add_argument(
        "--spider2_path", type=str, required=True,
        help="spider_git/spider2-lite 폴더 경로 (예: /path/to/spider_git/spider2-lite)"
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
