"""
쿼리 함수(Tool) 단위 테스트
실행: pytest tests/test_tools.py -v

주의: 실제 DB 연결이 필요합니다. .env 파일을 먼저 설정하세요.
"""
import pytest
from unittest.mock import patch, MagicMock
from src.tools.apc_tools import _to_dt
from datetime import datetime


# ── 헬퍼 함수 테스트 (DB 불필요) ──────────────────────
class TestToDatetime:
    def test_start_of_day(self):
        dt = _to_dt("2026-02-01")
        assert dt == datetime(2026, 2, 1, 0, 0, 0)

    def test_end_of_day(self):
        dt = _to_dt("2026-02-20", end=True)
        assert dt == datetime(2026, 2, 20, 23, 59, 59)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            _to_dt("20260201")


# ── Tool 함수 테스트 (DB Mock) ─────────────────────────
class TestGetBatchCount:
    @patch("src.tools.apc_tools._session")
    def test_returns_count(self, mock_session):
        mock_batch = MagicMock()
        mock_batch.status = "completed"

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            mock_batch, mock_batch
        ]
        mock_session.return_value = mock_ctx

        from src.tools.apc_tools import get_batch_count
        result = get_batch_count.invoke({
            "start_date": "2026-02-01",
            "end_date": "2026-02-20",
        })
        assert "2" in result

    @patch("src.tools.apc_tools._session")
    def test_no_data(self, mock_session):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.query.return_value.filter.return_value.filter.return_value.all.return_value = []
        mock_session.return_value = mock_ctx

        from src.tools.apc_tools import get_batch_count
        result = get_batch_count.invoke({
            "start_date": "2026-02-01",
            "end_date": "2026-02-20",
        })
        assert "없습니다" in result
