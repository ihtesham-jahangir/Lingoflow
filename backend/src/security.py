"""
Password-hash helpers — kept import-cycle-free.
"""
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _pwd_ctx.verify(password, hashed_password)
