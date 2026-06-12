import requests
import logging

from config import Config

logging.basicConfig(level=logging.INFO)

def send_telegram_alert(message: str, is_premium: bool = False):
    token = Config.TELEGRAM_BOT_TOKEN
    channel_id = Config.PREMIUM_CHANNEL_ID if is_premium else Config.FREE_CHANNEL_ID
    
    if not token or not channel_id:
        logging.error("Telegram Token or Channel ID missing from Configuration.")
        return False

    # FIX: Corrected API pathing format
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logging.info(f"Alert successfully dispatched to {'Premium' if is_premium else 'Free'} Channel.")
            return True
        else:
            logging.error(f"Telegram API Error: {response.text}")
            return False
    except Exception as e:
        logging.error(f"Failed to transmit Telegram alert: {str(e)}")
        return False
