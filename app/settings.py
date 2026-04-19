# ========================================
# app-gci/settings.py
# Variables de entorno → objeto tipado
# ========================================
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    port: int = os.getenv("APP_PORT", 8080)
    flask_env: str = int(os.getenv("FLASK_ENV", "production")) # "production"

    # Postgres
    pg_host: str = os.getenv("DB_HOST", "postgres-gci")
    pg_port: int = os.getenv("DB_PORT", 5432)
    pg_db: str = os.getenv("DB_NAME")
    pg_user: str = os.getenv("DB_USER")
    pg_password: str = os.getenv("DB_PASSWORD")    

    # BigQuery
    bq_project: str = os.getenv("BQ_PROJECT")
    bq_dataset: str = os.getenv("BQ_DATASET")
    google_application_credentials: str = "/app/credentials/credentials.json"

    @property
    def pg_dsn(self) -> str:
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )


settings = Settings()