import logging
import os

import requests
from HalaLLM import SovereignHubLLM
from langchain.agents import AgentExecutor, AgentType, Tool, initialize_agent
from langchain_core.prompts import PromptTemplate

API_URL = os.getenv("HALA_API_URL", "http://localhost:8000")
# Default to "default" so the adapter load succeeds out-of-the-box.
SPORTS_ADAPTER = os.getenv("SPORTS_ADAPTER", "default")

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

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

logger.info("🔌 Switching Hub to Sports Mode (adapter=%s)...", SPORTS_ADAPTER)
resp = requests.post(f"{API_URL}/adapters/load", json={"adapter_name": SPORTS_ADAPTER}, timeout=15)
if resp.status_code == 404:
    logger.warning(
        "Adapter '%s' not found on the server. Using base model instead. "
        "Set SPORTS_ADAPTER to a valid adapter folder if available.",
        SPORTS_ADAPTER,
    )

# initialize the Agent
llm = SovereignHubLLM(api_url=API_URL, adapter=SPORTS_ADAPTER, max_tokens=512, priority=1)

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
# logger.info("🏈 Agent Running...")
response = agent.run("Check the Giants score and tell me if they are winning.")
# logger.info("Final Answer: %s", response)
