import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from pydantic import validator
from typing import Optional
from loguru import logger

class Settings(BaseSettings):
    APP_NAME: str = "FPG FastAPI"
    
    # 環境設定
    ENVIRONMENT: str = "development"  # 'development', 'production', 'test'
    DEBUG: bool = False
    
    # 資料庫設定
    DATABASE_URL: Optional[str] = None
    
    # Azure 設定
    AZURE_TENANT_ID: Optional[str] = None
    AZURE_CLIENT_ID: Optional[str] = None
    AZURE_CLIENT_SECRET: Optional[str] = None
    AZURE_ENDPOINT: Optional[str] = None
    AZURE_API_KEY: Optional[str] = None
    
    # FPG 登入設定
    USERNAME: str
    PASSWORD: str
    BASE_URL: str = "https://www.e-fpg.com.tw/"
    LOGIN_URL: str = "https://fpg.com.tw"
    
    # 瀏覽器設定
    HEADLESS_MODE: bool = False
    BROWSER_WINDOW_SIZE: str = "1920,1080"
    IMPLICIT_WAIT: int = 10
    CHROME_DRIVER_PATH: Optional[str] = None
    
    # Telegram 設定
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    ENABLE_TELEGRAM_NOTIFY: bool = True

    @validator('HEADLESS_MODE', pre=True)
    def validate_headless_mode(cls, v, values):
        """根據環境設定決定是否使用 headless 模式"""
        # 如果明確設置了環境變數，優先使用環境變數的值
        env_headless = os.getenv('HEADLESS_MODE')
        if env_headless is not None:
            logger.debug(f"從環境變數讀取 HEADLESS_MODE: {env_headless}")
            return str(env_headless).lower() == 'true'
            
        # 如果是 GitHub Actions 環境，強制使用 headless 模式
        if os.getenv('GITHUB_ACTIONS'):
            logger.debug("檢測到 GitHub Actions 環境，使用 headless 模式")
            return True
            
        # 如果是 production 環境，使用 headless 模式
        if values.get('ENVIRONMENT') == 'production':
            logger.debug("檢測到 production 環境，使用 headless 模式")
            return True
            
        # 其他情況使用配置文件中的設定
        logger.debug(f"使用默認設定: {v}")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True  # 確保環境變數名稱大小寫敏感

def get_settings():
    """獲取設定實例"""
    return Settings()

settings = get_settings()
logger.info(f"HEADLESS_MODE 設定為: {settings.HEADLESS_MODE}")