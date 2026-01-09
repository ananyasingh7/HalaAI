import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

import aiohttp
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.logging_setup import setup_logging
from core.search.browser import visit_page
from core.search.brave_search import _check_quota, _consume_quota

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")


def _prioritize_wikipedia(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wiki = []
    non_wiki = []
    for item in results:
        url = (item.get("url") or "").lower()
        if "wikipedia.org" in url:
            wiki.append(item)
        else:
            non_wiki.append(item)
    return wiki + non_wiki


def _is_error_content(text: str) -> bool:
    return text.startswith("[Error:") or text.startswith("[Browser Error:")


def _sanitize_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "url": item.get("url"),
        "description": item.get("description"),
        "extra_snippets": item.get("extra_snippets", []),
        "page_age": item.get("page_age"),
        "age": item.get("age"),
    }


async def _fetch_content(item: dict[str, Any], max_chars: int) -> None:
    page_url = item.get("url")
    if not page_url:
        return
    content = await asyncio.to_thread(
        visit_page, page_url, max_chars=max_chars, include_header=False
    )
    if _is_error_content(content):
        return
    item["content"] = content


async def search_and_browse(
    query: str, num_results: int = 3, max_chars: int = 25000
) -> dict[str, Any] | str:
    """
    Run Brave search and attach parsed page text to each result when available.
    """
    if not BRAVE_API_KEY:
        return "[SYSTEM ERROR: Brave API Key missing. Tell the user to check .env]"

    logger.info("Searching for: '%s'...", query)

    quota_error, usage = _check_quota()
    if quota_error:
        return quota_error

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "X-Subscription-Token": BRAVE_API_KEY,
        "Accept": "application/json",
    }
    params = {"q": query, "count": num_results}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    return f"[Error: Brave API returned {response.status}]"

                data = await response.json()
                if usage is not None:
                    _consume_quota(usage)

                web_results = data.get("web", {}).get("results", [])
                if not web_results:
                    return "No relevant results found on the internet."

                selected = _prioritize_wikipedia(web_results[:num_results])
                sanitized = [_sanitize_result(item) for item in selected]

                tasks = [
                    _fetch_content(item, max_chars)
                    for item in sanitized
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

                return {"query": query, "results": sanitized}

    except Exception as e:
        return f"[Search Exception: {str(e)}]"


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(search_and_browse("All-in podcast"))
    logger.info(result)
