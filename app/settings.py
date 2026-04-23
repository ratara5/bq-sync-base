# ========================================
# app-gci/settings.py
# Variables de entorno → objeto tipado
# ========================================
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

from dotenv import load_dotenv

load_dotenv() # no sobrescribe las variables de entorno si ya existen en el sistema.


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    port: int = os.getenv("APP_PORT")
    flask_debug: bool = os.getenv("FLASK_DEBUG")
    flask_use_reloader: bool = os.getenv("FLASK_USE_RELOADER")

    # Postgres
    pg_host: str = os.getenv("DB_HOST")
    pg_port: int = os.getenv("DB_PORT")
    pg_db: str = os.getenv("DB_NAME")
    pg_user: str = os.getenv("DB_USER")
    pg_password: str = os.getenv("DB_PASSWORD")    

    # BigQuery
    bq_project: str = os.getenv("BQ_PROJECT")
    bq_dataset: str = os.getenv("BQ_DATASET")
    google_application_credentials: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    @property
    def pg_dsn(self) -> str:
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@localhost:{self.pg_port}/{self.pg_db}" #nombre del contenedor docker o localhost si se expone el puerto
        )


settings = Settings()