from typing import Dict, List
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from datetime import date

Base = declarative_base()

# ─────────── User ────────────
class UserBase(BaseModel):
    email: EmailStr

    # now optional
    username: str | None = Field(
        default=None, min_length=3, max_length=50,
        description="Omit to receive a random username",
    )

    first_name: str
    last_name: str

    country: str | None = None
    city: str | None = None
    phone_number: str | None = None
    date_of_birth: date | None = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    is_verified: bool

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str

class PasswordReset(BaseModel):
    email: EmailStr

class NewPassword(BaseModel):
    token: str
    new_password: str

class VerifyEmailRequest(BaseModel):
    email: str
    otp: str

class LoginEvent(Base):
    __tablename__ = "login_events"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    ip_address = Column(String)
    user_agent = Column(String)
    timestamp = Column(DateTime, server_default=func.now())
    successful = Column(Integer)

class StoryStart(BaseModel):
    user_id: int
    interests: List[str]

class StoryContinue(BaseModel):
    session_id: int
    choice: int
    context_token: str

class StoryResponse(BaseModel):
    session_id: int
    story_text: str
    choices: Dict[int, str]
    audio_url: str
    context_token: str
class LoginRequest(BaseModel):
    identifier: str  # email OR username
    password: str
class UserInterestsUpdate(BaseModel):
    interests: List[str]  # A list of interests, stored as strings

    class Config:
        orm_mode = True