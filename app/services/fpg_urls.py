"""FPG 站台 URL：網域只來自 LOGIN_URL（.env），程式碼只留相對路徑。"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit, urljoin

from app.core.config import settings

# 相對路徑（不含網域）
LOGIN_PATH = "/j202/mgt/mgt_logon.jsp"
LOGIN_SERVLET_PATH = "/j202/servlet/com.fpg.j202.Cj202000"
CAPTCHA_PATH = "/j202/Captcha.do"
BULLETIN_PAGE_PATH = "/j202/prc/prc_anno_comp_srh.jsp"
BULLETIN_POST_PATH = "/j202/servlet/com.fpg.j202.Cj202c12"
BID_PAGE_PATH = "/j202/prc/prc_bid_gen_srh.jsp"
BID_POST_PATH = "/j202/servlet/com.fpg.j202.Cj202c13"
CMP_BID_PAGE_PATH = "/j202/cmp/prc_bid_gen_srh.jsp"
CMP_BID_POST_PATH = "/j202/servlet/com.fpg.j202.Cj202c14"


@lru_cache
def fpg_base_url() -> str:
    """從 LOGIN_URL 取出 scheme://host。"""
    parts = urlsplit((settings.LOGIN_URL or "").strip())
    if not parts.scheme or not parts.netloc:
        raise RuntimeError("LOGIN_URL 無效，請在 .env 設定完整 URL（含 https://）")
    return f"{parts.scheme}://{parts.netloc}"


def fpg_url(path: str) -> str:
    return urljoin(fpg_base_url() + "/", (path or "").lstrip("/"))
