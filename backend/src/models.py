from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Date, UniqueConstraint
from src.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("username", name="uq_users_username"),
    )

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String, nullable=False, index=True)
    username      = Column(String(50), nullable=False, index=True)   # ← NEW

    first_name    = Column(String(100), nullable=False)              # ← NEW
    last_name     = Column(String(100), nullable=False)              # ← NEW
    country       = Column(String(100))                              # ← NEW
    city          = Column(String(100))                              # ← NEW
    phone_number  = Column(String(30))                               # ← NEW
    date_of_birth = Column(Date)                                     # ← NEW

    hashed_password = Column(String, nullable=False)

    is_active    = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    is_verified  = Column(Boolean, default=False)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
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