import asyncio
import json
import logging
import os
import sys
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlparse

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
BLOCKLIST_PATH = ROOT_DIR / "config" / "search_blocklist.json"
FAILURE_PATH = ROOT_DIR / "config" / "search_blocklist_failures.json"
FAILURE_THRESHOLD = 3
FAILURE_WINDOW_SEC = 24 * 60 * 60


def _load_blocklist() -> list[str]:
    try:
        with BLOCKLIST_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [str(item).strip().lower() for item in data if str(item).strip()]
    return []


def _is_blocklisted(url: str, blocklist: list[str]) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    for blocked in blocklist:
        if host == blocked or host.endswith(f".{blocked}"):
            return True
    return False


def _load_failure_state() -> dict:
    try:
        with FAILURE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"domains": {}}
    if isinstance(data, dict):
        return data
    return {"domains": {}}


def _save_failure_state(state: dict) -> None:
    with FAILURE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def _append_blocklist(domain: str) -> None:
    current = _load_blocklist()
    if domain in current:
        return
    current.append(domain)
    with BLOCKLIST_PATH.open("w", encoding="utf-8") as handle:
        json.dump(sorted(set(current)), handle, indent=2)


def _record_failure(url: str) -> None:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return

    state = _load_failure_state()
    domains = state.setdefault("domains", {})
    now = time.time()
    entry = domains.get(host, {"count": 0, "last_ts": 0})

    if now - entry.get("last_ts", 0) > FAILURE_WINDOW_SEC:
        entry = {"count": 0, "last_ts": 0}

    entry["count"] = int(entry.get("count", 0)) + 1
    entry["last_ts"] = now
    domains[host] = entry
    _save_failure_state(state)

    if entry["count"] >= FAILURE_THRESHOLD:
        _append_blocklist(host)
        logger.warning(
            "Auto-blocklisted domain %s after %s browse failures in %ss.",
            host,
            FAILURE_THRESHOLD,
            FAILURE_WINDOW_SEC,
        )
        domains.pop(host, None)
        _save_failure_state(state)


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
        item["browse_error"] = content
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

                blocklist = _load_blocklist()
                filtered = [
                    item for item in web_results if not _is_blocklisted(item.get("url", ""), blocklist)
                ]
                if not filtered:
                    return "No accessible results found on the internet."

                selected = _prioritize_wikipedia(filtered[:num_results])
                sanitized = [_sanitize_result(item) for item in selected]

                tasks = [
                    _fetch_content(item, max_chars)
                    for item in sanitized
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                for item in sanitized:
                    error = item.get("browse_error")
                    if error and error.startswith("[Browser Error:"):
                        _record_failure(item.get("url", ""))

                accessible = [item for item in sanitized if item.get("content")]
                if not accessible:
                    return "No accessible results found on the internet."

                return {"query": query, "results": accessible}

    except Exception as e:
        return f"[Search Exception: {str(e)}]"


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(search_and_browse("All-in podcast"))
    logger.info(result)
