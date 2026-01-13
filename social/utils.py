# utils.py - Updated with Real YouTube Integration
import httpx
import secrets
import os
import json
import pickle
import shutil
from urllib.parse import urlencode, parse_qs
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

# Google API imports for real YouTube integration
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    from google_auth_oauthlib.flow import Flow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    GOOGLE_API_AVAILABLE = True
except ImportError:
    print("WARNING: Google API packages not installed.")
    GOOGLE_API_AVAILABLE = False

from .models import SocialAccount, SocialPost, YouTubeChannelInfo, YouTubeVideoStatus
from .config import get_platform_config, YOUTUBE_CONFIG
import logging

logger = logging.getLogger(__name__)


class SocialMediaAPI:
    """Base class for social media platform APIs"""
    
    def __init__(self, platform: str):
        self.platform = platform
        self.config = get_platform_config(platform)
    
    async def post_video(self, account: SocialAccount, video_path: str, caption: str, hashtags: list = None) -> Dict[str, Any]:
        """Post video to platform - to be implemented by subclasses"""
        raise NotImplementedError


class YouTubeAPI(SocialMediaAPI):
    """Real YouTube API integration using Google API Client"""
    
    def __init__(self):
        super().__init__("youtube")
        self.credentials_file = os.path.join(
            YOUTUBE_CONFIG["CREDENTIALS_DIR"], 
            self.config["credentials_file"]
        )
    
    def get_oauth_flow(self, state: str = None) -> Flow:
        """Create OAuth2 flow for YouTube authentication"""
        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"OAuth2 credentials file not found: {self.credentials_file}. "
                "Download client_secret.json from Google Cloud Console."
            )
        
        flow = Flow.from_client_secrets_file(
            self.credentials_file,
            scopes=self.config["scopes"]
        )
        
        flow.redirect_uri = self.config["redirect_uri"]
        return flow
    
    def get_youtube_service(self, account: SocialAccount):
        """Get authenticated YouTube API service"""
        try:
            # Create credentials from stored tokens
            creds = Credentials(
                token=account.access_token,
                refresh_token=account.refresh_token,
                token_uri=self.config["token_url"],
                client_id=self.config["client_id"],
                client_secret=self.config["client_secret"],
                scopes=self.config["scopes"]
            )
            
            # Refresh token if expired
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Update account with new token
                account.access_token = creds.token
                account.token_expires_at = creds.expiry
            
            return build(
                self.config["api_service_name"],
                self.config["api_version"],
                credentials=creds
            )
        except Exception as e:
            logger.error(f"Failed to create YouTube service: {e}")
            raise
    
    async def get_channel_info(self, account: SocialAccount) -> YouTubeChannelInfo:
        """Get YouTube channel information"""
        try:
            youtube = self.get_youtube_service(account)
            
            response = youtube.channels().list(
                part="snippet,statistics,brandingSettings",
                mine=True
            ).execute()
            
            if not response.get("items"):
                raise Exception("No YouTube channel found for this account")
            
            channel = response["items"][0]
            snippet = channel["snippet"]
            statistics = channel["statistics"]
            
            return YouTubeChannelInfo(
                channel_id=channel["id"],
                channel_title=snippet["title"],
                subscriber_count=int(statistics.get("subscriberCount", 0)),
                video_count=int(statistics.get("videoCount", 0)),
                view_count=int(statistics.get("viewCount", 0)),
                custom_url=snippet.get("customUrl"),
                description=snippet.get("description"),
                thumbnail_url=snippet["thumbnails"]["default"]["url"]
            )
            
        except Exception as e:
            logger.error(f"Failed to get YouTube channel info: {e}")
            raise
    
    async def upload_video(
        self, 
        account: SocialAccount, 
        video_path: str, 
        title: str, 
        description: str = "",
        tags: List[str] = None,
        category_id: str = "22",
        privacy_status: str = "private",
        **kwargs
    ) -> Dict[str, Any]:
        """Upload video to YouTube with real API integration"""
        
        try:
            # Validate file
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            file_size = os.path.getsize(video_path)
            if file_size > YOUTUBE_CONFIG["MAX_FILE_SIZE"]:
                raise ValueError("Video file exceeds YouTube size limit (128GB)")
            
            youtube = self.get_youtube_service(account)
            
            # Prepare video metadata
            body = {
                "snippet": {
                    "title": title[:100],  # YouTube title limit
                    "description": description[:5000],  # YouTube description limit
                    "tags": tags[:50] if tags else [],  # YouTube tags limit
                    "categoryId": category_id,
                    "defaultLanguage": kwargs.get("default_language", "en"),
                    "defaultAudioLanguage": kwargs.get("default_language", "en")
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": kwargs.get("made_for_kids", False),
                    "embeddable": kwargs.get("embeddable", True),
                    "publicStatsViewable": kwargs.get("public_stats_viewable", True),
                    "license": kwargs.get("license", "youtube")
                }
            }
            
            # Create media upload object
            media = MediaFileUpload(
                video_path,
                chunksize=-1,
                resumable=True,
                mimetype="video/*"
            )
            
            # Execute upload
            logger.info(f"Starting YouTube upload for video: {title}")
            insert_request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )
            
            # Upload with resumable upload
            response = None
            error = None
            retry = 0
            
            while response is None:
                try:
                    status, response = insert_request.next_chunk()
                    if status:
                        logger.info(f"Upload progress: {int(status.progress() * 100)}%")
                        
                except HttpError as e:
                    if e.resp.status in YOUTUBE_CONFIG["RETRIABLE_STATUS_CODES"]:
                        error = f"HTTP error {e.resp.status}: {e.content}"
                        logger.warning(f"Retriable error: {error}")
                        retry += 1
                        if retry > YOUTUBE_CONFIG["MAX_RETRIES"]:
                            raise Exception(f"Max retries exceeded: {error}")
                    else:
                        raise e
                
                except Exception as e:
                    logger.error(f"Upload error: {e}")
                    raise e
            
            if response:
                video_id = response.get("id")
                if video_id:
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    logger.info(f"Upload successful! Video ID: {video_id}")
                    
                    return {
                        "success": True,
                        "video_id": video_id,
                        "video_url": video_url,
                        "title": title,
                        "status": response.get("status", {}),
                        "snippet": response.get("snippet", {}),
                        "upload_status": "uploaded"
                    }
                else:
                    raise Exception("Upload completed but no video ID returned")
            else:
                raise Exception("Upload failed - no response received")
                
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "upload_status": "failed"
            }
    
    async def get_video_status(self, video_id: str, account: SocialAccount) -> YouTubeVideoStatus:
        """Get video processing status from YouTube"""
        try:
            youtube = self.get_youtube_service(account)
            
            response = youtube.videos().list(
                part="status,processingDetails",
                id=video_id
            ).execute()
            
            if not response.get("items"):
                raise Exception(f"Video not found: {video_id}")
            
            video = response["items"][0]
            status = video["status"]
            processing = video.get("processingDetails", {})
            
            return YouTubeVideoStatus(
                video_id=video_id,
                upload_status=status.get("uploadStatus", "unknown"),
                privacy_status=status.get("privacyStatus", "unknown"),
                failure_reason=status.get("failureReason"),
                rejection_reason=status.get("rejectionReason"),
                processing_progress=processing
            )
            
        except Exception as e:
            logger.error(f"Failed to get video status: {e}")
            raise


class InstagramAPI(SocialMediaAPI):
    def __init__(self):
        super().__init__("instagram")
    
    async def post_video(self, account: SocialAccount, video_path: str, caption: str, hashtags: list = None) -> Dict[str, Any]:
        """Post video to Instagram (existing implementation)"""
        # Keep your existing Instagram implementation
        pass


class FacebookAPI(SocialMediaAPI):
    def __init__(self):
        super().__init__("facebook")
    
    async def post_video(self, account: SocialAccount, video_path: str, caption: str, hashtags: list = None) -> Dict[str, Any]:
        """Post video to Facebook (existing implementation)"""
        # Keep your existing Facebook implementation
        pass


# Platform factory
def get_platform_api(platform: str) -> SocialMediaAPI:
    """Get appropriate API class for platform"""
    apis = {
        "youtube": YouTubeAPI,
        "instagram": InstagramAPI,
        "facebook": FacebookAPI,
    }
    
    api_class = apis.get(platform)
    if not api_class:
        raise ValueError(f"Unsupported platform: {platform}")
    
    return api_class()


# OAuth utilities
def get_oauth_url(platform: str, user_id: str) -> Dict[str, str]:
    """Generate OAuth URL for platform authentication"""
    config = get_platform_config(platform)
    if not config:
        raise ValueError(f"Platform not supported: {platform}")
    
    state = secrets.token_urlsafe(32)
    
    if platform == "youtube":
        # Use Google OAuth2 flow
        youtube_api = YouTubeAPI()
        flow = youtube_api.get_oauth_flow(state)
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to get refresh token
        )
        
        return {
            "auth_url": auth_url,
            "state": state
        }
    else:
        # Generic OAuth for other platforms
        params = {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "scope": " ".join(config["scopes"]),
            "response_type": "code",
            "state": f"{state}:{user_id}:{platform}"
        }
        
        auth_url = f"{config['oauth_url']}?{urlencode(params)}"
        
        return {
            "auth_url": auth_url,
            "state": state
        }


async def handle_oauth_callback(
    platform: str, 
    code: str, 
    state: str, 
    user_id: str, 
    db: Session
) -> SocialAccount:
    """Handle OAuth callback and store account"""
    
    config = get_platform_config(platform)
    
    if platform == "youtube":
        return await handle_youtube_callback(code, state, user_id, db)
    else:
        # Handle other platforms with generic OAuth
        return await handle_generic_oauth_callback(platform, code, state, user_id, db)


async def handle_youtube_callback(code: str, state: str, user_id: str, db: Session) -> SocialAccount:
    """Handle YouTube OAuth callback"""
    try:
        youtube_api = YouTubeAPI()
        flow = youtube_api.get_oauth_flow(state)
        
        # Exchange code for token
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Get channel info
        youtube = build("youtube", "v3", credentials=credentials)
        response = youtube.channels().list(part="snippet", mine=True).execute()
        
        if not response.get("items"):
            raise Exception("No YouTube channel found")
        
        channel = response["items"][0]
        channel_snippet = channel["snippet"]
        
        # Create or update social account
        account = db.query(SocialAccount).filter(
            SocialAccount.user_id == user_id,
            SocialAccount.platform == "youtube",
            SocialAccount.channel_id == channel["id"]
        ).first()
        
        if not account:
            account = SocialAccount(
                user_id=user_id,
                platform="youtube"
            )
            db.add(account)
        
        # Update account with new credentials
        account.access_token = credentials.token
        account.refresh_token = credentials.refresh_token
        account.token_expires_at = credentials.expiry
        account.platform_user_id = channel["id"]
        account.channel_id = channel["id"]
        account.channel_title = channel_snippet["title"]
        account.platform_username = channel_snippet["title"]
        account.platform_email = None  # Would need additional API call
        account.last_used_at = datetime.utcnow()
        account.is_active = True
        
        db.commit()
        db.refresh(account)
        
        logger.info(f"YouTube account connected: {channel_snippet['title']}")
        return account
        
    except Exception as e:
        logger.error(f"YouTube OAuth callback failed: {e}")
        raise


async def handle_generic_oauth_callback(
    platform: str, 
    code: str, 
    state: str, 
    user_id: str, 
    db: Session
) -> SocialAccount:
    """Handle generic OAuth callback for other platforms"""
    # Keep your existing implementation for other platforms
    pass


async def post_to_platform(
    account: SocialAccount, 
    video_path: str, 
    post_data: Dict[str, Any],
    db: Session
) -> Dict[str, Any]:
    """Post video to social media platform"""
    
    try:
        api = get_platform_api(account.platform)
        
        if account.platform == "youtube":
            result = await api.upload_video(
                account=account,
                video_path=video_path,
                title=post_data.get("title", ""),
                description=post_data.get("description", ""),
                tags=post_data.get("tags", []),
                category_id=post_data.get("category_id", "22"),
                privacy_status=post_data.get("privacy_status", "private"),
                **post_data.get("youtube_settings", {})
            )
        else:
            result = await api.post_video(
                account=account,
                video_path=video_path,
                caption=post_data.get("caption", ""),
                hashtags=post_data.get("hashtags", [])
            )
        
        # Update last used timestamp
        account.last_used_at = datetime.utcnow()
        db.commit()
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to post to {account.platform}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def schedule_post(post_id: str, scheduled_time: datetime):
    """Schedule a post for later (placeholder for celery/background task)"""
    # This would integrate with your background task system
    # (Celery, RQ, or similar)
    pass