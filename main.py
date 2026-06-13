import os
import sys
import json
import requests
import logging
import time as time_lib
from datetime import datetime, timezone, timedelta
from config import Config
from engine import fetch_live_world_cup_matches, analyze_match_anomalies, FEEDBACK_FILE
from bot import send_telegram_alert

# Hook directly into OpenClaw's stdout logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [OpenClaw-Arbitrage] - %(levelname)s - %(message)s'
)

SCHEDULE_FILE = "schedule.json"
SENT_ALERTS_FILE = "sent_alerts.json"

def fetch_and_save_schedule():
    """
    Fetches the entire scheduled football events for today.
    Uses 1 API request and saves it locally.
    """
    logging.info("schedule.json not found or outdated. Fetching daily schedule...")
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    
    url = f"{Config.BASE_URL}/sport/football/scheduled-events/{today_str}"
    headers = {
        "X-RapidAPI-Key": Config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": Config.RAPIDAPI_HOST
    }
    
    if not Config.RAPIDAPI_KEY:
        logging.error("RapidAPI Key is not configured in environment. Cannot fetch schedule.")
        return []
        
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            logging.error(f"Failed to fetch season schedule: {response.status_code}")
            return []
        
        data = response.json()
        events = data.get("events", [])
        if not events:
            logging.warning("No events returned from SportAPI for today.")
            return []
            
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=4)
        logging.info(f"Successfully cached {len(events)} events to {SCHEDULE_FILE}")
        return events
    except Exception as e:
        logging.error(f"Error fetching/saving schedule: {str(e)}")
        return []

def load_schedule():
    """
    Loads schedule from local cache file. If not found, fetches from API.
    """
    if os.path.exists(SCHEDULE_FILE):
        try:
            # Check if cache file is from today
            mtime = os.path.getmtime(SCHEDULE_FILE)
            cache_date = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if cache_date == today_str:
                with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                logging.info("Cached schedule is from a previous day. Re-fetching...")
        except Exception as e:
            logging.error(f"Error reading local schedule file: {str(e)}")
            
    return fetch_and_save_schedule()

def load_sent_alerts():
    """
    Loads sent alerts tracking to prevent duplicates.
    """
    if os.path.exists(SENT_ALERTS_FILE):
        try:
            with open(SENT_ALERTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error reading sent alerts file: {str(e)}")
    return {}

def save_sent_alerts(alerts):
    """
    Saves sent alerts tracking to file.
    """
    try:
        with open(SENT_ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts, f, indent=4)
        logging.info(f"Saved sent alerts state to {SENT_ALERTS_FILE}")
    except Exception as e:
        logging.error(f"Error writing to sent alerts file: {str(e)}")

def check_active_windows(fixtures):
    """
    Evaluates matches against current UTC time.
    Returns:
      - today_fixtures: list of matches scheduled for today
      - active_fixtures: list of matches currently in their active time window (kickoff - 15m to kickoff + 3h)
    """
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    
    today_fixtures = []
    active_fixtures = []
    
    for item in fixtures:
        # Filter for World Cup matches
        tournament_name = item.get("tournament", {}).get("name", "").lower()
        unique_tournament_name = item.get("tournament", {}).get("uniqueTournament", {}).get("name", "").lower()
        
        is_world_cup = (
            "world cup" in tournament_name or
            "world cup" in unique_tournament_name or
            "world championship" in tournament_name or
            "world championship" in unique_tournament_name or
            "worldcup" in tournament_name or
            "worldcup" in unique_tournament_name
        )
        if not is_world_cup:
            continue
            
        ts = item.get("startTimestamp")
        if not ts:
            continue
        match_time = datetime.fromtimestamp(ts, tz=timezone.utc)
        match_date_str = match_time.strftime("%Y-%m-%d")
        
        if match_date_str == today_str:
            today_fixtures.append(item)
            # Match window: 15 minutes before kickoff up to 3 hours after kickoff
            start_window = match_time - timedelta(minutes=15)
            end_window = match_time + timedelta(hours=3)
            
            if start_window <= now_utc <= end_window:
                active_fixtures.append(item)
                
    return today_fixtures, active_fixtures

def fetch_match_incidents(event_id: int):
    url = f"{Config.BASE_URL}/event/{event_id}/incidents"
    headers = {
        "X-RapidAPI-Key": Config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": Config.RAPIDAPI_HOST
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("incidents", [])
        return []
    except Exception as e:
        logging.error(f"Error fetching incidents for event {event_id}: {str(e)}")
        return []

def evaluate_concluded_matches():
    logging.info("Feedback Loop: Commencing concluded matches evaluation check...")
    
    if not os.path.exists(SCHEDULE_FILE):
        return
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            fixtures = json.load(f)
    except Exception as e:
        logging.error(f"Error loading schedule for evaluation: {str(e)}")
        return

    sent_alerts = load_sent_alerts()
    if not sent_alerts:
        return

    # Load feedback loop
    feedback = {}
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                feedback = json.load(f)
        except Exception as e:
            logging.error(f"Error loading feedback: {str(e)}")
            
    # Default initialization
    for tier in ["WHALE_VAULT", "HIGH_YIELD", "PRESSURE_ANOMALY"]:
        if tier not in feedback:
            feedback[tier] = {"successes": 0, "failures": 0, "bias_adjustment": 0.0}

    updated_alerts = False
    updated_feedback = False

    for match in fixtures:
        match_id = match['id']
        match_id_str = str(match_id)
        
        status_type = match.get('status', {}).get('type', '')
        if status_type != 'finished':
            continue
            
        home_score = match.get('homeScore', {}).get('current', 0)
        away_score = match.get('awayScore', {}).get('current', 0)
        
        # Check alerts for this match
        for alert_key, val in list(sent_alerts.items()):
            if not alert_key.startswith(f"{match_id_str}_"):
                continue
                
            # Normalize old string format to dict
            if isinstance(val, str):
                val = {
                    "timestamp": val,
                    "evaluated": False,
                    "minute": 45,
                    "type": alert_key.split('_', 1)[1]
                }
                sent_alerts[alert_key] = val
                updated_alerts = True
                
            if val.get("evaluated", False):
                continue
                
            alert_type = val.get("type")
            alert_minute = val.get("minute", 0)
            
            success = False
            evaluation_possible = True
            
            if alert_type == "WHALE_VAULT":
                # Predicted winner
                predicted = val.get("predicted_winner")
                if predicted == "home" and home_score > away_score:
                    success = True
                elif predicted == "away" and away_score > home_score:
                    success = True
                else:
                    success = False
            elif alert_type in ["PRESSURE_ANOMALY", "HIGH_YIELD"]:
                if home_score == 0 and away_score == 0:
                    success = False
                    evaluation_possible = True
                else:
                    incidents = fetch_match_incidents(match_id)
                    if incidents:
                        goal_scored = False
                        for inc in incidents:
                            if inc.get("incidentType") == "goal":
                                inc_time = inc.get("time", 0)
                                if inc_time > alert_minute:
                                    goal_scored = True
                                    break
                        success = goal_scored
                    else:
                        evaluation_possible = False
            else:
                success = True
                
            if evaluation_possible:
                tier_stats = feedback.get(alert_type)
                if not tier_stats:
                    feedback[alert_type] = {"successes": 0, "failures": 0, "bias_adjustment": 0.0}
                    tier_stats = feedback[alert_type]
                    
                if success:
                    tier_stats["successes"] += 1
                    tier_stats["bias_adjustment"] = min(tier_stats["bias_adjustment"] + 0.01, 0.05)
                    logging.info(f"Feedback Loop: SUCCESS for {alert_key}. Reward (+0.01 bias) applied.")
                else:
                    tier_stats["failures"] += 1
                    tier_stats["bias_adjustment"] = max(tier_stats["bias_adjustment"] - 0.02, -0.10)
                    logging.info(f"Feedback Loop: FAILURE for {alert_key}. Penalty (-0.02 bias) applied.")
                    
                val["evaluated"] = True
                val["success"] = success
                updated_alerts = True
                updated_feedback = True

    if updated_alerts:
        save_sent_alerts(sent_alerts)
    if updated_feedback:
        try:
            with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(feedback, f, indent=4)
            logging.info(f"Saved updated feedback state to {FEEDBACK_FILE}")
        except Exception as e:
            logging.error(f"Error saving feedback loop: {str(e)}")

def run_pipeline():
    logging.info("OpenClaw heartbeat triggered. Commencing live data parse...")
    dry_run = "--dry-run" in sys.argv or os.getenv("DRY_RUN") == "True"
    
    if dry_run:
        logging.info("Running in DRY-RUN mode. Skipping API checks and budget guardrails.")
        # Perform a quick configuration check
        if not Config.TELEGRAM_BOT_TOKEN:
            logging.warning("Telegram Bot Token is missing from environment.")
        return

    # 1. Budget Guardrail - Load schedule
    fixtures = load_schedule()
    if not fixtures:
        logging.warning("No schedule available. Exiting to protect API limits.")
        return

    # 2. Budget Guardrail - Evaluate matches today & active windows
    today_fixtures, active_fixtures = check_active_windows(fixtures)
    
    logging.info(f"Today's matches: {len(today_fixtures)} | Active match windows: {len(active_fixtures)}")
    
    if not today_fixtures:
        logging.info("API Guardrail: No World Cup matches scheduled for today. Exiting.")
        return
        
    if not active_fixtures:
        logging.info("API Guardrail: Matches scheduled today, but none are in active window. Exiting.")
        return

    # 3. Fetch Live Matches
    logging.info("API Guardrail passed. Querying live fixtures...")
    live_matches = fetch_live_world_cup_matches()
    if not live_matches:
        logging.info("No active high-variance match windows found at this checkpoint.")
        # Perform evaluation on finished matches even if no matches are currently live
        evaluate_concluded_matches()
        return

    logging.info(f"Found {len(live_matches)} live match(es). Analyzing for anomalies...")
    sent_alerts = load_sent_alerts()
    updated = False
    
    for match in live_matches:
        fixture_id = match['id']
        fixture_id_str = str(fixture_id)
        
        # Parse elapsed time dynamically
        status_desc = match.get('status', {}).get('description', '')
        current_ts = int(time_lib.time())
        if status_desc == '1st half':
            start_ts = match.get('startTimestamp', current_ts)
            elapsed = (current_ts - start_ts) // 60
        elif status_desc == '2nd half':
            period_start = match.get('time', {}).get('currentPeriodStartTimestamp')
            if period_start:
                elapsed = 45 + (current_ts - period_start) // 60
            else:
                start_ts = match.get('startTimestamp', current_ts)
                elapsed = (current_ts - start_ts) // 60
        elif status_desc == 'Halftime':
            elapsed = 45
        else:
            start_ts = match.get('startTimestamp', current_ts)
            elapsed = (current_ts - start_ts) // 60
            
        # Optimization: Only process matches in the anomaly detection time-window (15' to 80')
        # This saves statistics API calls for early/late game periods
        if not (15 <= elapsed <= 80):
            logging.info(f"Match {fixture_id_str} is at minute {elapsed}'. Outside detection range (15'-80'). Skipping stats query.")
            continue
            
        anomaly = analyze_match_anomalies(match)
        if anomaly:
            anomaly_type = anomaly['type']
            alert_key = f"{fixture_id_str}_{anomaly_type}"
            is_premium = anomaly.get('premium', False)
            
            if alert_key not in sent_alerts:
                logging.info(f"New anomaly detected: {anomaly_type} for fixture {fixture_id_str}")
                
                if is_premium:
                    # Send full alert to Premium VIP Channel
                    success_premium = send_telegram_alert(anomaly['message'], is_premium=True)
                    logging.info(f"Premium signal successfully pushed to VIP layer. Tier: {anomaly_type}")
                    
                    # Construct and send teaser to Free Channel
                    teaser_message = (
                        "🔒 *[PREMIUM MODEL MISMATCH DETECTED]* 🔒\n\n"
                        f"🏟️ *Match*: {match['homeTeam']['name']} vs {match['awayTeam']['name']}\n"
                        f"⏱️ *Current Window*: Minute {elapsed}'\n"
                        "📈 *Indicator Matrix*: High-Stake / Low-Risk Probability Arbitrage Node.\n\n"
                        "⚠️ *Notice*: This signal has met the criteria for our maximum confidence thresholds. "
                        "To prevent betting line collapse, the full position is restricted to verified subscribers.\n\n"
                        "👇 *Unlock the real-time target and protect your bankroll instantly:* \n"
                        "🔗 [Join The Premium Whale Vault Here](https://t.me/mock_arbitrage_arena_premium)"
                    )
                    success_free = send_telegram_alert(teaser_message, is_premium=False)
                    success = success_premium or success_free
                else:
                    # Send full alert directly to Free Channel
                    success = send_telegram_alert(anomaly['message'], is_premium=False)
                    
                if success:
                    # Save sent alert with extra evaluation metadata
                    sent_alerts[alert_key] = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "evaluated": False,
                        "minute": elapsed,
                        "type": anomaly_type,
                        "predicted_winner": "home" if match.get('homeScore', {}).get('current', 0) > match.get('awayScore', {}).get('current', 0) else "away"
                    }
                    updated = True
            else:
                logging.info(f"Duplicate alert prevented for {alert_key}")
                
    if updated:
        save_sent_alerts(sent_alerts)

    # Perform evaluation on finished matches at the end of the run
    evaluate_concluded_matches()

main = run_pipeline

if __name__ == "__main__":
    run_pipeline()
