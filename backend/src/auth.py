from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import os
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
from src.security import verify_password
from src.database import get_db
from src.schemas import UserCreate, User, Token, PasswordReset, NewPassword , LoginRequest
from src.auth_utils import create_access_token, decode_token, authenticate_user
from src.crud import (
    get_user_by_email, create_user, update_user_password,
    create_otp, mark_otp_as_used, get_otp_by_email_and_code,
    update_user_verified,
    get_user_by_identifier,
    get_user_by_username
)
from src.utils import generate_unique_username
router = APIRouter(tags=["Authentication"])

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
def render_email_template(otp: str, otp_expiry_minutes: int = 10) -> str:
    logo_url = "https://raw.githubusercontent.com/ihtesham-jahangir/portfolio-CICD/main/20250630_1212_Enhanced_Glow_remix_01jyztspq4ey7tne3b84nmtfz2-removebg-preview.png"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>LingoFlow Account Verification</title>
        <style type="text/css">
            /* Base styles with optimized contrast */
            body, table, td, p, a {{
                font-family: 'Segoe UI', 'SF Pro Display', -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', sans-serif;
                -webkit-text-size-adjust: 100%;
                -ms-text-size-adjust: 100%;
                margin: 0;
                padding: 0;
                color: #334155; /* Dark gray for better contrast */
                line-height: 1.7;
            }}
            body {{
                background-color: #f8fafc;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px 10px;
            }}
            .email-container {{
                max-width: 640px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 12px 30px rgba(0, 0, 0, 0.05);
                position: relative;
                z-index: 1;
                border: 1px solid #e2e8f0;
            }}
            .email-container:before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 6px;
                background: linear-gradient(90deg, #06b6d4, #0ea5e9, #0891b2);
                z-index: 2;
            }}
            .header {{
                background: #ffffff;
                padding: 40px 30px 30px;
                text-align: center;
                border-bottom: 1px solid #f1f5f9;
                position: relative;
            }}
            .logo-container {{
                display: inline-block;
                background: #ffffff;
                padding: 16px;
                border-radius: 24px;
                margin-bottom: 25px;
                box-shadow: 0 8px 20px rgba(8, 145, 178, 0.1);
                border: 1px solid #e2e8f0;
            }}
            .logo {{
                height: 56px;
                display: block;
            }}
            .header h1 {{
                margin: 0;
                font-size: 28px;
                font-weight: 700;
                letter-spacing: -0.5px;
                color: #0f172a; /* Dark color for contrast */
            }}
            .cyan-accent {{
                color: #0891b2;
                font-weight: 700;
            }}
            .content {{
                padding: 45px 50px 40px;
            }}
            .greeting {{
                margin-bottom: 30px;
                position: relative;
                padding-left: 25px;
            }}
            .greeting:before {{
                content: '';
                position: absolute;
                left: 0;
                top: 12px;
                height: 32px;
                width: 4px;
                background: linear-gradient(180deg, #06b6d4, #0891b2);
                border-radius: 4px;
            }}
            .greeting h2 {{
                font-size: 26px;
                font-weight: 700;
                margin: 0 0 10px;
                color: #0f172a; /* Dark color for contrast */
            }}
            .greeting p {{
                font-size: 17px;
                color: #475569; /* Medium gray for readability */
                margin: 0;
                line-height: 1.8;
            }}
            .otp-container {{
                background: linear-gradient(135deg, #f0f9ff 0%, #ecfeff 100%);
                border: 1px solid #cffafe;
                border-radius: 18px;
                padding: 40px 30px;
                text-align: center;
                margin: 30px 0;
                position: relative;
                overflow: hidden;
                box-shadow: 0 6px 15px rgba(8, 145, 178, 0.08);
            }}
            .otp-container:before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: linear-gradient(90deg, #06b6d4, #0ea5e9, #0891b2);
            }}
            .otp-title {{
                font-size: 18px;
                color: #475569; /* Medium gray for contrast */
                margin: 0 0 25px;
                font-weight: 500;
            }}
            .otp-code {{
                font-size: 48px;
                letter-spacing: 10px;
                color: #0c4a6e; /* Dark cyan-blue for maximum contrast */
                font-weight: 800;
                margin: 25px 0;
                font-family: 'SF Mono', 'Roboto Mono', monospace;
                padding: 15px 25px;
                display: inline-block;
                background: rgba(255, 255, 255, 0.7);
                border-radius: 14px;
                border: 1px dashed #a5f3fc;
                box-shadow: 0 5px 15px rgba(8, 145, 178, 0.1);
            }}
            .expiry {{
                font-size: 17px;
                color: #475569; /* Medium gray for contrast */
                margin-top: 25px;
                font-weight: 500;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }}
            .security-note {{
                background: linear-gradient(135deg, #ecfeff 0%, #f0f9ff 100%);
                border-left: 4px solid #06b6d4;
                padding: 22px;
                margin: 40px 0 30px;
                border-radius: 14px;
                display: flex;
                align-items: center;
                gap: 15px;
            }}
            .security-icon {{
                font-size: 28px;
                color: #0891b2;
                flex-shrink: 0;
            }}
            .security-text {{
                font-size: 16px;
                color: #164e63; /* Dark cyan-blue for contrast */
                line-height: 1.7;
                font-weight: 500;
            }}
            .quote-container {{
                background: linear-gradient(135deg, #f0f9ff 0%, #ecfeff 100%);
                border-radius: 16px;
                padding: 30px;
                margin: 40px 0;
                text-align: center;
                position: relative;
                overflow: hidden;
                border: 1px solid #cffafe;
            }}
            .quote {{
                font-style: italic;
                font-size: 19px;
                color: #164e63; /* Dark cyan-blue for contrast */
                margin: 0;
                position: relative;
                z-index: 1;
                font-weight: 500;
            }}
            .author {{
                font-size: 15px;
                color: #0891b2;
                margin-top: 15px;
                font-weight: 600;
            }}
            .cta-button {{
                display: block;
                width: 80%;
                max-width: 320px;
                background: linear-gradient(90deg, #06b6d4, #0891b2);
                color: #ffffff !important;
                text-align: center;
                padding: 20px;
                border-radius: 14px;
                margin: 45px auto 30px;
                text-decoration: none;
                font-weight: 600;
                font-size: 18px;
                box-shadow: 0 8px 20px rgba(6, 182, 212, 0.2);
                position: relative;
                overflow: hidden;
                border: none;
            }}
            .signature {{
                text-align: center;
                margin: 40px 0 0;
                font-size: 17px;
                color: #334155; /* Dark gray for contrast */
            }}
            .signature strong {{
                color: #0f172a; /* Very dark for contrast */
                font-weight: 700;
            }}
            .footer {{
                text-align: center;
                padding: 40px 30px 30px;
                background: #f8fafc;
                color: #64748b; /* Medium gray for footer text */
                font-size: 14px;
                border-top: 1px solid #e2e8f0;
            }}
            .social-icons {{
                display: flex;
                justify-content: center;
                gap: 20px;
                margin: 0 0 30px;
            }}
            .social-icon {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 44px;
                height: 44px;
                background: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
                border: 1px solid #e2e8f0;
            }}
            .social-icon img {{
                width: 22px;
                height: 22px;
            }}
            .footer-links {{
                display: flex;
                justify-content: center;
                flex-wrap: wrap;
                gap: 18px;
                margin: 0 0 25px;
            }}
            .footer-links a {{
                color: #0891b2;
                text-decoration: none;
                font-weight: 500;
                font-size: 14px;
            }}
            .footer-links a:hover {{
                text-decoration: underline;
            }}
            .copyright {{
                margin-top: 20px;
                font-size: 13px;
                line-height: 1.7;
            }}
            .copyright a {{
                color: #0891b2;
                text-decoration: none;
                font-weight: 500;
            }}
            
            /* Responsive styles */
            @media only screen and (max-width: 600px) {{
                .email-container {{
                    width: 100% !important;
                    border-radius: 0;
                    margin: 0;
                }}
                .content {{
                    padding: 30px 25px !important;
                }}
                .header {{
                    padding: 30px 20px 25px !important;
                }}
                .logo-container {{
                    padding: 14px !important;
                }}
                .logo {{
                    height: 48px !important;
                }}
                .greeting {{
                    padding-left: 20px !important;
                }}
                .greeting h2 {{
                    font-size: 22px !important;
                }}
                .otp-container {{
                    padding: 30px 20px !important;
                }}
                .otp-code {{
                    font-size: 36px !important;
                    letter-spacing: 8px !important;
                    padding: 12px 20px !important;
                }}
                .cta-button {{
                    width: 90% !important;
                    padding: 18px !important;
                    font-size: 16px !important;
                }}
                .footer {{
                    padding: 30px 20px !important;
                }}
                .footer-links {{
                    gap: 12px !important;
                }}
            }}
        </style>
    </head>
    <body>
        <center>
            <table border="0" cellpadding="0" cellspacing="0" width="100%" bgcolor="#f8fafc">
                <tr>
                    <td align="center" style="padding: 20px 10px;">
                        <!--[if (gte mso 9)|(IE)]>
                        <table align="center" border="0" cellspacing="0" cellpadding="0" width="640">
                        <tr>
                        <td align="center" valign="top" width="640">
                        <![endif]-->
                        <div class="email-container">
                            <div class="header">
                                <div class="logo-container">
                                    <img src="{logo_url}" alt="LingoFlow" class="logo" style="display: block;">
                                </div>
                                <h1>Account <span class="cyan-accent">Verification</span></h1>
                            </div>
                            
                            <div class="content">
                                <div class="greeting">
                                    <h2>Hello Language Learner! 👋</h2>
                                    <p>Welcome to <strong>LingoFlow</strong>! We're thrilled to have you join our community. To ensure the security of your account, please verify your email using the code below:</p>
                                </div>
                                
                                <div class="otp-container">
                                    <p class="otp-title">Your Verification Code</p>
                                    <div class="otp-code">{otp}</div>
                                    <p class="expiry">⏳ Valid for {otp_expiry_minutes} minutes</p>
                                </div>
                                
                                <div class="security-note">
                                    <div class="security-icon">🔒</div>
                                    <div class="security-text">
                                        <strong>Security Notice:</strong> This code is confidential. Never share it with anyone. LingoFlow will never ask you for this verification code.
                                    </div>
                                </div>
                                
                                <div class="quote-container">
                                    <p class="quote">"Language is the road map of a culture. It tells you where its people come from and where they are going."</p>
                                    <p class="author">- Rita Mae Brown</p>
                                </div>
                                
                                <a href="#" class="cta-button">Begin Your Language Journey</a>
                                
                                <p class="signature">Happy learning,<br><strong>The LingoFlow Team</strong></p>
                            </div>
                            
                            <div class="footer">
                                
                                
                                <p class="copyright">
                                    © 2025 LingoFlow Inc. All rights reserved.<br>
                                    Settlite Town Sargodha,40100,PK<br>
                                    <a href="#">Unsubscribe</a> | <a href="#">Update Preferences</a>
                                </p>
                                
                                <p style="font-size: 12px; margin-top: 20px; color: #94a3b8; line-height: 1.6;">
                                    This email was sent to you as part of your LingoFlow account registration.<br>
                                    Please do not reply to this automated message.
                                </p>
                            </div>
                        </div>
                        <!--[if (gte mso 9)|(IE)]>
                        </td>
                        </tr>
                        </table>
                        <![endif]-->
                    </td>
                </tr>
            </table>
        </center>
    </body>
    </html>
    """
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
class NewPassword(BaseModel):
    email: str
    otp: str
    new_password: str


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
@router.post("/login", response_model=Token)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    user = await get_user_by_identifier(db, data.identifier)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": str(user.id)})
    return Token(access_token=access_token, token_type="bearer")
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

# POST /reset-password
@router.post("/reset-password")
async def reset_password(
    new_pw: NewPassword,  # Expecting OTP instead of token
    db: AsyncSession = Depends(get_db)
) -> dict:
    email = new_pw.email
    otp_code = new_pw.otp  # Using OTP for validation
    new_password = new_pw.new_password

    # Get OTP from the database based on the email and the code provided
    otp = await get_otp_by_email_and_code(db, email, otp_code)
    if not otp or otp.expires_at < datetime.utcnow() or otp.is_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    # Mark OTP as used
    await mark_otp_as_used(db, otp.id)

    # Update the user's password
    await update_user_password(db, email, new_password)

    return {"message": "Password updated successfully"}