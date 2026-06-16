import os
import sys
import json
import sqlite3
import base64
import logging
from datetime import datetime
import requests

# Add workspace directory to path if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config

logging.basicConfig(level=logging.INFO)

DB_PATH = "database.db"

def normalize_phone(phone: str) -> str:
    """
    Normalizes Kenyan phone numbers to the Safaricom Daraja format: 2547XXXXXXXX or 2541XXXXXXXX.
    Accepts formats: +254..., 254..., 07..., 01..., 7...
    """
    cleaned = "".join(c for c in phone if c.isdigit())
    if cleaned.startswith("07"):
        return "2547" + cleaned[2:]
    elif cleaned.startswith("01"):
        return "2541" + cleaned[2:]
    elif cleaned.startswith("254"):
        return cleaned
    elif len(cleaned) == 9 and (cleaned.startswith("7") or cleaned.startswith("1")):
        return "254" + cleaned
    return cleaned

def log_transaction(invoice_id: str, tg_user_id: int, amount: float, currency: str, gateway: str, status: str = "pending"):
    """Inserts or updates a transaction in the billing ledger database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO billing_ledger (invoice_id, tg_user_id, amount, currency, gateway, status) VALUES (?, ?, ?, ?, ?, ?)",
            (invoice_id, tg_user_id, amount, currency, gateway, status)
        )
        conn.commit()
        conn.close()
        logging.info(f"Billing ledger updated: {invoice_id} ({gateway}) -> {status}")
    except Exception as e:
        logging.error(f"Error logging transaction in database: {e}")

def get_daraja_auth_token() -> str:
    """Fetches Safaricom Daraja OAuth Access Token."""
    consumer_key = Config.SAFARICOM_DARAJA_CONSUMER_KEY or "MOCK_CONSUMER_KEY"
    consumer_secret = Config.SAFARICOM_DARAJA_CONSUMER_SECRET or "MOCK_CONSUMER_SECRET"
    
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    auth_str = f"{consumer_key}:{consumer_secret}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {"Authorization": f"Basic {encoded_auth}"}
    try:
        # If in mock mode or values are placeholder
        if "MOCK" in auth_str or not Config.SAFARICOM_DARAJA_CONSUMER_KEY:
            return "MOCK_ACCESS_TOKEN"
            
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            logging.error(f"Daraja OAuth failed: {response.text}")
    except Exception as e:
        logging.error(f"Error fetching Daraja token: {e}")
    return "MOCK_ACCESS_TOKEN"

def trigger_mpesa_stk_push(phone: str, amount: float, tg_user_id: int) -> dict:
    """Triggers M-Pesa STK Push request."""
    normalized = normalize_phone(phone)
    token = get_daraja_auth_token()
    
    shortcode = Config.SAFARICOM_SHORTCODE or "174379"
    passkey = Config.SAFARICOM_PASSKEY or "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
    callback_url = Config.SAFARICOM_CALLBACK_URL or "https://mock.sandbox.safaricom.co.ke/webhook/mpesa"
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()
    
    url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": normalized,
        "PartyB": shortcode,
        "PhoneNumber": normalized,
        "CallBackURL": callback_url,
        "AccountReference": "ArbitrageArenaVIP",
        "TransactionDesc": "VIP Access Subscription"
    }
    
    try:
        if token == "MOCK_ACCESS_TOKEN":
            # Return simulated STK push success
            mock_id = f"MPESA_{timestamp}_{tg_user_id}"
            log_transaction(mock_id, tg_user_id, amount, "KES", "mpesa", "pending")
            return {"MerchantRequestID": mock_id, "ResponseCode": "0", "CustomerMessage": "STK Push Mock Triggered Successfully"}
            
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        res_json = response.json()
        if response.status_code == 200 and res_json.get("ResponseCode") == "0":
            req_id = res_json.get("MerchantRequestID")
            log_transaction(req_id, tg_user_id, amount, "KES", "mpesa", "pending")
            return res_json
        else:
            logging.error(f"M-Pesa STK Push failed: {response.text}")
            return {"ResponseCode": "1", "CustomerMessage": "Daraja STK push failed"}
    except Exception as e:
        logging.error(f"Error triggering STK push: {e}")
        return {"ResponseCode": "1", "CustomerMessage": str(e)}

def send_telegram_invoice(chat_id: int, amount: float, currency: str) -> bool:
    """Fires a Telegram Bot sendInvoice call (using native Card payments)."""
    token = Config.TELEGRAM_BOT_TOKEN
    provider_token = Config.TELEGRAM_PAYMENT_PROVIDER_TOKEN or "MOCK_PROVIDER_TOKEN"
    
    if not token:
        logging.error("TELEGRAM_BOT_TOKEN missing in Config")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendInvoice"
    
    # Decimal conversion rule (e.g. USD requires amount in cents)
    cents_multiplier = 100
    if currency.upper() in ["JPY", "KRW"]:
        cents_multiplier = 1 # Zero-decimal currencies
        
    invoice_cents = int(amount * cents_multiplier)
    
    # Generate unique invoice ID
    invoice_id = f"INV_{chat_id}_{int(datetime.now().timestamp())}"
    
    payload = {
        "chat_id": chat_id,
        "title": "VIP Live Arbitrage Pass",
        "description": "Continuous access to Whale Vault and High-Yield live arbitrage feeds.",
        "payload": invoice_id,
        "provider_token": provider_token,
        "currency": currency.upper(),
        "prices": json.dumps([{"label": "VIP Pass", "amount": invoice_cents}])
    }
    
    try:
        # If mock provider, return true and log
        if provider_token == "MOCK_PROVIDER_TOKEN":
            log_transaction(invoice_id, chat_id, amount, currency, "card", "pending")
            # Simulating sending invoice to the channel/chat
            url_msg = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url_msg, json={
                "chat_id": chat_id,
                "text": f"💳 *[MOCK INVOICE]* 💳\n\n*Amount*: {amount:.2f} {currency.upper()}\n*Gateway*: Telegram Payments (Stripe)\n\nType `/mockpay {invoice_id}` to complete purchase."
            }, timeout=10)
            return True
            
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            log_transaction(invoice_id, chat_id, amount, currency, "card", "pending")
            return True
        else:
            logging.error(f"Telegram sendInvoice failed: {response.text}")
    except Exception as e:
        logging.error(f"Error sending Telegram invoice: {e}")
    return False

def generate_cryptopay_invoice(amount: float, asset: str, tg_user_id: int) -> str:
    """Generates a cryptocurrency invoice via CryptoPay API (@CryptoBot)."""
    api_key = Config.CRYPTOPAY_API_KEY or "MOCK_CRYPTOPAY_API_KEY"
    
    # Sandbox/Testnet vs Mainnet URL
    url = "https://testnet-pay.cryptoboot.org/api/createInvoice"
    if Config.CRYPTOPAY_API_KEY and not Config.CRYPTOPAY_API_KEY.startswith("test-"):
        url = "https://pay.cryptoboot.org/api/createInvoice"
        
    headers = {
        "Crypto-Pay-API-Token": api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "asset": asset.upper(),
        "amount": str(amount),
        "description": "VIP Live Arbitrage Pass Subscription",
        "payload": str(tg_user_id)
    }
    
    try:
        if api_key == "MOCK_CRYPTOPAY_API_KEY":
            invoice_id = f"CRYPTO_{tg_user_id}_{int(datetime.now().timestamp())}"
            log_transaction(invoice_id, tg_user_id, amount, asset, "crypto", "pending")
            return f"https://t.me/CryptoBot?start=mock_{invoice_id}"
            
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        res_json = response.json()
        if response.status_code == 200 and res_json.get("ok"):
            result = res_json.get("result", {})
            invoice_id = str(result.get("invoice_id"))
            pay_url = result.get("pay_url")
            log_transaction(invoice_id, tg_user_id, amount, asset, "crypto", "pending")
            return pay_url
        else:
            logging.error(f"CryptoPay invoice generation failed: {response.text}")
    except Exception as e:
        logging.error(f"Error generating CryptoPay invoice: {e}")
    return f"https://t.me/CryptoBot?start=err_{tg_user_id}"

def complete_payment(invoice_id: str) -> bool:
    """Marks payment as completed and sends a unique VIP invite link to the user."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT tg_user_id, amount, currency, gateway FROM billing_ledger WHERE invoice_id=?", (invoice_id,))
        row = cursor.fetchone()
        
        if not row:
            logging.error(f"No transaction found for invoice: {invoice_id}")
            conn.close()
            return False
            
        tg_user_id, amount, currency, gateway = row
        cursor.execute("UPDATE billing_ledger SET status='completed' WHERE invoice_id=?", (invoice_id,))
        conn.commit()
        conn.close()
        
        logging.info(f"Payment SUCCESS: User {tg_user_id} paid {amount:.2f} {currency} via {gateway}")
        
        # Generate Invite Link for VIP Premium Channel
        bot_token = Config.TELEGRAM_BOT_TOKEN
        premium_channel = Config.PREMIUM_CHANNEL_ID
        
        if not bot_token or not premium_channel:
            logging.error("Telegram token or Premium channel ID not configured. Cannot generate invite link.")
            return False
            
        url = f"https://api.telegram.org/bot{bot_token}/createChatInviteLink"
        payload = {
            "chat_id": premium_channel,
            "member_limit": 1,
            "expire_date": int(datetime.now().timestamp()) + 86400 * 7 # link valid for 7 days
        }
        
        invite_link = "https://t.me/joinchat/mock_premium_invite_link"
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("ok"):
                    invite_link = res_json.get("result", {}).get("invite_link")
                else:
                    logging.error(f"Telegram createChatInviteLink returned error: {res_json.get('description')}")
            else:
                logging.error(f"Telegram createChatInviteLink HTTP error {resp.status_code}: {resp.text}")
        except Exception as invite_err:
            logging.error(f"Error generating invite link: {invite_err}")
            
        # Send invite link to the user
        url_msg = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        msg_payload = {
            "chat_id": tg_user_id,
            "text": (
                "🎉 *PAYMENT VERIFIED SUCCESSFULLY!* 🎉\n\n"
                f"Thank you for subscribing to the *VIP Live Arbitrage Pass*.\n"
                f"Amount: {amount:.2f} {currency}\n"
                f"Gateway: {gateway.upper()}\n\n"
                f"👇 *Click the link below to join the VIP Channel:* \n"
                f"🔗 [Join VIP Premium Feed Here]({invite_link})\n\n"
                "_*Note*: This invite link is single-use and will expire in 7 days._"
            ),
            "parse_mode": "Markdown"
        }
        requests.post(url_msg, json=msg_payload, timeout=10)
        return True
    except Exception as e:
        logging.error(f"Error completing payment: {e}")
        return False

def fail_payment(invoice_id: str):
    """Marks a payment as failed."""
    log_transaction(invoice_id, 0, 0.0, "", "", "failed")
