"""LLM provider 工厂。"""
from functools import lru_cache

from ..config import settings
from .base import LLMProvider


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "deepseek":
        from .deepseek import DeepSeekLLM
        return DeepSeekLLM()
    raise RuntimeError(f"未知 LLM_PROVIDER: {provider}")
