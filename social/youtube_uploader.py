import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import googleapiclient.discovery
import googleapiclient.errors  
import googleapiclient.http
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

class YouTubeUploader:
    """YouTube video uploader using existing OAuth tokens from database"""
    
    API_SERVICE_NAME = "youtube"
    API_VERSION = "v3"
    
    def __init__(self):
        self.youtube_service = None
    
    def authenticate_with_token(self, access_token: str, refresh_token: str = None, client_id: str = None, client_secret: str = None) -> bool:
        """Authenticate with existing access token from database with refresh capability"""
        try:
            # Create credentials object with necessary fields for refresh
            creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=["https://www.googleapis.com/auth/youtube.upload"]
            )
            
            # Build YouTube service
            self.youtube_service = googleapiclient.discovery.build(
                self.API_SERVICE_NAME, self.API_VERSION, credentials=creds)
            
            logger.info("YouTube service authenticated with existing token (refresh-enabled)")
            return True
            
        except Exception as e:
            logger.error(f"YouTube authentication failed with token: {e}")
            return False

    
    def upload_video(self,
                    video_path: str,
                    title: str,
                    description: str = "",
                    tags: list = None,
                    category_id: str = "22",
                    privacy_status: str = "private",
                    made_for_kids: bool = False) -> Dict[str, Any]:
        """
        Upload a video to YouTube using existing authentication
        """
        
        if not self.youtube_service:
            return {"success": False, "error": "Not authenticated"}
            
        if not os.path.exists(video_path):
            return {"success": False, "error": f"Video file not found: {video_path}"}
        
        # Prepare tags
        if tags is None:
            tags = []
        
        # Remove # from tags if present and limit count
        clean_tags = [tag.replace("#", "").strip() for tag in tags if tag.strip()][:50]
        
        # YouTube API request body
        request_body = {
            "snippet": {
                "categoryId": category_id,
                "title": title[:100],  # YouTube title limit
                "description": description[:5000] if description else "",  # YouTube description limit
                "tags": clean_tags,
                "defaultLanguage": "en"
            },
            "status": {
                "privacyStatus": privacy_status,
                "madeForKids": made_for_kids,
                "selfDeclaredMadeForKids": made_for_kids
            }
        }
        
        try:
            # Create upload request
            media_file = googleapiclient.http.MediaFileUpload(
                video_path,
                chunksize=-1,  # Upload entire file in one request
                resumable=True
            )
            
            request = self.youtube_service.videos().insert(
                part="snippet,status",
                body=request_body,
                media_body=media_file
            )
            
            logger.info(f"Starting YouTube upload for: {title}")
            
            # Execute upload with progress tracking
            response = None
            while response is None:
                try:
                    status, response = request.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        logger.info(f"YouTube upload progress: {progress}%")
                except Exception as chunk_error:
                    logger.error(f"Upload chunk error: {chunk_error}")
                    # Try to continue with next chunk
                    continue
            
            if response and 'id' in response:
                video_id = response['id']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                logger.info(f"YouTube upload successful! Video ID: {video_id}")
                
                return {
                    "success": True,
                    "video_id": video_id,
                    "video_url": video_url,
                    "title": title,
                    "privacy_status": privacy_status,
                    "upload_time": datetime.utcnow().isoformat()
                }
            else:
                return {"success": False, "error": "Upload completed but no video ID received"}
                
        except googleapiclient.errors.HttpError as e:
            error_details = json.loads(e.content.decode('utf-8'))
            error_message = error_details.get('error', {}).get('message', str(e))
            logger.error(f"YouTube API error: {error_message}")
            return {"success": False, "error": f"YouTube API error: {error_message}"}
            
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return {"success": False, "error": str(e)}

# Global YouTube uploader instance
youtube_uploader = None

def get_youtube_uploader() -> YouTubeUploader:
    """Get or create YouTube uploader instance"""
    global youtube_uploader
    if youtube_uploader is None:
        youtube_uploader = YouTubeUploader()
    return youtube_uploader