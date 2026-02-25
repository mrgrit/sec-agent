from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    APP_SECRET_KEY: str
    STORAGE_DIR: str = "/data"
    DEFAULT_LLM_TIMEOUT_S: int = 300

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
