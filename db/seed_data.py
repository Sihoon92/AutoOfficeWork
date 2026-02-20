"""
APC 샘플 데이터 적재 스크립트
실행: python db/seed_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import random
from datetime import datetime, timedelta
from sqlalchemy import text
from src.config import get_engine

LINES = ["A", "B", "C"]
PRODUCTS = ["PROD-001", "PROD-002", "PROD-003"]
PARAMS = [
    ("temperature", "°C", 200, 250),
    ("pressure",    "bar",  1.0, 5.0),
    ("flow_rate",   "L/min", 10, 50),
]


def seed(days: int = 90):
    engine = get_engine()
    with engine.begin() as conn:
        # 스키마 적용
        with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
            conn.execute(text(f.read()))

        base = datetime.now() - timedelta(days=days)
        batch_num = 1

        for day_offset in range(days):
            day = base + timedelta(days=day_offset)
            daily_count = random.randint(3, 8)

            for _ in range(daily_count):
                batch_id = f"BATCH-{day.strftime('%Y%m%d')}-{batch_num:03d}"
                start_time = day + timedelta(hours=random.randint(0, 22))
                end_time = start_time + timedelta(hours=random.uniform(0.5, 4))
                status = random.choices(
                    ["completed", "failed"], weights=[90, 10]
                )[0]

                conn.execute(text("""
                    INSERT INTO apc_batch
                        (batch_id, product_code, line_id, start_time, end_time, status)
                    VALUES
                        (:batch_id, :product_code, :line_id, :start_time, :end_time, :status)
                    ON CONFLICT DO NOTHING
                """), {
                    "batch_id": batch_id,
                    "product_code": random.choice(PRODUCTS),
                    "line_id": random.choice(LINES),
                    "start_time": start_time,
                    "end_time": end_time,
                    "status": status,
                })

                # 측정값 3~5개
                for param_name, unit, lo, hi in PARAMS:
                    conn.execute(text("""
                        INSERT INTO apc_measurement
                            (batch_id, param_name, param_value, unit, measured_at)
                        VALUES
                            (:batch_id, :param_name, :param_value, :unit, :measured_at)
                    """), {
                        "batch_id": batch_id,
                        "param_name": param_name,
                        "param_value": round(random.uniform(lo, hi), 2),
                        "unit": unit,
                        "measured_at": start_time + timedelta(minutes=random.randint(5, 30)),
                    })

                batch_num += 1

    print(f"샘플 데이터 적재 완료: {batch_num - 1}개 배치")


if __name__ == "__main__":
    seed()
