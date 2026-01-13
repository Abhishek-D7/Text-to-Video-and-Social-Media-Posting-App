from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .models import User, UserCreate
import secrets
import string
from PIL import Image, ImageDraw, ImageFont
import io
import base64
import random
import time
import hashlib

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    if len(password.encode("utf-8")) > 72:
        password = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    if len(plain_password.encode("utf-8")) > 72:
        plain_password = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
    return pwd_context.verify(plain_password, hashed_password)

async def create_user(db: Session, user_data: UserCreate) -> User:
    """Create new user in database"""
    hashed_password = hash_password(user_data.password)
    
    user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=hashed_password,
        full_name=user_data.full_name
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

async def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Authenticate user with email and password"""
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    
    if not user or not verify_password(password, user.password_hash):
        return None
    
    # Update last login
    from datetime import datetime
    user.last_login = datetime.now()
    db.commit()
    
    return user

# CAPTCHA functionality
CAPTCHA_STORE = {}  # In production, use Redis

def generate_captcha() -> tuple[str, str]:
    """Generate a simple text-based CAPTCHA"""
    # Generate random 5-character string
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    
    # Create image
    img = Image.new('RGB', (150, 50), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use default font, fallback to basic if not available
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    # Add some noise and distortion
    for _ in range(20):
        x = random.randint(0, 150)
        y = random.randint(0, 50)
        draw.point((x, y), fill='gray')
    
    # Draw text
    draw.text((20, 15), captcha_text, fill='black', font=font)
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    # Store for verification (expires in 5 minutes)
    captcha_id = secrets.token_urlsafe(16)
    CAPTCHA_STORE[captcha_id] = {
        'text': captcha_text,
        'expires': time.time() + 300  # 5 minutes
    }
    
    return captcha_id, f"data:image/png;base64,{img_str}"

def verify_captcha(captcha_id: str, user_input: str) -> bool:
    """Verify CAPTCHA input"""
    
    
    if captcha_id not in CAPTCHA_STORE:
        return False
    
    captcha_data = CAPTCHA_STORE[captcha_id]
    
    # Check expiration
    if time.time() > captcha_data['expires']:
        del CAPTCHA_STORE[captcha_id]
        return False
    
    # Verify text (case insensitive)
    is_valid = captcha_data['text'].upper() == user_input.upper()
    
    # Remove after verification
    if captcha_id in CAPTCHA_STORE:
        del CAPTCHA_STORE[captcha_id]
    
    return is_valid
