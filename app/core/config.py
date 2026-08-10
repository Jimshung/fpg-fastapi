from functools import lru_cache
from typing import Optional

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "FPG FastAPI"

    # 環境設定
    ENVIRONMENT: str = "development"  # 'development', 'production', 'test'

    # Azure OCR（登入驗證碼）
    AZURE_TENANT_ID: Optional[str] = None
    AZURE_CLIENT_ID: Optional[str] = None
    AZURE_CLIENT_SECRET: Optional[str] = None
    AZURE_ENDPOINT: Optional[str] = None
    AZURE_API_KEY: Optional[str] = None

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
logger.info("Settings loaded (HTTP archive mode)")
