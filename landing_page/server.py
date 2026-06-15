import os
import sys
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

# Load env variables
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(workspace_dir, ".env"))

PORT = 8000

class CustomHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve files from landing_page directory
        directory = os.path.dirname(os.path.abspath(__file__))
        super().__init__(*args, directory=directory, **kwargs)

    def do_POST(self):
        if self.path == "/api/subscribe":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode('utf-8'))
                email = data.get("email", "").strip().lower()
                frequency = int(data.get("frequency", 3)) # Default 3 hours (spicy reminders)
                
                if not email or "@" not in email:
                    self.send_error_response(400, "Invalid email address.")
                    return
                
                # Save subscriber to SQLite billing/gateway database
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database.db")
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
                api_url = os.getenv("LISTMONK_API_URL")
                username = os.getenv("LISTMONK_USERNAME")
                password = os.getenv("LISTMONK_PASSWORD")
                list_id = os.getenv("LISTMONK_CAMPAIGN_LIST_ID")
                
                if api_url and username and password and list_id:
                    try:
                        import requests
                        url = f"{api_url}/subscribers"
                        headers = {
                            "Authorization": f"token {username}:{password}",
                            "Content-Type": "application/json"
                        }
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
                        resp = requests.post(url, json=payload, headers=headers)
                        print(f"[API] Listmonk subscription status: {resp.status_code}")
                    except Exception as le:
                        print(f"[API Error] Failed to subscribe to Listmonk: {le}")
                
                # Send JSON response
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Subscribed successfully"}).encode('utf-8'))
            except Exception as e:
                self.send_error_response(500, f"Server error: {e}")
        else:
            self.send_error_response(404, "Endpoint not found.")

    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "error", "message": message}).encode('utf-8'))

# Set to track sent reminders to avoid duplicates in logs
already_notified = set()

def run_email_reminder_daemon():
    print("[Daemon] Email Reminder Daemon started...")
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(workspace_dir, "database.db")
    schedule_path = os.path.join(workspace_dir, "landing_page", "schedule.json")
    config_path = os.path.join(workspace_dir, "landing_page", "config.json")
    log_path = os.path.join(workspace_dir, "landing_page", "email_reminders.log")
    
    while True:
        try:
            # Load fresh env vars in case they changed
            api_url = os.getenv("LISTMONK_API_URL")
            username = os.getenv("LISTMONK_USERNAME")
            password = os.getenv("LISTMONK_PASSWORD")
            
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
                    # Pick the highest confidence match (just using the first one or sorting by timestamp)
                    best_match = valid_fixtures[0]
                    home = best_match["homeTeam"]["name"]
                    away = best_match["awayTeam"]["name"]
                    fixture_id = best_match["id"]
                    
                    # Generate realistic GenZ copywriting messages
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
                            if api_url and username and password:
                                try:
                                    import requests
                                    tx_url = f"{api_url}/tx"
                                    headers = {
                                        "Authorization": f"token {username}:{password}",
                                        "Content-Type": "application/json"
                                    }
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
                                    tx_resp = requests.post(tx_url, json=tx_payload, headers=headers)
                                    print(f"[Daemon] Listmonk tx send status for {email}: {tx_resp.status_code}")
                                except Exception as le:
                                    print(f"[Daemon Error] Failed to send transactional email to {email}: {le}")
                                
                            print(f"[Daemon] Dispatched GenZ reminder to {email} for match: {home} vs {away}")
                            already_notified.add(alert_key)
            
        except Exception as e:
            print(f"[Daemon Error] {e}")
            
        time.sleep(10) # Loop daemon every 10 seconds for real-time validation

def run_server():
    # Start Email Reminder Daemon Thread
    daemon_thread = threading.Thread(target=run_email_reminder_daemon, daemon=True)
    daemon_thread.start()
    
    server = HTTPServer(('0.0.0.0', PORT), CustomHandler)
    print(f"GenZ Dashboard Server running on port {PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    run_server()
