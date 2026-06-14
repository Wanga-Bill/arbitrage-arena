import os
import sys
import json
import sqlite3
import hmac
import hashlib
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# Add workspace directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config
import components.payments.payment_engine as payment_engine

logging.basicConfig(level=logging.INFO)

PORT = 8080

class PaymentWebhookHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Override to suppress standard http.server stdout logging
        return

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        path = self.path
        logging.info(f"Received webhook POST on: {path}")
        
        if path == "/webhook/mpesa":
            self.handle_mpesa_callback(body)
        elif path == "/webhook/cryptopay":
            self.handle_cryptopay_callback(body)
        else:
            self.send_response(404)
            self.end_headers()

    def handle_mpesa_callback(self, body):
        try:
            payload = json.loads(body.decode('utf-8'))
            logging.info(f"M-Pesa STK Callback Payload: {json.dumps(payload)}")
            
            stk_callback = payload.get("Body", {}).get("stkCallback", {})
            req_id = stk_callback.get("MerchantRequestID")
            res_code = stk_callback.get("ResultCode")
            
            if res_code == 0:
                logging.info(f"M-Pesa payment SUCCESS for transaction {req_id}")
                payment_engine.complete_payment(req_id)
            else:
                logging.warning(f"M-Pesa payment FAILED / CANCELLED for transaction {req_id}. ResultCode: {res_code}")
                payment_engine.fail_payment(req_id)
                
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ResultCode": 0, "ResultDesc": "Success"}).encode())
        except Exception as e:
            logging.error(f"Error handling M-Pesa webhook callback: {e}")
            self.send_response(500)
            self.end_headers()

    def handle_cryptopay_callback(self, body):
        try:
            signature = self.headers.get("Crypto-Pay-API-Signature")
            secret = Config.CRYPTOPAY_WEBHOOK_SECRET or Config.CRYPTOPAY_API_KEY or "MOCK_SECRET"
            
            # Signature Verification
            secret_hash = hashlib.sha256(secret.encode()).digest()
            calculated = hmac.new(secret_hash, body, hashlib.sha256).hexdigest()
            
            # Skip signature verification if using mock key
            if secret != "MOCK_SECRET" and not hmac.compare_digest(calculated, signature or ""):
                logging.warning("CryptoPay Webhook Signature verification failed!")
                self.send_response(401)
                self.end_headers()
                return
                
            payload = json.loads(body.decode('utf-8'))
            logging.info(f"CryptoPay Callback Verified: {json.dumps(payload)}")
            
            update_type = payload.get("update_type")
            invoice_data = payload.get("payload", {})
            invoice_id = str(invoice_data.get("invoice_id"))
            status = invoice_data.get("status")
            
            if update_type == "invoice_paid" and status == "paid":
                logging.info(f"CryptoPay payment SUCCESS for invoice {invoice_id}")
                payment_engine.complete_payment(invoice_id)
            elif status in ["expired", "failed"]:
                logging.info(f"CryptoPay payment {status.upper()} for invoice {invoice_id}")
                payment_engine.fail_payment(invoice_id)
                
            self.send_response(200)
            self.end_headers()
        except Exception as e:
            logging.error(f"Error handling CryptoPay webhook callback: {e}")
            self.send_response(500)
            self.end_headers()

def run_webhook_server():
    server = HTTPServer(('0.0.0.0', PORT), PaymentWebhookHandler)
    logging.info(f"Payment Webhook Listener running on port {PORT}...")
    server.serve_forever()

def handle_telegram_updates():
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        logging.error("TELEGRAM_BOT_TOKEN missing. Bot command listener disabled.")
        return
        
    logging.info("Starting Telegram Bot updates polling command listener...")
    offset = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url, timeout=35)
            if response.status_code == 200:
                res_json = response.json()
                if res_json.get("ok"):
                    for update in res_json.get("result", []):
                        offset = update["update_id"] + 1
                        process_single_update(update)
            else:
                logging.error(f"getUpdates API failed: {response.text}")
                time.sleep(5)
        except Exception as e:
            logging.error(f"Error polling bot updates: {e}")
            time.sleep(5)

def process_single_update(update):
    bot_token = Config.TELEGRAM_BOT_TOKEN
    
    # 1. Handle command /start or /pay messages
    if "message" in update:
        msg = update["message"]
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()
        
        if not text or not chat_id:
            return
            
        if text.startswith("/start"):
            welcome_text = (
                "👋 *Welcome to Arbitrage Arena Billing Gateway!* 👋\n\n"
                "Get instant access to the VIP Premium World Cup alerts channel using our open-source gateways:\n\n"
                "💰 *Available Plans:*\n"
                "• *Weekly Pass*: $14.99 (KES 2,000)\n"
                "• *Monthly Pass*: $29.99 (KES 4,000)\n\n"
                "🛒 *To Pay, use the `/pay` command followed by parameters:*\n"
                "• *M-Pesa STK Push (Kenya)*:\n"
                "  `/pay mpesa <amount_in_kes> <phone_number>`\n"
                "  _Example:_ `/pay mpesa 2000 0712345678`\n\n"
                "• *Traditional Cards / PayPal (Global)*:\n"
                "  `/pay card <amount_in_usd> <currency>`\n"
                "  _Example:_ `/pay card 14.99 USD`\n\n"
                "• *Cryptocurrencies (USDT, TON, BTC)*:\n"
                "  `/pay crypto <amount_in_usd> <asset>`\n"
                "  _Example:_ `/pay crypto 14.99 USDT`"
            )
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                "chat_id": chat_id,
                "text": welcome_text,
                "parse_mode": "Markdown"
            }, timeout=10)
            
        elif text.startswith("/pay"):
            parts = text.split()
            if len(parts) < 4:
                err_text = "⚠️ *Invalid Format!*\nUse: `/pay <method> <amount> <currency_or_phone_or_asset>`"
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": err_text,
                    "parse_mode": "Markdown"
                }, timeout=10)
                return
                
            gateway = parts[1].lower()
            try:
                amount = float(parts[2])
            except ValueError:
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "⚠️ *Amount must be a number!*"
                }, timeout=10)
                return
                
            param = parts[3]
            
            if gateway == "mpesa":
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"⏳ *Triggering M-Pesa STK Push of KES {int(amount)} to phone {param}...*"
                }, timeout=10)
                res = payment_engine.trigger_mpesa_stk_push(param, amount, chat_id)
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"📲 *M-Pesa Callback response:* {res.get('CustomerMessage')}"
                }, timeout=10)
                
            elif gateway == "card":
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"⏳ *Generating Credit Card Invoice for {amount:.2f} {param.upper()}...*"
                }, timeout=10)
                success = payment_engine.send_telegram_invoice(chat_id, amount, param)
                if not success:
                    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "⚠️ *Invoice generation failed.* Contact support."
                    }, timeout=10)
                    
            elif gateway == "crypto":
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"⏳ *Creating CryptoPay invoice for {amount:.2f} {param.upper()}...*"
                }, timeout=10)
                pay_url = payment_engine.generate_cryptopay_invoice(amount, param, chat_id)
                msg_text = (
                    "🪙 *CRYPTOPAY INVOICE CREATED!* 🪙\n\n"
                    f"Please click the link below to complete payment via CryptoBot:\n"
                    f"🔗 [Pay with CryptoBot Here]({pay_url})"
                )
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": msg_text,
                    "parse_mode": "Markdown"
                }, timeout=10)
                
            else:
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"⚠️ *Unknown gateway*: `{gateway}`. Choose `mpesa`, `card`, or `crypto`."
                }, timeout=10)

        elif text.startswith("/mockpay"):
            # A developer shortcut command to mock pay/complete credit card invoices
            parts = text.split()
            if len(parts) < 2:
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "⚠️ Format: `/mockpay <invoice_id>`"
                }, timeout=10)
                return
            inv_id = parts[1]
            success = payment_engine.complete_payment(inv_id)
            if success:
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"✅ Mock payment completed successfully for {inv_id}"
                }, timeout=10)
            else:
                requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"❌ Failed to mock payment for {inv_id}. Invoice not found?"
                }, timeout=10)

    # 2. Handle Telegram Pre-Checkout Handshake (Required for Bot Payments)
    elif "pre_checkout_query" in update:
        query = update["pre_checkout_query"]
        query_id = query["id"]
        
        logging.info(f"Answering Pre-Checkout Query Handshake: {query_id}")
        url = f"https://api.telegram.org/bot{bot_token}/answerPreCheckoutQuery"
        payload = {
            "pre_checkout_query_id": query_id,
            "ok": True
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Error answering pre-checkout query: {e}")

def main():
    # Start Webhook listener thread
    webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
    webhook_thread.start()
    
    # Start Bot Updates long-polling loop
    handle_telegram_updates()

if __name__ == "__main__":
    main()
