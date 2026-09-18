from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_url: str = "https://example.invalid/model"
    timeout: float = Field(default=10, gt=0, le=60)
    attempts: int = Field(default=3, ge=1, le=5)
