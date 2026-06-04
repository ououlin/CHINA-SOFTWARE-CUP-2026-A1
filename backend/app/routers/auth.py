"""鉴权路由：登录、获取当前用户。"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, verify_password
from ..db import get_db
from ..models import User
from ..schemas import LoginResp, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResp)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.execute(
        select(User).where(User.username == form.username)
    ).scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token = create_access_token(user)
    return LoginResp(
        access_token=token, username=user.username,
        display_name=user.display_name or user.username, role=user.role,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
