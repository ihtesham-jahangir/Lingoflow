"""
Holds JWT helpers *and* DB-aware `authenticate_user`
so the main router can stay slim.
"""
import os
from datetime import datetime, timedelta
from typing import Any, Optional

from jose import jwt, JWTError
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from src.security import verify_password
from src.crud import get_user_by_email, get_user_by_username

load_dotenv()

SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")
ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
)


# ─── JWT ─────────────────────────────────────────────────────
def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ─── Auth ────────────────────────────────────────────────────
async def authenticate_user(
    identifier: str,
    password: str,
    db: AsyncSession,
) -> Optional[int]:  # returns user.id if OK
    if "@" in identifier:
        user = await get_user_by_email(db, identifier)
    else:
        user = await get_user_by_username(db, identifier)

    if user and verify_password(password, user.hashed_password):
        return user.id
    return None
