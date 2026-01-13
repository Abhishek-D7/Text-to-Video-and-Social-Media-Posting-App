"""
User authentication models
"""
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from core.database import Base
from core.pydantic_base import OrmBase
from pydantic import EmailStr, field_serializer
from typing import Optional
from datetime import datetime
import uuid

# SQLAlchemy Model
class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships using fully qualified paths
    social_accounts = relationship(
        "social.models.SocialAccount", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    videos = relationship(
        "video.models.Video",
        back_populates="user",
        cascade="all, delete-orphan"
    )

# Pydantic Models
class UserCreate(OrmBase):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None

class UserLogin(OrmBase):
    email: EmailStr
    password: str

class UserResponse(OrmBase):
    id: str  # Will be serialized from UUID to str
    email: str
    username: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    
    @field_serializer("id")
    def serialize_id(self, value) -> str:
        return str(value)

class Token(OrmBase):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"