import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
    RAPIDAPI_HOST = "sportapi7.p.rapidapi.com"
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    FREE_CHANNEL_ID = os.getenv("TELEGRAM_FREE_CHANNEL_ID")
    PREMIUM_CHANNEL_ID = os.getenv("TELEGRAM_PREMIUM_CHANNEL_ID")
    TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "mock_arbitrage_arena_bot")
    WHOP_CHECKOUT_LINK = os.getenv("WHOP_CHECKOUT_LINK", "https://whop.com/checkout/mock_arbitrage_arena_vip")
    
    # Safaricom Daraja API
    SAFARICOM_DARAJA_CONSUMER_KEY = os.getenv("SAFARICOM_DARAJA_CONSUMER_KEY")
    SAFARICOM_DARAJA_CONSUMER_SECRET = os.getenv("SAFARICOM_DARAJA_CONSUMER_SECRET")
    SAFARICOM_SHORTCODE = os.getenv("SAFARICOM_SHORTCODE")
    SAFARICOM_PASSKEY = os.getenv("SAFARICOM_PASSKEY")
    SAFARICOM_CALLBACK_URL = os.getenv("SAFARICOM_CALLBACK_URL")
    
    # Telegram Bot Payments (Stripe/PayPal)
    TELEGRAM_PAYMENT_PROVIDER_TOKEN = os.getenv("TELEGRAM_PAYMENT_PROVIDER_TOKEN")
    
    # CryptoPay API
    CRYPTOPAY_API_KEY = os.getenv("CRYPTOPAY_API_KEY")
    CRYPTOPAY_WEBHOOK_SECRET = os.getenv("CRYPTOPAY_WEBHOOK_SECRET")
    
    BASE_URL = "https://sportapi7.p.rapidapi.com/api/v1"
    
    # Affiliate Trackers
    INCOME_ACCESS_LINK = os.getenv("YOUR_INCOME_ACCESS_AFFILIATE_LINK", "YOUR_INCOME_ACCESS_AFFILIATE_LINK")
    GAMBLING_ATTACK_LINK = os.getenv("YOUR_GAMBLING_ATTACK_AFFILIATE_LINK", "YOUR_GAMBLING_ATTACK_AFFILIATE_LINK")
