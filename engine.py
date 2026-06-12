import requests
import logging
import time as time_lib
from config import Config

logging.basicConfig(level=logging.INFO)

def fetch_live_world_cup_matches():
    url = f"{Config.BASE_URL}/sport/football/events/live"
    headers = {
        "X-RapidAPI-Key": Config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": Config.RAPIDAPI_HOST
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            logging.error(f"SportAPI live fixtures error: {response.status_code}")
            return []
        
        events = response.json().get("events", [])
        wc_events = []
        for e in events:
            tournament_name = e.get("tournament", {}).get("name", "").lower()
            unique_tournament_name = e.get("tournament", {}).get("uniqueTournament", {}).get("name", "").lower()
            
            is_world_cup = (
                "world cup" in tournament_name or
                "world cup" in unique_tournament_name or
                "world championship" in tournament_name or
                "world championship" in unique_tournament_name or
                "worldcup" in tournament_name or
                "worldcup" in unique_tournament_name
            )
            if is_world_cup:
                wc_events.append(e)
                
        return wc_events
    except Exception as e:
        logging.error(f"Network error fetching live fixtures: {str(e)}")
        return []

def fetch_match_statistics(fixture_id: int):
    url = f"{Config.BASE_URL}/event/{fixture_id}/statistics"
    headers = {
        "X-RapidAPI-Key": Config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": Config.RAPIDAPI_HOST
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("statistics", [])
        return []
    except Exception as e:
        logging.error(f"Error fetching stats for event {fixture_id}: {str(e)}")
        return []

def analyze_match_anomalies(fixture_data: dict):
    fixture_id = fixture_data['id']
    home_team = fixture_data['homeTeam']['name']
    away_team = fixture_data['awayTeam']['name']
    
    home_goals = fixture_data.get('homeScore', {}).get('current')
    away_goals = fixture_data.get('awayScore', {}).get('current')
    home_goals = home_goals if home_goals is not None else 0
    away_goals = away_goals if away_goals is not None else 0
    
    # SofaScore referee format
    referee = fixture_data.get('referee', {})
    referee_name = referee.get('name', 'Unknown')
    
    # Calculate elapsed time dynamically
    current_ts = int(time_lib.time())
    status_desc = fixture_data.get('status', {}).get('description', '')
    
    if status_desc == '1st half':
        start_ts = fixture_data.get('startTimestamp', current_ts)
        elapsed_time = (current_ts - start_ts) // 60
        elapsed_time = min(max(elapsed_time, 0), 45)
    elif status_desc == '2nd half':
        time_info = fixture_data.get('time', {})
        period_start = time_info.get('currentPeriodStartTimestamp')
        if period_start:
            elapsed_time = 45 + (current_ts - period_start) // 60
        else:
            start_ts = fixture_data.get('startTimestamp', current_ts)
            elapsed_time = (current_ts - start_ts) // 60
        elapsed_time = min(max(elapsed_time, 45), 90)
    elif status_desc == 'Halftime':
        elapsed_time = 45
    else:
        # Default fallback or estimation
        start_ts = fixture_data.get('startTimestamp', current_ts)
        elapsed_time = (current_ts - start_ts) // 60
        elapsed_time = min(max(elapsed_time, 0), 90)
        
    metrics = {
        "home_shots_on_goal": 0, "away_shots_on_goal": 0,
        "home_possession": 50, "away_possession": 50,
        "home_corners": 0, "away_corners": 0,
        "home_yellow_cards": 0, "away_yellow_cards": 0,
        "home_red_cards": 0, "away_red_cards": 0
    }
    
    # Fetch true real-time stats array explicitly
    stats_payload = fetch_match_statistics(fixture_id)
    if not stats_payload:
        return None 
        
    # Get period "ALL" (overall match stats)
    all_period = None
    for period_data in stats_payload:
        if period_data.get("period") == "ALL":
            all_period = period_data
            break
    if not all_period and stats_payload:
        all_period = stats_payload[0]
        
    if all_period:
        for group in all_period.get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key")
                
                # SofaScore provides values directly as homeValue / awayValue (or home / away as strings)
                home_val = item.get("homeValue")
                away_val = item.get("awayValue")
                if home_val is None:
                    home_val = item.get("home", 0)
                if away_val is None:
                    away_val = item.get("away", 0)
                
                if isinstance(home_val, str):
                    home_val = int(home_val.replace("%", ""))
                if isinstance(away_val, str):
                    away_val = int(away_val.replace("%", ""))
                    
                if key == "ballPossession":
                    metrics["home_possession"] = home_val
                    metrics["away_possession"] = away_val
                elif key == "cornerKicks":
                    metrics["home_corners"] = home_val
                    metrics["away_corners"] = away_val
                elif key == "yellowCards":
                    metrics["home_yellow_cards"] = home_val
                    metrics["away_yellow_cards"] = away_val
                elif key == "redCards":
                    metrics["home_red_cards"] = home_val
                    metrics["away_red_cards"] = away_val
                elif key == "shotsOnGoal":
                    metrics["home_shots_on_goal"] = home_val
                    metrics["away_shots_on_goal"] = away_val

    home_red_cards = metrics['home_red_cards']
    away_red_cards = metrics['away_red_cards']
    total_yellow = metrics['home_yellow_cards'] + metrics['away_yellow_cards']

    # 🧠 Algorithmic Anomalies
    is_red_card_anomaly = (home_red_cards >= 1 or away_red_cards >= 1)
    
    is_pressure_anomaly = (
        20 <= elapsed_time <= 75 and
        home_goals == 0 and away_goals == 0 and
        ((metrics['home_shots_on_goal'] >= 4 and metrics['home_possession'] >= 62) or 
         (metrics['away_shots_on_goal'] >= 4 and metrics['away_possession'] >= 62))
    )
    
    total_corners = metrics['home_corners'] + metrics['away_corners']
    is_corner_anomaly = (30 <= elapsed_time <= 60 and total_corners >= 7)

    is_card_blitz_anomaly = (
        elapsed_time <= 80 and
        (
            (elapsed_time <= 45 and total_yellow >= 4) or
            (elapsed_time > 45 and total_yellow >= 7)
        )
    )

    if is_red_card_anomaly:
        team_with_red = home_team if home_red_cards >= 1 else away_team
        return {
            "type": "RED_CARD_ANOMALY",
            "message": (
                "🟥 *RED CARD ALERT* 🟥\n\n"
                f"🏟️ *Match*: {home_team} vs {away_team}\n"
                f"⏱️ *Time*: Minute {elapsed_time}'\n"
                f"📊 *Score*: {home_goals} - {away_goals}\n"
                f"👤 Referee: {referee_name}\n\n"
                f"🚨 Red Card Issued to: *{team_with_red}*\n\n"
                f"💡 *Data Science Indicator*: Severe dynamic shift. The short-handed team is mathematically projected to face massive defensive pressure. Monitor live totals."
            )
        }

    if is_pressure_anomaly:
        dominant_team = home_team if metrics['home_possession'] > metrics['away_possession'] else away_team
        return {
            "type": "PRESSURE_ANOMALY",
            "message": (
                "⚠️ *LIVE WORLD CUP ANOMALY DETECTED* ⚠️\n\n"
                f"🏟️ *Match*: {home_team} vs {away_team}\n"
                f"⏱️ *Time*: Minute {elapsed_time}'\n"
                f"📊 *Score*: {home_goals} - {away_goals}\n"
                f"👤 Referee: {referee_name}\n\n"
                f"🔥 Dominant Side: *{dominant_team}*\n"
                f"📈 Possession: Home {metrics['home_possession']}% | Away {metrics['away_possession']}%\n"
                f"🎯 Shots On Goal: Home {metrics['home_shots_on_goal']} | Away {metrics['away_shots_on_goal']}\n\n"
                f"💡 *Data Science Indicator*: Strong attacking dominance implies high mathematical probability of a breakthrough goal shortly."
            )
        }
        
    if is_corner_anomaly:
        return {
            "type": "CORNER_ANOMALY",
            "message": (
                "🚩 *LIVE MATCH ALERT: CORNER BLITZ* 🚩\n\n"
                f"🏟️ *Match*: {home_team} vs {away_team}\n"
                f"⏱️ *Time*: Minute {elapsed_time}'\n"
                f"📊 Total Match Corners: *{total_corners}* (Extremely high rate for current window)\n"
                f"👤 Referee: {referee_name}\n\n"
                f"💡 *Data Science Indicator*: Fast wing transitions present. Check Live Over Corner options."
            )
        }

    if is_card_blitz_anomaly:
        return {
            "type": "CARD_BLITZ",
            "message": (
                "🟨 *CARD BLITZ WARNING* 🟨\n\n"
                f"🏟️ *Match*: {home_team} vs {away_team}\n"
                f"⏱️ *Time*: Minute {elapsed_time}'\n"
                f"📊 Total Yellow Cards: *{total_yellow}* (Highly physical rate)\n"
                f"👤 Referee: {referee_name}\n\n"
                f"💡 *Data Science Indicator*: Fast-building disciplinary pressure. High statistical likelihood of a red card or massive card total. Check Live Card options."
            )
        }
        
    return None
