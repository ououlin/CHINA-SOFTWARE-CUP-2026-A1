"""接口限流（进阶）：纯 Python 内存滑动窗口，按「用户 + 接口组」限流。

目的：调用的是云端付费 API（DeepSeek / DashScope），防止前端连击或脚本刷接口
导致 Token 额度瞬间暴毙。零依赖（不引入 slowapi / redis），单机演示足够；
多实例横向扩展时可把计数后端换成 Redis，接口不变。审核员/管理员限额 ×3。
"""
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Depends, HTTPException

from .auth import get_current_user
from .config import settings
from .models import User

_WINDOW = 60.0
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def _check(key: str, limit: int) -> None:
    now = time.time()
    dq = _hits[key]
    while dq and now - dq[0] > _WINDOW:
        dq.popleft()
    if len(dq) >= limit:
        retry = int(_WINDOW - (now - dq[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁，请约 {retry} 秒后再试（接口限流保护云端额度）",
        )
    dq.append(now)


def rate_limit(group: str, limit_attr: str):
    """FastAPI 依赖：限流通过则返回当前用户（替代 get_current_user）。"""
    def dep(user: User = Depends(get_current_user)) -> User:
        if not settings.rate_limit_enabled:
            return user
        limit = getattr(settings, limit_attr)
        if user.role in ("auditor", "admin"):
            limit *= 3
        _check(f"{group}:{user.id}", limit)
        return user
    return dep
