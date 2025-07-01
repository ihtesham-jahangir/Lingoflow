from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.schemas import UserCreate, User, Token, PasswordReset, NewPassword
from src.auth_utils import create_access_token, decode_token, authenticate_user
from src.crud import get_user_by_email, create_user, update_user_password
from datetime import timedelta
import os

router = APIRouter(tags=["Authentication"])

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload is None:
            raise credentials_exception
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user

@router.post("/signup", response_model=User, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    db_user = await get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_data = user.model_dump()
    return await create_user(db, user_data)

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
) -> Token:
    user = await authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/forgot-password")
async def forgot_password(
    reset: PasswordReset,
    db: AsyncSession = Depends(get_db)
) -> dict:
    user = await get_user_by_email(db, reset.email)
    if not user:
        return {"message": "If the email exists, a reset link will be sent"}
    
    reset_token = create_access_token(
        data={"sub": reset.email, "purpose": "password_reset"},
        expires_delta=timedelta(minutes=10)
    )
    # In production: Send email with this token
    print(f"Password reset token for {reset.email}: {reset_token}")
    return {"message": "Password reset instructions sent"}

@router.post("/reset-password")
async def reset_password(
    new_pw: NewPassword,
    db: AsyncSession = Depends(get_db)
) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token"
    )
    payload = decode_token(new_pw.token)
    if not payload:
        raise credentials_exception
    
    email = payload.get("sub")
    purpose = payload.get("purpose")
    if not email or purpose != "password_reset":
        raise credentials_exception
    
    user = await get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await update_user_password(db, email, new_pw.new_password)
    return {"message": "Password updated successfully"}

@router.get("/users/me", response_model=User)
async def read_current_user(
    current_user: User = Depends(get_current_user)
) -> User:
    return current_user