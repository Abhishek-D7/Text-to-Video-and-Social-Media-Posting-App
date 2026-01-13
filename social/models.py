
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import uuid

# SQLAlchemy Models
class SocialAccount(Base):
    __tablename__ = "social_accounts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    platform = Column(String(50), nullable=False)  # youtube, instagram, facebook, linkedin, tiktok
    
    # Universal fields
    platform_user_id = Column(String(255))  # Platform-specific user ID
    platform_username = Column(String(255))  # @username or handle
    platform_email = Column(String(255))  # Account email
    display_name = Column(String(255))  # Full name/channel name
    
    # OAuth2 tokens (all platforms need these)
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime(timezone=True))
    
    # Platform-specific identifiers
    # YouTube: channel_id, Instagram: user_id, Facebook: page_id, LinkedIn: organization_id, TikTok: user_id
    primary_id = Column(String(255))  # Main platform identifier
    secondary_id = Column(String(255))  # Secondary identifier if needed
    
    # Platform capabilities & settings
    platform_metadata = Column(JSONB, default=dict)  # Store platform-specific data
    # Example metadata:
    # YouTube: {"channel_type": "personal", "subscriber_count": 1000, "upload_quota": 100}
    # Instagram: {"account_type": "business", "follower_count": 500, "media_limit": 25}
    # Facebook: {"page_name": "My Page", "page_category": "brand", "fan_count": 200}
    # LinkedIn: {"company_name": "My Company", "follower_count": 300, "post_limit": 20}
    # TikTok: {"follower_count": 150, "video_count": 50}
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # Platform verification status
    account_status = Column(String(50), default="active")  # active, suspended, limited, etc.
    
    # Timestamps
    connected_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True))
    last_token_refresh = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("auth.models.User", back_populates="social_accounts")
    posts = relationship("SocialPost", back_populates="account", cascade="all, delete-orphan")

class SocialPost(Base):
    __tablename__ = "social_posts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("social_accounts.id", ondelete="CASCADE"))
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"))
    
    # Post content
    title = Column(String(255))
    description = Column(Text)
    tags = Column(JSONB, default=list)  # ["#ai", "#video", "cool"]
    
    # Platform-specific post data
    platform_post_id = Column(String(255))  # ID returned by platform
    post_url = Column(String(512))  # Direct URL to post
    embed_url = Column(String(512))  # Embed URL if different
    thumbnail_url = Column(String(512))  # Platform thumbnail URL
    
    # Platform-specific settings stored as JSON
    platform_settings = Column(JSONB, default=dict)
    # Examples:
    # YouTube: {"category_id": "22", "privacy_status": "public", "made_for_kids": false}
    # Instagram: {"caption": "...", "location": "New York", "accessibility_caption": "..."}
    # Facebook: {"targeting": {"age_min": 18}, "boost_budget": 0}
    # LinkedIn: {"visibility": {"members-only": true}, "article_type": "video"}
    # TikTok: {"privacy_level": "public", "comment_setting": "everyone"}
    
    # Post status and metrics
    status = Column(String(50), default="pending")  # pending, processing, posted, failed, scheduled
    post_type = Column(String(50), default="video")  # video, image, carousel, story, etc.
    
    # Scheduling
    posted_at = Column(DateTime(timezone=True))
    scheduled_for = Column(DateTime(timezone=True))
    
    # Engagement metrics (updated periodically)
    metrics = Column(JSONB, default=dict)
    # Examples:
    # YouTube: {"views": 1000, "likes": 50, "comments": 10, "shares": 5}
    # Instagram: {"likes": 100, "comments": 5, "saves": 2, "shares": 1}
    # Facebook: {"reactions": 20, "comments": 3, "shares": 2, "views": 500}
    # LinkedIn: {"reactions": 15, "comments": 2, "shares": 1, "views": 200}
    # TikTok: {"views": 2000, "likes": 80, "comments": 15, "shares": 10}
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_metrics_update = Column(DateTime(timezone=True))
    
    # Relationships
    account = relationship("SocialAccount", back_populates="posts")
    video = relationship("video.models.Video", back_populates="social_posts")

# Pydantic Models for API
class SocialAccountCreate(BaseModel):
    platform: str = Field(..., description="Platform name: youtube, instagram, facebook, linkedin, tiktok")
    platform_username: str = Field(..., min_length=1, description="Username/handle")
    platform_email: Optional[str] = None
    display_name: Optional[str] = None
    
    # OAuth tokens
    access_token: str = Field(..., min_length=10, description="OAuth2 access token")
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    
    # Platform-specific IDs
    primary_id: Optional[str] = None  # Channel ID for YouTube, User ID for others
    secondary_id: Optional[str] = None
    
    # Platform metadata
    platform_metadata: Optional[Dict[str, Any]] = {}
    
    # Verification
    is_verified: bool = False

class SocialAccountResponse(BaseModel):
    model_config = {"from_attributes": True}
    
    id: str
    platform: str
    platform_username: str
    platform_email: Optional[str] = None
    display_name: Optional[str] = None
    primary_id: Optional[str] = None
    is_active: bool
    is_verified: bool
    account_status: str
    connected_at: datetime
    last_used_at: Optional[datetime] = None
    platform_metadata: Dict[str, Any] = {}

class PostRequest(BaseModel):
    video_id: str = Field(..., description="Video task ID or UUID")
    platforms: List[str] = Field(..., min_items=1, description="List of platforms to post to")
    
    # Universal post content
    title: str = Field(..., min_length=1, max_length=200, description="Post title")
    description: Optional[str] = Field(None, max_length=5000, description="Post description/caption")
    tags: List[str] = Field(default=[], max_items=50, description="Tags/hashtags")
    
    # Platform-specific settings
    platform_settings: Optional[Dict[str, Dict[str, Any]]] = Field(default={})
    # Example:
    # {
    #   "youtube": {"category_id": "22", "privacy_status": "public", "made_for_kids": false},
    #   "instagram": {"location": "New York", "accessibility_caption": "Cool video"},
    #   "facebook": {"targeting": {"age_min": 18}},
    #   "linkedin": {"visibility": {"members-only": false}},
    #   "tiktok": {"privacy_level": "public", "comment_setting": "everyone"}
    # }
    
    # Scheduling
    scheduled_for: Optional[datetime] = None

class PostResponse(BaseModel):
    model_config = {"from_attributes": True}
    
    id: str
    platform: str
    platform_post_id: Optional[str] = None
    post_url: Optional[str] = None
    status: str
    title: Optional[str] = None
    description: Optional[str] = None
    posted_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = {}

class PlatformAuth(BaseModel):
    platform: str
    auth_url: str
    state: str
    scopes: List[str] = []

# Platform-specific validation models
class YouTubeAccountData(BaseModel):
    access_token: str
    refresh_token: str
    channel_id: str
    channel_title: str
    subscriber_count: Optional[int] = 0

class InstagramAccountData(BaseModel):
    access_token: str
    user_id: str
    username: str
    account_type: str = "personal"  # personal, business, creator
    follower_count: Optional[int] = 0

class FacebookAccountData(BaseModel):
    access_token: str
    page_id: str
    page_name: str
    page_access_token: str  # Different from user access token
    page_category: Optional[str] = None

class LinkedInAccountData(BaseModel):
    access_token: str
    person_id: Optional[str] = None  # For personal posts
    organization_id: Optional[str] = None  # For company posts
    profile_name: str

class TikTokAccountData(BaseModel):
    access_token: str
    open_id: str  # TikTok's user identifier
    username: str
    display_name: str
    follower_count: Optional[int] = 0