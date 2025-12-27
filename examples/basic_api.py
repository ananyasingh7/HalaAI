import logging

import requests

from app.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8000"

# Load an adapter (use "default" if you have a single adapter in ./adapters/)
requests.post(f"{API_URL}/adapters/load", json={"adapter_name": "default"})

# Ask the question
payload = {
    "prompt": "Analyze the Giants vs Cowboys matchup.",
    "system_prompt": "You are a sharp sports handicapper."
}
response = requests.post(f"{API_URL}/chat", json=payload)

logger.info("Response: %s", response.json())
