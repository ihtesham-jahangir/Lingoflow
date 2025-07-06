# src/crud.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import User, OTP, StorySession
from src.schemas import StoryStart
from src.security import get_password_hash


# ────────────────────────────────────────────────────────────
# User helpers
# ────────────────────────────────────────────────────────────
async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()


async def create_user(db: AsyncSession, user: dict) -> User:
    hashed_password = get_password_hash(user["password"])
    db_user = User(
        email=user["email"],
        full_name=user["full_name"],
        hashed_password=hashed_password,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def update_user_password(db: AsyncSession, email: str, new_password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user:
        user.hashed_password = get_password_hash(new_password)
        await db.commit()
        await db.refresh(user)
    return user


async def update_user_verified(db: AsyncSession, email: str) -> None:
    user = await get_user_by_email(db, email)
    if not user:
        raise ValueError("User not found")
    user.is_verified = True
    await db.commit()
    await db.refresh(user)


# ────────────────────────────────────────────────────────────
# OTP helpers
# ────────────────────────────────────────────────────────────
async def create_otp(db: AsyncSession, email: str, otp_code: str, expires_at: datetime) -> OTP:
    otp = OTP(email=email, otp_code=otp_code, expires_at=expires_at)
    db.add(otp)
    await db.commit()
    await db.refresh(otp)
    return otp


async def get_otp_by_email_and_code(db: AsyncSession, email: str, otp_code: str) -> OTP | None:
    stmt = (
        select(OTP)
        .where(
            OTP.email == email,
            OTP.otp_code == otp_code,
            OTP.is_used.is_(False),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def mark_otp_as_used(db: AsyncSession, otp_id: int) -> None:
    otp = await db.get(OTP, otp_id)
    if otp:
        otp.is_used = True
        await db.commit()


# ────────────────────────────────────────────────────────────
# Story-session helpers (async)
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
) -> StorySession | None:
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


async def get_story_session(db: AsyncSession, session_id: int) -> StorySession | None:
    return await db.get(StorySession, session_id)
