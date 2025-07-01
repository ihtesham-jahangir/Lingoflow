import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from dotenv import load_dotenv
from src.security import verify_password
from src.crud import get_user_by_email
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

async def authenticate_user(email: str, password: str, db):
 # Local import to avoid circular dependency
    
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user