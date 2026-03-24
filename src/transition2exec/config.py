from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    service_name: str = "transition2exec"
    prompt_version: str = "0.1.0"
    backend: Literal["stub", "ollama", "openai_compatible", "qwen"] = "qwen"
    model_name: str = "transition2exec-stub"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_reasoning_model: str = "qwen2.5:3b"
    ollama_formatting_model: str = "qwen2.5:3b"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_model: str = "gpt-4o"
    openai_formatting_model: str = "gpt-4o"
    openai_api_key: str | None = None
    qwen_api_base: str = "http://localhost:11434/v1"
    qwen_model_name: str = "qwen2.5:3b"
    model_temperature: float = 0.0
    model_config = ConfigDict(env_file=".env", env_prefix="TRANSITION2EXEC_", extra="ignore")


settings = Settings()
