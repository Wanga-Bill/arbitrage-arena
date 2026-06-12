import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
    RAPIDAPI_HOST = "sportapi7.p.rapidapi.com"
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    FREE_CHANNEL_ID = os.getenv("TELEGRAM_FREE_CHANNEL_ID")
    PREMIUM_CHANNEL_ID = os.getenv("TELEGRAM_PREMIUM_CHANNEL_ID")
    
    BASE_URL = "https://sportapi7.p.rapidapi.com/api/v1"
    
    # Affiliate Trackers
    INCOME_ACCESS_LINK = os.getenv("YOUR_INCOME_ACCESS_AFFILIATE_LINK", "YOUR_INCOME_ACCESS_AFFILIATE_LINK")
    GAMBLING_ATTACK_LINK = os.getenv("YOUR_GAMBLING_ATTACK_AFFILIATE_LINK", "YOUR_GAMBLING_ATTACK_AFFILIATE_LINK")
