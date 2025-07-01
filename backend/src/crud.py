from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import User
from src.security import get_password_hash  # Import from security.py

async def get_user_by_email(db: AsyncSession, email: str) -> User:
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalars().first()

async def create_user(db: AsyncSession, user: dict) -> User:
    hashed_password = get_password_hash(user["password"])
    db_user = User(
        email=user["email"],
        full_name=user["full_name"],
        hashed_password=hashed_password
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user_password(db: AsyncSession, email: str, new_password: str) -> User:
    user = await get_user_by_email(db, email)
    if user:
        user.hashed_password = get_password_hash(new_password)
        await db.commit()
        await db.refresh(user)
    return user