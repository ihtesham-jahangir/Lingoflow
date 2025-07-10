"""
Misc helpers shared across the project.
"""
import secrets
import string
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud import get_user_by_username

_ALPHABET = string.ascii_lowercase + string.digits


async def generate_unique_username(
    db: AsyncSession,
    length: int = 8,
    prefix: str = "user",
) -> str:
    while True:
        candidate = f"{prefix}_{''.join(secrets.choice(_ALPHABET) for _ in range(length))}"
        if not await get_user_by_username(db, candidate):
            return candidate
