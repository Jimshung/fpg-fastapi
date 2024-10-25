from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "FPG Automation"
    DEBUG: bool = True

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

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
