import os
import sys
import logging
import requests
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load environment variables from .env if present
load_dotenv()

try:
    from config import Config
    # Run the safety/security validation checks on configuration parameters
    Config.validate(component="dns")
except ValueError as e:
    logging.error(f"Configuration validation failed:\n{e}")
    sys.exit(1)
except ImportError:
    logging.error("Could not import Config from config.py.")
    sys.exit(1)

# API parameters
VPS_IP = Config.VPS_IP
PDNS_API_KEY = Config.PDNS_API_KEY
DOMAIN = "arbitragearena.io."  # Trailing dot is required for canonical DNS zones

PDNS_API_URL = f"http://{VPS_IP}:8081/api/v1/servers/localhost"

HEADERS = {
    "X-API-Key": PDNS_API_KEY,
    "Content-Type": "application/json"
}

def create_zone():
    """Creates the master DNS zone for your domain."""
    payload = {
        "name": DOMAIN,
        "kind": "Native",
        "nameservers": [f"ns1.{DOMAIN}", f"ns2.{DOMAIN}"]
    }
    try:
        response = requests.post(f"{PDNS_API_URL}/zones", headers=HEADERS, json=payload, timeout=10)
        if response.status_code == 201:
            logging.info(f"✅ Zone {DOMAIN} created successfully.")
        elif response.status_code in (409, 422) and "already exists" in response.text.lower():
            logging.info(f"ℹ️ Zone {DOMAIN} already exists. Proceeding...")
        else:
            logging.error(f"Failed to create zone (HTTP {response.status_code}): {response.text}")
    except requests.RequestException as e:
        logging.error(f"Network error while creating zone: {e}")

def add_a_record(subdomain, target_ip):
    """Routes a specific subdomain (or root) to an IP address using REPLACE changetype."""
    record_name = f"{subdomain}.{DOMAIN}" if subdomain != "@" else DOMAIN
    
    payload = {
        "rrsets": [
            {
                "name": record_name,
                "type": "A",
                "ttl": 300,
                "changetype": "REPLACE",
                "records": [{"content": target_ip, "disabled": False}]
            }
        ]
    }
    
    try:
        response = requests.patch(f"{PDNS_API_URL}/zones/{DOMAIN}", headers=HEADERS, json=payload, timeout=10)
        if response.status_code == 204:
            logging.info(f"✅ A Record set: {record_name} -> {target_ip}")
        else:
            logging.error(f"Failed to set A record for {record_name} (HTTP {response.status_code}): {response.text}")
    except requests.RequestException as e:
        logging.error(f"Network error while setting A record: {e}")

if __name__ == "__main__":
    logging.info("Initializing Sovereign DNS Routing...")
    create_zone()
    
    # Route the root domain
    add_a_record("@", VPS_IP)
    # Route the www subdomain
    add_a_record("www", VPS_IP)
    # Route nameservers back to VPS
    add_a_record("ns1", VPS_IP)
    add_a_record("ns2", VPS_IP)
