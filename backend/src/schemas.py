from typing import Dict, List, Optional, Any
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, Integer, String, DateTime, func, JSON
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
    profile_picture: Optional[str] = None
    country: str | None = None
    city: str | None = None
    phone_number: str | None = None
    date_of_birth: date | None = None
    interests: List[str] = []  # Add interests field with default empty list

    class Config:
        from_attributes = True

class UserCreate(UserBase):
    password: str

    # Override interests to be optional in creation
    interests: List[str] = []

class User(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    is_verified: bool

    class Config:
        from_attributes = True

class UserInDB(User):
    """User model as it exists in the database"""
    hashed_password: str
    interests: List[str] = []  # Ensure it's in the DB model

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

class UserUpdate(BaseModel):
    """Model for updating user information - all fields are optional"""
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(
        default=None, min_length=3, max_length=50,
        description="Omit to receive a random username"
    )
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_picture: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    interests: Optional[List[str]] = None  # Make interests optional for updates
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "country": "United States",
                "city": "New York",
                "phone_number": "+1234567890",
                "date_of_birth": "1990-01-01"
            }
        }

# Updated SQLAlchemy User model with interests column
class UserDB(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    profile_picture = Column(String, nullable=True)
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    date_of_birth = Column(String, nullable=True)  # Using String for simplicity
    hashed_password = Column(String, nullable=False)
    is_active = Column(Integer, default=1)  # 1 for active, 0 for inactive
    is_superuser = Column(Integer, default=0)
    is_verified = Column(Integer, default=0)
    interests = Column(JSON, default=[])  # Add interests column as JSON

    class Config:
        from_attributes = True