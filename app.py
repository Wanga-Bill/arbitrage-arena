import os
import sys
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
import requests
from requests.auth import HTTPBasicAuth
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env variables from workspace root
workspace_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(workspace_dir, ".env"))
from config import Config

app = FastAPI(title="Arbitrage Arena Web Engine")

# Extract configurations
LISTMONK_URL = os.getenv("LISTMONK_API_URL", "http://localhost:9000/api")
LISTMONK_USER = os.getenv("LISTMONK_USERNAME", "api_agent")
LISTMONK_PASS = os.getenv("LISTMONK_PASSWORD")

class SubscribeRequest(BaseModel):
    email: str
    frequency: int = 3

@app.post("/api/subscribe")
async def api_subscribe(req: SubscribeRequest):
    """
    Subscribes a user from the landing page waitlist form.
    Saves the user locally in SQLite and synchronizes them to Listmonk.
    """
    email = req.email.strip().lower()
    frequency = req.frequency
    
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address.")
        
    try:
        # Save subscriber to SQLite billing/gateway database
        db_path = os.path.join(workspace_dir, "database.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                email TEXT PRIMARY KEY,
                frequency INTEGER DEFAULT 3,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("INSERT OR REPLACE INTO subscribers (email, frequency) VALUES (?, ?)", (email, frequency))
        conn.commit()
        conn.close()
        
        print(f"[API] New subscription added: {email} (Frequency: {frequency}h)")
        
        # Also subscribe to Listmonk if configured
        list_id = os.getenv("LISTMONK_CAMPAIGN_LIST_ID", "1")
        
        if LISTMONK_URL and LISTMONK_USER and LISTMONK_PASS:
            url = f"{LISTMONK_URL}/subscribers"
            freq_map = {
                3: "🌶️ Spicy Mode (Every 3 hours)",
                24: "⚡ Daily Digest (Every 24 hours)",
                168: "🐢 Boomer Mode (Once a week)"
            }
            freq_str = freq_map.get(frequency, f"{frequency} hours")
            
            payload = {
                "email": email,
                "name": email.split("@")[0].capitalize(),
                "status": "enabled",
                "lists": [int(list_id)],
                "attribs": {
                    "frequency": freq_str,
                    "source": "landing_page"
                }
            }
            try:
                resp = requests.post(url, json=payload, auth=HTTPBasicAuth(LISTMONK_USER, LISTMONK_PASS), timeout=10)
                print(f"[API] Listmonk subscription status: {resp.status_code}")
            except Exception as le:
                print(f"[API Error] Failed to subscribe to Listmonk: {le}")
                
        return {"status": "success", "message": "Subscribed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database or signup error: {str(e)}")

@app.post("/webhooks/payment-success")
async def handle_payment_flow(request: Request):
    """
    Listens to successful transaction signals (Whop checkout, Crypto, native cards)
    and instantly subscribes the active email target to your real-time mailing lists.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    
    print(f"[Webhook] Received payment success webhook payload: {json.dumps(payload)}")
    
    # Isolate buyer specific context dynamically from the webhook payload matrix
    user_email = payload.get("user", {}).get("email")
    user_name = payload.get("user", {}).get("username", "Arbitrage Subscriber")
    
    if not user_email:
        raise HTTPException(status_code=400, detail="Invalid payload context: Email parameter missing.")

    # Execute programmatic user creation inside your Listmonk instance
    subscriber_endpoint = f"{LISTMONK_URL}/subscribers"
    list_id = int(os.getenv("LISTMONK_CAMPAIGN_LIST_ID", 1))
    
    subscriber_data = {
        "email": user_email,
        "name": user_name,
        "status": "enabled",
        "lists": [list_id]  # Premium alert list
    }
    
    try:
        response = requests.post(
            subscriber_endpoint,
            json=subscriber_data,
            auth=HTTPBasicAuth(LISTMONK_USER, LISTMONK_PASS),
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            # Trigger welcome email outbox notification
            trigger_welcome_email(user_email)
            return {"status": "success", "message": "User registered and email routing active."}
        else:
            return {"status": "error", "message": f"Listmonk integration failure: {response.text}"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal pipeline failure: {str(e)}")

@app.post("/webhooks/payment-failed-or-cancelled")
async def handle_subscription_termination(request: Request):
    """
    Listens for subscription failures or explicit cancellations to immediately
    remove the target email from premium data distribution lists.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
        
    user_email = payload.get("user", {}).get("email")
    
    if not user_email:
        raise HTTPException(status_code=400, detail="Invalid payload: Email parameter missing.")
        
    # Query Listmonk to fetch the specific Subscriber ID based on the email address
    search_url = f"{LISTMONK_URL}/subscribers?query=subscribers.email='{user_email}'"
    
    try:
        search_response = requests.get(search_url, auth=HTTPBasicAuth(LISTMONK_USER, LISTMONK_PASS), timeout=10)
        results = search_response.json().get("data", {}).get("results", [])
        if not results:
            return {"status": "cleared", "message": "No active email profile matching criteria found."}
            
        subscriber_id = results[0]["id"]
        
        # Completely remove the user object or strip them of their VIP list entitlements
        delete_url = f"{LISTMONK_URL}/subscribers/{subscriber_id}"
        requests.delete(delete_url, auth=HTTPBasicAuth(LISTMONK_USER, LISTMONK_PASS), timeout=10)
        
        return {"status": "revoked", "message": "Premium email access rights successfully dismantled."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute subscriber database cleanup: {str(e)}")

def trigger_welcome_email(recipient_email: str):
    """Dispatches a transactional onboarding verification alert immediately."""
    tx_endpoint = f"{LISTMONK_URL}/tx"
    payload = {
        "template_id": 3,  # Sample transactional template
        "subscriber_email": recipient_email,
        "subscriber_mode": "fallback",
        "subject": "🚨 [Access Granted] Welcome to Arbitrage Arena VIP",
        "data": {
            "message": "<h1>Your Premium Signal Feed is Active!</h1><p>Our algorithms have locked your data connection profile. Expect real-time market anomalies hitting your inbox before the sports betting lines adjust.</p>"
        },
        "content_type": "html"
    }
    try:
        resp = requests.post(tx_endpoint, json=payload, auth=HTTPBasicAuth(LISTMONK_USER, LISTMONK_PASS), timeout=10)
        print(f"[Webhook] Welcome email dispatch status: {resp.status_code}")
    except Exception as e:
        print(f"[Webhook Error] Failed to send welcome email: {e}")

# Set to track sent reminders to avoid duplicates in logs
already_notified = set()

def run_email_reminder_daemon():
    print("[Daemon] Email Reminder Daemon started...")
    db_path = os.path.join(workspace_dir, "database.db")
    schedule_path = os.path.join(workspace_dir, "landing_page", "schedule.json")
    config_path = os.path.join(workspace_dir, "landing_page", "config.json")
    log_path = os.path.join(workspace_dir, "landing_page", "email_reminders.log")
    
    while True:
        try:
            # 1. Fetch active subscribers
            subscribers = []
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscribers (
                        email TEXT PRIMARY KEY,
                        frequency INTEGER DEFAULT 3,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute("SELECT email, frequency FROM subscribers")
                subscribers = cursor.fetchall()
                conn.close()
            
            # 2. Fetch target matches from schedule.json
            fixtures = []
            if os.path.exists(schedule_path) and subscribers:
                with open(schedule_path, "r", encoding="utf-8") as f:
                    fixtures = json.load(f)
            
            # 3. Read bot username
            bot_username = "sport_anomalybot"
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    bot_username = cfg.get("bot_username", "sport_anomalybot")

            if subscribers and fixtures:
                now_ts = int(time.time())
                
                # Filter upcoming/live target matches
                target_tournaments = [
                    "world cup", "world championship", "worldcup", "euro", "copa america",
                    "champions league", "premier league", "la liga", "laliga", "serie a", "bundesliga"
                ]
                
                valid_fixtures = []
                for item in fixtures:
                    t_name = (item.get("tournament", {}).get("name", "")).lower()
                    u_t_name = (item.get("tournament", {}).get("uniqueTournament", {}).get("name", "")).lower()
                    
                    is_target = any(t in t_name or t in u_t_name for t in target_tournaments)
                    if not is_target:
                        continue
                        
                    ts = item.get("startTimestamp")
                    if not ts:
                        continue
                        
                    status = item.get("status", {}).get("type", "notstarted")
                    if status != "finished" and ts > now_ts - 3600 * 3:
                        valid_fixtures.append(item)
                
                # If we have matches to alert on, send reminders
                if valid_fixtures:
                    best_match = valid_fixtures[0]
                    home = best_match["homeTeam"]["name"]
                    away = best_match["awayTeam"]["name"]
                    fixture_id = best_match["id"]
                    
                    reminder_templates = [
                        "Yo bestie, sheeesh! 💅 The agent just cooked a massive win path. {home} vs {away} has a high certainty rate. kelly stake allocation is active (literally a money glitch). Mirror the smart money here: https://t.me/{bot_username}. No cap, go secure the W! 🚀",
                        "🚨 BIG BRAIN MOMENT: Let the agent cook! 🧠 {home} vs {away} is flashing dynamic anomalies with max profit stakes. Don't look away, this is an absolute cheat code. Access the alert feed: https://t.me/{bot_username} 🔥",
                        "Bestie, no cap, we are printing USD/KES today! 🤑 The sports bookies are crying because {home} vs {away} is highly anomalous. Kelly stake is locked and loaded. Mirror positions now: https://t.me/{bot_username} ⚡"
                    ]
                    
                    for sub in subscribers:
                        email = sub[0]
                        freq = sub[1]
                        
                        alert_key = f"{email}_{fixture_id}"
                        if alert_key not in already_notified:
                            # Select template based on length of email hash to randomize
                            tpl = reminder_templates[hash(email) % len(reminder_templates)]
                            msg = tpl.format(home=home, away=away, bot_username=bot_username)
                            
                            # Log the sent email reminder
                            log_entry = (
                                f"--------------------------------------------------\n"
                                f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"To: {email} (Frequency: {freq}h)\n"
                                f"Subject: 💅 Bestie, the agent cooked a new anomaly lock! No cap.\n"
                                f"Message: {msg}\n"
                                f"--------------------------------------------------\n"
                            )
                            with open(log_path, "a", encoding="utf-8") as lf:
                                lf.write(log_entry)
                                
                            # Send via Listmonk transactional API
                            if LISTMONK_URL and LISTMONK_USER and LISTMONK_PASS:
                                try:
                                    tx_url = f"{LISTMONK_URL}/tx"
                                    tx_payload = {
                                        "template_id": 3,
                                        "subscriber_email": email,
                                        "subscriber_mode": "fallback",
                                        "subject": "💅 Bestie, the agent cooked a new anomaly lock! No cap.",
                                        "data": {
                                            "message": msg
                                        },
                                        "content_type": "html"
                                    }
                                    tx_resp = requests.post(tx_url, json=tx_payload, auth=HTTPBasicAuth(LISTMONK_USER, LISTMONK_PASS), timeout=10)
                                    print(f"[Daemon] Listmonk tx send status for {email}: {tx_resp.status_code}")
                                except Exception as le:
                                    print(f"[Daemon Error] Failed to send transactional email to {email}: {le}")
                                
                            print(f"[Daemon] Dispatched GenZ reminder to {email} for match: {home} vs {away}")
                            already_notified.add(alert_key)
            
        except Exception as e:
            print(f"[Daemon Error] {e}")
            
        time.sleep(10)

def sync_smtp_settings():
    in_docker = os.path.exists('/.dockerenv') or os.path.isdir('/app')
    
    db_host = os.getenv("LISTMONK_DB_HOST", "listmonk_db" if in_docker else "localhost")
    db_port = os.getenv("LISTMONK_DB_PORT", "5432")
    db_user = os.getenv("LISTMONK_DB_USER", "arena_admin")
    db_pass = os.getenv("LISTMONK_DB_PASSWORD")
    db_name = os.getenv("LISTMONK_DB_DATABASE", "arena_mailing_db")
    
    smtp_host = os.getenv("SMTP_HOST", "listmonk_mailpit" if in_docker else "localhost")
    smtp_port = os.getenv("SMTP_PORT", "1025")
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_tls_type = os.getenv("SMTP_TLS_TYPE", "None")
    from_email = os.getenv("SMTP_FROM_EMAIL", "Arbitrage Arena <arbitragearena@xyz>")
    
    print(f"[SMTP Sync] Syncing SMTP settings to database {db_host}:{db_port}...")
    
    smtp_cfg = [{
        "host": smtp_host,
        "port": int(smtp_port),
        "enabled": True,
        "username": smtp_username,
        "password": smtp_password,
        "tls_type": smtp_tls_type,
        "max_conns": 10,
        "idle_timeout": "15s",
        "wait_timeout": "5s",
        "auth_protocol": "login" if smtp_username else "",
        "email_headers": [],
        "hello_hostname": "",
        "max_msg_retries": 2,
        "tls_skip_verify": True if smtp_host in ["mailpit", "listmonk_mailpit", "localhost", "127.0.0.1"] else False
    }]
    
    smtp_json = json.dumps(smtp_cfg)
    escaped_from = json.dumps(from_email).replace("'", "''")
    escaped_smtp = smtp_json.replace("'", "''")
    
    api_user = os.getenv("LISTMONK_USERNAME", "api_agent")
    api_pass = os.getenv("LISTMONK_PASSWORD")
    
    sql_updates = f"""
    UPDATE settings SET value = '{escaped_from}' WHERE key = 'app.from_email';
    UPDATE settings SET value = '{escaped_smtp}' WHERE key = 'smtp';
    
    -- Ensure api_agent user exists in users table (role_id 1 is Super Admin)
    INSERT INTO users (username, password_login, password, email, name, type, user_role_id, status)
    VALUES ('{api_user}', false, '{api_pass}', '{api_user}@api', '{api_user}', 'api', 1, 'enabled')
    ON CONFLICT (username) DO UPDATE SET password = '{api_pass}', status = 'enabled';
    
    -- Ensure template 3 (Sample transactional template) is configured to render custom messages
    UPDATE templates SET body = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="font-family: sans-serif; padding: 20px;"><p>{{{{ .Tx.Data.message }}}}</p></body></html>' WHERE id = 3;
    """
    
    success = False
    # Attempt 1: Direct PostgreSQL connection
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_pass,
            database=db_name,
            connect_timeout=5
        )
        cursor = conn.cursor()
        cursor.execute(sql_updates)
        conn.commit()
        cursor.close()
        conn.close()
        print("[SMTP Sync] Database updated successfully via psycopg2.")
        success = True
    except Exception as pe:
        print(f"[SMTP Sync] Direct psycopg2 connection failed: {pe}. Trying fallback...")
        
    # Attempt 2: docker exec fallback
    if not success and not in_docker:
        import subprocess
        try:
            subprocess.run(
                ["docker", "exec", "-i", "listmonk_db", "psql", "-U", db_user, "-d", db_name],
                input=sql_updates,
                capture_output=True,
                text=True,
                check=True
            )
            print("[SMTP Sync] Database updated successfully via docker exec.")
            success = True
        except Exception as de:
            print(f"[SMTP Sync] docker exec fallback failed: {de}")
            
    if success:
        print("[SMTP Sync] Settings synchronization complete.", flush=True)
    else:
        print("[SMTP Sync] Settings synchronization failed.", flush=True)
        raise Exception("Database sync failed.")

@app.on_event("startup")
def startup_event():
    # Validate environment configurations
    Config.validate()
    
    # Sync SMTP settings and create API user
    # Note: If PostgreSQL is starting up in compose, psycopg2 might take a few seconds to connect.
    # We run it in a short background initialization loop to prevent blocking FastAPI startup.
    def init_db_loop():
        print("[DB Init] Starting background DB initialization loop...", flush=True)
        for i in range(20):  # retry for 100 seconds
            try:
                sync_smtp_settings()
                print("[DB Init] Successfully initialized and synchronized Listmonk settings.", flush=True)
                break
            except Exception as e:
                print(f"[DB Init] Retry {i+1}/20 failed: {e}", flush=True)
                time.sleep(5)
                
    threading.Thread(target=init_db_loop, daemon=True).start()

    # Start Email Reminder Daemon Thread
    daemon_thread = threading.Thread(target=run_email_reminder_daemon, daemon=True)
    daemon_thread.start()

# Define frontend static routes
# Order is important: explicit routes first, then the fallback static files mount at '/'
@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(workspace_dir, "landing_page", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return HTMLResponse("<h1>Arbitrage Arena Landing Page Missing</h1>", status_code=404)

# Serve config.json, schedule.json, etc. from landing_page
app.mount("/", StaticFiles(directory=os.path.join(workspace_dir, "landing_page")), name="landing")
