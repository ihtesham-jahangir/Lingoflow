# src/crud.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import User, OTP, StorySession
from src.schemas import StoryStart
from src.security import get_password_hash


# ────────────────────────────────────────────────────────────
# User helpers
# ────────────────────────────────────────────────────────────
async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    res = await db.execute(select(User).where(User.email == email))
    return res.scalars().first()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    res = await db.execute(select(User).where(User.username == username))
    return res.scalars().first()


async def get_user_by_identifier(db: AsyncSession, ident: str) -> Optional[User]:
    """Return a user by e-mail **or** username."""
    if "@" in ident:
        return await get_user_by_email(db, ident)
    return await get_user_by_username(db, ident)


async def create_user(db: AsyncSession, data: dict[str, Any]) -> User:
    """`data` comes from `UserCreate.model_dump()` plus injected `username`."""
    hashed_pw = get_password_hash(data["password"])
    db_user = User(
        email=data["email"],
        username=data["username"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        country=data.get("country"),
        city=data.get("city"),
        phone_number=data.get("phone_number"),
        date_of_birth=data.get("date_of_birth"),
        hashed_password=hashed_pw,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def update_user_password(db: AsyncSession, email: str, new_pw: str) -> None:
    user = await get_user_by_email(db, email)
    if user:
        user.hashed_password = get_password_hash(new_pw)
        await db.commit()
        await db.refresh(user)


async def update_user_verified(db: AsyncSession, email: str) -> None:
    user = await get_user_by_email(db, email)
    if user:
        user.is_verified = True
        await db.commit()
        await db.refresh(user)


# ────────────────────────────────────────────────────────────
# OTP helpers
# ────────────────────────────────────────────────────────────
async def create_otp(
    db: AsyncSession, email: str, code: str, expires_at: datetime
) -> OTP:
    otp = OTP(email=email, otp_code=code, expires_at=expires_at)
    db.add(otp)
    await db.commit()
    await db.refresh(otp)
    return otp


async def get_otp_by_email_and_code(
    db: AsyncSession, email: str, code: str
) -> Optional[OTP]:
    stmt = (
        select(OTP)
        .where(
            OTP.email == email,
            OTP.otp_code == code,
            OTP.is_used.is_(False),
        )
    )
    res = await db.execute(stmt)
    return res.scalars().first()


async def mark_otp_as_used(db: AsyncSession, otp_id: int) -> None:
    otp = await db.get(OTP, otp_id)
    if otp:
        otp.is_used = True
        await db.commit()


# ────────────────────────────────────────────────────────────
# Story-session helpers
# ────────────────────────────────────────────────────────────
async def create_story_session(db: AsyncSession, story: StoryStart) -> StorySession:
    db_story = StorySession(
        user_id=story.user_id,
        interests=story.interests,
        current_story="",
        current_choices={},
        audio_path="",
        context_history=[],
    )
    db.add(db_story)
    await db.commit()
    await db.refresh(db_story)
    return db_story


async def update_story_session(
    db: AsyncSession,
    session_id: int,
    story_text: str,
    choices: Dict[int, str],
    audio_path: str,
    context: str,
) -> Optional[StorySession]:
    db_story = await db.get(StorySession, session_id)
    if not db_story:
        return None

    db_story.current_story = story_text
    db_story.current_choices = choices
    db_story.audio_path = audio_path
    history: List[str] = list(db_story.context_history or [])
    history.append(context)
    db_story.context_history = history

    await db.commit()
    await db.refresh(db_story)
    return db_story


async def get_story_session(db: AsyncSession, session_id: int) -> Optional[StorySession]:
    return await db.get(StorySession, session_id)
async def update_reset_password_otp_verified(db: AsyncSession, user_id: int, verified: bool) -> None:
    stmt = (
        select(User)
        .where(User.id == user_id)
    )
    
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if user:
        user.reset_password_otp_verified = verified
        await db.commit()
        await db.refresh(user)
    else:
        raise Exception("User not found")
# Update User Interests
async def update_user_interests(db: AsyncSession, user_id: int, interests: list):
    # Fetch the user by ID
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()

    if user:
        user.interests = interests
        db.add(user)
        await db.commit()
        return user
    return None

# Get User Interests
async def get_user_interests(db: AsyncSession, user_id: int):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        return user.interests
    return None


async def get_user_by_id(db, user_id):
    # Cast to int to match DB column type
    user_id = int(user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
