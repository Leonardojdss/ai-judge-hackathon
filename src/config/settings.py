from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    ASSESSMENT_OUTPUT_DIR: Path = Path("outputs/assessments")
    CRITERION_MAX_ATTEMPTS: int = Field(default=3, ge=1)
    CRITERION_RETRY_DELAY: float = Field(default=1.0, ge=0)
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: SecretStr | None = None
    LANGFUSE_HOST: str = "http://localhost:3000"

    @property
    def model_name(self) -> str:
        model = (self.LLM_MODEL or "").strip()
        if not model:
            raise ValueError("LLM_MODEL is required for the selected provider")
        return model

    def validate_llm_configuration(self) -> None:
        """Validate the provider/model pair and its required local credential."""
        self.model_name
        if self.PROVIDER_LLM == "openai":
            secret = self.OPENAI_API_KEY
            variable = "OPENAI_API_KEY"
        elif self.PROVIDER_LLM == "google_gemini":
            secret = self.GEMINI_API_KEY
            variable = "GEMINI_API_KEY"
        else:
            return
        if secret is None or not secret.get_secret_value().strip():
            raise ValueError(f"{variable} is required for {self.PROVIDER_LLM}")
