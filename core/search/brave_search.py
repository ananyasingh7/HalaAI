import os
import json
import logging
import sys
from pathlib import Path
from datetime import date
import calendar
import math

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

LIMITS_PATH = ROOT_DIR / "config" / "brave_search_limits.json"
USAGE_PATH = ROOT_DIR / "config" / "brave_search_usage.json"


def _load_json(path: Path, default: dict) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _period_start(today: date, billing_day: int) -> date:
    billing_day = max(1, min(31, billing_day))
    current_day = min(billing_day, _last_day_of_month(today.year, today.month))
    if today.day >= current_day:
        return date(today.year, today.month, current_day)

    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    prev_day = min(billing_day, _last_day_of_month(year, month))
    return date(year, month, prev_day)


def _next_period_start(period_start: date, billing_day: int) -> date:
    billing_day = max(1, min(31, billing_day))
    if period_start.month == 12:
        year, month = period_start.year + 1, 1
    else:
        year, month = period_start.year, period_start.month + 1
    day = min(billing_day, _last_day_of_month(year, month))
    return date(year, month, day)


def _check_quota() -> tuple[str | None, dict | None]:
    limits = _load_json(
        LIMITS_PATH,
        {
            "monthly_limit": 1000,
            "billing_day": 1,
            "daily_limit_strategy": "remaining_per_day",
        },
    )
    today = date.today()
    billing_day = int(limits.get("billing_day", 1))
    period_start = _period_start(today, billing_day)
    next_start = _next_period_start(period_start, billing_day)

    usage = _load_json(USAGE_PATH, {"period_start": period_start.isoformat(), "count": 0, "daily": {}})
    if usage.get("period_start") != period_start.isoformat():
        usage = {"period_start": period_start.isoformat(), "count": 0, "daily": {}}

    monthly_limit = int(limits.get("monthly_limit", 1000))
    count = int(usage.get("count", 0))
    remaining = monthly_limit - count
    if remaining <= 0:
        return f"[Error: Brave API monthly quota reached ({monthly_limit}/{monthly_limit}).]", None

    remaining_days = max(1, (next_start - today).days)
    daily_budget = None
    if limits.get("daily_limit_strategy") == "remaining_per_day":
        daily_budget = max(1, math.ceil(remaining / remaining_days))

    daily = usage.get("daily") or {}
    if daily.get("date") != today.isoformat():
        daily = {"date": today.isoformat(), "count": 0}

    if daily_budget is not None and int(daily.get("count", 0)) >= daily_budget:
        return f"[Error: Brave API daily budget reached ({daily_budget} today).]", None

    usage["daily"] = daily
    return None, usage


def _consume_quota(usage: dict) -> None:
    usage["count"] = int(usage.get("count", 0)) + 1
    daily = usage.get("daily") or {}
    daily["count"] = int(daily.get("count", 0)) + 1
    usage["daily"] = daily
    _save_json(USAGE_PATH, usage)


async def search_brave(query: str, num_results: int = 3) -> str:
    """
    Async search tool that returns a string formatted for the LLM.
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
        "Accept": "application/json"
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
    logger.info(asyncio.run(search_brave("glp novo nordisk")))
