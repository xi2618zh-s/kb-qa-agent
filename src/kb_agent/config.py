"""Settings from environment variables, optionally seeded from a local .env file."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Dict, Optional

from .llm.base import LLM, LLMError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOCS_DIR = ROOT / "data" / "docs"


def read_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


@dataclass
class Settings:
    provider: str
    api_key: str
    base_url: str
    model: str
    timeout: float

    @classmethod
    def load(cls, env_file: Optional[Path] = None) -> "Settings":
        file_values = read_env_file(env_file or ROOT / ".env")

        def get(key: str, default: str = "") -> str:
            return os.environ.get(key) or file_values.get(key) or default

        return cls(
            provider=get("LLM_PROVIDER", "mock").lower(),
            api_key=get("LLM_API_KEY"),
            base_url=get("LLM_BASE_URL"),
            model=get("LLM_MODEL", "deepseek-chat"),
            timeout=float(get("LLM_TIMEOUT", "60")),
        )


def make_llm(settings: Settings, provider: Optional[str] = None) -> LLM:
    provider = (provider or settings.provider).lower()
    if provider == "mock":
        from .llm.mock import MockLLM

        return MockLLM()
    if provider == "openai":
        if not settings.api_key:
            raise LLMError("未配置 LLM_API_KEY：请复制 .env.example 为 .env 并填写，或改用 --provider mock")
        from .llm.openai_compat import OpenAICompatLLM

        return OpenAICompatLLM(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url or None,
            timeout=settings.timeout,
        )
    raise LLMError(f"未知 provider：{provider}（可选 mock、openai）")
