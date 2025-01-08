import unittest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile

from XEnvironment import (
    NeedState, ActionType, XMetrics, StateManager, 
    XEnvironment, TwitterAPI
)

class TestNeedState(unittest.TestCase):
    def test_decay_rates(self):
        rates = NeedState.decay_rates()
        self.assertEqual(rates[NeedState.ENGAGEMENT], 0.5)
        self.assertEqual(rates[NeedState.REACH], 0.3)
        self.assertEqual(rates[NeedState.RELEVANCE], 0.2)
        self.assertEqual(rates[NeedState.AUTHORITY], 0.1)
        self.assertEqual(rates[NeedState.CONVERSION], 0.4)

class TestXMetrics(unittest.TestCase):
    def setUp(self):
        self.metrics = XMetrics()

    def test_default_values(self):
        self.assertEqual(self.metrics.followers, 0)
        self.assertEqual(self.metrics.following, 0)
        self.assertEqual(self.metrics.tweets, 0)
        self.assertEqual(self.metrics.engagement_rate, 0.0)
        self.assertEqual(self.metrics.impression_rate, 0.0)

    def test_update_from_api_response(self):
        api_data = {
            "public_metrics": {
                "followers_count": 100,
                "following_count": 50,
                "tweet_count": 25
            }
        }
        self.metrics.update_from_api_response(api_data)
        self.assertEqual(self.metrics.followers, 100)
        self.assertEqual(self.metrics.following, 50)
        self.assertEqual(self.metrics.tweets, 25)

class TestStateManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "test_state.json"
        self.state_manager = StateManager(state_file=self.state_file)

    def test_initial_state(self):
        for need in NeedState:
            self.assertEqual(self.state_manager.needs[need], 100.0)

    def test_decay_needs(self):
        # Set initial state
        self.state_manager.needs[NeedState.ENGAGEMENT] = 100.0
        self.state_manager.last_action_time = datetime.now() - timedelta(hours=1)
        
        # Apply decay
        self.state_manager.decay_needs()
        
        # Verify decay was applied
        self.assertLess(self.state_manager.needs[NeedState.ENGAGEMENT], 100.0)
        self.assertGreaterEqual(self.state_manager.needs[NeedState.ENGAGEMENT], 0.0)

class TestXEnvironment(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_api = Mock(spec=TwitterAPI)
        
        # Setup mock API methods
        async def mock_api_call(*args, **kwargs):
            return {"data": {"id": "123"}}
            
        self.mock_api.create_tweet = mock_api_call
        self.mock_api.like_tweet = mock_api_call
        self.mock_api.follow_user = mock_api_call
        
        self.environment = XEnvironment(self.mock_api)

    def test_initialize_action_effects(self):
        effects = self.environment._initialize_action_effects()
        self.assertIn(ActionType.POST, effects)
        self.assertIn(ActionType.REPLY, effects)
        self.assertIn(ActionType.LIKE, effects)
        self.assertIn(ActionType.FOLLOW, effects)

    def test_get_available_actions(self):
        actions = self.environment.get_available_actions()
        self.assertTrue(isinstance(actions, list))
        self.assertTrue(all(isinstance(a, tuple) and len(a) == 2 for a in actions))

    async def test_execute_action(self):
        result = await self.environment.execute_action(
            ActionType.POST, 
            text="Test tweet"
        )
        self.assertIn("data", result)
        self.assertEqual(result["data"]["id"], "123")

if __name__ == '__main__':
    unittest.main() 