import os
import sys
import sqlite3
import json
import requests
import time

# Add components path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "payments"))
import payment_engine

def print_ledger_status(invoice_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT invoice_id, tg_user_id, amount, gateway, status FROM billing_ledger WHERE invoice_id=?", (invoice_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        print(f"   [Ledger Record] Invoice: {row[0]} | User: {row[1]} | Amount: {row[2]} | Gateway: {row[3]} | Status: {row[4]}")
    else:
        print("   [Ledger Record] No record found in database.")

def run_demo():
    print("==================================================")
    print("   SOVEREIGN BILLING & PAYMENT GATEWAY DEMO")
    print("==================================================")
    
    tg_user_id = 987654321
    phone_number = "0712345678"
    amount = 2000.0  # KES 2,000 for Weekly VIP Pass
    
    # Step 1: Simulate the user triggering a payment (M-Pesa STK Push)
    print("\n1. [User Interaction] User requests M-Pesa payment...")
    response = payment_engine.trigger_mpesa_stk_push(phone_number, amount, tg_user_id)
    merchant_request_id = response.get("MerchantRequestID")
    print(f"   STK Push Response Message: {response.get('CustomerMessage')}")
    print(f"   MerchantRequestID (Invoice ID): {merchant_request_id}")
    
    # Step 2: Verify it is logged as 'pending' in the database ledger
    print("\n2. [Database Validation] Checking ledger status immediately after trigger...")
    print_ledger_status(merchant_request_id)
    
    # Step 3: Simulate the Safaricom callback webhook arriving at FastAPI
    print("\n3. [Webhook Simulation] Simulating successful payment webhook arriving from Safaricom...")
    webhook_url = "http://localhost:8000/webhook/mpesa"
    callback_payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": merchant_request_id,
                "CheckoutRequestID": "ws_CO_16062026_1234",
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": amount},
                        {"Name": "MpesaReceiptNumber", "Value": "QFG1234567"},
                        {"Name": "TransactionDate", "Value": 20260616120000},
                        {"Name": "PhoneNumber", "Value": 254712345678}
                    ]
                }
            }
        }
    }
    
    try:
        resp = requests.post(webhook_url, json=callback_payload, timeout=10)
        print(f"   Webhook Endpoint HTTP Status: {resp.status_code}")
        print(f"   Webhook Endpoint Response Payload: {resp.text}")
    except Exception as e:
        print(f"   Error sending webhook post: {e}")
        return
        
    # Step 4: Verify that the ledger status is now updated to 'completed'
    print("\n4. [Database Validation] Checking ledger status after webhook execution...")
    print_ledger_status(merchant_request_id)
    
    print("\n==================================================")
    print("   DEMO COMPLETED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_demo()
