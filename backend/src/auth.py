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
import ssl
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

# SMTP configuration - Updated for better reliability
SMTP_SERVER = os.getenv("SMTP_SERVER", "mail.alphanetwork.com.pk")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))  # Changed to 587 for STARTTLS
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "no-reply@alphanetwork.com.pk")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "Hang1122@123")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "30"))

# Ensure SMTP credentials are loaded
if not SMTP_USERNAME or not SMTP_PASSWORD:
    logger.error("SMTP credentials (username or password) not found. Please set SMTP_USERNAME and SMTP_PASSWORD environment variables.")

# OTP Settings
OTP_EXPIRY_MINUTES = 10

# Function to generate OTP
def generate_otp():
    return pyotp.TOTP(pyotp.random_base32()).now()

# Enhanced SMTP email sending function
def send_otp_email_via_smtp(to_email: str, otp: str) -> bool:
    """
    Send OTP email via SMTP with improved error handling and multiple configuration options
    """
    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = formataddr(("LingoFlow", SMTP_USERNAME))
        msg["To"] = to_email
        msg["Subject"] = "Your LingoFlow Verification Code"
        msg.attach(MIMEText(render_email_template(otp, otp_expiry_minutes=10), "html"))

        # Try different SMTP configurations
        smtp_configs = [
            # Configuration 1: STARTTLS (most common)
            {
                "server": SMTP_SERVER,
                "port": 587,
                "use_tls": True,
                "use_ssl": False
            },
            # Configuration 2: SSL/TLS
            {
                "server": SMTP_SERVER,
                "port": 465,
                "use_tls": False,
                "use_ssl": True
            },
            # Configuration 3: Plain (not recommended but sometimes needed)
            {
                "server": SMTP_SERVER,
                "port": 25,
                "use_tls": False,
                "use_ssl": False
            },
            # Configuration 4: User-defined port with TLS
            {
                "server": SMTP_SERVER,
                "port": SMTP_PORT,
                "use_tls": SMTP_USE_TLS,
                "use_ssl": SMTP_USE_SSL
            }
        ]

        last_error = None
        
        for config in smtp_configs:
            try:
                logger.info(f"Attempting SMTP connection to {config['server']}:{config['port']} (TLS: {config['use_tls']}, SSL: {config['use_ssl']})")
                
                if config['use_ssl']:
                    # Use SMTP_SSL for SSL connections
                    context = ssl.create_default_context()
                    server = smtplib.SMTP_SSL(config['server'], config['port'], timeout=SMTP_TIMEOUT, context=context)
                else:
                    # Use regular SMTP
                    server = smtplib.SMTP(config['server'], config['port'], timeout=SMTP_TIMEOUT)
                    
                    if config['use_tls']:
                        server.starttls()
                
                # Login and send
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
                server.quit()
                
                logger.info(f"OTP email sent successfully to {to_email} via {config['server']}:{config['port']}")
                return True
                
            except Exception as config_error:
                last_error = config_error
                logger.warning(f"SMTP config {config['server']}:{config['port']} failed: {str(config_error)}")
                continue
        
        # If all configurations failed
        logger.error(f"All SMTP configurations failed. Last error: {str(last_error)}")
        return False
        
    except Exception as e:
        logger.error(f"Critical SMTP error: {str(e)}")
        return False

# Email delivery function with retry logic
def deliver_otp(email: str, otp: str, max_retries: int = 3) -> bool:
    """
    Deliver OTP with retry logic
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to send OTP to {email} (attempt {attempt + 1}/{max_retries})")
            
            if send_otp_email_via_smtp(email, otp):
                return True
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"Delivery attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    
    logger.error(f"Failed to deliver OTP to {email} after {max_retries} attempts. OTP: {otp}")
    return False

# Test SMTP connection function
def test_smtp_connection() -> dict:
    """
    Test SMTP connection and return status
    """
    test_configs = [
        {"server": SMTP_SERVER, "port": 587, "use_tls": True, "use_ssl": False},
        {"server": SMTP_SERVER, "port": 465, "use_tls": False, "use_ssl": True},
        {"server": SMTP_SERVER, "port": 25, "use_tls": False, "use_ssl": False},
    ]
    
    results = []
    
    for config in test_configs:
        try:
            if config['use_ssl']:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(config['server'], config['port'], timeout=10, context=context)
            else:
                server = smtplib.SMTP(config['server'], config['port'], timeout=10)
                if config['use_tls']:
                    server.starttls()
            
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.quit()
            
            results.append({
                "config": f"{config['server']}:{config['port']}",
                "tls": config['use_tls'],
                "ssl": config['use_ssl'],
                "status": "SUCCESS"
            })
            
        except Exception as e:
            results.append({
                "config": f"{config['server']}:{config['port']}",
                "tls": config['use_tls'],
                "ssl": config['use_ssl'],
                "status": f"FAILED: {str(e)}"
            })
    
    return {"smtp_tests": results}

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

    # Send OTP via email with improved error handling
    if not deliver_otp(email, otp):
        # Don't fail the request, but log the issue
        logger.error(f"Failed to send OTP email to {email}, but OTP was stored in database")
        # You might want to implement a fallback notification mechanism here
        return {
            "message": "OTP generated successfully. If email delivery fails, please contact support.",
            "otp_for_testing": otp if os.getenv("DEBUG", "false").lower() == "true" else None
        }

    return {"message": "OTP resent successfully"}

# Add SMTP test endpoint (for debugging)
@router.get("/test-smtp")
async def test_smtp():
    """
    Test SMTP connection - only enable in development
    """
    if os.getenv("DEBUG", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")
    
    return test_smtp_connection()

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
        
        await create_otp(db, user.email, otp, expires_at)

        # Try to send email, but don't fail signup if it fails
        email_sent = deliver_otp(user.email, otp)
        
        # persist user
        user_data = user.model_dump()
        user_data["username"] = username
        created_user = await create_user(db, user_data)
        
        response_data = {
            "user": created_user,
            "email_sent": email_sent
        }
        
        if not email_sent and os.getenv("DEBUG", "false").lower() == "true":
            response_data["otp_for_testing"] = otp
        
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
    
    email_sent = deliver_otp(reset.email, otp)
    
    response = {"message": "OTP for password reset sent"}
    if not email_sent and os.getenv("DEBUG", "false").lower() == "true":
        response["otp_for_testing"] = otp

    return response

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
    id_token: str
    access_token: str = None  # Optional for additional verification

@router.post("/google-login")
async def google_login(
    google_request: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Google Sign-In endpoint that accepts ID token from Flutter app
    """
    if not google_request.id_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing id_token"
        )

    try:
        # Verify the ID token with Google's public keys
        idinfo = id_token.verify_oauth2_token(
            google_request.id_token,
            google_requests.Request(),
            audience=os.getenv("GOOGLE_CLIENT_ID")
        )
        
        # Additional security checks
        if idinfo.get('iss') not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
            
        email = idinfo.get("email")
        full_name = idinfo.get("name", "")
        google_id = idinfo.get("sub")
        profile_picture = idinfo.get("picture", "")
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account does not have an email address"
            )
            
        if not idinfo.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email is not verified"
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ID token: {str(e)}"
        )

    # Check if user exists
    existing_user = await get_user_by_email(db, email)

    if existing_user:
        # Update Google ID if not present
        if not existing_user.google_id:
            await update_user_google_id(db, existing_user.id, google_id)
        
        # Generate JWT token for existing user
        access_token_jwt = create_access_token({"sub": str(existing_user.id)})
        return {
            "access_token": access_token_jwt, 
            "token_type": "bearer",
            "user": {
                "id": existing_user.id,
                "email": existing_user.email,
                "first_name": existing_user.first_name,
                "last_name": existing_user.last_name,
                "username": existing_user.username,
                "profile_picture": existing_user.profile_picture or profile_picture
            }
        }

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
        username=username,
        google_id=google_id,
        profile_picture=profile_picture,
        is_verified=True  # Auto-verify Google users
    )

    new_user = await create_user(db, new_user_data.model_dump())
    
    access_token_jwt = create_access_token({"sub": str(new_user.id)})
    return {
        "access_token": access_token_jwt, 
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name,
            "username": new_user.username,
            "profile_picture": new_user.profile_picture
        }
    }

# Dependency to get the current user from the JWT token
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
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception
    return user

# GET /me route
@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user