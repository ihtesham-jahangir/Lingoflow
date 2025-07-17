from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import requests
import os
from src.crud import get_user_by_id
import pyotp
import jwt  # PyJWT
from jwt.exceptions import PyJWTError
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pydantic import BaseModel
from typing import Optional
import time  # For retry logic
import secrets  # For generating secure tokens
from src.email_templete import render_email_template
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from src.security import verify_password
from src.database import get_db
from src.schemas import UserCreate, User, Token, PasswordReset, NewPassword , LoginRequest
from src.auth_utils import create_access_token, decode_token, authenticate_user
from src.crud import (
    get_user_by_email, create_user, update_user_password,
    create_otp, mark_otp_as_used, get_otp_by_email_and_code,
    update_user_verified,
    get_user_by_identifier,
    get_user_by_username,update_reset_password_otp_verified
)
from src.utils import generate_unique_username
router = APIRouter(tags=["Authentication"])

class GoogleLoginRequest(BaseModel):
    code: str

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# Gmail SMTP configuration
GMAIL_SMTP_SERVER = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
GMAIL_USERNAME = os.getenv("GMAIL_USERNAME")  # Your Gmail address
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")  # Your Gmail App Password

# Ensure Gmail credentials are loaded
if not GMAIL_USERNAME or not GMAIL_PASSWORD:
    logger.error("Gmail credentials (username or password) not found. Please set GMAIL_USERNAME and GMAIL_APP_PASSWORD environment variables.")

# OTP Settings
OTP_EXPIRY_MINUTES = 10

# Function to generate OTP
def generate_otp():
    return pyotp.TOTP(pyotp.random_base32()).now()

# Send OTP via Gmail SMTP
def send_otp_email_via_gmail(to_email: str, otp: str) -> bool:
    try:
        msg = MIMEMultipart()
        msg["From"] = formataddr(("LingoFlow", GMAIL_USERNAME))
        msg["To"] = to_email
        msg["Subject"] = "Your LingoFlow Verification Code"
        msg.attach(MIMEText(render_email_template(otp, otp_expiry_minutes=10), "html"))

        with smtplib.SMTP(GMAIL_SMTP_SERVER, GMAIL_SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(GMAIL_USERNAME, GMAIL_PASSWORD)
            server.send_message(msg)
        logger.info(f"OTP sent via Gmail SMTP to {to_email}")
        return True
    except Exception as e:
        logger.warning(f"Gmail SMTP fallback failed: {str(e)}")
        return False

# Email delivery with Gmail SMTP
def deliver_otp(email: str, otp: str) -> bool:
    if send_otp_email_via_gmail(email, otp):
        return True
    logger.warning(f"Email delivery failed for {email}. Fallback OTP: {otp}")
    return False

# Pydantic Model for Verify Email Request
class VerifyEmailRequest(BaseModel):
    email: str
    otp: str


# POST /verify-email
@router.post("/verify-email")
async def verify_email(
    request: VerifyEmailRequest,  # Use the correct Pydantic model
    db: AsyncSession = Depends(get_db)
):
    email = request.email
    otp_code = request.otp

    # Validate OTP
    otp = await get_otp_by_email_and_code(db, email, otp_code)
    if not otp or otp.expires_at < datetime.utcnow() or otp.is_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )

    # Mark OTP as used
    await mark_otp_as_used(db, otp.id)

    # Mark user as verified
    await update_user_verified(db, email)

    return {"message": "Email verified successfully"}

class ResendOTPRequest(BaseModel):
    email: str
# ─────────── Resend OTP Endpoint ───────────
@router.post("/resend-otp")
async def resend_otp(request: ResendOTPRequest, db: AsyncSession = Depends(get_db)):
    email = request.email

    # Check if the user exists
    user = await get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Generate a new OTP
    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    # Store the new OTP in the database
    await create_otp(db, email, otp, expires_at)

    # Send OTP via email
    if not deliver_otp(email, otp):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send OTP email")

    return {"message": "OTP resent successfully"}


# ─────────── SIGN-UP ───────────
@router.post("/signup", response_model=User, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    if await get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    if user.username and await get_user_by_username(db, user.username):
        raise HTTPException(status_code=400, detail="Username already taken")

    # generate username if none supplied
    username = user.username or await generate_unique_username(db)

    try:
        # send OTP
        otp = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
        if not deliver_otp(user.email, otp):
            raise HTTPException(status_code=500, detail="Failed to send verification email")

        await create_otp(db, user.email, otp, expires_at)

        # persist user
        user_data = user.model_dump()
        user_data["username"] = username
        created_user = await create_user(db, user_data)
        return created_user

    except Exception as e:
        logger.error(f"Signup failed for {user.email}: {e}")
        raise HTTPException(status_code=500, detail="Registration failed, please try again")


# ─────────── LOGIN ───────────
@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user: User = await get_user_by_identifier(db, data.identifier)
    
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": str(user.id)})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id
    }
# POST /forgot-password
@router.post("/forgot-password")
async def forgot_password(
    reset: PasswordReset,
    db: AsyncSession = Depends(get_db)
) -> dict:
    user = await get_user_by_email(db, reset.email)
    if not user:
        return {"message": "If the email exists, an OTP will be sent"}

    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    await create_otp(db, reset.email, otp, expires_at)
    deliver_otp(reset.email, otp)

    return {"message": "OTP for password reset sent"}
class NewPassword(BaseModel):
    email: str
    new_password: str
# ─────────── Reset Password Endpoint ───────────
@router.post("/reset-password")
async def reset_password(new_pw: NewPassword, db: AsyncSession = Depends(get_db)) -> dict:
    email = new_pw.email
    new_password = new_pw.new_password

    # Get user from database
    user = await get_user_by_email(db, email)
    
    # Check if user exists
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    # Check if OTP for password reset has been verified
    if not user.reset_password_otp_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not verified. Please verify OTP before resetting your password.")
    
    # Update the user's password
    await update_user_password(db, email, new_password)

    return {"message": "Password updated successfully"}
@router.post("/verify-reset-otp")
async def verify_reset_otp(
    request: VerifyEmailRequest,  # OTP verification request model
    db: AsyncSession = Depends(get_db)
):
    email = request.email
    otp_code = request.otp

    # Fetch OTP from the database using the provided email and OTP code
    otp = await get_otp_by_email_and_code(db, email, otp_code)
    
    if not otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not found")
    
    if otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired")
    
    if otp.is_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has already been used")

    # OTP is valid, update the user's `reset_password_otp_verified` field
    user = await get_user_by_email(db, email)
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Update the reset_password_otp_verified field
    await update_reset_password_otp_verified(db, user.id, True)
    
    return {"message": "OTP successfully verified and password reset allowed"}

class GoogleLoginRequest(BaseModel):
    code: str

@router.post("/google-login")
async def google_login(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    body = await request.json()
    token = body.get("id_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing id_token"
        )

    try:
        # Verify the ID token with Google's public keys
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=os.getenv("GOOGLE_CLIENT_ID")
        )

        email = idinfo.get("email")
        full_name = idinfo.get("name", "")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account does not have an email address"
            )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ID token"
        )

    # Check if user exists
    existing_user = await get_user_by_email(db, email)

    if existing_user:
        # Generate JWT token for existing user
        access_token_jwt = create_access_token({"sub": str(existing_user.id)})
        return {"access_token": access_token_jwt, "token_type": "bearer"}

    # Create a new user
    dummy_password = secrets.token_urlsafe(16)
    name_parts = full_name.split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    username = await generate_unique_username(db)

    new_user_data = UserCreate(
        email=email,
        password=dummy_password,
        first_name=first_name,
        last_name=last_name,
        username=username
    )

    new_user = await create_user(db, new_user_data.model_dump())
    await update_user_verified(db, email)  # Auto-verify Google users

    access_token_jwt = create_access_token({"sub": str(new_user.id)})
    return {"access_token": access_token_jwt, "token_type": "bearer"}
# Dependency to extract the current user from token
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)  # Your own util to decode JWT
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception
    return user
# GET /me route
@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user