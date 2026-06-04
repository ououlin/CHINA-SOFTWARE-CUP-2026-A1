"""视觉语言模型(VL) provider 工厂。用于故障图片理解。"""
from functools import lru_cache

from ..config import settings
from .base import VLProvider


@lru_cache(maxsize=1)
def get_vl() -> VLProvider:
    provider = settings.vl_provider.lower()
    if provider == "dashscope":
        from .dashscope_vl import DashScopeVL
        return DashScopeVL()
    raise RuntimeError(f"未知 VL_PROVIDER: {provider}")
