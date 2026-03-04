# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

Text-to-SQL system with two implementations:
1. **APC POC** - PostgreSQL-based natural language query system for APC (Advanced Process Control) data
2. **Spider2** - General-purpose SQLite Text-to-SQL system using LangGraph for Spider 2.0-Lite benchmark evaluation

Core Design Philosophy (DBGorilla paper approach):
- LLM generates structured query specifications (QuerySpec JSON), not raw SQL
- Application-side Query Builder mechanically converts QuerySpec → SQL
- Separation enables extensibility: add filter types in schema, update builder logic only

---

## Common Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Setup environment (copy .env.example to .env and configure)
cp .env.example .env

# Seed sample data for APC POC
python db/seed_data.py
```

### Running Applications
```bash
# APC CLI (interactive or single query)
python main.py                          # Interactive loop
python main.py "2월 배치 수 알려줘"    # Single query

# Spider2 evaluation
python -m spider2.evaluator \
    --data_dir ./Spider2/spider2-lite \
    --db_dir ./Spider2/spider2-lite/resource/databases/sqlite \
    --gold_dir ./Spider2/spider2-lite/evaluation_suite/gold/sql \
    --limit 20
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_builder.py -v
```

---

## Architecture

### APC POC Architecture
```
Natural Language Question
    ↓
LLM (with_structured_output → QuerySpec)
    ↓
QueryBuilder (QuerySpec → SQLAlchemy query)
    ↓
PostgreSQL execution
    ↓
LLM response generation
```

**Key Components:**
- `src/query/schema.py` - QuerySpec Pydantic models (APC-specific: date_range_filter, fixed filter types)
- `src/query/builder.py` - QueryBuilder executes QuerySpec via SQLAlchemy
- `src/agent.py` - LangChain agent with `with_structured_output` pattern
- `db/registry.py` - Static collection registry (table/column metadata) for APC LLM context
- `src/models.py` - SQLAlchemy ORM models (ApcBatch, ApcMeasurement)

### Spider2 Architecture (LangGraph-based)
```
[load_schema] → [generate_spec] → [execute_query]
                        ↑                    ↓
                        └── retry (error) ──┤
                                                    ↓ success
                                               [finalize]
```

**Key Components:**
- `spider2/schema.py` - Spider2QuerySpec (generalized: arbitrary tables, JOINs, multiple WHERE conditions)
- `spider2/builder.py` - Spider2Builder converts to SQLite SQL string
- `spider2/graph.py` - LangGraph state machine with self-correction loop
- `spider2/schema_loader.py` - Dynamic schema loader from SQLite DB files
- `spider2/evaluator.py` - Spider 2.0-Lite benchmark evaluation

### Schema Loading Differences
- **APC**: Static `db/registry.py` with hardcoded collection metadata
- **Spider2**: Dynamic `spider2/schema_loader.load_sqlite_schema()` reads SQLite PRAGMA at runtime

---

## Data Models

### APC Tables (PostgreSQL)
- `apc_batch` - Batch records (batch_id, product_code, line_id, start_time, end_time, status)
- `apc_measurement` - Process parameter measurements (batch_id FK, param_name, param_value, unit, measured_at)

### Spider2 (SQLite)
- Arbitrary schema loaded dynamically from Spider 2.0-Lite DB files
- Supports flat or nested directory structures (see `find_sqlite_db()`)

---

## Extension Points

### Adding New Filter Types (APC)
1. Add new filter class in `src/query/schema.py`
2. Add field to `QuerySpec` with Optional default=None
3. Add `_apply_new_filter()` method in `src/query/builder.py`
4. Call new method in `QueryBuilder.execute()` or `_execute_aggregation()`
5. Update `db/registry.py` if new columns added to collections

### Adding New Data Sources (APC)
1. Add collection metadata to `COLLECTION_REGISTRY` in `db/registry.py`
2. Add SQLAlchemy model in `src/models.py`
3. Add to `_MODEL_MAP` in `src/query/builder.py`

### Spider2 Extensions
- Modify `Spider2QuerySpec` schema for new operators/features
- Update `Spider2Builder.build()` methods for new clause types
- No agent changes needed (LLM uses structured_output pattern)

---

## Configuration

Environment variables (`.env`):
```bash
# PostgreSQL (APC)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=apc_db
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# LLM (OpenAI-compatible internal API)
LLM_BASE_URL=http://your-internal-api/v1
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-4o-mini

# Spider2 self-correction retry limit
SPIDER2_MAX_RETRY=3
```

---

## File Organization

```
T2S/
├── db/
│   ├── registry.py          # Static APC collection metadata
│   ├── schema.sql          # APC table definitions
│   └── seed_data.py       # Sample data generator
├── src/
│   ├── config.py           # DB/LLM configuration
│   ├── models.py          # SQLAlchemy ORM models
│   ├── query/
│   │   ├── schema.py      # QuerySpec models (APC)
│   │   └── builder.py     # QuerySpec → SQLAlchemy
│   └── agent.py           # APC LangChain agent
├── spider2/
│   ├── schema.py          # Spider2QuerySpec (generalized)
│   ├── builder.py         # QuerySpec → SQLite SQL
│   ├── schema_loader.py   # Dynamic SQLite schema loader
│   ├── graph.py          # LangGraph state machine
│   └── evaluator.py      # Spider 2.0-Lite benchmark runner
├── tests/
│   └── test_builder.py    # QuerySpec validation tests
├── main.py               # APC CLI entry point
├── requirements.txt
├── PRD.md               # Product requirements (Korean)
└── README.md
```
