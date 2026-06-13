import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import time as time_lib

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
import bot
import engine
import main

class TestWorldCupBot(unittest.TestCase):
    
    def setUp(self):
        # Clear files before each test
        for f in [main.SCHEDULE_FILE, main.SENT_ALERTS_FILE, engine.FEEDBACK_FILE, "agent_memory.db"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def tearDown(self):
        # Clean up files after each test
        for f in [main.SCHEDULE_FILE, main.SENT_ALERTS_FILE, engine.FEEDBACK_FILE, "agent_memory.db"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    @patch('bot.requests.post')
    def test_send_telegram_alert_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        Config.TELEGRAM_BOT_TOKEN = "mock_token"
        Config.FREE_CHANNEL_ID = "mock_free_id"
        Config.PREMIUM_CHANNEL_ID = "mock_premium_id"
        
        result = bot.send_telegram_alert("Hello world", is_premium=False)
        self.assertTrue(result)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("botmock_token/sendMessage", args[0])
        self.assertEqual(kwargs['json']['chat_id'], "mock_free_id")

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_pressure(self, mock_stats):
        # Set up mock statistics for pressure anomaly (possession 65%, shots 5)
        # dominance_index = (65*0.4) + (5*1.5) = 33.5 (<= 68, so doesn't trigger HIGH_YIELD)
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 65, "awayValue": 35},
                            {"key": "shotsOnGoal", "homeValue": 5, "awayValue": 1},
                            {"key": "cornerKicks", "homeValue": 2, "awayValue": 1}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 35 * 60, # 35 minutes ago
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "PRESSURE_ANOMALY")
        self.assertFalse(anomaly['premium'])
        self.assertIn("ANOMALY DETECTED", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_corners(self, mock_stats):
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 50, "awayValue": 50},
                            {"key": "shotsOnGoal", "homeValue": 2, "awayValue": 2},
                            {"key": "cornerKicks", "homeValue": 4, "awayValue": 4}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 40 * 60,
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "CORNER_ANOMALY")
        self.assertFalse(anomaly['premium'])
        self.assertIn("CORNER BLITZ", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_red_card(self, mock_stats):
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "yellowCards", "homeValue": 1, "awayValue": 2},
                            {"key": "redCards", "homeValue": 0, "awayValue": 1}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "2nd half"},
            "time": {"currentPeriodStartTimestamp": current_ts - 15 * 60}, # 60th minute total
            "referee": {"name": "Ivan Barton"},
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 1},
            "awayScore": {"current": 1}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "RED_CARD_ANOMALY")
        self.assertFalse(anomaly['premium'])
        self.assertIn("RED CARD ALERT", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_card_blitz(self, mock_stats):
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "yellowCards", "homeValue": 2, "awayValue": 2},
                            {"key": "redCards", "homeValue": 0, "awayValue": 0}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 30 * 60,
            "referee": {"name": "Slavko Vincic"},
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "CARD_BLITZ")
        self.assertFalse(anomaly['premium'])
        self.assertIn("CARD BLITZ WARNING", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_whale_vault(self, mock_stats):
        # Set up mock statistics for Whale Vault (2-0 lead, elapsed 75)
        # dominance_index = (70*0.4) + (10*1.5) = 43.0
        # calculate_live_probability(75, 43, 2, 0) -> differential 2, time factor 0.83 -> prob = 0.95 (> 0.92)
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 70, "awayValue": 30},
                            {"key": "shotsOnGoal", "homeValue": 10, "awayValue": 1}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "2nd half"},
            "time": {"currentPeriodStartTimestamp": current_ts - 30 * 60}, # 75th minute
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 2},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "WHALE_VAULT")
        self.assertTrue(anomaly['premium'])
        self.assertIn("WHALE VAULT: MAX STAKE SURE SIGNAL", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_analyze_match_anomalies_high_yield(self, mock_stats):
        # Set up mock statistics for High Yield (scoreless, min 35, dominance > 68)
        # dominance_index = (70*0.4) + (28*1.5) = 28 + 42 = 70.0 (> 68)
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 70, "awayValue": 30},
                            {"key": "shotsOnGoal", "homeValue": 28, "awayValue": 0}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 35 * 60, # 35th minute
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "HIGH_YIELD")
        self.assertTrue(anomaly['premium'])
        self.assertIn("HIGH-YIELD VALUE RADAR", anomaly['message'])

    @patch('main.load_schedule')
    @patch('main.fetch_live_world_cup_matches')
    def test_main_no_games_today(self, mock_live, mock_schedule):
        mock_schedule.return_value = [
            {
                "id": 999,
                "tournament": {
                    "name": "World Cup",
                    "uniqueTournament": {"name": "World Cup"}
                },
                "startTimestamp": 1000000000
            }
        ]
        
        with patch('main.logging.info') as mock_log:
            main.main()
            mock_log.assert_any_call("API Guardrail: No World Cup matches scheduled for today. Exiting.")
            mock_live.assert_not_called()

    def test_load_feedback_bias_defaults(self):
        bias = engine.load_feedback_bias("WHALE_VAULT")
        self.assertEqual(bias, 0.0)

    def test_load_feedback_bias_loaded(self):
        import json
        dummy = {
            "WHALE_VAULT": {"successes": 5, "failures": 1, "bias_adjustment": 0.03}
        }
        with open(engine.FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(dummy, f)
        
        bias = engine.load_feedback_bias("WHALE_VAULT")
        self.assertEqual(bias, 0.03)
        bias_missing = engine.load_feedback_bias("HIGH_YIELD")
        self.assertEqual(bias_missing, 0.0)

    def test_calculate_live_probability_with_bias(self):
        # Base probability with differential = 1, dominance > 75, time > 0.80 -> 0.93
        # dominance_index = 80, elapsed = 85 (time_factor = 0.94), lead = 1
        prob_no_bias = engine.calculate_live_probability(85, 80, 2, 1, bias_adjustment=0.0)
        self.assertAlmostEqual(prob_no_bias, 0.93, places=4)
        
        prob_with_bias = engine.calculate_live_probability(85, 80, 2, 1, bias_adjustment=0.03)
        self.assertAlmostEqual(prob_with_bias, 0.96, places=4)

    @patch('engine.fetch_match_statistics')
    def test_high_yield_threshold_adjustments(self, mock_stats):
        # Set up mock statistics for High Yield (scoreless, min 35, dominance = 65.0)
        # dominance_index = (50*0.4) + (30*1.5) = 20 + 45 = 65.0
        # If bias is 0.0, threshold is 68.0 -> dominance 65.0 < 68.0 (No trigger)
        # If bias is 0.4, threshold is 68.0 - 4.0 = 64.0 -> dominance 65.0 > 64.0 (Triggers!)
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 50, "awayValue": 50},
                            {"key": "shotsOnGoal", "homeValue": 30, "awayValue": 0}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 456,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 35 * 60,
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        # Test with no bias (should return None since 65 < 68)
        with patch('engine.load_feedback_bias', return_value=0.0):
            anomaly = engine.analyze_match_anomalies(fixture_data)
            self.assertIsNone(anomaly)
            
        # Test with positive bias (should return HIGH_YIELD since 65 > 64)
        with patch('engine.load_feedback_bias', return_value=0.4):
            anomaly = engine.analyze_match_anomalies(fixture_data)
            self.assertIsNotNone(anomaly)
            self.assertEqual(anomaly['type'], "HIGH_YIELD")

    @patch('main.fetch_match_incidents')
    def test_evaluate_concluded_matches_success(self, mock_incidents):
        import json
        # Setup finished matches schedule
        schedule_data = [
            {
                "id": 111,
                "status": {"type": "finished"},
                "homeScore": {"current": 2},
                "awayScore": {"current": 0},
                "homeTeam": {"name": "Team A"},
                "awayTeam": {"name": "Team B"},
                "tournament": {"name": "World Cup", "uniqueTournament": {"name": "World Cup"}}
            },
            {
                "id": 222,
                "status": {"type": "finished"},
                "homeScore": {"current": 1},
                "awayScore": {"current": 1},
                "homeTeam": {"name": "Team C"},
                "awayTeam": {"name": "Team D"},
                "tournament": {"name": "World Cup", "uniqueTournament": {"name": "World Cup"}}
            }
        ]
        with open(main.SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(schedule_data, f)
            
        # Setup sent alerts
        # 111_WHALE_VAULT: predicted home (which won 2-0) -> Success
        # 222_PRESSURE_ANOMALY: alert minute 40, goal scored minute 55 -> Success
        sent_alerts = {
            "111_WHALE_VAULT": {
                "timestamp": "2026-06-13T00:00:00Z",
                "evaluated": False,
                "minute": 70,
                "type": "WHALE_VAULT",
                "predicted_winner": "home"
            },
            "222_PRESSURE_ANOMALY": {
                "timestamp": "2026-06-13T00:00:00Z",
                "evaluated": False,
                "minute": 40,
                "type": "PRESSURE_ANOMALY"
            }
        }
        with open(main.SENT_ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(sent_alerts, f)
            
        # Mock incidents for 222: Goal at 55
        mock_incidents.return_value = [
            {"incidentType": "goal", "time": 55, "isHome": True}
        ]
        
        main.evaluate_concluded_matches()
        
        # Check sent alerts updated
        with open(main.SENT_ALERTS_FILE, "r", encoding="utf-8") as f:
            alerts_after = json.load(f)
        self.assertTrue(alerts_after["111_WHALE_VAULT"]["evaluated"])
        self.assertTrue(alerts_after["111_WHALE_VAULT"]["success"])
        self.assertTrue(alerts_after["222_PRESSURE_ANOMALY"]["evaluated"])
        self.assertTrue(alerts_after["222_PRESSURE_ANOMALY"]["success"])
        
        # Check feedback loop bias increased
        with open(engine.FEEDBACK_FILE, "r", encoding="utf-8") as f:
            feedback = json.load(f)
        self.assertEqual(feedback["WHALE_VAULT"]["successes"], 1)
        self.assertAlmostEqual(feedback["WHALE_VAULT"]["bias_adjustment"], 0.01)
        self.assertEqual(feedback["PRESSURE_ANOMALY"]["successes"], 1)
        self.assertAlmostEqual(feedback["PRESSURE_ANOMALY"]["bias_adjustment"], 0.01)

    @patch('main.fetch_match_incidents')
    def test_evaluate_concluded_matches_failure(self, mock_incidents):
        import json
        # Setup finished matches schedule
        schedule_data = [
            {
                "id": 111,
                "status": {"type": "finished"},
                "homeScore": {"current": 0},
                "awayScore": {"current": 2},
                "homeTeam": {"name": "Team A"},
                "awayTeam": {"name": "Team B"},
                "tournament": {"name": "World Cup", "uniqueTournament": {"name": "World Cup"}}
            },
            {
                "id": 222,
                "status": {"type": "finished"},
                "homeScore": {"current": 0},
                "awayScore": {"current": 0},
                "homeTeam": {"name": "Team C"},
                "awayTeam": {"name": "Team D"},
                "tournament": {"name": "World Cup", "uniqueTournament": {"name": "World Cup"}}
            }
        ]
        with open(main.SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(schedule_data, f)
            
        # Setup sent alerts
        # 111_WHALE_VAULT: predicted home (which lost 0-2) -> Failure
        # 222_PRESSURE_ANOMALY: alert minute 40, no goals scored (0-0) -> Failure (evaluated immediately since score is 0-0)
        sent_alerts = {
            "111_WHALE_VAULT": {
                "timestamp": "2026-06-13T00:00:00Z",
                "evaluated": False,
                "minute": 70,
                "type": "WHALE_VAULT",
                "predicted_winner": "home"
            },
            "222_PRESSURE_ANOMALY": {
                "timestamp": "2026-06-13T00:00:00Z",
                "evaluated": False,
                "minute": 40,
                "type": "PRESSURE_ANOMALY"
            }
        }
        with open(main.SENT_ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(sent_alerts, f)
            
        # Mock incidents should not even be called for 222 since score is 0-0,
        # but let's make sure it returns empty if called
        mock_incidents.return_value = []
        
        main.evaluate_concluded_matches()
        
        # Check sent alerts updated
        with open(main.SENT_ALERTS_FILE, "r", encoding="utf-8") as f:
            alerts_after = json.load(f)
        self.assertTrue(alerts_after["111_WHALE_VAULT"]["evaluated"])
        self.assertFalse(alerts_after["111_WHALE_VAULT"]["success"])
        self.assertTrue(alerts_after["222_PRESSURE_ANOMALY"]["evaluated"])
        self.assertFalse(alerts_after["222_PRESSURE_ANOMALY"]["success"])
        
        # Check feedback loop bias decreased
        with open(engine.FEEDBACK_FILE, "r", encoding="utf-8") as f:
            feedback = json.load(f)
        self.assertEqual(feedback["WHALE_VAULT"]["failures"], 1)
        self.assertAlmostEqual(feedback["WHALE_VAULT"]["bias_adjustment"], -0.02)
        self.assertEqual(feedback["PRESSURE_ANOMALY"]["failures"], 1)
        self.assertAlmostEqual(feedback["PRESSURE_ANOMALY"]["bias_adjustment"], -0.02)

    def test_sqlite_initialization_and_weights(self):
        import backtest_handler
        import sqlite3
        
        backtest_handler.initialize_memory_db()
        self.assertTrue(os.path.exists("agent_memory.db"))
        
        # Test default weight
        self.assertEqual(backtest_handler.get_current_weight("WHALE_VAULT"), 1.0)
        
        # Mock insert prediction
        conn = sqlite3.connect('agent_memory.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO historical_logs (fixture_id, match_name, calculated_prob, trigger_type, outcome, current_weight) VALUES (?, ?, ?, ?, ?, ?)",
            (999, "Test vs Mock", 0.95, "WHALE_VAULT", -1, 1.0)
        )
        conn.commit()
        conn.close()
        
        # Reward outcome (hit and prob >= 0.85) -> min(1.25, weight + 0.05)
        new_w = backtest_handler.evaluate_and_adjust_weights(999, "WHALE_VAULT", 1)
        self.assertAlmostEqual(new_w, 1.05)
        self.assertAlmostEqual(backtest_handler.get_current_weight("WHALE_VAULT"), 1.05)

        # Mock penalty prediction (fail and prob >= 0.90) -> max(0.50, weight - 0.15)
        conn = sqlite3.connect('agent_memory.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO historical_logs (fixture_id, match_name, calculated_prob, trigger_type, outcome, current_weight) VALUES (?, ?, ?, ?, ?, ?)",
            (888, "Test vs Mock 2", 0.92, "HIGH_YIELD", -1, 1.0)
        )
        conn.commit()
        conn.close()
        
        new_w2 = backtest_handler.evaluate_and_adjust_weights(888, "HIGH_YIELD", 0)
        self.assertAlmostEqual(new_w2, 0.85)
        self.assertAlmostEqual(backtest_handler.get_current_weight("HIGH_YIELD"), 0.85)

    @patch('engine.fetch_match_statistics')
    def test_kelly_criterion_stake_whale(self, mock_stats):
        import backtest_handler
        backtest_handler.initialize_memory_db()
        
        # Lead by 2 goals, elapsed 75 -> base_prob = 0.95.
        # If weight is 1.0 -> prob = 0.95. Goal diff >= 2 -> odds = 1.08 -> b = 0.08.
        # f* = (0.95 * 1.08 - 1) / 0.08 = 0.325 (32.5% allocation) -> >= 0.08 -> MAX STAKE label
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 70, "awayValue": 30},
                            {"key": "shotsOnGoal", "homeValue": 10, "awayValue": 1}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 777,
            "status": {"description": "2nd half"},
            "time": {"currentPeriodStartTimestamp": current_ts - 30 * 60}, # 75th minute
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 2},
            "awayScore": {"current": 0}
        }
        
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "WHALE_VAULT")
        self.assertIn("MAX STAKE / HIGH ASSET ALLOCATION", anomaly['message'])
        self.assertIn("Kelly Allocation", anomaly['message'])
        self.assertIn("32.5%", anomaly['message'])

    @patch('engine.fetch_match_statistics')
    def test_weight_throttling_guardrail(self, mock_stats):
        import backtest_handler
        import sqlite3
        backtest_handler.initialize_memory_db()
        
        # Setup mock stats that triggers PRESSURE_ANOMALY
        mock_stats.return_value = [
            {
                "period": "ALL",
                "groups": [
                    {
                        "groupName": "Match overview",
                        "statisticsItems": [
                            {"key": "ballPossession", "homeValue": 65, "awayValue": 35},
                            {"key": "shotsOnGoal", "homeValue": 5, "awayValue": 1},
                            {"key": "cornerKicks", "homeValue": 2, "awayValue": 1}
                        ]
                    }
                ]
            }
        ]
        
        current_ts = int(time_lib.time())
        fixture_data = {
            "id": 123,
            "status": {"description": "1st half"},
            "startTimestamp": current_ts - 35 * 60,
            "homeTeam": {"name": "Team A"},
            "awayTeam": {"name": "Team B"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0}
        }
        
        # Normal weight 1.0 triggers pressure anomaly
        anomaly = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly['type'], "PRESSURE_ANOMALY")
        
        # Inject weight 0.65 (under 0.70 throttle boundary)
        conn = sqlite3.connect('agent_memory.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO historical_logs (fixture_id, match_name, calculated_prob, trigger_type, outcome, current_weight) VALUES (?, ?, ?, ?, ?, ?)",
            (1122, "Dummy", 0.90, "PRESSURE_ANOMALY", 0, 0.65)
        )
        conn.commit()
        conn.close()
        
        # Weight under 0.70 should mute the pressure anomaly alert (return None)
        anomaly_throttled = engine.analyze_match_anomalies(fixture_data)
        self.assertIsNone(anomaly_throttled)

    def test_brier_score_calculation(self):
        import backtest_handler
        import sqlite3
        backtest_handler.initialize_memory_db()
        
        conn = sqlite3.connect('agent_memory.db')
        cursor = conn.cursor()
        # Predictions:
        # Match 1: prob 0.90, outcome 1 (error 0.10, sq_error 0.01)
        # Match 2: prob 0.80, outcome 0 (error 0.80, sq_error 0.64)
        # Brier Score should be (0.01 + 0.64) / 2 = 0.325
        cursor.executemany(
            "INSERT INTO historical_logs (fixture_id, match_name, calculated_prob, trigger_type, outcome, current_weight) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "M1", 0.90, "WHALE_VAULT", 1, 1.0),
                (2, "M2", 0.80, "HIGH_YIELD", 0, 1.0)
            ]
        )
        conn.commit()
        conn.close()
        
        bs = backtest_handler.calculate_brier_score()
        self.assertAlmostEqual(bs, 0.325)

if __name__ == '__main__':
    unittest.main()
