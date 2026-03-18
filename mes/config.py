"""MES WAS 연결 설정 및 세션 컨텍스트(F_ 파라미터).

WAS 호출 시 고정되는 F_ prefix 파라미터와 WAS URL 등을 관리한다.
실제 값은 .env에서 로드한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass
class WASConfig:
    """WAS 연결 설정 + 세션 컨텍스트 파라미터."""

    # WAS 엔드포인트
    was_url: str = field(
        default_factory=lambda: os.getenv("WAS_URL", "http://localhost:8080/api/query")
    )

    # 세션/컨텍스트 파라미터 (F_ prefix) — 사용자/공장/앱별 고정값
    f_fct_id: str = field(default_factory=lambda: os.getenv("WAS_F_FCT_ID", ""))
    f_site_id: str = field(default_factory=lambda: os.getenv("WAS_F_SITE_ID", ""))
    f_app_id: str = field(default_factory=lambda: os.getenv("WAS_F_APP_ID", ""))
    f_menu_id: str = field(default_factory=lambda: os.getenv("WAS_F_MENU_ID", ""))
    f_line_id: str = field(default_factory=lambda: os.getenv("WAS_F_LINE_ID", ""))
    f_shop_id: str = field(default_factory=lambda: os.getenv("WAS_F_SHOP_ID", ""))
    f_bld_id: str = field(default_factory=lambda: os.getenv("WAS_F_BLD_ID", ""))
    f_biz_id: str = field(default_factory=lambda: os.getenv("WAS_F_BIZ_ID", ""))
    f_work_id: str = field(default_factory=lambda: os.getenv("WAS_F_WORK_ID", ""))
    f_version: str = field(default_factory=lambda: os.getenv("WAS_F_VERSION", ""))
    f_line_rprs_group_id: str = field(
        default_factory=lambda: os.getenv("WAS_F_LINE_RPRS_GROUP_ID", "")
    )
    f_data_auth: str = field(
        default_factory=lambda: os.getenv("WAS_F_DATA_AUTH", "")
    )
    lang_cd: str = field(default_factory=lambda: os.getenv("WAS_LANG_CD", "KOR"))
    crud: str = field(default_factory=lambda: os.getenv("WAS_CRUD", "R"))

    def get_context_params(self) -> Dict[str, str]:
        """WAS 요청에 포함할 고정 컨텍스트 파라미터 dict를 반환한다."""
        return {
            "F_FCT_ID": self.f_fct_id,
            "F_SITE_ID": self.f_site_id,
            "F_APP_ID": self.f_app_id,
            "F_MENU_ID": self.f_menu_id,
            "F_LINE_ID": self.f_line_id,
            "F_SHOP_ID": self.f_shop_id,
            "F_BLD_ID": self.f_bld_id,
            "F_BIZ_ID": self.f_biz_id,
            "F_WORK_ID": self.f_work_id,
            "F_VERSION": self.f_version,
            "F_LINE_RPRS_GROUP_ID": self.f_line_rprs_group_id,
            "F_DATA_AUTH": self.f_data_auth,
            "LANG_CD": self.lang_cd,
            "CRUD": self.crud,
        }
