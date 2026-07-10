"""
Core configuration module using Pydantic settings for environment-based configuration.
Supports Requirements 11.1, 11.2 for configurable settings.
"""

from typing import Optional, List, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from functools import lru_cache
import os
from dotenv import load_dotenv

# Load .env file explicitly
load_dotenv()


class DatabaseSettings(BaseSettings):
    """Database configuration settings"""
    
    host: str = Field(default="localhost", validation_alias="DB_HOST")
    port: int = Field(default=5432, validation_alias="DB_PORT")
    name: str = Field(default="llm_gateway", validation_alias="DB_NAME")
    user: str = Field(default="postgres", validation_alias="DB_USER")
    password: str = Field(default="", validation_alias="DB_PASSWORD")
    pool_size: int = Field(default=20, validation_alias="DB_POOL_SIZE")
    max_overflow: int = Field(default=30, validation_alias="DB_MAX_OVERFLOW")
    pool_timeout: int = Field(default=30, validation_alias="DB_POOL_TIMEOUT")
    
    @property
    def url(self) -> str:
        """Generate database URL"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis configuration settings"""
    
    host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")
    password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")
    db: int = Field(default=0, validation_alias="REDIS_DB")
    pool_size: int = Field(default=20, validation_alias="REDIS_POOL_SIZE")
    socket_timeout: int = Field(default=5, validation_alias="REDIS_SOCKET_TIMEOUT")
    socket_connect_timeout: int = Field(default=5, validation_alias="REDIS_SOCKET_CONNECT_TIMEOUT")
    
    @property
    def url(self) -> str:
        """Generate Redis URL"""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class LoggingSettings(BaseSettings):
    """Logging configuration settings"""
    
    level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    format: str = Field(default="json", validation_alias="LOG_FORMAT")  # json or text
    enable_request_logging: bool = Field(default=True, validation_alias="ENABLE_REQUEST_LOGGING")
    log_pii_redaction: bool = Field(default=True, validation_alias="LOG_PII_REDACTION")
    s3_log_bucket: Optional[str] = Field(default=None, validation_alias="S3_LOG_BUCKET")
    
    @field_validator("level")
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()


class ProviderSettings(BaseSettings):
    """Provider configuration settings"""
    
    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    google_api_key: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY")
    aws_access_key_id: Optional[str] = Field(default=None, validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, validation_alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_REGION")
    
    # Timeouts
    timeout: float = Field(default=60.0, validation_alias="PROVIDER_TIMEOUT_SECONDS")
    
    # Default models
    default_model: str = Field(default="gpt-4o", validation_alias="DEFAULT_MODEL")
    fallback_models: List[str] = Field(
        default=["gpt-4o-mini", "claude-3-5-sonnet-20241022"],
        validation_alias="FALLBACK_MODELS"
    )
    
    @field_validator("fallback_models", mode="before")
    @classmethod
    def parse_fallback_models(cls, v):
        if isinstance(v, str):
            return [model.strip() for model in v.split(",")]
        return v


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration settings"""
    
    default_requests_per_minute: int = Field(default=60, validation_alias="DEFAULT_REQUESTS_PER_MINUTE")
    global_requests_per_second: int = Field(default=1000, validation_alias="GLOBAL_REQUESTS_PER_SECOND")
    burst_allowance: int = Field(default=10, validation_alias="BURST_ALLOWANCE")


class CacheSettings(BaseSettings):
    """Cache configuration settings"""
    
    default_ttl: int = Field(default=86400, validation_alias="CACHE_DEFAULT_TTL")  # 24 hours
    max_entry_size: int = Field(default=1048576, validation_alias="CACHE_MAX_ENTRY_SIZE")  # 1MB
    enable_cache: bool = Field(default=True, validation_alias="ENABLE_CACHE")
    semantic_cache_enabled: bool = Field(default=False, validation_alias="SEMANTIC_CACHE_ENABLED")
    semantic_cache_threshold: float = Field(default=0.95, validation_alias="SEMANTIC_CACHE_THRESHOLD")
    semantic_cache_dimension: int = Field(default=1536, validation_alias="SEMANTIC_CACHE_DIMENSION")


class SecuritySettings(BaseSettings):
    """Security configuration settings"""
    
    api_key_length: int = Field(default=32, validation_alias="API_KEY_LENGTH")
    argon2_time_cost: int = Field(default=2, validation_alias="ARGON2_TIME_COST")
    argon2_memory_cost: int = Field(default=65536, validation_alias="ARGON2_MEMORY_COST")
    argon2_parallelism: int = Field(default=1, validation_alias="ARGON2_PARALLELISM")    # Global security
    cors_origins: List[str] = Field(default=["*"], validation_alias="CORS_ORIGINS")
    admin_api_key: Optional[str] = Field(default=None, validation_alias="ADMIN_API_KEY")
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


class Settings(BaseSettings):
    """Main application settings"""
    
    # Application settings
    app_name: str = Field(default="Universal LLM Gateway", validation_alias="APP_NAME")
    app_version: str = Field(default="1.0.0", validation_alias="APP_VERSION")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    mock_llm: bool = Field(default=False, validation_alias="MOCK_LLM")
    webhook_url: Optional[str] = Field(default=None, validation_alias="WEBHOOK_URL")
    
    # Server settings
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    port: int = Field(default=8000, validation_alias="PORT")
    workers: int = Field(default=1, validation_alias="WORKERS")
    
    # Component settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    providers: ProviderSettings = Field(default_factory=ProviderSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    # Downstream API gateway config
    downstream_url: str = Field(default="http://ftgo-api-gateway:8080", validation_alias="DOWNSTREAM_URL")
    downstream_health_url: str = Field(default="http://ftgo-api-gateway:8080/actuator/health", validation_alias="DOWNSTREAM_HEALTH_URL")

    # JWT Authentication config
    jwt_secret_key: str = Field(validation_alias="JWT_SECRET_KEY")

    # S3 Audit storage config
    s3_bucket_name: Optional[str] = Field(default="ftgo-audit-logs", validation_alias="S3_BUCKET_NAME")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()