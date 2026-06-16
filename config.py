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
    
    # Listmonk Credentials
    LISTMONK_API_URL = os.getenv("LISTMONK_API_URL", "http://localhost:9000/api")
    LISTMONK_USERNAME = os.getenv("LISTMONK_USERNAME", "api_agent")
    LISTMONK_PASSWORD = os.getenv("LISTMONK_PASSWORD")
    LISTMONK_DB_PASSWORD = os.getenv("LISTMONK_DB_PASSWORD")
    LISTMONK_ADMIN_PASSWORD = os.getenv("LISTMONK_ADMIN_PASSWORD")
    
    BASE_URL = "https://sportapi7.p.rapidapi.com/api/v1"
    
    # Affiliate Trackers
    INCOME_ACCESS_LINK = os.getenv("YOUR_INCOME_ACCESS_AFFILIATE_LINK", "YOUR_INCOME_ACCESS_AFFILIATE_LINK")
    GAMBLING_ATTACK_LINK = os.getenv("YOUR_GAMBLING_ATTACK_AFFILIATE_LINK", "YOUR_GAMBLING_ATTACK_AFFILIATE_LINK")

    @classmethod
    def validate(cls):
        """Validates that all critical credentials are set and secure."""
        # Compromised historic values (commit 02d5aec4)
        COMPROMISED_SECRETS = {
            "8857855755:AAF-YxPVBqJpv4PzUqfwaGbTpoKGLQ0Ra5w", # historic telegram bot token
            "596334:AA1dYlvQobh5dvQfzrOhX72uG8qmDb2hnPf",      # historic cryptopay api key
            "AFNeWPKPkIr09fv6mh9eKwcYsGgjkj2wwxgIvZgh10wk3WWS", # historic safaricom key
            "OckVaZ2ALIPotnQjTUt65ZSPZoF6q0yCuXfyyKteaAAnjQ0dPSM9FX3hfGtbcgxr", # historic safaricom secret
            "8vNiP7dgh13dntgtRYAOylPR1C6BN4PH", # historic listmonk api password
            "ArenaAdmin_db_secure_2026!", # historic default listmonk db pass
            "L1stM0nk_admin_5ecur3_2026!", # historic default admin pass
            "L1stM0nk_db_5ecur3_2026!" # listmonk fallback db pass
        }
        
        errors = []
        
        # Check required credentials
        required_vars = {
            "RAPIDAPI_KEY": cls.RAPIDAPI_KEY,
            "TELEGRAM_BOT_TOKEN": cls.TELEGRAM_BOT_TOKEN,
            "LISTMONK_PASSWORD": cls.LISTMONK_PASSWORD,
            "LISTMONK_DB_PASSWORD": cls.LISTMONK_DB_PASSWORD,
            "LISTMONK_ADMIN_PASSWORD": cls.LISTMONK_ADMIN_PASSWORD,
        }
        
        for name, value in required_vars.items():
            if not value:
                errors.append(f"Required environment variable '{name}' is missing or empty.")
            elif value in COMPROMISED_SECRETS:
                errors.append(f"Environment variable '{name}' uses a compromised/exposed historic secret.")
            elif any(placeholder in str(value).lower() for placeholder in ["your_telegram_bot_token", "your_rapidapi_key", "your_product_id", "placeholder"]):
                errors.append(f"Environment variable '{name}' contains a template placeholder: '{value}'")
        
        # Check optional but critical if provided
        optional_vars = {
            "SAFARICOM_DARAJA_CONSUMER_KEY": cls.SAFARICOM_DARAJA_CONSUMER_KEY,
            "SAFARICOM_DARAJA_CONSUMER_SECRET": cls.SAFARICOM_DARAJA_CONSUMER_SECRET,
            "CRYPTOPAY_API_KEY": cls.CRYPTOPAY_API_KEY,
        }
        
        for name, value in optional_vars.items():
            if value:
                if value in COMPROMISED_SECRETS:
                    errors.append(f"Optional environment variable '{name}' uses a compromised/exposed historic secret.")
                elif any(placeholder in str(value).lower() for placeholder in ["your_", "placeholder"]):
                    errors.append(f"Optional environment variable '{name}' contains a template placeholder: '{value}'")
                    
        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f" - {err}" for err in errors))

