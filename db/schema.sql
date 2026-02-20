-- APC POC 데이터베이스 스키마

CREATE TABLE IF NOT EXISTS apc_batch (
    batch_id        VARCHAR(50) PRIMARY KEY,
    product_code    VARCHAR(50),
    line_id         VARCHAR(20),
    start_time      TIMESTAMP NOT NULL,
    end_time        TIMESTAMP,
    status          VARCHAR(20) DEFAULT 'completed',  -- completed | in_progress | failed
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS apc_measurement (
    id              SERIAL PRIMARY KEY,
    batch_id        VARCHAR(50) REFERENCES apc_batch(batch_id),
    param_name      VARCHAR(100),
    param_value     FLOAT,
    unit            VARCHAR(20),
    measured_at     TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_batch_start_time ON apc_batch(start_time);
CREATE INDEX IF NOT EXISTS idx_batch_line_id    ON apc_batch(line_id);
CREATE INDEX IF NOT EXISTS idx_measurement_batch ON apc_measurement(batch_id);
