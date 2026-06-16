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
import backtest_handler

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
        
        # Also copy/write to landing_page/schedule.json for the frontend
        landing_page_schedule = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing_page", "schedule.json")
        try:
            with open(landing_page_schedule, "w", encoding="utf-8") as f:
                json.dump(events, f, indent=4)
            logging.info(f"Successfully cached copy of schedule to {landing_page_schedule}")
        except Exception as copy_err:
            logging.error(f"Failed to copy schedule to landing page: {copy_err}")
            
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
                # Ensure it's copied to landing_page if missing
                landing_page_schedule = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing_page", "schedule.json")
                if not os.path.exists(landing_page_schedule):
                    try:
                        import shutil
                        shutil.copy2(SCHEDULE_FILE, landing_page_schedule)
                        logging.info("Copied existing daily schedule to landing page.")
                    except Exception as copy_err:
                        logging.error(f"Error copying existing schedule to landing page: {copy_err}")
                
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
        tournament_name = item.get("tournament", {}).get("name", "").lower()
        unique_tournament_name = item.get("tournament", {}).get("uniqueTournament", {}).get("name", "").lower()
        
        target_tournaments = [
            "world cup", "world championship", "worldcup",
            "euro", "copa america", "champions league", "europa league",
            "premier league", "la liga", "la-liga", "laliga", "serie a", "bundesliga",
            "ligue 1", "eredivisie", "primeira liga", "mls", "major league soccer",
            "copa libertadores", "liga mx", "super lig", "pro league", "championship",
            "fa cup", "copa del rey", "coppa italia", "dfb pokal", "coupe de france",
            "brasileirao", "liga profesional", "k league", "j1 league", "a-league",
            "african cup of nations", "afcon", "asian cup"
        ]
        
        is_target_league = any(t in tournament_name or t in unique_tournament_name for t in target_tournaments)
        if not is_target_league:
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
                
                # Closed-loop backtest evaluation
                real_outcome = 1 if success else 0
                new_weight = backtest_handler.evaluate_and_adjust_weights(match_id, alert_type, real_outcome)
                if new_weight is not None:
                    logging.info(f"Closed-loop SQLite weight for {alert_type} adjusted to {new_weight:.2f}")
                bs = backtest_handler.calculate_brier_score()
                logging.info(f"Cumulative Brier Score: {bs:.4f}")

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

def export_past_analysis():
    import sqlite3
    db_path = "agent_memory.db"
    backtest_handler.initialize_memory_db()
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT fixture_id, match_name, calculated_prob, trigger_type, outcome, current_weight FROM historical_logs ORDER BY rowid DESC")
        rows = cursor.fetchall()
        conn.close()
        
        # Calculate metrics
        evaluated_rows = [r for r in rows if r[4] != -1]
        total_evaluated = len(evaluated_rows)
        successes = len([r for r in evaluated_rows if r[4] == 1])
        failures = len([r for r in evaluated_rows if r[4] == 0])
        win_rate = (successes / total_evaluated * 100) if total_evaluated > 0 else 0.0
        
        squared_errors = []
        for r in evaluated_rows:
            squared_errors.append((r[2] - r[4])**2)
        brier_score = (sum(squared_errors) / len(squared_errors)) if len(squared_errors) > 0 else 0.0
        
        # Calculate profit units: +0.5 for success, -1.0 for failure
        profit_units = sum([0.5 if r[4] == 1 else -1.0 for r in evaluated_rows])
        profit_usd = profit_units * 100.0
        profit_kes = profit_units * 13000.0
        
        past_matches = []
        for r in rows:
            prob_percent = r[2]
            if prob_percent <= 1.0:
                prob_percent = prob_percent * 100
                
            past_matches.append({
                "fixture_id": r[0],
                "match_name": r[1],
                "calculated_prob": round(prob_percent, 1),
                "trigger_type": r[3].replace("_", " "),
                "outcome": r[4], # -1 = pending, 1 = success, 0 = failure
                "current_weight": round(r[5], 2)
            })
            
        # Get latest weights from database
        weight_whale = backtest_handler.get_current_weight("WHALE_VAULT")
        weight_high_yield = backtest_handler.get_current_weight("HIGH_YIELD")
        weight_pressure = backtest_handler.get_current_weight("PRESSURE_ANOMALY")

        analysis_data = {
            "total_evaluated": total_evaluated,
            "successes": successes,
            "failures": failures,
            "win_rate": round(win_rate, 1),
            "brier_score": round(brier_score, 4),
            "profit_units": round(profit_units, 1),
            "profit_usd": f"${profit_usd:+,.2f}" if profit_usd != 0 else "$0.00",
            "profit_kes": f"KES {profit_kes:+,.0f}" if profit_kes != 0 else "KES 0",
            "weights": {
                "WHALE_VAULT": round(weight_whale, 2),
                "HIGH_YIELD": round(weight_high_yield, 2),
                "PRESSURE_ANOMALY": round(weight_pressure, 2)
            },
            "past_matches": past_matches
        }
        
        out_path = os.path.join("landing_page", "past_analysis.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(analysis_data, f, indent=4)
        logging.info(f"Successfully exported past analysis data to {out_path}")
    except Exception as e:
        logging.error(f"Error exporting past analysis: {e}")

def run_pipeline():
    # Safe environment diagnostic logs
    logging.info(f"RAPIDAPI_KEY loaded: {'YES' if Config.RAPIDAPI_KEY else 'NO'}")
    logging.info(f"TELEGRAM_BOT_TOKEN loaded: {'YES' if Config.TELEGRAM_BOT_TOKEN else 'NO'}")
    
    # Validate environment configurations
    Config.validate(component="engine")

    
    logging.info("OpenClaw heartbeat triggered. Commencing live data parse...")
    backtest_handler.initialize_memory_db()
    export_past_analysis()
    
    # Fetch bot username dynamically if not configured explicitly
    if not Config.TELEGRAM_BOT_USERNAME or Config.TELEGRAM_BOT_USERNAME == "mock_arbitrage_arena_bot":
        try:
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/getMe"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                username = resp.json().get("result", {}).get("username")
                if username:
                    Config.TELEGRAM_BOT_USERNAME = username
                    logging.info(f"Dynamically fetched bot username from Telegram: @{username}")
        except Exception as e:
            logging.error(f"Error fetching bot username from Telegram: {e}")

    # Write config.json for the landing page
    try:
        free_channel_link = "https://t.me/mock_arbitrage_arena_free"
        if Config.FREE_CHANNEL_ID:
            try:
                url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/getChat"
                resp = requests.post(url, json={"chat_id": Config.FREE_CHANNEL_ID}, timeout=5)
                if resp.status_code == 200:
                    res_json = resp.json()
                    if res_json.get("ok"):
                        chat_data = res_json.get("result", {})
                        username = chat_data.get("username")
                        if username:
                            free_channel_link = f"https://t.me/{username}"
                        else:
                            invite_link = chat_data.get("invite_link")
                            if invite_link:
                                free_channel_link = invite_link
            except Exception as e:
                logging.error(f"Error fetching free channel link from Telegram: {e}")

        whop_link = Config.WHOP_CHECKOUT_LINK
        if whop_link and ("mock" in whop_link.lower()) and Config.TELEGRAM_BOT_USERNAME:
            whop_link = f"https://t.me/{Config.TELEGRAM_BOT_USERNAME}"

        config_data = {
            "bot_username": Config.TELEGRAM_BOT_USERNAME,
            "free_channel_link": free_channel_link,
            "whop_checkout_link": whop_link
        }
        config_path = os.path.join("landing_page", "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
        logging.info(f"Wrote landing page config to {config_path}")
    except Exception as e:
        logging.error(f"Error writing landing page config: {e}")

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
                    bot_link = f"https://t.me/{Config.TELEGRAM_BOT_USERNAME}"
                    teaser_message = (
                        "🔒 *[VIP MODEL MISMATCH ISOLATED]* 🔒\n\n"
                        f"🏟️ *Match*: {match['homeTeam']['name']} vs {match['awayTeam']['name']}\n"
                        "📈 *Certainty Index*: Max-Confidence Whale Security Alert Matrix.\n\n"
                        "⚠️ *Line Sensitivity Restriction:* This premium model alert has cleared our highest risk-mitigation metrics. "
                        "To shield the position from immediate odds devaluation by bookmakers, access is closed to public users.\n\n"
                        "👇 *Unlock the live position target and mirror the smart money instantly:* \n"
                        f"👉 [Get a 7-Day Weekly Pass ($9.99) or Full Monthly Access ($29.99)]({bot_link})"
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
                    
                    # Log prediction to database
                    try:
                        import sqlite3
                        conn = sqlite3.connect('agent_memory.db')
                        cursor = conn.cursor()
                        match_name = f"{match['homeTeam']['name']} vs {match['awayTeam']['name']}"
                        prob = anomaly.get('calculated_prob', 1.0)
                        weight = anomaly.get('current_weight', 1.0)
                        
                        cursor.execute(
                            "INSERT OR REPLACE INTO historical_logs (fixture_id, match_name, calculated_prob, trigger_type, outcome, current_weight) VALUES (?, ?, ?, ?, ?, ?)",
                            (fixture_id, match_name, prob, anomaly_type, -1, weight)
                        )
                        conn.commit()
                        conn.close()
                        logging.info(f"Logged prediction to database: {match_name} ({anomaly_type}) with prob {prob:.2f} and weight {weight:.2f}")
                    except Exception as db_e:
                        logging.error(f"Error logging to SQLite: {db_e}")
            else:
                logging.info(f"Duplicate alert prevented for {alert_key}")
                
    if updated:
        save_sent_alerts(sent_alerts)

    # Perform evaluation on finished matches at the end of the run
    evaluate_concluded_matches()
    export_past_analysis()

main = run_pipeline

if __name__ == "__main__":
    run_pipeline()
