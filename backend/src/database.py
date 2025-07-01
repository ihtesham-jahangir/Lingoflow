import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Validate and force async driver
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

if "+asyncpg" not in DATABASE_URL:
    # Convert to async URL format
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        raise ValueError("DATABASE_URL must use postgresql+asyncpg:// protocol")

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    future=True,
    echo=True
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session