import os
from typing import Any, List, Optional, Mapping

import requests
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM

class SovereignHubLLM(LLM):
    """
    A custom LangChain wrapper for your Sovereign AI Hub.
    Allows you to use Qwen 2.5 14B with LangChain Agents.
    """
    
    api_url: str = os.getenv("HALA_API_URL", "http://localhost:8000")
    adapter: str = "default"
    max_tokens: int = 1024
    system_prompt: Optional[str] = (
        "You are a helpful assistant. "
        "When using tools, NEVER produce a final answer in the same message as an action. "
        "Follow ReAct: Thought -> Action -> Observation -> Thought -> Final Answer."
    )
    
    @property
    def _llm_type(self) -> str:
        return "sovereign_hub_m4"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        
        # 1. Prepare the Payload
        payload = {
            "prompt": prompt,
            "max_tokens": self.max_tokens,
            "system_prompt": self.system_prompt,
        }

        base_url = self.api_url.rstrip("/")

        # 2. Hit your Local API (Blocking HTTP for simplicity in Agents)
        # Note: Agents often prefer blocking over streaming for logic steps
        try:
            response = requests.post(f"{base_url}/chat", json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result.get("text", "")
        except Exception as e:
            return f"Error communicating with Sovereign Hub at {base_url}: {e}"

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "adapter": self.adapter,
            "api_url": self.api_url,
            "max_tokens": self.max_tokens,
        }
