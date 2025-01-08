import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import ollama
from twitter_cli import TwitterAPI
from XEnvironment import XEnvironment, ActionType, NeedState

# Structured Input/Output Models
class ActionIntent(BaseModel):
    """Input structure for agent's intended action"""
    action_type: str = Field(..., description="Type of action to take (post, reply, like, etc)")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in this action choice")
    reasoning: str = Field(..., description="Explanation for choosing this action")
    target_needs: List[str] = Field(..., description="Needs this action aims to satisfy")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters")

class ContextAnalysis(BaseModel):
    """Output structure for analyzing current state"""
    current_needs: Dict[str, float]
    priority_need: str
    recent_metrics: Dict[str, float]
    suggested_actions: List[ActionIntent]

class ActionResult(BaseModel):
    """Output structure for action execution"""
    success: bool
    metrics_impact: Dict[str, float]
    needs_impact: Dict[str, float]
    next_wait_time: int

class XAgent:
    def __init__(self, environment: XEnvironment, model: str = "llama3.2:1b"):
        self.environment = environment
        self.model = model
        self.action_history = []
        
    async def analyze_context(self) -> ContextAnalysis:
        """Analyze current state and suggest next actions"""
        state_dict = self.environment.state.model_dump()
        
        prompt = f"""Given the current state:
        Needs: {state_dict['needs']}
        Metrics: {state_dict['metrics']}
        Recent Actions: {self.action_history[-5:] if self.action_history else 'None'}
        
        Analyze the situation and suggest next actions. Format response as JSON matching:
        {ContextAnalysis.model_json_schema()}
        """
        
        response = ollama.chat(model=self.model, messages=[
            {"role": "system", "content": "You are a Twitter engagement optimization agent."},
            {"role": "user", "content": prompt}
        ])
        
        return ContextAnalysis.model_validate_json(response['message']['content'])

    async def decide_action(self, analysis: ContextAnalysis) -> ActionIntent:
        """Decide on next action based on analysis"""
        available_actions = self.environment.get_available_actions()
        
        prompt = f"""Given the analysis:
        {analysis.model_dump_json(indent=2)}
        
        And available actions:
        {available_actions}
        
        Choose the most appropriate next action. Format response as JSON matching:
        {ActionIntent.model_json_schema()}
        """
        
        response = ollama.chat(model=self.model, messages=[
            {"role": "system", "content": "You are a Twitter engagement optimization agent."},
            {"role": "user", "content": prompt}
        ])
        
        return ActionIntent.model_validate_json(response['message']['content'])

    async def execute_action(self, intent: ActionIntent) -> ActionResult:
        """Execute chosen action and measure results"""
        pre_state = self.environment.state.model_dump()
        
        # Map intent parameters to action execution
        action_params = {}
        if intent.action_type.upper() == "POST":
            action_params["text"] = intent.parameters.get("text", "")
            if "media_path" in intent.parameters:
                action_params["media_path"] = intent.parameters["media_path"]
        elif intent.action_type.upper() == "REPLY":
            action_params["text"] = intent.parameters.get("text", "")
            action_params["reply_to_id"] = intent.parameters.get("reply_to_id")
        
        result = await self.environment.execute_action(
            ActionType[intent.action_type.upper()],
            **action_params
        )
        
        post_state = self.environment.state.model_dump()
        
        # Calculate impacts
        metrics_impact = {
            k: post_state['metrics'][k] - pre_state['metrics'][k]
            for k in pre_state['metrics']
            if isinstance(pre_state['metrics'][k], (int, float))
        }
        
        needs_impact = {
            k: post_state['needs'][k] - pre_state['needs'][k]
            for k in pre_state['needs']
        }
        
        action_result = ActionResult(
            success='error' not in result,
            metrics_impact=metrics_impact,
            needs_impact=needs_impact,
            next_wait_time=300
        )
        
        self.action_history.append({
            'intent': intent.model_dump(),
            'result': action_result.model_dump(),
            'timestamp': datetime.now().isoformat()
        })
        
        return action_result

    def generate_tweet_content(self, need_state: NeedState) -> str:
        """Generate tweet content based on current need state"""
        prompt = f"""Generate a tweet that addresses the need: {need_state.value}
        The tweet should be engaging, relevant, and under 280 characters.
        Consider our current metrics and recent actions.
        
        Recent actions: {self.action_history[-3:] if self.action_history else 'None'}
        """
        
        response = ollama.chat(model=self.model, messages=[
            {"role": "system", "content": "You are a Twitter engagement optimization agent."},
            {"role": "user", "content": prompt}
        ])
        
        return response['message']['content'].strip()

async def run_agent(debug: bool = True):
    """Main agent loop with optional debug output"""
    api = TwitterAPI()
    environment = XEnvironment(api)
    agent = XAgent(environment)
    
    print("🤖 Starting Twitter engagement agent...")
    
    try:
        while True:
            if debug:
                print("\n📊 Analyzing context...")
            analysis = await agent.analyze_context()
            
            if debug:
                print(f"Priority need: {analysis.priority_need}")
                print(f"Current needs: {analysis.current_needs}")
            
            intent = await agent.decide_action(analysis)
            
            if debug:
                print(f"\n🎯 Chosen action: {intent.action_type}")
                print(f"Confidence: {intent.confidence}")
                print(f"Reasoning: {intent.reasoning}")
            
            # If action is a post/reply, generate content
            if intent.action_type.upper() in ["POST", "REPLY"]:
                content = agent.generate_tweet_content(
                    NeedState[analysis.priority_need.upper()]
                )
                intent.parameters["text"] = content
                
                if debug:
                    print(f"\n📝 Generated content: {content}")
            
            result = await agent.execute_action(intent)
            
            if debug:
                print(f"\n✨ Action result: {'Success' if result.success else 'Failed'}")
                print(f"Metrics impact: {result.metrics_impact}")
                print(f"Needs impact: {result.needs_impact}")
                print(f"Waiting {result.next_wait_time}s before next action...")
            
            await asyncio.sleep(result.next_wait_time)
            
    except KeyboardInterrupt:
        print("\n👋 Agent stopped gracefully")
        environment.state.save_state()
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        environment.state.save_state()
        raise

if __name__ == "__main__":
    asyncio.run(run_agent())