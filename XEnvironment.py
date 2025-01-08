from typing import Dict, List, Optional, Set, Any, Tuple
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import random

# Import your existing Twitter CLI implementation
from twitter_cli import TwitterAPI, TwitterAuth

class NeedState(Enum):
    """Core advertiser needs that drive behavior"""
    ENGAGEMENT = "engagement"
    REACH = "reach"
    RELEVANCE = "relevance"
    AUTHORITY = "authority"
    CONVERSION = "conversion"

    @classmethod
    def decay_rates(cls) -> Dict["NeedState", float]:
        """Define how quickly each need decays"""
        return {
            cls.ENGAGEMENT: 0.5,
            cls.REACH: 0.3,
            cls.RELEVANCE: 0.2,
            cls.AUTHORITY: 0.1,
            cls.CONVERSION: 0.4
        }

class ActionType(Enum):
    """Available actions mapped to API endpoints"""
    POST = "post"
    REPLY = "reply"
    QUOTE = "quote"
    RETWEET = "retweet"
    LIKE = "like"
    FOLLOW = "follow"
    SEARCH = "search"

class XMetrics(BaseModel):
    """Performance metrics tracker"""
    followers: int = Field(default=0)
    following: int = Field(default=0)
    tweets: int = Field(default=0)
    engagement_rate: float = Field(default=0.0)
    impression_rate: float = Field(default=0.0)
    last_updated: datetime = Field(default_factory=datetime.now)

    def update_from_api_response(self, api_data: Dict[str, Any]) -> None:
        """Update metrics from API response data"""
        if "public_metrics" in api_data:
            metrics = api_data["public_metrics"]
            self.followers = metrics.get("followers_count", self.followers)
            self.following = metrics.get("following_count", self.following)
            self.tweets = metrics.get("tweet_count", self.tweets)
        self.last_updated = datetime.now()

    def model_dump(self, *args, **kwargs) -> Dict[str, Any]:
        """Override model_dump method to handle datetime serialization"""
        d = super().model_dump(*args, **kwargs)
        d["last_updated"] = self.last_updated.isoformat()
        return d

class StateManager(BaseModel):
    """Manages state persistence and updates"""
    needs: Dict[NeedState, float] = Field(
        default_factory=lambda: {need: 100.0 for need in NeedState}
    )
    metrics: XMetrics = Field(default_factory=XMetrics)
    last_action_time: datetime = Field(default_factory=datetime.now)
    state_file: Path = Field(default=Path.home() / ".twitter_state.json")

    def save_state(self) -> None:
        """Persist current state to disk"""
        state_dict = {
            "needs": {k.value: v for k, v in self.needs.items()},
            "metrics": self.metrics.model_dump(),
            "last_action_time": self.last_action_time.isoformat()
        }
        self.state_file.write_text(json.dumps(state_dict))

    def load_state(self) -> None:
        """Load state from disk if exists"""
        if self.state_file.exists():
            state_dict = json.loads(self.state_file.read_text())
            self.needs = {NeedState(k): v for k, v in state_dict["needs"].items()}
            self.metrics = XMetrics(**state_dict["metrics"])
            self.last_action_time = datetime.fromisoformat(state_dict["last_action_time"])

    def decay_needs(self) -> None:
        """Apply time-based decay to needs"""
        time_delta = datetime.now() - self.last_action_time
        decay_hours = time_delta.total_seconds() / 3600

        for need, rate in NeedState.decay_rates().items():
            decay = rate * decay_hours
            self.needs[need] = max(0.0, self.needs[need] - decay)

    def model_dump(self, *args, **kwargs) -> Dict[str, Any]:
        """Override model_dump method to handle datetime serialization"""
        d = super().model_dump(*args, **kwargs)
        d["last_action_time"] = self.last_action_time.isoformat()
        d["metrics"] = self.metrics.model_dump()
        return d

class XEnvironment:
    """Twitter environment with needs-based state management"""
    def __init__(self, api: TwitterAPI):
        self.api = api
        self.state = StateManager()
        self.state.load_state()
        self.action_effects = self._initialize_action_effects()
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("XEnvironment")

    def _initialize_action_effects(self) -> Dict[ActionType, Dict[NeedState, float]]:
        """Define how actions affect needs"""
        return {
            ActionType.POST: {
                NeedState.ENGAGEMENT: 15.0,
                NeedState.REACH: 10.0,
                NeedState.RELEVANCE: 5.0
            },
            ActionType.REPLY: {
                NeedState.ENGAGEMENT: 20.0,
                NeedState.AUTHORITY: 5.0
            },
            ActionType.LIKE: {
                NeedState.ENGAGEMENT: 5.0,
                NeedState.RELEVANCE: 2.0
            },
            ActionType.FOLLOW: {
                NeedState.REACH: 10.0,
                NeedState.AUTHORITY: 5.0
            }
        }

    def get_available_actions(self) -> List[Tuple[ActionType, float]]:
        """Return available actions with their utility scores"""
        self.state.decay_needs()
        actions = []
        
        for action in ActionType:
            if action in self.action_effects:
                utility = sum(
                    effect * (1.0 - self.state.needs[need] / 100.0)
                    for need, effect in self.action_effects[action].items()
                )
                actions.append((action, utility))
        
        return sorted(actions, key=lambda x: x[1], reverse=True)

    async def execute_action(self, action: ActionType, **kwargs) -> Dict[str, Any]:
        """Execute an action and update state"""
        self.logger.info(f"Executing action: {action.value}")
        
        try:
            result = await self._perform_api_action(action, **kwargs)
            
            if "error" not in result:
                self._update_state_from_action(action)
                self.state.save_state()
            
            return result
        except Exception as e:
            self.logger.error(f"Action execution failed: {str(e)}")
            return {"error": str(e)}

    async def _perform_api_action(self, action: ActionType, **kwargs) -> Dict[str, Any]:
        """Map environment actions to API calls"""
        api_actions = {
            ActionType.POST: self.api.create_tweet,
            ActionType.REPLY: lambda **kw: self.api.create_tweet(reply_to_id=kw.get("reply_to_id"), **kw),
            ActionType.LIKE: self.api.like_tweet,
            ActionType.FOLLOW: self.api.follow_user
        }
        
        if action not in api_actions:
            raise ValueError(f"Unsupported action: {action}")
            
        return await api_actions[action](**kwargs)

    def _update_state_from_action(self, action: ActionType) -> None:
        """Update needs based on action effects"""
        if action in self.action_effects:
            for need, effect in self.action_effects[action].items():
                self.state.needs[need] = min(100.0, self.state.needs[need] + effect)
        
        self.state.last_action_time = datetime.now()

class AdvertiserAgent:
    """Autonomous agent that operates in the X environment"""
    def __init__(self, environment: XEnvironment):
        self.environment = environment
        self.logger = logging.getLogger("AdvertiserAgent")

    async def run_cycle(self) -> None:
        """Execute one decision-making cycle"""
        available_actions = self.environment.get_available_actions()
        
        if not available_actions:
            self.logger.info("No actions available")
            return

        chosen_action, utility = available_actions[0]
        self.logger.info(f"Selected action {chosen_action.value} with utility {utility:.2f}")
        
        await self.environment.execute_action(chosen_action)

async def main():
    """Initialize environment and agent"""
    api = TwitterAPI()
    environment = XEnvironment(api)
    agent = AdvertiserAgent(environment)
    return environment, agent

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())