"""Configuración de la aplicación, leída de variables de entorno o de un archivo .env.

Nunca se loguea ni se expone el contenido de esta clase: contiene secretos.
"""

import re
from typing import Literal

from fastapi import Request
from limits import parse as parse_rate_limit
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.jdbc import jdbc_url_to_dsn

_ORACLE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,29}$")
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Los errores de validación no muestran el valor recibido (puede ser un secreto).
        hide_input_in_errors=True,
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Driver: "jdbc" (ojdbc8 en una JVM embebida, no necesita Instant Client) u
    # "oracledb" (python-oracledb en modo thick; con 11g requiere Instant Client 19).
    db_driver: Literal["jdbc", "oracledb"] = "jdbc"
    jdbc_driver_jar: str = "lib/ojdbc8-19.27.0.0.jar"
    java_home: str | None = None  # vacío = JAVA_HOME del sistema
    db_user: str = ""
    db_password: SecretStr = SecretStr("")
    # Conexión: una URL JDBC (jdbc:oracle:thin:@host:1521:SID) o un DSN de oracledb.
    db_jdbc_url: str = ""
    db_dsn: str = ""
    db_pool_min: int = Field(2, ge=1)
    db_pool_max: int = Field(10, ge=1)
    db_pool_wait_timeout_ms: int = Field(3000, ge=0)
    db_call_timeout_ms: int = Field(5000, ge=100)
    oracle_client_lib_dir: str | None = None
    view_schema: str | None = None

    # Autenticación: usuarios en archivo + tokens JWT firmados con HS256
    users_file: str = "users.json"
    jwt_secret: SecretStr = SecretStr("")
    jwt_expire_minutes: int = Field(30, ge=1, le=1440)

    # Rate limiting, CORS
    rate_limit: str = "60/minute"
    login_rate_limit: str = "10/minute"
    # memory:// sirve con un solo proceso; con varios workers usar redis://host:6379
    rate_limit_storage_uri: str = "memory://"
    cors_origins: str = ""  # lista separada por comas

    @field_validator("view_schema")
    @classmethod
    def _validate_schema(cls, value: str | None) -> str | None:
        if not value:
            return None
        if not _ORACLE_IDENTIFIER.fullmatch(value):
            raise ValueError("VIEW_SCHEMA must be a plain Oracle identifier")
        return value.upper()

    @field_validator("oracle_client_lib_dir", "java_home")
    @classmethod
    def _empty_lib_dir_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if any("*" in origin for origin in origins):
            raise ValueError("CORS_ORIGINS must list explicit origins, never '*'")
        return ",".join(origins)

    @field_validator("rate_limit", "login_rate_limit")
    @classmethod
    def _validate_rate_limit(cls, value: str) -> str:
        parse_rate_limit(value)  # lanza ValueError si el formato es inválido
        return value

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET is required and must have at least {MIN_JWT_SECRET_LENGTH} characters"
            )
        return value

    @field_validator("db_jdbc_url")
    @classmethod
    def _validate_jdbc_url(cls, value: str) -> str:
        if value.strip():
            jdbc_url_to_dsn(value)  # lanza JdbcUrlError (ValueError) si es inválida
        return value.strip()

    @model_validator(mode="after")
    def _validate_pool(self) -> "Settings":
        if self.db_pool_min > self.db_pool_max:
            raise ValueError("DB_POOL_MIN must be <= DB_POOL_MAX")
        if self.db_jdbc_url and self.db_dsn:
            raise ValueError("set only one of DB_JDBC_URL or DB_DSN")
        if self.db_driver == "jdbc" and self.db_dsn:
            raise ValueError("DB_DRIVER=jdbc requires DB_JDBC_URL (DB_DSN is for oracledb)")
        return self

    @property
    def dsn(self) -> str:
        """DSN efectivo para python-oracledb."""
        return jdbc_url_to_dsn(self.db_jdbc_url) if self.db_jdbc_url else self.db_dsn

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin for origin in self.cors_origins.split(",") if origin]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
