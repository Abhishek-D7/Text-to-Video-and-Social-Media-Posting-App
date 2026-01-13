import os
from pydantic_settings import BaseSettings
from pathlib import Path
class Settings(BaseSettings):
    # Database
    database_url: str = database_url
    
    # Security
    secret_key: str = "your-secret-key"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # AI Services
    hf_token: str = ""
    google_api_key: str = google_api_key 
    genai_text_model: str = "gemini-1.5-pro"
    genai_video_model: str = "veo-3"
    
    # Social Media APIs
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    youtube_client_id: str = youtube_client_id 
    youtube_client_secret: str = youtube_client_secret 
    youtube_redirect_uri: str = youtube_redirect_uri 
    youtube_api_key: str =  youtube_api_key 
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    tiktok_client_id: str = ""
    tiktok_client_secret: str = ""
    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    
    # File Storage
    upload_dir: str = "generated_videos"
    max_file_size_mb: int = 100
    
    # App Settings
    app_name: str = "Video Generation App"
    debug: bool = False
    
    class Config:
        env_file = ".env"


settings = Settings()