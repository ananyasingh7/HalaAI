import os
import json
import logging
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.logging_setup import setup_logging

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")

async def search_brave(query: str, num_results: int = 3) -> str:
    """
    Async search tool that returns a string formatted for the LLM.
    """
    if not BRAVE_API_KEY:
        return "[SYSTEM ERROR: Brave API Key missing. Tell the user to check .env]"

    logger.info("Searching for: '%s'...", query)
    
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "X-Subscription-Token": BRAVE_API_KEY,
        "Accept": "application/json"
    }
    params = {"q": query, "count": num_results}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    return f"[Error: Brave API returned {response.status}]"
                
                data = await response.json()
                
                # Format results into a 'Knowledge Block'
                results_text = "--- INTERNET SEARCH RESULTS ---\n"
                
                web_results = data.get('web', {}).get('results', [])
                if not web_results:
                    return "No relevant results found on the internet."

                for i, item in enumerate(web_results):
                    title = item.get('title', 'No Title')
                    link = item.get('url', '#')
                    snippet = item.get('description', 'No description available.')
                    extra = " ".join(item.get('extra_snippets', []))
                    
                    results_text += f"[{i+1}] {title}\n    Source: {link}\n    Summary: {snippet} {extra}\n\n"
                
                return results_text

    except Exception as e:
        return f"[Search Exception: {str(e)}]"

if __name__ == "__main__":
    import asyncio
    logger.info(asyncio.run(search_brave("Who won the 2024 Super Bowl?")))
