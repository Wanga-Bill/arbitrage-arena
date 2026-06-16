import asyncio
import os
import json
import logging
import time
from datetime import datetime, timezone
import requests
from requests.auth import HTTPBasicAuth
from web3 import Web3
from dotenv import load_dotenv

# Load workspace configurations
workspace_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(workspace_dir, ".env"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Web3Watcher] - %(levelname)s - %(message)s'
)

# RPC and contract configs
RPC_URL = os.getenv("WEB3_PROVIDER_RPC_URL", "http://localhost:8545")
CONTRACT_ADDRESS_RAW = os.getenv("CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000")

# Setup Web3 Connection
w3 = None
if RPC_URL:
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        logging.info(f"Web3 connection initialized on RPC: {RPC_URL}")
    except Exception as init_err:
        logging.error(f"Failed to connect to RPC endpoint: {init_err}")

CONTRACT_ADDRESS = None
if w3 and CONTRACT_ADDRESS_RAW and CONTRACT_ADDRESS_RAW != "0x0000000000000000000000000000000000000000":
    try:
        CONTRACT_ADDRESS = w3.to_checksum_address(CONTRACT_ADDRESS_RAW)
        logging.info(f"Contract target checksum set to: {CONTRACT_ADDRESS}")
    except Exception as addr_err:
        logging.error(f"Invalid Contract address configuration: {addr_err}")

# Minimal ABI containing the SubscriptionPurchased event and isMemberValid function
ABI = json.loads('''[
  {
    "anonymous": false,
    "inputs": [
      {
        "indexed": true,
        "internalType": "address",
        "name": "user",
        "type": "address"
      },
      {
        "indexed": false,
        "internalType": "uint256",
        "name": "expirationTime",
        "type": "uint256"
      },
      {
        "indexed": false,
        "internalType": "uint256",
        "name": "amountPaid",
        "type": "uint256"
      }
    ],
    "name": "SubscriptionPurchased",
    "type": "event"
  },
  {
    "inputs": [
      {
        "internalType": "address",
        "name": "_user",
        "type": "address"
      }
    ],
    "name": "isMemberValid",
    "outputs": [
      {
        "internalType": "bool",
        "name": "",
        "type": "bool"
      }
    ],
    "stateMutability": "view",
    "type": "function"
  }
]''')

contract = None
if w3 and CONTRACT_ADDRESS:
    try:
        contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)
    except Exception as contract_err:
        logging.error(f"Failed to initialize contract bindings: {contract_err}")

def listmonk_sync_wallet_target(user_address: str, expiry_timestamp: int):
    """Integrates with Listmonk API to register/enable users using wallet email mockups."""
    email = f"{user_address.lower()}@arbitragearena.io"
    name = f"Wallet {user_address[:6]}...{user_address[-4:]}"
    
    listmonk_url = os.getenv("LISTMONK_API_URL", "http://localhost:9000/api")
    username = os.getenv("LISTMONK_USERNAME", "api_agent")
    password = os.getenv("LISTMONK_PASSWORD")
    list_id = os.getenv("LISTMONK_CAMPAIGN_LIST_ID", "1")
    
    if not (listmonk_url and username and password):
        logging.warning("Listmonk configuration missing in environment. Sync skipped.")
        return
        
    url = f"{listmonk_url}/subscribers"
    
    # Check if subscription is valid/active
    is_active = expiry_timestamp > time.time()
    status = "enabled" if is_active else "disabled"
    
    # ISO formatted expiration date for attributes
    expiry_date = datetime.fromtimestamp(expiry_timestamp, tz=timezone.utc).isoformat()
    
    payload = {
        "email": email,
        "name": name,
        "status": status,
        "lists": [int(list_id)],
        "attribs": {
            "wallet_address": user_address,
            "expires_at": expiry_date,
            "source": "web3_contract"
        }
    }
    
    try:
        resp = requests.post(url, json=payload, auth=HTTPBasicAuth(username, password), timeout=10)
        if resp.status_code in [200, 201]:
            logging.info(f"Successfully synced Web3 subscriber {email} to Listmonk. Status: {status}")
            # Dispatch welcome email if enabled
            if is_active:
                trigger_welcome_email(email)
        elif resp.status_code == 409:
            logging.info(f"Subscriber {email} already exists. Querying and updating via PUT...")
            # Query Listmonk to find the subscriber's ID
            search_url = f"{listmonk_url}/subscribers?query=subscribers.email='{email}'"
            search_resp = requests.get(search_url, auth=HTTPBasicAuth(username, password), timeout=10)
            if search_resp.status_code == 200:
                results = search_resp.json().get("data", {}).get("results", [])
                if results:
                    sub_id = results[0]["id"]
                    # PUT update
                    update_url = f"{listmonk_url}/subscribers/{sub_id}"
                    update_payload = {
                        "email": email,
                        "name": name,
                        "status": status,
                        "lists": [int(list_id)],
                        "attribs": {
                            "wallet_address": user_address,
                            "expires_at": expiry_date,
                            "source": "web3_contract"
                        }
                    }
                    put_resp = requests.put(update_url, json=update_payload, auth=HTTPBasicAuth(username, password), timeout=10)
                    if put_resp.status_code == 200:
                        logging.info(f"Successfully updated subscriber {email} in Listmonk. Status: {status}")
                        # If subscription was renewed from disabled/unsubscribed, trigger welcome email
                        if is_active and results[0].get("status") != "enabled":
                            trigger_welcome_email(email)
                    else:
                        logging.warning(f"Failed to update subscriber {email} via PUT: {put_resp.status_code} - {put_resp.text}")
            else:
                logging.warning(f"Failed to query existing subscriber {email}: {search_resp.status_code}")
        else:
            logging.warning(f"Failed to sync subscriber to Listmonk: {resp.status_code} - {resp.text}")
    except Exception as e:
        logging.error(f"Error executing Listmonk API sync: {e}")

def trigger_welcome_email(recipient_email: str):
    """Dispatches onboarding transactional notifications upon active block confirmations."""
    listmonk_url = os.getenv("LISTMONK_API_URL", "http://localhost:9000/api")
    username = os.getenv("LISTMONK_USERNAME", "api_agent")
    password = os.getenv("LISTMONK_PASSWORD")
    
    tx_endpoint = f"{listmonk_url}/tx"
    payload = {
        "template_id": 3,
        "subscriber_email": recipient_email,
        "subscriber_mode": "fallback",
        "subject": "🚨 [Access Granted] Welcome to Arbitrage Arena VIP",
        "data": {
            "message": "<h1>Your Premium Web3 Signal Feed is Active!</h1><p>Our decentralized watcher node has verified your on-chain subscription. Expect real-time sports market anomalies directly in your inbox.</p>"
        },
        "content_type": "html"
    }
    try:
        resp = requests.post(tx_endpoint, json=payload, auth=HTTPBasicAuth(username, password), timeout=10)
        logging.info(f"Web3 welcome email dispatch status: {resp.status_code}")
    except Exception as e:
        logging.error(f"Failed to send welcome email to {recipient_email}: {e}")

async def check_expirations_loop(poll_interval: int = 60):
    """Periodically scans for expired subscriptions in Listmonk and revokes VIP entitlements."""
    logging.info("Autonomous Web3 expiration cleanup task initialized.")
    while True:
        try:
            listmonk_url = os.getenv("LISTMONK_API_URL", "http://localhost:9000/api")
            username = os.getenv("LISTMONK_USERNAME", "api_agent")
            password = os.getenv("LISTMONK_PASSWORD")
            list_id = os.getenv("LISTMONK_CAMPAIGN_LIST_ID", "1")
            
            if listmonk_url and username and password:
                # Retrieve all subscribers belonging to our VIP alert list
                url = f"{listmonk_url}/subscribers?list_id={list_id}&per_page=all"
                resp = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=10)
                if resp.status_code == 200:
                    subscribers = resp.json().get("data", {}).get("results", [])
                    now_utc = datetime.now(timezone.utc)
                    
                    for sub in subscribers:
                        attribs = sub.get("attribs", {})
                        expires_at_str = attribs.get("expires_at")
                        wallet_address = attribs.get("wallet_address")
                        
                        if expires_at_str and wallet_address:
                            try:
                                # Parse ISO formatted timestamp
                                expires_at = datetime.fromisoformat(expires_at_str)
                                if expires_at < now_utc and sub.get("status") == "enabled":
                                    logging.info(f"🔒 SUBSCRIPTION EXPIRED: Revoking VIP access for {sub.get('email')}")
                                    # Disable subscriber list status
                                    update_url = f"{listmonk_url}/subscribers/{sub.get('id')}"
                                    update_payload = {
                                        "status": "disabled"
                                    }
                                    requests.put(update_url, json=update_payload, auth=HTTPBasicAuth(username, password), timeout=5)
                            except Exception as parse_err:
                                logging.error(f"Error parsing date format for subscriber {sub.get('id')}: {parse_err}")
        except Exception as e:
            logging.error(f"Error checking expirations loop: {e}")
            
        await asyncio.sleep(poll_interval)

async def log_loop(event_filter, poll_interval: int = 2):
    """Asynchronously polls the RPC filter for new blockchain subscription events."""
    logging.info("Listening for SubscriptionPurchased events on-chain...")
    while True:
        try:
            for event in event_filter.get_new_entries():
                user_address = event['args']['user']
                expiry_timestamp = event['args']['expirationTime']
                amount_paid = event['args']['amountPaid']
                
                logging.info(f"💥 WEB3 PAYMENT CONFIRMED: User {user_address} paid {amount_paid} USDC/USDT. Access valid until {expiry_timestamp}")
                listmonk_sync_wallet_target(user_address, expiry_timestamp)
        except Exception as poll_err:
            logging.error(f"Error polling logs from filter: {poll_err}")
            
        await asyncio.sleep(poll_interval)

async def main():
    if not w3 or not contract:
        logging.error("Web3 provider or contract configurations are uninitialized. Check .env variables.")
        # Start only the expiration cleanup loop if RPC is unconfigured to keep local test systems running
        await check_expirations_loop(60)
        return

    logging.info("Initializing event filters...")
    try:
        event_filter = contract.events.SubscriptionPurchased.create_filter(fromBlock='latest')
        await asyncio.gather(
            log_loop(event_filter, 2),
            check_expirations_loop(60)
        )
    except Exception as e:
        logging.error(f"Error launching Web3 event monitoring loops: {e}. Falling back to check loop.")
        await check_expirations_loop(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Watcher daemon terminated by user.")
