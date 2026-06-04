"""Embedding provider 工厂：按配置返回本地或云端实现。"""
from functools import lru_cache

from ..config import settings
from .base import EmbeddingProvider


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider == "dashscope":
        from .dashscope import DashScopeEmbedding
        return DashScopeEmbedding()
    # 默认本地 fastembed
    from .local import LocalEmbedding
    return LocalEmbedding()
