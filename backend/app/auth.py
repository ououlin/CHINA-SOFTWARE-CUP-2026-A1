"""鉴权工具：密码哈希（标准库 pbkdf2，免原生依赖）+ JWT 签发/校验。"""
import datetime as dt
import hashlib
import hmac
import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

_PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, rounds, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            bytes.fromhex(salt_hex), int(rounds),
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def create_access_token(user: User) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "username": user.username,
               "role": user.role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise cred_exc
    try:
        payload = jwt.decode(token, settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
    except Exception:
        raise cred_exc
    user = db.get(User, user_id)
    if not user:
        raise cred_exc
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return checker
