# config.py - Updated with Real YouTube Integration
from core.core_config import settings
import os

def get_platform_config(platform: str) -> dict:
    """Get configuration for social media platform"""
    
    configs = {
        
        "youtube": {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "oauth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "user_info_url": "https://www.googleapis.com/youtube/v3/channels",
            "scopes": [
                "https://www.googleapis.com/auth/youtube",
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.readonly"
            ],
            "redirect_uri": "http://127.0.0.1:8000/social/auth/youtube/callback",
            # Real YouTube API settings
            "credentials_file": "client_secret.json",  # OAuth2 credentials from Google Cloud
            "token_pickle": "token.pickle",  # Stores access token
            "api_service_name": "youtube",
            "api_version": "v3"
        }
        
        
    }
    
    return configs.get(platform, {})


# YouTube specific configuration
YOUTUBE_CONFIG = {
    "UPLOAD_DIR": "uploads",
    "CREDENTIALS_DIR": "credentials",
    "MAX_FILE_SIZE": 128 * 1024 * 1024 * 1024,  # 128 GB (YouTube limit)
    "ALLOWED_VIDEO_FORMATS": [
        "video/mp4", "video/mpeg", "video/quicktime", 
        "video/avi", "video/wmv", "video/flv", "video/webm"
    ],
    "DEFAULT_CATEGORY_ID": "22",  # People & Blogs
    "PRIVACY_STATUSES": ["public", "unlisted", "private"],
    "RETRY_EXCEPTIONS": (
        ConnectionError, 
        TimeoutError,
        Exception  # Generic exception for API errors
    ),
    "MAX_RETRIES": 3,
    "RETRIABLE_STATUS_CODES": [500, 502, 503, 504]
}

def ensure_directories():
    """Ensure required directories exist"""
    dirs = [YOUTUBE_CONFIG["UPLOAD_DIR"], YOUTUBE_CONFIG["CREDENTIALS_DIR"]]
    for directory in dirs:
        os.makedirs(directory, exist_ok=True)

# Initialize directories on import
ensure_directories()