from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    PROVIDER_LLM: Literal["openai", "ollama", "aws_bedrock", "google_gemini"] = "openai"
    LLM_MODEL: str | None = None
    OPENAI_API_KEY: SecretStr | None = None
    GEMINI_API_KEY: SecretStr | None = None
    AWS_REGION: str = "us-east-1"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY: SecretStr | None = None
    GITHUB_APP_PRIVATE_KEY_PATH: Path | None = None
    GITHUB_TIMEOUT: float = Field(default=20, gt=0)
    LLM_TIMEOUT: float = Field(default=90, gt=0)
    MAX_ATTEMPTS: int = Field(default=3, ge=1, le=5)
    RETRY_DELAY: float = Field(default=1, ge=0)
    MAX_FILES: int = Field(default=100, ge=1)
    MAX_FILE_BYTES: int = Field(default=65536, ge=1)
    MAX_TOTAL_BYTES: int = Field(default=2097152, ge=1)
    MAX_TREE_ENTRIES: int = Field(default=20000, ge=1)
    MAX_TREE_REQUESTS: int = Field(default=200, ge=1)
    INPUT_TOKEN_BUDGET: int = Field(default=16000, ge=1024)
    OUTPUT_TOKEN_BUDGET: int = Field(default=4096, ge=256)
    MODEL_CONTEXT_TOKENS: int = Field(default=32768, ge=2048)
    ASSESSMENT_OUTPUT_DIR: Path = Path("outputs/assessments")
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: SecretStr | None = None
    LANGFUSE_HOST: str = "http://localhost:3000"

    @model_validator(mode="after")
    def validate_budget(self):
        if self.INPUT_TOKEN_BUDGET + self.OUTPUT_TOKEN_BUDGET > self.MODEL_CONTEXT_TOKENS:
            raise ValueError("Input and output budgets exceed model context")
        return self

    @property
    def model_name(self) -> str:
        if self.LLM_MODEL:
            return self.LLM_MODEL
        if self.PROVIDER_LLM == "openai":
            return "gpt-4.1-mini"
        raise ValueError("LLM_MODEL is required for the selected provider")
