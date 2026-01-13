
import urllib.parse
import requests
import os
import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.core_config import settings
from core.database import get_db
from auth.dependencies import get_current_active_user
from auth.models import User
from video.models import Video
from .models import (
    SocialAccount, SocialPost,
    SocialAccountCreate, SocialAccountResponse,
    PostRequest, PostResponse
)





logger = logging.getLogger(__name__)
router = APIRouter(prefix="/social", tags=["social"])


# Platform configurations
PLATFORM_CONFIGS = {
    "youtube": {
        "name": "YouTube",
        "scopes": ["https://www.googleapis.com/auth/youtube.upload", 
                  "https://www.googleapis.com/auth/youtube.readonly"],
        "required_fields": ["channel_id", "channel_title"]
    },
    "instagram": {
        "name": "Instagram", 
        "scopes": ["instagram_basic", "instagram_content_publish"],
        "required_fields": ["user_id", "username"]
    },
    "facebook": {
        "name": "Facebook",
        "scopes": ["pages_manage_posts", "pages_read_engagement", "publish_video"],
        "required_fields": ["page_id", "page_name"]
    },
    "linkedin": {
        "name": "LinkedIn",
        "scopes": ["w_member_social", "r_basicprofile"],
        "required_fields": ["person_id"]
    },
    "tiktok": {
        "name": "TikTok",
        "scopes": ["video.publish", "user.info.basic"],
        "required_fields": ["open_id", "username"]
    },
    "twitter": {
        "name": "Twitter/X",
        "scopes": ["tweet.read", "tweet.write", "users.read"],
        "required_fields": ["user_id", "username"]
    }
}

@router.get("/platforms")
async def get_supported_platforms():
    """Get list of supported social media platforms with their capabilities"""
    platforms = []
    for platform_key, config in PLATFORM_CONFIGS.items():
        platforms.append({
            "name": platform_key,
            "display_name": config["name"],
            "supports": ["video", "scheduling", "metrics"],
            "auth_type": "oauth2",
            "scopes": config["scopes"],
            "required_fields": config["required_fields"]
        })
    
    return {"platforms": platforms}


@router.post("/youtube/upload-redirect")
async def youtube_upload_redirect(
    request: PostRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Generate YouTube Studio upload URL with pre-filled data"""
    
    try:
        # Get video
        video = db.query(Video).filter(
            Video.task_id == request.video_id,
            Video.user_id == current_user.id
        ).first()
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Get YouTube account
        youtube_account = db.query(SocialAccount).filter(
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == "youtube",
            SocialAccount.is_active == True
        ).first()
        
        if not youtube_account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No YouTube account connected"
            )
        
        # Create post record for tracking
        post = SocialPost(
            account_id=youtube_account.id,
            video_id=video.id,
            title=request.title or "AI Generated Video",
            description=request.description or "Amazing AI generated video!",
            tags=request.tags or ["AI", "Video"],
            status="redirect_ready",
            platform_settings=request.platform_settings.get("youtube", {}) if request.platform_settings else {},
            created_at=datetime.utcnow()
        )
        
        db.add(post)
        db.commit()
        db.refresh(post)
        
        # Get YouTube settings safely
        youtube_settings = {}
        if request.platform_settings:
            youtube_settings = request.platform_settings.get("youtube", {})
        
        privacy_status = youtube_settings.get("privacy_status", "unlisted")
        category_id = youtube_settings.get("category_id", "28")
        
        # Build YouTube Studio upload URL
        base_url = "https://studio.youtube.com"
        
        # For now, just redirect to YouTube Studio upload page
        # The full pre-fill URL is complex and may not work reliably
        upload_url = f"{base_url}/channel/{youtube_account.platform_user_id}/videos/upload"
        
        logger.info(f"YouTube Studio redirect created for user {current_user.id}, video {request.video_id}")
        
        return {
            "success": True,
            "post_id": str(post.id),
            "upload_url": upload_url,
            "message": "YouTube Studio redirect ready",
            "video_file_path": video.file_path or "N/A",
            "prefilled_data": {
                "title": request.title or "AI Generated Video",
                "description": request.description or "Amazing AI generated video!",
                "tags": request.tags or ["AI", "Video"],
                "privacy": privacy_status,
                "category": category_id
            },
            "instructions": [
                "1. Click the YouTube Studio link below",
                "2. YouTube Studio will open in a new tab", 
                "3. Upload your video file (drag & drop or select file)",
                "4. Fill in the title, description, and tags manually",
                "5. Set privacy and category settings",
                "6. Click 'Publish' or 'Schedule'"
            ]
        }
        
    except Exception as e:
        logger.error(f"YouTube upload redirect failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create YouTube redirect: {str(e)}"
        )

@router.post("/accounts/add", response_model=SocialAccountResponse)
async def add_social_account_manual(
    account_data: SocialAccountCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Manually add a social media account with tokens"""
    
    if account_data.platform not in PLATFORM_CONFIGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform: {account_data.platform}"
        )

    # Check if account already exists  
    existing_account = db.query(SocialAccount).filter(
        SocialAccount.user_id == current_user.id,
        SocialAccount.platform == account_data.platform,
        SocialAccount.platform_username == account_data.platform_username
    ).first()
    
    if existing_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account already exists for {account_data.platform}"
        )

    # Create new account
    try:
        social_account = SocialAccount(
            user_id=current_user.id,
            platform=account_data.platform,
            platform_user_id=getattr(account_data, 'primary_id', account_data.platform_username),
            platform_username=account_data.platform_username,
            platform_email=account_data.platform_email,
            access_token=account_data.access_token,
            refresh_token=account_data.refresh_token,
            token_expires_at=account_data.token_expires_at,
            is_active=True,
            connected_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )
        
        # Set new fields if they exist
        if hasattr(social_account, 'display_name'):
            social_account.display_name = getattr(account_data, 'display_name', account_data.platform_username)
        if hasattr(social_account, 'primary_id'):
            social_account.primary_id = getattr(account_data, 'primary_id', account_data.platform_username)
        if hasattr(social_account, 'platform_metadata'):
            social_account.platform_metadata = getattr(account_data, 'platform_metadata', {})
        if hasattr(social_account, 'is_verified'):
            social_account.is_verified = getattr(account_data, 'is_verified', False)
        if hasattr(social_account, 'last_token_refresh'):
            social_account.last_token_refresh = datetime.utcnow()

        db.add(social_account)
        db.commit()
        db.refresh(social_account)

        # Convert to response
        return SocialAccountResponse(
            id=str(social_account.id),
            platform=social_account.platform,
            platform_username=social_account.platform_username,
            platform_email=social_account.platform_email,
            display_name=getattr(social_account, 'display_name', social_account.platform_username),
            primary_id=getattr(social_account, 'primary_id', social_account.platform_user_id),
            is_active=social_account.is_active,
            is_verified=getattr(social_account, 'is_verified', False),
            account_status=getattr(social_account, 'account_status', 'active'),
            connected_at=social_account.connected_at,
            last_used_at=social_account.last_used_at,
            platform_metadata=getattr(social_account, 'platform_metadata', {})
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add {account_data.platform} account: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to add account: {str(e)}"
        )

@router.get("/accounts", response_model=List[SocialAccountResponse])
async def get_user_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user's connected social accounts"""
    accounts = db.query(SocialAccount).filter(
        SocialAccount.user_id == current_user.id
    ).all()
    
    response_accounts = []
    for account in accounts:
        response_accounts.append(SocialAccountResponse(
            id=str(account.id),
            platform=account.platform,
            platform_username=account.platform_username,
            platform_email=account.platform_email,
            display_name=getattr(account, 'display_name', account.platform_username),
            primary_id=getattr(account, 'primary_id', account.platform_user_id),
            is_active=account.is_active,
            is_verified=getattr(account, 'is_verified', False),
            account_status=getattr(account, 'account_status', 'active'),
            connected_at=account.connected_at,
            last_used_at=account.last_used_at,
            platform_metadata=getattr(account, 'platform_metadata', {})
        ))
    
    return response_accounts

@router.post("/post", response_model=List[PostResponse]) 
async def create_posts(
    request: PostRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Post video - YouTube gets special redirect treatment"""
    
    response_posts = []
    
    for platform in request.platforms:
        if platform == "youtube":
            # YouTube Upload
            try:
                # Get video file
                video = db.query(Video).filter(
                    Video.task_id == request.video_id,
                    Video.user_id == current_user.id
                ).first()
                
                if not video:
                    raise Exception("Video not found")
                
                # Get YouTube account with upload permissions
                youtube_account = db.query(SocialAccount).filter(
                    SocialAccount.user_id == current_user.id,
                    SocialAccount.platform == "youtube",
                    SocialAccount.is_active == True
                ).first()
                
                if not youtube_account:
                    raise Exception("No YouTube account connected")
                
                # Create post record
                post = SocialPost(
                    account_id=youtube_account.id,
                    video_id=video.id,
                    title=request.title or "AI Generated Video",
                    description=request.description or "Amazing AI generated video!",
                    tags=request.tags or ["AI", "Video"],
                    status="uploading",
                    platform_settings=request.platform_settings.get("youtube", {}) if request.platform_settings else {},
                    created_at=datetime.utcnow()
                )
                db.add(post)
                db.commit()
                db.refresh(post)
                
                # Import and use the YouTube uploader
                from .youtube_uploader import get_youtube_uploader
                
                logger.info(f"Starting YouTube upload: {request.title}")
                youtube_uploader = get_youtube_uploader()
                
                # Authenticate with database tokens
                # Authenticate with database tokens
                auth_success = youtube_uploader.authenticate_with_token(
                    access_token=youtube_account.access_token,
                    refresh_token=youtube_account.refresh_token,
                    client_id=settings.youtube_client_id,
                    client_secret=settings.youtube_client_secret
                )
                
                if not auth_success:
                    post.status = "failed"
                    post.error_message = "YouTube authentication failed"
                    db.commit()
                    raise Exception("YouTube authentication failed")

                
                # Get YouTube settings
                youtube_settings = request.platform_settings.get("youtube", {}) if request.platform_settings else {}

                # YouTube upload with video file
                try:
                    # Get full absolute path to video file
                    base_video_dir = os.path.join(os.path.dirname(__file__), "..", "generated_videos")
                    full_video_path = os.path.join(base_video_dir, os.path.basename(video.file_path))
                    full_video_path = os.path.abspath(full_video_path)

                    logger.info(f"Video file path: {full_video_path}")

                    # Check if file exists
                    if not os.path.exists(full_video_path):
                        raise Exception(f"Video file not found: {full_video_path}")

                    upload_result = youtube_uploader.upload_video(
                        video_path=full_video_path,
                        title=request.title or "AI Generated Video",
                        description=request.description or f"AI-generated video: {video.original_text or ''}",
                        tags=request.tags or ["AI", "Video", "Generated"],
                        category_id=youtube_settings.get("category_id", "28"),
                        privacy_status=youtube_settings.get("privacy_status", "private"),
                        made_for_kids=youtube_settings.get("made_for_kids", False)
                    )
                except Exception as upload_exc:
                    upload_result = {"success": False, "error": str(upload_exc)}
                
                # Update post based on upload result
                if upload_result.get("success"):
                    post.status = "posted"
                    post.platform_post_id = upload_result["video_id"]
                    post.post_url = upload_result["video_url"]
                    post.posted_at = datetime.utcnow()
                    post.metrics = {
                        "views": 0, 
                        "likes": 0, 
                        "comments": 0, 
                        "upload_status": "uploaded",
                        "youtube_video_id": upload_result["video_id"]
                    }
                    logger.info(f"YouTube upload successful! Video ID: {upload_result['video_id']}")
                    
                    response_posts.append(PostResponse(
                        id=str(post.id),
                        platform="youtube",
                        platform_post_id=upload_result["video_id"],
                        post_url=upload_result["video_url"],
                        status="posted",
                        title=request.title,
                        description=request.description,
                        posted_at=datetime.utcnow(),
                        error_message=None,
                        metrics=post.metrics
                    ))
                else:
                    post.status = "failed"
                    post.error_message = upload_result.get("error", "YouTube upload failed")
                    logger.error(f"YouTube upload failed: {post.error_message}")
                    
                    response_posts.append(PostResponse(
                        id=str(post.id),
                        platform="youtube",
                        status="failed",
                        title=request.title,
                        error_message=post.error_message,
                        metrics={}
                    ))
                
                # Save final post state
                db.commit()
                    
            except Exception as youtube_error:
                logger.error(f"YouTube upload exception: {youtube_error}")
                response_posts.append(PostResponse(
                    id=str(uuid.uuid4()),
                    platform="youtube",
                    status="failed",
                    title=request.title,
                    error_message=f"YouTube error: {str(youtube_error)}",
                    metrics={}
                ))

        
        else:
            # Other platforms: Regular demo posting
            # ... your existing platform logic ...
            pass
    
    return response_posts

@router.post("/youtube/connect-simple")
async def connect_youtube_simple(
    request: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Connect YouTube channel using username or custom URL to fetch real channel ID"""

    channel_name = request.get("channel_name", "").strip()
    if not channel_name:
        raise HTTPException(status_code=400, detail="Channel name required")

    api_key = settings.youtube_api_key
    if not api_key:
        raise HTTPException(status_code=500, detail="YouTube API key not configured")

    # Remove @ if present
    if channel_name.startswith("@"):
        channel_name = channel_name[1:]

    # Fetch channel by username
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "id,snippet", "forUsername": channel_name, "key": api_key}
    response = requests.get(url, params=params).json()

    if not response.get("items"):
        raise HTTPException(status_code=404, detail="Channel not found")

    channel = response["items"][0]
    channel_id = channel["id"]
    channel_title = channel["snippet"]["title"]

    # Save in DB
    youtube_account = SocialAccount(
        user_id=current_user.id,
        platform="youtube",
        platform_user_id=channel_id,
        platform_username=channel_name,
        display_name=channel_title,
        primary_id=channel_id,
        access_token="simple_api_key_connection",
        is_active=True,
        is_verified=True,
        connected_at=datetime.utcnow(),
        last_used_at=datetime.utcnow(),
        platform_metadata={"channel_title": channel_title, "channel_id": channel_id}
    )

    db.add(youtube_account)
    db.commit()
    db.refresh(youtube_account)

    return {
        "success": True,
        "message": f"YouTube channel {channel_title} connected successfully!",
        "channel_id": channel_id,
        "can_upload": True,
        "account_id": str(youtube_account.id)
    }


@router.delete("/accounts/{account_id}")
async def delete_social_account(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a social media account"""
    
    account = db.query(SocialAccount).filter(
        SocialAccount.id == account_id,
        SocialAccount.user_id == current_user.id
    ).first()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Social account not found"
        )

    platform_name = account.platform
    db.delete(account)
    db.commit()
    
    return {"message": f"Successfully deleted {platform_name} account"}

@router.get("/posts/{post_id}/metrics", response_model=Dict[str, Any])
async def get_post_metrics(
    post_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get post metrics from database"""
    
    # Use raw SQL to get post metrics
    sql = text("""
        SELECT sp.metrics, sp.status, sa.platform
        FROM social_posts sp
        JOIN social_accounts sa ON sp.account_id = sa.id
        WHERE sp.id = :post_id AND sa.user_id = :user_id
    """)
    
    result = db.execute(sql, {
        'post_id': post_id,
        'user_id': str(current_user.id)
    }).fetchone()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Return stored metrics
    try:
        metrics = json.loads(result.metrics) if result.metrics else {}
        return {
            **metrics,
            "status": result.status,
            "platform": result.platform
        }
    except:
        return {
            "views": 0,
            "likes": 0, 
            "comments": 0,
            "shares": 0,
            "status": result.status,
            "platform": result.platform
        }


@router.post("/auth/youtube/exchange-token")
async def exchange_youtube_token(
    request: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exchange OAuth code for tokens and save account"""
    
    code = request.get("code")
    state = request.get("state") 
    redirect_uri = request.get("redirect_uri")
    
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state"
        )
    
    try:
        # Exchange code for tokens
        token_data = {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri  # Use the 8000 redirect URI
        }
        
        response = requests.post("https://oauth2.googleapis.com/token", data=token_data)
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code for tokens"
            )
        
        tokens = response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        
        # Get YouTube channel info
        headers = {"Authorization": f"Bearer {access_token}"}
        channel_response = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            headers=headers,
            params={"part": "snippet,statistics", "mine": "true"}
        )
        
        if channel_response.status_code == 200:
            channel_data = channel_response.json()
            if channel_data["items"]:
                channel = channel_data["items"][0]
                channel_id = channel["id"]
                channel_title = channel["snippet"]["title"]
                subscriber_count = int(channel["statistics"].get("subscriberCount", 0))
                video_count = int(channel["statistics"].get("videoCount", 0))
                view_count = int(channel["statistics"].get("viewCount", 0))
                
                # Check if account already exists
                existing_account = db.query(SocialAccount).filter(
                    SocialAccount.user_id == current_user.id,
                    SocialAccount.platform == "youtube",
                    SocialAccount.primary_id == channel_id
                ).first()
                
                if existing_account:
                    # Update existing account
                    existing_account.access_token = access_token
                    existing_account.refresh_token = refresh_token
                    existing_account.token_expires_at = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
                    existing_account.last_token_refresh = datetime.utcnow()
                    existing_account.platform_metadata = {
                        "subscriber_count": subscriber_count,
                        "video_count": video_count,
                        "view_count": view_count,
                        "channel_type": "personal"
                    }
                    account = existing_account
                else:
                    # Create new account
                    account = SocialAccount(
                        user_id=current_user.id,
                        platform="youtube",
                        platform_user_id=channel_id,
                        platform_username=channel_title,
                        display_name=channel_title,
                        primary_id=channel_id,
                        access_token=access_token,
                        refresh_token=refresh_token,
                        token_expires_at=datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600)),
                        is_active=True,
                        is_verified=True,
                        connected_at=datetime.utcnow(),
                        last_used_at=datetime.utcnow(),
                        last_token_refresh=datetime.utcnow(),
                        platform_metadata={
                            "subscriber_count": subscriber_count,
                            "video_count": video_count,
                            "view_count": view_count,
                            "channel_type": "personal"
                        }
                    )
                    db.add(account)
                
                db.commit()
                db.refresh(account)
                
                logger.info(f"YouTube channel {channel_title} connected for user {current_user.id}")
                
                return {
                    "success": True,
                    "message": f"YouTube channel {channel_title} connected successfully!",
                    "channel_name": channel_title,
                    "channel_id": channel_id,
                    "subscriber_count": subscriber_count,
                    "account_id": str(account.id)
                }
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to get YouTube channel information"
        )
        
    except Exception as e:
        logger.error(f"Token exchange error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token exchange failed: {str(e)}"
        )



# OAuth endpoints (simplified for now)
@router.get("/auth/{platform}")
async def initiate_oauth(
    platform: str,
    current_user: User = Depends(get_current_active_user)
):
    """Initiate OAuth flow"""
    
    if platform == "youtube":
        client_id = settings.youtube_client_id
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="YouTube client ID not configured"
            )
        
        # Ensure this matches Google Console
        redirect_uri = "http://localhost:8000/social/auth/youtube/callback"
        scopes = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
        state = f"{current_user.id}:youtube:{uuid.uuid4()}"
        
        auth_url = (
            f"https://accounts.google.com/o/oauth2/auth?"
            f"client_id={client_id}&"
            f"redirect_uri={redirect_uri}&"  # This MUST match Google Console exactly
            f"scope={scopes}&"
            f"response_type=code&"
            f"access_type=offline&"
            f"prompt=consent&"
            f"state={state}"
        )
        
        return {
            "platform": platform,
            "auth_url": auth_url,
            "state": state,
            "instructions": "Click the URL above to login with your YouTube account"
        }
    
@router.get("/auth/youtube/login")
async def youtube_login(current_user: User = Depends(get_current_active_user)):
    client_id = settings.youtube_client_id
    redirect_uri = settings.youtube_redirect_uri
    
    # CHANGE THIS - Add upload scope
    scope = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
    
    state = f"{current_user.id}:youtube:{uuid.uuid4()}"
    
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"response_type=code&"
        f"scope={urllib.parse.quote(scope)}&"  # Now includes upload permission
        f"access_type=offline&"
        f"prompt=consent&"
        f"state={urllib.parse.quote(state)}"
    )
    
    return {"auth_url": auth_url, "state": state}




@router.get("/auth/youtube/callback")
async def youtube_oauth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: Session = Depends(get_db)
):
    logger.info(f"Callback URL: {request.url}")
    logger.info(f"Query params: {dict(request.query_params)}")
    
    if error:
        logger.error(f"OAuth error received: {error}")
        return RedirectResponse(
            url=f"http://localhost:8501/?oauth_status=error&error_msg={error}",
            status_code=302
        )
    
    if not code or not state:
        logger.error("Missing code or state parameters")
        return RedirectResponse(
            url="http://localhost:8501/?oauth_status=error&error_msg=missing_code_or_state",
            status_code=302
        )
    
    try:
        # Parse state to get user ID
        user_id_str, platform, request_id = state.split(":")
        user_id = uuid.UUID(user_id_str)
        
        # Exchange code for tokens
        token_data = {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": "http://localhost:8000/social/auth/youtube/callback"  # MUST match initiate_oauth
        }
        
        response = requests.post("https://oauth2.googleapis.com/token", data=token_data)
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.text}")
            return RedirectResponse(
                url="http://localhost:8501/?oauth_status=error&error_msg=token_exchange_failed",
                status_code=302
            )
        
        tokens = response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        
        # Get YouTube channel info
        headers = {"Authorization": f"Bearer {access_token}"}
        channel_response = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            headers=headers,
            params={"part": "snippet,statistics", "mine": "true"}
        )
        
        if channel_response.status_code == 200:
            channel_data = channel_response.json()
            if channel_data["items"]:
                channel = channel_data["items"][0]
                channel_id = channel["id"]
                channel_title = channel["snippet"]["title"]
                subscriber_count = int(channel["statistics"].get("subscriberCount", 0))
                video_count = int(channel["statistics"].get("videoCount", 0))
                view_count = int(channel["statistics"].get("viewCount", 0))
                
                # Check if account already exists
                existing_account = db.query(SocialAccount).filter(
                    SocialAccount.user_id == user_id,
                    SocialAccount.platform == "youtube",
                    SocialAccount.primary_id == channel_id
                ).first()
                
                if existing_account:
                    # Update existing account
                    existing_account.access_token = access_token
                    existing_account.refresh_token = refresh_token
                    existing_account.token_expires_at = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
                    existing_account.last_token_refresh = datetime.utcnow()
                    existing_account.platform_metadata = {
                        "subscriber_count": subscriber_count,
                        "video_count": video_count,
                        "view_count": view_count,
                        "channel_type": "personal"
                    }
                else:
                    # Create new account
                    account = SocialAccount(
                        user_id=user_id,
                        platform="youtube",
                        platform_user_id=channel_id,
                        platform_username=channel_title,
                        display_name=channel_title,
                        primary_id=channel_id,
                        access_token=access_token,
                        refresh_token=refresh_token,
                        token_expires_at=datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600)),
                        is_active=True,
                        is_verified=True,
                        connected_at=datetime.utcnow(),
                        last_used_at=datetime.utcnow(),
                        last_token_refresh=datetime.utcnow(),
                        platform_metadata={
                            "subscriber_count": subscriber_count,
                            "video_count": video_count,
                            "view_count": view_count,
                            "channel_type": "personal"
                        }
                    )
                    db.add(account)
                
                db.commit()
                
                logger.info(f"YouTube channel {channel_title} connected for user {user_id}")
                
                # Redirect to Streamlit with success
                return RedirectResponse(
                    url=f"http://localhost:8501/?oauth_status=success&platform=youtube&channel={channel_title}",
                    status_code=302
                )
        
        return RedirectResponse(
            url="http://localhost:8501/?oauth_status=error&error_msg=channel_fetch_failed",
            status_code=302
        )
        
    except Exception as e:
        logger.error(f"YouTube OAuth callback error: {e}")
        return RedirectResponse(
            url=f"http://localhost:8501/?oauth_status=error&error_msg={str(e)}",
            status_code=302
        )
    
 