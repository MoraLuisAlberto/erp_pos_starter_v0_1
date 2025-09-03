from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = Field(default="ERP POS", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    database_url: str = Field(default="sqlite:///./app.db", alias="DATABASE_URL")
    store_id: int = Field(default=1, alias="STORE_ID")
    store_name: str = Field(default="Tienda Principal", alias="STORE_NAME")
    currency: str = Field(default="MXN", alias="CURRENCY")
    cash_close_tolerance: float = Field(default=15.0, alias="CASH_CLOSE_TOLERANCE")
    cash_rounding_step: float = Field(default=0.5, alias="CASH_ROUNDING_STEP")
    cart_max: int = Field(default=5, alias="CART_MAX")
    undo_seconds: int = Field(default=5, alias="UNDO_SECONDS")
    offline_max_ops: int = Field(default=500, alias="OFFLINE_MAX_OPS")
    offline_max_hours: int = Field(default=48, alias="OFFLINE_MAX_HOURS")
    offline_soft_ops: int = Field(default=400, alias="OFFLINE_SOFT_OPS")
    offline_soft_hours: int = Field(default=36, alias="OFFLINE_SOFT_HOURS")

    class Config:
        env_file = ".env"


settings = Settings()
