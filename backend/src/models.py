from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from src.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
# OTP table model
class OTP(Base):
    __tablename__ = "otps"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    otp_code = Column(String(6), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)


class StorySession(Base):
    __tablename__ = "story_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    interests = Column(JSON, nullable=False)
    current_story = Column(String, nullable=False)
    current_choices = Column(JSON, nullable=False)
    audio_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    context_history = Column(JSON, default=[]) 