from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # FPG 登入
    FPG_USERNAME: str
    FPG_PASSWORD: str
    LOGIN_URL: str

    # Telegram 設定
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    ENABLE_TELEGRAM_NOTIFY: bool = True

    # Notion（標售案件歸檔）
    NOTION_TOKEN: Optional[str] = None
    NOTION_DATABASE_ID: Optional[str] = None
    # 政府財物變賣（獨立 database，勿與 FPG 混用）
    PCC_NOTION_DATABASE_ID: Optional[str] = None
    # PCC 轉發代理（見 gas/pcc_proxy.gs）；留空則直連。實際值只放 .env 或 GitHub Secrets
    PCC_PROXY_URL: str = ""
    PCC_PROXY_KEY: str = ""
    NOTION_VERSION: str = "2022-06-28"
    NOTION_FILE_UPLOAD_VERSION: str = "2026-03-11"


@lru_cache()
def get_settings():
    """獲取設定實例"""
    try:
        return Settings()
    except Exception as e:
        print(f"Error loading settings: {str(e)}")
        raise


settings = get_settings()
