import logging

import requests
from HalaLLM import SovereignHubLLM
from langchain.agents import AgentExecutor, AgentType, Tool, initialize_agent
from langchain_core.prompts import PromptTemplate

from app.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
API_URL = "http://localhost:8000"
SPORTS_ADAPTER = "sports_v1"

# setup the tool
def get_live_score(query: str):
    """Fake function to simulate checking ESPN"""
    return "Giants 24 - Cowboys 17 (4th Quarter)"

tools = [
    Tool(
        name="ScoreChecker",
        func=get_live_score,
        description="Useful for when you need to check current sports scores."
    )
]

logger.info("🔌 Switching Hub to Sports Mode...")
requests.post(f"{API_URL}/adapters/load", json={"adapter_name": SPORTS_ADAPTER}, timeout=15)

# initialize the Agent
llm = SovereignHubLLM(api_url=API_URL, adapter=SPORTS_ADAPTER, max_tokens=512)

# tighten the prompt to reduce over-answering
prefix = (
    "You are a sports assistant. Use the ScoreChecker tool to look up scores. "
    "Do NOT include Final Answer in the same turn as an Action. "
    "Follow the pattern: Thought -> Action -> Observation -> Thought -> Final Answer."
)

agent = initialize_agent(
    tools,
    llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
    agent_kwargs={"prefix": prefix},
    handle_parsing_errors=True,
)

# run it
logger.info("🏈 Agent Running...")
response = agent.run("Check the Giants score and tell me if they are winning.")
logger.info("Final Answer: %s", response)
