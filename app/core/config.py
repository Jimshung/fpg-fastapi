import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from pydantic import validator

class Settings(BaseSettings):
    APP_NAME: str = "FPG Automation"
    DEBUG: bool = True
    
    # 環境設定
    ENVIRONMENT: str = "development"
    
    # 瀏覽器設定
    CHROME_DRIVER_PATH: str
    HEADLESS_MODE: bool = False
    
    # 網站設定
    BASE_URL: str
    LOGIN_URL: str
    
    # 帳號設定
    USERNAME: str
    PASSWORD: str
    
    # Azure 設定
    AZURE_ENDPOINT: str
    AZURE_API_KEY: str

    @validator('HEADLESS_MODE', pre=True)
    def set_headless_mode(cls, v, values):
        """根據環境設定決定是否使用 headless 模式"""
        # 如果是 production 環境或是 CI 環境，強制使用 headless 模式
        if values.get('ENVIRONMENT') == 'production' or os.getenv('GITHUB_ACTIONS'):
            return True
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True  # 確保環境變數名稱大小寫敏感

@lru_cache()
def get_settings():
    """獲取設定實例（使用 lru_cache 做快取）"""
    return Settings()

settings = get_settings()