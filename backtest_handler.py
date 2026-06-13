import sqlite3
import logging

logging.basicConfig(level=logging.INFO)

def initialize_memory_db():
    """Sets up local lightweight relational storage for tracking past hits."""
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historical_logs (
            fixture_id INTEGER,
            match_name TEXT,
            calculated_prob REAL,
            trigger_type TEXT,
            outcome INTEGER DEFAULT -1,
            current_weight REAL,
            PRIMARY KEY (fixture_id, trigger_type)
        )
    ''')
    conn.commit()
    conn.close()

def get_current_weight(trigger_type: str) -> float:
    """Retrieves the latest METRIC_CONFIDENCE_WEIGHT for a given trigger type."""
    initialize_memory_db()
    try:
        conn = sqlite3.connect('agent_memory.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT current_weight FROM historical_logs WHERE trigger_type=? AND outcome != -1 ORDER BY rowid DESC LIMIT 1",
            (trigger_type,)
        )
        row = cursor.fetchone()
        conn.close()
        if row is not None:
            return row[0]
    except Exception as e:
        logging.error(f"Error reading weight from SQLite: {e}")
    return 1.0

def evaluate_and_adjust_weights(fixture_id: int, trigger_type: str, real_outcome: int):
    """
    Applies the exact Markdown Penalty/Reward parameters directly into database vectors
    """
    initialize_memory_db()
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    
    # Extract prediction state
    cursor.execute(
        "SELECT calculated_prob, current_weight FROM historical_logs WHERE fixture_id=? AND trigger_type=?",
        (fixture_id, trigger_type)
    )
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
        
    prob, weight = row
    new_weight = weight
    
    # Apply Markdown Logic parameters explicitly
    if real_outcome == 1 and prob >= 0.85:
        new_weight = min(1.25, weight + 0.05)
        logging.info(f"🏆 REWARD SYSTEM: {trigger_type} hit. Weight increased to {new_weight:.2f}")
    elif real_outcome == 0 and prob >= 0.90:
        new_weight = max(0.50, weight - 0.15)
        logging.warning(f"💥 PENALTY SYSTEM: {trigger_type} failed. Weight throttled to {new_weight:.2f}")
        
    cursor.execute(
        "UPDATE historical_logs SET outcome=?, current_weight=? WHERE fixture_id=? AND trigger_type=?",
        (real_outcome, new_weight, fixture_id, trigger_type)
    )
    conn.commit()
    conn.close()
    return new_weight

def calculate_brier_score() -> float:
    """Computes the overall Brier Score for all evaluated matches in the database."""
    initialize_memory_db()
    try:
        conn = sqlite3.connect('agent_memory.db')
        cursor = conn.cursor()
        cursor.execute("SELECT calculated_prob, outcome FROM historical_logs WHERE outcome != -1")
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return 0.0
        
        squared_errors = [(prob - outcome) ** 2 for prob, outcome in rows]
        return sum(squared_errors) / len(squared_errors)
    except Exception as e:
        logging.error(f"Error calculating Brier Score: {e}")
        return 0.0
