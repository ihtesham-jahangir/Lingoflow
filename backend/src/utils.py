"""
Misc helpers shared across the project.
"""
import secrets
import string
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud import get_user_by_username

_ALPHABET = string.ascii_lowercase + string.digits


async def generate_unique_username(db: AsyncSession, max_attempts: int = 10) -> str:
    """Generate a unique username with a random string"""
    for _ in range(max_attempts):
        # Generate a random string of 8 characters
        random_str = ''.join(secrets.choice(string.ascii_lowercase + string.digits) 
                            for _ in range(8))
        username = f"user_{random_str}"
        
        # Check if username exists
        if not await get_user_by_username(db, username):
            return username
    
    # Fallback if all attempts fail
    return f"user_{secrets.token_hex(4)}"